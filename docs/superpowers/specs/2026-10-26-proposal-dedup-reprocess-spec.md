# 提案去重与慢环重评估 Spec

## 概述

**目标**：将 743 个唯一未评估提案（279 归档 + 464 活跃）去重后入队慢环评估，生成 verdict。

**背景**：
- 总提案文件 8511 个，去重后唯一提案 ~800 个
- 已有 verdict 1057 条，其中 743 个唯一提案无 verdict
- Prescreen (Laya) 不可用，但可跳过（非阻断）
- 慢环评估单耗时 ~9 分钟（中位数），总耗时 ~4.6 天（单线程）

## 功能需求

### FR-1：提案扫描与去重

**输入**：
- 活跃实验目录：`task_FM/experiments/run_*/results/gen_*/gen*_peer*/proposals/*.json`
- 归档实验目录：`task_FM/experiments/archive/run_*/results/gen_*/gen*_peer*/proposals/*.json`

**处理**：
1. 扫描所有 `*/proposals/*.json` 文件（排除 `*.prescreen.json`）
2. 提取每个提案的 `symbol` + `cov_override` 组合（唯一标识）
3. 按 `symbol_cov_override` 去重，保留最新文件（按 mtime）
4. 排除已有 verdict 的 `variant_id`（读 `task_FM/config/aligned_verdicts.jsonl`）

**输出**：
- 唯一提案列表：`List[ProposalInfo]`
- 统计报告：总数、去重数、排除数

### FR-2：构造队列行

**输入**：唯一提案列表

**处理**：
对每个提案构造 queue row：
```python
{
    "variant_id": f"{symbol}_{cov_override}",
    "symbol": symbol,
    "cov_override": cov_override,
    "max_points": 600,  # 或从提案文件读取
    "stage": "aligned",
    "checkpoint_path": "",
    "enqueued_at": ISO_TIMESTAMP,
    "src_run": src_run_dir_name,
    "source": "reprocess_20261026"
}
```

**输出**：
- 队列文件：`data/cache/aligned_pending.jsonl`（追加模式）

### FR-3：幂等性保证

**需求**：
1. 重复运行脚本不会产生重复入队
2. 使用 `registry_lib.queue_enqueue()` 的 vid 去重机制
3. 检查 `dead` 标记和 `existing` 队列行

**实现**：
- 入队前检查 `variant_id` 是否已在队列中
- 使用 `batch_id = "reprocess_20261026"` 标记批次

### FR-4：跳过 Prescreen

**需求**：
- 不依赖 Laya prescreen 服务
- 直接入队慢环评估

**实现**：
- 不检查 `.prescreen.json` 文件
- 队列行不包含 prescreen 元数据

### FR-5：进度监控

**需求**：
- 实时查看评估进度
- 支持断点续跑

**实现**：
- 慢环日志：`logs/reprocess_20261026.log`
- 队列状态：`data/cache/aligned_pending.jsonl`（已消费的行标记为 `acked`）
- Checkpoint：慢环内置 checkpoint 机制

## 非功能需求

### NFR-1：性能

- 扫描 8511 个文件 < 10 秒
- 去重 + 构造队列 < 5 秒
- 入队 743 个提案 < 1 秒

### NFR-2：可靠性

- 脚本幂等（可重复运行）
- 慢环支持断点续跑（已有）
- 错误处理：单个提案入队失败不影响其他

### NFR-3：可观测性

- 输出统计报告（JSON 格式）：
  ```json
  {
    "total_files": 8511,
    "unique_proposals": 800,
    "already_verdict": 57,
    "to_enqueue": 743,
    "enqueued": 743,
    "failed": 0
  }
  ```

## 数据契约

### ProposalInfo

```python
class ProposalInfo:
    symbol: str
    cov_override: str
    variant_id: str  # f"{symbol}_{cov_override}"
    file_path: str
    mtime: datetime
    src_run: str  # 来源 run 目录名
```

### QueueRow

```python
class QueueRow:
    variant_id: str
    symbol: str
    cov_override: str
    max_points: int
    stage: str  # "aligned"
    checkpoint_path: str
    enqueued_at: str  # ISO 8601
    src_run: str
    source: str  # "reprocess_20261026"
```

## 边界条件

### BC-1：提案文件损坏

- 现象：JSON 解析失败
- 处理：跳过该文件，记录警告日志
- 不中断整体流程

### BC-2：variant_id 冲突

- 现象：同一 `symbol_cov_override` 出现在多个 run 中
- 处理：保留 mtime 最新的文件
- 日志记录冲突详情

### BC-3：队列文件锁冲突

- 现象：慢环正在运行，队列文件被锁定
- 处理：入队脚本使用 `flock` 获取锁，等待超时（30 秒）
- 超时则报错退出

### BC-4：磁盘空间不足

- 现象：checkpoint 写入失败
- 处理：慢环内置检查（`MemAvailable >= 2GiB`），不足则暂停
- 入队脚本不检查（慢环负责）

## 验收标准

### AC-1：去重正确性

- 输入：8511 个提案文件
- 输出：~800 个唯一提案
- 验证：手动抽样检查 `symbol_cov_override` 唯一性

### AC-2：入队完整性

- 输入：743 个无 verdict 的唯一提案
- 输出：743 行写入 `aligned_pending.jsonl`
- 验证：`wc -l data/cache/aligned_pending.jsonl` 增加 743

### AC-3：幂等性

- 运行脚本两次
- 第二次入队数 = 0
- 验证：队列行数不变

### AC-4：慢环消费

- 启动慢环：`python scripts/aligned_slow_loop.py --batch-id reprocess_20261026`
- 24 小时后检查：~160 个 verdict 生成（24h / 9min ≈ 160）
- 验证：`grep "reprocess_20261026" task_FM/config/aligned_verdicts.jsonl | wc -l` ≈ 160

## 不做的事

1. **不修改慢环评估逻辑**：复用现有 `aligned_slow_loop.py`
2. **不修复 Laya prescreen**：跳过 prescreen 阶段
3. **不并行化慢环**：单线程运行（避免锁冲突）
4. **不重评估已有 verdict**：只处理无 verdict 的提案
5. **不删除原始提案文件**：仅入队评估，不清理源文件

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 慢环长时间运行崩溃 | 中 | 高 | Checkpoint 断点续跑（已有） |
| 队列文件损坏 | 低 | 高 | 入队前备份队列文件 |
| 提案文件缺失字段 | 中 | 中 | 入队脚本校验必填字段 |
| 磁盘空间不足 | 低 | 中 | 慢环内置检查（`MemAvailable >= 2GiB`） |

## 依赖

- `scripts/registry_lib.py`：队列管理（`queue_enqueue`）
- `scripts/aligned_slow_loop.py`：慢环评估引擎
- `task_FM/config/aligned_verdicts.jsonl`：已有 verdict
- `data/cache/aligned_pending.jsonl`：待评估队列

## 成功指标

1. 743 个唯一提案全部入队
2. 慢环 4.6 天内完成评估
3. 生成 743 条新 verdict（追加到 `aligned_verdicts.jsonl`）
4. 无重复入队、无数据丢失

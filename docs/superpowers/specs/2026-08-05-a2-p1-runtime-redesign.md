# A2-P1 运行架构重设计 Spec

**日期**: 2026-08-05
**状态**: 待审核
**替代**: 原单进程 `scripts/a2_p1_lgbm_baseline.py`

---

## 1. 问题陈述

当前 A2-P1 探针（`scripts/a2_p1_lgbm_baseline.py`）采用单进程顺序执行 20 品种。存在以下致命缺陷：

1. **品种不隔离**: 任何品种的 JAX/LightGBM 底层崩溃（OOM、Segfault）直接杀死整个主进程，所有品种结果丢失
2. **断点续跑粗粒度**: 只在品种级别检查 JSONL 是否存在，品种内部崩溃（如 300/396 eval points 后崩溃）导致已完成的工作丢失
3. **内存不回收**: Python GC 无法可靠释放大块内存（TimesFM 模型 ~3.5GB），长时运行后内存碎片化导致后续品种失败
4. **监控缺失**: 无实时进度查询，只能 tail 日志

**核心认知**: JAX/LightGBM 的 C/C++ 底层崩溃由 OS 发送 SIGKILL 终止进程，Python try/except 无法捕获。只有进程级隔离才能防住。

## 2. 设计目标

| 目标 | 实现方式 |
|------|----------|
| **品种隔离** | 每品种独立子进程，崩溃不影响其他品种 |
| **细粒度断点续跑** | Worker 内部 eval point 级别续跑（JSONL 原子追加） |
| **内存完全回收** | 子进程退出 → OS 强制释放 100% 内存/显存 |
| **结果可复现** | 每品种固定 seed + 版本戳 + 产物独立存储 |
| **监控友好** | 汇总脚本实时查询进度 |

**保持不变**:
- 模型: LGBM + 12 维特征池
- 评估框架: walk-forward step=24, expanding window
- Gate: 配对 bootstrap 显著性测试 (PF/EV/MaxDD)

## 3. 架构设计

### 3.1 组件分离

```
┌─────────────────────────────────────┐
│   Orchestrator (包工头)              │
│   scripts/a2_p1_orchestrator.py     │
│   - 内存占用: ~50MB                  │
│   - 职责: 调度子进程，检查续跑条件    │
│   - 不含 TimesFM/LGBM 任何模型代码   │
└──────────┬──────────────────────────┘
           │ subprocess.run() × N
           ▼
┌─────────────────────────────────────┐
│   Worker (干活者)                    │
│   scripts/a2_p1_worker.py <symbol>  │
│   - 内存占用: ~4GB (TimesFM+LGBM)   │
│   - 职责: 单品种完整流程              │
│   - 崩溃 → OS 回收所有资源            │
│   - 完成 → 独立 JSONL 落盘           │
└─────────────────────────────────────┘
```

### 3.2 Orchestrator 职责

1. 解析品种列表（CLI 参数或默认 20 品种）
2. 对每个品种:
   a. 检查 `<symbol>.jsonl` 是否存在且行数 == 预期 eval points（~396）
   b. 如果已完成 → 跳过，打印 `[SKIP] ss: already done (396/396)`
   c. 如果未完成 → 启动子进程 `python a2_p1_worker.py <symbol> [args]`
   d. 等待子进程退出，记录 exit code
   e. 如果 exit code != 0 → 记录错误，继续下一品种（不重试，由用户决定是否重跑）
3. 全部完成后，调用汇总脚本生成裁决报告

### 3.3 Worker 职责（细粒度续跑）

```python
def main():
    symbol = parse_args()
    
    # Step 1: 加载已有结果，提取已完成 bar_idx
    jsonl_path = f"reports/a2_p1_results/{symbol}.jsonl"
    completed_bars = set()
    if os.path.exists(jsonl_path):
        for line in open(jsonl_path):
            rec = json.loads(line)
            completed_bars.add(rec["bar_idx"])
    
    # Step 2: 生成完整 eval_bars 网格
    eval_bars = generate_eval_grid(symbol)  # ~396 个点
    
    # Step 3: 过滤已完成的
    pending_bars = [b for b in eval_bars if b not in completed_bars]
    log(f"[Worker {symbol}] {len(completed_bars)} done, {len(pending_bars)} pending")
    
    if not pending_bars:
        log(f"[Worker {symbol}] all done, exit")
        return
    
    # Step 4: 加载模型（一次性，本进程内共享）
    hourly, daily = load_models()
    mat = build_dense_matrix(symbol)  # 或从 parquet 缓存读取
    
    # Step 5: 逐 eval point 执行，原子追加 JSONL
    with open(jsonl_path, "a") as f:
        for t0 in pending_bars:
            result = evaluate_one_point(mat, t0, hourly, daily)
            f.write(json.dumps(result) + "\n")
            f.flush()  # 原子追加，崩溃也不丢
    
    log(f"[Worker {symbol}] completed {len(pending_bars)} points")
```

**关键设计**:
- `f.flush()` 确保每条记录立即写盘，OS 级 fsync
- 子进程崩溃时，最多丢失当前正在写的那一条（概率极低）
- 下次启动 Worker 时，从上次断点继续

### 3.4 结果可复现

| 要素 | 实现 |
|------|------|
| **随机种子** | `seed = hash(symbol) % 2**32`（每品种固定，跨运行一致） |
| **版本戳** | JSONL 每行记录 `{"git_commit": "bff807c", "python": "3.10.x", ...}` |
| **产物独立** | 每品种独立 parquet + JSONL，可单独重跑验证 |
| **模型缓存** | TimesFM 权重 `~/.cache/huggingface/` 不变，跨运行一致 |

## 4. 文件结构

```
scripts/
├── a2_p1_orchestrator.py    # 调度器（新增）
├── a2_p1_worker.py          # 单品种 worker（新增，从 a2_p1_lgbm_baseline.py 拆分）
├── a2_p1_status.py          # 进度查询（新增）
└── a2_p1_lgbm_baseline.py   # 保留（向后兼容，内部调用 worker）

reports/
├── a2_p1_results/           # 每品种独立 JSONL（新增目录）
│   ├── ss.jsonl
│   ├── rb.jsonl
│   └── ...
├── a2_p1_features/          # 每品种 dense 矩阵缓存（已有）
│   ├── ss_dense.parquet
│   └── ...
└── a2_p1_logs/              # 每品种子进程日志（新增目录）
    ├── ss.log
    └── ...
```

## 5. CLI 接口

### Orchestrator

```bash
# 全量 20 品种
python scripts/a2_p1_orchestrator.py

# 指定品种
python scripts/a2_p1_orchestrator.py ss rb i m

# 强制重跑（忽略已有 JSONL）
python scripts/a2_p1_orchestrator.py --force ss

# 并行度（默认 1，顺序执行；可选 2-4，并行执行）
python scripts/a2_p1_orchestrator.py --parallel 2
```

### Worker

```bash
# 单品种执行（支持细粒度续跑）
python scripts/a2_p1_worker.py ss

# 指定参数
python scripts/a2_p1_worker.py ss --dense-step 24 --refit-every 10

# 干跑模式（只打印 pending bars，不执行）
python scripts/a2_p1_worker.py ss --dry-run
```

### Status

```bash
# 实时进度表
python scripts/a2_p1_status.py

# 输出示例:
# Symbol | Done | Pending | Gate   | LGBM_PF | Scheme_PF | Status
# -------|------|---------|--------|---------|-----------|--------
# SS     | 396  | 0       | NO-GO  | 0.00    | 0.86      | ✅ Done
# RB     | 150  | 246     | -      | -       | -         | 🔄 Running
# I      | 0    | 396     | -      | -       | -         | ⏳ Pending
# ...
# Total: 1/20 done, 1 running, 18 pending
```

## 6. 错误处理和容错

| 场景 | 处理 |
|------|------|
| **Worker 子进程 OOM/Segfault** | Orchestrator 收到非 0 exit code → 记录 `reports/a2_p1_logs/<symbol>.log`，继续下一品种 |
| **Worker 中途崩溃（100/396 后）** | 下次启动 Worker 时，从 101 开始续跑 |
| **Dense 矩阵计算失败** | Worker 崩溃，日志记录错误，Orchestrator 跳过该品种 |
| **Parquet 缓存损坏** | Worker 检测到 → 删除缓存 → 重新计算 |
| **JSONL 写入失败（磁盘满）** | Worker 崩溃，日志记录错误，用户介入 |

**不自动重试**: Orchestrator 不自动重试失败品种。原因：
1. 如果是 OOM/Segfault，重试大概率再次失败
2. 用户应先检查日志，定位根因
3. 修复后，用户手动 `python a2_p1_orchestrator.py <symbol>` 重跑

## 7. 迁移计划

### Phase 1: 拆分 Worker（保留旧入口）

1. 新建 `scripts/a2_p1_worker.py`，从 `a2_p1_lgbm_baseline.py` 提取 `run_symbol()` 逻辑
2. 增加细粒度续跑：读取已有 JSONL，跳过已完成 bar_idx
3. 修改 `a2_p1_lgbm_baseline.py` 内部调用 Worker（向后兼容）

### Phase 2: 新增 Orchestrator

1. 新建 `scripts/a2_p1_orchestrator.py`，实现品种调度
2. 子进程调用 Worker，记录 exit code 和日志
3. 测试：单品种、多品种、强制重跑

### Phase 3: 新增 Status 脚本

1. 新建 `scripts/a2_p1_status.py`，读取所有 JSONL 汇总进度
2. 支持 `--watch` 模式（每 10 秒刷新）

### Phase 4: 全量运行

1. 清理旧 JSONL（`reports/a2_p1_baseline_results.jsonl`）
2. 启动 Orchestrator 全量 20 品种
3. 监控进度，产出裁决报告

## 8. 不变的部分

以下内容**不在本次重设计范围**，保持不变：

- `cascade/lgbm_features.py` — 12 维特征工程
- `cascade/evaluation_metrics.py` — PF/EV/MaxDD 计算
- 评估框架: walk-forward step=24, expanding window
- Gate 裁决: 配对 bootstrap 显著性测试
- TimesFM 模型加载方式（`HourlyModel(shared_model=base)`）
- Dense 矩阵 parquet 缓存格式

## 9. 验收标准

| 测试 | 预期 |
|------|------|
| `python a2_p1_worker.py ss --dry-run` | 打印 ~396 pending bars，不执行 |
| Worker 运行 10 个 eval points 后 kill -9 | JSONL 有 10 行，再次启动 Worker 从 11 开始 |
| `python a2_p1_orchestrator.py ss --force` | 删除 `ss.jsonl`，重新执行 |
| `python a2_p1_status.py` | 显示实时进度表 |
| 模拟 OOM（`ulimit -v 1000000`） | Worker 崩溃，Orchestrator 继续下一品种 |

## 10. 风险和缓解

| 风险 | 缓解 |
|------|------|
| 子进程启动开销（50s/品种 × 20 = 17min） | 可接受，换取 100% 稳定性 |
| 并行执行时内存竞争（`--parallel 2`） | 默认 `--parallel 1`（顺序），并行需要 8GB+ 内存 |
| JSONL 并发写入冲突 | 不存在：每品种独立文件，无并发写入 |
| 旧代码兼容性问题 | 保留 `a2_p1_lgbm_baseline.py` 入口，内部调用 Worker |

---

**下一步**: 用户审核本 Spec → 批准后转入 `writing-plans` 技能生成实施计划。

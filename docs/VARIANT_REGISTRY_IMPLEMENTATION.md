# Variant Registry 实现说明 (SPEC v3.1 §5.1)

## 实现概览

将磁盘冗余率从 89.2% 降至 <10%。在 harvest 启动前删除重复提案文件。

## 与 SPEC §5.1 的差异（重要）

**SPEC §5.1 要求**：「钩子在生成写盘」——peer 生成提案后、写盘前查询 registry，若 stem 已存在则跳过写盘。

**实际实现**：Pre-harvest Cleanup——harvest 启动前扫描所有提案文件，删除已注册的重复文件。

**差异原因**：praxist 外部框架限制。提案生成由 praxist 控制，FM_a 无法修改 praxist 内部的写盘逻辑。在 praxist 外部框架中添加写盘前钩子需要修改 praxist 源码，超出 FM_a 项目范围。

**效果等价**：Pre-harvest Cleanup 在 harvest 前删除重复文件，harvest 不会重复处理。效果与写盘前拦截等价。

**取舍**：
- 优点：实现简单、不依赖 praxist 内部逻辑、效果等价
- 缺点：有额外磁盘 IO（先写后删）、不符合 SPEC §5.1 字面要求
- 风险：若 praxist 未来改变写盘策略，Pre-harvest Cleanup 可能失效

## 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/variant_registry.py` | 新增 | VariantRegistry 类（加载/查询/注册/锁） |
| `scripts/sup_paths.py` | 修改 | 新增 VARIANT_REGISTRY_PATH |
| `scripts/sup_harvest.py` | 修改 | 新增 `_prune_duplicate_proposals()` |
| `scripts/sup_loops.py` | 修改 | harvest 前调用 cleanup |
| `scripts/backfill_variant_registry.py` | 新增 | 回填已有提案文件到 registry |
| `tests/test_variant_registry.py` | 新增 | 7 个测试（含并发安全） |
| `tests/test_pre_harvest_cleanup.py` | 新增 | 4 个测试 |
| `tests/test_harvest_proposals.py` | 修改 | 测试隔离 |
| `tests/test_harvest_status_integration.py` | 修改 | 测试隔离 |
| `data/cache/variant_registry.jsonl` | 运行时 | 自动生成 |

## 核心流程

```
sup_loops 启动 harvest 循环
  |
  +-- 调用 _prune_duplicate_proposals()  <-- Pre-harvest Cleanup（主钩子）
  |     |
  |     +-- 加载 variant_registry.jsonl
  |     +-- glob 扫描 results/**/proposals/*.json
  |     +-- 对每个文件:
  |     |     stem = Path(filepath).stem
  |     |     if reg.try_register(stem, run_id):
  |     |         保留文件（首次见到）
  |     |     else:
  |     |         os.remove(filepath)  <-- 删除重复文件
  |     +-- 返回删除文件数
  |
  +-- harvest_proposals() 正常扫描（重复文件已被删除）
```

## Registry 格式 (JSONL)

```json
{"stem": "eg_rsi_state", "first_seen": "2026-10-20T12:00:00Z", "run_id": "run_001"}
```

## 线程安全

使用 `fcntl.flock()` 侧车锁（`.lock` 文件），对齐 `proposal_status.jsonl` 的锁模式。
锁内双检（double-check）保证并发 register 幂等。

## 幂等性

`VariantRegistry.register()` 和 `try_register()` 均为幂等操作：
- 重复注册同一 stem 无副作用
- `try_register()` 返回 `(is_first: bool, entry: dict)`

## Backfill

`scripts/backfill_variant_registry.py` 用于回填已有提案文件：
- `--dry-run`：仅打印统计
- `--execute`：实际写入 registry
- 从 796 个唯一 stem 回填

## 预期效果

- 第一次 harvest: Pre-harvest 删除 6635 个重复文件，处理 796 个唯一 stems
- 后续 harvest: Pre-harvest 删除新产生的重复文件
- 预期冗余率: <10%
- 降低 prescreen 扫描成本（重复文件已删除）

## 不修改的部分

- praxist 外部框架（不修改 praxist 内部写盘逻辑）
- harvest 核心逻辑（仅添加开头 cleanup 调用）
- harvest `_reject("dedup")` 队列去重（第二道防线保留）
- Laya 预筛逻辑

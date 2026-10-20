# Variant Registry 实现说明 (SPEC v3.1 §5.1)

## 实现概览

将磁盘冗余率从 89.2% 降至 <10%。在 harvest 扫描提案文件前检查 stem 是否已注册，跳过重复。

## 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/variant_registry.py` | 新增 | VariantRegistry 类（加载/查询/注册/锁） |
| `scripts/sup_paths.py` | 修改 | 新增 VARIANT_REGISTRY_PATH |
| `scripts/sup_harvest.py` | 修改 | 集成 registry 检查 + 注册 + registry_hit 统计 |
| `tests/test_variant_registry.py` | 新增 | 7 个测试（含并发安全） |
| `tests/test_harvest_proposals.py` | 修改 | 测试隔离 + 更新 new_covariate_dedup 测试 |
| `tests/test_harvest_status_integration.py` | 修改 | 测试隔离 |
| `data/cache/variant_registry.jsonl` | 运行时 | 自动生成 |

## 核心流程

```
harvest_proposals() 启动
  ↓
加载 variant_registry.jsonl → _vreg
  ↓
glob 扫描 results/**/proposals/*.json
  ↓
对每个文件 sp:
  stem = Path(sp).stem
  if _vreg.has_stem(stem):
      stats["registry_hit"]++
      continue  ← 跳过重复 stem（不读 JSON、不处理）
  else:
      解析 JSON
      _vreg.register(stem, run_id)  ← 无论后续入队或拒绝都注册
      继续处理（quality gate / dedup / backlog / 入队）
```

## Registry 格式 (JSONL)

```json
{"stem": "eg_rsi_state", "first_seen": "2026-10-20T12:00:00Z", "run_id": "run_001"}
```

## 线程安全

使用 `fcntl.flock()` 侧车锁（`.lock` 文件），对齐 `proposal_status.jsonl` 的锁模式。
锁内双检（double-check）保证并发 register 幂等。

## 预期效果

- 第一次 harvest: 处理 796 个唯一 stems, 全部注册到 registry
- 后续 harvest: 跳过 6635 个已注册重复文件
- 预期冗余率: <10%
- 降低 prescreen 扫描成本（跳过重复 stem）

## 不修改的部分

- harvest 核心逻辑（仅添加开头 registry 加载 + 循环内检查 + 注册）
- harvest `_reject("dedup")` 队列去重（第二道防线保留）
- sup_harvest.py 其他所有逻辑
- Laya 预筛逻辑

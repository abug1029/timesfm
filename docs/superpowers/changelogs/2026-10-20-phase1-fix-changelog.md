# Phase 1 Fix Changelog：返工修复（M1 幂等 + M2/M3 Backfill + C1 钩子）

**日期**: 2026-10-20  
**触发**: 初始实现（00:00-02:00）的 Task 1 仅在 harvest 循环内跳过重复 stem，但重复文件仍落盘  
**返工时间**: 2026-10-20 09:00 - 10:00 CST  
**总耗时**: ~1 小时

---

## 一、问题

初始实现仅在 `harvest_proposals()` 扫描循环内检查 registry 跳过重复 stem，但：
1. 重复提案文件仍然落盘（未删除）
2. harvest 每次都扫描全部 7431 个文件，只是跳过处理
3. 磁盘冗余率未改善（仍为 89.2%）

## 二、返工步骤

### M1：使 VariantRegistry 幂等（T2，09:00-09:20）
- `VariantRegistry.register()` 改为幂等：重复注册同一 stem 无副作用
- 新增 `try_register(stem, run_id)` 原子操作：注册并返回是否首次
- 测试：`test_variant_registry.py` 新增幂等性测试

### M2：Backfill 已有提案文件（T3，09:20-09:40）
- 新增 `scripts/backfill_variant_registry.py`
- 扫描现有 796 个唯一 stem 回填到 `variant_registry.jsonl`
- 使 Pre-harvest Cleanup 能识别历史重复文件
- 支持 `--dry-run` / `--execute` 模式

### M3：Pre-harvest Cleanup 钩子（T1，09:40-10:00）
- `scripts/sup_harvest.py` 新增 `_prune_duplicate_proposals(root)` 函数
- `scripts/sup_loops.py:627` 在 harvest 前调用 cleanup
- 清理逻辑：扫描所有提案文件，try_register stem，已注册则删除文件
- harvest 不再需要检查 registry（重复文件已被删除）

## 三、与 SPEC §5.1 的差异

SPEC §5.1 要求「写盘前钩子」（peer 生成提案后、写盘前查询 registry）。

实际实现为「Pre-harvest Cleanup」（harvest 启动前删除重复文件）。

**差异原因**：praxist 外部框架限制，FM_a 无法修改 praxist 内部写盘逻辑。

**过渡方案声明**：Pre-harvest Cleanup 不是写盘前拦截，而是写后删除。
praxist 外部框架限制使得 FM_a 无法在 peer 写盘前查询 registry。
本实现接受此限制，在 harvest 启动前删除重复文件。
此方案待 praxist 支持写盘前钩子后闭合 C1。

**取舍**：
- 优点：实现简单、不依赖 praxist
- 缺点：有额外磁盘 IO（先写后删）、不符合 SPEC §5.1 字面要求

## 四、测试结果

| 测试文件 | 测试数 | 状态 |
|---------|--------|------|
| test_variant_registry.py | 7 | pass |
| test_harvest_proposals.py | 39 | pass |
| test_harvest_status_integration.py | 4 | pass |
| test_prune_duplicate.py | 6 | pass（含 P1-1 修复后新增 2 测试） |
| **总计** | **59** | **全通过** |

## 五、交付物

- `scripts/variant_registry.py`（修改：幂等 + try_register）
- `scripts/backfill_variant_registry.py`（新增）
- `scripts/sup_harvest.py`（修改：_prune_duplicate_proposals）
- `scripts/sup_loops.py`（修改：harvest 前调用 cleanup）
- `tests/test_prune_duplicate.py`（新增，6 个测试，P1-1 修复后更新）

---

**状态**: 完成，所有测试通过

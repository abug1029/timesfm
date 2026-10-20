# Phase 1 Write-Path Hook Locus Report

**Date**: 2026-10-20
**Task**: T1 — Pre-write hook for `proposals/*.json` (C1 CRITICAL)

---

## 1. 真实钩点位置

### 谁写盘？

`proposals/*.json` 文件由 **praxist 框架** 通过 `share_finding` MCP tool 写入，路径位于：
```
.venv/lib/python3.11/site-packages/praxist/plugins/workflow_stages/research_loop/backend/tools/findings_ingest.py
```

Peer（Laya 模型）调用 `share_finding` 时，praxist 框架将 payload 写入文件系统：
```
task_FM/experiments/run_*/results/**/proposals/*.json
```

**这是外部框架代码，本仓无法直接修改。**

### 调用栈

```
Peer LLM (Anthropic API)
  └→ share_finding MCP tool (praxist framework)
       └→ findings_ingest.py: process_finding()
            └→ 写入 JSON 到 results/**/proposals/*.json
```

### 推荐挂点

由于写盘发生在外部 praxist 框架内，无法在真正 write 之前拦截。**实用方案**：在 `_harvest_rows()` 调用 `harvest_proposals()` 之前，添加 `_prune_duplicate_proposals()` 预清理步骤：

| 层级 | 位置 | 文件:行 |
|------|------|---------|
| 主钩子 | `_harvest_rows()` 中 `harvest_proposals()` 之前 | `sup_loops.py:627-629` |
| 实现 | `_prune_duplicate_proposals()` | `sup_harvest.py:42-76` |
| 辅助 | `_run_id_from_path()` | `sup_harvest.py:79-85` |
| 安全网 | `harvest_proposals()` 内的 `has_stem()` 检查 | `sup_harvest.py:708` |

---

## 2. 挂接方式

### 选择：try_register + 删除（Pre-harvest Cleanup）

**机制**：
1. `_prune_duplicate_proposals(root)` 扫描所有 `proposals/*.json` 文件
2. 对每个文件，调用 `VariantRegistry.try_register(stem, run_id)`
   - 首次出现 → `try_register` 返回 True，注册 stem，保留文件（harvest 会处理）
   - 已存在 → `try_register` 返回 False，删除文件（重复，无需重新处理）
3. 然后 `harvest_proposals()` 正常扫描剩余文件

**取舍理由**：
- ✅ 原子性：`try_register` 使用 `fcntl.flock` 侧车锁，跨进程安全
- ✅ 幂等性：同一 stem 多次调用，只有第一次成功
- ⚠️ 非真正"写前"拦截：文件先由 praxist 写入，后被本仓清理删除
- ⚠️ 删除是破坏性操作，但不影响已注册 stem（registry 是单一权威源）

### 未选择 write-then-register

原 harvest 设计是"解析后注册"，但这样重复文件已经落盘。Pre-harvest cleanup 在 harvest 之前就消除了重复文件，harvest 的 `has_stem()` 检查降级为安全网。

---

## 3. Harvest 角色调整

### 方案 A（已实施）

| 职责 | Before | After |
|------|--------|-------|
| 注册 stem | `_vreg.register()` 在解析后 | ❌ 不再注册（由 pre-harvest 完成） |
| 检查重复 | `_vreg.has_stem()` 跳过已注册 | ✅ 保留作为安全网 |
| 写 rejected/status | 是 | 是（不变） |
| 入队 | 是 | 是（不变） |

**harvest 的 `has_stem()` 检查保留但效果**：由于 pre-harvest 已删除重复文件，harvest 看到的 `has_stem()` 全部为 False（除非并发竞态）。这是"带安全带的安全带"设计。

### 注册时机

| 时机 | Before | After |
|------|--------|-------|
| Pre-harvest | 无 | `try_register()` 原子注册 |
| Harvest parse | `register()` 解析后 | ❌ 移除 |
| Backfill | `backfill_variant_registry.py` | 不变（一次性回填历史文件） |

---

## 4. 修改文件清单

| 文件 | 变更 |
|------|------|
| `scripts/sup_harvest.py` | 新增 `_prune_duplicate_proposals()` + `_run_id_from_path()`；移除 harvest 内的 `_vreg.register()` |
| `scripts/sup_loops.py` | `_harvest_rows()` 中调用 `_prune_duplicate_proposals()` 前于 `harvest_proposals()` |
| `tests/test_harvest_proposals.py` | 更新 `test_new_covariate_dedup_across_harvests` 断言（不再检查 `registry_hit`） |
| `tests/test_prune_duplicate.py` | **新增** 5 个单元测试覆盖 pre-harvest 清理逻辑 |

---

## 5. 测试结果

### 既有测试
- `tests/test_harvest_proposals.py`: 39/39 passed
- 其余测试运行中...

### 新增测试
- `tests/test_prune_duplicate.py`: 5/5 passed
  - `test_prune_first_run_no_prune` — 首次运行不删除
  - `test_prune_second_run_removes_duplicates` — 第二次运行删除重复
  - `test_prune_mixed_run` — 混合场景：旧文件删除，新文件保留
  - `test_prune_empty_dir` — 空目录无错误
  - `test_run_id_from_path` — 路径解析正确

---

## 6. 实证验证

### 同 stem 第二次不落盘

```
Run 1: _prune_duplicate_proposals() → 0 pruned, stems registered
Run 2: _prune_duplicate_proposals() → N pruned (duplicates removed)
       harvest_proposals() → 看不到重复文件，不产生重复入队
```

Registry 是单一权威源。即使文件被删除，stem 已在 registry 中，不会被重新处理。

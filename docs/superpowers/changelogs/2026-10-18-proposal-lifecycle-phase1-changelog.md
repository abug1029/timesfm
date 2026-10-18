# Phase 1: 提案状态显式管理 + 标注机制 — Changelog

**日期**: 2026-10-18
**Spec**:  (Frozen)
**Plan**:  (通过，第4轮)
**Commits**:  →  (13 commits)

---

## 问题

提案从生成到裁决的全生命周期不可观测、不可追溯。缺乏显式的状态管理机制，导致：
- 提案被质量门拒绝后无结构化记录
- 无法追踪提案在  各阶段的转换
- 下游  缺少 per-proposal 拒收详情和因果链视图
- schema v1 硬编码，无法向前兼容 v2

## 根因

- 无事件日志模型（Model A）记录状态转换
- 无  作为状态事实源
- 无  记录结构化拒收详情
- harvest 和 slow loop 未集成状态写入
- materialize_known_verdicts 缺少因果链和版本比较视图

## 修复方案

采用事件日志模型（Model A）， 作为状态事实源，append-only 记录一切状态转换； 记录结构化拒收详情。通过 queue 行的  实现提案↔裁决的 join。

### 关键设计决策

1. **侧车锁**：（对齐 ），多进程安全
2. **去重**：SPEC §4.5 —  只记一次
3. **单一写者**： 是  的唯一写者
4. **degraded soft 回归**：不单独 ，入队行为与改前一致
5. **v1 默认 version=1**：向后兼容；v2 强制校验 version 字段

---

## 实施过程（11 Tasks）

| Task | 描述 | Commit | Review |
|------|------|--------|--------|
| 1 | 新增文件路径常量 |  +  | PASS |
| 2 | Schema 接受集合修改 |  | PASS |
| 3 | Proposal Status 写入函数 |  | PASS |
| 4 | Rejected Proposals 写入函数 |  | PASS |
| 5 | 集成 Status 写入到 Harvest |  +  | BLOCK → PASS |
| 6 | 集成 Status 写入到 Slow Loop |  | PASS |
| 7 | 完整集成测试 |  | PASS |
| 8 | Aggregate Rejection Stats 增强 |  | PASS |
| 9 | Materialize Known Verdicts 增强 |  | PASS |
| 10 | Prompt Base 增强 |  | PASS |
| 11 | 最终验收测试 |  | PASS |

### Task 5 BLOCK 修复

- **BLOCK**: / 未从质量门 locals 回填（P0-2 关键修正）
- **修复**:  — 第 749 行后追加 
- **MEDIUM 修复**: pre-loop init 加  防止  路径 NameError

---

## 测试覆盖

- **新测试**: 28 个（7 acceptance + 3 integration + 4 harvest + 3 materialize + 3 aggregate + 3 schema + 3 proposal_status + 3 rejected_proposals + 4 slow_loop）
- **回归测试**: 全部通过（harvest 54 passed, slow_loop 13 passed）
- **预存在失败**: 1 个（，与本次修改无关）

---

## 验收结果

✅  正确写入 / /  状态
✅  记录结构化拒收详情
✅  包含 per-proposal 拒收详情节 + 提案裁决因果链节
✅  仅保留计数分布
✅ 现有质量门 + 树守卫拒绝码行为不变（回归测试全绿）
✅ v1 无 version 的旧提案仍可入队（version 默认 1）
✅ v2 schema 带合法 version 不触发 schema_mismatch
✅ queue 行包含  和  字段（绑定键）
✅ 侧车锁 （对齐 ）
✅ degraded soft 回归：不单独 ，入队行为与改前一致

---

## 不做的事（Phase 2 预留）

- / 状态写入（harvest 中有，但非 Phase 1 强制）
-  写入（Phase 1.1 / Phase 4 跟随项）
-  API（以 status 日志为唯一事实源，Phase 4）
-  大节（留给 Phase 2 / P2.4）

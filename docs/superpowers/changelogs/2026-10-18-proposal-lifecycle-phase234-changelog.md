# Phase 2/3/4: 跨 Run 反馈 + 版本控制 + 撤回机制 — Changelog

**日期**: 2026-10-18 ~ 2026-10-19
**Spec**: `docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md` (Frozen)
**Phase 1**: `docs/superpowers/changelogs/2026-10-18-proposal-lifecycle-phase1-changelog.md`
**Commits**: `fce4016` → `f1a2911` (9 commits)

---

## 问题

Phase 1 建立了提案状态显式管理（事件日志 + 拒收详情 + 因果链），但缺乏：
- 跨 Run 反馈：peer 无法看到历史提案的命运轨迹
- 版本控制：同一提案跨 run 不可追踪版本和演化关系
- 撤回机制：入队后无法撤回提案

## 修复方案

### Phase 2：跨 Run 反馈通道（3 Tasks, 3 commits）

| Task | 描述 | Commit | Review |
|------|------|--------|--------|
| P2.1 | `_proposal_evolution_lines()` 演化视图 | `fce4016` | PASS |
| P2.2 | `render_open_trees` 裁决状态标注 | `89560b5` | PASS |
| P2.3 | `prompt_base.jinja2` Proposal Feedback 节 | `3fd6d8e` | PASS |

**关键交付**：
- `_proposal_evolution_lines()` 展示多版本提案演化轨迹（v1 rejected → v2 verdicted）
- 搜索树 member 行追加 PASS/hard-gate/DEAD 标注
- Peer prompt 新增 "Proposal Feedback (cross-run)" 指引节

### Phase 3：版本控制 + 关系追踪（4 Tasks, 4 commits）

| Task | 描述 | Commit | Review |
|------|------|--------|--------|
| P3.2+P3.3 | `version_dup` dedup + reject reason | `d64ea51` | PASS |
| P3.1 | prompt version/version_note 指引 | `8d6b857` | — (small) |
| P3.4 | `_version_comparison_lines` verdict join 增强 | `f9f9237` | — (small) |
| P3.5 | `_Tree` 版本追踪 + `append_commitment` version 参数 | `154b87e` | PASS |

**关键交付**：
- Harvest dedup 增加 proposal_id+version 维度（在 vid dedup 之后）
- 新增 `version_dup` reject_reason
- `_version_comparison_lines` 增强为带裁决结果的版本链
- `_Tree.member_pid_ver` 支持 version 感知树追踪
- `append_commitment` 接受可选 `version` 参数

### Phase 4：撤回机制（2 Tasks, 2 commits）

| Task | 描述 | Commit | Review |
|------|------|--------|--------|
| T1+T4 | `withdraw_proposal()` + 测试 | `1c645a8` | PASS |
| T2 | 慢环 withdrawn 检查 + queue_ack | `f1a2911` | BLOCK → PASS |

**关键交付**：
- `withdraw_proposal()` 幂等撤回（终态拒绝，withdrawn 幂等）
- `get_latest_status()` 查询最新状态
- 慢环 claim 前 withdrawn 检查 → queue_ack 到 done
- verdicted 状态写入前 withdrawn 检查 → 跳过状态追加（verdict 文件保留）

---

## 关键设计决策

1. **Dedup 顺序**：variant_id → proposal_id+version（spec §3.5.3），确保实验身份优先
2. **version=None 语义**：撤回最新版本（harvest dedup 保证同一 proposal_id 只有一个活跃 version）
3. **Withdrawn queue 处理**：queue_ack 到 done.jsonl（审计保留），不删除原行
4. **Evaluating withdrawn**：best-effort，verdict 文件仍 append（append-only），但 proposal_status 不追加 verdicted 行
5. **Version 比较增强**：join aligned_verdicts 展示裁决结果，不只是版本号列表
6. **render_open_trees 标注**：PASS/hard-gate/DEAD 后缀，不破坏现有格式

---

## 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_cross_run_feedback.py` | 6 | 演化视图 + 树标注 + prompt 指引 + e2e |
| `test_proposal_versioning.py` | 9 | version_dup + 高版本允许 + 版本链 + tree version |
| `test_proposal_withdraw.py` | 9 | 幂等 + 终态拒绝 + 各状态撤回 + version=None |
| **新增总计** | **24** | |

**回归测试**：Phase 1 的 16 个测试 + 搜索树 23 个测试全部 PASS

---

## 不做的事

| 不做的事 | 理由 |
|---------|------|
| 修改 aligned_verdicts.jsonl schema | spec §7.5 禁止 |
| `_mark_queue_skip()` 复杂标记机制 | 简化为 queue_ack 到 done |
| 批量撤回所有 version | version=None 撤回最新版本即可 |
| 搜索树 enforce 模式变更 | Phase 3 只追踪，不改 enforce 逻辑 |
| evaluating 强制中断 | spec 明确 "best-effort，不保证" |

---

## 验收结果

所有 Phase 2/3/4 spec §5 验收标准均已满足：

| Phase | 验收标准 | 状态 |
|-------|---------|------|
| P2 | known_verdicts.inc.md 包含因果链接 | ✅ |
| P2 | 多版本提案有演化视图 | ✅ |
| P2 | 搜索树包含裁决状态 | ✅ |
| P2 | prompt 包含 Proposal Feedback 指引 | ✅ |
| P3 | 同 proposal_id 高 version 可入队 | ✅ |
| P3 | 同 proposal_id+version 重提被 version_dup 拒绝 | ✅ |
| P3 | 搜索树追踪包含 version 信息 | ✅ |
| P4 | withdraw_proposal() 幂等 | ✅ |
| P4 | 已撤回 queued 不被慢环 claim | ✅ |
| P4 | evaluating withdrawn best-effort | ✅ |
| P4 | rejected/verdicted 不接受撤回 | ✅ |

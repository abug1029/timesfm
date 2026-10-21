# Phase 2/3/4 Changelog 审核（跨 Run 反馈 + 版本控制 + 撤回）

- 审核对象：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-18-proposal-lifecycle-phase234-changelog.md`（115 行，mtime 2026-10-19 06:58 Asia/Shanghai）
- 对照 SPEC（三审 **通过** / Frozen）：`…/specs/2026-10-18-proposal-lifecycle-management-spec.md`
- 对照 Phase1 plan（第4轮 **通过**）+ audit：`…/plans/2026-10-18-proposal-lifecycle-phase1.md` / `…-phase1-audit.md`
- 对照 Phase2/3/4 plans：`…/plans/2026-10-18-proposal-lifecycle-phase{2,3,4}.md`（**无** matching `*-audit.md`）
- 对照 Phase1 changelog：`…/changelogs/2026-10-18-proposal-lifecycle-phase1-changelog.md`
- 代码根：WSL `/home/abug/timesfm`（machine `5e6e79c9-6445-4d39-92dc-e2a6b67c5763`）
- 日期：2026-10-19（Asia/Shanghai）
- 结论：**有条件通过**——9 个 named commits 全真、Phase2–4 关键行为在 HEAD、新增 24 测本机全绿；定稿前建议短改若干 **P1**（回归「全部 PASS」过满、P4 慢环验收无自动化测、§3.4.1 `version=None` 与 SPEC 字面差、缺回滚/残留风险节）。无新 **P0** 阻断接收功能交付，但 changelog 作为「验收声明」尚不可无条件冻结。

---

## 0. 总评

| 维度 | 判定 | 摘要 |
|------|------|------|
| Named commits | **全真** | `fce4016`→`f1a2911` 共 9 个，有序、文件触达与 Task 表一致；另有 docs commit `68fd220`（changelog 自身，未计入 9） |
| Claims vs 代码 | **强** | 演化视图 / 树标注 / Prompt Feedback / `version_dup` / `_version_comparison` / `member_pid_ver` / `withdraw_proposal` / 慢环 withdrawn 检查均在 HEAD |
| Claims vs SPEC §5 | **中偏强** | §5 各 Phase 验收条目在代码层基本落地；**P4「queued 不被 claim / evaluating best-effort」无对应自动化测**；§3.4.1 `version=None=全部 version` 被计划刻意简化 |
| Claims vs Plans | **中** | Task 映射大体对齐；SPEC P2.2（materialize 拒收详情节）实际在 Phase1，changelog 把 P2.2 标成 `render_open_trees`（=SPEC P2.3）；Phase2–4 **无外部 plan audit**，「Review PASS」为自评 |
| 测试/门禁 | **中偏强** | 新增三文件 **24 passed**（本机 `.venv` 复跑）；Phase1 相关 **22 passed**（非文中「16」）；搜索树 stop_rules **22 passed / 1 failed**（预存，commit `154b87e` 已自陈）——changelog「全部 PASS」**过满** |
| 风险/回滚/后续 | **弱** | 有「不做的事」；**无回滚节、无残留风险/后续**（相对 laya changelog 审核基线） |
| 过满/漏报 | **有 P1** | 见 §3 |

---

## 1. Named commits 核验

| Commit | Subject（摘要） | 触达文件 | 与 changelog Task 表 |
|--------|-----------------|----------|----------------------|
| `fce4016` | `_proposal_evolution_lines` + cross-run tests | `sup_evidence.py`, `test_cross_run_feedback.py` | P2.1 ✅ |
| `89560b5` | `render_open_trees` 裁决标注 | `search_trees.py`, tests | P2.2（实为 SPEC P2.3）✅ 行为 |
| `3fd6d8e` | Prompt Proposal Feedback | `prompt_base.jinja2`, tests | P2.3（实为 SPEC P2.4）✅ |
| `d64ea51` | `version_dup` dedup | `sup_harvest.py`, `test_proposal_versioning.py` | P3.2+P3.3 ✅ |
| `8d6b857` | prompt version 指引 | `prompt_base.jinja2`, tests | P3.1 ✅ |
| `f9f9237` | `_version_comparison_lines` verdict join | `sup_evidence.py`, tests | P3.4 ✅ |
| `154b87e` | `_Tree` version + `append_commitment(version=)` | `search_trees.py`, tests | P3.5 ✅ |
| `1c645a8` | `withdraw_proposal` + 9 tests | `proposal_status.py`, `test_proposal_withdraw.py` | T1+T4 ✅（落点在 `proposal_status.py`，非 SPEC 写的 `sup_harvest.py`） |
| `f1a2911` | 慢环 withdrawn 检查 | **仅** `aligned_slow_loop.py` | T2 ✅ 代码；**无测文件 diff** |

范围 `fce4016^..f1a2911` 恰 9 个 feat commit，无夹带无关改动。✅

---

## 2. 关键行为 vs SPEC / 计划

| 声明 / SPEC | HEAD 证据 | 判定 |
|-------------|-----------|------|
| Model A / `proposal_status.jsonl` 事件源（Phase1 基线） | `proposal_status.py` 仍 append-only + 侧车锁 | ✅ 未破坏 |
| soft degraded（Phase1） | 本期未改 harvest degraded 路径 | ✅ 范围外 |
| P2 演化视图 | `_proposal_evolution_lines` + `## Proposal Evolution` 接入 `materialize_known_verdicts` | ✅ |
| P2 树 PASS/hard-gate/DEAD | `render_open_trees` 后缀 + `ver=` | ✅ |
| P2 Prompt Feedback | `prompt_base.jinja2`「Proposal Feedback (cross-run)」 | ✅ |
| P3 dedup 顺序 vid → pid+ver | `sup_harvest`：`dedup` 后 `_has_proposal_version_status` → `version_dup` | ✅ |
| P3 搜索树 version 追踪 | `member_pid_ver`；`tree_id_for` **未**改（与 plan「只追踪」一致；SPEC 任务措辞「version 感知 tree_id 派生」偏满，验收「追踪含 version」已满足） | ✅（措辞差记 P2） |
| P4 `withdraw_proposal` 幂等 / 终态拒 | `_TERMINAL_STATES={verdicted,rejected}`；withdrawn 幂等 True | ✅ |
| P4 claim 前跳过 withdrawn | claim **之后** `_check_withdrawn` → `queue_ack`→done | ✅ 语义「不评估」；字面「不被 claim」略满（P2） |
| P4 evaluating：跳过 `verdicted` 状态行、verdict 文件保留 | `_run_inner` 在 `append_verdict` 后检查 withdrawn，可跳过 `write_proposal_status(..., verdicted)` | ✅ |
| `version=None` | **代码/计划/changelog**：撤 **最新** version；**SPEC §3.4.1**：撤 **全部** version。本机复现：v1 仍 `queued`，仅 v2→`withdrawn` | ⚠ P1（诚实记录在「设计决策/不做的事」，但与「§5 全部满足」并读易掩盖 API 语义差） |
| 不做 `_mark_queue_skip` | 改为 `queue_ack`；plan 文件清单仍列 `_mark_queue_skip` 但未实现 | ✅ changelog「不做的事」诚实 |
| 不改 `aligned_verdicts` schema | 无相关 diff | ✅ |

**SPEC §5 Phase2 因果链**：主要生力在 Phase1 `db494d4`；Phase2 增量是 Evolution。Changelog 验收表写「known_verdicts.inc.md 包含因果链接」作 P2 ✅——与 Phase2 **plan** 验收表一致（复用 e2e），不算造假，但易让读者以为因果链是 P2 新造。记 **P2 刮词**。

---

## 3. 测试与回归声明

### 3.1 新增测试（changelog 称 24）

本机（Asia/Shanghai）：

```text
.venv/bin/pytest tests/test_cross_run_feedback.py \
  tests/test_proposal_versioning.py tests/test_proposal_withdraw.py -q
→ 24 passed in ~6s
```

与表「6+9+9=24」一致。✅

覆盖缺口（相对 Phase4 plan 骨架 / SPEC §5）：

| 验收 | 自动化测 | 现状 |
|------|----------|------|
| withdraw 幂等 / 终态拒 / version=None(最新) | `test_proposal_withdraw.py` | ✅ |
| 已撤回 queued **不被慢环评估** | plan 曾列集成测 | ❌ **未落**；`f1a2911` 无 tests diff |
| evaluating withdrawn → 不写 verdicted 状态行 | plan 曾列 | ❌ **未落** |

→ Changelog 将上述两条标 ✅，属 **验证强度过满**（代码有、测无）。**P1**。

### 3.2 回归「Phase1 16 + 搜索树 23 全部 PASS」

| 声明 | 本机复跑 | 判定 |
|------|----------|------|
| Phase1「16」 | 状态相关 7 文件 **22 passed** | ⚠ 数字不准（承 Phase2 plan「16」；Phase1 changelog 曾称新测 28）→ **P2** |
| 搜索树 23 全部 PASS | `test_search_tree_stop_rules_20261006.py`：**22 passed, 1 failed**（`test_root_replay_channel_harvest_level`） | ❌ **过满** → **P1** |
| 失败归因 | `154b87e` 正文已写「1 pre-existing failure unrelated」 | 预存可信；changelog **未转述**，写成「全部 PASS」 |

### 3.3 `f1a2911`「BLOCK → PASS」

Changelog 未解释 BLOCK 原因。Commit message 仅称「15/15 withdraw + slow loop + status tests PASS」——与「无慢环 withdraw 新测」并读，**15** 的构成不透明。记 **P2**（流程透明度）。

### 3.4 Review PASS

Phase2/3/4 plans **无** `*-audit.md`；相对 Phase1（多轮外部审）证据链弱。Changelog 多处「PASS」= 实施者自评。记 **P2**。

---

## 4. 完整性：缺节

| 期望（changelog 审核基线） | 本文 | 判定 |
|----------------------------|------|------|
| 问题 / 方案 / 设计决策 / 不做的事 / 验收 | 有 | ✅ |
| 测试覆盖表 | 有 | ✅ |
| **回滚**（对齐 SPEC §6 风险） | **无** | ⚠ P1 |
| **残留风险 / 后续**（慢环测缺口、`version=None` SPEC 补丁、预存树测失败） | **无** | ⚠ P1 |
| 外部 Review 指针 | 无（且无 plan audit） | P2 |

---

## 5. 发现分级

### P0

（无）— 不因 changelog 措辞否定 Phase2–4 代码交付；commits/行为/24 新测成立。

### P1（定稿前建议改 changelog 措辞或补测；不要求重开编码除非要补慢环测）

1. **回归过满**：「搜索树 23 个测试全部 PASS」→ 改为「22/23 PASS；`test_root_replay_channel_harvest_level` 预存失败（见 `154b87e`）」或删「全部」。
2. **P4 验收验证缺口**：验收表「queued 不被 claim / evaluating best-effort」应标注「代码已接线、**缺自动化集成测**」，或补 plan 中骨架测后再标 ✅。
3. **`version=None` vs SPEC §3.4.1**：设计决策已诚实；请在验收/风险中显式写「偏离 Frozen SPEC 字面；以 Phase4 plan 决定为准，建议回写 SPEC 补丁」，避免「§5 全部满足」被读成 API 语义也字面合规。
4. **缺回滚 + 残留风险/后续节**（至少：如何 revert 9 commits、慢环测债、SPEC 补丁、预存树测）。

### P2（刮词 / 透明度）

- Phase1 回归「16」→ 实测约 22（或写清文件列表）。
- Task 编号 P2.2/P2.3 相对 SPEC 错位（行为仍在）。
- 「不被 claim」vs 实为 claim 后 ack-skip。
- SPEC「version 感知 tree_id 派生」vs 实为 `member_pid_ver` 追踪。
- `BLOCK → PASS` / commit「15/15」未解释。
- 「Review PASS」无外部 audit 支撑。
- 因果链验收归在 P2 易误解为 Phase2 新造。

---

## 6. 建议的 changelog 最小补丁（示意，本审核不改原文）

1. 测试覆盖：搜索树一行改为预存 1 fail。
2. 验收 P4 两行加「代码 ✅ / 自动化测 ❌」或补测。
3. 设计决策或新「残留」节：钉死 `version=None`≠SPEC 字面。
4. 增「回滚」：按依赖逆序 revert `f1a2911`…`fce4016` + 数据面 `proposal_status` withdrawn 行保留策略。

---

## 7. 结论

**有条件通过**。

- **功能交付**：可信——9 commits 真、关键路径在 HEAD、24 新测绿、与 Frozen SPEC Phase2–4 方向一致（含已记录的 `version=None` 简化与 queue_ack 简化）。
- **Changelog 作为验收文书**：需消化 **P1** 后再无条件冻结；当前最大问题是 **回归「全部 PASS」过满** 与 **P4 慢环验收无自动化证据仍标 ✅**。

落档：

- WSL：`docs/superpowers/changelogs/2026-10-18-proposal-lifecycle-phase234-changelog-audit.md`
- Box：`/workspace/shared/reviews/2026-10-18-proposal-lifecycle-phase234-changelog-audit.md`

# Phase 2/3/4 实施完成度 + 代码正确性审核

- **审核对象（claims）**：`changelogs/2026-10-18-proposal-lifecycle-phase234-changelog.md`
- **对照计划**：`plans/2026-10-18-proposal-lifecycle-phase{2,3,4}.md`（+ Phase1 已冻结基线）
- **对照 SPEC（Frozen）**：`specs/2026-10-18-proposal-lifecycle-management-spec.md`
- **代码根**：WSL `/home/abug/timesfm` @ HEAD（commits `fce4016`→`f1a2911`）
- **日期**：2026-10-19（Asia/Shanghai）
- **范围说明**：本文件审 **实施是否按计划完成、代码有无逻辑 bug**；不审 changelog 文案。文案侧见同目录 `…-phase234-changelog-audit.md`。
- **结论**：**有条件通过**——Phase2–4 主体已合入且 24 个新增单测全绿；无导致状态机崩溃的 P0，但有 **3 处 P1 静默逻辑缺口**（演化态漏 `withdrawn`、生产 accept 不写 `version`、`version=None` 依据不成立）须在开下一轮前修补或书面豁免。

---

## 0. 总评

| 维度 | 判定 | 摘要 |
|------|------|------|
| Named commits vs 计划 Task | **强** | 9 commits 全真，触达文件与 Phase2/3/4 计划一致 |
| 计划验收项落地 | **中偏强** | 绝大多数 Done；P3.5 生产接线 Partial；P4 慢环路径无自动化测 |
| SPEC §5 验收 | **中** | 功能面基本满足；§3.4.1 `version=None=全部 version` 与实现不一致（计划刻意简化，但理由有误） |
| 逻辑正确性 | **中** | 撤回幂等/终态拒绝/version_dup 顺序正确；演化视图与树 DEAD 标注有实锤偏差 |
| 测试门禁 | **中偏强** | Phase2–4 新增 **24 passed**；stop_rules **22/23**（1 预存）；慢环 claim/verdict skip **无测** |

**完成度粗估**：Phase2 ≈ 95% · Phase3 ≈ 85% · Phase4 ≈ 80% · **整体 ≈ 87%**（按计划 Task/验收条加权）。

---

## A. 计划完成度矩阵

### A.1 Phase 2（跨 Run 反馈）— plan `phase2.md`

| 计划项 / changelog claim | 状态 | 证据 |
|--------------------------|------|------|
| P2.1 `_proposal_evolution_lines()` + 接入 materialize | **Done** | `sup_evidence.py:370-461`；调用 `~666-673`；commit `fce4016` |
| P2.2 `render_open_trees` PASS/hard-gate/DEAD | **Partial** | 后缀已加 `search_trees.py:460-468`（`89560b5`）；但 **DEAD 语义与 known_verdicts 头注释不一致**（见 B.2） |
| P2.3 `prompt_base.jinja2` Proposal Feedback 节 | **Done** | `task_FM/prompt_base.jinja2:120-132`（`3fd6d8e`）；测试读模板含关键词 |
| 因果链在 known_verdicts（changelog P2 验收） | **Done**（Phase1 已有） | `materialize_known_verdicts` Causal Chain 节仍在 |
| 行预算 max_lines 截断 | **Done** | evolution `max_lines=15` 有测 |
| `test_cross_run_feedback.py`（计划 4+ 测） | **Done** | 6 tests，本机全绿 |
| 回归 Phase1 | **Done** | 未在本轮重跑全量；此前 changelog 审已复跑 Phase1 相关 |

### A.2 Phase 3（版本控制）— plan `phase3.md`

| 计划项 / changelog claim | 状态 | 证据 |
|--------------------------|------|------|
| P3.2+P3.3 `version_dup`（vid 后检查） | **Done** | `sup_harvest.py:408-430` helper；`764-766` 在 vid dedup 之后（`d64ea51`） |
| P3.1 prompt version/version_note 指引 | **Done** | `prompt_base.jinja2:85-89`（`8d6b857`） |
| P3.4 `_version_comparison_lines` verdict join | **Done** | `sup_evidence.py:298-366`（`f9f9237`） |
| P3.5 `_Tree.member_pid_ver` + `append_commitment(version=)` | **Partial** | 数据结构与 API **Done**（`search_trees.py:97-149,474-516`，`154b87e`）；**生产写入器未传 version**（见 B.3） |
| P3.5 `render_open_trees` `ver=` 标注 | **Done（形）/ Partial（数）** | 行格式含 `ver=%s`；生产 commitments 无 version → 常为 `?` |
| P3.6 测试矩阵 8 项 | **Partial** | 现有 9 tests；**缺** `test_version_dup_after_variant_id_dedup`、`test_v2_with_version_note`（计划有、未落） |
| 同 pid 高 version 可入队 / 同 pid+ver 拒 | **Done** | `test_higher_version_allowed` / `test_version_dup_rejected` |

### A.3 Phase 4（撤回）— plan `phase4.md`

| 计划项 / changelog claim | 状态 | 证据 |
|--------------------------|------|------|
| T1 `get_latest_status` / `withdraw_proposal` | **Done** | `proposal_status.py:120-196`（`1c645a8`）；幂等/终态/不存在行为有测 |
| T2 claim 前 withdrawn → 跳过 | **Done（代码）/ Missing（测）** | `aligned_slow_loop.py:636-649` `queue_ack`→done（`f1a2911`）；**无** 慢环集成测 |
| T2 verdict 写入前 skip verdicted 状态行 | **Done（代码）/ Missing（测）** | `aligned_slow_loop.py:572-597`；verdict 文件仍 append |
| T2 计划中的 `_mark_queue_skip` / pending 标记行 | **未做（有文档）** | changelog「不做的事」改为 `queue_ack`；与 SPEC §3.4.2「pending 标跳过」字面偏差，属 **设计偏离** |
| T2 cooperative cancel「每 N checkpoint」 | **未做（有文档）** | 计划已决定仅 claim 前 + verdict 前；符合 SPEC「best-effort 不保证」但未满足 §3.4.3 字面 |
| T3 `sup_paths` 确认 | **Done** | 无新增常量 |
| T4 测试 9 项 | **Partial** | 9 unit tests 全绿；计划中的慢环集成测 **未落地** |
| `version=None` | **Partial / 偏离 SPEC** | 实现=撤最新；SPEC §3.4.1=撤全部；计划/changelog 明示简化（见 B.1） |

### A.4 Changelog「关键设计决策」核对

| 决策 | 代码是否匹配 | 备注 |
|------|--------------|------|
| Dedup 顺序 vid → pid+ver | **是** | `sup_harvest.py:760-766` |
| `version=None`=撤最新（因「仅一活跃 version」） | **实现是；前提假** | harvest **允许** 同 pid 多 version 同时 queued（见 B.1） |
| Withdrawn → `queue_ack` done | **是** | 与计划初稿 `_mark_queue_skip` 不同，与 changelog 一致 |
| Evaluating withdrawn：verdict 保留、status 不追加 verdicted | **是** | |
| Version 比较 join verdicts | **是** | |
| render 标注不破格式 | **是** | 后缀追加 |

---

## B. 逻辑 / 正确性审查

### B.1 [P1] `version=None` 只撤最新 + 理由不成立（设计偏离 + 残留风险）

- **SPEC §3.4.1**：`version=None` → 撤回该 proposal_id 的**所有** version。
- **实现**（`proposal_status.py:150-154` + 测试 `test_withdraw_version_none`）：只撤 **append-only 最新一条** 对应的 version。
- **本机复现**：v1 queued + v2 queued → `withdraw(None)` 后 `get_latest_status(p,1)` 仍为 queued。
- **changelog 理由**：「harvest dedup 保证同一 proposal_id 只有一个活跃 version」——**与代码矛盾**：`version_dup` 只拦同 `pid+version`，**更高 version 可与旧 version 并存于 queue**（`test_higher_version_allowed` 正是此语义）。
- **分类**：有文档的设计偏离；因前提错误，多版本并存时 `withdraw(None)` 会 **漏撤** 旧 version → 慢环仍可能 claim。
- **建议**：实现改为撤全部非终态 version；或改 SPEC/changelog 并加「仅撤最新」警告 + 测试覆盖「v1 仍 queued」。

### B.2 [P1] `_proposal_evolution_lines` 状态优先级漏 `withdrawn`（静默展示 bug）

- **代码**：`_STATE_RANK = {verdicted:3, rejected:2, queued:1}`（`sup_evidence.py:~432`）；`withdrawn`/`evaluating`/`draft`/`degraded` 秩为 0。
- **本机复现**：同一 version 先 `queued` 再 `withdrawn` → 输出 `v1 queued`（应显示 withdrawn）。
- **影响**：跨 Run 反馈对 peer **谎报** 仍可评估/在途，与撤回事实相反。
- **分类**：**静默逻辑 bug**（非文档偏离）。
- **建议**：`withdrawn` ≥ queued（建议秩 4 或与 rejected 同级偏展示策略）；补单测 `test_evolution_prefers_withdrawn`。

### B.3 [P1] 生产 `append_commitment(accept)` **不传 `version`**（功能 Partial）

- **API 已支持**：`search_trees.append_commitment(..., version=None)` 有值才写入。
- **生产写入**：`sup_loops.py:~661-668` `_persist_search_accepts` 调用 **未传** `version=`（队列行已有 `version` 字段，`sup_harvest.py:821-822`）。
- **后果**：`member_pid_ver` 在生产 commitments 上为空 → `render_open_trees` 几乎总是 `ver=?`；changelog「搜索树追踪包含 version」**仅单测/手工写入路径成立**。
- **分类**：计划验收 **Partial**；静默缺口（不崩，但验收声明过满）。
- **建议**：`st.append_commitment(..., version=r.get("version"))`；补集成测：harvest→persist→`load_tree_index` → `member_pid_ver`。

### B.4 [P1] 树标注 `DEAD` 与 known_verdicts 头定义不一致

- **头注释**（`sup_evidence.py:476`）：`DEAD (gate_pass=False, status=ok)`。
- **render**（`search_trees.py:460-467`）：仅当 `status != "ok"` 才标 `DEAD`；`gate_pass=False, status=ok` **无标注**。
- **本机复现**：`gate_pass=False,status=ok` → 无 DEAD；`status=error` → 有 DEAD。
- **分类**：标注语义 bug / 与证据头冲突（Phase2 计划按 status!=ok 写，与头注释不一致）。
- **建议**：与 known_verdicts 对齐：`gate_pass is False and status=="ok"` → `DEAD`；保留 error 为 `DEAD` 或另标；补测。

### B.5 [P2] `evaluating` 状态从未被生产写入

- 枚举与 `withdraw_proposal` docstring 含 evaluating；**scripts 内无** `write_proposal_status(..., "evaluating")`。
- claim 后 status 仍为 queued；撤回仍可靠 verdict 前检查生效。
- **分类**：Phase1/状态机完整性缺口；不影响 Phase4 best-effort 主路径，但演进图/因果链看不到 evaluating。

### B.6 [P2] `_version_comparison_lines` vs evolution 职责重叠

- comparison：保留同一 version 的多个 (ver,status) 首次出现（可能 `v1 queued → v1 rejected`）。
- evolution：每 version 取最高态一条。
- 非正确性 bug；peer 可能看到两套略不同轨迹。计划两者都要 → 可接受，建议在 prompt 指引中一句区分。

### B.7 [P2] `version` 类型严格相等

- `_has_proposal_version_status` / `get_latest_status` 用 `==`；harvest 侧 `_version = int(...)`。
- 若历史行写入 string `"1"`，可能漏匹配或误放行。当前写入路径多为 int → 低风险。

### B.8 已核对为正确 / 非 bug

| 项 | 结论 |
|----|------|
| version_dup 在 vid dedup 之后 | 符合 SPEC §3.5.3 |
| 撤回终态拒绝 / withdrawn 幂等 | 单测覆盖，逻辑正确 |
| 同 pid 撤回后须新 version 恢复 | `version_dup` 对含 withdrawn 的历史行亦拦截同 ver → 符合「须新 version」 |
| Model A / soft degraded | Phase2–4 未改 PrescreenStatus；无回归迹象 |
| verdict 文件 append-only + 跳过 verdicted 状态行 | 符合 §3.4.6 选定路径 |
| Join 键 proposal_id/version / variant_id | evolution/comparison/withdrawn 检查一致使用；queue 已带两键（Phase1） |

---

## C. 测试缺口 vs 声称行为

| 声称行为 | 自动化覆盖 | 本机结果 |
|----------|------------|----------|
| 演化 / 树 PASS 标注 / prompt Feedback | `test_cross_run_feedback.py` ×6 | **24/24** Phase2–4 套件内全绿 |
| version_dup / 高 version / comparison / tree API | `test_proposal_versioning.py` ×9 | 全绿；**缺** dedup 顺序专测、v2+note 专测 |
| withdraw 幂等/终态/version=None | `test_proposal_withdraw.py` ×9 | 全绿 |
| 「已撤回 queued 不被慢环 claim」 | **无**（仅 status 层） | 代码存在，**验收缺口** |
| 「evaluating withdrawn → 不写 verdicted」 | **无** 慢环集成 | 代码存在，**验收缺口** |
| 「搜索树 23 测全部 PASS」 | stop_rules | **22 passed / 1 failed**（`test_root_replay_channel_harvest_level`，预存） |
| evolution 在 withdrawn 后仍正确 | **无** | 本机手工复现 **失败**（B.2） |
| 生产 accept 带 version | **无** | 代码路径确认 **未传**（B.3） |

复跑命令（本机）：

```bash
.venv/bin/pytest tests/test_cross_run_feedback.py tests/test_proposal_versioning.py tests/test_proposal_withdraw.py -q
# 24 passed
.venv/bin/pytest tests/test_search_tree_stop_rules_20261006.py -q
# 1 failed, 22 passed
```

---

## D. 结论与必改清单

### 结论

**有条件通过（实施完成度 + 代码正确性）**。

Phase2–4 按计划的主干（跨 Run 反馈物化、version_dup、撤回 API、慢环两处检查）已落地，新增 24 测全绿，可视为功能已交付。但对照 changelog/计划的验收声明，仍有 **展示错误** 与 **生产接线缺口**；`version=None` 与 Frozen SPEC 字面冲突且简化理由不成立。

**无 P0**（未发现直接导致错误入队终态双写/锁死慢环的崩溃级缺陷）。开下一阶段前建议消化下列 P1。

### 必改清单（建议优先级）

| ID | 级别 | 动作 |
|----|------|------|
| F1 | **P1** | 修 `_STATE_RANK`：`withdrawn`（及必要时 `evaluating`）进入优先级；加 evolution 单测 |
| F2 | **P1** | `sup_loops._persist_search_accepts` 传入 `version=r.get("version")`；加 harvest→index 集成测 |
| F3 | **P1** | 二选一：`withdraw(None)` 撤该 pid 全部非终态 version **或** 修订 SPEC/changelog 并删除错误「单活跃 version」断言；加多 version 并存用例 |
| F4 | **P1** | 对齐 `DEAD` 标注与 known_verdicts 头（或改头注释）；补 render 测 |
| F5 | **P1**（测试债） | 慢环：withdrawn claim skip + verdicted status skip 各至少 1 个集成测 |
| F6 | **P2** | 补 `test_version_dup_after_variant_id_dedup`；考虑写入 `evaluating`；澄清 comparison vs evolution |

### 不在本次要求内（刻意未改）

- 未改源码 / 计划 / changelog 正文
- 未释放 `local-pc.lock`（由总管释放）
- 未 commit/push

### 落档

- WSL：`/home/abug/timesfm/docs/superpowers/changelogs/2026-10-18-proposal-lifecycle-phase234-implementation-audit.md`
- Box：`/workspace/shared/reviews/2026-10-18-proposal-lifecycle-phase234-implementation-audit.md`

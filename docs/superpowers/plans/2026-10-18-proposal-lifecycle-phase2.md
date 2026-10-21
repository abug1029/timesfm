# Phase 2: 跨 Run 反馈通道 实施计划

> **修订状态**：2026-10-18 初版（Phase 1 已完成后编写）。

**Goal:** 让 peer agent 在每次生成提案时，能看到历史上同一 proposal_id 的完整命运（入队→评估→裁决/拒绝），并在搜索树渲染中标注裁决状态。

**Architecture:** Phase 1 已建立事件日志 + 拒收详情 + 因果链 + 版本比较 4 个数据源。Phase 2 在此基础上新增：① `_proposal_evolution_lines()` 展示提案演化轨迹（含每步 outcome）；② `render_open_trees` 裁决状态标注（join verdict snapshot）；③ `prompt_base.jinja2` 实际 Proposal Feedback 节（替换 Phase 1 的 3 行注释）；④ 端到端集成测试。

**Spec:** `docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md` §3.3, §5 Phase 2

**Tech Stack:** Python 3.11 + JSONL 读取 + Jinja2

## Global Constraints（继承 Phase 1）

- 单一 VERDICTS_INC 写者：`materialize_known_verdicts`
- 行预算：因果链 ≤ 25，拒收 ≤ 20，版本比较 ≤ 10，演化 ≤ 15
- `aligned_verdicts.jsonl` 不改 schema
- 追加不修改现有函数签名（向后兼容）

## Review Focus

1. **Join 正确性**：演化视图通过 proposal_status.jsonl 的多条记录（同一 proposal_id 不同 version）+ 各 version 对应的 outcome 构建
2. **render_open_trees 标注**：verdict 状态标注不能破坏现有渲染格式（tree member 行追加 `[PASS]`/`[FAIL]` 后缀）
3. **prompt 指引**：peer prompt 新增节不能超行预算，且必须包含可操作的指引（如何利用历史裁决）
4. **回归安全**：现有 `render_open_trees` 测试和 `materialize_known_verdicts` 测试不 break

---

### Task 1: 新增 `_proposal_evolution_lines()` + 端到端集成测试

**Files:**
- Modify: `scripts/sup_evidence.py`
- Test: `tests/test_cross_run_feedback.py`（新建，覆盖 P2.1 + P2.2 + P2.5）

**Interfaces:**
- Consumes: `proposal_status.jsonl`（同一 proposal_id 的多条记录，含 queued/verdicted/rejected 等状态）+ `rejected_proposals.jsonl` + `aligned_verdicts.jsonl`
- Produces: 每个多版本 proposal 一行演化轨迹，格式：`proposal_id: v1 rejected(reason) -> v2 verdicted(gate=True,fdr=True)`

**Steps:**

1. 新建 `tests/test_cross_run_feedback.py`，包含：
   - `test_proposal_evolution_lines` — 验证多版本演化轨迹正确
   - `test_proposal_evolution_empty` — 空数据返回 []
   - `test_proposal_evolution_budget` — max_lines 截断
   - `test_end_to_end_cross_run_feedback` — 完整 proposal→queue→verdict 夹具，验证 materialize_known_verdicts 包含因果行

2. 运行测试验证失败（`_proposal_evolution_lines` 不存在）

3. 在 `sup_evidence.py` 的 `_version_comparison_lines()` 之后实现 `_proposal_evolution_lines(status_path, rejected_path, verdicts_path, max_lines=15)`：
   - 按 proposal_id 分组，只处理 len(versions) >= 2 的
   - 对每个 version，取最高级状态（verdicted > rejected > queued）
   - verdicted：join verdicts_path 取 gate_pass/fdr_pass
   - rejected：join rejected_path 取 reject_reason
   - 输出格式：`proposal_id: v1 rejected(reason) -> v2 verdicted(gate=X,fdr=Y)`

4. 在 `materialize_known_verdicts()` 的 Phase 1 增强部分（line ~505 后），`## Version Comparison` 节之前插入：
   ```python
   evo_lines = _proposal_evolution_lines(
       sup_paths.PROPOSAL_STATUS_PATH,
       sup_paths.REJECTED_PROPOSALS_PATH,
       sup_paths.REGISTRY)
   if evo_lines:
       lines.append("")
       lines.append("## Proposal Evolution")
       lines.extend(evo_lines)
   ```

5. 运行测试验证通过

---

### Task 2: `render_open_trees` 裁决状态标注

**Files:**
- Modify: `scripts/search_trees.py`
- Test: `tests/test_cross_run_feedback.py`（追加）

**Interfaces:**
- Consumes: `render_open_trees(index, snapshot)` 的 snapshot 参数
- Produces: tree member 行追加 `[PASS]`/`[FAIL]`/`[DEAD]` 后缀

**Steps:**

1. 在 `test_cross_run_feedback.py` 追加 `test_render_open_trees_verdict_annotation`：
   - 创建简单 tree index（1 root + 1 exploit）
   - snapshot 中 exploit 的 variant_id 有 gate_pass=True, fdr_pass=True
   - 验证渲染行包含 "PASS" 标注

2. 运行测试验证失败

3. 修改 `search_trees.py` 的 `render_open_trees()` 中 member 行渲染（line ~441-450）：
   - 在 `near_miss` 计算后，检查 `row.get("gate_pass")`
   - gate_pass=True + fdr_pass=True → 追加 ` PASS`
   - gate_pass=True + fdr_pass=False → 追加 ` hard-gate`
   - status != "ok" → 追加 ` DEAD`
   - 修改行格式：`"  - parent %s near_miss=%s%s" % (vid, near, verdict_tag)`

4. 运行测试验证通过 + 回归测试

---

### Task 3: `prompt_base.jinja2` Proposal Feedback 节

**Files:**
- Modify: `task_FM/prompt_base.jinja2`
- Test: `tests/test_cross_run_feedback.py`（追加）

**Interfaces:**
- Consumes: `known_verdicts.inc.md`（已含因果链 + 拒收详情 + 版本比较 + 演化视图）
- Produces: peer prompt 中的 `## Proposal Feedback` 节

**Steps:**

1. 在 `test_cross_run_feedback.py` 追加 `test_prompt_has_proposal_feedback_section`：
   - 读取 prompt_base.jinja2
   - 验证包含 "Proposal Feedback" 文本
   - 验证包含 `known_verdicts.inc.md` include
   - 验证包含 peer 操作指引（historical/past/previous 关键词）

2. 运行测试验证失败

3. 替换 prompt_base.jinja2 line 114-116 的 Phase 1 注释为实际节：
   ```jinja2
   {# Phase 2: Proposal Feedback — peer 参考历史裁决结果 #}
   ## Proposal Feedback (cross-run)
   _above: causal chain + rejection details + version comparison from known_verdicts.inc.md_

   **How to use historical verdicts**:
   - `Proposal-Verdict Causal Chain`: past verdicts for same proposal_id. If `gate=False`, the hypothesis direction was validated as failing — **do not re-propose**.
   - `Recent Rejections`: quality-gate rejections with reasons. Same proposal_id reject_reason helps diagnose (e.g. quality_below_threshold = mechanism too weak).
   - `Proposal Evolution`: cross-version trajectory. If v1->v2->v3 all rejected, the hypothesis may have a fundamental issue.
   - `Version Comparison`: multi-version overview. Higher version passing = hypothesis validated after correction.

   **Citation discipline**: when referencing historical verdicts, include the original (e.g. `m_crack v2 gate=True fdr=True`), not just the conclusion.
   {% include 'known_verdicts.inc.md' ignore missing %}
   {% include 'known_rejections.inc.md' ignore missing %}
   ```

4. 运行测试验证通过

---

## 验收标准（对应 spec §5 Phase 2）

| 标准 | 验证方式 |
|------|---------|
| known_verdicts.inc.md 包含提案-裁决因果链接 | test_end_to_end_cross_run_feedback |
| 存在多 version 的提案有演化视图 | test_proposal_evolution_lines |
| 搜索树渲染包含裁决状态 | test_render_open_trees_verdict_annotation |
| prompt 包含 Proposal Feedback 指引 | test_prompt_has_proposal_feedback_section |
| 行预算不超标 | 函数内 max_lines 参数截断 |
| Phase 1 回归全绿 | 现有 16 测试 PASS |

## 不做的事

| 不做的事 | 理由 |
|---------|------|
| 修改 aligned_verdicts.jsonl schema | spec §7.5 明确禁止 |
| 修改质量门/树守卫阈值 | 不在 Phase 2 范围 |
| 增加 per-proposal 节到 known_rejections.inc.md | spec §3.3.2 分工：计数分布留给 known_rejections |
| withdraw_proposal() | Phase 4 范围 |
| version_dup dedup | Phase 3 范围 |

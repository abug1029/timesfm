# 提案生命周期管理 Spec 三审（第三轮）

- 审核对象：`/home/abug/timesfm/docs/superpowers/specs/2026-10-18-proposal-lifecycle-management-spec.md`
- 对象状态头：`Frozen`（二审修订完成，可开 Phase 1，2026-10-18）
- 上一轮审核：同目录再审 audit（结论 **有条件通过（轻条件）**，关键 P1 三条）；本文件覆盖该路径
- 代码根：WSL `/home/abug/timesfm`（DESKTOP-QO0RA3V；`git` tip `3d2a1fa`，截至三审当日）
- 对照辅助：box `/workspace/repos/timesfm-abug1029` **不以 box 为准**；断言均在 WSL `scripts/sup_*.py` / `scripts/search_trees.py` 核验
- 日期：2026-10-18（Asia/Shanghai）— **三审**
- 结论：**通过**——再审三条关键 P1 均已在草案中实质闭合，无新 P0；残留为 soft 措辞刮蹭与文档精度（P2），**不阻断 Phase 1 冻结与开工**。

---

## 0. 相对再审的 Delta

### 0.1 再审关键 P1 → 本轮闭合

| 再审 P1 | 修订落点 | 三审判定 |
|---------|----------|----------|
| 树守卫码表错/不全（虚构 `search_parent_not_found` / `tree_id_mismatch`；缺实码） | §2.1.3 重写：9 个 enforce 返回值齐全；虚构码已删；脚注「以代码为准」 | **闭合**（与 `scripts/search_trees.py` 返回值一致） |
| `degraded`「不入队」vs 今日 soft-prescreen，需 `[决定]` | §3.4.4 **`[决定]` soft（选项 b）**：Phase 1 **不改** harvest；status 日志仅可观测性；与生产一致 | **闭合**（见 §2.1 残留措辞 P2） |
| §3.3.2 vs P1.4 拒收物化位置打架 | §3.3.2 与 **P1.4** 对齐：per-proposal 详情 → `known_verdicts.inc.md`；`known_rejections.inc.md` **仅计数** | **闭合** |

### 0.2 再审可选 P1 → 本轮

| 再审项 | 修订 | 三审 |
|--------|------|------|
| Model A「均可重建」对 withdrawn 过满 | §3.2.3 增加 **例外**：withdrawn 以 status 日志为唯一事实源，不可当纯缓存丢弃 | **闭合**（前句「均可删除重建」仍略满，见 P2） |
| evaluating→withdrawn 后仍产出 verdict | §4.6「Withdrawn 与 Verdict 的关系」：不再追加 `verdicted`（或审计事件 `verdicted_after_withdraw`） | **闭合**（略早于 Phase 4 亦可；两选项择一可在 P4 PR 敲定） |
| §4.6「any → withdrawn」 | 改为「**非终态** → withdrawn」 | **闭合** |
| peer-memory D1 状态头互链 | §7.4 写明 D1 窗口仍待宿主对齐，与本规范 per-proposal 节互补 | **闭合** |

### 0.3 本轮新发现

无新 P0。仅 P2 刮蹭（§2）。

---

## 1. 总评

二修稿把再审要求的三处短改做完了：码表对齐实码、degraded 明确选 soft 且 Phase 1 不改 harvest、拒收详情/计数物化目标统一。状态机、Model A、join、schema `{v1,v2}`、撤回竞态等上一轮已闭合项未回退。

状态头标 `Frozen` 与本轮 **通过** 一致，可作为 Phase 1 编码冻结基线。建议开工前顺手刮掉 soft 段落里残留的「不入队」字样（P2，不挡冻结）。

---

## 2. 本轮问题清单（均为 P2，不挡冻结）

### 2.1 soft `[决定]` 旁残留「不入队」措辞（P2）

§3.4.4 已裁定 soft，且写「不硬拦入队 / Phase 1 不改 harvest / 与生产一致」，但同段仍出现「degraded 提案不入队（不写入 aligned_pending.jsonl）」；§3.2.1 状态表仍写「降级（保留但不入队）」。

今日代码：`_prescreen_async` 在候选入选**之后** fire-and-forget；`_apply_prescreen_score` 仅 `status=="success"` 调分；`degraded` **不** `_reject`、不拦入队。与 soft 裁定一致。

**建议刮词**（非必须先于开工）：
- §3.2.1：`degraded` 含义改为「prescreen 降级（可观测；soft 下不改变入队规则）」；
- §3.4.4：删「不入队 / 不写入 pending」句，保留 soft + 可观测性 + Phase 1 不改 harvest。
可选：补一句「current status 推导时，若同 proposal 已有 queued/evaluating/verdicted，不以后续 degraded 事件覆盖执行态」。

### 2.2 Model A 前句仍略满（P2）

§3.2.3 仍有「所有行可由 queue+verdict+prescreen+harvest 重现」「两个 jsonl 均可删除后重建」，随后才有 withdrawn 例外。建议把「均可」收成「执行面派生状态可重建；withdrawn（及可选 relation）除外」。不推翻 Model A。

### 2.3 P1.4 与 P2.2 均写「拒收详情节」（P2）

两处目标文件已统一为 `known_verdicts.inc.md`，无再审级冲突；但谁在哪一 Phase 写入同一节略叠：P1.4=`aggregate_rejection_stats` 读 `rejected_proposals.jsonl`；P2.2=`materialize_known_verdicts` join。建议 Phase 1 开工时定主写者（推荐 P1.4 写拒收节、P1.5/P2 写裁决因果链，P2.2 勿重复写拒收节）。

### 2.4 其余轻量（P2）

- soft + 异步 prescreen：理想状态机 `prescreened → queued` 与今日「先入候选再异步 prescreen」不完全同序；Phase 1 不改 harvest 下，status 日志允许 `queued` 早于 `prescreened`/`degraded` 事件即可（测试勿假设严格全序）。
- §4.6「或：追加 `verdicted_after_withdraw`」保留两选项——Phase 4 择一并写死。
- 质量门字面量表与 `_reject("...")` 一致（含 `no_success_delta` 动态说明）；树守卫九码齐全。

---

## 3. 已核验（与 WSL 代码一致）

| Spec 声明 | 实测 |
|-----------|------|
| 树守卫九码 | `search_trees.py`：`search_role_missing` / `search_tree_closed` / `search_tree_busy` / `search_root_while_tree_active` / `search_budget_exhausted` / `search_parent_missing` / `search_parent_not_near_miss` / `search_falsifier_same_cov` / `search_role_conflict`；**无** `search_parent_not_found` / `tree_id_mismatch` |
| 质量门 `_reject` 字面量 | 与 §2.1.3 表一致（含 `decision_abandon` / `backlog_dup` / `symbol_not_allowed` 等） |
| soft-prescreen | `_prescreen_async` @162 fire-and-forget；`_apply_prescreen_score` 仅 success；候选构建后才触发（@733） |
| S1 拆分 | `sup_harvest` / `sup_evidence` / `sup_paths` / `sup_loops` 仍成立 |
| schema 硬 `v1` | `sup_harvest.py:604-605` 仍待 P1.2 → `{v1,v2}` |
| `VERDICT_FIELDS_V2` 无 proposal_id | 仍成立；join 靠 queue+status |
| 样本复测非 lifecycle | `sup_loops._maybe_enqueue_retests`；§4.6 已删 `verdicted→retried` |
| `tree_id_for` | `sha256(proposal_id)[:12]` → `symbol::family::hash` |
| REJECTIONS_INC | `sup_paths.py` → `task_FM/known_rejections.inc.md`（计数目标未改） |

---

## 4. 验收标准（相对再审）

| 项 | 三审 |
|----|------|
| 树守卫码表可照表实现 | **是**（脚注仍以代码为准） |
| degraded soft 已裁定 | **是**；补测建议：Phase 1 断言「degraded 不单独 `_reject`、pending 行为与改前一致」 |
| 拒收详情落点唯一 | **是** → `known_verdicts.inc.md`；rejections.inc 仅计数 |
| withdrawn 重建例外 | **是** |
| withdrawn×verdict 竞态 | **是**（正文已有；P4 择一审计事件策略） |

---

## 5. 修正清单（本轮）

### P0

无。

### P1

无（再审三条关键 P1 均闭合）。

### P2（建议 Phase 1 PR 顺手刮；不挡冻结）

1. 刮 §3.2.1 / §3.4.4 残留「不入队」；可加 soft 下 current-status 优先级一句。
2. §3.2.3「均可重建」收紧到「执行面可重建；withdrawn 除外」。
3. 明确 P1.4 vs P2.2 拒收节主写者，避免双写。
4. Phase 4 敲定 `verdicted_after_withdraw` vs 静默不追加。

---

## 6. 建议结论

**通过**。

相对再审：从「有条件通过（轻条件）」升到 **可冻结开工**。再审要求的码表 / soft `[决定]` / 拒收物化三处均已落地；无回归性 P0。P2 刮词可随 Phase 1 文档小改或首个 PR 一并带上，不必再开一轮全文审核。

工作量估计（2–3 / 3–4 / 3–4 / 2 天）仍大体可信。

---

## 7. 证据摘录（短）

```text
# §2.1.3 树守卫（三审核对）— 九码齐全，虚构码已删
# search_role_missing, search_tree_closed, search_tree_busy,
# search_root_while_tree_active, search_budget_exhausted,
# search_parent_missing, search_parent_not_near_miss,
# search_falsifier_same_cov, search_role_conflict

# §3.4.4 — soft [决定]（选项 b）；Phase 1 不改 harvest
# （残留「不入队」句见 §2.1 P2）

# P1.4 — known_verdicts.inc.md 拒收详情节；
#         known_rejections.inc.md 仅计数分布

# scripts/sup_harvest.py — soft 实码
162: def _prescreen_async(...):  # fire-and-forget
138: if ... ps.get("status") != "success": return score
733: _prescreen_async(p, sp, symbol)  # 在 candidates.append 之后
```

审核人：New Bot（executor，三审；对照 WSL 实码；相对再审做 delta）

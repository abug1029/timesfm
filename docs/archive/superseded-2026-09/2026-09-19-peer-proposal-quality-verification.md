# Peer 提案质量改动：验证评估报告

> 日期: 2026-09-19。分支: `feat/three-loop-followup`。
> 对照: `docs/2026-09-19-verdict-analysis-report.md`（本 run 提案过门 0/11）。
> 状态: **单测门已过；快环过门率要等下一轮 run 才能量。**

## 1. 改了什么

| 面 | 文件 | 行为 |
|---|---|---|
| 提示词 | `task_FM/prompt_base.jinja2` | 先读证据再写；示例改为 `p_oi`；删除「优先波动率」和「五分钟先写两份」；选题顺序改为过门族迁品种；要求 `failure_delta` |
| 证据 | `scripts/praxist_supervisor.py` `_effective_clue_lines` | 从 snapshot 现场生成 Passing families / Near-miss / Weak families，禁止写死重点族 |
| 收割 | `harvest_proposals` | 同 symbol 或同 cov 已有失败时，`failure_delta` &lt; 20 字 → `no_failure_delta` |
| 评分 | `_proposal_priority_score` | 提案带 `covariate_family` 且该族在其他品种过门 → +8；同族 ≥4 ok 且 0 过门 → −8。不加 family 的旧路径分数不变 |

未改：`gate()` 公式、Praxist `.venv`、协变量族归档、launcher asyncio。

## 2. 单测验证（本机已跑）

工作树 `/home/abug/timesfm-wt/three-loop-followup`，解释器 `/home/abug/timesfm/.venv/bin/python`。

```
PRAXIST_BIN=/home/abug/timesfm/.venv/bin/praxist python -m pytest \
  tests/test_harvest_proposals.py tests/test_supervisor.py \
  tests/test_praxist_evidence_ladder.py tests/test_praxist_task_contract.py \
  tests/test_fm_two_peer_topology.py tests/test_verdict_registry.py \
  tests/test_praxist_fm_evaluator.py -q
```

**结果: 120 passed, 1 xfailed**（`test_task_generation_window_allows_synthesis`，原先就有，与本次无关）。

新增断言对照：

| 验收项 | 测试 | 结果 |
|---|---|---|
| 提示词不再优先波动率、不再五分钟先写 | `test_prompt_base_selection_discipline` | PASS |
| 示例是 `p_oi.json`，含 `failure_delta` 与 ACTIVE 优先 | 同上 | PASS |
| oi 过门、vor 4 败 0 过门 → clues 出现 positioning 与弱族 volatility | `test_materialize_known_verdicts_effective_clues` | PASS |
| 近门 `sh_oi` dir_acc=0.510 &lt; 0.52 出现在 Near-miss | 同上 | PASS |
| 同品种已失败且无 delta → `no_failure_delta` | `test_failure_delta_required_when_symbol_already_failed` | PASS |
| 同 cov 已失败且无 delta → 拒绝 | `test_failure_delta_required_when_cov_already_failed` | PASS |
| delta 太短 → 拒绝 | `test_failure_delta_short_rejected` | PASS |
| 有 ≥20 字 delta → 入队 | `test_failure_delta_enqueued_when_present` | PASS |
| 过门族迁品种 20 分 &gt; 全新 cov 14 分 | `test_proposal_score_family_transfer_beats_fresh_cov` | PASS |
| 弱族 −8 | `test_proposal_score_weak_family_penalty` | PASS |
| 旧评分夹具（无 covariate_family）分数不变 | `test_proposal_score_exploration_bias` / `guards` | PASS |
| 无失败史仍可无 delta 入队 | `test_good_proposal_enqueued` | PASS |

## 3. 还不能从本报告声称的

- **不能**说「过门率已经高于 0/11」。那是慢环事实，要等合入后的下一轮 `aligned_verdicts.jsonl`。
- **不能**说 PI 议程一定通过。topology 已在同分支，但要真实 Chair 合成才知道。
- 提示词纪律靠模型遵守；`no_failure_delta` 是代码硬门，选题顺序仍可能被忽略，评分只影响入队排序。

## 4. 下一轮快环怎么验（人工）

合入并重启监督环之后，看同一个 run 的收割日志和提案树：

1. `harvest` 的 `reject_reasons` 应出现 `no_failure_delta`（若 peer 仍照抄失败组合）。
2. 入队 `variant_id` 的族，持仓 / 日历周期占比应高于 vor/stddev。
3. `known_verdicts.inc.md` 的 Effective clues 不得再出现「优先波动率」。
4. 鸡蛋提案应为 `symbol_dead`，不应进慢环。
5. 等慢环消化后，统计「本 run 提案的 gate_pass 数 / 已出 verdict 数」，与 0/11 对比。样本少，只作方向，不作显著性结论。

## 5. 风险

- `failure_delta` 只查字数，模型可以写满 20 字空话。若下一轮仍 0 过门，再加「必须点名已有 variant_id」的子串检查。
- 弱族 −8 只在提案声明了 `covariate_family` 时生效；peer 漏填 family 就绕过。harvest 仍可从池里补 family，评分目前不读池。有意保持与旧测试兼容。

# FM_a 协变量搜索任务包

在冻结的 FM_a 评估管线（`scripts/monthly_backtest.py` 单品种 walk-forward）上搜索「品种 × 协变量」假设。
评估器与裁决口径归 FM_a 所有，预注册见仓库根 `config/praxist_task.yaml`。

**2026-09-08 方案 A 起：peer 是假设作者，不是评估器。** 不要跑 `evaluations/fm_eval/run.py`，不要加载 TimesFM。把机制化提案写到：

`results/gen_<N>/<peer>/proposals/<symbol>_<cov>.json`

合同：schema `fm.hypothesis_proposal.v1`；`mechanism` ≥40 字（禁模板）；必须有 `symbol_fit` 与预注册 kill/promote。只许提议 `task_FM/config/covariate_pool.json` 中 **active** 的协变量。新指标写 `new_cov_<name>.json`（`cov_override=null`），进 backlog，不入评估队列。

慢环 `aligned_slow_loop.py` 是唯一验证器（walk-forward n=350–600；硬门 n≥350 且 IC≥0.05 且扣滑点 EV>0）。诊断档小样本 PF 不作数。架构见仓库 `docs/praxist.md`。

# 文档对齐日志（2026-09-11）

计划：`docs/superpowers/plans/2026-09-11-doc-sync.md`  
仓：WSL `/home/abug/timesfm` HEAD 工作区（相对 `9653264`）  
范围：只改文档/注释/docstring。生产逻辑未改。

## 改了什么

活人类文档与合同：

- `docs/system_design.md` 1.1：方向/IC/`gate_pass` 对齐活代码；如实写 Copilot 日线分叉与实盘裸读
- `docs/praxist.md`、`docs/runbook_praxist_three_loop.md`：现场以 JSON 为准；429 仍 harvest；failover 例外；绑定解释 #4 作废
- `STATE.md`、`docs/README.md`：2026-09-11 快照；`ss_vor` / `i_oi` / `m_ccl`；n 口径
- `docs/copilot.md`、`config/AGENTS.md`、`cascade/signal_contract.py` docstring：级联/回测加权 1H，Copilot 卡面仍日线
- `data/AGENTS.md`：cutoff 为 bar 时刻 + `hour>=15`
- `loop-constraints.md`：failover model id 不同可新 run
- `scripts/praxist_goal.yaml` 仅注释；`config/backtest_config.py` 仅理论 n=589 注释

失效/已落地横幅：hardening、compile-skip、09-02 spec/plan、A2 四份 + next-steps、Phase 15、07–08 协变量战役、研究文档、peer-eval-fix、控制面宿主 7.7GiB。

## 故意没改

- `task_FM/experiments/**`、`task_FM/docs/praxist_reports/**` 历史 run
- 同名 `.txt` spec 副本
- `known_verdicts.inc.md` / `covariate_menu.inc.md`（生成物）
- 代码缺口（CC-1 接线、Copilot 改加权 1H、schema 校验、给 gate 加 EV）

## 自检

活文档不再把 IC 写成现行 Pearson、不再把 STEP=24 写成现行配置、不再把「paused_429 不 harvest」当运维合同、不再把 peer-eval-fix 标待执行、不再把 09-09 `cycles_done=6` 写成现在。

研究文档正文仍保留 2026-09-09 考古段落；文首与 §6/§7.3 已标明不是现行待办。

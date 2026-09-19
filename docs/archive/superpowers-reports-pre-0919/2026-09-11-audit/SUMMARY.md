# FM_a 全系统审核总报告（2026-09-11）

- 任务：`docs/superpowers/plans/2026-09-11-full-system-audit.md` Task 11
- 仓：WSL `/home/abug/timesfm`（HEAD 本审核落盘时 `9653264`；不把 `D:\FlyBuddy\timesfm` 当真相源）
- 输入：`docs/superpowers/reports/2026-09-11-audit/task-{1..10}-*.md`
- 只综合子报告证据 + 控制器裁定。不发明新结论。不改生产代码、不 push、不启 Praxist。

去重后计数：**代码 Critical 1 · 文档 Critical 3 · Important 18**。

---

## 一页结论：现在能信什么、不能信什么

**能信（活代码 + 磁盘）：**

- 级联预测和月报回测的可交易方向是 `sign(加权 1H − T0 收盘)`，实现是 `cascade/signal_contract.position_from_forecast`。日线斜率只填 `regime_direction`。
- 慢环 IC 是 `2×|dir_acc−0.5|`，不是 Pearson。磁盘 26 条裁决与该式 0 条 mismatch。
- `gate_pass` 布尔只判 `n≥350` 且 `IC≥0.05`。经济过门是另一层 `pass_variants()` = `gate_pass and ev>0`。目标统计不会把亏钱的 `i_oi` / `m_ccl` 算进成功。
- Vol / Neutral 压平默认 OFF。Copilot 打不开 overlay，预测点位不会被静默拍平。
- 快环活收割是 `harvest_proposals`（读 `proposals/*.json`），不是诊断 `evaluation_summary.json`。生产 tick 里只有 `aligned_slow_loop.py` 往 `aligned_verdicts.jsonl` 追加。同提供商 429 会 resume 同一 `run_dir`。
- 回测 `monthly_backtest` 已不再无条件吞当日日线：`hour>=15` 才含当日。ss 库上已收盘日线对齐 14:00，不等于当晚 21:00/23:00。**不要把这条设计选择写成 PF 穿越。**
- 网格已是 `STEP=2`、`EVAL_WINDOW_BARS=1200`。理论 n=589，磁盘最高 588。硬门阈值仍是 350，不是 396 也不是 600。
- 生产 SCHEMES 的 SS 仍是 `calendar_cyclical`。`ss_vor` 只是慢环过门，没固化。

**不能信：**

- 不能信盘中 Copilot / `cascade_predict` 的日线 context 已经收盘。`DailyModel.predict` 仍裸读 `get_main_continuous`。ss 库尾挂着「下一交易日」未完成日线（2026-09-08 close=13860 = 2026-09-07 21:00 的 1H，没有 09-08 的 1H）。这会进 TimesFM，再进 1H 协变量和领航员建议。**这是本审核唯一的代码 Critical。**
- 不能信 Copilot 卡面「方向」等于可交易方向。卡面、建议、止损、研报、账本方向全走日线 `_compute_direction_v2`。加权 1H 既不算也不印。
- 不能拿 `docs/system_design.md`（日期 2026-09-10）当方向 / IC / `gate_pass` 合同。按它改生产，会把仓位改回日线阈值，把硬门 IC 改成相关。
- 不能拿研究文档「必须立即修前视 / 当前 STEP=24」当待办。回测无条件含当日和 STEP=24 已经修过。
- 不能顺着 `docs/praxist.md` → runbook「Spec 绑定解释」→ 09-02 计划第 4 条去「修收割」。那条解释仍命令 diagnostic 幸存者。活代码不是这条。
- 不能拿 `STATE.md` 的 Praxist 快照表判断监督环是否在跑。机器事实在 `supervisor_state.json` 和 `aligned_verdicts.jsonl`。
- 不能把 `gate_pass=True` 读成「赚钱、已解决」。磁盘上 `i_oi`（ev=−2.46）和 `m_ccl`（ev=−3.64）都是 true。
- 不能把 `get_safe_daily` 已 merge、SPEC-003 已合进 master，读成「预测已经防护」。helper 只接到 cascade 报告图。
- 不能把指定 pytest 子集 123 passed 读成七条硬合同已锁。唯一失败是过期测试；现行合同大多没有能在今天红掉的锁。

**一句话：** 回测秤、硬门布尔、级联方向、三环收割骨架是对齐的；盘中日线读法和 Copilot 主句还不是同一套合同。文档里最新的总览，恰好写错了两处会改生产的条款。

---

## 代码 Critical

按裁定：当前错的活信号 / 活前视，会影响建议或 PF；硬门被绕过；非慢环写 verdict。

| ID | 缺陷 | 标签 | 证据指针 | 来源（去重） |
|----|------|------|----------|--------------|
| **CC-1** | 实盘日线预测裸读未收盘 / 下一交易日盘中日线。Copilot 与 `cascade_predict` 的 `DailyModel.predict` 走活 `DataStore.get_main_continuous`，无 15:00 掩码、不剔除 `date>today`。夜盘采集 + guard 放行会在库尾留下未完成日线；`get_safe_daily` 会丢掉它，但模型没用。ss 在 2026-09-11 仍挂 `2026-09-08` 日线 close=13860 = `2026-09-07 21:00` 1H，无当日 1H。这根 bar 进 TimesFM context → `horizon_slope` / `daily_slope` → 1H 点预测 → 领航员卡片和级联报告。`validate_prediction_data` 只拦日线落后，不拦超前。 | **两者**（代码路径错；`2fcb3ee` 与 system_design「防穿越」暗示已修） | `cascade/daily_model.py:104`；`scripts/copilot.py:396-400`；`scripts/cascade_predict.py:101` vs `:106-107`（报告才 `get_safe_daily`）；`data/data_store.py:158-188`；ss `db/futures_ss.db` 日线尾 `2026-09-08` / `updated_at=2026-09-07 13:30:59` | Task 5 C1（主）；Task 4 R21 / I「get_safe_daily 未接预测」；Task 2 I7；Task 6 指针。**不**含 `monthly_backtest` 的 `hour>=15` |

**不升代码 Critical（裁定已确认）：**

- `monthly_backtest` `hour>=15` 含当日：ss 上该日线 = 14:00 收盘，不是夜盘价。21:00 评估点用的是 15:00 已知信息。
- Copilot 违反 CF-01 A：卡面主方向是日线，点位没被拍平 → 代码 Important。
- Task 8 I1（`launch_allowed` / 评估入口仍挂着）：Praxist 0.5.0 不按该键自动跑评估；评估靠 env `PRAXIST_EVALUATION_ENTRYPOINT` 给 peer 调。提示词禁止仍在。保持 Important。
- `gate_pass` 不含 EV：不是硬门被绕过。经济层 `pass_variants()` 仍要 `ev>0`。
- 非慢环写 verdict：生产 tick 只有慢环 `append_verdict`。

**建议（不落地）：** `DailyModel.predict` 在非 `BacktestDataStore` 路径改走 `get_safe_daily`（或同一套 15:00 / 跨日规则）。夜盘后到次日 15:00 前，日线尾必须是最近已收盘交易日。另开 plan，人工确认盘中建议路径。不要为了让过期单测变绿，把回测 10:00 改回含当日。

---

## 文档 Critical

按裁定：跟着这份文档改生产，会改错信号、硬门或收割。Task 2 C1/C2 **不是**代码 Critical——`cascade_predict` / `monthly_backtest` 已经用加权 1H，IC 已经是 `2×|dir_acc−0.5|`。

| ID | 缺陷 | 标签 | 证据指针 | 来源（去重） |
|----|------|------|----------|--------------|
| **DC-1** | `docs/system_design.md` §3.3 / §5.1 / §8 把可交易方向写成日线斜率，并给出可复制 `_compute_direction`。按它去「统一」级联，会把 `cascade_predict` / `monthly_backtest` 从加权 1H 改回带 0.1%/天阈值的日线，中小 1H 位移被拍中性，日线与 1H 反向时仓位跟日线走。仓内没有 `_compute_direction`。 | **文档** | `docs/system_design.md:197-207,313-332,577-580`；更高权威 `docs/product_positioning.md:15-22`；活代码 `cascade/signal_contract.py:5-13,32-89`；`scripts/cascade_predict.py:208-230`；`scripts/monthly_backtest.py:50,329`；`tests/test_signal_contract.py:67-77` | Task 2 C1；Task 1 I-01；Task 6 §2 复核 |
| **DC-2** | `docs/system_design.md` §7.1 把 IC 写成 `corr(预测, 实际)`。按它改硬门，过门集合会变（`m_vor` / `ss_vor` / `i_oi` 都可能翻转），`gate_pass` 不再与 `loop-constraints.md` 同构。评估器没有 Pearson。 | **文档** | `docs/system_design.md:485`；`loop-constraints.md` 预注册段；`task_FM/evaluations/fm_eval/evaluator.py:199-203`；`scripts/aligned_slow_loop.py:101`；磁盘 26/26 `ic == 2*\|dir_acc-0.5\|` | Task 2 C2；Task 1 I-02；Task 7 I-02 |
| **DC-3** | 文档自称的覆盖链把方案 A 绕回 diagnostic 收割。`praxist.md` 说冲突以 runbook「Spec 绑定解释」为准；runbook 指到 09-02 **计划**；计划第 4 条仍写「幸存者 = diagnostic + status=ok + ev>0」，源是 `evaluation_summary.json`。按这条「修 harvest」会把 `harvest_survivors` 接回主路径，peer 重新加载 TimesFM。09-02 spec 本身无「已被方案 A 取代」横幅。 | **文档** | `docs/praxist.md:154`；`docs/runbook_praxist_three_loop.md:192`；`docs/superpowers/plans/2026-09-02-praxist-three-loop.md:7,37`；对照 `loop-constraints.md:49`；活代码 `_harvest_rows` → `harvest_proposals`（`scripts/praxist_supervisor.py:1289`） | Task 3 C1（主）；Task 3 I5 并入 |

**建议（不落地）：** 改 `system_design.md` §5/§7/§8，主方向只引用 `position_from_forecast`，IC 改 loop-constraints 原文，`gate_pass` 伪代码改成 n+ic。在 praxist.md / runbook / 09-02 计划头写明：方案 A 之后 Spec 绑定解释第 4 条作废，收割以 `harvest_proposals` 为准。不要按这些文档去改 `signal_contract.py` 或 `evaluator.gate`。

---

## Important（去重）

同一缺陷文档和代码各报一次的，合并为一条。测试缺口单列「测试债」，不在本表重复计分。

| ID | 缺陷 | 标签 | 证据指针 | 来源 |
|----|------|------|----------|------|
| **I-01** | Copilot 把日线 `_compute_direction_v2` 当卡面主方向，违反 CF-01 A。UI / 研报 / 建议 / 止损 / `variety_analysis` / ledger.direction 全跟日线；加权 1H 不算也不印；`delta_pct` 用 T+24 终点。纸面 health / MAE 同样评终点符号。预测点位没被 overlay 拍平，所以不是代码 Critical。 | **代码** | `scripts/copilot.py:384,433-446,247-287,617-630,684`；`cascade/signal_contract.py:12-13`（模块头谎称 copilot MUST 调用）；`cascade/live_ledger.py:60-95,293-318,453-487`；`docs/product_positioning.md:15-22`；对照正确路径 `scripts/cascade_predict.py:208-230,530-548` | Task 9 I1+I2；Task 6 I3；Task 2 C1 的 copilot 分叉 |
| **I-02** | `gate_pass` 与「硬门含 EV」混名。布尔不含 EV；磁盘 `i_oi` ev=−2.46、`m_ccl` ev=−3.64 均为 `gate_pass=true`。`pass_variants()` 才要 `ev>0`，经济过门实质只有 `ss_vor`。materializer / `prompt_base` 把 `gate_pass=True` 写成 already solved，亏钱组合被当成已解决，却既非 `pass_variants` 也非 DEAD，peer 仍可再入队。**不要给 `evaluator.gate` 加 EV**，除非另开合同改 materializer 语义。 | **两者** | `evaluator.py:199-203`；`scripts/registry_lib.py:39-45`；`aligned_verdicts.jsonl` 第 16/19/26 行；`praxist_supervisor.py:483-486`；`task_FM/prompt_base.jinja2:67-68`；`docs/system_design.md:537-544`；`config/praxist_task.yaml:19-20`；`docs/praxist.md:91-95` vs `:115` | Task 1 I-03；Task 2 I4；Task 7 I-01；Task 8 I3+I8 |
| **I-03** | peer「禁止评估 / 禁止加载 TimesFM」只写在提示词里。`task.yaml` 仍挂 `evaluations/fm_eval/run.py`、`diagnostic.launch_allowed: true`、`praxist_plugins.evaluations`；peer role 仍给 `evaluation_tools.peer`。Praxist 0.5.0 **不会**因 `launch_allowed` 自动跑评估（评估入口是 env `PRAXIST_EVALUATION_ENTRYPOINT`）。能力面仍在，7.7GiB 宿主上 peer 若主动调会和慢环抢内存。不升代码 Critical。 | **代码** | `task_FM/task.yaml:83-85,90-98,136-137`；`roles/peer_generalist/role.yaml`；对照 `prompt_base.jinja2:5-9`、`loop-constraints.md:49` | Task 8 I1（裁定 3） |
| **I-04** | 研究文档仍以「待执行修复 / 必须立即修前视 / 当前 STEP=24 → 396 点」号召。代码已是 STEP=2 / 窗口 1200 / `hour>=15` 截断。按该文档再改 `BacktestDataStore` 会动已经修过的回测。 | **文档** | `docs/research/slow_loop_evaluation_points_research.md` 文首、§4.2、§8、§10；`config/backtest_config.py:55-56`；`data/data_store.py:795-802`；git `ee1f176` | Task 4 主 Important；Task 1 过期清单 |
| **I-05** | Hardening spec 仍写「critical-fixes 完成后可启动」、计划 71 框全空；compile-skip spec 状态「待审阅」、验收框全空。SPEC-004…013 与 `ensure_compiled` 已在 master（`243693d` / `a8b0b6b`）。按施工单再跑会重改已冻结的 `cascade/` / `prediction_scheme.py`。 | **文档** | `docs/superpowers/specs/2026-09-10-system-hardening-design.md` 头部；`docs/superpowers/plans/2026-09-10-system-hardening.md` 0 个 `[x]`；`CLAUDE.md` hardening 能力表；compile-skip spec L4；`cascade/daily_model.py:53` | Task 3 I1+I2 |
| **I-06** | 控制面仍按 15GiB + peer `fm_eval` 作战，harvest 选人「再按 EV 补齐」。现行宿主 7.7GiB、方案 A peer 零次 TimesFM。 | **文档** | `docs/superpowers/specs/praxist_control_plane.md` L3, L19-27, L190；`docs/host_environment_assessment.md`；`docs/praxist.md:65-67` | Task 3 I3 |
| **I-07** | runbook 写 `paused_429` 期间不 harvest；代码和控制面都说要 harvest（方案 A 下提案是本地文件，合理）。运维按 runbook 会在 429 时人为跳过收割。 | **两者** | runbook L82、L123；`praxist_supervisor.py:1299-1300,1527-1529`；控制面 L191 | Task 3 I4；Task 8 R10 |
| **I-08** | `config/praxist_task.yaml` 仍留 diagnostic 阶梯；`test_praxist_task_contract.py` **绿着**锁 2026-09-01 可写区 `scripts/praxist_ws` 和「必须有 diagnostic 档」。方案 A 可写区是 run 下 `results/`。按这只绿测「修契约」会把方案 A 改回去。 | **两者** | `config/praxist_task.yaml:16-26`；`tests/test_praxist_task_contract.py:48-57`；`loop-constraints.md:49-51` | Task 1 I-06；Task 8 I7；Task 10 §3 |
| **I-09** | `STATE.md` 人类快照停在 2026-09-09：`cycles_done=6` / `phase=slow` / 有限预算；磁盘 `supervisor_state.json` 是 `phase=fast`、`cycles_done=1`；goal 已无限预算。权威层 1 文件里还有死链 `/root/timesFM_fu/...`。`docs/praxist.md` §4 现场复制了同一张过期表。 | **文档** | `STATE.md` L7, L26-38, L621-627；`data/cache/supervisor_state.json`；`scripts/praxist_goal.yaml` budgets 999999 | Task 1 I-07 |
| **I-10** | SS 三套名字：生产 SCHEMES=`calendar_cyclical`；慢环过门=`ss_vor`（未固化）；`system_design` §4.2 与 §4.3 都叫「当前」。执行者会把 vor 写进 `SCHEMES`。 | **文档** | `config/prediction_scheme.py:120-133`；`aligned_verdicts.jsonl` `ss_vor`；`docs/system_design.md:232-236` vs `:267-271` | Task 1 I-04；Task 2 I3 |
| **I-11** | 样本量四套数并排：硬门阈值 350；旧网格/截断 396；理论 589；goal 上限 600。磁盘 396×21、588×3；`ss_vor` 的 396 是 09-09 旧网格；09-11 的 `m_ccl` 又被 `max_points=396` 截回。跨 variant 比 n 不可比。 | **两者** | `backtest_config.py:55-56`；goal `aligned_max_points: 600`；磁盘 n 分布；`tests/test_system_hardening.py` 用 589 | Task 1 I-05；Task 4 R9；Task 7 I-04 |
| **I-12** | Copilot 在 `ensure_fresh_data` **全部失败**时 `symbols = valid or symbols`，回到原始列表继续预测。cascade_predict 没有这个回退。 | **代码** | `scripts/copilot.py:764-769`；对照 `scripts/cascade_predict.py:840-844` | Task 5 I2 |
| **I-13** | SPEC-011 后复权在生产日线读取上是死代码：schema 有 `raw_close` 列（值全 NULL）把开关短路；真正调用的是价差比不是截面比；1H 从未复权。三条路径一视同仁（都没真正复权），不是前视。 | **代码** | `data/data_store.py:84-110,416-421`；ss `raw_close` 全 NULL、`adjustment_factor` 全 0 | Task 5 I3 |
| **I-14** | `HourlyModel` 在非 `_MAIN` 且 1H 合约 ≠ 日线合约时走 `get_klines_1h`（无 `end_date`）。`BacktestDataStore` 没覆盖这个方法，回测可能丢掉时刻截断。ss 走 `SS_MAIN`，这条不触发。价格序列与协变量还可能不是同一合约。 | **代码** | `cascade/hourly_model.py:131-147`；`features.py` 总是 `get_main_contract_1h` | Task 5 I4；Task 6 I4 |
| **I-15** | `data.config.get_timesfm_model_path()` 从未进过 Python。Daily/Hourly 硬编码 HuggingFace hub id；本仓 `models/timesfm-2.5-200m-pytorch` 是 HF cache 的符号链接，不是隔离副本。不证明信号已经算错。 | **两者** | `AGENTS.md:28-38`；`data/config.py` 无此符号；`cascade/daily_model.py:80-81`；`hourly_model.py:84-85` | Task 6 I1 |
| **I-16** | 同名 `rsi_state`：单路径 = 日线 RSI（rb/lh/jd），combo = 1H RSI（sr/p）。horizon 都从 context 末端衰减，不是穿越，但不能假设「rsi_state 到处一样」。 | **代码** | `cascade/features.py:1076-1119` vs `:1483-1487`；`hourly_model.py:196-197` | Task 6 I2 |
| **I-17** | 保证金 MaxDD 吃的是毛 PnL（`position_sign * delta_real`），名义 MaxDD 走净盈亏。两套回撤成本口径不一致。不进 `gate()`。 | **代码** | `scripts/aligned_slow_loop.py:105`；`scripts/monthly_backtest.py:355`；`cascade/evaluation_metrics.py:82-88,278-340` | Task 7 I-03 |
| **I-18** | `harvest_proposals` 不读 `p["schema"]`，缺或不符 `fm.hypothesis_proposal.v1` 只要有 symbol+cov+≥40 字 mechanism 就会入队。429 failover 在模型身份墙（claude→qwen）时开新 run，测试把 FRESH start 锁成预期；`praxist.md` 未写这条例外。 | **代码**（schema）/ **两者**（failover 合同） | `praxist_supervisor.py:603-623`（无 schema 分支）；`:320-329,1094-1110`；`tests/test_supervisor.py:823-851` | Task 8 I2+I6 |

`system_design.md` 其余过时伪代码（单位自相矛盾、10 列写成 P10~P90、`confidence_band` 线性版、Windows 激活路径、示例 `build_calendar_cyclical` / 归一化 RSI、附录漏 `signal_contract.py`、标题「开平仓建议」）并入 **Minor 簇 SD-***，不升 Important——DC-1/DC-2 已经锁住「按该文档改生产」的主风险。

---

## Minor（摘录，去重）

| ID | 内容 | 标签 |
|----|------|------|
| M-01 | Vol 章节/架构图读起来像生产路径，正文已写默认 OFF | 文档 |
| M-02 | `docs/praxist_peer_evaluation_fix.md` 状态「待执行」；07/08 spec 状态栏普遍未关 | 文档 |
| M-03 | `AGENTS.md` 仍写 `timesFM_fu`；`praxist_goal.yaml` 头注释仍写 15GiB | 文档 |
| M-04 | `evaluator.py` 模块头仍提 diagnostic 档 | 文档 |
| M-05 | 理论 n 注释写成 600；活公式 589。`docs/AGENTS.md` EV 单位注仍说 stdout 打印 `EV=`，代码已改 `EV_ratio=` | 两者 |
| M-06 | supervisor `cad.get("aligned_max_points", 400)`；goal 有 600 时无害 | 代码 |
| M-07 | SPEC-007 cosine 已实现，生产 SCHEMES 全关 | 代码 |
| M-08 | compile-skip 规格名 `_ensure_compiled`，实现 `ensure_compiled` | 文档 |
| M-09 | `config/AGENTS.md` 仍写「实盘用日线定方向，回测用终点」——与现行两边都走 `position_from_forecast` 相反 | 文档 |
| M-10 | Copilot「加权作补充」空注释；`craft_advisory_v2` 未接到 `run_one`；`stars>=3` 死分支；cascade `--three-star` help 仍写 SS/UR/SR | 代码 |
| M-11 | `n_eff` 只记录不进门；DirAcc 先 round 到 3 位再算 IC | 代码 |
| M-12 | harvest 重扫全部 `run_*`；mechanism「禁模板」无实现；materializer `items[:20]` | 代码 |
| M-13 | `restore-verdicts` 人工 CLI 默认可写生产 jsonl | 代码 |
| M-14 | 效率审计 F-002/003/006/007 等未按原方案落地（不是本审核主合同） | 代码 |
| M-15 | md/txt 双份且 followup-4 / alpha2 内容漂移 | 文档 |
| M-16 | ss 2026-09-01 日线收盘对齐 00:00 而非 14:00（数据质量，不推翻「已收盘日线不含夜盘」） | 代码 |

Task 6 M6「combo 不支持 ccl」**作废**：HEAD `9653264` 已补 combo 的 ccl / basis_momentum / gated_slope / regime_gated。不要当现行缺口。

---

## 测试债

现场（Task 10 指定子集）：**1 failed, 123 passed, 3 skipped in 10.68s**。

**失败 ≠ 代码 bug（裁定 5）：**

`tests/test_backtest_cutoff.py::TestBarExactCutoff::test_daily_includes_cutoff_calendar_day` 期望 10:00 cutoff **含** `2026-03-10` 日线；活代码 `hour<15` 推到前一日历日，得到 `{'2026-03-09'}`。锁的是 09-03 旧合同。若为了让它绿把 10:00 改回含当日，会拆掉已修的回测前视防护。

**绿着锁旧合同（更危险）：**

| 测试 | 锁的过期合同 | 若按测试「修」代码 |
|------|----------------|---------------------|
| `test_praxist_task_contract::test_write_paths_within_redlines` | peers 可写 `scripts/praxist_ws` | 方案 A 的 `results/` 可写区被改回去 |
| `test_praxist_task_contract::test_evidence_maturity_gates` | 必须有 diagnostic 档；gate 列表非空（yaml 含 `ev>0`） | 保住 diagnostic 入口；把最终裁决列表当成 `evaluator.gate` |
| `test_system_hardening` craft_advisory v2 | revoked 冻结句 | 误以为卡面已接 v2 |

**现行合同没有锁（缺口，今天全绿也给不了信心）：**

1. Copilot 主方向 = 加权 1H（补了今天会红）。函数层 `test_signal_contract` 只锁 `position_from_forecast` 本身。
2. IC 公式显式断言；`n=400, ic=0.06, ev=-2 → gate True`。没有这两例，给 `gate()` 加 EV 或改 Pearson，指定子集无感。
3. `DailyModel.predict` 最后一根 dt 不得晚于 `get_safe_daily`。`test_daily_freshness` 只锁 helper。
4. 现行 cutoff：10:00 日线 **不含**当日；15:00 **含**当日。正向绿锁不存在。
5. peer 禁评估（提示词 / role 不含 `evaluation_tools`）。现在去锁会先红，因为 role 还含有。
6. Vol 默认 OFF；Copilot 源码不含 `apply_neutral_override`。
7. 慢环唯一写 `aligned_verdicts.jsonl`（「别人不 append」）。
8. `survivors_per_cycle=3` 读真实 `praxist_goal.yaml`；429 期间仍 harvest。

`test_future_bar_guard` 绿证明夜盘**故意允许**下一交易日标签——正好解释 CC-1 会吃到它，不是「预测已安全」。

---

## 建议修复顺序

文档先于代码。代码里实盘日线接线优先于 Copilot 方向。本审核不改代码。

### 只改文档

| 顺序 | 做什么 | 挡住什么 |
|------|--------|----------|
| D1 | `system_design.md` §3.3/§5/§7/§8：主方向改 `position_from_forecast`；IC 改 `2×\|dir_acc−0.5\|`；`gate_pass` 伪代码改 n+ic，另写 `econ_pass = gate_pass and ev>0`；文首声明方向/IC/gate 以 product_positioning + loop-constraints 为准 | DC-1、DC-2 |
| D2 | praxist.md / runbook / 09-02 计划头：方案 A 之后 Spec 绑定解释第 4 条作废；09-02 spec 加「部分取代」横幅 | DC-3 |
| D3 | 研究文档改为 Historical，顶部写被 `ee1f176` + SPEC-003 取代；删「立即修复」祈使句 | I-04 |
| D4 | Hardening / compile-skip spec 与计划改「已落地 master」，勾选框不要再当施工单 | I-05 |
| D5 | runbook L82/L123 与代码对齐（429 期间仍 harvest）；控制面宿主改 7.7GiB，「peer eval」改为「任何 TimesFM（现仅慢环）」 | I-06、I-07 |
| D6 | STATE / praxist 现场：快照改「以 JSON 为准」或按磁盘重刷；补 `m_ccl`；写清 396=旧网格或截断、588≈现行 589、600=上限；删 `/root/timesFM_fu` 死链 | I-02、I-09、I-11 |
| D7 | SS 拆两行：生产 SCHEMES=`calendar_cyclical`；慢环过门 `ss_vor` 未固化。yaml diagnostic 段标注作废 | I-08、I-10 |
| D8 | `data/AGENTS.md` cutoff 改 bar 时刻 + `hour>=15`；`config/AGENTS.md` 删「实盘≠回测方向」；`signal_contract.py` 模块头不要写 copilot 已合规；Windows 激活路径改 WSL | I-01 的文档侧、M-09、DC-1 配套 |
| D9 | 合同补一句：failover 且模型 id 不同 → 允许新 `run_dir`。两套固化门写明 v2 ≠ `gate_pass` | I-18、Task 1 I-08 |

改文档时 **禁止** 顺手改 `prediction_scheme.py`、`evaluator.gate`、`BacktestDataStore`。

### 需要改代码（另开 plan + 人工确认高风险路径）

| 顺序 | 做什么 | 风险 | 对应 |
|------|--------|------|------|
| C1 | **实盘日线接线：** `DailyModel.predict` 非回测路径走 `get_safe_daily`（或与 `BacktestDataStore` 同一套 15:00 / 跨日规则）。先只读探针：同一 `DataStore` 比较裸读最后 `dt` 与 helper 最后 `dt`。 | **高。** 改盘中建议的日线 context，会动 `horizon_slope` 和 1H `daily_slope`。须人工确认夜盘后、次日 15:00 前的 copilot / cascade_predict。接上 helper 仍要处理「有今日标签但不是 14:00 收盘」的陈旧盘中 bar。 | CC-1 |
| C2 | 把红测 `test_daily_includes_cutoff_calendar_day` 改成 10:00 **不含**当日；另加 15:00 含当日。不要改回测实现去迁就红测。 | 低（只改测试） | 测试债；裁定 5 |
| C3 | Copilot `run_one` 调 `position_from_forecast`：卡面 `direction` = 加权 1H，另存 `regime_direction`；CLI/研报印可交易方向 / 加权价 / 日线状态；`generate_risk_bounds` 跟可交易方向。纸面 schema 加 `weighted_pred` 需迁移。 | **高。** 人读建议会「突然反了」。不要为了对齐 Copilot 去改 `position_from_forecast`。 | I-01 |
| C4 | materializer + `prompt_base` 改三态：经济过门 / 过硬门但亏钱 / DEAD。夹具 `gate_pass=True, ev<0`。 | 中（改 peer 每代看到的名单，不改磁盘 `gate_pass` 语义） | I-02 |
| C5 | 关掉 peer 评估能力面：`diagnostic.launch_allowed: false`；拿掉 `evaluation_tools`；审计规则改为提案文件。然后再锁提示词测试。 | 中（须对照 Praxist 插件是否仍注入 `PRAXIST_EVALUATION_ENTRYPOINT`） | I-03 |
| C6 | Copilot 全失败不再 `valid or symbols`；与 cascade 一样停或只跑 valid。 | 中（盘中可用性 vs 脏库） | I-12 |
| C7 | harvest 拒绝非 `fm.hypothesis_proposal.v1`；goal.yaml 的 `survivors_per_cycle=3` 加测试。 | 低 | I-18 的 schema 侧 |
| C8 | 保证金 MaxDD 改吃净 PnL。 | 中（改 verdict 字段，不进 gate） | I-17 |
| C9 | ALIGN 路径：features 吃 HourlyModel 已读的 `df_1h`，或 `BacktestDataStore` 覆盖 `get_klines_1h`。先扫哪些生产品种没有 `{SYM}_MAIN`。 | **高**（可能动无 `_MAIN` 品种的 PF） | I-14 |
| C10 | SPEC-011：要么按截面比真正打开，要么文档承认日线/1H 都没后复权。禁止在未确认 `raw_close` 列语义时删列抢跑。 | **高**（价位制度） | I-13 |
| C11 | 实现或删除 `get_timesfm_model_path` 合同。隔离要复制，不要 symlink。 | 中（加载路径，不改预测公式） | I-15 |
| C12 | `rsi_state` 分名或统一构造；固化前用该品种真实路径回测。 | **高**（改 XReg 输入） | I-16 |

**明确不做：** 不要把 EV 塞进 `evaluator.gate`（裁定 6）。不要按研究文档再改 STEP。不要按 `system_design` §5.1 去改级联方向。不要按 09-02 绑定解释去接回 `harvest_survivors`。

---

## Rulings（控制器，绑定）

子报告若与下列冲突，以本表为准。

1. **严重度拆分。** SUMMARY 里 **代码 Critical** = 当前错的活信号 / 活前视，会影响建议或 PF / 硬门被绕过 / 非慢环写 verdict。**文档 Critical** = 跟着那份文档会改错生产。两列不要合并。Task 2 C1/C2 是文档 Critical，不是代码 Critical（`cascade_predict` / `monthly_backtest` 已经用加权 1H，IC 已经是 `2×|dir_acc−0.5|`）。
2. **Task 5 C1 是代码 Critical。** `DailyModel.predict` 在 copilot 与 `cascade_predict` 上裸 `get_main_continuous`；夜盘下一交易日未完成日线在 ss 库里。影响实盘建议。`monthly_backtest` 的 `hour>=15` 含当日 **不是** PF 前视（收盘与 14:00 对齐）。
3. **Task 8 I1 不升代码 Critical。** 只读核对 Praxist 0.5.0：`launch_allowed` 未在 Praxist Python 里被引用。评估作为 env `PRAXIST_EVALUATION_ENTRYPOINT` 注入，供 peer 调用，不会每代自动跑。保持 Important：提示词禁止仍在，能力面也仍在。
4. **Copilot 违反 CF-01 A = 代码 Important，不是 Critical。** 卡面主方向是日线；点位没有被拍平。
5. **`test_daily_includes_cutoff_calendar_day` FAIL = 过期测试锁旧合同，不是代码 bug。**
6. **`gate_pass` 布尔只判 n+ic。** 经济过门是 `pass_variants()`，要求 `ev>0`。不要建议在没有单独规格的情况下把 EV 加进 `evaluator.gate`。
7. **本审核不改代码。** 修复顺序分两列：只改文档 vs 需要改代码（另开 plan + 人工确认高风险路径）。

（去重规则，执行已用：同一缺陷文档和代码各报一次，合并为一条，标 文档 / 代码 / 两者。）

---

## 权威链（给后续修复用，不重新裁决）

冲突时：磁盘 JSONL / `supervisor_state.json` / `SCHEMES` / `backtest_config.py` 压过散文快照；`loop-constraints.md` 的 IC 公式压过 `system_design` 的 Pearson；`product_positioning.md` CF-01 A 压过 `system_design` 日线主方向；`gate_pass` 字段以 `evaluator.gate()` 为准，经济过门是 `pass_variants()`。

现行敢当合同的 spec：`docs/spec_hypothesis_driven_fast_loop_20260908.md`（快环）；hardening / compile-skip 的**接口不变量**（不是启动姿态）；控制面的 flock=1 / 2.5GiB / 未经批准不启 Praxist（不是 15GiB 或 peer eval）。09-02 三环 spec **不敢**当收割合同。

---

## 子报告冲突与本表处理

| 冲突 | 处理 |
|------|------|
| Task 1 把方向/IC 只标 Important；Task 2 标 Critical | Ruling 1：升为 **文档 Critical**（DC-1/DC-2），不升代码 Critical |
| Task 4 不把实盘裸读标 Critical，交给 Task 5 | Ruling 2：Task 5 C1 = **代码 Critical**（CC-1） |
| Task 8 开放问题「若 Praxist 自动调度评估则 I1 升 Critical」 | Ruling 3：不升。I-03 保持 Important |
| Task 2 把 copilot 分叉写进 C1 的代码事实 | Ruling 4：copilot 分叉单独 I-01，代码 Important |
| Task 4/5/10 都报 `test_daily_includes_cutoff_calendar_day` 红 | Ruling 5：测试债，不是代码 bug。三份合成一条 |
| Task 2 I4 / 若干文档暗示给 `gate()` 加 EV | Ruling 6：禁止。I-02 建议只改文档命名和 materializer 三态 |
| Task 6 M6 combo 无 ccl | HEAD `9653264` 已补。本表删除该 Minor |

未发现子报告在「级联方向已经是加权 1H」「IC 公式」「回测夜盘含当日 ≠ 含夜盘价」「Vol 默认 OFF」上互相打架。

---

## 本任务未做

- 未改生产代码、未 push、未启 Praxist / 监督环 / 全量 walk-forward。
- 未重跑 TimesFM，未对「接上 `get_safe_daily` 前后斜率差多少」做数值对照（CC-1 的路径闭合，斜率差仍是 Critical Unknown）。
- 日线收盘构成只深探了 ss。其它夜盘更长的品种未扫。
- 未列出全部无 `{SYM}_MAIN` 的生产品种（I-14）。

---

## 状态

**DONE**

- path: `docs/superpowers/reports/2026-09-11-audit/SUMMARY.md`
- 去重后：代码 Critical **1**（CC-1）/ 文档 Critical **3**（DC-1, DC-2, DC-3）/ Important **18**（I-01…I-18）
- 本审核不改代码

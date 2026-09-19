# Spec–代码对齐总表（Task 8）

- 任务：`docs/superpowers/plans/2026-09-11-spec-code-alignment.md` Task 8
- 仓：WSL `/home/abug/timesfm`（子报告 HEAD `9653264`）
- 输入：`spec-alignment/task-{1..7}-*.md`
- 上一轮全审计：`docs/superpowers/reports/2026-09-11-audit/SUMMARY.md`（代码 Critical 1 / 文档 Critical 3 / Important 18）
- 只综合子报告 + 控制器裁定。不改生产代码、不 push、不启 Praxist。

**有效性（Task 1，20 份）:** 仍有效 **5** · 部分有效 **10** · 设计失效 **5**

**本轮新代码 Critical: 0。** 活信号/硬门/收割上，没有「有效 spec 写反、上一轮没报过」的新 Critical。CC-1 / I-13 / I-17 / copilot v2 未接线，一律引用上一轮，不新开号。

控制器已绑定：失效设计不当缺口；不要建议去实现 diagnostic 收割、A2 LGBM 生产、Phase 15 晋升 SCHEMES、15GiB 宿主、peer-eval 作战。Praxist 0.5.0 不会因 `launch_allowed` 自动跑 `fm_eval`（评估入口是 env `PRAXIST_EVALUATION_ENTRYPOINT`）。compile-skip = **对齐**。hardening = **部分对齐**（10 条缺口多为实现偏离 spec 公式，不是「没做」）。

---

## 20 行总表

计数口径：对齐 / 部分 / 缺口 / 失效 = 该 spec 条款行（Task 2/4 用原表整数；Task 3/5/6/7 按条款表点过的判定格清点）。失效列是**条款**数，不是「这份文件作废」。整份设计失效的，缺口计 0（不评代码对错）。

| # | Spec | 有效性 | 总评 | 对齐 | 部分 | 缺口 | 失效条款 | 来源 |
|:-:|------|--------|------|:----:|:----:|:----:|:--------:|------|
| 1 | `2026-09-10-system-hardening-design.md` | 仍有效 | **部分对齐** | 41 | 9 | **10** | 0 | Task 2 |
| 2 | `2026-09-09-compile-skip-phase1-design.md` | 仍有效 | **对齐** | 22 | 0 | **0** | 1（§8 按设计不做） | Task 3；裁定 4 |
| 3 | `2026-09-02-praxist-three-loop-design.md` | 部分有效 | 骨架部分对齐；diagnostic **失效** | 21 | 6 | **0** | 10 | Task 4 |
| 4 | `praxist_control_plane.md` | 部分有效 | **部分对齐** | 19 | 8 | **6** | 7 | Task 5 |
| 5 | `ACCEPT_flock_20260906.md` | 仍有效 | **对齐** | 6 | 1 | 1（无 pytest，Low） | 0 | Task 5 |
| 6 | `2026-07-28-covariate-optimization-design.md` | 部分有效 | **部分对齐** | 4 | 1 | 0 | 4 | Task 6 |
| 7 | `2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md` | 部分有效 | **部分对齐** | 6 | 0 | 1（G1 Low） | 4 | Task 6 |
| 8 | `2026-07-29-followup-4-directions-optimization-design.md` | 部分有效 | **部分对齐** | 5 | 0 | **1**（S1） | 1（方向 4 固化） | Task 1+6 |
| 9 | `2026-07-29-phase4-calendar-cyclical-design.md` | 仍有效 | **部分对齐** | 5 | 2 | **1**（C1） | 1（JD 首验） | Task 1 有效性；Task 6 对齐 |
| 10 | `2026-07-31-phase8-crack-spread-design.md` | 部分有效（池，非 SCHEMES） | **对齐** | 13 | 0 | **0** | 0（固化从未是合同） | Task 6 |
| 11 | `2026-08-04-alpha2-phase1-baseline-gate-design.md` | **部分有效** | 生产模型失效；评价库残留对齐 | 1（`calc_vol_scaled_mae`） | 0 | **0** | 2（LGBM 生产 / Track B） | Task 1 有效性；Task 7 生产 0 import |
| 12 | `2026-08-04-phase9-toxic-variety-design.md` | 部分有效 | **部分对齐** | 7 | 0 | 0（L3 文案 Low） | 1（JD combo 固化） | Task 6 |
| 13 | `2026-08-05-a2-p1-dense-cache-resume-design.md` | **设计失效** | 不评；残留脚本对齐探针 | — | — | **0** | 整份 | Task 1+7 |
| 14 | `2026-08-05-a2-p1-market-vectorize-design.md` | **设计失效** | 不评；残留对齐 | — | — | **0** | 整份 | Task 1+7 |
| 15 | `2026-08-05-a2-p1-runtime-redesign.md` | **设计失效** | 不评；残留对齐（网格已跟 STEP=2） | — | — | **0** | 整份 | Task 1+7 |
| 16 | `2026-08-22-phase15-new-covariates-design.md` | 部分有效 | 池部分对齐；固化 **失效** | 8 | 2 | 0（N1/N2/B1 均 Low） | 3 | Task 6 |
| 17 | `docs/spec_hypothesis_driven_fast_loop_20260908.md` | 仍有效 | **部分对齐** | 25 | 8 | **2** | 1（glob 仅本 run） | Task 4 |
| 18 | `docs/praxist_directive_design.md` | 部分有效 | 指令闭环仍在；§3 **失效** | — | — | **0** | §3 阶梯 / peer 评估 | Task 1；Task 4 X10 |
| 19 | `docs/praxist_integration_plan.md` | **设计失效** | 不评（方案稿，所有权已迁走） | — | — | **0** | 整份 | Task 1 |
| 20 | `docs/praxist_peer_evaluation_fix.md` | **设计失效** | 不评；按它施工会与方案 A 相反 | — | — | **0** | 整份 | Task 1+7 |

**20 行有效性清点:** 仍有效 5（1, 2, 5, 9, 17）+ 部分有效 10（3, 4, 6, 7, 8, 10, 11, 12, 16, 18）+ 设计失效 5（13, 14, 15, 19, 20）= 20。

**总评清点:** 对齐 3（#2 compile-skip、#5 ACCEPT、#10 crack 池）· 部分对齐 12 · 设计失效不评 5。hardening（#1）与方案 A（#17）都是部分对齐，不是「没落地」。

spec 11 冲突：Task 7 因四入口 0 import 把整份标失效。本表有效性跟 Task 1（评价库 + JSONL 工具形态仍在 → 部分有效），生产模型条款跟 Task 7 标失效、**缺口 0**。不要把「monthly 没接 LGBM」写成缺口。

critical-fixes SPEC-001…003：仓内无独立 spec 文件，不占 20 行。`get_safe_daily` 未接 `DailyModel.predict` = 上一轮 **CC-1**，见下节引用，不新发明一份 spec。

---

## 有效缺口（只列 Critical / Important）

Low 缺口（报告文案、乘数恒 10、半衰期建议表、无后缀 gated 名、NVI streak、VWAP 声称、缺 batch 脚本、日志文件名、ACCEPT 无 pytest、SendToAgent）不进本表。部分对齐里会改信号/收割/硬门理解的，升到 Important，并去重上一轮。

### Critical：本轮新增 0

没有「有效 spec 与活生产路径相反、且会改错信号 / 硬门 / 收割」的新条款。

| 引用 | 为何不是本轮新 Critical |
|------|-------------------------|
| **CC-1** `get_safe_daily` 未接 `DailyModel.predict` | 上一轮唯一代码 Critical。SPEC-001…003 无独立文件。`scripts/cascade_predict.py:106-107` 只给报告图用 helper；`copilot.py:445` / `DailyModel.predict` 仍裸 `get_main_continuous`。本轮不重开号。 |
| SPEC-011 `raw_close` 短路 | Task 2 High，**不是** Critical：未证实跳空已系统性打歪活信号；不进 `gate()`。→ 上一轮 **I-13**。 |
| SPEC-008 保证金 MaxDD 喂毛 PnL | Task 2 High，不进 `gate()`。→ 上一轮 **I-17**。 |
| 方案 A peer 能力面仍开 | Task 4 H2 曾考虑升 Critical。裁定 2：Praxist 0.5.0 **不会**自动跑 `fm_eval`。保持 **I-03** Important。 |
| 方案 A schema 不校验 | Task 4 H1 High：收割源仍是 `proposals/`，不是诊断 PF。→ 上一轮 **I-18**。 |

### Important（去重后 11 条）

同一缺陷只留一行。标签：缺口 = 有效条款代码没有或写反；偏差 = 任务报告的「部分对齐」但生产相关。

#### A. 引用上一轮（不新开 ID）

| ID | 本轮挂到 | 证据 | 修（另开 plan，本任务不改代码） |
|----|----------|------|--------------------------------|
| **I-13** | SPEC-011：日线 `raw_close` 列恒在 → `get_main_continuous` 永不复权；`detect_rolls_from_price_gaps` 用 `P_t/P_{t-1}` 不是截面比；TqSdk 无双合约快照 | Task 2：`data/data_store.py:416-421,83-110`；`data/db.py` `MAIN_COLUMNS` 含 `raw_close` | 要么按截面比真正打开，要么文档承认日线/1H 都没后复权。禁止未确认列语义就删列。 |
| **I-17** | SPEC-008：形参 `net_pnl_pts`，慢环喂 `p["pnl"]` = `position_sign * delta_real`（毛） | Task 2：`aligned_slow_loop.py:109-114`；名义 MaxDD 走 `calc_net_metrics` | 保证金 MaxDD 改吃净 PnL。不进 `gate()`。 |
| **I-01** | SPEC-012：`cascade_predict` 可交易方向走 `position_from_forecast`；`copilot` 卡面 `direction = _compute_direction_v2` | Task 2 部分对齐；`copilot.py:434` vs `cascade_predict.py:208-242` | Copilot `run_one` 改调加权 1H，日线只留副标签。不要改 `position_from_forecast`。 |
| **I-03** | 方案 A「peers 禁止评估 / 禁止加载 TimesFM」只写在提示词；`task.yaml` `diagnostic.launch_allowed: true`，评估入口 `evaluations/fm_eval/run.py`，peer role 仍给 `evaluation_tools.peer` | Task 4 H2；`task_FM/task.yaml:55,83-85,136-137`。**不升 Critical**（裁定 2） | `launch_allowed: false`；拿掉 peer 的 `evaluation_tools`。不要按 spec 20 去教 peer 跑 `fm_eval`。 |
| **I-18** | 方案 A `:144`「schema 不符即拒绝」；`harvest_proposals` 不读 `p["schema"]` | Task 4 G1；`praxist_supervisor.py:603-623` 无此符号 | `_reject("schema_mismatch")` 除非 `== "fm.hypothesis_proposal.v1"`。 |

`craft_advisory_v2` 未进 `run_one`（Task 2 High / 上一轮 **M-10**）：活路径 `copilot.py:445` 仍调 v1。不改信号、不改 SCHEMES。本表不升 Important，仍引用 M-10。要修就改接线，不要为了对齐去改 `SCHEMES`。

#### B. 本轮新挂到有效条款（上一轮未单独成 I-xx，或只在 Minor）

| 本轮 ID | 严重度 | spec 条款 | 代码 | 为何 Important | 修 |
|---------|--------|-----------|------|----------------|----|
| **SA-012-log** | Important | SPEC-012 对数空间 `polyfit(log(forecast))` | `daily_model.py:146-150` 对**价格**线性回归再 `/ mean` | 标签量纲与合同不符；Copilot v2 吃这条斜率。不进硬门。 | 改成对数回归，或改 spec 承认线性 `/mean`。测试必须走 `DailyModel.predict`。 |
| **SA-006-revoked** | Important | SPEC-006：连续 2 个月 degraded → `revoked` | `build_knowledge_base.py` **无**连续月计数，sync **从不写** `revoked` | 退役合同半截：degraded 会写，revoked 永远不会自动出现。不改 SCHEMES。 | 按月计数或改 spec 删这条规则。不要为了 revoked 去改 `prediction_scheme.py`。 |
| **SA-A-family** | Important | 方案 A `:144` family 缺 → reject | `praxist_supervisor.py:628` fallback `"other"` 继续入队 | 与 schema 同属收割拒绝清单。池内 active 目前都有 family，活风险低于 I-18。 | 双源皆空则 `_reject("family_missing")`。 |
| **SA-C1** | Important | Phase 4：horizon 复用交易日历 | `features.py:2226-2233` 自走 `replace(minute=0)` + 周末爬行；`daily_slope` 用 `generate_trading_dates`（周末跳周一 00:00） | 日历品种（ss/sp/fu/m/bu/cf/ao/eg/ta）第 k 根 XReg 日历编码可能对不上 `daily_slope` 的时钟。不是把未来收盘偷进 XReg。上一轮 cascade M2 仅 Minor，本轮挂回 Phase 4 条款。 | 日历 horizon 直接用已算好的 `future_dates`。不要改 SCHEMES。 |
| **SA-S1** | Important | followup-4 方向 3：DirAcc 展示名 + 3% MAE 显著性标签 | `scripts/covariate_scan.py` **不存在**；`covariate_scan_new.py` 无这些标签 | 不改现行 SCHEMES 仓位。后人再拿 7pt DirAcc 当裁决会选错协变量。STATE `:601` 写「已完成」，磁盘合同断了。 | 在仍用的 scan 入口补标签，或 spec/STATE 标明旧 scan 退役。 |
| **SA-CP-path** | Important（运维，不改信号） | 控制面 / ACCEPT：hardcap daemon 3s 后备；unstick 数 claude | `timesfm_hardcap_daemon.py:13` `REPO = Path('/workspace/repos/timesfm-abug1029')`（本机 `/workspace` 不存在）；unstick `pgrep -f /home/box/.local/bin/claude`（本机在 `/home/abug/...`） | flock 主路径仍对齐。后备 daemon 起不来；unstick 在 WSL 上 `claude_n` 恒 0，可能误触发解卡。不是 15GiB 问题。 | daemon 根改本仓；pgrep 改本机路径。**不要**动 `MIN_AVAIL_BYTES` / 槽位数。 |

未列入 Important（Realist 降级）：

- SPEC-009 copilot/monthly 不传 `half_life_bars`：活 `SCHEMES` 全默认 12.0，当前信号不变。Medium 接线债，另开 plan 时再收。
- 控制面 G1 cgroup 0.85：代码只有 0.90；本机无 cgroup，门是惰性的。改文档即可。
- 控制面 G5 安装器 python3.13 / `/home/box`：现 3.11 `.pth` 已装，只在重建 venv 时踩坑。

---

## 失效清单（不当缺口）

杀手必须是更高权威，不是状态栏。按这份去改代码 = 把死设计接回主路径。

### 整份设计失效

| # | Spec | 杀手 | 残留能力面（引用，不新开） |
|:-:|------|------|---------------------------|
| 13 | A2-P1 dense-cache | `STATE.md:74,100-103` A2-P1.1 / A2-P2 **0/5 GO**；`module_freeze.md:9` CF-13 **A** 永久关闭 Track B | `scripts/a2_p1_*.py`、`cascade/lgbm_features.py`（生产入口 0 import） |
| 14 | A2-P1 market-vectorize | 同 13 | 同上 |
| 15 | A2-P1 runtime | 同 13 | orchestrator / worker / status；网格数字已跟 `STEP=2`，不是 396 合同复活 |
| 19 | `praxist_integration_plan.md` | 文件自身 L3–5：以 `praxist.md` + 方案 A 为准；`/root/timesFM_fu`、独立 venv、peer 跑 diagnostic、8.4GB 过时 | P0 预注册所有权已迁 `loop-constraints.md` |
| 20 | `praxist_peer_evaluation_fix.md` | `loop-constraints.md:50`；方案 A `:37`。目标是让 peer 跑 `fm_eval/run.py` | 上一轮 **M-02** 状态栏「待执行」。禁止按它施工 |

### 部分有效里已杀掉的条款

| 出处 | 失效内容 | 杀手 | 不要做 |
|------|----------|------|--------|
| spec 3 / 09-02 X1–X10 | diagnostic 筛选、诊断幸存者收割、`evaluation_summary` 当收割源、非 429 才 harvest、计划绑定解释 #4 | `loop-constraints.md:49-50`；方案 A `:37,57-62,142-149`；控制面 `:191` | **不要**把 `_harvest_rows` 改回 `harvest_survivors`。函数体按方案 A `:221` 是回滚面 = 上一轮 **I-03** 旁路，不是缺口 |
| spec 4 | 宿主 **15GiB** / 0 Swap；「peer eval 硬顶」作战；goal 表 20 cycles / 2026-09-20；harvest 按诊断 EV 选座；归档 `/workspace/...`；「禁止 supervisor 持续跑」绝对句 | `host_environment_assessment.md:3-10`（7.7GiB）；方案 A；磁盘 `praxist_goal.yaml` 无限制；控制面自己 L166 已批自转 | **不要**改代码去贴 15GiB，也不要把槽位抬到 2「因为 peer 不加载」 |
| spec 6 / 7 / 8 / 12 | 品种级当时固化（CJ gated、TA `basis_momentum` / `bb_squeeze`、JD `rsi_state+oi`、EG/MA 表内首选等） | Phase 11 结案 + 活 `SCHEMES`（CJ=`hourly_slope`，TA=`calendar_cyclical`，JD=`rsi_state`） | 不要按 07 月战役表改 `prediction_scheme.py` |
| spec 10 | 「应固化 crack」 | spec 自己 §0.3/§6「8a 不固化」+ scheme 注释归档 | 池内实现对齐即可 |
| spec 11 | LGBM 当生产预测器；打败 scheme → 开 A2-P2 / 残差叠加 | STATE 0/5 GO + CF-13；四入口 AST 0 import | **不要**把 LGBM 接进 copilot / cascade / monthly / supervisor |
| spec 16 | 「GREEN → 固化 NVI/QSTICK/VWAP/StdDev 进 SCHEMES」；「0 GREEN → 路径彻底穷尽」；原文 StdDev=std(close) | `STATE.md:18,489-509` **24 tests 0 GREEN**，「非路径彻底穷尽」；15b 保留 returns std | **不要**晋升进 SCHEMES，不要把 StdDev 改回价格 std |
| spec 17 | glob「仅本 run」 | 同文件 2026-09-09 增补：每 cycle 重扫 `run_*` | 不是缺口 |
| spec 18 §3 | diagnostic → aligned 阶梯；peer 每代 aligned 限额 | 文件自己 L3 横幅 + 方案 A | 指令闭环仍有效；不要按 §3 给 peer 开评估 |

---

## 子报告冲突与本表处理

| 冲突 | 处理 |
|------|------|
| Task 7 把 spec 11 整份标失效；Task 1 标部分有效 | 有效性跟 Task 1。生产模型条款失效、缺口 0。评价秤未进 monthly/慢环 = Task 7 证伪「慢环用 A2 秤」，不把库函数写成仍有效硬门 |
| Task 4 开放问题「若 Praxist 自动跑 fm_eval 则 H2 升 Critical」 | **裁定 2：不升。** I-03 保持 Important |
| Task 2 把 SPEC-011 / SPEC-008 标 High | 去重为 I-13 / I-17。不进本轮 Critical（不改 `gate()`；未证活信号已系统性打歪） |
| Task 2 `craft_advisory_v2` High vs 上一轮 M-10 Minor | 不升。不改信号。引用 M-10 |
| Task 6 C1 上一轮仅 Minor | 本轮挂 Phase 4 有效条款，升 Important（SA-C1）。仍不是 Critical |
| Task 5 15GiB / peer eval | **失效，不是缺口。** 不要改 `mem_guard.py` 去迁就 |
| compile-skip spec 状态「待审阅」、验收框全空 | **对齐**（裁定 4）。文档框过期 = 上一轮 I-05，改横幅 |
| hardening 10 缺口看起来像「没做」 | **部分对齐**（裁定 4）。SPEC-004…013 已在 master（`243693d`）；10 条是公式/接线偏离，不是整份没落地 |

未发现子报告在「compile-skip 已落地」「harvest 活路径是 `harvest_proposals`」「crack 池公式对齐」「A2 生产入口 0 import」上互相打架。

---

## 建议（不落地）

### 只改文档横幅

1. hardening / compile-skip spec 与计划：改「已落地 master」，勾选框不要再当施工单（上一轮 I-05）。
2. `praxist_control_plane.md` L3：宿主改 7.7GiB；「peer eval」改成「TimesFM / aligned 加载（现仅慢环）」；2.5GiB 改「拒启」；删 15GiB / 0 Swap / goal 表 20 cycles。
3. 09-02 spec / 计划绑定解释 #4 / runbook L192：加「方案 A 之后诊断收割作废」横幅（上一轮 DC-3）。
4. 四份 Alpha2 spec + `alpha2-next-steps.md`：文首写 CF-13 / 0/5 GO 永久关闭；生产入口不 import。
5. Phase 15：「应固化」加失效横幅，指向 STATE 0 GREEN。
6. `praxist_peer_evaluation_fix.md`：状态从「待执行」改成「失效（方案 A）」。
7. CJ scheme 注释仍写影线门控（`prediction_scheme.py:424` vs 活 `hourly_slope`）——改注释。

改文档时 **禁止** 顺手改 `prediction_scheme.py`、`evaluator.gate`、`BacktestDataStore`、`MIN_AVAIL_BYTES`。

### 有效缺口另开 plan（人工确认高风险路径）

| 顺序 | 做什么 | 对应 |
|------|--------|------|
| 已有 C1 | 实盘日线接 `get_safe_daily` | 上一轮 CC-1，不在本 20 份 spec 内 |
| 1 | harvest 拒绝非 `fm.hypothesis_proposal.v1`；family 双空 reject | I-18、SA-A-family |
| 2 | 关掉 peer 评估能力面（不是去实现 spec 20） | I-03 |
| 3 | SPEC-011：打开截面复权 **或** 文档承认没复权 | I-13 |
| 4 | 保证金 MaxDD 吃净 PnL | I-17 |
| 5 | Copilot 主方向改 `position_from_forecast` | I-01 |
| 6 | SPEC-012 对数回归（或改 spec） | SA-012-log |
| 7 | 日历 horizon 复用 `generate_trading_dates` | SA-C1 |
| 8 | scan 标签或正式退役 | SA-S1 |
| 9 | daemon / unstick 旧盒路径 | SA-CP-path |
| 10 | SPEC-006 连续月 revoked（或删规则） | SA-006-revoked |

### 明确不要做

- 不要实现 diagnostic 收割 / 把 `harvest_survivors` 接回 `_harvest_rows`
- 不要把 A2 LGBM 接进生产入口
- 不要把 NVI/QSTICK/VWAP/StdDev 写入 SCHEMES
- 不要改代码去满足 15GiB，也不要把 flock 抬到 2
- 不要按 `praxist_peer_evaluation_fix.md` 教 peer 跑 `fm_eval`
- 不要给 `evaluator.gate` 加 EV
- 不要按 07 月固化表改 CJ/TA/JD

---

## 给后续的计数（一页）

| 项 | 数 |
|----|----|
| spec 仍有效 | 5 |
| spec 部分有效 | 10 |
| spec 设计失效 | 5 |
| 总评对齐 | 3（compile-skip、ACCEPT flock、crack 池） |
| 总评部分对齐 | 12 |
| 本轮新代码 Critical | **0** |
| 有效缺口 Important（去重后） | **11**（引用上一轮 5：I-13/I-17/I-01/I-03/I-18；新挂 6：SA-012-log / SA-006-revoked / SA-A-family / SA-C1 / SA-S1 / SA-CP-path） |
| 失效整份 | 5（13, 14, 15, 19, 20） |
| 失效条款（仍活文件里） | 见上表 spec 3/4/6/7/8/11/12/16/17/18 |

hardening 10 缺口按严重度：High 4 条全部并入上一轮 I-13/I-17/M-10（后复权 2 条 + MaxDD + v2 未接线）；其余 Medium/Low 只把对数回归与 revoked 留在 Important。

---

## 状态

**DONE**

- path: `docs/superpowers/reports/2026-09-11-audit/spec-alignment/SUMMARY.md`
- 20 行已齐
- 有效缺口只保留 Critical/Important；失效设计未当代码缺口
- 本审核不改代码

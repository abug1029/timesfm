# Task 1：Spec 有效 / 失效判定表

**日期**: 2026-09-11  
**范围**: 计划清单 specs 1–20（另记 critical-fixes SPEC-001…003 无独立文件）  
**权威链**（后者不能推翻前者的磁盘事实）:
1. `STATE.md` + `config/prediction_scheme.py` + `config/backtest_config.py` + `config/praxist_task.yaml` + `loop-constraints.md`
2. `docs/spec_hypothesis_driven_fast_loop_20260908.md`（方案 A）+ `docs/praxist.md`
3. 仍有效的 superpowers spec 接口（hardening SPEC-004…013、compile-skip）
4. 早期协变量 spec：仅当机制仍在 `SCHEMES` 或 `cascade/features.py` 生产/池路径上

**判定规则**（本表严格执行，不把状态栏当杀手）:
- **设计失效**的唯一合法理由：后续更高权威明确废止——`STATE.md` 结案、`loop-constraints.md` 方案 A、后一份 spec 的 Non-Goals / 取代声明、0/N GO 关轨。
- 仅「状态栏待审核 / 待审阅 / Draft / 日期早」**不够**作废。本表未因此作废的例子：compile-skip「待审阅」、09-02「待审阅」、Phase 4/8「待用户审核」、A2-P1「Draft 待用户 review」、dense-cache「待审核」。
- **仍有效**：即使文件标历史，机制仍在生产路径（`SCHEMES` 或现行三环合同）就必须对齐。
- **部分有效**：拆条；不要整份扔掉。
- 活 `SCHEMES` `covariate_type` 并集（已核对 `config/prediction_scheme.py`）：`ao_accel, calendar_cyclical, ha_body, hourly_slope, reversal_shadow, rsi_state`；组合里还有 `oi`。与计划给定集合一致。

**不计代码对错**：本文件只判合同是否还活。缺口留给 Task 2–7。

---

## 0. 计数

| 判定 | 份数 | 编号 |
|------|:----:|------|
| 仍有效 | 5 | 1, 2, 5, 9, 17 |
| 部分有效 | 10 | 3, 4, 6, 7, 8, 10, 11, 12, 16, 18 |
| 设计失效 | 5 | 13, 14, 15, 19, 20 |
| 合计 | 20 | — |

critical-fixes SPEC-001…003：仓内无独立 spec 文件。本任务记「无文件」，条款对齐并入 Task 2（`get_safe_daily` / 前视），用 git `cd29bb6` 与代码，不发明一份不存在的 spec。

---

## 1. 总表（必须每份一行）

| # | Spec | 状态栏（不作为杀手） | 判定 | 杀手或仍有效依据 |
|:-:|------|----------------------|------|------------------|
| 1 | `docs/superpowers/specs/2026-09-10-system-hardening-design.md` | v1.2-final 终审封版 | **仍有效** | 权威链第 3 档接口；无后续废止。Non-Goals 明确不改硬门、不改 `SCHEMES` 协变量、不引入新协变量——与现行生产一致。 |
| 2 | `docs/superpowers/specs/2026-09-09-compile-skip-phase1-design.md` | 待审阅 | **仍有效** | 「待审阅」不够作废。无 STATE / 方案 A / 后份 Non-Goals 废止 compile 指纹跳过。仍是慢环效率合同。 |
| 3 | `docs/superpowers/specs/2026-09-02-praxist-three-loop-design.md` | 待审阅 | **部分有效** | 杀手：方案 A。`loop-constraints.md:50`「peers 不再跑任何评估/加载 TimesFM」；`spec_hypothesis…md:37`「Peer 不再跑评估」；`STATE.md:22,33`「方案 A：peer 写假设，慢环唯一验证器」。骨架（慢环独占 verdict、daily 缓存、429 resume）未被废止。 |
| 4 | `docs/superpowers/specs/praxist_control_plane.md` | 2026-09-06 已批准稳妥启动 | **部分有效** | 2.5GiB / slots=1 / 429 / 启停审批仍是控制面合同（与 spec 5 一致）。宿主「15GiB」被方案 A 实施后增补废止（`spec_hypothesis…md:13` 现 7.7 GiB）。「peer eval 硬顶」作为 peer 跑 TimesFM 的前提被方案 A 废止；慢环 TimesFM 的 flock 硬顶仍有效。 |
| 5 | `docs/superpowers/specs/ACCEPT_flock_20260906.md` | 无状态栏（验收记录） | **仍有效** | `MIN_AVAIL_BYTES=2.5GiB`、`DEFAULT_MAX_SLOTS=1` 无后续废止。方案 A 只停 peer 评估，不停慢环 flock。 |
| 6 | `docs/superpowers/specs/2026-07-28-covariate-optimization-design.md` | Approved (Phase 1 in progress) | **部分有效** | 扫描工具补量、ha_body / reversal_shadow / ao_accel 等机制仍在 `SCHEMES` 或池。品种级固化建议被后续 Phase 11 `STATE.md` 结案覆盖（例：CJ 现为 `hourly_slope`，不是 spec 首选 `reversal_shadow`）。 |
| 7 | `docs/superpowers/specs/2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md` | Draft 待用户审批 | **部分有效** | Draft 不够作废。`reversal_shadow` 仍在 `SCHEMES`（i/sh/p）。CJ 改 `reversal_shadow_gated` 被 Phase 11 结案杀掉（CJ=`hourly_slope`，`prediction_scheme.py:420`）。`basis_momentum` 生产固化被 STATE Q1 D3「已归档」+ TA 注释 Phase 6 归档杀掉；函数与池注册仍在。 |
| 8 | `docs/superpowers/specs/2026-07-29-followup-4-directions-optimization-design.md` | 等待 spec 自审 + 用户审阅 | **部分有效** | 方向 1/2 仍活：`STATE.md:599-600` 与 `monthly_backtest.py` 仍有 `--cache-interval` / `--max-points` / `--resume`；`get_basis_1h` P95×5% OI 过滤。方向 4「TA 保 bb_squeeze」被 Phase 11 结案杀掉（TA=`calendar_cyclical`，`prediction_scheme.py:479`）。 |
| 9 | `docs/superpowers/specs/2026-07-29-phase4-calendar-cyclical-design.md` | 待用户审核 | **仍有效** | 「待用户审核」不够作废。`calendar_cyclical` 在活 `SCHEMES`（ss/sp/fu/m/bu/cf/ao/eg/ta 等）。后续 SPEC-010 是增强，不是废止。 |
| 10 | `docs/superpowers/specs/2026-07-31-phase8-crack-spread-design.md` | 待用户审核 | **部分有效** | Spec 自身 `§0.3/§6`「Phase 8a 不固化」。`SCHEMES` TA 注释 `prediction_scheme.py:489`「Phase 8a crack_spread 弱信号, 归档」。`calc_crack_spread`（`features.py:749`）+ 三模式分发仍在；`task_FM/config/covariate_pool.json` 三 mode 均为 `active`。池内仍有效，非 `SCHEMES` 合同。 |
| 11 | `docs/superpowers/specs/2026-08-04-alpha2-phase1-baseline-gate-design.md` | Draft 待用户 review | **部分有效** | LGBM 当生产模型：spec 自身 Non-Goals 本就不改生产路径；`STATE.md:74,100-103` A2-P1.1 0/5 GO + A2-P2 0/5 GO **关闭 Track B**。评价秤 `calc_vol_scaled_mae`（`evaluation_metrics.py:285`）+ 测试 + `scripts/a2_p1_*.py` JSONL 工具仍在。生产入口 `copilot.py` / `cascade_predict.py` / `monthly_backtest.py` / `praxist_supervisor.py` / `aligned_slow_loop.py` **不 import** `a2_p1`。 |
| 12 | `docs/superpowers/specs/2026-08-04-phase9-toxic-variety-design.md` | 无状态栏 | **部分有效** | AO 固化 `hourly_slope+calendar_cyclical` 仍在 `SCHEMES`（`prediction_scheme.py:357-358`，注释 2026-08-04）。ha_body 对 AO/JD 有毒：生产 AO/JD 均未用 ha_body。JD 候选列表被 Phase 11 结案改成单 `rsi_state`（`prediction_scheme.py:439`）。 |
| 13 | `docs/superpowers/specs/2026-08-05-a2-p1-dense-cache-resume-design.md` | 待审核 | **设计失效** | 待审核不够。杀手：Alpha2 模型轨 0/N GO 关轨——`STATE.md:74` A2-P1.1 0/5 GO、`STATE.md:100-103` 关闭 Track B。本 spec 只服务该探针的 dense matrix。生产入口不调用。残留：`scripts/a2_p1_*.py`、`reports/a2_p1_features/`。 |
| 14 | `docs/superpowers/specs/2026-08-05-a2-p1-market-vectorize-design.md` | 待审核 | **设计失效** | 同 13。只加速 A2-P1 market 特征；关轨后不再是生产合同。残留脚本同上。 |
| 15 | `docs/superpowers/specs/2026-08-05-a2-p1-runtime-redesign.md` | 待审核 | **设计失效** | 同 13。替代对象是 `a2_p1_lgbm_baseline.py` 单进程探针，不是 Copilot/慢环。关轨后整份不再是合同。残留：orchestrator/worker/status 脚本。 |
| 16 | `docs/superpowers/specs/2026-08-22-phase15-new-covariates-design.md` | 待审核 (v2) | **部分有效** | 「应固化 NVI/QSTICK/VWAP/StdDev 进 `SCHEMES`」失效：`STATE.md:18,506` 24 tests **0 GREEN**；Q1 D2/D4 CANCEL（`STATE.md:584,586`）。「失败则路径彻底穷尽」被 STATE 修订为「非路径彻底穷尽」（`STATE.md:18,509`）。`_calc_nvi/_calc_qstick/_calc_vwap_deviation/_calc_stddev`（`features.py:872,917,930,957`）仍在池内；Phase 15b StdDev 改 returns std **保留**（`STATE.md:534-536`）。固化合同失效，实现对齐任务另走 Task 6。 |
| 17 | `docs/spec_hypothesis_driven_fast_loop_20260908.md` | **已实施** | **仍有效** | 现行快环合同。`STATE.md:22,33`；`loop-constraints.md:48-56` 方案 A 修订。权威链第 2 档。 |
| 18 | `docs/praxist_directive_design.md` | 2026-09-09 横幅自述 | **部分有效** | 文件自身 `docs/praxist_directive_design.md:3`：「指令闭环（PI 议程 × 角色契约 × 证据路径）仍有效。§3 的 diagnostic/aligned 证据阶梯与『peer 跑评估』已被 2026-09-08 **方案 A** 取代」。 |
| 19 | `docs/praxist_integration_plan.md` | 2026-09-09：保留为方案稿 | **设计失效** | 文件自身取代声明 `docs/praxist_integration_plan.md:3-5`：「路径与现行架构以 `praxist.md` 和方案 A 为准」；点名 peer 跑 diagnostic、`/root/timesFM_fu`、独立 `/root/.praxist-venv`、磁盘 8.4GB 为过时假设。P0 预注册等活条款已迁入 `loop-constraints.md` / 方案 A，**本文件不再是合同**。 |
| 20 | `docs/praxist_peer_evaluation_fix.md` | 待执行 | **设计失效** | 「待执行」不够。杀手：整份目标是让 peer 跑成评估；方案 A 废止该目标——`loop-constraints.md:50`、`spec_hypothesis…md:37`、directive 横幅。按本 spec 去修 delete guard / 教 peer 调 `fm_eval/run.py` 会与现行合同相反。 |

---

## 2. 部分有效拆条

### 3. `2026-09-02-praxist-three-loop-design.md`

**仍有效**
- 三环骨架：监督环 / 快环 / 慢环；cycle = 快环一次 + 慢环清队列。
- daily 预测按 `(symbol, cutoff)` 缓存（`§4.1`）。
- 慢环 `aligned_slow_loop.py`：checkpoint 续跑、单实例 flock、SIGTERM 可恢复。
- `aligned_verdicts.jsonl` **仅慢环写**（`§4.3`）；与 `loop-constraints.md:17-21` 同文。
- 429 解析、配额窗等待、resume（`§4.4` / `§6` / 验收「429 注入演练」）。
- goal.yaml 可测量条件；不自动改 goal（`§9` 非目标仍立）。

**失效**（杀手：方案 A）
- `§3`「PI 面板 + 4 角色 peers + **diagnostic 筛选**」；「产出: **诊断幸存者** -> pending 队列」。
- `§3` 数据流「run_summary + **frontier 幸存者**」再收割。
- `§4.4` 第 4 步「run 结束…**收割幸存者入队**」（诊断档幸存者）。
- 验收「supervisor 起 run -> **收割入队**」若指 diagnostic frontier，已改成 `harvest_proposals`（`spec_hypothesis…md:217-219`）。

取代合同：`docs/spec_hypothesis_driven_fast_loop_20260908.md`。慢环本身「不改」（该 spec `§1.4` 非目标）。

### 4. `praxist_control_plane.md`

**仍有效**
- MemAvailable < 2.5 GiB 预警；< 2.2 GiB 强制评测并发 ≤ 1。
- flock 槽位默认 1；加压 eval=2 须另批。
- 429 / paused_429 / failover 纪律；启停须总管批准；禁止未授权 `praxist start`。
- `scripts/mem_guard.py` + hook 作为实现锚点（与 spec 5 同一套阈值）。

**失效**
- 文首「宿主：8×CPU / **15GiB**」：杀手 `spec_hypothesis…md:13`「7.7 GiB RAM」；`docs/host_environment_assessment.md:3,10` 2026-09-09 迁移声明。
- 「主动停 **peer eval** / 真实 `fm_eval` 作为 peer 工作负载」：杀手方案 A（peer 0 次模型加载）。慢环 TimesFM 的容量硬顶不因此作废。

### 6. `2026-07-28-covariate-optimization-design.md`

**仍有效**
- Phase 0：scan 列表纳入 ha_body / reversal_shadow / ao_accel 等（这些类型现仍在 `SCHEMES` 或 `features.py` 分发链）。
- 双段闸门：scan 快筛 + `monthly_backtest` walk-forward 再固化。
- 「达阈才改 `prediction_scheme.py`」的人工固化纪律（与 loop-constraints 禁自动改 SCHEMES 同向）。

**失效**
- 品种级当时推荐（MA→ha_body、CJ→reversal_shadow、JD 日历「本轮不做」后的过渡配置等）。杀手：`STATE.md` Phase 11 结案（L12 附近 + Phase 11 节）把活 `SCHEMES` 重写成上表；CJ=`hourly_slope`，JD=`rsi_state`，MA 仍 `hourly_slope+oi`（并未换成 ha_body）。
- TA「技术无效已归档」后被后续 Phase 复活再被 Phase 11 换成 `calendar_cyclical`——本 spec 的 TA 结论不是现行合同。

### 7. `2026-07-28-phase5-6-shadow-threshold-and-basis-pipeline-design.md`

**仍有效**
- `calc_reversal_shadow_ratio` 增 `min_shadow_atr` 默认 0（现有品种字节级不变）——`reversal_shadow` 仍服务 i/sh/p。
- 门控变体 `reversal_shadow_gated_02/_03/_05` 仍在 `features.py:1297+` 与 `covariate_pool.json`（池内，非 SCHEMES）。
- 近远月采集 / `get_basis_1h` 管道作为数据层能力（方向 2 的 OI 过滤仍活，见 spec 8）。

**失效**
- 「CJ scheme 的 `covariate_type` 改为胜出的 gated 版」。杀手：Phase 11 结案，CJ=`hourly_slope`（`prediction_scheme.py:420`）。
- 「TA 用 `basis_momentum` 实证后固化」。杀手：TA 注释 Phase 6 归档（`prediction_scheme.py:488`）；`STATE.md:585` Q1 D3「basis_momentum SKIP，已归档，无活跃方案」。

说明：`covariate_pool.json` 里 `basis_momentum` 仍标 `active`，这是池文件与 STATE 的漂移，**不能**把池标 active 当成 SCHEMES 合同复活。Task 6 可记残留能力面，本表不把归档生产协变量判回「仍有效固化」。

### 8. `2026-07-29-followup-4-directions-optimization-design.md`

**仍有效**
- 方向 1：`--cache-interval` / `--max-points` / `--resume` JSONL 断点。`STATE.md:599` 勾选；`monthly_backtest.py` 仍有这些开关。
- 方向 2：`get_basis_1h` 合约自身 P95×5% OI 过滤。`STATE.md:600`。
- 方向 3：scan 展示层 DirAcc 不参与裁决 + 相对 MAE 显著性标签（无后续废止）。

**失效**
- 方向 4：「TA: bb_squeeze 固化」「保 bb_squeeze」。杀手：Phase 11 结案 TA=`calendar_cyclical`（`prediction_scheme.py:479-480`）。归档注释里 Phase 6/8a 历史仍可当史料，不是现行 covariate_type。

### 10. `2026-07-31-phase8-crack-spread-design.md`

**仍有效（池 / 实现，非 SCHEMES）**
- 公式 `spread = TA_close - 0.655 × PX_close`、三 mode、left-join+ffill、max_ffill_gap、feedstock 继承 cutoff。
- `cascade/features.py:749 calc_crack_spread`；`config/crack_spread_pairs.py`；单/组合分发；池内 `crack_spread_{slope,level,zscore}` = `active`。

**失效（固化合同）**
- 向 `prediction_scheme.py` 固化 crack。Spec 自己就写「Phase 8a 不固化」（`§0.3` L35、`§6` L300）。SCHEMES 再加归档戳（L489）。不是「待审核」作废，是**从未成为 SCHEMES 合同** + 归档声明。

本行判定：**部分有效** = 「池内仍有效，非 SCHEMES 合同」。

### 11. `2026-08-04-alpha2-phase1-baseline-gate-design.md`

**仍有效**
- 评价库字段：`calc_vol_scaled_mae`（`cascade/evaluation_metrics.py:285`）+ `tests/test_vol_scaled_mae.py`。
- JSONL 逐点追加、品种进程隔离——作为 **A2 工具脚本形态** 仍躺在 `scripts/a2_p1_*.py`。
- Spec 自己的 Non-Goals：不改 `forecast_with_covariates`、不改 `prediction_scheme.py` / `features.py`——这条从未被违反，也未被废止。

**失效**
- 「LGBM-B 打赢 scheme → 启动 A2-P2 / 残差叠加」。杀手：`STATE.md:74` 0/5 GO；`STATE.md:80-103` A2-P2 **0/5 GO**，「关闭 Track B，不启动 A2-P3」。
- 把 LGBM 当生产预测器：生产入口不 import `a2_p1`（已 grep `copilot.py` / `cascade_predict.py` / `monthly_backtest.py` / `praxist_supervisor.py` / `aligned_slow_loop.py`，无命中）。

`monthly_backtest.py` / 慢环 **不调用** `calc_vol_scaled_mae`。评价秤活在库+测试+A2 脚本，不是慢环硬门。硬门仍是 n/IC/EV/PF（方案 A / loop-constraints）。

### 12. `2026-08-04-phase9-toxic-variety-design.md`

**仍有效**
- AO 不用 ha_body；现行 `hourly_slope+calendar_cyclical`（`prediction_scheme.py:357-358`）即本 spec 候选 #8，注释写 2026-08-04 固化。
- JD 不用 ha_body（现 `rsi_state`）。
- v2 裁决规则作为当时固化闸门的历史合同；AO 那次 PASS 仍写在 SCHEMES 注释里。

**失效**
- JD 候选「保持 rsi_state+oi / 试 rsi_state+oi+calendar」作为现行方案。杀手：Phase 11 结案 JD=`rsi_state` 单协变量（`prediction_scheme.py:439-440`）。
- 候选表里未胜出、也未进 SCHEMES 的条目（AO 的 vor/bb_squeeze 等）本来就不是合同。

### 16. `2026-08-22-phase15-new-covariates-design.md`

**仍有效（实现 / 池，非固化）**
- 四函数定义与 `build_*` 分发仍在 `features.py`。
- Phase 15b：StdDev 用 returns std **保留**（`STATE.md:534-536`）；VWAP 衰减填充回滚是后续修订，不是把 `_calc_vwap_deviation` 整函数删除。
- 池内 `nvi/qstick/vwap_deviation/stddev` 均为 `active`（可被慢环 `cov_override` 扫，不是 SCHEMES 默认）。

**失效（固化与穷尽声明）**
- 「GREEN → 固化进 SCHEMES」。杀手：`STATE.md:18,489-509` **24 tests 全 FAIL, 0 GREEN**。
- 「0 GREEN 且 PF 无提升 → 宣告协变量路径彻底穷尽」（spec `§1` / 固化决策表）。杀手：`STATE.md:18,509` 明确改成「非路径彻底穷尽」。
- Q1 对 QSTICK 窗口 / NVI lookback 的继续调参：`STATE.md:584,586` CANCEL。

### 18. `docs/praxist_directive_design.md`

**仍有效**
- 指令闭环：PI 议程 × 角色契约 × 证据路径（文件 L3 自承仍有效）。
- P1 结构化假设卡（mechanism-first）——被方案 A 吸收进 `fm.hypothesis_proposal.v1`。
- P4 证据纪律（canonical results 树、share_finding）在「peer 不跑评估」前提下仍约束快环产物。
- P5 每代指令要有信息增量。

**失效**
- `§3` P2 **diagnostic (p3/p6) 快筛 → aligned 确认**；「peers 执行 (diagnostic 筛 -> aligned 确认)」。
- aligned 每 peer 每代限额 2 次（peer 侧评估预算）。杀手：方案 A，peer 0 次 TimesFM。
- `§4` 落地映射里「阶梯感知评估器 STAGE_POINTS」作为 **peer 必跑评估** 的合同（宿主冒烟 diagnostic 仍可存在，见方案 A `§4` staged_protocols 降级为宿主冒烟——那是方案 A 的条款，不是本文件 §3）。

---

## 3. 设计失效的残留（不当缺口）

| # | 残留 | 处理 |
|---|------|------|
| 13–15 | `scripts/a2_p1_orchestrator.py` / `worker.py` / `runtime.py` / `lgbm_baseline.py` 等 | 残留能力面。Task 7 列清单。不要按这些 spec 去改 Copilot/慢环。 |
| 19 | P0 预注册口径、红线「peers 不改 SCHEMES」 | 活条款的**所有权已迁走**（`loop-constraints.md` 预注册段、方案 A）。对齐时引用迁入后的文件，不引用本方案稿。 |
| 20 | delete guard / sitecustomize 技术事实 | 可当事故记录。禁止按「让 peer 跑 `fm_eval/run.py`」实施。 |

---

## 4. 预置嫌疑：证实或证伪

计划 Task 1 Step 3 的预置嫌疑，本表结论：

| 预置嫌疑 | 结论 | 证据 |
|----------|------|------|
| 09-02 的 diagnostic 收割 = 失效（方案 A）；慢环唯一写 verdict / daily 缓存 / 429 resume = 仍有效 | **证实** | 见 §2 spec 3 拆条；杀手 `loop-constraints.md:50`、`spec_hypothesis…md:37`、`STATE.md:22,33`。 |
| A2-P2 残差叠加 / Track B = 失效（STATE 0/5 GO） | **证实** | `STATE.md:80-103`。清单 1–20 无独立 A2-P2 spec；挂在 spec 11 失效条。 |
| A2-P1 LGBM 作为生产模型 = 失效；评价秤/JSONL 若仍被工具使用 = 部分有效 | **证实** | 生产入口不 import `a2_p1`；`calc_vol_scaled_mae` 在评价库+测试+`a2_p1_lgbm_baseline.py`。整份 → **部分有效**。 |
| Phase 15「应固化 NVI/QSTICK/VWAP」= 失效（0 GREEN）；`_calc_stddev` 等实现仍在 features = 实现对齐任务，不是固化合同 | **证实** | `STATE.md:18,506`；`features.py:872+`。整份 → **部分有效**。 |
| calendar / reversal_shadow / rsi_state / hourly_slope 设计 = 仍有效（在 SCHEMES） | **证实** | 活集合见下节。Phase 4 整份 **仍有效**；shadow/rsi/hourly 的设计条款分别落在 spec 7/6/12 的仍有效条，不是把那些历史战役 spec 整份标仍有效。 |
| crack_spread = 若 SCHEMES 未用但 `calc_crack_spread` 仍被池/扫描调用，标「池内仍有效，非 SCHEMES 合同」 | **证实** | spec 10 **部分有效**。SCHEMES 归档注释 L489；函数 L749；池三 mode `active`。 |

---

## 5. 活 SCHEMES `covariate_type` 核对

来源：`config/prediction_scheme.py` `SCHEMES`（只读核对，未改）。

| 类型 | 出现（含 combo） |
|------|------------------|
| `calendar_cyclical` | ss, sp, fu, m, bu, cf, ao, eg, ta |
| `ao_accel` | ur |
| `rsi_state` | sr, rb, p, lh, jd |
| `ha_body` | m, jm, fg, cf |
| `reversal_shadow` | i, sh, p |
| `hourly_slope` | bu, ao, cj, ma |
| `oi`（仅 combo） | sr, ma |

并集：`ao_accel, calendar_cyclical, ha_body, hourly_slope, reversal_shadow, rsi_state` + combo 中的 `oi`。与计划 Global Constraints 给定集合一致。

**不在活 SCHEMES、但在 features/池里的**（本表不当 SCHEMES 合同）：`crack_spread_*`、`nvi`、`qstick`、`vwap_deviation`、`stddev`、`basis_momentum`、`reversal_shadow_gated_*`、`vor` 等。有独立 spec 的按「池内仍有效 / 固化失效」拆条（10、16、7）。

---

## 6. 明确不作废的状态栏

以下 **没有** 因状态栏把整份判失效：

- compile-skip「待审阅」→ 仍有效
- 09-02「待审阅」→ 部分有效（失效条来自方案 A，不是状态栏）
- Phase 4 / Phase 8「待用户审核」→ 仍有效 / 部分有效
- Phase 5+6「Draft 待用户审批」→ 部分有效
- A2-P1「Draft 待用户 review」→ 部分有效
- dense-cache / market-vectorize / runtime / Phase 15 / peer-eval-fix「待审核」或「待执行」→ 失效条来自 0/N GO 或方案 A，**不是**状态栏

---

## 7. SPEC-001…003

仓内无独立 spec 文件。不在上表 20 行里发明一行「仍有效 spec」。Task 2 用 git `cd29bb6` + `get_safe_daily` / 前视相关代码对齐。

---

## 8. 给 Task 2–7 的有效性闸门

| Task | 消费本表 |
|------|----------|
| 2 Hardening | spec 1 = **仍有效**，按条款对齐，禁止把 Non-Goals 当缺口。 |
| 3 Compile-skip | spec 2 = **仍有效**。 |
| 4 三环 | spec 17 **仍有效**；spec 3 只对齐「仍有效」条，diagnostic 收割标失效不报缺口。 |
| 5 控制面 | spec 5 **仍有效**；spec 4 拆条：2.5GiB/slots=1/429 对齐，15GiB 与 peer-eval 硬顶按失效/文档过期，不要改代码去满足 15GiB。 |
| 6 协变量 | spec 9 整份对齐；6/7/8/10/12/16 只对齐仍有效条。Phase 15 固化目标不报「SCHEMES 缺 nvi」缺口。crack 按池对齐。 |
| 7 Alpha2 | spec 11 拆条；13–15 **设计失效** + 残留脚本清单。评价秤若被慢环误用再另报，不在失效 spec 下发明生产缺口。 |

不改生产代码，不启动 Praxist，不写 `.txt` 副本。

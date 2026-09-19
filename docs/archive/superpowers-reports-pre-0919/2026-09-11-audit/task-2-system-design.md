# Task 2：`docs/system_design.md` 合理性与漏洞

- **任务**: 全系统审核计划 Task 2（只审文档，不改生产代码）
- **文档**: `docs/system_design.md`（821 行，版本栏 1.0 / 2026-09-10；git `a1b298f` 2026-09-10 14:58 +0800「docs: update for Critical Fixes v1.4」）
- **对照**: `docs/product_positioning.md`、`loop-constraints.md`、`docs/praxist.md`、`cascade/`、`config/prediction_scheme.py`、`scripts/copilot.py`、`scripts/cascade_predict.py`、`scripts/aligned_slow_loop.py`、`task_FM/evaluations/fm_eval/evaluator.py`
- **Task 1**: `docs/superpowers/reports/2026-09-11-audit/` 在本报告落盘时仍空，无矛盾矩阵可消费。下列对账按计划「探索期嫌疑」独立取证。
- **前视**: 本文**不**判定代码是否仍穿越。只记录：系统设计写了「防穿越」，但没点名 `get_safe_daily`。穿越本身归 Task 5。

## Summary

`docs/system_design.md` 把级联、context/horizon、Vol 默认 OFF、2 星名单和 `backtest_config.py` 数值写对了一大半，但把**可交易方向**画成日线斜率、把 **IC** 写成 Pearson 相关。按这份文档去改生产，会把 `cascade_predict` / 回测仓位从 `sign(weighted_1H − base)` 改回日线阈值，并把硬门 IC 从 `2×|dir_acc−0.5|` 换成相关。这两条是 Critical。其余是过时伪代码、SS 协变量双口径、以及 `gate_pass` 是否含 EV 的旗标分叉。

主建议：把 §5 / §8 / §3.3 的方向合同改成引用 `cascade/signal_contract.position_from_forecast`（CF-01 A）；把 §7.1 IC 改成 `loop-constraints.md` 公式；附录补上 `signal_contract.py`。不要按 §5.1 的 `_compute_direction` 去「统一」级联入口。

## 逐节判定表（§1–§10）

| 节 | 判定 | 一句话 |
|----|------|--------|
| §1 系统概览 | **内部自相矛盾 / 与代码不符** | 「领航员」对，但标题和架构图把日线斜率、Vol 熔断画进决策主链；「开平仓建议」与产品红线打架。 |
| §2 数据管线 | **合理（有缺口）** | 表名、`ensure_fresh_data`、星期滞后表与代码大致同构；未点名 `get_safe_daily`，1H 表未写节假日扣除。 |
| §3 两阶段级联 | **与代码不符 / 内部自相矛盾** | 250/22、480/24 对；`horizon_slope` 单位自相矛盾；10 列写成 P10~P90；§3.3「日线定大方向」违反 CF-01 A。 |
| §4 协变量 | **内部自相矛盾 / 过时** | §4.2/§10.1 的 SS=`calendar_cyclical` 等于 `SCHEMES`；§4.3 过门表写成 `vor`。示例函数名/形状已过时。 |
| §5 信号与方向 | **与代码不符（Critical）** | 可交易方向被写成日线斜率；幽灵函数 `_compute_direction`；`confidence_band` 算法已换。 |
| §6 Vol 熔断 | **合理（图示过满）** | 默认 OFF、v2 覆盖、`ThrPolicy` 优先级大体对；字段表与 dataclass 不一致；架构图读起来像生产路径。 |
| §7 评估与门禁 | **与代码不符（Critical）** | IC 写成 `corr`；`gate_pass` 伪代码含 EV，生产旗标只判 n+ic。PF/EV/MaxDD 公式大体对。 |
| §8 交易建议 | **与代码不符 / 诱导误解** | 报告模板用日线斜率当【方向判断】；`craft_advisory` 伪代码不是现行函数。 |
| §9 流程示例 | **过时** | 激活路径写成 `D:/FlyBuddy/FM_a`；SS 协变量仍是 calendar；方向示例跟日线走。 |
| §10 附录 | **合理（缺合同文件）** | 数值与 2 星表对；未列 `cascade/signal_contract.py`。 |

## Findings

### C1 — Critical — 按 §5.1/§3.3/§8 执行会改错生产可交易方向

- **文档原文**
  - `docs/system_design.md:4`：「在任意时间点给出期货品种的**开平仓建议**」
  - `docs/system_design.md:313-332`：`def _compute_direction(horizon_slope, scheme)`，「基于**日线斜率**判断方向」；`horizon_slope * 100 > thr` → 「看多 ↑」；「低于阈值视为震荡/中性，**不建议开仓**」
  - `docs/system_design.md:197-207`：§3.3「Stage 1 (日线) … **确定大方向**」；「1H 模型以日线斜率为条件，避免与大势矛盾」
  - `docs/system_design.md:577-580`：报告模板「【方向判断】看多 ↑ / 日线斜率: +0.15%/天」
- **更高权威**
  - `docs/product_positioning.md:11-16`：可交易方向 = `sign(weighted_1H − base)` via `signal_weight` / short_horizon；日线状态仅副标签。实现：`cascade/signal_contract.position_from_forecast`。
- **代码事实**
  - 仓内**没有** `_compute_direction`。日线摘要走 `cascade/daily_model.py:189-213` 的 `_compute_direction_v2`（R²<0.35 强制中性，阈值是 `trend_threshold_pct/100` 比分数斜率）。
  - 回测与级联主入口走加权 1H：`cascade/signal_contract.py:32-89` `position_from_forecast`；`scripts/cascade_predict.py:208-230` 注释写明「可交易方向=加权1H」；`scripts/monthly_backtest.py:50,329` 同样调用。
  - 锁合同的测试：`tests/test_signal_contract.py:67-77` — 日线 0.0005 分数/天 → regime 中性，仓位仍是 1H 看多。
  - **分叉**：`scripts/copilot.py:384,433-446` 把 `direction = _compute_direction_v2(daily_result, scheme)` 当作卡面主方向和 `craft_advisory` 入参，**没有** import `position_from_forecast`。文档与 copilot 一致，与 CF-01 A / cascade_predict / 回测不一致。
- **建议**: 改文档，不要改 `position_from_forecast`。§5.1 应改成：主方向 = `position_from_forecast`；日线只出 `regime_direction`。copilot 分叉交给 Task 9，不要按 §5.1 去「统一」级联。
- **若按文档落地的后果**: `cascade_predict` / `monthly_backtest` 的 `direction`/`position_sign` 会从加权 1H 换成带 0.1%/天阈值的日线斜率，中小 1H 位移会被拍成中性，日线与 1H 反向时仓位会跟日线走。

### C2 — Critical — §7.1 把 IC 写成 Pearson，按它改硬门会改错 gate

- **文档原文**: `docs/system_design.md:485`：`**IC** | corr(预测, 实际) | 信息系数 | ≥ 0.05`
- **更高权威**: `loop-constraints.md` 预注册段：`IC≥0.05（ic=2×|dir_acc−0.5|）`。`docs/praxist.md` 慢环硬门同式。
- **代码事实**
  - `cascade/evaluation_metrics.py` **没有** `corr` / Pearson。只有 DirAcc。
  - `task_FM/evaluations/fm_eval/evaluator.py:199-202`：`ic = 2 * abs(m.get("dir_acc", 0.5) - 0.5)`；`gate` = `n>=350 and ic>=0.05`。
  - `scripts/aligned_slow_loop.py:101`：写入 verdict 的 `ic` 同式。
  - 磁盘：`ss_vor` dir_acc=0.53 → ic=0.06（`task_FM/config/aligned_verdicts.jsonl` 第 16 行）；`m_vor` dir_acc=0.524 → ic=0.048，`gate_pass=false`（第 4 行）。这是方向性 IC，不是预测值与实现值的相关。
- **建议**: §7.1 公式改成 `ic=2×|dir_acc−0.5|`，并指向 `evaluator.gate` / `aligned_slow_loop`。删掉 `corr(预测, 实际)`。
- **若按文档落地的后果**: 硬门 IC 换成 Pearson 后，过门集合会变（`m_vor` / `ss_vor` / `i_oi` 都可能翻转），慢环 `gate_pass` 不再与 `loop-constraints.md` 同构。

---

### I1 — Important — 幽灵 `_compute_direction`；活函数是 `_compute_direction_v2`（含 R² 门）

- **文档**: `docs/system_design.md:313` `def _compute_direction(...)`；无 R²。
- **代码**: 全仓无 `_compute_direction`。`cascade/daily_model.py:189-213` `_compute_direction_v2`：`slope_unreliable`（R²<0.35）→「中性 → (形态分歧)」；阈值 `thr_ratio = scheme.trend_threshold_pct / 100.0`。`DailyResult` 另有 `r_squared`、`slope_unreliable`（`daily_model.py:27-28`），文档 dataclass 没写。
- **建议**: 删幽灵函数。日线副标签写 `_compute_direction_v2` / `trend_direction`。不要把 v2 的 R² 门接到可交易仓位上。

### I2 — Important — `horizon_slope` 单位在文档内部打架

- **文档**: `docs/system_design.md:131,140` 写 `horizon_slope = 回归系数 / 预测均值 (%/天)`，字段已是百分比；同文件 `326-328` 又 `horizon_slope * 100 > thr`，「转换为百分比」。
- **代码**: `cascade/daily_model.py:148-151`：`horizon_slope = reg_slope / forecast.mean()`，是**分数/天**。摘要 `180` 行才 `* 100` 打成 `%/天`。`position_from_forecast`（`signal_contract.py:85`）同样 `daily_slope * 100.0` 再交给 `trend_direction`。`trend_direction`（`prediction_scheme.py:562-577`）假定入参已经是 `%/天`，不再乘 100。
- **建议**: 合同写成：存储值 = 分数/天；展示 = `×100` 得 `%/天`；`trend_threshold_pct=0.1` 表示 0.1%/天。示例代码不要既宣称已是百分比又 `*100`。
- **风险**: 若执行者按 §3.1 把字段当 0.15（%/天）再抄 §5.1 `*100`，阈值比较变成 15>0.1，几乎永远出方向。

### I3 — Important — SS 主协变量双口径：`SCHEMES`/`§4.2`/`§10.1` = `calendar_cyclical`，`§4.3` 过门 = `vor`

- **文档**: `docs/system_design.md:232-236,271,765,687`：生产示例 SS=`calendar_cyclical`；§4.3 表「当前过门」SS=`vor` PF=1.123 EV=+11.06 IC=0.060。
- **代码 / 磁盘**
  - `config/prediction_scheme.py:117-133`：`ss` `covariate_type="calendar_cyclical"`，`stars=2`（G005-E 升回 2 星的依据是另一套口径）。
  - `task_FM/config/aligned_verdicts.jsonl:16`：`ss_vor` n=396 PF=1.123 ev=11.06 ic=0.06 `gate_pass=true`。
  - `docs/praxist.md` 现场快照：经济意义上过门实质只有 `ss_vor`。
- **建议**: 拆两行：**(a) 生产 SCHEMES** SS=`calendar_cyclical`（未自动换成 vor；固化须人工）；**(b) 慢环过门** `ss_vor`。禁止把 §4.3 读成「该改 SCHEMES」。
- **若误改 SCHEMES**: 会改 SS 生产 XReg 输入，属高风险路径（`loop-constraints.md` 禁止自动改 `prediction_scheme.py`）。

### I4 — Important — `gate_pass` 伪代码含 EV>0，生产旗标只判 n+ic

- **文档**: `docs/system_design.md:537-547`：`return (n >= 350) and (ic >= 0.05) and (ev > 0)`。§4.3 流程同样写「n≥350 + IC≥0.05 + EV>0」。
- **权威分裂**: `loop-constraints.md` / `config/praxist_task.yaml:20` 全量 walk-forward 的 gate 列表含 `ev>0`；`docs/praxist.md` 第 4 节明确：`i_oi` `gate_pass=True` 但 ev=−2.46，「硬门只判 n+ic」。
- **代码**: `evaluator.py:199-202` `gate()` **不含 EV**。磁盘 `aligned_verdicts.jsonl:19` `i_oi`：n=396 dir_acc=0.467 ic=0.066 ev=−2.46 **`gate_pass: true`**。按文档函数，该行应为 false。
- **建议**: 文档把「预注册最终裁决（含 EV、PF/incumbent）」和「`gate_pass` 布尔（现行 n+ic）」拆开写。不要在未开 plan 的情况下按 §7.3 去改 `evaluator.gate`——那会改写全部 verdict 旗标。细节归 Task 7。

### I5 — Important — 10 列分位数写成 P10~P90，与 TimesFM 列合同不对齐

- **文档**: `docs/system_design.md:143,192`：`shape (22, 10), P10~P90` / `(24, 10), P10~P90`。§5.3 用 `[:, 5:6]` 当 P50、`[1..4]` P10~P40、`[6..9]` P60~P90，等于承认 Col0 不是 P10，但 §3 标题仍写 P10~P90。
- **代码**: `config/prediction_scheme.py:586-591`：Col 0 = Point Forecast (Mean)；Col 5 = P50；Col 1–4 = P10–P40；Col 6–9 = P60–P90。`daily_model.py:183-184`、`copilot.py:429-431` 用 `[:,1]`/`[:,9]` 当 P10/P90。`apply_neutral_override_v2`（`vol_risk_filter.py:148-160`）10 列 z 与文档 §6.4 表一致。
- **建议**: 所有 `shape (H, 10)` 旁写清 10 列合同。不要把 Col0 当 P10。P10~P90 是 9 个分位 + 1 个 mean。

### I6 — Important — `confidence_band` 伪代码是线性展宽，代码是对数空间 + Col0 隔离 + 排序

- **文档**: `docs/system_design.md:374-396`：`median - (median - q) * mult`，循环 Col 1–4 / 6–9。
- **代码**: `config/prediction_scheme.py:582-619`：`np.log` → 对 Col1–9 乘乘数 → `np.sort` → **恢复 Col5 P50** → `np.exp`；Col0 原样通过。`scripts/cascade_predict.py:302` 生产报告会调用它。
- **建议**: 用现行函数替换 §5.3。线性版会改 CI，从而改报告里的 P10/P90 止损参考（`copilot.py` 当前用的是原始分位，未走 `confidence_band`）。

### I7 — Important — 「防穿越」是原则句，未引用 `get_safe_daily`；Stage 1 预测读的是 `get_main_continuous`

- **文档**: `docs/system_design.md:60,809`：「所有预测严格使用历史数据，不使用未来信息」；全文 **零次** `get_safe_daily`。
- **代码**: `data/data_store.py:158-199` `get_safe_daily`：剔除未收盘/未来日线。`scripts/cascade_predict.py:106-107` 只用来生成**报告**用的 `daily_df`。`cascade/daily_model.py:104` Stage 1 预测：`store.get_main_continuous(limit=context_days)`。`copilot.py` 不调用 `get_safe_daily`。
- **建议**: 在 §1.2 / §2 写清：哪条路径用 `get_safe_daily`，哪条仍 `get_main_continuous`。是否仍穿越由 Task 5 取证，本文不宣称「代码仍穿越」。

### I8 — Important — 「开平仓建议 / 中等仓位开仓」会让人把领航员读成自动交易

- **文档**: `docs/system_design.md:4` 开平仓建议；`657-661` 「强建议 … **中等仓位开仓**」；「不建议 … 空仓等待」。
- **权威**: `docs/product_positioning.md:7-9`：不是自动下单系统。`docs/system_design.md:25-27,57` 自己也写「不是自动交易系统 / 领航员而非自动驾驶」。
- **建议**: 标题和 §8.3 改成「结构辅助 / 方向+信用+风险标签」。动作表不要写「开仓」。

### I9 — Important — §9.2 激活路径指向错误仓库和错误 venv

- **文档**: `docs/system_design.md:738-739`：`source D:/FlyBuddy/shared/timesfm/.venv/Scripts/activate` + `cd D:/FlyBuddy/FM_a`。
- **事实**: 活仓是 WSL `/home/abug/timesfm`，预测/Praxist 用 `.praxist-venv`（`docs/praxist.md`、`AGENTS.md`）。`D:\FlyBuddy\timesfm` 被明确标为可能过期副本；`D:/FlyBuddy/FM_a` 不是本仓路径。
- **建议**: 换成 `cd /home/abug/timesfm` + `source .praxist-venv/bin/activate`。按 §9.2 跑会进错环境。

### I10 — Important — §4.4 示例函数名、形状、RSI 语义都已过时

- **文档**
  - `docs/system_design.md:279-292`：`def build_calendar_cyclical` → 一维 `sin(2π·month/12)`。
  - `docs/system_design.md:295-305`：`_calc_rsi` 返回 `(rsi-50)/50`，范围 [-1,1]。
- **代码**
  - 无 `build_calendar_cyclical`。`cascade/features.py:2097-2160` `calc_calendar_cyclical`：返回 **4 维** `[sin/cos DOY, sin/cos Month]`，shape `(context+horizon, 4)`，horizon 按交易时段外推。
  - `_calc_rsi`（`features.py:165-199`）返回 **0–100**。生产协变量是 `calc_rsi_state`（`features.py:391-420`）：离散 {-2,-1,0,+1,+2}，不是归一化 RSI。
- **建议**: 示例改成 `calc_calendar_cyclical` / `calc_rsi_state`。按文档实现会得到错误 XReg 维数和错误 RSI 编码。

### I11 — Important — 方向合同文件 `signal_contract.py` 未进入 §10.3

- **文档**: `docs/system_design.md:787-799` 文件表有 daily/hourly/features/vol/cascade_predict/copilot，**没有** `cascade/signal_contract.py`。全文不出现 `position_from_forecast`。
- **代码**: `signal_contract.py:1-16` 自称 live/backtest 单一真相源。
- **建议**: 附录补该文件，并在 §5 把它标成方向合同。

---

### M1 — Minor — 衰减曲线数字对不上公式

- **文档**: `docs/system_design.md:347,363-369`：trend `decay=1.35`，T+1=0.97 … T+24=0.64。
- **代码**: `prediction_scheme.py:524-533`：`w = decay ** (-t / horizon)`。decay=1.35、H=24 时 T+1≈0.988、T+24≈0.741。文档数字更接近 **decay=1.60**（stable 默认）。SS 实际 `decay=1.30`（`prediction_scheme.py:127`）。
- **建议**: 用公式重算，或标明「示意、非 SS 生产 decay」。

### M2 — Minor — dataclass 缺字段

- **文档** `DailyResult`（`system_design.md:135-144`）无 `r_squared` / `slope_unreliable`。`HourlyResult`（`186-194`）无 `context_len` / `horizon` / `baseline_*`。
- **代码**: `daily_model.py:20-28`、`hourly_model.py:22-35`。
- **建议**: 与源码对齐，避免复制粘贴漏字段。

### M3 — Minor — `ThrPolicy` 字段表不是现行 dataclass

- **文档**: `system_design.md:441-447` 把 `calibrated_thr` 画成字段（截断稿还出现 `rated_thr`）。
- **代码**: `vol_risk_filter.py:204-226` 字段是 `global_cli, sector_cli, operational_map, default, allow_calibrated, allow_operational`。`calibrated_thr` / `operational_thr` 是 `resolve()` 的 kwargs。优先级 6 档与注释一致。
- **建议**: 按源码重画字段；保留优先级列表。

### M4 — Minor — `craft_advisory` 伪代码不是现行实现

- **文档**: `system_design.md:614-651` 有「方向看多，建议逢低做多」等句。
- **代码**: `scripts/copilot.py:247-318` 现行 `craft_advisory` 用 `vol_sensitivity`（HELPS/HURTS/MIXED）和「时效策略 / 副驾建议」；另有 `craft_advisory_v2`（`322-342`，文档未提）处理 degraded/revoked。
- **建议**: 伪代码改成「见 copilot.py:247」，或同步 v2 状态机。盘中文案对账归 Task 9。

### M5 — Minor — §2.2 星期滞后表未写节假日扣除

- **文档**: `system_design.md:91-97` 周一 1H=3 天 / 日线=5 天等。
- **代码**: 日线阈值 `daily_model.py:121-129` 与表一致。1H `data_validator.py:103-118` 星期放宽一致，但还会 `count_holidays_between` 扣法定假日。
- **建议**: 加一句「1H 再扣 `data/holidays.py`」。

### M6 — Minor — `VarietyScheme.stars` 默认 3，与「无真实 3 星」并列易误导

- **文档**: §7.4 正确写无 3 星、2 星 8 个。
- **代码**: `prediction_scheme.py:81` `stars: int = 3`；每个 SCHEMES 项都显式覆盖。`list_by_stars(2)` 注释列出 CJ/SS/SR/M/JD/LH/EG/RB，与 §7.4 / §10.1 一致（8 个 2 星、13 个 1 星）。`--three-star` 映射 ≥2 星（`copilot.py:14,728,744-745`）。
- **建议**: 默认值改文档说明「dataclass 默认 3 已被逐项覆盖，CLI 历史名 ≠ 3 星」。

### M7 — Minor — Vol 默认 OFF 正文对，架构图仍画在决策主链

- **文档**: `system_design.md:58,402-410,701` 明确默认 OFF；`35-42` 架构图把「风控熔断 (Vol Gating)」画在数据→输出的必经决策层；§8.3「不建议」含「Vol 熔断」。
- **代码**: `cascade_predict.py:56-63,136-141` 默认 OFF；启用靠 `--vol-filter-neutral` / `FM_VOL_FILTER=1`。`vol_risk_filter.py:354` `FM_VOL_FILTER=="1"`。copilot `evaluate_vol_radar`（`copilot.py:139-177`）只打标签，注释「永不压平」。v2 覆盖函数存在且 cascade_predict 在熔断开启时调用（`cascade_predict.py:176`）。
- **建议**: 图上标注「可选 / 默认 OFF」。正文已正确，不必改代码。

### M8 — Minor — `signal_weight` 短段还有 `smooth_cutoff` cosine，文档只写硬切 12 根

- **文档**: `system_design.md:357-361` T+1–12 权重 1、其后 0。
- **代码**: `prediction_scheme.py:534-554`：`smooth_cutoff` 时 plateau=8 / cutoff=16 cosine（SPEC-007）；默认 `smooth_cutoff=False`，硬切 `half=min(horizon//2, 12)`，horizon=24 时与文档相同。
- **建议**: 加一句「默认硬切；`smooth_cutoff` 走 cosine，生产 SCHEMES 现为 False」。

## 符号核对表（计划 Step 1）

| 文档符号 | 仓内 | 签名/语义是否一致 |
|----------|------|-------------------|
| `DailyResult` | `cascade/daily_model.py:20` | 有；文档缺 `r_squared`/`slope_unreliable` |
| `HourlyResult` | `cascade/hourly_model.py:22` | 有；文档缺 `context_len`/`horizon`/`baseline_*` |
| `_compute_direction` | **不存在** | 活函数 `_compute_direction_v2`（`daily_model.py:189`） |
| `signal_weight` | `config/prediction_scheme.py:524` | 有；短段另有 cosine 分支 |
| `confidence_band` | `config/prediction_scheme.py:582` | 有；算法已换成 log-space |
| `ThrPolicy` | `cascade/vol_risk_filter.py:204` | 有；字段不是文档那张表 |
| `apply_neutral_override` | `vol_risk_filter.py:95` | 有 |
| `apply_neutral_override_v2` | `vol_risk_filter.py:115` | 有；z 表与 §6.4 一致 |
| `gate_pass` | **无此函数名** | 活函数 `evaluator.gate`（n+ic，不含 EV） |
| `craft_advisory` | `scripts/copilot.py:247` | 有；另有未入文档的 `craft_advisory_v2:322` |
| `position_from_forecast` | `cascade/signal_contract.py:32` | **文档未出现**（生产方向合同） |
| `trend_direction` | `prediction_scheme.py:562` | 文档未出现；regime 副标签 |
| `ensure_fresh_data` | `cascade/data_validator.py:395` | 有；copilot/cascade_predict 会调 |
| `get_safe_daily` | `data/data_store.py:158` | **文档未出现** |
| `build_calendar_cyclical` | **不存在** | 活函数 `calc_calendar_cyclical` |
| `_calc_rsi` | `cascade/features.py:165` | 有；返回 0–100，不是文档的 [-1,1] |

## 关键数值核对（计划 Step 2）

| 项 | 文档 | 代码 | 判定 |
|----|------|------|------|
| context 1H / 日线 | 480 / 250 | `backtest_config.py:65-66`；`VarietyScheme` 默认同 | 一致 |
| horizon 1H / 日线 | 24 / 22 | `backtest_config.py:67-68` | 一致 |
| `STEP` / `EVAL_WINDOW_BARS` | 2 / 1200 | `backtest_config.py:69-70` | 一致 |
| `SLIPPAGE_TICKS` | 2 | `backtest_config.py:118` | 一致 |
| `trend_threshold_pct` | 0.1 | `prediction_scheme.py:107` 默认 0.1 | 一致（单位见 I2） |
| decay 示例 | trend 1.35 / stable 1.60 | `DEFAULT_DECAY_FACTORS` 同；**生产用 scheme.decay**（SS=1.30） | 默认一致，示例曲线数字错（M1） |
| 2 星集合 | SS SR M RB EG LH CJ JD | `list_by_stars` 注释同一批；SCHEMES `stars=2` 即这 8 个 | 一致 |
| SS 协变量 | 正文示例 calendar；§4.3 vor | SCHEMES=calendar_cyclical；verdict `ss_vor` 过门 | **双口径（I3）** |
| Vol 默认 | OFF | `is_vol_filter_enabled` 默认 False；`FM_VOL_FILTER` 默认 `"0"` | 一致 |
| v2 neutral | 2026-09-10 生产已切 v2 | `cascade_predict.py:176` `apply_neutral_override_v2` | 一致 |
| 无真实 3 星 | 是 | `list_by_stars` 文档字符串；`--three-star`→≥2 | 一致 |
| 1H 时效星期表 | 3/4/3/1/2~3 | `data_validator.py:103-114` | 大体一致（假日见 M5） |
| 日线时效星期表 | 5/6/5/3/4 | `daily_model.py:121-129` | 一致 |

## Root Cause

`system_design.md` 是 2026-09-10 为「从预测到交易建议」新写的总览（git `fcf9a4e` → `a1b298f`），叙事中心仍是「日线定方向、1H 定时机、再给开平仓建议」。更高权威在 8 月已经把产品法改成 CF-01 A（加权 1H），9 月把 IC 钉成 `2×|dir_acc−0.5|`，并把 `position_from_forecast` 做成单一入口。总览更新了 Vol v2、STEP=2、2 星名单，**没有改方向合同和 IC 公式**，也没有把 `signal_contract.py` 收进附录。于是一份「看起来是现行设计」的文档，在两个会改生产信号/硬门的点上仍停在旧叙事。

次因：生产路径已经分叉——`cascade_predict` / 回测守 CF-01 A，`copilot.py` 仍用日线 `_compute_direction_v2`。文档与 copilot 同侧，会给执行者「以文档为准去改级联」的错误信心。

## Recommendations

1. **改 §5 / §3.3 / §8 方向合同** — 低工作量、高影响。主方向只引用 `position_from_forecast`；日线改称「日线状态」。不要用文档去改 `signal_contract.py`。
2. **改 §7.1 IC 公式** — 低工作量、高影响。写成 `ic=2×|dir_acc−0.5|`，指向 `evaluator.gate`。
3. **拆 SS 协变量两行、拆 gate 旗标与最终裁决** — 低工作量、中影响。避免有人改 `SCHEMES["ss"]` 或给 `gate()` 加 EV。
4. **补符号与路径**：`signal_contract.py`、`get_safe_daily` 的职责边界、WSL 激活命令、10 列分位合同、`calc_calendar_cyclical` / `calc_rsi_state`。
5. **copilot 方向分叉** — 不要在本任务改代码。交给 Task 9；修复前文档应写明「盘中 copilot 主句仍是日线，与 CF-01 A 不一致」。

## Trade-offs

| 选项 | 好处 | 代价 |
|------|------|------|
| A. 只改 `system_design.md` 对齐 CF-01 A 与 IC 合同 | 阻止执行者改错级联/硬门；工作量小；不动高风险路径 | copilot 仍按日线说话，文档会暂时暴露产品分叉 |
| B. 先改 copilot 再改文档，让三条路径都走 `position_from_forecast` | 文档与盘中一致 | 改的是盘中主句，属 Task 9；未测前可能让人觉得「建议突然反了」 |
| C. 维持日线定方向的叙事，把 CF-01 A 降为回测细节 | 少改文档 | 直接违反 `product_positioning.md`；下一次有人按总览改 `cascade_predict` 就会改错仓位 |
| D. 按 §7.3 给 `gate()` 加上 EV>0 | 与 yaml/loop-constraints 的「最终裁决」字面一致，`i_oi` 不再假过门 | 改写已落盘 `gate_pass`；materializer/peer 视图全变；须另开 plan，不是本文档修补 |

倾向 A，B 另开 Task 9，D 另开 Task 7。不要选 C。

## 合理性专项（计划 Step 3）

| 问题 | 结论 |
|------|------|
| 把领航员画成开平仓建议？ | 会。标题 L4、§8.3「开仓」与产品「不是自动下单」冲突（I8）。 |
| 方向若与 CF-01 A 相反，会不会让人改错信号？ | 会。§5.1 是日线主方向；级联/回测是加权 1H（C1）。 |
| `horizon_slope * 100` 单位错了吗？ | 文档内部自相矛盾。对**存储的分数斜率**乘 100 是对的；若按 §3.1 当成已是 %/天再乘，就错（I2）。 |
| 10 列分位假设对齐 TimesFM 了吗？ | 没有。Col0=mean，不是 P10（I5）。 |
| 「防穿越」vs 已确认的日内日线穿越？ | 文档只给原则，不引用 `get_safe_daily`。是否仍穿越归 Task 5（I7）。 |

## References

- `docs/system_design.md:4,35-42,57-60,131-150,197-207,232-236,271,279-332,363-396,402-410,441-447,485,537-547,577-584,614-661,738-739,765,787-799` — 文档合同原文
- `docs/product_positioning.md:7-16` — CF-01 A
- `loop-constraints.md` — IC 公式；禁止自动改 SCHEMES/daily/hourly/features
- `docs/praxist.md` — `ss_vor` 过门；`i_oi` 假过门
- `cascade/signal_contract.py:1-16,32-89` — 可交易方向实现
- `cascade/daily_model.py:20-28,104,148-151,180,189-213` — DailyResult、分数斜率、v2 方向
- `cascade/hourly_model.py:22-35` — HourlyResult
- `cascade/features.py:165-199,391-420,2097-2160` — RSI / calendar
- `cascade/vol_risk_filter.py:95-160,204-226,354` — override / ThrPolicy / env
- `cascade/data_validator.py:103-118,395` — 1H 时效、`ensure_fresh_data`
- `config/prediction_scheme.py:81,107,117-133,524-619` — SCHEMES SS、权重、CI
- `config/backtest_config.py:65-70,118` — context/horizon/STEP/滑点
- `config/praxist_task.yaml:4-20` — 预注册 gate 列表含 ev>0
- `scripts/cascade_predict.py:56-63,106-107,176,208-230,302` — Vol OFF、safe daily 仅报告、v2、加权方向
- `scripts/copilot.py:14,139-177,247-342,384,423-446` — 雷达-only、advisory、日线主方向
- `scripts/aligned_slow_loop.py:101` — ic 写入
- `task_FM/evaluations/fm_eval/evaluator.py:163,199-202` — gate 实现
- `task_FM/config/aligned_verdicts.jsonl:4,16,19` — m_vor / ss_vor / i_oi
- `data/data_store.py:158-199` — `get_safe_daily`
- `tests/test_signal_contract.py:67-77` — CF-01 A 锁

## Finding counts

| 级别 | 条数 | ID |
|------|------|-----|
| Critical | 2 | C1 方向, C2 IC |
| Important | 11 | I1–I11 |
| Minor | 8 | M1–M8 |
| **合计** | **21** | |

不把「文档过期」写成「代码仍穿越」。不建议在本任务改 `SCHEMES`、`daily_model.py`、`hourly_model.py`、`features.py` 或 `evaluator.gate`。

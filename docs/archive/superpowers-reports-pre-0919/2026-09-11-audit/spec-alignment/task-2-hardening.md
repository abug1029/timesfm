# Task 2：System Hardening SPEC-004…013 条款对齐

> **仓**: WSL `/home/abug/timesfm`（master，合并提交 `243693d` 仍有效）  
> **合同**: `docs/superpowers/specs/2026-09-10-system-hardening-design.md` v1.2-final  
> **接口判定**: 仍有效（计划 Task 1 预置；本任务不因计划复选框未勾而判未实现）  
> **方法**: 只读对照活代码 + `tests/test_system_hardening.py`；不改生产代码  
> **日期**: 2026-09-11

## 计数

| 判定 | 条款数 |
|------|--------|
| 对齐 | 41 |
| 部分对齐 | 9 |
| 缺口 | 10 |
| 失效 | 0 |

**合计有效条款 60。** 10 份 SPEC 均仍有效，无设计失效条款。

按 SPEC 汇总：

| SPEC | 对齐 | 部分 | 缺口 | 总评 |
|------|------|------|------|------|
| 004 有效样本量 | 7 | 1 | 1 | 部分对齐 |
| 005 Col 0 隔离展宽 | 7 | 0 | 0 | 对齐 |
| 006 SCHEMES 退役治理 | 5 | 1 | 1 | 部分对齐 |
| 007 余弦滚降 | 4 | 0 | 0 | 对齐 |
| 008 保证金 MaxDD | 3 | 2 | 1 | 部分对齐 |
| 009 半衰期品种级 | 2 | 2 | 1 | 部分对齐 |
| 010 交易时段嗅探 | 3 | 1 | 0 | 对齐 |
| 011 换月后复权 | 4 | 0 | 4 | 缺口 |
| 012 对数斜率 + R² | 2 | 2 | 2 | 部分对齐 |
| 013 漂移截断 | 2 | 0 | 0 | 对齐 |

---

## 必须核对（计划点名）

| 点 | 结论 | 证据 |
|----|------|------|
| SPEC-004 `n_eff` 不进 gate | **对齐** | `gate()` 只用名义 `n` 与 IC；`n_eff` 在 `build_summary` 之后写入 JSONL |
| SPEC-005 Col 0 隔离 | **对齐** | 10 列与非 10 列都只动 Col 1 以后；测试锁死 Col 0 |
| SPEC-008 保证金 MaxDD 输入净 vs 毛 | **缺口**（上一轮 I-17） | 函数形参叫 `net_pnl_pts`，慢环喂的是 `p["pnl"]` = `position_sign * delta_real`，未扣滑点 |
| SPEC-007 cosine 默认关 | **对齐** | `smooth_cutoff: bool = False`；生产 `SCHEMES` 无 `True` |
| SPEC-011 日线 `raw_close` 短路 | **缺口** | `get_main_continuous` 见列就跳过复权；表结构恒有该列 |
| SPEC-012 `_compute_direction_v2` 只做副标签 | **部分对齐** | `cascade_predict` 可交易方向走 `position_from_forecast`；`copilot` 把 v2 当作卡片方向 |
| SPEC-006 不改 `SCHEMES` | **对齐** | SPEC-006 两提交未改 `prediction_scheme.py`；退役只写 KB / copilot 文案 |

---

## SPEC-004：重叠窗口有效样本量

**文件**: `task_FM/evaluations/fm_eval/evaluator.py`，`scripts/aligned_slow_loop.py`  
**测试**: `tests/test_system_hardening.py::TestSPEC004EffectiveSampleSize`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| Bartlett 全阶核：`K=⌊(H-1)/S⌋`，`VIF=1+2Σ(1-k/(K+1))ρ^k` | `evaluator.py:206-234` `effective_sample_size` | `test_default_rho09_returns_71` | 对齐 |
| 默认 `ρ=0.9` | `evaluator.py:222-223` | 同上（不传 rho） | 对齐 |
| `step >= horizon` 返回名义 n | `evaluator.py:219-220` | `test_no_overlap_returns_nominal` | 对齐 |
| 589 / H=24 / S=2 → `n_eff=71` | `evaluator.py:233-234` 用 `int()` 截断；手算 VIF≈8.236、n≈71.51 | `== 71` | 对齐 |
| JSONL 增 `n_eff`、`n_eff_method=bartlett_full_kernel_rho0.9` | `aligned_slow_loop.py:104-106`（`build_summary` 之后附加） | 无专门 JSONL 断言；集成点在慢环 | 对齐 |
| **不进硬门**：gate 仍用名义 n≥350、IC≥0.05 | `evaluator.py:199-203` `gate()` 只用 `m["n"]` 与 `ic`；`163` 先算 `gate_pass`，慢环再写 `n_eff` | 无「gate 忽略 n_eff」测试，源码可证 | 对齐 |
| 硬门阈值不变（Non-Goals / Invariants） | `gate(..., min_n=350, min_ic=0.05)` | `tests/test_praxist_fm_evaluator.py` 等既有门测 | 对齐 |
| 报告文案「名义 n=… 有效 n≈71」+ 偏低警告 | 仓内无此格式化字符串 | 无 | 缺口 |
| ρ=0.5 时 n_eff ∈ [120, 200] | 同公式手算 ≈220.87 | `test_rho05_range` 放宽为 `[120, 250]` | 部分对齐 |

**备注（不升缺口）**: 设计稿实现片段写 `int(np.round(n_eff))`（71.51→72），但 v1.2 变更与断言明文是 71。活代码用截断得到 71，与测试和封版数字一致，按 71 口径算对齐。

**缺口严重度**: 报告文案缺失 = Low（JSONL 字段已有，不影响硬门）。

---

## SPEC-005：置信区间对数保序展宽 + Col 0 隔离

**文件**: `config/prediction_scheme.py` `confidence_band`  
**测试**: `TestSPEC005ConfidenceBand`，`TestH3P50Preservation`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `mult==1.0` 原样返回 | `prediction_scheme.py:595-597` | `test_mult_1_passthrough` | 对齐 |
| 对数空间、杜绝负价 | `599-600`，`616` `np.exp` | `test_all_positive` | 对齐 |
| 以 Col 5 P50 为中枢对称展宽 | `601`，`609` | `test_median_unchanged` | 对齐 |
| **Col 0 不参与展宽/排序**（10 列） | `607-611` 只写 `[:, 1:]` | `test_col0_unchanged` | 对齐 |
| Col 1…9 展宽后 `np.sort` 保序 | `609-610` | `test_no_crossing_col1_to_col9` | 对齐 |
| 非 10 列仍隔离 Col 0 | `612-614` 仍只 sort `[:, 1:]`（优于 spec 全排序回退；`207af94`） | `test_nonstandard_cols_col0_preserved` | 对齐 |
| P50 在非对称展宽+排序后仍等于原值 | `608`/`611` 先存再写回（H-3） | `TestH3P50Preservation` 四测 | 对齐 |

生产路径：`scripts/cascade_predict.py:302` 对 1H 分位数调用 `confidence_band`。多数 `SCHEMES` 的 `confidence_multiplier=1.0`，走透传。

---

## SPEC-008：保证金口径 MaxDD（非重叠 stride）

**文件**: `cascade/evaluation_metrics.py`，`scripts/aligned_slow_loop.py`  
**测试**: `TestSPEC008MarginMaxDD`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `stride = max(1, horizon // step)`（H=24,S=2→12） | `evaluation_metrics.py:328-332` | `test_stride_reduces_leverage_inflation` | 对齐 |
| 子序列各自走资金曲线，再平均 MaxDD | `331-355` | 同上 + `test_basic_drawdown_negative` | 对齐 |
| Note 1：`max(1, lots)` + `equity<=0 → -1.0` 前置 | `344-349` | `test_bankruptcy_returns_minus_one` | 对齐 |
| **输入为每笔净盈亏** `net_pnl_pts` | 形参名 `315`；慢环 `aligned_slow_loop.py:109-115` 喂 `p["pnl"]` | 测试自造数组，不验净/毛 | **缺口** |
| 报告同时出名义 MaxDD 与保证金 MaxDD | JSONL 有 `margin_maxdd`（`113-116`）；名义 `maxdd` 来自 `summarize` 净口径。无 spec 文案「MaxDD (保证金口径, 12% margin)」 | 无报告层测试 | 部分对齐 |
| 合约乘数按品种 | `aligned_slow_loop.py:111-112` `getattr(scheme, "contract_multiplier", 10.0)`；`VarietyScheme` **无此字段**，恒 10 | 测试写死 10 | 部分对齐 |

**I-17 细节（净 vs 毛）**

- 点字段：`scripts/monthly_backtest.py:352-353`  
  `pnl = position_sign * delta_real` → **毛**（未减 `tick_size * SLIPPAGE_TICKS`）。
- 名义 MaxDD / PF / EV：`summarize()` → `metrics_from_backtest_points` → `calc_net_metrics`，对活跃仓扣滑点，是 **净**。
- 保证金 MaxDD：慢环把毛 `pnl` 当作 `net_pnl_pts`。与 spec 字面、也与名义 MaxDD 口径不一致。

**缺口严重度**: High（评估数字口径错，但不改 `gate_pass`）。Critical 仅当会改错硬门；此处不进门。

---

## SPEC-007：短段余弦滚降

**文件**: `config/prediction_scheme.py` `signal_weight` / `VarietyScheme`  
**测试**: `TestSPEC007CosineRolloff`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `smooth_cutoff: bool = False`（向后兼容默认关） | `prediction_scheme.py:99` | `test_hard_cutoff_unchanged` | 对齐 |
| 生产 SCHEMES 不打开 cosine | 全仓仅测试里把 `smooth_cutoff=True` | 生产无 `= True` | 对齐 |
| 余弦：Bar1–8=1，9–16 半余弦，17+=0 | `543-553` | plateau / zero_tail / monotone 三测 | 对齐 |
| 默认硬截断前 12 根为 1 | `556-559` `half = min(horizon//2, 12)`；H=24 即前 12 | `test_hard_cutoff_unchanged` | 对齐 |

---

## SPEC-009：协变量半衰期品种级 + 原子化

**文件**: `config/prediction_scheme.py`，`cascade/features.py`，`cascade/hourly_model.py`  
**测试**: `TestSPEC009HalfLifeRefactor`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `VarietyScheme.half_life_bars = 12.0` | `prediction_scheme.py:112` | 无字段存在性测试 | 对齐 |
| 衰减统一走 `_decay_fill` | `features.py:983-989`；combo 路径传 `half_life` | `test_decay_fill_custom_half_life` / `default_unchanged` | 部分对齐 |
| `grep 12.0` 除签名/注释为 0 | 活文件仅 4 处签名默认：`754, 983, 1003, 1421` | `test_no_hardcoded_12_in_features` | 对齐 |
| 从 scheme 读入并传到构建函数 | `cascade_predict.py:113,153,163` 传入；`hourly_model.py:97,179,194` 下传。**`copilot.py:415-424`、`monthly_backtest.py:295-315` 不传**，回落到 12.0 | 无生产接线测试 | 部分对齐 |
| 建议 SS/RB/MA=8、M/SR/JD/EG=12、CJ/LH=16 | `SCHEMES` 中 cj/lh/ma/ss/rb 均未覆盖该字段，全默认 12 | 无 | 缺口 |

**部分对齐细节**: 单协变量路径 `ao_accel` / `bb_squeeze` / `reversal_shadow` / `sar_dist` 调用 `_decay_fill(last_val, horizon)` **不传** `half_life`（`features.py:1271-1326`）。`basis_momentum` 单路径写死 `half_life=24.0`（`1242`）。combo 路径（`1525+`）才用参数。

**缺口严重度**: Low（建议表不是硬合同；机制字段在）。接线遗漏对回测/领航员 = Medium。

---

## SPEC-012：对数斜率 + R² 滤网 + 决策闭环

**文件**: `cascade/daily_model.py`，`scripts/cascade_predict.py`，`scripts/copilot.py`，`cascade/signal_contract.py`  
**测试**: `TestSPEC012R2DecisionClosure`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `DailyResult.r_squared` / `slope_unreliable` | `daily_model.py:28-29, 156-167` | 构造 `DailyResult` 的三测 | 对齐 |
| **对数空间** `polyfit(log(forecast))`，斜率=复合日收益 | `146-150`：对 **价格** 线性回归，再 `/ mean`。R² 也在价格空间 | `test_r_squared_computation` 自算线性 R²，**不调用** `DailyModel.predict` | **缺口** |
| R²<0.35 → `slope_unreliable` | `157` | 无生产路径测试 | 对齐 |
| `_compute_direction_v2`：不可信则「中性 → (形态分歧)」 | `189-207` | `test_low_r2_returns_neutral` 等 | 对齐（函数） |
| 决策闭环接到方向决策 | 报告日线块：`cascade_predict.py:296` 用 v2。JSON `regime_direction`：`220` 来自 `position_from_forecast` → `trend_direction`（**不看 R²**，`signal_contract.py:88-91`） | 只测 v2 本身 | 部分对齐 |
| **只做副标签，不是可交易方向** | `cascade_predict.py:208-242` 可交易=`position_from_forecast`；`product_note` 写明。`copilot.py:434` 卡片 `direction = _compute_direction_v2`，且 **未** 调 `position_from_forecast` | 无 copilot 方向源测试 | 部分对齐 |
| 报告「斜率 %/天 (R²=…)」 | `daily_model.py:179-180` 打印斜率与方向，**无 R²** | 无 | 缺口 |

阈值量纲：v2 用 `trend_threshold_pct/100` 去比 `horizon_slope`（分数）。线性 `/mean` 与对数斜率在小波动下接近，但合同写的是对数回归。

**缺口严重度**: 对数回归 = Medium（标签量纲近似，不是硬门）。copilot 把 v2 当卡片方向 = Medium（产品是辅助、非自动下单；与 `signal_contract`「领航员必须走加权 1H」不一致）。

---

## SPEC-013：Stage 1→2 漂移截断

**文件**: `cascade/features.py`  
**测试**: `TestSPEC013DriftClipping`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `last_close * (1±0.05)^t` 包络截断 | `features.py:22-32` | extreme / normal / symmetric 三测 | 对齐 |
| 在 rsi_state / rsi_slope 使用预测价前调用 | 单路径 `1015-1019`、combo `1441-1445` **入口顶部**就截，覆盖全部协变量（宽于 spec 仅 rsi 分支） | 无接线测试；源码可见 | 对齐 |

---

## SPEC-006：SCHEMES 退役/晋升（不改 SCHEMES）

**文件**: `scripts/build_knowledge_base.py`，`scripts/copilot.py`，`config/knowledge_base.json`  
**测试**: `TestSPEC006SchemeRetirement`  
**提交**: `c1672ff`、`9de3c14` 均未改 `config/prediction_scheme.py`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| KB 字段：`production_covariate`、`slow_loop_status/pf/ev/updated` | `build_knowledge_base.py:166-170`；活 JSON 各品种均有 | `test_build_includes_new_fields` | 对齐 |
| 复合主键 `(symbol, covariate)`，只更新当前生产协变量 | `177-217`；H-2 用 `prod_cov in cov` 子串 | `test_sync_ignores_non_production_covariate` | 对齐 |
| variant_id 下划线切分兜底（v1.2） | `189-193` | 同上用 `ss_calendar_cyclical` | 对齐 |
| `craft_advisory_v2`：degraded/revoked 有效 1 星；revoked 冻结 | `copilot.py:322-341` | revoked / degraded 两测 | 部分对齐 |
| degraded：EV<0 或 PF<0.95 | `211-212` | `test_sync_degrades_on_negative_ev` | 对齐 |
| revoked：连续 2 个月 degraded | **无** 连续月计数，sync 从不写 `revoked` | 只测手工把状态设为 revoked | **缺口** |
| **不改 SCHEMES**（Non-Goals / Invariants） | 只读 `SCHEMES` 填 KB；退役改 `slow_loop_status` 与文案 | `test_build_includes_new_fields` 断言 KB 与 SCHEMES 协变量一致，不改 SCHEMES | 对齐 |
| 晋升需人工改回 `ok` | 无自动晋升 | 无 | 对齐 |

**生产接线**: `copilot.py:445` `run_one` 仍调 `craft_advisory`（v1），**不调** `craft_advisory_v2`。函数与单测存在，领航员主路径不生效。

**缺口严重度**: revoked 规则 = Medium。v2 未接线 = High（治理文案在生产看不见；仍不改 SCHEMES、不改硬门）。

---

## SPEC-010：calendar 交易时段自愈

**文件**: `cascade/features.py` `calc_calendar_cyclical`，`cascade/data_validator.py`  
**测试**: `TestSPEC010TradingHourAutoDetect`，既有 `tests/test_calendar_cyclical.py`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| `valid_hours is None` 时 `detect_trading_hours`，禁止一上来就 `freq='h'` | `features.py:2210-2212` | `test_calc_calendar_no_silent_fallback` | 对齐 |
| Note 3：小时占比 ≥5% 才算交易时段 | `data_validator.py:562-581` 默认 `min_frequency_pct=0.05` | `test_detect_trading_hours_filters_noise` | 对齐 |
| `generate_trading_dates` 跳过非交易小时与周末 | `584-601`；`features.py` 协变量时间轴 `1031-1033`、`1458-1460` 调用 | 日历形状测试 | 对齐 |
| Horizon 编码用真实交易时段 | `calc_calendar_cyclical` **内联** while 循环（`2221-2233`），未调用 `generate_trading_dates`；嗅探结果为空时仍 `freq='h'`（`2214-2220`） | 有自动嗅探测试，无「空列表回退」测试 | 部分对齐 |

空列表回退是嗅探失败的最后兜底，不是「None 时静默 hourly」。主路径已自愈。

---

## SPEC-011：主力换月比例后复权

**文件**: `data/data_store.py`，`data/tqsdk_fetcher.py`  
**测试**: `TestSPEC011RollAdjustment`

| 条款 | 代码 | 测试 | 判定 |
|------|------|------|------|
| 向量化 `adj_series`，禁止循环逐次 `*=` | `data_store.py:113-154` | `test_no_quadratic_explosion` | 对齐 |
| 保留 `raw_close` | `127-130` | `test_raw_close_preserved` | 对齐 |
| 最新合约不动（factor=1） | `142-145` 只乘 `dt < roll_dt` | `test_latest_contract_unchanged` | 对齐 |
| 报告层禁止除法还原，预测即名义价 | 预测/领航员路径无 `/ adjustment_factor` | 无 | 对齐 |
| **同时间戳** `roll_ratio = P_new(t)/P_old(t)` | `detect_roll_events`（`tqsdk_fetcher.py:268-315`）读列或默认 1.0，**不算截面**。`detect_rolls_from_price_gaps`（`data_store.py:83-110`）用 `closes[i]/closes[i-1]`，混入当日涨跌（spec 点名的 v1.0 缺陷） | `test_detect_roll_events_basic` 不断言 ratio | **缺口** |
| TqSdk 换月时刻双合约快照 | `tqsdk_fetcher.py` 无双订阅/快照 | 无 | **缺口** |
| Note 2：旧合约缺失时前向填充 / 前一根 / `WARN` | 仓内无此回退与日志 | 无 | **缺口** |
| **日线 `raw_close` 短路** | `get_main_continuous` `416-421`：`"raw_close" not in df.columns` 才复权。`main_continuous_1d` 表（`data/db.py:119-122`）与 `MAIN_COLUMNS` **恒有该列**，`SELECT *` 必带列 → 生产日线 **永不**走 `apply_backward_adjustment_robust`。`DailyModel.predict`（`daily_model.py:104-108`）读 `close_price` | 测试直接调复权函数，不经 `get_main_continuous` | **缺口** |

`scripts/data_audit.py:571-581` 仍把 `close_price == raw_close` 当健康，与「读时后复权」合同冲突，加重短路。

**缺口严重度**: raw_close 短路 + 非截面比率 = High（换月跳空可进日线 Context；不改硬门阈值本身）。Critical 仅当已证实生产信号被跳空系统性打歪；本轮按计划挂到条款，不新开全仓取证。

---

## 不变量对照

| 不变量 | 活代码 | 判定 |
|--------|--------|------|
| 硬门 n≥350 / IC≥0.05 不改；`n_eff` 只报告 | `evaluator.gate` 未读 `n_eff` | 对齐 |
| SPEC-006 不改 SCHEMES | 退役写 KB；`prediction_scheme.py` 不在 SPEC-006 提交里 | 对齐 |
| 后复权预测 = 名义价，禁止除法还原 | 预测层无除法还原 | 对齐 |
| 量纲仍是价格点 | MaxDD 保证金路径用点数×乘数；斜率标签见 SPEC-012 | 部分（斜率非对数） |

---

## 测试覆盖缺口（不另计条款）

- 无测试断言 `gate()` 忽略 `n_eff`（源码已证）。
- 无测试断言保证金 MaxDD 输入为净 PnL。
- `test_r_squared_computation` 不调用 `DailyModel.predict`。
- `craft_advisory_v2` 有单测，`run_one` 未接。
- SPEC-011 测试绕过 `get_main_continuous`，测不到短路。

`tests/test_system_hardening.py` 覆盖 10 个 SPEC 的函数级行为；合并提交 `243693d` 带齐实现，计划复选框空不代表未落地。

---

## 严重度汇总（有效缺口 / 部分里的生产偏差）

| 级 | 项 |
|----|----|
| High | SPEC-011 日线 `raw_close` 短路；SPEC-011 非截面 `P_t/P_{t-1}`；SPEC-008 保证金 MaxDD 喂毛 PnL；SPEC-006 `craft_advisory_v2` 未进 `run_one` |
| Medium | SPEC-012 未做对数回归；SPEC-012 copilot 用 v2 当卡片方向；SPEC-006 无「连续两月 revoked」；SPEC-009 回测/领航员未传 `half_life_bars` |
| Low | SPEC-004 报告警告文案；SPEC-008 乘数恒 10；SPEC-009 建议表 8/16 未写入 SCHEMES；SPEC-012 summary 不打印 R² |

本任务不改代码。有效缺口需另开 plan；不要为了填复选框去改 `SCHEMES` 或硬门。

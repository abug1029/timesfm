# Alpha 2.0 Phase 1 — 评价体系重构 + LGBM 基线门禁

- **日期**: 2026-08-04
- **状态**: Draft (待用户 review)
- **Track**: B (模型线 Alpha 2.0)
- **范围**: 仅 A2-P1。A2-P2（残差叠加架构）/ A2-P3（Copilot 升维）spec 待 A2-P1 门禁结果出来后再做。
- **北极星指标**: PF / EV / MaxDD。DirAcc 与 Vol-Scaled MAE **仅 logging，永不参与 Go/No-Go**。

---

## 1. 背景与动机

Phase 9 全量回测确认：当前 TimesFM XReg 架构下，DirAcc 天花板约 58%，3 星（65%）不可达。但 `cascade/evaluation_metrics.py` 的正式门禁是 `PF_dynamic > PF_static AND EV_dynamic > 0`（DirAcc 明确标注"仅报告，不做决策依据"）。

两个未解的关键问题：

1. **58% 是架构限还是信噪比限？** 即：是 TimesFM XReg 的**线性 Ridge 残差学习器**拖了后腿，还是 1H OHLCV 数据本身已无更多 Alpha 可榨？
2. **树模型能不能打败当前生产配置的 PF/EV？** 若能，A2-P2 的 LGBM 残差叠加器值得建；若不能，当前 xreg 已是树模型上限，应转 Track A 或 #10 动态路由。

`forecast_with_covariates(xreg_mode="xreg + timesfm")` 本质是 `final = timesfm_point + xreg_adjustment`，其中 adjustment 是**每次调用在 480-bar context 上单独拟合的线性 Ridge**（`normalize_xreg_target_per_input=True`，combo 模式 `ridge=0.1`）。其线性局限是真实的。但替换它为全局 LGBM 是 3-5 天的大工程——必须先用一根廉价探针确认有可榨的 Alpha，再决定是否投入。

**A2-P1 就是这根探针。**

---

## 2. 目标与非目标

### 目标
1. 在 `evaluation_metrics.py` 增加 **Vol-Scaled MAE**（`|Pred-Actual|/ATR_14`），作为报告诊断字段。
2. 构建 **LGBM 基线探针**：在同一组 walk-forward 点上对比三条曲线的 PF/EV/MaxDD。
3. 产出 **GO/NO-GO 门禁裁决**（含配对 bootstrap 显著性），决定是否启动 A2-P2。

### 非目标（明确排除）
- ❌ 训练残差叠加器（那是 A2-P2）
- ❌ 修改 `forecast_with_covariates` 或任何生产预测路径
- ❌ 修改 `prediction_scheme.py` / `features.py` 的现有协变量逻辑
- ❌ Copilot 终端改造（那是 A2-P3）
- ❌ 池化跨品种统一模型（A2-P1 主线为每品种独立模型；池化为可选后续 A2-P1.1）

---

## 3. 成功标准（GO/NO-GO 门禁）

### 三条曲线（同一组 walk-forward 点）

| 曲线 | 定义 | 角色 |
|------|------|------|
| ① TimesFM-pure | `HourlyModel._fallback_predict`（`forecast()` 无协变量） | A2-P2 残差架构的 backbone；裸模型基线 |
| ② TimesFM-scheme | 当前生产配置（`forecast_with_covariates` + 品种 SCHEMES 协变量） | 要打败的对手 |
| ③ LGBM-B | LGBM 回归百分比收益率 `Y=(Actual−T0)/T0`，12 维标准特征池，`sample_weight=\|Y\|×10000`，dense 训练（§7） | 树模型+特征的天花板探针 |

### 门禁判据（唯一决策依据：PF/EV）

**GO**（启动 A2-P2）：
- LGBM-B 的 PF > TimesFM-scheme 的 PF **且**
- LGBM-B 的 EV > 0 **且**
- 配对 bootstrap（1000 resample，on per-point net PnL 差 `LGBM-B − TimesFM-scheme`）的 EV 差 95% CI 下界 > 0

**NO-GO**（不启动 A2-P2）：
- 上述任一不满足 → 信噪比天花板确认（PF/EV 口径），当前 xreg 已是树模型上限。

**每品种独立裁决 + 全量聚合裁决**：门禁按品种分别判定（哪些品种有可榨 Alpha）。聚合裁决规则：在**足样本品种**（n≥350，排除 UNDERPOWERED）中，GO 品种数占多数（>50%）-> 聚合 GO；否则聚合 NO-GO。聚合 GO 即触发 A2-P2 启动；聚合 NO-GO 但个别品种 GO -> 仅对 GO 品种考虑 A2-P2 局部试点（记录待定）。

### 诊断（仅打印，不决策）
- LGBM-B vs TimesFM-pure：树模型是否比裸 backbone 强
- LGBM-B 特征重要性中 TimesFM 特征(#10/#11)的增益占比：间接量化大模型时序表征贡献（无独立 standalone run）
- Vol-Scaled MAE 三曲线对比

> **关键反 framing**：原"58% DirAcc 天花板"重定义为"PF/EV 天花板"。DirAcc 仅作 logging 印证，不参与门禁代码逻辑。

---

## 4. 标准宽特征池（12 维，全品种统一 schema）

设计原则（用户裁决）：SCHEMES 里的单一协变量配置是 TimesFM XReg 线性残疾的妥协产物。LGBM 的威力在于非线性特征交叉，必须铺开一组**逻辑自洽、独立物理意义**的标准化特征，让信息增益自动挑选。过拟合由 LGBM 超参 + Nested CV 压制，而非人工掩盖特征。

| # | 特征 | 来源 | 物理意义 |
|---|------|------|----------|
| 1 | `daily_slope` | `features.build_daily_slope_covariate` 末值 | 宏观趋势基石 |
| 2 | `hourly_slope` | `features.calc_hourly_slope` 末值 | 微观价格动能 |
| 3 | `pca_momentum` | `features.calc_pca_momentum` 末值 | 多周期 RSI 复合动量 |
| 4 | `rsi_state` | `features.calc_rsi_state` 末值 (-2..+2) | 均值回归状态 |
| 5 | `oi_pct_change` | `features.calc_oi_pct_change` 末值 | 资金流动性 |
| 6 | `hurst` | `features.calc_rolling_hurst` 末值 (-1..+1) | 分形/趋势持续性 |
| 7 | `vol_prob` | `vol_risk_filter.VolRiskFilter.bind_for_symbol().evaluate().vol_prob` | 波动率爆发概率 |
| 8 | `hour_of_day` | T0 的 `dt.hour` (0-23) | 时段异质性（早/午/夜盘） |
| 9 | `day_of_week` | T0 的 `dt.dayofweek` (0-6) | 周内季节性 |
| 10 | `timesfm_pure_pred` | 曲线①的 T+24 点预测 / T0_close（归一化） | TimesFM backbone 信号 |
| 11 | `timesfm_confidence` | 曲线①的 P90−P10 宽度 / T0_close | 模型不确定度 |
| 12 | `horizon_slope` | `daily_result.horizon_slope` | 日线级联斜率 |

**全品种统一 schema**：所有品种喂相同 12 维。缺失特征（如某品种无 OI）→ NaN，由 LGBM 原生 NaN 处理（`use_missing=True`）吸收，不填 0 不丢弃。

**防穿越**：所有特征仅用 `cutoff` 前数据。`BacktestDataStore(symbol, cutoff)` 保证 1H/daily 截止；`vol_prob` 的 VolRiskFilter 亦在 cutoff-bounded 数据上构造。

**vol_prob 前瞻瑕疵声明**（用户陷阱 2）：现有 R0/R1 波动率模型用截止 2026-03-31 的全量数据一次性训练。walk-forward 评估点若早于 2026-03，`vol_prob` 由"看过未来"的模型产出，存在极轻微 Lookahead Bias。探针不搞在线重训，仅在代码注释与最终裁决报告显式声明此瑕疵（"vol_prob 在 2026-03 前评估点有轻微 Lookahead，不影响探针定性结论"）。

**编码说明**：`hour_of_day`/`day_of_week` 用原始整数（树按阈值分裂，能学到"夜盘 21-23∪0-1"这类区间）。若 impl 阶段发现整数编码欠拟合，可补 sin/cos 编码作为 refinement（不阻塞主线）。

**特征/目标尺度约定**：特征 #10/#11 归一化（/T0_close）为平稳性；回归目标亦用**百分比收益率** `Y=(Actual−T0)/T0`（用户建议，首版治非平稳，见 §8）。预测时 `Pred_move = T0 × Pred_Return` 还原价格点送 PF/EV。特征与目标同在收益率尺度，叶子切分免疫价格水位跨年漂移。

---

## 5. 设计决策：每品种独立模型（非池化）

**决策**：A2-P1 主线为**每品种独立 LGBM**（统一 12 维 schema，百分比收益率目标，见 §8）。

**理由**：
1. 用户指定的目标 `Actual_T24 − T0` 与 `sample_weight=|move|` 均为价格点尺度，品种间不可比（MA~2500 vs ss~14000）。
2. 每品种 n≈396（AO n=193）对 12 特征 LGBM 足够（10-20 样本/特征阈值满足）。
3. 与当前每品种 SCHEMES 苹果对苹果可比，门禁能定位**哪些品种**有可榨 Alpha。
4. "统一特征池"指 schema 统一，非模型统一——每品种模型用相同特征集满足该约束。

**池化跨品种模型**（ATR 归一化目标、跨品种学习）列为可选 A2-P1.1：仅当每品种主线 NO-GO 但怀疑是小样本所致时启动。A2-P1 不构建。

---

## 6. 组件

| 文件 | 动作 | 内容 |
|------|------|------|
| `cascade/evaluation_metrics.py` | 改（追加） | `calc_vol_scaled_mae(pred, actual, atr)`；不动 `calc_net_metrics`/`compare_strategies` 决策逻辑 |
| `cascade/lgbm_features.py` | 新建 | `build_dense_feature_matrix(symbol, store, dense_step) -> DataFrame`：全历史逐 bar 12 维特征 + Y + weight（§7 阶段 0）；`extract_t0_features` 为单点封装 |
| `scripts/a2_p1_lgbm_baseline.py` | 新建 | 探针 runner：walk-forward 三曲线 + 嵌套 CV + bootstrap + JSONL 落盘 + 裁决报告 |
| `reports/research/2026-08-04_a2_p1_baseline_result.md` | 生成 | 门禁裁决报告（GO/NO-GO + 诊断 + 三曲线表） |

**复用**：`features.py`（协变量计算）、`hourly_model.py`（曲线①②预测）、`data_store.BacktestDataStore`（cutoff 防穿越）、`prediction_scheme.SCHEMES`（品种清单）、`vol_risk_filter.VolRiskFilter`（vol_prob）、`monthly_backtest.py`（396 点窗口 + JSONL 断点续跑模式）、`toxic_variety_runner`（共享 TimesFM 模型实例模式）。

---

## 7. 数据流与 walk-forward 方法论（Dense Training, Sparse Evaluation）

> **用户陷阱 1 修正**：评估用稀疏无重叠点保统计意义；训练用密集历史 bar 防小样本过拟合。两者解耦。原方案在 396 稀疏点上做 Nested CV，首折训练 <80 样本 -> 必然过拟合。修正为：训练集 = 截止 T0 前所有有效 1H bar（step=24 采样，非重叠目标，~300-400 行/品种）；测试集 = 当前 T0 评估点。

### 阶段 0 - 特征矩阵预计算（每品种一次性）

对品种全量 1H 历史，按 `--dense-step`（**默认 24**）采样所有有效 bar t（满足 t+24 存在），逐 bar 计算：
- **X_t** = 12 维特征（§4），其中 `timesfm_pure_pred`/`timesfm_confidence` 由 TimesFM **批量**预测（共享实例，batch=128）
- **Y_t** = (close[t+24] − close[t]) / close[t]（百分比收益率，§8）
- **weight_t** = |Y_t| × 10000

缓存为 `reports/a2_p1_features/<symbol>_dense_matrix.parquet`。

> **为何 step=24 而非 step=4**（用户优化指令 · Overlapping Target Bias）：目标 Y_t = 未来 24 bar 收益率。若 step=4，相邻样本（T 与 T+4）的目标窗口重叠 83%，极高自相关致 LGBM 树分裂过拟合。step=24 使每样本目标完全独立无重叠，统计更鲁棒。且算力骤降：~10000 bar 只需 ~400 次 TimesFM 预测（batch=128 → 3-4 batch，分钟级，非数小时）。若 impl 发现欠拟合（样本不足），降至 `--dense-step 12`（50% 重叠，样本翻倍）。

> **12 特征完全体是唯一主线**（用户裁决）：不设 standalone 预筛。TimesFM 的时序表征不可被传统指标替代，去 #10/#11 的 9 特征败北 ≠ 12 特征败北，预筛会造成假阴性误杀 Alpha 2.0。算力已由 step=24 化解，无需降级。

### 阶段 1 - walk-forward 评估（396 稀疏点）

```
SMOKE: ss/rb/i 三品种 × --max-points 50
FULL:  全 20 品种 × 396 点 (step=24, 无重叠, AO 等标注 UNDERPOWERED)

eval_points = walk_forward_grid(variety, step=24, max_points=396)  # 复用 monthly_backtest 网格
for T0 in eval_points:
    1. 训练切片 = dense_matrix 中 t <= T0-24 的所有行 (成千上万, 防穿越)
    2. 曲线①② TimesFM-pure/scheme pred @ T0 (① 已在 dense_matrix; ② 复用 monthly_backtest 缓存或现算)
    3. 内层 TimeSeriesSplit(5) on 训练切片 -> 选超参 (仅训练段, 外层 T0 零接触)
    4. LGBM 训练 on 全训练切片 (选定超参) -> 预测 @ T0 -> Pred_Return
    5. Pred_move   = T0_close × Pred_Return    (还原价格点)
       Actual_move = close[T0+24] - close[T0]
    6. 记录 (Pred_move, Actual_move, pure_pred, scheme_pred, T0)
refit 频率: --refit-every N (默认 10), 每 N 个 eval 点重训一次, 中间复用上次模型
            (最近 N bar vs 千万级训练集, stale 可忽略)

三曲线分别 calc_net_metrics(PF/EV/MaxDD) + calc_vol_scaled_mae(logging)
配对 bootstrap(1000) on per-point net PnL 差 -> EV 差 95% CI
JSONL 原子追加 + --resume 断点续跑 (同 monthly_backtest 抗崩溃)
```

**TimesFM 共享实例**：全 run 单次加载（~800MB）；阶段 0 的 dense 批量预测 + 曲线② 现算共用同一实例（`_fallback_predict` 用 `forecast()`，曲线② 用 `forecast_with_covariates`，每次 predict 前 `compile` 对应配置）。

---

## 8. 嵌套 CV 与过拟合控制（门禁可信前提）

LGBM 超参**仅在每折训练段内选**，外层测试折零接触。否则基线乐观偏差会把 NO-GO 误判为 GO。

**超参网格**（内层 TimeSeriesSplit 5 折选）：
- `num_leaves`: [15, 31, 63]
- `min_child_samples`: [20, 50, 100]
- `lambda_l1`: [0.0, 0.1, 1.0]
- `lambda_l2`: [0.0, 0.1, 1.0]
- `colsample_bytree`: [0.7, 0.9, 1.0]
- `n_estimators`: [100, 300]
- `learning_rate`: [0.05, 0.1]
- `max_depth`: [-1, 6, 8]

**目标**（用户建议，首版即用百分比收益率治非平稳）：回归 `Y = (Actual_T24 − T0)/T0`（百分比收益率），`sample_weight = |Y| × 10000`（放大防浮点下溢，重权大波动对齐 PF）。还原价格：`Pred_move = T0_close × Pred_Return`，再送 `calc_net_metrics` 算 PF/EV。
**早停**：内层用验证折 `early_stopping_rounds=50`，防过拟合。

**小样本品种**（dense 训练切片 < 200 行，如 AO 历史短）：报告标注 `UNDERPOWERED`，门禁结论降权。step=24 下足样本品种训练集 ~300-400 行；若普遍 <200，全量降 `--dense-step 12` 翻倍样本。

---

## 9. 错误处理

- TimesFM 预测失败 → 该点 SKIP + 记录（不崩溃）；xreg_fallback 标记
- 特征 NaN/Inf → 保留 NaN（LGBM 原生吸收），仅全 NaN 行 SKIP
- LGBM 训练失败（某折）→ 该折 SKIP，日志记录跳过数（Rule 12 可见失败）
- 数据不足品种 → 仍跑，报告标注 UNDERPOWERED
- `vol_prob` 计算需 VolRiskFilter 在 cutoff-bounded 数据构造；若该品种无对应 sector 模型 → `vol_prob=NaN`，不阻断
- **vol_prob 前瞻瑕疵**：2026-03 前评估点的 vol_prob 有轻微 Lookahead（模型训练截止 2026-03-31）；代码注释 + 裁决报告显式声明，不重训
- JSONL 原子追加 + `--resume <checkpoint.jsonl>` 断点续跑（同 monthly_backtest）
- 全程日志：跳过点数、失败原因、UNDERPOWERED 标注均明示

---

## 10. 测试

- **单测 `calc_vol_scaled_mae`**：已知 ATR + 已知误差 → 期望缩放值（含 ATR=0 边界）
- **单测 `build_dense_feature_matrix` 防泄漏**：构造 cutoff=T，断言 dense 矩阵中 t 行特征均不含 `dt > t` 的数据（无未来泄漏）
- **单测 dense 矩阵 schema**：断言 12 维特征键齐全 + Y + weight 列，缺失特征为 NaN 非 0
- **单测 LGBM 嵌套 CV**：小样本下断言外层测试折预测仅用训练段超参（无泄漏）
- **集成 smoke**：单品种(ss) `--max-points 20` 跑通三曲线 + JSONL 落盘 + 报告生成
- 门禁裁决本身是研究产出，非 pass/fail 自动化测试

---

## 11. 输出产物

1. `reports/a2_p1_features/<symbol>_dense_matrix.parquet` — 每品种 dense 特征矩阵（12 维 + Y + weight，阶段 0 一次性缓存）
2. `reports/a2_p1_baseline_results.jsonl` — 每点三曲线预测 + 实际 + 特征（断点续跑）
3. `reports/research/2026-08-04_a2_p1_baseline_result.md` — 裁决报告：
   - 每品种三曲线 PF/EV/MaxDD 表
   - 每品种 GO/NO-GO + bootstrap CI
   - 全量聚合裁决
   - 诊断（DirAcc ceiling、Vol-Scaled MAE、LGBM 特征重要性 Top-K）
4. `reports/a2_p1_lgbm_models/` — 每品种训练好的 LGBM pkl（若 GO，供 A2-P2 复用）

---

## 12. 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 北极星指标 | PF/EV/MaxDD | 用户裁决；与 evaluation_metrics.py 正式门禁一致 |
| 特征池 | 9 维市场特征 + 3 维 TimesFM 信号 | 用户裁决；打破 SCHEMES 线性残疾妥协 |
| 模型粒度 | 每品种独立 | 与 SCHEMES 苹果对苹果可比；百分比收益率已使跨品种可比，独立模型保留品种特异性 |
| 过拟合控制 | Nested CV + 超参网格 + Dense 训练 | 门禁可信前提；dense 防小样本，CV 防超参泄漏 |
| 训练数据 | Dense (step=4 全历史) + Sparse 评估 (396 点 step=24) | 用户陷阱 1：396 点首折 <80 样本必过拟合 |
| 回归目标 | 百分比收益率 Y=(Actual−T0)/T0 | 用户建议：免疫价格漂移；还原价格点算 PF/EV |
| vol_prob 前瞻 | 声明不重训 | 模型训练截止 2026-03-31；探针定性结论不受影响 |
| DirAcc/Vol-Scaled MAE | logging only | 用户裁决；不进 Go/No-Go |
| 范围 | 仅 A2-P1，门禁驱动 A2-P2 | 避免门禁失败时浪费 A2-P2 设计工 |

---

## 13. 开放问题（impl 阶段解决，不阻塞 spec）

1. `hour_of_day`/`day_of_week` 整数编码是否够，还是要补 sin/cos → smoke 阶段验证
2. `vol_prob` 的 VolRiskFilter 在回测中按 cutoff 构造的性能开销 → impl 时测，必要时缓存
3. LGBM 特征重要性若显示某特征恒无用，是否从池中剔除 → 不剔除（保持统一 schema），仅 logging
4. 池化模型 A2-P1.1 是否启动 → 仅当每品种主线 NO-GO 且怀疑小样本时
5. ~~目标非平稳性~~ 已解决：用户建议首版即用百分比收益率 `Y=(Actual−T0)/T0` 作目标，免疫价格水位跨年漂移（见 §8），无需等 NO-GO 复查
6. ~~TimesFM dense 预计算成本~~ 已化解：`--dense-step 24` 默认使 TimesFM 调用降至 ~400/品种（batch=128，分钟级）。欠拟合时降 `--dense-step 12`。不降级 standalone（见 §7）。

---

## 14. 参考资料

- `cascade/evaluation_metrics.py` — 全项目唯一秤（PF/EV 门禁）
- `cascade/hourly_model.py:228` — `forecast_with_covariates(xreg_mode="xreg + timesfm")` 线性 Ridge 残差
- `cascade/features.py` — 11+ 协变量计算
- `cascade/vol_risk_filter.py:315` — `vol_prob = predict_proba(xs)[0,1]`
- `reports/research/20260803_phase9_two_star_to_three_study.md` — 58% 天花板实证
- `scripts/toxic_variety_runner.py` — 共享模型 + JSONL 断点续跑模式
- `scripts/monthly_backtest.py` — 396 点 walk-forward 网格

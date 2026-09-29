# FM_a 系统优化规格说明书 (Spec)

> **基于**: 系统设计文档 v2.4 (`docs/system_design.md`)  
> **日期**: 2026-09-10  
> **目标**: 将设计文档 §11 已知局限 + §4.3 治理机制转化为可执行的优化任务  
> **原则**: 每项改动必须保持回测内部一致性，禁止破坏现有过门裁决

---

## 目录

1. [P0 — 必须修复（影响实盘正确性）](#p0--必须修复)
2. [P1 — 应当改进（影响统计严谨性）](#p1--应当改进)
3. [P2 — 建议优化（提升工程质量）](#p2--建议优化)
4. [依赖关系与执行顺序](#依赖关系与执行顺序)

---

## P0 — 必须修复

### SPEC-001: 熔断后置信区间宽度归零

**来源**: §11.7  
**严重度**: CRITICAL — 向交易员传递错误的零风险信号  
**影响文件**: `cascade/vol_risk_filter.py`

**现状**:
```python
def apply_neutral_override(point_forecast, base_price, quantile_forecast):
    flat = np.full(horizon, float(base_price))
    q_flat = np.full_like(quantile_forecast, float(base_price))  # ← 所有分位数 = base_price
    return flat, q_flat
```

**问题**: Vol Gating 触发时，P10 = P50 = P90 = base_price，CI 宽度 = 0。交易员看到"零波动"假象。

**规格**:
1. 点预测拉平为 base_price（空仓建议，保持不变）
2. 分位数预测改为基于 ATR 的布朗运动扩散带：
   - `sigma = ATR_14 / sqrt(24)` （单 bar 标准差）
   - `q_override[t] = base_price + z_q * sigma * sqrt(t) * 1.5` （1.5 为高波风控乘数）
   - z_q: P10=-1.28, P25=-0.67, P50=0, P75=+0.67, P90=+1.28
3. 必须保证分位数单调递增（P10 ≤ P25 ≤ ... ≤ P90）
4. 报告输出标注"已熔断 — 波动率惩罚带"

**验收标准**:
```python
# 单元测试
def test_neutral_override_quantile_spread():
    point = np.array([100.0] * 24)
    quant = np.array([[98,99,99.5,100,100,100,100.5,101,102,103]] * 24)
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=2.0)
    
    assert np.all(flat_p == 100.0)           # 点预测拉平
    assert flat_q[0, 0] < flat_q[0, 9]       # P10 < P90
    assert flat_q[-1, 9] - flat_q[-1, 0] > 0 # 末端 CI 宽度 > 0
    # 单调性
    for t in range(24):
        for i in range(9):
            assert flat_q[t, i] <= flat_q[t, i+1]
```

**预估工作量**: 0.5 天

---

### SPEC-002: 空头方向止盈止损分位数对偶

**来源**: §8.1, §9 审查意见  
**严重度**: CRITICAL — 空头场景下止损止盈反转  
**影响文件**: `scripts/copilot.py`

**现状**: `copilot.py` L608-610 已正确处理：
```python
f"- **做多**: 止损可参考 P10 下方 1–2 个最小变动价位；"
f"- **做空**: 止损可参考 P90 上方对称处理"
```

**问题**: 设计文档 §8.1 的模板只展示了多头场景，新开发者可能按模板错误实现。

**规格**:
1. 在 `craft_advisory()` 中增加 `generate_risk_bounds(direction, p10, p90)` 函数
2. 方向自适应映射：
   - 做多: 止损=P10, 止盈=P90
   - 做空: 止损=P90, 止盈=P10
   - 中性: 支撑=P10, 阻力=P90
3. 输出文案必须包含方向标签

**验收标准**:
- 做多报告: "止损参考 (多头防线): P10=xxx"
- 做空报告: "止损参考 (空头防线): P90=xxx"
- 单元测试覆盖三种方向

**预估工作量**: 0.5 天

---

### SPEC-003: 日线前视防护 — cutoff_hour 分时判定

**来源**: §2 审查意见, §11  
**严重度**: HIGH — 夜盘评估时使用滞后 1 天的日线  
**影响文件**: `data/data_store.py`

**现状**: `BacktestDataStore.get_main_continuous` 已实现 cutoff_hour ≥ 15 判定 ✅

**问题**: 需确认生产路径（非回测路径）是否也有同样保护。

**规格**:
1. 确认 `DataStore.get_main_continuous`（非 Backtest 路径）的 cutoff 行为
2. 若生产路径无 cutoff 机制，需增加 `cutoff_ts` 参数支持
3. 所有调用 `get_main_continuous` 的预测脚本必须感知当前时刻

**验收标准**:
- 周一 21:30（夜盘）评估时，日线数据包含周一当日（15:00 后已收盘）
- 周一 10:30（日盘）评估时，日线数据仅到上周五
- 单元测试覆盖 4 个时段（早盘/午盘/夜盘/周末）

**预估工作量**: 1 天

---

## P1 — 应当改进

### SPEC-004: 重叠窗口有效样本量修正

**来源**: §11.8  
**严重度**: HIGH — 名义 n=589 可能远大于有效自由度  
**影响文件**: `task_FM/evaluations/fm_eval/evaluator.py`, `scripts/aligned_slow_loop.py`

**现状**: 硬门使用名义 n ≥ 350，忽略 STEP=2 + HORIZON=24 的 91.7% 重叠。

**规格**:
1. 在 evaluator 中增加有效样本量估算函数：
   ```python
   def effective_n(nominal_n, horizon, step, autocorr_fn):
       """Bartlett 公式估算有效自由度"""
       # 使用评估残差的自相关系数
       rho = autocorr_fn(lag=step)
       n_eff = nominal_n / (1 + 2 * (horizon/step - 1) * rho)
       return max(1, int(n_eff))
   ```
2. 回测报告同时输出名义 n 和有效 n
3. 硬门暂不修改（保持 n ≥ 350 名义值），但报告中标注有效 n
4. 后续版本可考虑将硬门改为有效 n ≥ 50

**验收标准**:
- 回测 JSONL 每行增加 `n_eff` 字段
- 报告显示: "名义 n=589, 有效 n≈50 (ρ=0.92)"
- 不改变现有裁决结果

**预估工作量**: 2 天

---

### SPEC-005: 置信区间对数空间保序展宽

**来源**: §11.11  
**严重度**: MEDIUM — 极端场景下分位数可能倒挂或出现负值  
**影响文件**: `config/prediction_scheme.py` (`confidence_band`)

**现状**: `confidence_band()` 在绝对价格空间做线性对称拉伸。TimesFM 内置 `fix_quantile_crossing=True` 但展宽可能重新引入交叉。

**规格**:
1. 转移至对数空间展宽：
   ```python
   log_q = np.log(np.maximum(quantile_forecast, 1e-6))
   log_median = log_q[:, 5:6]
   log_adjusted = log_median + (log_q - log_median) * mult
   log_adjusted = np.sort(log_adjusted, axis=-1)  # 保序
   return np.exp(log_adjusted)
   ```
2. 保证: 输出分位数严格单调递增
3. 保证: 所有分位数值 > 0

**验收标准**:
```python
def test_confidence_band_no_crossing():
    q = np.array([[100,102,104,106,108,110,112,114,116,118]] * 24)
    scheme = VarietyScheme(..., confidence_multiplier=1.5)
    adjusted = confidence_band(q, scheme)
    # 单调性
    for t in range(24):
        for i in range(9):
            assert adjusted[t, i] <= adjusted[t, i+1]
    # 正值
    assert np.all(adjusted > 0)
```

**预估工作量**: 1 天

---

### SPEC-006: SCHEMES 退役/晋升治理机制

**来源**: §4.3  
**严重度**: MEDIUM — 慢环实证与生产配置脱节无自动纠偏  
**影响文件**: `scripts/copilot.py`, `config/prediction_scheme.py`

**现状**: SCHEMES 固化后无自动降级机制。SR 在慢环中退化（PF=0.973, EV=-0.85）但生产仍为 2 星。

**规格**:
1. 在 `knowledge_base.json` 中增加 `slow_loop_status` 字段：
   ```json
   "sr": {
     "credit_stars": 2,
     "slow_loop_status": "degraded",  // "ok" | "degraded" | "revoked"
     "slow_loop_pf": 0.973,
     "slow_loop_ev": -0.85
   }
   ```
2. `copilot.py` 读取 `slow_loop_status`：
   - `degraded`: 降级为 1 星行为（弱建议，轻仓）
   - `revoked`: 冻结强建议输出
3. 退役触发条件：连续 2 个月慢环 EV < 0 或 PF < 0.95
4. 晋升触发条件：慢环硬门通过 + monthly_backtest 对齐验证

**验收标准**:
- SR 在 `slow_loop_status=degraded` 时，copilot 输出"弱信号品种，轻仓试探"
- 手动设置 `revoked` 后，copilot 不输出"强建议"文案
- `build_knowledge_base.py` 增加慢环状态同步逻辑

**预估工作量**: 2 天

---

### SPEC-007: 短段信号权重余弦滚降

**来源**: §11.9  
**严重度**: MEDIUM — Bar 12→13 信号强度断崖  
**影响文件**: `config/prediction_scheme.py` (`signal_weight`)

**现状**: `short_horizon_only=True` 品种，`w[:12]=1.0, w[12:]=0.0`

**规格**:
1. 余弦滚降替代硬截断：
   ```python
   def signal_weight_smooth(horizon=24, plateau=8, cutoff=16):
       t = np.arange(1, horizon + 1)
       w = np.ones(horizon)
       decay_mask = (t > plateau) & (t <= cutoff)
       w[decay_mask] = 0.5 * (1 + np.cos(np.pi * (t[decay_mask] - plateau) / (cutoff - plateau)))
       w[t > cutoff] = 0.0
       return w
   ```
2. 保持向后兼容：`short_horizon_only=False` 的路径不变
3. 品种配置中可选 `smooth_cutoff: bool = True`

**验收标准**:
- CJ/AO/CF 的信号权重曲线无断崖
- Bar 8: 1.0, Bar 12: ~0.5, Bar 16: 0.0
- 现有回测结果不受影响（smooth_cutoff 默认 False）

**预估工作量**: 0.5 天

---

## P2 — 建议优化

### SPEC-008: MaxDD 保证金口径

**来源**: §11.10  
**严重度**: LOW — 当前名义 MaxDD 仍可用于策略比较  
**影响文件**: `cascade/evaluation_metrics.py`

**规格**:
1. 增加 `calc_margin_dd()` 函数，接受保证金比例参数
2. 报告同时输出名义 MaxDD 和保证金口径 MaxDD
3. 标准账户: 100 万元，单品种固定名义头寸

**预估工作量**: 1 天

---

### SPEC-009: 协变量半衰期品种级配置

**来源**: §11.4  
**严重度**: LOW — 当前全局 12 bars 对多数品种可接受  
**影响文件**: `config/prediction_scheme.py`, `cascade/features.py`

**规格**:
1. `VarietyScheme` 增加 `half_life_bars: float = 12.0`
2. `features.py` 的衰减函数从配置读取而非硬编码
3. 高频品种（MA/SC）可设为 6 bars，低换手品种（CU）设为 18 bars

**预估工作量**: 1 天

---

### SPEC-010: calendar_cyclical 交易时段感知

**来源**: §11.5  
**严重度**: LOW — 日历信号低频，24 bars 内影响有限  
**影响文件**: `cascade/features.py` (`calc_calendar_cyclical`)

**规格**:
1. 复用 `data_validator.generate_trading_dates()` 替代 `pd.date_range(freq='h')`
2. 需要传入品种的交易所交易时段信息

**预估工作量**: 0.5 天

---

### SPEC-011: 主力换月比例后复权

**来源**: §11.1  
**严重度**: LOW — 换月频率低，TimesFM RevIN 部分缓解  
**影响文件**: `data/data_store.py`, `data/tqsdk_fetcher.py`

**规格**:
1. 换月日计算 `adjustment_factor = P_new / P_old`
2. 对 T < T_roll 的历史数据做比例调整
3. 报告输出层逆向还原为名义价格
4. `adjustment_factor` 字段当前全为 0，需实现真实计算

**预估工作量**: 3 天

---

### SPEC-012: 斜率计算对数回归 + R² 滤网

**来源**: §11.2  
**严重度**: LOW — 当前线性回归对多数品种足够  
**影响文件**: `cascade/daily_model.py`

**规格**:
1. 改用对数价格回归: `ln(P) = α + β·t`
2. 增加 R² 检查: R² < 0.35 时标记 `slope_unreliable=True`
3. `DailyResult` 增加 `r_squared: float` 和 `slope_unreliable: bool`
4. `cascade_predict.py` 在 R² < 0.35 时输出"形态分歧"警告

**预估工作量**: 1 天

---

### SPEC-013: Stage 1 → Stage 2 漂移截断

**来源**: §11.6  
**严重度**: LOW — 阶梯衰减已部分抑制误差放大  
**影响文件**: `cascade/features.py`

**规格**:
1. 在 `build_covariate_matrix` 的 rsi_state/rsi_slope 分支增加漂移截断：
   ```python
   max_drift_pct = 0.05  # 5% 单日复合漂移上限
   upper = last_close * (1 + max_drift_pct) ** np.arange(1, len(pred)+1)
   lower = last_close * (1 - max_drift_pct) ** np.arange(1, len(pred)+1)
   safe_pred = np.clip(pred_daily, lower, upper)
   ```
2. 截断后计算 RSI 等衍生特征

**预估工作量**: 0.5 天

---

## 依赖关系与执行顺序

```
Phase 1 (P0, 本周):
  SPEC-001 → SPEC-002 → SPEC-003
  (熔断CI → 空头对偶 → 日线前视)

Phase 2 (P1, 下周):
  SPEC-004 → SPEC-005 → SPEC-006 → SPEC-007
  (有效样本量 → 对数保序 → 退役机制 → 余弦滚降)

Phase 3 (P2, 后续):
  SPEC-008 ~ SPEC-013 (可并行)
```

**关键依赖**:
- SPEC-004 (有效样本量) 的结果可能影响未来硬门调整
- SPEC-006 (退役机制) 依赖慢环数据管道稳定
- SPEC-011 (换月复权) 是独立大项，可单独排期

---

## 不变量约束

以下约束在任何 SPEC 实施过程中**不可违反**：

1. **回测内部一致性**: 训练和推理必须使用相同的填充/截断逻辑
2. **跨品种对齐不变量**: 所有品种 eval 点数必须恒等（当前 589）
3. **硬门单调性**: 已通过的裁决不可被新代码推翻
4. **量纲一致性**: 所有盈亏计算在绝对价格点数空间
5. **防穿越**: 任何修改不得引入未来信息

---

*Spec 维护: 每项 SPEC 完成后在此文档标注状态 (✅ Done / 🔄 In Progress / ⏳ Pending)*

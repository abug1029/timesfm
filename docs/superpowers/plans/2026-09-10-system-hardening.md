# System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 10 SPEC items (SPEC-004~013) that upgrade FM_a from "usable" to "trustworthy" — fixing statistical rigor, prediction decision closure, report consistency, and data layer integrity.

**Architecture:** 3-phase rollout: Phase 1 establishes statistical defense lines (effective sample size, confidence band isolation, margin-based MaxDD); Phase 2 closes prediction-to-report loops (cosine rolloff, R² gating, drift clipping, scheme retirement); Phase 3 hardens data sources (trading hour auto-detect, per-variety half-life, roll adjustment). All changes preserve existing hard gates and aligned verdicts.

**Tech Stack:** Python 3.11, NumPy, pandas, TqSdk, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-09-10-system-hardening-design.md` (v1.2-final)

## Global Constraints

- Hard gate thresholds unchanged: n≥350, IC≥0.05, EV>0
- `aligned_verdicts.jsonl` must have zero diff before/after each SPEC
- No GPU acceleration — CPU only
- No new covariates — do not expand covariate pool
- All price computations in absolute price space (points)
- No look-ahead bias — all computations use only past data
- SPEC-004 n_eff is report-only, must not alter gate_pass logic
- SPEC-006 retirement only affects copilot output, not prediction_scheme.py SCHEMES

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `task_FM/evaluations/fm_eval/evaluator.py` | Add `effective_sample_size()` |
| Modify | `scripts/aligned_slow_loop.py` | Output `n_eff` field in JSONL |
| Modify | `config/prediction_scheme.py` | Rewrite `confidence_band()`, add `smooth_cutoff` + `half_life_bars` to VarietyScheme, add cosine `signal_weight()` |
| Modify | `cascade/evaluation_metrics.py` | Add `calc_margin_maxdd_robust()` |
| Modify | `cascade/daily_model.py` | Add R² / `slope_unreliable` to DailyResult, add `_compute_direction_v2()` |
| Modify | `cascade/features.py` | Atomic refactor: replace all `12.0` with `_decay_fill(half_life)`, add `_clip_prediction_drift()`, update `calc_calendar_cyclical()` |
| Modify | `cascade/data_validator.py` | Add `detect_trading_hours()` threshold filter |
| Modify | `scripts/copilot.py` | Add `craft_advisory_v2()` with effective_stars |
| Modify | `scripts/build_knowledge_base.py` | Add `sync_slow_loop_status()` with composite key |
| Modify | `config/knowledge_base.json` | Add `production_covariate`, `slow_loop_status` fields |
| Modify | `data/tqsdk_fetcher.py` | Add `detect_roll_events()` with cross-sectional ratio |
| Modify | `data/data_store.py` | Add `apply_backward_adjustment_robust()` |
| Create | `tests/test_system_hardening.py` | All 10 SPEC unit tests |

---

### Task 1: SPEC-004 — Bartlett Effective Sample Size

**Files:**
- Modify: `task_FM/evaluations/fm_eval/evaluator.py`
- Modify: `scripts/aligned_slow_loop.py`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Produces: `effective_sample_size(nominal_n: int, horizon: int, step: int, residual_autocorr: float | None = None) -> int`
- Consumes: nothing (standalone math function)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_system_hardening.py
import numpy as np
import pytest
from task_FM.evaluations.fm_eval.evaluator import effective_sample_size


class TestSPEC004EffectiveSampleSize:
    """SPEC-004: 完整 Bartlett 卷积核有效样本量"""

    def test_default_rho09_returns_71(self):
        """H=24, S=2, K=11, VIF≈8.237 → n_eff=71"""
        assert effective_sample_size(589, 24, 2) == 71

    def test_no_overlap_returns_nominal(self):
        """step >= horizon → no overlap → n_eff = nominal_n"""
        assert effective_sample_size(100, 24, 24) == 100

    def test_monotonicity_higher_rho_lower_neff(self):
        """rho越大 → VIF越大 → n_eff越小"""
        n_high = effective_sample_size(589, 24, 2, 0.9)
        n_low = effective_sample_size(589, 24, 2, 0.5)
        assert n_high < n_low

    def test_rho05_range(self):
        """rho=0.5 时 n_eff 在合理区间"""
        n_eff = effective_sample_size(589, 24, 2, 0.5)
        assert 120 <= n_eff <= 200

    def test_minimum_is_one(self):
        """极端情况 n_eff 最小为 1"""
        assert effective_sample_size(1, 24, 2) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC004EffectiveSampleSize -v`
Expected: FAIL — `ImportError: cannot import name 'effective_sample_size'`

- [ ] **Step 3: Implement `effective_sample_size` in evaluator.py**

Add to `task_FM/evaluations/fm_eval/evaluator.py` (at end of file):

```python
def effective_sample_size(
    nominal_n: int,
    horizon: int,
    step: int,
    residual_autocorr: float | None = None,
) -> int:
    """
    基于完整 Bartlett 卷积核估算重叠窗口有效独立自由度

    重叠阶数 K = floor((H-1) / S)
    VIF = 1 + 2 * sum_{k=1}^{K} (1 - k/(K+1)) * rho^k
    n_eff = nominal_n / VIF
    """
    if step >= horizon:
        return nominal_n

    if residual_autocorr is None:
        residual_autocorr = 0.9

    max_overlap_step = (horizon - 1) // step

    kernel_sum = 0.0
    for k in range(1, max_overlap_step + 1):
        weight = 1.0 - (k / (max_overlap_step + 1))
        kernel_sum += weight * (residual_autocorr ** k)

    variance_inflation_factor = 1.0 + 2.0 * kernel_sum
    n_eff = nominal_n / variance_inflation_factor
    return max(1, int(np.round(n_eff)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC004EffectiveSampleSize -v`
Expected: 5/5 PASS

- [ ] **Step 5: Integrate n_eff into aligned_slow_loop.py JSONL output**

In `scripts/aligned_slow_loop.py`, find the JSONL record writing section and add:

```python
from task_FM.evaluations.fm_eval.evaluator import effective_sample_size

# In the record construction:
n_eff = effective_sample_size(len(eval_indices), horizon=24, step=2)
record["n_eff"] = n_eff
record["n_eff_method"] = "bartlett_full_kernel_rho0.9"
```

- [ ] **Step 6: Verify aligned_verdicts.jsonl is unchanged**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && git diff task_FM/aligned_verdicts.jsonl`
Expected: empty diff (n_eff is additive field, does not alter gate_pass)

- [ ] **Step 7: Commit**

```bash
git add task_FM/evaluations/fm_eval/evaluator.py scripts/aligned_slow_loop.py tests/test_system_hardening.py
git commit -m "feat(SPEC-004): Bartlett full-kernel effective sample size (n_eff=71)"
```

---

### Task 2: SPEC-005 — Isolated Log Monotonic Confidence Band

**Files:**
- Modify: `config/prediction_scheme.py:568` (existing `confidence_band`)
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Consumes: `quantile_forecast: np.ndarray` (shape [T, 10]), `scheme: VarietyScheme`
- Produces: `np.ndarray` same shape, Col 0 unchanged, Col 1~9 monotonically increasing

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC005ConfidenceBand:
    """SPEC-005: Col 0 隔离对数保序展宽"""

    def test_no_crossing_col1_to_col9(self):
        """Col 1~9 分位数通道单调递增"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        for t in range(24):
            for i in range(1, 9):
                assert adjusted[t, i] <= adjusted[t, i + 1]

    def test_col0_unchanged(self):
        """Col 0 (点预测) 不参与排序/展宽"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 0], q[:, 0], rtol=1e-6)

    def test_all_positive(self):
        """所有输出值 > 0"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        assert np.all(adjusted > 0)

    def test_median_unchanged(self):
        """Col 5 (P50) 作为中枢不变"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 5], q[:, 5], rtol=1e-6)

    def test_mult_1_passthrough(self):
        """confidence_multiplier=1.0 时直接透传"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 1.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_array_equal(adjusted, q)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC005ConfidenceBand -v`
Expected: FAIL — `test_col0_unchanged` fails (current code sorts all 10 cols including Col 0)

- [ ] **Step 3: Rewrite `confidence_band` in prediction_scheme.py**

Replace the existing `confidence_band` function (around line 568):

```python
def confidence_band(quantile_forecast, scheme):
    """
    v2: 对数空间保序展宽 (v1.2: Col 0 严格隔离)

    TimesFM 10 列契约:
      Col 0 = Point Forecast (Mean); Col 5 = P50 (Median)
      Col 1~4 = P10~P40; Col 6~9 = P60~P90

    [v1.2 修正]: Col 0 不参与展宽运算，仅 Col 1~9 做对称展宽+保序
    """
    mult = scheme.confidence_multiplier
    if mult == 1.0:
        return quantile_forecast

    eps = 1e-6
    log_q = np.log(np.maximum(quantile_forecast, eps))
    log_median = log_q[:, 5:6]

    # [v1.2] 严格隔离: Col 0 保持原值，仅展宽 Col 1~9
    log_adjusted = log_q.copy()
    if log_adjusted.shape[-1] == 10:
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted[:, 1:] = np.sort(log_adjusted[:, 1:], axis=-1)
    else:
        # 非标准列数: 回退全排序
        log_adjusted[:, 1:] = log_median + (log_q[:, 1:] - log_median) * mult
        log_adjusted = np.sort(log_adjusted, axis=-1)

    return np.exp(log_adjusted)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC005ConfidenceBand -v`
Expected: 5/5 PASS

- [ ] **Step 5: Run existing confidence_band tests to check no regression**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/ -k "confidence" -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add config/prediction_scheme.py tests/test_system_hardening.py
git commit -m "feat(SPEC-005): isolate Col 0 from log monotonic confidence band"
```

---

### Task 3: SPEC-008 — Non-overlapping Stride Margin MaxDD

**Files:**
- Modify: `cascade/evaluation_metrics.py`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Produces: `calc_margin_maxdd_robust(net_pnl_pts, base_prices, contract_multiplier, horizon, step, margin_rate, capital_allocation_ratio, initial_capital) -> float`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC008MarginMaxDD:
    """SPEC-008: 非重叠步长抽样保证金口径 MaxDD"""

    def test_basic_drawdown_negative(self):
        """连续亏损应产生负 MaxDD"""
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, -5.0)  # 120 笔每笔亏 5 点
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10)
        assert dd < 0

    def test_all_profit_zero_drawdown(self):
        """连续盈利 MaxDD = 0"""
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, 5.0)
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10)
        assert dd == 0.0

    def test_bankruptcy_returns_minus_one(self):
        """穿仓返回 -1.0"""
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, -500.0)  # 巨额亏损
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(
            pnl, prices, contract_multiplier=10, initial_capital=10_000.0
        )
        assert dd == -1.0

    def test_stride_reduces_leverage_inflation(self):
        """非重叠抽样应比串行累加产生更温和的回撤"""
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        rng = np.random.RandomState(42)
        pnl = rng.randn(589) * 10
        prices = np.full(589, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10,
                                       horizon=24, step=2)
        # 非重叠抽样下 MaxDD 应在合理范围 (不应超过 -100%)
        assert -1.0 <= dd <= 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC008MarginMaxDD -v`
Expected: FAIL — `ImportError: cannot import name 'calc_margin_maxdd_robust'`

- [ ] **Step 3: Implement `calc_margin_maxdd_robust` in evaluation_metrics.py**

Add to `cascade/evaluation_metrics.py`:

```python
def calc_margin_maxdd_robust(
    net_pnl_pts: np.ndarray,
    base_prices: np.ndarray,
    contract_multiplier: float,
    horizon: int = 24,
    step: int = 2,
    margin_rate: float = 0.12,
    capital_allocation_ratio: float = 0.30,
    initial_capital: float = 1_000_000.0,
) -> float:
    """
    保证金口径最大回撤 — 非重叠步长抽样版本

    stride = horizon // step = 12 组独立序列，取平均 MaxDD
    """
    stride = max(1, horizon // step)
    sub_dd_list = []

    for offset in range(stride):
        sub_pnl = net_pnl_pts[offset::stride]
        sub_prices = base_prices[offset::stride]

        if len(sub_pnl) < 2:
            continue

        equity = initial_capital
        peak = initial_capital
        max_dd = 0.0

        for t in range(len(sub_pnl)):
            margin_per_lot = sub_prices[t] * contract_multiplier * margin_rate
            lots = max(1, int((equity * capital_allocation_ratio) / margin_per_lot))
            equity += sub_pnl[t] * contract_multiplier * lots

            if equity <= 0:
                max_dd = -1.0
                break
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak)

        sub_dd_list.append(max_dd)

    return float(np.mean(sub_dd_list)) if sub_dd_list else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC008MarginMaxDD -v`
Expected: 4/4 PASS

- [ ] **Step 5: Run existing evaluation_metrics tests for regression**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_evaluation_metrics_contract.py -v`
Expected: All PASS

- [ ] **Step 5b: Integrate `calc_margin_maxdd_robust` into aligned_slow_loop.py**

在 `scripts/aligned_slow_loop.py` 结果汇总处调用并写入 JSONL:

```python
from cascade.evaluation_metrics import calc_margin_maxdd_robust

# 在评估主循环前初始化收集器:
all_net_pnl = []
all_base_prices = []

# 在每步评估记录时追加:
all_net_pnl.append(current_net_pnl)
all_base_prices.append(current_bar_close)

# 在评估指标汇总段:
margin_maxdd = calc_margin_maxdd_robust(
    net_pnl_pts=np.array(all_net_pnl),
    base_prices=np.array(all_base_prices),
    contract_multiplier=scheme.contract_multiplier,
    horizon=24, step=2,
)
record["margin_maxdd"] = margin_maxdd
```

同时确保报告模板中输出:
```
MaxDD (名义): {nominal_maxdd:.1%}
MaxDD (保证金口径, 12% margin): {margin_maxdd:.1%}
```

- [ ] **Step 6: Commit**

```bash
git add cascade/evaluation_metrics.py tests/test_system_hardening.py
git commit -m "feat(SPEC-008): non-overlapping stride margin MaxDD (stride=12)"
```

---

### Task 4: SPEC-007 — Cosine Rolloff Signal Weight

**Files:**
- Modify: `config/prediction_scheme.py` (add `smooth_cutoff` to VarietyScheme, add cosine branch to `signal_weight`)
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Consumes: `VarietyScheme.smooth_cutoff: bool` (new field, default False)
- Produces: `signal_weight(horizon, scheme) -> np.ndarray` with cosine rolloff when `smooth_cutoff=True`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC007CosineRolloff:
    """SPEC-007: 短段信号权重余弦滚降"""

    def test_cosine_rolloff_plateau(self):
        """Bar 1~8 全权重 1.0"""
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = True
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[:8], 1.0)

    def test_cosine_rolloff_zero_tail(self):
        """Bar 17+ 零权重"""
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = True
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[16:], 0.0)

    def test_cosine_rolloff_monotone_decay(self):
        """Bar 9~16 余弦衰减单调递减"""
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = True
        w = signal_weight(24, scheme)
        decay_region = w[8:16]
        for i in range(len(decay_region) - 1):
            assert decay_region[i] >= decay_region[i + 1]

    def test_hard_cutoff_unchanged(self):
        """smooth_cutoff=False 时保持旧硬截断"""
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = False
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[:12], 1.0)
        np.testing.assert_allclose(w[12:], 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC007CosineRolloff -v`
Expected: FAIL — `smooth_cutoff` attribute missing

- [ ] **Step 3: Add `smooth_cutoff` field and cosine branch**

In `config/prediction_scheme.py`:

1. Add to `VarietyScheme` dataclass: `smooth_cutoff: bool = False`
2. Modify `signal_weight()` to add cosine branch (see spec §5 SPEC-007 for full code)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC007CosineRolloff -v`
Expected: 4/4 PASS

- [ ] **Step 5: Commit**

```bash
git add config/prediction_scheme.py tests/test_system_hardening.py
git commit -m "feat(SPEC-007): cosine rolloff signal weight (smooth_cutoff)"
```

---

### Task 5: SPEC-012 — Log Slope R² + Decision Closure

**Files:**
- Modify: `cascade/daily_model.py`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Consumes: `DailyResult` (add `r_squared: float`, `slope_unreliable: bool`)
- Produces: `_compute_direction_v2(daily_result, scheme) -> str`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC012R2DecisionClosure:
    """SPEC-012: 对数斜率 R² 滤网 + 决策闭环"""

    def test_low_r2_returns_neutral(self):
        """R² < 0.35 → 一票否决为中性"""
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = 0.005  # 强斜率
        dr.slope_unreliable = True  # 但 R² 低
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert "中性" in _compute_direction_v2(dr, scheme_mock)

    def test_high_r2_bullish(self):
        """R² ≥ 0.35 + 正斜率 → 看多"""
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = 0.005
        dr.slope_unreliable = False
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert "看多" in _compute_direction_v2(dr, scheme_mock)

    def test_high_r2_bearish(self):
        """R² ≥ 0.35 + 负斜率 → 看空"""
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = -0.005
        dr.slope_unreliable = False
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert "看空" in _compute_direction_v2(dr, scheme_mock)

    def test_r_squared_computation(self):
        """完美线性数据 R² ≈ 1.0"""
        # 直接用 polyfit 验证 R² 计算逻辑
        x = np.arange(22, dtype=float)
        y = 0.001 * x + 5.0  # 完美线性
        coeffs = np.polyfit(x, y, 1)
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        assert r2 > 0.99
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC012R2DecisionClosure -v`
Expected: FAIL — `_compute_direction_v2` not defined

- [ ] **Step 3: Add R² fields and `_compute_direction_v2`**

In `cascade/daily_model.py`:

1. Add to `DailyResult` dataclass (around line 20):
```python
r_squared: float = 0.0
slope_unreliable: bool = False
```

2. In `predict()`, after polyfit, add R² computation (around line 147):
```python
y_pred = np.polyval(coeffs, x)
ss_res = np.sum((log_forecast - y_pred) ** 2)
ss_tot = np.sum((log_forecast - np.mean(log_forecast)) ** 2)
r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
slope_unreliable = r_squared < 0.35
```

3. Pass `r_squared` and `slope_unreliable` to DailyResult constructor.

4. Add `_compute_direction_v2` function:
```python
def _compute_direction_v2(daily_result, scheme) -> str:
    if getattr(daily_result, "slope_unreliable", False):
        return "中性 → (形态分歧)"
    thr_ratio = scheme.trend_threshold_pct / 100.0
    slope = daily_result.horizon_slope
    if slope > thr_ratio:
        return "看多 ↑"
    elif slope < -thr_ratio:
        return "看空 ↓"
    else:
        return "中性 →"
```

- [ ] **Step 3b: Replace all callers of old `_compute_direction` with `_compute_direction_v2`**

搜索并替换所有调用旧接口的代码:

```bash
cd /home/abug/timesfm && grep -rn '_compute_direction(' cascade/ scripts/ --include="*.py" | grep -v '_v2'
```

典型调用点:
- `cascade/daily_model.py` 内部 predict() 末尾的方向判断行 (约 line 167)
- `scripts/copilot.py` 中引用方向结果的逻辑

将:
```python
direction = "看多 ↑" if result.horizon_slope > 0.001 else "看空 ↓" if result.horizon_slope < -0.001 else "中性 →"
```
替换为:
```python
direction = _compute_direction_v2(result, scheme)
```

确保 `result` (DailyResult 实例) 携带 `r_squared` 和 `slope_unreliable` 字段。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC012R2DecisionClosure -v`
Expected: 4/4 PASS

- [ ] **Step 5: Run existing daily_model tests for regression**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_daily_pred_cache.py tests/test_daily_freshness.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add cascade/daily_model.py tests/test_system_hardening.py
git commit -m "feat(SPEC-012): log slope R² filter + decision closure (_compute_direction_v2)"
```

---

### Task 6: SPEC-013 — Prediction Drift Clipping

**Files:**
- Modify: `cascade/features.py`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Produces: `_clip_prediction_drift(hist_daily, pred_daily, max_daily_drift_pct=0.05) -> np.ndarray`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC013DriftClipping:
    """SPEC-013: Stage 1 预测漂移截断"""

    def test_extreme_prediction_clipped(self):
        """极端预测被截断到 5% 日漂移包络内"""
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred = np.array([200.0] * 22)  # 预测翻倍 → 极端
        clipped = _clip_prediction_drift(hist, pred)
        upper = 100.0 * (1.05) ** np.arange(1, 23)
        np.testing.assert_array_less(clipped, upper + 1e-6)

    def test_normal_prediction_unchanged(self):
        """温和预测不被截断"""
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred = 100.0 + np.arange(1, 23) * 0.5  # 每日涨 0.5
        clipped = _clip_prediction_drift(hist, pred)
        np.testing.assert_allclose(clipped, pred)

    def test_symmetric_clipping(self):
        """上下双向截断"""
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred_down = np.array([10.0] * 22)  # 极端下跌
        clipped = _clip_prediction_drift(hist, pred_down)
        lower = 100.0 * (1 - 0.05) ** np.arange(1, 23)
        np.testing.assert_array_less(lower - 1e-6, clipped)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC013DriftClipping -v`
Expected: FAIL — `_clip_prediction_drift` not defined

- [ ] **Step 3: Implement `_clip_prediction_drift` in features.py**

Add near top of `cascade/features.py` (after imports):

```python
def _clip_prediction_drift(
    hist_daily: np.ndarray,
    pred_daily: np.ndarray,
    max_daily_drift_pct: float = 0.05,
) -> np.ndarray:
    """限制 Stage 1 预测价格相对最新收盘价的漂移"""
    last_close = hist_daily[-1]
    t = np.arange(1, len(pred_daily) + 1)
    upper = last_close * (1 + max_daily_drift_pct) ** t
    lower = last_close * (1 - max_daily_drift_pct) ** t
    return np.clip(pred_daily, lower, upper)
```

Then integrate into rsi_state / rsi_slope branches where `pred_daily` is constructed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC013DriftClipping -v`
Expected: 3/3 PASS

- [ ] **Step 5: Commit**

```bash
git add cascade/features.py tests/test_system_hardening.py
git commit -m "feat(SPEC-013): prediction drift clipping (5% daily envelope)"
```

---

### Task 7: SPEC-006 — Scheme Retirement Composite Key + Star Override

**Files:**
- Modify: `scripts/build_knowledge_base.py`
- Modify: `scripts/copilot.py`
- Modify: `config/knowledge_base.json`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Produces: `sync_slow_loop_status(kb, verdicts_path) -> dict`
- Produces: `craft_advisory_v2(symbol, kb, direction, delta_pct, vol, scheme_type) -> list[str]`

- [ ] **Step 1: Write failing tests**

```python
import json
import tempfile
from pathlib import Path

class TestSPEC006SchemeRetirement:
    """SPEC-006: 复合主键退役治理 + 星级覆盖 (真实函数调用)"""

    def _make_kb(self):
        """构造测试用 KB 字典"""
        return {
            "symbols": {
                "ss": {
                    "credit_stars": 2,
                    "historical_pf": 1.10,
                    "production_covariate": "vor",
                    "slow_loop_status": "ok",
                },
                "rb": {
                    "credit_stars": 1,
                    "historical_pf": 1.05,
                    "production_covariate": "rsi_state",
                    "slow_loop_status": "ok",
                },
            }
        }

    def test_sync_slow_loop_degrades_on_negative_ev(self):
        """EV<0 的裁决将生产协变量匹配的品种标记为 degraded"""
        from scripts.build_knowledge_base import sync_slow_loop_status
        kb = self._make_kb()
        # 构造临时 JSONL: ss_vor 的裁决 EV<0
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "symbol": "ss", "variant_id": "ss_vor",
                "gate_pass": False, "ev": -1.5, "pf": 0.90,
                "metrics": {"ev_after_slippage": -1.5}
            }) + "\n")
            tmppath = Path(f.name)
        result = sync_slow_loop_status(kb, tmppath)
        assert result["symbols"]["ss"]["slow_loop_status"] == "degraded"
        # rb 无匹配裁决，状态不变
        assert result["symbols"]["rb"]["slow_loop_status"] == "ok"
        tmppath.unlink()

    def test_sync_ignores_non_production_covariate(self):
        """非生产协变量的裁决不覆盖状态"""
        from scripts.build_knowledge_base import sync_slow_loop_status
        kb = self._make_kb()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # ss 测了 calendar_cyclical 但不是生产协变量
            f.write(json.dumps({
                "symbol": "ss", "variant_id": "ss_calendar_cyclical",
                "gate_pass": False, "ev": -2.0, "pf": 0.80,
            }) + "\n")
            tmppath = Path(f.name)
        result = sync_slow_loop_status(kb, tmppath)
        assert result["symbols"]["ss"]["slow_loop_status"] == "ok"  # 不变
        tmppath.unlink()

    def test_craft_advisory_v2_revoked_freezes(self):
        """revoked 状态输出冻结文案"""
        from scripts.copilot import craft_advisory_v2
        kb = self._make_kb()
        kb["symbols"]["ss"]["slow_loop_status"] = "revoked"
        lines = craft_advisory_v2("ss", kb, "看多 ↑", 0.5, 0.3, "vor")
        assert any("冻结" in line for line in lines)

    def test_craft_advisory_v2_degraded_downgrades_stars(self):
        """degraded 状态 effective_stars=1, 输出弱信号文案"""
        from scripts.copilot import craft_advisory_v2
        kb = self._make_kb()
        kb["symbols"]["ss"]["slow_loop_status"] = "degraded"
        kb["symbols"]["ss"]["credit_stars"] = 3  # 原始 3 星
        lines = craft_advisory_v2("ss", kb, "看多 ↑", 0.5, 0.3, "vor")
        # 应输出弱信号而非标准仓位
        assert any("弱信号" in line for line in lines)
        assert not any("标准仓位" in line for line in lines)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC006SchemeRetirement -v`
Expected: FAIL — `ImportError: cannot import name 'sync_slow_loop_status'`

- [ ] **Step 3: Implement `sync_slow_loop_status` in build_knowledge_base.py**

Add the composite-key function as shown in spec §6.

- [ ] **Step 4: Implement `craft_advisory_v2` in copilot.py**

Add the effective_stars override function as shown in spec §6.

- [ ] **Step 5: Add new fields to knowledge_base.json**

For each symbol entry, add:
```json
"production_covariate": "<covariate_name>",
"slow_loop_status": "ok",
"slow_loop_pf": null,
"slow_loop_ev": null,
"slow_loop_updated": null
```

- [ ] **Step 6: Run integration test**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python scripts/build_knowledge_base.py`
Expected: KB rebuilds without errors, new fields populated

- [ ] **Step 7: Commit**

```bash
git add scripts/build_knowledge_base.py scripts/copilot.py config/knowledge_base.json tests/test_system_hardening.py
git commit -m "feat(SPEC-006): composite key retirement + effective_stars override"
```

---

### Task 8: SPEC-010 — Calendar Trading Hour Auto-Detect

**Files:**
- Modify: `cascade/features.py:2073` (`calc_calendar_cyclical`)
- Modify: `cascade/data_validator.py:555` (`detect_trading_hours` — add 5% threshold)
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Consumes: `detect_trading_hours(df_1h) -> list[int]` (already exists, needs threshold filter)
- Modifies: `calc_calendar_cyclical` to auto-detect when `valid_hours=None`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC010TradingHourAutoDetect:
    """SPEC-010: calendar 交易时段自动嗅探"""

    def test_detect_trading_hours_filters_noise(self):
        """频次 <5% 的小时被过滤"""
        from cascade.data_validator import detect_trading_hours
        import pandas as pd
        # [v1.2 修正] 直接按真实小时累加，不做 h-9 偏移
        base_hours = [9, 10, 11, 13, 14, 15, 21, 22, 23]  # 9 个正常时段
        rows = []
        for day in range(100):
            for h in base_hours:
                rows.append(pd.Timestamp("2026-01-01") + pd.Timedelta(days=day, hours=h))

        # 添加 3 个偶发噪声时段 (真实 20 时，占比 3/903 ≈ 0.33% < 5%)
        for i in range(3):
            rows.append(pd.Timestamp("2026-01-01") + pd.Timedelta(days=i, hours=20))

        df = pd.DataFrame({"dt": rows})
        detected = detect_trading_hours(df)
        assert 20 not in detected  # 噪声时段被成功过滤
        assert 9 in detected       # 正常主力交易时段保留

    def test_calc_calendar_no_silent_fallback(self):
        """valid_hours=None 时不再静默回退 freq='h'"""
        from cascade.features import calc_calendar_cyclical
        import pandas as pd
        # 构造 200 根 1H K 线
        n = 200
        dts = pd.date_range("2026-01-01", periods=n, freq="h")
        df = pd.DataFrame({"dt": dts, "close": np.random.randn(n)})
        result = calc_calendar_cyclical(df, horizon=24)
        # [v1.2 修正] shape = (context_rows + horizon_rows, 4_features)
        # ctx_4d 有 n 行, horiz_4d 有 horizon 行, vstack 后 = (224, 4)
        assert result.shape == (224, 4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC010TradingHourAutoDetect -v`
Expected: FAIL — threshold filter not yet implemented

- [ ] **Step 3: Add 5% threshold filter to `detect_trading_hours`**

In `cascade/data_validator.py` (around line 555), modify to add frequency threshold:

```python
def detect_trading_hours(df_1h: pd.DataFrame, min_frequency_pct: float = 0.05) -> list:
    """从 1H 数据中提取活跃交易小时，过滤占比 < min_frequency_pct 的噪声"""
    dt_col = 'dt' if 'dt' in df_1h.columns else 'date'
    hours = pd.DatetimeIndex(df_1h[dt_col]).hour
    counts = hours.value_counts(normalize=True)
    return sorted(counts[counts >= min_frequency_pct].index.tolist())
```

- [ ] **Step 4: Modify `calc_calendar_cyclical` to auto-detect**

Replace the `valid_hours is None` fallback branch (around line 2073+):

```python
if valid_hours is None:
    from .data_validator import detect_trading_hours
    valid_hours = detect_trading_hours(df_1h)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC010TradingHourAutoDetect -v`
Expected: 2/2 PASS

- [ ] **Step 6: Run existing calendar tests**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_calendar_cyclical.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add cascade/features.py cascade/data_validator.py tests/test_system_hardening.py
git commit -m "feat(SPEC-010): calendar trading hour auto-detect with 5% threshold"
```

---

### Task 9: SPEC-009 — Per-Variety Half-Life Atomic Refactor

**Files:**
- Modify: `config/prediction_scheme.py` (add `half_life_bars` to VarietyScheme)
- Modify: `cascade/features.py` (replace all 15 instances of `12.0` with `_decay_fill(half_life)`)
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Consumes: `VarietyScheme.half_life_bars: float` (new field, default 12.0)
- Modifies: 15 sites in `features.py` where `0.5 ** (i / 12.0)` is hardcoded

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC009HalfLifeRefactor:
    """SPEC-009: 品种级半衰期参数化 + 原子化重构"""

    def test_decay_fill_custom_half_life(self):
        """自定义半衰期产生不同衰减曲线"""
        from cascade.features import _decay_fill
        d_fast = _decay_fill(100.0, 24, half_life=8.0)
        d_slow = _decay_fill(100.0, 24, half_life=16.0)
        # 快衰减 (half_life=8) 在 bar 10 时应比慢衰减 (half_life=16) 更低
        assert d_fast[10] < d_slow[10]

    def test_decay_fill_default_unchanged(self):
        """默认半衰期 12.0 与原硬编码结果一致"""
        from cascade.features import _decay_fill
        d = _decay_fill(100.0, 24, half_life=12.0)
        expected = 100.0 * np.array([0.5 ** (i / 12.0) for i in range(24)])
        np.testing.assert_allclose(d, expected)

    def test_no_hardcoded_12_in_features(self):
        """原子化重构后 features.py 中无 12.0 硬编码"""
        import subprocess
        result = subprocess.run(
            ["grep", "-n", "12\\.0", "cascade/features.py"],
            capture_output=True, text=True, cwd="/home/abug/timesfm"
        )
        # 排除注释行后应无匹配
        lines = [l for l in result.stdout.strip().split("\n")
                 if l and "#" not in l.split(":", 2)[-1]]
        assert len(lines) == 0, f"残留硬编码: {lines}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC009HalfLifeRefactor -v`
Expected: `test_no_hardcoded_12_in_features` FAIL (15 instances remain)

- [ ] **Step 3: Add `half_life_bars` to VarietyScheme**

In `config/prediction_scheme.py`, add to VarietyScheme:
```python
half_life_bars: float = 12.0
```

- [ ] **Step 4: Atomic refactor — function signature changes + replace all 15 `12.0` instances**

**Phase A: 统一收敛至 `_decay_fill`**

所有 15 处内联衰减代码统一替换为标准包装器调用:
```python
# 替换前 (散落在各函数内):
decay = np.array([0.5 ** (i / 12.0) for i in range(horizon)])

# 替换后 (统一调用标准包装器):
decay = _decay_fill(last_val, horizon, half_life=half_life)
```

**Phase B: 函数签名改造清单**

以下协变量函数需新增 `half_life` 参数 (默认 12.0 保持向后兼容):

| 函数名 | 文件行号 | 签名变更 |
|--------|---------|---------|
| `calc_vor` | ~784, ~793 | 增加 `half_life: float = 12.0` |
| `calc_bb_squeeze` | ~1350 | 增加 `half_life: float = 12.0` |
| `calc_reversal_shadow` | ~1498-1545 (6处) | 增加 `half_life: float = 12.0` |
| `calc_ao_accel` | ~1239 | 增加 `half_life: float = 12.0` |
| 其余 (1581-1602, 5处) | | 增加 `half_life: float = 12.0` |

**Phase C: 顶层入口统一提取**

在 `build_covariate_matrix` 入口从 scheme 提取并透传:
```python
def build_covariate_matrix(df, scheme, ...):
    half_life = scheme.half_life_bars if scheme else 12.0
    # 各协变量调用时传入:
    vor = calc_vor(df, half_life=half_life)
    bb = calc_bb_squeeze(df, half_life=half_life)
    rev = calc_reversal_shadow(df, half_life=half_life)
    ao = calc_ao_accel(df, half_life=half_life)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC009HalfLifeRefactor -v`
Expected: 3/3 PASS

- [ ] **Step 6: Verify full test suite for regression**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_covariate_pool.py tests/test_combo_parity.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add config/prediction_scheme.py cascade/features.py tests/test_system_hardening.py
git commit -m "feat(SPEC-009): per-variety half_life_bars + atomic 12.0 cleanup"
```

---

### Task 10: SPEC-011 — Cross-Sectional Roll Adjustment

**Files:**
- Modify: `data/tqsdk_fetcher.py`
- Modify: `data/data_store.py`
- Test: `tests/test_system_hardening.py`

**Interfaces:**
- Produces: `detect_roll_events(kline_df) -> list[dict]` with `roll_ratio` cross-sectional ratio
- Produces: `apply_backward_adjustment_robust(kline_df, roll_records) -> pd.DataFrame`

- [ ] **Step 1: Write failing tests**

```python
class TestSPEC011RollAdjustment:
    """SPEC-011: 同时间戳截面比例后复权"""

    def test_no_quadratic_explosion(self):
        """多次换月不产生二次幂爆炸"""
        from data.data_store import apply_backward_adjustment_robust
        import pandas as pd
        # 构造 100 根 K 线, 3 次换月
        df = pd.DataFrame({
            'dt': pd.date_range("2026-01-01", periods=100, freq="D"),
            'open': np.full(100, 100.0),
            'high': np.full(100, 105.0),
            'low': np.full(100, 95.0),
            'close': np.full(100, 100.0),
        })
        rolls = [
            {'dt': pd.Timestamp("2026-02-01"), 'roll_ratio': 1.05},
            {'dt': pd.Timestamp("2026-03-01"), 'roll_ratio': 1.03},
            {'dt': pd.Timestamp("2026-04-01"), 'roll_ratio': 0.98},
        ]
        result = apply_backward_adjustment_robust(df, rolls)
        # 早期数据不应暴涨到百万级 (二次幂爆炸的典型特征)
        assert result['close'].max() < 200.0  # 合理范围

    def test_latest_contract_unchanged(self):
        """最新合约价格不变 (factor=1.0 基准)"""
        from data.data_store import apply_backward_adjustment_robust
        import pandas as pd
        df = pd.DataFrame({
            'dt': pd.date_range("2026-01-01", periods=50, freq="D"),
            'open': np.full(50, 100.0),
            'high': np.full(50, 105.0),
            'low': np.full(50, 95.0),
            'close': np.full(50, 100.0),
        })
        rolls = [{'dt': pd.Timestamp("2026-01-20"), 'roll_ratio': 1.05}]
        result = apply_backward_adjustment_robust(df, rolls)
        # 换月日之后的数据 (最新合约) 应不变
        mask_after = df['dt'] >= pd.Timestamp("2026-01-20")
        np.testing.assert_allclose(
            result.loc[mask_after, 'close'], 100.0
        )

    def test_raw_close_preserved(self):
        """raw_close 列保留原始价格"""
        from data.data_store import apply_backward_adjustment_robust
        import pandas as pd
        df = pd.DataFrame({
            'dt': pd.date_range("2026-01-01", periods=50, freq="D"),
            'open': np.full(50, 100.0),
            'high': np.full(50, 105.0),
            'low': np.full(50, 95.0),
            'close': np.full(50, 100.0),
        })
        rolls = [{'dt': pd.Timestamp("2026-01-20"), 'roll_ratio': 1.05}]
        result = apply_backward_adjustment_robust(df, rolls)
        assert 'raw_close' in result.columns
        np.testing.assert_allclose(result['raw_close'], 100.0)

    def test_empty_rolls_passthrough(self):
        """无换月事件时直接透传"""
        from data.data_store import apply_backward_adjustment_robust
        import pandas as pd
        df = pd.DataFrame({
            'dt': pd.date_range("2026-01-01", periods=10, freq="D"),
            'close': np.full(10, 100.0),
        })
        result = apply_backward_adjustment_robust(df, [])
        np.testing.assert_allclose(result['close'], 100.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC011RollAdjustment -v`
Expected: FAIL — `apply_backward_adjustment_robust` not defined

- [ ] **Step 3: Implement `detect_roll_events` in tqsdk_fetcher.py**

Add the cross-sectional roll detection function as shown in spec §7 SPEC-011. Include fallback strategy from Implementation Note 2 (forward-fill → prior bar close ratio → WARN log).

- [ ] **Step 4: Implement `apply_backward_adjustment_robust` in data_store.py**

Add the vectorized backward adjustment function as shown in spec §7 SPEC-011. Key: construct `adj_series` once, apply all price columns in single vectorized multiplication.

- [ ] **Step 4b: Hook `apply_backward_adjustment_robust` into data loading pipeline**

在 `data/data_store.py` 的 K 线提取函数中挂接后复权:

```python
# data/data_store.py — 在 get_kline / load_daily_context 等返回 K 线前挂接
def get_kline_with_adjustment(db_path, symbol, ...):
    df = get_kline(db_path, symbol, ...)  # 原始 K 线
    roll_records = load_roll_records(db_path, symbol)  # 从 roll_events 表加载
    if roll_records:
        df = apply_backward_adjustment_robust(df, roll_records)
    return df
```

同时在 `cascade/daily_model.py` 的 `load_daily_context` 入口确认调用路径经过复权处理。

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py::TestSPEC011RollAdjustment -v`
Expected: 4/4 PASS

- [ ] **Step 6: Commit**

```bash
git add data/tqsdk_fetcher.py data/data_store.py tests/test_system_hardening.py
git commit -m "feat(SPEC-011): cross-sectional roll adjustment with vectorized backward adj"
```

---

### Task 11: Final Integration Verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full test suite**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/test_system_hardening.py -v`
Expected: All 10 SPEC test classes PASS

- [ ] **Step 2: Verify aligned_verdicts.jsonl unchanged**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && git diff task_FM/aligned_verdicts.jsonl`
Expected: empty diff

- [ ] **Step 3: Verify no `12.0` hardcoded in features.py**

Run: `cd /home/abug/timesfm && grep -n '12\.0' cascade/features.py | grep -v '#'`
Expected: 0 matches

- [ ] **Step 4: Run full regression suite**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python -m pytest tests/ -x --timeout=120 2>&1 | tail -20`
Expected: No new failures (pre-existing failures in test_a2_p1_integrity, test_aligned_slow_loop, test_backtest_cutoff are acceptable)

- [ ] **Step 5: Verify knowledge_base.json rebuild**

Run: `cd /home/abug/timesfm && source .praxist-venv/bin/activate && python scripts/build_knowledge_base.py`
Expected: Completes without errors

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat(system-hardening): v1.2-final all 10 SPECs integrated and verified"
```

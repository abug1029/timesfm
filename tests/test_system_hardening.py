import numpy as np
import pytest
from task_FM.evaluations.fm_eval.evaluator import effective_sample_size


class TestSPEC004EffectiveSampleSize:
    """SPEC-004: Bartlett full-kernel effective sample size"""

    def test_default_rho09_returns_71(self):
        """H=24, S=2, K=11, VIF~8.237 -> n_eff=71"""
        assert effective_sample_size(589, 24, 2) == 71

    def test_no_overlap_returns_nominal(self):
        assert effective_sample_size(100, 24, 24) == 100

    def test_monotonicity_higher_rho_lower_neff(self):
        n_high = effective_sample_size(589, 24, 2, 0.9)
        n_low = effective_sample_size(589, 24, 2, 0.5)
        assert n_high < n_low

    def test_rho05_range(self):
        n_eff = effective_sample_size(589, 24, 2, 0.5)
        assert 120 <= n_eff <= 250

    def test_minimum_is_one(self):
        assert effective_sample_size(1, 24, 2) >= 1


class TestSPEC005ConfidenceBand:
    """SPEC-005: Col 0 isolated log monotonic confidence band"""

    def test_no_crossing_col1_to_col9(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        for t in range(24):
            for i in range(1, 9):
                assert adjusted[t, i] <= adjusted[t, i + 1]

    def test_col0_unchanged(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 0], q[:, 0], rtol=1e-6)

    def test_all_positive(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        assert np.all(adjusted > 0)

    def test_median_unchanged(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 5], q[:, 5], rtol=1e-6)

    def test_mult_1_passthrough(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 1.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_array_equal(adjusted, q)

    def test_nonstandard_cols_col0_preserved(self):
        """Non-10-col input (7 cols) must still isolate Col 0"""
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 0], q[:, 0], rtol=1e-6)


class TestSPEC008MarginMaxDD:
    """SPEC-008: Non-overlapping stride margin MaxDD"""

    def test_basic_drawdown_negative(self):
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, -5.0)
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10)
        assert dd < 0

    def test_all_profit_zero_drawdown(self):
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, 5.0)
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10)
        assert dd == 0.0

    def test_bankruptcy_returns_minus_one(self):
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        pnl = np.full(120, -500.0)
        prices = np.full(120, 3600.0)
        dd = calc_margin_maxdd_robust(
            pnl, prices, contract_multiplier=10, initial_capital=10_000.0
        )
        assert dd == -1.0

    def test_stride_reduces_leverage_inflation(self):
        from cascade.evaluation_metrics import calc_margin_maxdd_robust
        rng = np.random.RandomState(42)
        pnl = rng.randn(589) * 10
        prices = np.full(589, 3600.0)
        dd = calc_margin_maxdd_robust(pnl, prices, contract_multiplier=10,
                                       horizon=24, step=2)
        assert -1.0 <= dd <= 0.0


class TestSPEC007CosineRolloff:
    """SPEC-007: Cosine rolloff signal weight"""

    def test_cosine_rolloff_plateau(self):
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = True
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[:8], 1.0)

    def test_cosine_rolloff_zero_tail(self):
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = True
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[16:], 0.0)

    def test_cosine_rolloff_monotone_decay(self):
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
        from config.prediction_scheme import signal_weight, VarietyScheme
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.use_full_signal = False
        scheme.short_horizon_only = True
        scheme.smooth_cutoff = False
        w = signal_weight(24, scheme)
        np.testing.assert_allclose(w[:12], 1.0)
        np.testing.assert_allclose(w[12:], 0.0)


class TestSPEC012R2DecisionClosure:
    """SPEC-012: Log slope R² filter + decision closure"""

    def test_low_r2_returns_neutral(self):
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = 0.005
        dr.slope_unreliable = True
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert '中性' in _compute_direction_v2(dr, scheme_mock)

    def test_high_r2_bullish(self):
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = 0.005
        dr.slope_unreliable = False
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert '看多' in _compute_direction_v2(dr, scheme_mock)

    def test_high_r2_bearish(self):
        from cascade.daily_model import _compute_direction_v2, DailyResult
        dr = DailyResult.__new__(DailyResult)
        dr.horizon_slope = -0.005
        dr.slope_unreliable = False
        scheme_mock = type('S', (), {'trend_threshold_pct': 0.1})()
        assert '看空' in _compute_direction_v2(dr, scheme_mock)

    def test_r_squared_computation(self):
        x = np.arange(22, dtype=float)
        y = 0.001 * x + 5.0
        coeffs = np.polyfit(x, y, 1)
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        assert r2 > 0.99


class TestSPEC013DriftClipping:
    """SPEC-013: Stage 1 prediction drift clipping."""

    def test_extreme_prediction_clipped(self):
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred = np.array([200.0] * 22)
        clipped = _clip_prediction_drift(hist, pred)
        upper = 100.0 * (1.05) ** np.arange(1, 23)
        assert np.all(clipped <= upper + 1e-6)

    def test_normal_prediction_unchanged(self):
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred = 100.0 + np.arange(1, 23) * 0.5
        clipped = _clip_prediction_drift(hist, pred)
        np.testing.assert_allclose(clipped, pred)

    def test_symmetric_clipping(self):
        from cascade.features import _clip_prediction_drift
        hist = np.array([100.0])
        pred_down = np.array([10.0] * 22)
        clipped = _clip_prediction_drift(hist, pred_down)
        lower = 100.0 * (1 - 0.05) ** np.arange(1, 23)
        assert np.all(clipped >= lower - 1e-6)

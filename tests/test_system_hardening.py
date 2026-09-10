import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
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


class TestSPEC006SchemeRetirement:
    """SPEC-006: Composite key retirement + star override (real function calls)"""

    def _make_kb(self):
        return {
            "symbols": {
                "ss": {
                    "credit_stars": 2, "historical_pf": 1.10,
                    "production_covariate": "vor", "slow_loop_status": "ok",
                },
                "rb": {
                    "credit_stars": 1, "historical_pf": 1.05,
                    "production_covariate": "rsi_state", "slow_loop_status": "ok",
                },
            }
        }

    def test_sync_degrades_on_negative_ev(self):
        from scripts.build_knowledge_base import sync_slow_loop_status
        kb = self._make_kb()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "symbol": "ss", "variant_id": "ss_vor",
                "gate_pass": False, "ev": -1.5, "pf": 0.90,
                "metrics": {"ev_after_slippage": -1.5}
            }) + "\n")
            tmppath = Path(f.name)
        result = sync_slow_loop_status(kb, tmppath)
        assert result["symbols"]["ss"]["slow_loop_status"] == "degraded"
        assert result["symbols"]["rb"]["slow_loop_status"] == "ok"
        tmppath.unlink()

    def test_sync_ignores_non_production_covariate(self):
        from scripts.build_knowledge_base import sync_slow_loop_status
        kb = self._make_kb()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "symbol": "ss", "variant_id": "ss_calendar_cyclical",
                "gate_pass": False, "ev": -2.0, "pf": 0.80,
            }) + "\n")
            tmppath = Path(f.name)
        result = sync_slow_loop_status(kb, tmppath)
        assert result["symbols"]["ss"]["slow_loop_status"] == "ok"
        tmppath.unlink()

    def test_craft_advisory_revoked_freezes(self):
        from scripts.copilot import craft_advisory_v2
        kb = self._make_kb()
        kb["symbols"]["ss"]["slow_loop_status"] = "revoked"
        lines = craft_advisory_v2("ss", kb, "看多 ↑", 0.5, 0.3, "vor")
        assert any("冻结" in line for line in lines)

    def test_craft_advisory_degraded_downgrades_stars(self):
        from scripts.copilot import craft_advisory_v2
        kb = self._make_kb()
        kb["symbols"]["ss"]["slow_loop_status"] = "degraded"
        kb["symbols"]["ss"]["credit_stars"] = 3
        lines = craft_advisory_v2("ss", kb, "看多 ↑", 0.5, 0.3, "vor")
        assert any("弱信号" in line for line in lines)
        assert not any("标准仓位" in line for line in lines)

    def test_build_includes_new_fields(self):
        """Integration test: build() must produce all 5 new SPEC-006 fields."""
        from scripts.build_knowledge_base import build
        from config.prediction_scheme import SCHEMES
        # Use a dummy l1_path that does not exist (build handles missing gracefully)
        kb = build(Path("/nonexistent/ECONOMIC_VERDICT.json"))
        assert len(kb["symbols"]) > 0, "build() produced no symbols"
        for sym, entry in kb["symbols"].items():
            assert "production_covariate" in entry, f"{sym} missing production_covariate"
            assert "slow_loop_status" in entry, f"{sym} missing slow_loop_status"
            assert "slow_loop_pf" in entry, f"{sym} missing slow_loop_pf"
            assert "slow_loop_ev" in entry, f"{sym} missing slow_loop_ev"
            assert "slow_loop_updated" in entry, f"{sym} missing slow_loop_updated"
        # Verify production_covariate matches SCHEMES primary covariate
        for sym in SCHEMES:
            scheme = SCHEMES[sym]
            expected = (scheme.covariate_types or [scheme.covariate_type])[0]
            assert kb["symbols"][sym]["production_covariate"] == expected, (
                f"{sym}: expected {expected}, got {kb[symbols][sym][production_covariate]}"
            )


class TestSPEC010TradingHourAutoDetect:
    """SPEC-010: Calendar trading hour auto-detect with 5% threshold"""

    def test_detect_trading_hours_filters_noise(self):
        """Noise hour (0.3%) should be filtered; real trading hour (11.1%) should pass."""
        from cascade.data_validator import detect_trading_hours
        import pandas as pd

        base_hours = [9, 10, 11, 13, 14, 15, 21, 22, 23]
        rows = []
        for day in range(100):
            for h in base_hours:
                rows.append(pd.Timestamp("2026-01-01") + pd.Timedelta(days=day, hours=h))
        # Add noise: hour 20 appears only 3 times (0.3%)
        for i in range(3):
            rows.append(pd.Timestamp("2026-01-01") + pd.Timedelta(days=i, hours=20))

        df = pd.DataFrame({"dt": rows})
        detected = detect_trading_hours(df)
        assert 20 not in detected, f"Noise hour 20 should be filtered, got {detected}"
        assert 9 in detected, f"Real trading hour 9 should be detected, got {detected}"

    def test_calc_calendar_no_silent_fallback(self):
        """calc_calendar_cyclical should auto-detect trading hours when valid_hours=None."""
        from cascade.features import calc_calendar_cyclical
        import pandas as pd
        import numpy as np

        n = 200
        dts = pd.date_range("2026-01-01", periods=n, freq="h")
        df = pd.DataFrame({"dt": dts, "close": np.random.randn(n)})
        result = calc_calendar_cyclical(df, horizon=24)
        assert result.shape == (224, 4), f"Expected (224, 4), got {result.shape}"


class TestSPEC009HalfLifeRefactor:
    """SPEC-009: Per-variety half-life + atomic refactor"""

    def test_decay_fill_custom_half_life(self):
        from cascade.features import _decay_fill
        d_fast = _decay_fill(100.0, 24, half_life=8.0)
        d_slow = _decay_fill(100.0, 24, half_life=16.0)
        assert d_fast[10] < d_slow[10]

    def test_decay_fill_default_unchanged(self):
        import numpy as np
        from cascade.features import _decay_fill
        d = _decay_fill(100.0, 24, half_life=12.0)
        expected = 100.0 * np.array([0.5 ** (i / 12.0) for i in range(24)])
        np.testing.assert_allclose(d, expected)

    def test_no_hardcoded_12_in_features(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-n", "12\\.0", "cascade/features.py"],
            capture_output=True, text=True, cwd="/home/abug/timesfm"
        )
        lines = [l for l in result.stdout.strip().split("\n")
                 if l and "#" not in l.split(":", 2)[-1]]
        # Only function signature defaults should remain (half_life: float = 12.0)
        non_sig = [l for l in lines if "half_life" not in l]
        assert len(non_sig) == 0, f"Remaining hardcoded: {non_sig}"


class TestSPEC011RollAdjustment:
    """SPEC-011: Cross-sectional roll adjustment with vectorized backward adj."""

    def test_no_quadratic_explosion(self):
        from data.data_store import apply_backward_adjustment_robust
        df = pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=100, freq="D"),
            "open": np.full(100, 100.0),
            "high": np.full(100, 105.0),
            "low": np.full(100, 95.0),
            "close": np.full(100, 100.0),
        })
        rolls = [
            {"dt": pd.Timestamp("2026-02-01"), "roll_ratio": 1.05},
            {"dt": pd.Timestamp("2026-03-01"), "roll_ratio": 1.03},
            {"dt": pd.Timestamp("2026-04-01"), "roll_ratio": 0.98},
        ]
        result = apply_backward_adjustment_robust(df, rolls)
        # 100 * 1.05 * 1.03 * 0.98 = 106.027 < 200
        assert result["close"].max() < 200.0

    def test_latest_contract_unchanged(self):
        df = pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=50, freq="D"),
            "open": np.full(50, 100.0),
            "high": np.full(50, 105.0),
            "low": np.full(50, 95.0),
            "close": np.full(50, 100.0),
        })
        from data.data_store import apply_backward_adjustment_robust
        rolls = [{"dt": pd.Timestamp("2026-01-20"), "roll_ratio": 1.05}]
        result = apply_backward_adjustment_robust(df, rolls)
        # Rows at/after the roll date should be unchanged (factor=1.0)
        mask_after = df["dt"] >= pd.Timestamp("2026-01-20")
        np.testing.assert_allclose(result.loc[mask_after, "close"], 100.0)

    def test_raw_close_preserved(self):
        df = pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=50, freq="D"),
            "open": np.full(50, 100.0),
            "high": np.full(50, 105.0),
            "low": np.full(50, 95.0),
            "close": np.full(50, 100.0),
        })
        from data.data_store import apply_backward_adjustment_robust
        rolls = [{"dt": pd.Timestamp("2026-01-20"), "roll_ratio": 1.05}]
        result = apply_backward_adjustment_robust(df, rolls)
        assert "raw_close" in result.columns
        np.testing.assert_allclose(result["raw_close"], 100.0)

    def test_empty_rolls_passthrough(self):
        df = pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=10, freq="D"),
            "close": np.full(10, 100.0),
        })
        from data.data_store import apply_backward_adjustment_robust
        result = apply_backward_adjustment_robust(df, [])
        np.testing.assert_allclose(result["close"], 100.0)

    def test_detect_roll_events_basic(self):
        from data.tqsdk_fetcher import detect_roll_events
        df = pd.DataFrame({
            "dt": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "contract_code": ["CF2509", "CF2509", "CF2601", "CF2601"],
            "close": [100.0, 101.0, 150.0, 151.0],
        })
        rolls = detect_roll_events(df)
        # Contract change detected between index 1 and 2
        assert len(rolls) == 1
        assert rolls[0]["old_contract"] == "CF2509"
        assert rolls[0]["new_contract"] == "CF2601"

    def test_detect_roll_events_empty(self):
        from data.tqsdk_fetcher import detect_roll_events
        assert detect_roll_events(pd.DataFrame()) == []

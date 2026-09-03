"""Signal contract: backtest position matches live signal_weight / short_horizon."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.prediction_scheme import VarietyScheme, signal_weight  # noqa: E402
from cascade.signal_contract import position_from_forecast  # noqa: E402


def _full_scheme(**kw) -> VarietyScheme:
    defaults = dict(
        symbol="xx", name="test", scheme_type="trend",
        use_full_signal=True, short_horizon_only=False, decay=1.35,
        trend_threshold_pct=0.1,
    )
    defaults.update(kw)
    return VarietyScheme(**defaults)


class TestSignalContract(unittest.TestCase):
    def test_full_signal_matches_live_weighted_average(self):
        scheme = _full_scheme(short_horizon_only=False, decay=1.35)
        base = 100.0
        # rising path: early bars near base, late bars high
        fc = np.linspace(100.0, 110.0, 24)
        w = signal_weight(24, scheme)
        live_weighted = float(np.average(fc, weights=w))
        sig = position_from_forecast(fc, base, scheme=scheme)
        self.assertAlmostEqual(sig["weighted_pred"], live_weighted, places=10)
        self.assertAlmostEqual(sig["delta_pred"], live_weighted - base, places=10)
        self.assertEqual(sig["position_sign"], 1.0)
        self.assertTrue(sig["used_scheme_weights"])
        # weighted != endpoint when decay applies
        self.assertNotAlmostEqual(sig["weighted_pred"], float(fc[-1]), places=6)

    def test_short_horizon_ignores_second_half_endpoint(self):
        """short_horizon_only: second-half spike must not flip position if first half flat-down."""
        scheme = _full_scheme(short_horizon_only=True, use_full_signal=False)
        base = 100.0
        fc = np.ones(24) * 99.0  # first half slightly below base
        fc[12:] = 120.0  # late spike — endpoint would be long
        endpoint_sign = float(np.sign(fc[-1] - base))
        self.assertEqual(endpoint_sign, 1.0)
        sig = position_from_forecast(fc, base, scheme=scheme)
        self.assertTrue(sig["short_horizon_only"])
        # first half mean 99 → short
        self.assertEqual(sig["position_sign"], -1.0)
        self.assertLess(sig["delta_pred"], 0.0)
        self.assertEqual(sig["endpoint_delta"], 20.0)

    def test_no_scheme_endpoint_fallback(self):
        base = 50.0
        fc = np.array([51.0, 52.0, 53.0])
        sig = position_from_forecast(fc, base, scheme=None)
        self.assertFalse(sig["used_scheme_weights"])
        self.assertEqual(sig["delta_pred"], 3.0)
        self.assertEqual(sig["position_sign"], 1.0)

    def test_trade_direction_is_weighted_1h_regime_is_daily(self):
        """CF-01 A: 可交易方向=1H 加权；日线 thr 只进 regime_direction。"""
        scheme = _full_scheme(trend_threshold_pct=0.1)
        fc = np.linspace(100, 105, 24)
        # slope 0.0005 fraction/day → 0.05 %/day < 0.1 thr → regime 中性
        sig = position_from_forecast(fc, 100.0, scheme=scheme, daily_slope=0.0005)
        self.assertEqual(sig["position_sign"], 1.0)
        self.assertTrue(sig["direction"].startswith("看多"), msg=sig["direction"])
        self.assertIsNotNone(sig["regime_direction"])
        self.assertTrue(sig["regime_direction"].startswith("中性"), msg=sig["regime_direction"])


if __name__ == "__main__":
    unittest.main()

"""Phase 15: 4 个新协变量单元测试 (TDD — 先写后实现)"""
import unittest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cascade.features import _calc_nvi, _calc_qstick, _calc_vwap_deviation, _calc_stddev


def _make_df(n=500, seed=42):
    """构造测试用 1H DataFrame (列名匹配 kline_1h schema)"""
    rng = np.random.RandomState(seed)
    close = 5000 + np.cumsum(rng.randn(n) * 10)
    open_ = close + rng.randn(n) * 5
    high = np.maximum(close, open_) + np.abs(rng.randn(n) * 3)
    low = np.minimum(close, open_) - np.abs(rng.randn(n) * 3)
    volume = (rng.uniform(1000, 10000, n)).astype(int)
    return pd.DataFrame({
        "close_price": close, "open_price": open_,
        "high": high, "low": low, "volume": volume,
    })


class TestNVI(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_volume_null_handling(self):
        """volume NULL bar 应跳过累积, 不产生 NaN"""
        df = _make_df()
        df.loc[10:13, "volume"] = np.nan
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_volume_null_streak_gt6(self):
        """连续 NULL > 6 bar 后仍应回退为 0, 不产生 NaN"""
        df = _make_df()
        df.loc[10:20, "volume"] = np.nan
        result = _calc_nvi(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_zscore_normalized(self):
        """rolling z-score 中间段均值接近 0"""
        df = _make_df(n=1000)
        result = _calc_nvi(df, lookback=20)
        mid = result[100:900]
        self.assertAlmostEqual(np.mean(mid), 0.0, delta=0.5)


class TestQSTICK(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_qstick(df, lookback=14)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_qstick(df, lookback=14)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_bounded_range(self):
        """标准化后绝对值应 < 10"""
        df = _make_df(n=1000)
        result = _calc_qstick(df, lookback=14)
        self.assertTrue(np.all(np.abs(result[60:]) < 10))


class TestVWAPDeviation(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_high_low_null_fallback(self):
        """high/low NULL 应回退为 0"""
        df = _make_df()
        df.loc[10:13, "high"] = np.nan
        result = _calc_vwap_deviation(df, lookback=24)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_deviation_near_zero(self):
        """正常行情下 VWAP 偏离均值接近 0"""
        df = _make_df(n=1000)
        result = _calc_vwap_deviation(df, lookback=24)
        mid = result[100:900]
        self.assertAlmostEqual(np.mean(np.abs(mid)), 0.0, delta=0.05)


class TestStdDev(unittest.TestCase):
    def test_output_shape(self):
        df = _make_df()
        result = _calc_stddev(df, lookback=20)
        self.assertEqual(result.shape, (len(df),))

    def test_no_nan(self):
        df = _make_df()
        result = _calc_stddev(df, lookback=20)
        self.assertEqual(np.isnan(result).sum(), 0)

    def test_positive_and_negative(self):
        """标准化偏差应有正有负"""
        df = _make_df(n=1000)
        result = _calc_stddev(df, lookback=20)
        mid = result[100:900]
        self.assertTrue(np.any(mid > 0))
        self.assertTrue(np.any(mid < 0))


class TestComboIntegration(unittest.TestCase):
    """测试新协变量在 build_combo_covariate_matrix 中的集成"""

    def test_all_four_in_combo(self):
        from cascade.features import build_combo_covariate_matrix
        from data.data_store import DataStore
        store = DataStore("ss")
        hist = np.random.randn(500) * 100 + 5000
        pred = np.random.randn(22) * 10 + hist[-1]
        result = build_combo_covariate_matrix(
            symbol="ss", store=store,
            historical_daily_closes=hist,
            predicted_daily_closes=pred,
            covariate_types=["nvi", "qstick", "vwap_deviation", "stddev"],
            limit=480,
        )
        for key in ["nvi", "qstick", "vwap_deviation", "stddev"]:
            self.assertIn(key, result)
            self.assertEqual(len(result[key].shape), 1)
            self.assertEqual(np.isnan(result[key]).sum(), 0)


if __name__ == "__main__":
    unittest.main()

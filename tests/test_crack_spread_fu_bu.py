"""SC->FU/BU crack spread 单元测试 (Phase 8b)"""
import unittest
import numpy as np
import pandas as pd
from cascade.features import calc_crack_spread, _align_feedstock
from config.crack_spread_pairs import get_crack_pair


def _df(dts, closes):
    return pd.DataFrame({"dt": pd.to_datetime(dts), "close_price": closes})


class TestCrackPairConfig(unittest.TestCase):
    def test_fu_pair(self):
        pair = get_crack_pair("fu")
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0], "sc")
        self.assertAlmostEqual(pair[1], 4.7191, places=3)

    def test_bu_pair(self):
        pair = get_crack_pair("bu")
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0], "sc")
        self.assertAlmostEqual(pair[1], 2.8067, places=3)

    def test_case_insensitive(self):
        self.assertEqual(get_crack_pair("FU"), get_crack_pair("fu"))
        self.assertEqual(get_crack_pair("BU"), get_crack_pair("bu"))


class TestAlignFeedstock(unittest.TestCase):
    def test_basic_alignment(self):
        """SC 和 FU 时间轴完全一致 -> 对齐后无缺失"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = _df(dts, np.full(60, 5000.0))
        leg = _df(dts, np.full(60, 3000.0))
        aligned = _align_feedstock(main, leg)
        self.assertEqual(len(aligned), 60)
        self.assertTrue(aligned.notna().all())
        np.testing.assert_array_equal(aligned.values, 3000.0)

    def test_partial_overlap_ffill(self):
        """SC 只有前 50 根 -> 后 10 根 ffill 用 SC 末值"""
        dts_main = pd.date_range("2024-01-01 09:00", periods=60, freq="h")
        dts_leg = pd.date_range("2024-01-01 09:00", periods=50, freq="h")
        main = _df(dts_main, np.full(60, 5000.0))
        leg = _df(dts_leg, np.full(50, 3000.0))
        aligned = _align_feedstock(main, leg, max_ffill_gap=15)
        # 后 10 根 ffill (gap=10 <= 15, 信任)
        self.assertTrue(aligned.notna().all())
        np.testing.assert_array_equal(aligned.values[:50], 3000.0)
        np.testing.assert_array_equal(aligned.values[50:], 3000.0)

    def test_gap_exceeds_limit(self):
        """SC 连续缺失 > max_ffill_gap -> NaN"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        dts_leg = pd.date_range("2024-01-01", periods=40, freq="h")
        main = _df(dts, np.full(60, 5000.0))
        leg = _df(dts_leg, np.full(40, 3000.0))
        aligned = _align_feedstock(main, leg, max_ffill_gap=4)
        # bar 0-39: 真实命中
        self.assertTrue(aligned.iloc[:40].notna().all())
        # bar 40-43: gap 1-4, 信任 ffill
        self.assertTrue(aligned.iloc[40:44].notna().all())
        # bar 44-59: gap 5-20 > 4, NaN
        self.assertTrue(aligned.iloc[44:].isna().all())

    def test_sc_night_session_superset(self):
        """SC 有凌晨 bar (00:00-02:30) 但 FU 没有 -> FU 主表不受影响"""
        # FU 时间轴 (无凌晨)
        fu_dts = pd.date_range("2024-01-01 09:00", periods=20, freq="h")
        # SC 时间轴 (含凌晨, 比 FU 多)
        sc_dts = pd.date_range("2024-01-01 09:00", periods=30, freq="h")
        fu = _df(fu_dts, np.full(20, 5000.0))
        sc = _df(sc_dts, np.linspace(3000, 3100, 30))
        aligned = _align_feedstock(fu, sc)
        # FU 只有 20 根, SC 有 30 根 -> 对齐后 FU 的 20 根全命中 (都在 SC 范围内)
        self.assertEqual(len(aligned), 20)
        self.assertTrue(aligned.notna().all())


class TestCalcCrackSpreadFUBU(unittest.TestCase):
    def test_fu_spread_formula(self):
        """spread = FU - 4.7191 * SC"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        fu = _df(dts, np.full(60, 5000.0))
        sc = _df(dts, np.full(60, 1000.0))
        out = calc_crack_spread(fu, sc, ratio=4.7191, mode="level", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertFalse(np.any(np.isnan(out)))
        # spread = 5000 - 4.7191 * 1000 = 280.9 -> level 模式非零
        self.assertTrue(np.any(out[:60] != 0))

    def test_bu_spread_formula(self):
        """spread = BU - 2.8067 * SC"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        bu = _df(dts, np.full(60, 4000.0))
        sc = _df(dts, np.full(60, 1000.0))
        out = calc_crack_spread(bu, sc, ratio=2.8067, mode="slope", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertFalse(np.any(np.isnan(out)))

    def test_sc_empty_returns_zeros(self):
        """SC 数据为空 -> crack_spread 全 0, 不 crash"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        fu = _df(dts, np.full(60, 5000.0))
        out = calc_crack_spread(fu, None, ratio=4.7191, mode="slope", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertTrue(np.all(out == 0))

    def test_sc_empty_df_returns_zeros(self):
        """SC DataFrame 为空 -> crack_spread 全 0"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        fu = _df(dts, np.full(60, 5000.0))
        empty_sc = pd.DataFrame({"dt": [], "close_price": []})
        out = calc_crack_spread(fu, empty_sc, ratio=4.7191, mode="level", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertTrue(np.all(out == 0))


if __name__ == "__main__":
    unittest.main()

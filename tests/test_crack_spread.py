"""crack_spread 协变量单测"""
import unittest
import numpy as np
import pandas as pd
from cascade.features import calc_crack_spread


def _df(dts, closes):
    return pd.DataFrame({"dt": pd.to_datetime(dts), "close_price": closes})


class TestCrackSpread(unittest.TestCase):
    def test_formula_slope(self):
        """spread = TA - 0.655·PX (slope 模式, 有信号)"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5200, 60)   # TA 单调上行
        leg = np.linspace(3000, 3000, 60)    # PX 平
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), ratio=0.655, mode="slope", lookback=20, horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertFalse(np.any(np.isnan(out)))
        # spread 单调上行 -> slope > 0 -> tanh>0 (后半段)
        self.assertTrue(np.mean(out[-24:]) > 0)

    def test_alignment_partial_overlap(self):
        """TA 10 根(含 3 根 PX 无的夜盘), PX 7 根 -> ffill 用 PX 末值"""
        dts_main = pd.date_range("2024-01-01 09:00", periods=10, freq="h")
        # PX 只有前 7 根
        dts_leg = pd.date_range("2024-01-01 09:00", periods=7, freq="h")
        main = np.full(10, 5000.0)
        leg = np.full(7, 3000.0)
        out = calc_crack_spread(_df(dts_main, main), _df(dts_leg, leg), mode="level", horizon=24)
        self.assertEqual(out.shape, (34,))
        # 后 3 根 ffill 用 PX=3000, spread=5000-0.655*3000=3035, 应非零
        self.assertTrue(np.any(out[:10] != 0))

    def test_ffill_gap_exceeds_limit(self):
        """连续 20 根 PX 缺失 (>max_ffill_gap=4) -> 这些 bar 协变量=0"""
        dts = pd.date_range("2024-01-01 09:00", periods=60, freq="h")
        # PX 前 40 根有, 后 20 根缺 (gap=20 > 4)
        dts_leg = pd.date_range("2024-01-01 09:00", periods=40, freq="h")
        main = np.linspace(5000, 5100, 60)   # TA 单调上行, 产生非零 slope
        leg = np.full(40, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts_leg, leg), mode="slope", lookback=20, horizon=24)
        # bar 0-39: PX 真实命中, runs=0
        # bar 40-43: PX 缺失第 1-4 根, runs=1..4 <= max_ffill_gap=4 -> 信任 -> 非零
        # bar 44-59: runs=5..20 > 4 -> 守卫触发 -> 协变量=0
        self.assertTrue(np.all(out[44:60] == 0))
        self.assertTrue(np.all(out[40:44] != 0))   # ffill 信任窗口内 (slope > 0)
        self.assertTrue(np.any(out[20:40] != 0))   # 有 slope 窗口且 PX 命中

    def test_no_leg_returns_zeros(self):
        """df_leg=None -> 全 0, 不 crash"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        out = calc_crack_spread(_df(dts, np.full(60, 5000.0)), None, mode="slope", horizon=24)
        self.assertEqual(out.shape, (84,))
        self.assertTrue(np.all(out == 0))

    def test_level_constant_horizon(self):
        """level 模式 horizon=常数 (末值平铺)"""
        dts = pd.date_range("2024-01-01", periods=150, freq="h")
        main = np.linspace(5000, 5100, 150); leg = np.full(150, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="level", horizon=24)
        self.assertAlmostEqual(out[-1], out[-24], places=5)

    def test_slope_decay_horizon(self):
        """slope 模式 horizon 向 0 衰减"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5200, 60); leg = np.full(60, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="slope", horizon=24)
        # 衰减: |out[-1]| < |out[-24]|
        self.assertLess(abs(out[-1]), abs(out[-24]) + 1e-9)

    def test_slope_tanh_not_saturated(self):
        """大斜率下 rolling_std 归一化后 tanh 未全压缩到 ±1"""
        dts = pd.date_range("2024-01-01", periods=150, freq="h")
        main = np.linspace(5000, 6000, 150)  # 大斜率
        leg = np.full(150, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="slope", lookback=20, horizon=24)
        ctx = out[:150]
        # 不应全为 ±1 (有梯度)
        self.assertFalse(np.all(np.abs(ctx[-20:]) >= 0.999))

    def test_zscore_decay_horizon(self):
        """zscore 模式 horizon 向 0 衰减"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.concatenate([np.full(30, 5000.0), np.linspace(5000, 5200, 30)])
        leg = np.full(60, 3000.0)
        out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode="zscore", lookback=20, horizon=24)
        self.assertLess(abs(out[-1]), abs(out[-24]) + 1e-9)

    def test_no_nan_output(self):
        """所有模式无 NaN"""
        dts = pd.date_range("2024-01-01", periods=60, freq="h")
        main = np.linspace(5000, 5100, 60); leg = np.linspace(3000, 3050, 60)
        for m in ("level", "slope", "zscore"):
            out = calc_crack_spread(_df(dts, main), _df(dts, leg), mode=m, horizon=24)
            self.assertFalse(np.any(np.isnan(out)), f"{m} has NaN")


class TestBuildCrackSpread(unittest.TestCase):
    def _fake_store(self):
        class _S:
            def get_main_contract_1h(self, limit=1023):
                dts = pd.date_range("2024-01-01", periods=100, freq="h")
                return pd.DataFrame({"dt": dts, "close_price": np.linspace(5000,5100,100),
                                     "open_price": 5000.0, "high_price": 5100.0, "low_price": 4990.0,
                                     "volume": 1000.0, "open_interest": 5000.0, "contract_code": "TA_MAIN"})
        return _S()

    def test_build_single_crack_spread(self):
        from cascade.features import build_covariate_matrix
        dts = pd.date_range("2024-01-01", periods=100, freq="h")
        px_df = pd.DataFrame({"dt": dts, "close_price": np.full(100, 3000.0)})
        res = build_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_type="crack_spread_slope",
            feedstock_cache={"px": px_df})
        self.assertIn("crack_spread_slope", res)
        self.assertEqual(len(res["crack_spread_slope"]), 124)

    def test_build_zero_regression_no_cache(self):
        """非 crack_spread 类型, feedstock_cache=None, 不感知"""
        from cascade.features import build_covariate_matrix
        res = build_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_type="ccl", feedstock_cache=None)
        self.assertIn("daily_slope", res)
        self.assertIn("ccl_pct", res)

    def test_build_combo_with_crack_spread(self):
        """combo 模式: bb_squeeze + crack_spread_slope 同时返回"""
        from cascade.features import build_combo_covariate_matrix
        dts = pd.date_range("2024-01-01", periods=100, freq="h")
        px_df = pd.DataFrame({"dt": dts, "close_price": np.full(100, 3000.0)})
        res = build_combo_covariate_matrix("ta", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_types=["bb_squeeze", "crack_spread_slope"],
            feedstock_cache={"px": px_df})
        self.assertIn("bb_squeeze", res)
        self.assertIn("crack_spread_slope", res)
        self.assertEqual(len(res["crack_spread_slope"]), 124)

    def test_build_combo_no_pair_returns_zeros(self):
        """combo 模式 + 无配对品种 (SS) -> crack_spread 全 0"""
        from cascade.features import build_combo_covariate_matrix
        res = build_combo_covariate_matrix("ss", self._fake_store(),
            historical_daily_closes=np.linspace(5000,5100,50),
            predicted_daily_closes=np.linspace(5100,5150,22),
            daily_dates=pd.date_range("2024-01-01", periods=50, freq="D"),
            horizon=24, covariate_types=["bb_squeeze", "crack_spread_slope"],
            feedstock_cache=None)
        self.assertIn("crack_spread_slope", res)
        self.assertTrue(np.all(res["crack_spread_slope"] == 0))


class TestHourlyDI(unittest.TestCase):
    def test_needs_feedstock_detection(self):
        from cascade.hourly_model import _needs_feedstock
        self.assertTrue(_needs_feedstock("crack_spread_slope", None))
        self.assertTrue(_needs_feedstock(None, ["bb_squeeze", "crack_spread_level"]))
        self.assertFalse(_needs_feedstock("ccl", None))
        self.assertFalse(_needs_feedstock(None, ["oi", "hurst"]))


class TestEffectiveN(unittest.TestCase):
    def test_verdict_uses_effective_n(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from phase4d_parse_results import verdict
        # baseline 失败, cand 精度持平, n=396 但 effective_n=178 -> UNDERPOWERED
        base = {"n": 396, "ev": 0.0, "pf": 1.0, "maxdd": -0.2, "mape": 2.5, "diracc": 50}
        cand = {"n": 396, "effective_n": 178, "ev": 0.0, "pf": 1.0, "maxdd": -0.2, "mape": 2.5, "diracc": 50}
        status, tag, reasons = verdict(base, cand)
        self.assertEqual(status, "UNDERPOWERED")
        self.assertTrue(any("178" in r for r in reasons))

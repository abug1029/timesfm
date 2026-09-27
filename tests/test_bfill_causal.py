"""D4：禁止用未来值回填。"""
import inspect
import unittest

import numpy as np
import pandas as pd

from cascade.features import causal_ffill


class TestCausalFfill(unittest.TestCase):
    def test_leading_nan_uses_cold_start_not_future_value(self):
        out = causal_ffill(pd.Series([np.nan, np.nan, 3.0, 4.0]), cold_start_fill=1.0)
        self.assertEqual(list(out), [1.0, 1.0, 3.0, 4.0])

    def test_interior_nan_carries_forward(self):
        out = causal_ffill(pd.Series([1.0, np.nan, 3.0]), cold_start_fill=0.0)
        self.assertEqual(list(out), [1.0, 1.0, 3.0])

    def test_all_nan_becomes_cold_start(self):
        out = causal_ffill(pd.Series([np.nan, np.nan]), cold_start_fill=1.0)
        self.assertEqual(list(out), [1.0, 1.0])


class TestCclPctCausality(unittest.TestCase):
    """真泄漏点：oi 前导为 0 → replace(0,nan) → rolling NaN → bfill 搬未来值。"""

    def _df(self, n=60):
        rng = np.random.default_rng(0)
        oi = np.zeros(n)
        oi[10:] = rng.uniform(100, 200, n - 10)   # 前 10 根为 0
        return pd.DataFrame({
            "dt": pd.date_range("2026-01-01", periods=n, freq="h"),
            "ccl": rng.normal(0, 1, n),
            "oi": oi,
        })

    def test_ccl_pct_leading_segment_is_causal(self):
        from cascade.features import calc_ccl_pct
        df = self._df()
        full = calc_ccl_pct(df["ccl"], df["oi"])
        # 截断到冷启动段内（第 5 点）：此时未来数据尚不存在
        part = calc_ccl_pct(df["ccl"].iloc[:5], df["oi"].iloc[:5])
        for k in range(5):
            self.assertAlmostEqual(
                float(full.iloc[k]), float(part.iloc[k]), places=10,
                msg=f"ccl_pct 第 {k} 点依赖了未来数据（bfill 泄漏）")


class TestAoAccelBfillRemoved(unittest.TestCase):
    """结构性前视但被 tanh 饱和掩盖：只断言源码不再 bfill。"""

    def test_no_bfill_in_calc_ao_acceleration(self):
        from cascade.features import calc_ao_acceleration
        src = inspect.getsource(calc_ao_acceleration)
        self.assertNotIn(".bfill()", src)

    def test_no_bfill_in_calc_ccl_pct(self):
        from cascade.features import calc_ccl_pct
        src = inspect.getsource(calc_ccl_pct)
        self.assertNotIn(".bfill()", src)


if __name__ == "__main__":
    unittest.main()

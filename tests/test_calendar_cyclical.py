"""calendar_cyclical 协变量单测 (Phase 4)
验证: 4维正交性、周期边界(12月↔1月, 12/31↔1/1)、horizon精确填充、时间列兼容、4D→4×1D 拆分
"""
import unittest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from cascade.features import calc_calendar_cyclical


class TestCalendarCyclical(unittest.TestCase):

    def setUp(self):
        # 构造 100 根 1H K线,时间跨度含 12 月底 → 1 月初边界
        base = pd.Timestamp("2024-12-30 00:00:00")
        dts = pd.date_range(base, periods=100, freq="h")
        self.df = pd.DataFrame({
            "dt": dts,
            "close_price": np.random.rand(100) * 5000 + 4000,
            "open_price": np.random.rand(100) * 5000 + 4000,
            "high_price": np.random.rand(100) * 5000 + 4000,
            "low_price": np.random.rand(100) * 5000 + 4000,
            "volume": np.random.randint(1000, 10000, 100),
            "open_interest": np.random.randint(50000, 200000, 100),
        })

    def test_output_shape(self):
        """输出形状 = (n_rows + horizon, 4)"""
        horizon = 24
        out = calc_calendar_cyclical(self.df, horizon)
        self.assertEqual(out.shape, (100 + horizon, 4))

    def test_orthogonality(self):
        """sin^2 + cos^2 ≈ 1 (数值精度内)"""
        out = calc_calendar_cyclical(self.df, horizon=0)
        doy_sin, doy_cos, m_sin, m_cos = out[:,0], out[:,1], out[:,2], out[:,3]
        np.testing.assert_allclose(doy_sin**2 + doy_cos**2, 1.0, rtol=1e-6)
        np.testing.assert_allclose(m_sin**2 + m_cos**2, 1.0, rtol=1e-6)

    def test_periodic_boundary_dec_jan(self):
        """12月31日 23:00 与 1月1日 00:00 的 DayOfYear 衔接平滑"""
        # 构造跨年边界数据
        dts = pd.date_range("2024-12-31 22:00", periods=4, freq="h")
        df = pd.DataFrame({"dt": dts, "close_price": [1]*4})
        out = calc_calendar_cyclical(df, horizon=0)
        # 12/31 dayofyear=366 (闰年), 1/1 dayofyear=1
        # sin/cos 应平滑过渡,无突变
        diff = np.abs(out[1] - out[0])  # 相邻小时差
        self.assertTrue(np.all(diff < 0.1), f"跨年边界突变过大: {diff}")

    def test_horizon_exact_fill(self):
        """horizon 部分精确等于未来每小时的真实 dayofyear/month"""
        horizon = 12
        out = calc_calendar_cyclical(self.df, horizon)
        last_ctx = self.df["dt"].iloc[-1]
        future_dts = pd.date_range(last_ctx + pd.Timedelta(hours=1), periods=horizon, freq="h")
        expected_doy = future_dts.dayofyear.values
        expected_month = future_dts.month.values
        # 取 horizon 部分 (最后 horizon 行)
        horiz_part = out[-horizon:]
        np.testing.assert_allclose(
            np.round(np.arcsin(horiz_part[:,0]) * 365.25 / (2*np.pi)),
            expected_doy, atol=1
        )
        np.testing.assert_allclose(
            np.round(np.arcsin(horiz_part[:,2]) * 12 / (2*np.pi)),
            expected_month, atol=1
        )

    def test_time_column_compat(self):
        """同时兼容 'dt' 和 'date' 列名"""
        df_dt = self.df.copy()
        df_date = self.df.rename(columns={"dt": "date"})
        out_dt = calc_calendar_cyclical(df_dt, horizon=5)
        out_date = calc_calendar_cyclical(df_date, horizon=5)
        np.testing.assert_array_equal(out_dt, out_date)

    def test_build_covariate_matrix_split_single(self):
        """验证 build_covariate_matrix 将 4D 拆分为 4 个独立 1D key"""
        from cascade.features import build_covariate_matrix

        # 构造最小 mock df (context_bars=10, horizon=5)
        df = pd.DataFrame({
            'dt': pd.date_range('2024-01-01', periods=10, freq='h'),
            'close_price': np.linspace(4000, 4100, 10),
            'open_price': np.linspace(4000, 4100, 10),
            'high_price': np.linspace(4000, 4100, 10),
            'low_price': np.linspace(4000, 4100, 10),
            'volume': np.ones(10) * 1000,
            'open_interest': np.ones(10) * 50000,
        })

        store = MagicMock()
        store.get_main_contract_1h = MagicMock(return_value=df)

        # 调用 build_covariate_matrix
        result = build_covariate_matrix(
            symbol='jd',
            store=store,
            historical_daily_closes=np.linspace(4000, 4100, 300),
            predicted_daily_closes=np.linspace(4100, 4200, 22),
            daily_dates=pd.date_range('2024-01-01', periods=300, freq='D'),
            horizon=5,
            covariate_type='calendar_cyclical'
        )

        # 断言返回 4 个独立 key (不包含 "calendar_cyclical")
        self.assertIn('calendar_doy_sin', result)
        self.assertIn('calendar_doy_cos', result)
        self.assertIn('calendar_month_sin', result)
        self.assertIn('calendar_month_cos', result)
        self.assertNotIn('calendar_cyclical', result)

        # 断言每个 key 的 shape 为 1D (10 + 5 = 15)
        for key in ['calendar_doy_sin', 'calendar_doy_cos', 'calendar_month_sin', 'calendar_month_cos']:
            self.assertEqual(result[key].shape, (15,))
            self.assertEqual(result[key].dtype, np.float32)

    def test_build_combo_covariate_matrix_split(self):
        """验证 build_combo_covariate_matrix 将 calendar_cyclical 拆分为 4 个 key"""
        from cascade.features import build_combo_covariate_matrix

        # 构造最小 mock df
        df = pd.DataFrame({
            'dt': pd.date_range('2024-01-01', periods=10, freq='h'),
            'close_price': np.linspace(4000, 4100, 10),
            'open_price': np.linspace(4000, 4100, 10),
            'high_price': np.linspace(4000, 4100, 10),
            'low_price': np.linspace(4000, 4100, 10),
            'volume': np.ones(10) * 1000,
            'open_interest': np.ones(10) * 50000,
        })

        store = MagicMock()
        store.get_main_contract_1h = MagicMock(return_value=df)

        # 调用 build_combo_covariate_matrix
        result = build_combo_covariate_matrix(
            symbol='jd',
            store=store,
            historical_daily_closes=np.linspace(4000, 4100, 300),
            predicted_daily_closes=np.linspace(4100, 4200, 22),
            daily_dates=pd.date_range('2024-01-01', periods=300, freq='D'),
            horizon=5,
            covariate_types=['calendar_cyclical', 'oi']
        )

        # 断言 calendar_cyclical 被拆分为 4 个 key
        self.assertIn('calendar_doy_sin', result)
        self.assertIn('calendar_doy_cos', result)
        self.assertIn('calendar_month_sin', result)
        self.assertIn('calendar_month_cos', result)
        self.assertNotIn('calendar_cyclical', result)

        # 断言 shape 一致 (10 + 5 = 15)
        for key in ['calendar_doy_sin', 'calendar_doy_cos', 'calendar_month_sin', 'calendar_month_cos', 'oi_pct_change']:
            self.assertEqual(result[key].shape, (15,))


if __name__ == "__main__":
    unittest.main()
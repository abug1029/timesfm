import unittest
import numpy as np
import pandas as pd
from cascade.features import _calc_stddev

class TestStdDevFix(unittest.TestCase):
    def test_stddev_uses_returns_not_prices(self):
        """StdDev 应使用收益率 std,而非价格 std (price-level invariant)"""
        n = 100
        trend = np.linspace(1000, 2000, n)
        noise = np.random.normal(0, 10, n)
        close = trend + noise

        df = pd.DataFrame({"close_price": close})
        result = _calc_stddev(df, lookback=20)

        # 另一组: 价格水平翻倍,但波动率相同
        close2 = trend * 2 + noise * 2
        df2 = pd.DataFrame({"close_price": close2})
        result2 = _calc_stddev(df2, lookback=20)

        # 两组结果应近似相等 (收益率 std 相同)
        valid = ~np.isnan(result) & ~np.isnan(result2)
        if valid.sum() > 0:
            ratio = np.mean(np.abs(result[valid])) / (np.mean(np.abs(result2[valid])) + 1e-8)
            self.assertGreater(ratio, 0.7, f"StdDev should be price-level invariant, ratio={ratio:.3f}")
            self.assertLess(ratio, 1.4, f"StdDev should be price-level invariant, ratio={ratio:.3f}")

    def test_stddev_shape_no_nan(self):
        """输出 shape 正确,无 NaN"""
        n = 200
        df = pd.DataFrame({"close_price": np.random.normal(100, 5, n)})
        result = _calc_stddev(df, lookback=20)
        self.assertEqual(result.shape, (n,))
        self.assertFalse(np.isnan(result).any())

    def test_stddev_detects_volatility_regime(self):
        """StdDev 应能检测波动率 regime 变化

        设计: 用纯低波动 warmup (200 bars) + 纯低波动段 (200 bars) + 纯高波动段 (400 bars),
        确保比较时两个滚动窗口都是完全稳定的同质段。
        """
        np.random.seed(42)

        # 构造 returns: 低波 std=0.002, 高波 std=0.020 (10x 差异)
        warmup_returns = np.random.normal(0, 0.002, 200)
        low_vol_returns = np.random.normal(0, 0.002, 200)
        high_vol_returns = np.random.normal(0, 0.020, 400)

        # 从 returns 构造价格
        all_returns = np.concatenate([warmup_returns, low_vol_returns, high_vol_returns])
        prices = 1000 * np.cumprod(1 + all_returns)

        df = pd.DataFrame({"close_price": prices})
        result = _calc_stddev(df, lookback=20)

        # 低波动段: 索引 [220:320] (warmup 之后 20+60=80 bars)
        # 高波动段: 索引 [480:580] (transition 之后 20+60=80 bars)
        low_vol_values = result[220:320]
        high_vol_values = result[480:580]

        low_mean = np.mean(low_vol_values)
        high_mean = np.mean(high_vol_values)

        # 高波动段归一化 std 应显著高于低波动段
        self.assertGreater(high_mean, low_mean,
                          f"StdDev high-vol mean={high_mean:.4f} should exceed low-vol mean={low_mean:.4f}")

if __name__ == "__main__":
    unittest.main()

"""Phase 15 audit fix: VWAP 衰减填充对照实验"""
import unittest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cascade.features import build_combo_covariate_matrix
from data.data_store import DataStore


class TestVWAPFillStrategy(unittest.TestCase):
    """验证 VWAP 协变量支持 default (常数填充) 和 decay (衰减填充) 两种策略"""

    def _get_test_context(self):
        """准备 build_combo_covariate_matrix 所需的测试上下文"""
        store = DataStore("ss")
        hist = np.random.RandomState(42).randn(500) * 100 + 5000
        pred = np.random.RandomState(43).randn(22) * 10 + hist[-1]
        return store, hist, pred

    def test_vwap_default_constant_fill(self):
        """VWAP 默认用常数填充 (保持现有行为)"""
        store, hist, pred = self._get_test_context()
        result = build_combo_covariate_matrix(
            symbol="ss",
            store=store,
            historical_daily_closes=hist,
            predicted_daily_closes=pred,
            covariate_types=["vwap_deviation"],
            horizon=24,
            limit=200,
            fill_strategy="default",
        )

        vwap_cov = result["vwap_deviation"]
        context_len = 200
        horizon_vals = vwap_cov[context_len:]
        self.assertEqual(len(horizon_vals), 24,
                         "Horizon should have 24 values")
        # 常数填充: 最后 24 个值应相同
        self.assertTrue(np.allclose(horizon_vals, horizon_vals[0]),
                        "Constant fill: last 24 values should be identical")

    def test_vwap_decay_fill(self):
        """VWAP 用衰减填充 (新选项: 12-bar 半衰期)"""
        store, hist, pred = self._get_test_context()
        result = build_combo_covariate_matrix(
            symbol="ss",
            store=store,
            historical_daily_closes=hist,
            predicted_daily_closes=pred,
            covariate_types=["vwap_deviation"],
            horizon=24,
            limit=200,
            fill_strategy="decay",
        )

        vwap_cov = result["vwap_deviation"]
        context_len = 200
        horizon_vals = vwap_cov[context_len:]
        self.assertEqual(len(horizon_vals), 24,
                         "Horizon should have 24 values")

        last_context = vwap_cov[context_len - 1]
        # 衰减填充: horizon 值从 last_context 开始按 0.5^(i/12) 衰减
        expected_decay = np.array([0.5 ** (i / 12.0) for i in range(24)])
        expected_horizon = last_context * expected_decay
        self.assertTrue(np.allclose(horizon_vals, expected_horizon, rtol=1e-10),
                        "Decay fill: should follow 12-bar half-life exponential decay")

    def test_vwap_default_is_default_parameter(self):
        """fill_strategy 参数默认为 'default' (向后兼容)"""
        store, hist, pred = self._get_test_context()

        # 不传 fill_strategy 应等同于 "default"
        result_no_arg = build_combo_covariate_matrix(
            symbol="ss", store=store,
            historical_daily_closes=hist, predicted_daily_closes=pred,
            covariate_types=["vwap_deviation"], horizon=24, limit=200,
        )
        result_default = build_combo_covariate_matrix(
            symbol="ss", store=store,
            historical_daily_closes=hist, predicted_daily_closes=pred,
            covariate_types=["vwap_deviation"], horizon=24, limit=200,
            fill_strategy="default",
        )

        self.assertTrue(
            np.allclose(result_no_arg["vwap_deviation"], result_default["vwap_deviation"]),
            "Default fill_strategy should be 'default' (constant fill)")

    def test_vwap_no_nan(self):
        """两种填充策略都不应产生 NaN"""
        store, hist, pred = self._get_test_context()

        for strategy in ["default", "decay"]:
            result = build_combo_covariate_matrix(
                symbol="ss", store=store,
                historical_daily_closes=hist, predicted_daily_closes=pred,
                covariate_types=["vwap_deviation"], horizon=24, limit=200,
                fill_strategy=strategy,
            )
            self.assertEqual(
                np.isnan(result["vwap_deviation"]).sum(), 0,
                f"fill_strategy='{strategy}' should not produce NaN values")


if __name__ == "__main__":
    unittest.main()

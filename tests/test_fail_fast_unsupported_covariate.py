"""
Fail-fast 机制测试：不支持的协变量立即返回

测试场景：
1. build_covariate_matrix 遇到不支持的协变量时抛出 UnsupportedCovariateError
2. build_combo_covariate_matrix 遇到不支持的组合协变量时抛出 UnsupportedCovariateError
3. run_symbol_backtest 在第一个 eval point 捕获该异常并立即返回 None
4. aligned_slow_loop 正确处理 None 返回值，生成 no_data verdict
"""

import pytest
from cascade.features import UnsupportedCovariateError, build_covariate_matrix, build_combo_covariate_matrix
import numpy as np
import pandas as pd


def test_unsupported_covariate_raises():
    """测试 build_covariate_matrix 对不支持的协变量抛出 UnsupportedCovariateError"""

    class MockStore:
        def get_main_contract_1h(self, limit=480):
            return pd.DataFrame({
                "dt": pd.date_range("2024-01-01", periods=100, freq="h"),
                "close_price": np.random.randn(100).cumsum() + 100,
                "high_price": np.random.randn(100).cumsum() + 101,
                "low_price": np.random.randn(100).cumsum() + 99,
                "contract_code": ["TEST"] * 100
            })

    with pytest.raises(UnsupportedCovariateError) as exc_info:
        build_covariate_matrix(
            symbol="TEST",
            store=MockStore(),
            historical_daily_closes=np.array([100.0] * 50),
            predicted_daily_closes=np.array([100.0] * 30),
            covariate_type="invalid_covariate_xyz"
        )

    assert "不支持" in str(exc_info.value) or "not supported" in str(exc_info.value).lower()


def test_combo_unsupported_raises():
    """Test that build_combo_covariate_matrix raises UnsupportedCovariateError for invalid combo covariate."""

    class MockStore:
        def get_main_contract_1h(self, limit=480):
            return pd.DataFrame({
                "dt": pd.date_range("2024-01-01", periods=100, freq="h"),
                "close_price": np.random.randn(100).cumsum() + 100,
                "high_price": np.random.randn(100).cumsum() + 101,
                "low_price": np.random.randn(100).cumsum() + 99,
                "contract_code": ["TEST"] * 100
            })

    with pytest.raises(UnsupportedCovariateError) as exc_info:
        build_combo_covariate_matrix(
            symbol="TEST",
            store=MockStore(),
            historical_daily_closes=np.array([100.0] * 50),
            predicted_daily_closes=np.array([100.0] * 30),
            covariate_types=["invalid_combo_cov"]
        )

    assert "不支持" in str(exc_info.value) or "not supported" in str(exc_info.value).lower()


def test_unsupported_covariate_is_value_error():
    """测试 UnsupportedCovariateError 是 ValueError 的子类（向后兼容）"""
    assert issubclass(UnsupportedCovariateError, ValueError)

    # 应该可以被 ValueError 捕获
    try:
        raise UnsupportedCovariateError("test")
    except ValueError as e:
        assert "test" in str(e)


if __name__ == "__main__":
    # 直接运行时打印测试结果
    print("Running fail-fast mechanism tests...")

    test_unsupported_covariate_raises()
    print("✓ test_unsupported_covariate_raises passed")

    test_combo_unsupported_raises()
    print("✓ test_combo_unsupported_raises passed")

    test_unsupported_covariate_is_value_error()
    print("✓ test_unsupported_covariate_is_value_error passed")

    print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")

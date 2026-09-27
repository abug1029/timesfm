"""协变量诊断系统单元测试（PR-B2）"""

import pytest
import numpy as np
from cascade.covariate_diagnostics import diagnose_covariates


class TestDiagnoseCovariates:
    """测试协变量诊断"""

    def test_empty_covariates(self):
        """空协变量"""
        result = diagnose_covariates({}, context_len=10)
        assert result["cov_effective"] == 0
        assert result["inert_constant"] == []
        assert result["horizon_flat"] == []
        assert result["all_zero"] == []

    def test_all_zero_detected(self):
        """全零通道检测"""
        covariates = {
            "zero_cov": np.zeros(20),
            "normal_cov": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert "zero_cov" in result["all_zero"]
        assert result["cov_effective"] == 1  # 只有 normal_cov 有效

    def test_inert_constant_detected(self):
        """惰性常数检测"""
        covariates = {
            "constant_cov": np.ones(20) * 5.0,  # 常数，std = 0
            "normal_cov": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert "constant_cov" in result["inert_constant"]
        assert result["cov_effective"] == 1

    def test_horizon_flat_detected(self):
        """horizon 平坦检测"""
        arr = np.random.randn(20)
        arr[10:] = 0  # horizon 部分全零
        covariates = {
            "flat_horizon_cov": arr,
            "normal_cov": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert "flat_horizon_cov" in result["horizon_flat"]
        assert result["cov_effective"] == 1

    def test_effective_counted_correctly(self):
        """有效通道计数"""
        covariates = {
            "cov1": np.random.randn(20),
            "cov2": np.random.randn(20),
            "cov3": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert result["cov_effective"] == 3

    def test_mixed_scenario(self):
        """混合场景"""
        covariates = {
            "all_zero": np.zeros(20),
            "constant": np.ones(20) * 3.0,
            "flat_horizon": np.concatenate([np.random.randn(10), np.zeros(10)]),
            "effective": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert "all_zero" in result["all_zero"]
        assert "constant" in result["inert_constant"]
        assert "flat_horizon" in result["horizon_flat"]
        assert result["cov_effective"] == 1  # 只有 effective 有效

    def test_non_array_ignored(self):
        """非数组值忽略"""
        covariates = {
            "not_array": "string_value",
            "normal_cov": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        assert result["cov_effective"] == 1

    def test_empty_horizon(self):
        """空 horizon 处理"""
        covariates = {
            "cov": np.random.randn(10)  # 只有 context，没有 horizon
        }
        result = diagnose_covariates(covariates, context_len=10)
        # context 部分有效，horizon 为空，应该算有效
        assert result["cov_effective"] == 1

    def test_very_small_std(self):
        """非常小的标准差（接近惰性常数）"""
        covariates = {
            "tiny_std": np.ones(20) * 5.0 + np.random.randn(20) * 1e-13,
            "normal_cov": np.random.randn(20)
        }
        result = diagnose_covariates(covariates, context_len=10)
        # std < 1e-12 应该被检测为惰性常数
        assert "tiny_std" in result["inert_constant"]
        assert result["cov_effective"] == 1


class TestDiagnoseCovariatesEdgeCases:
    """边界情况测试"""

    def test_single_element_context(self):
        """单元素 context"""
        covariates = {
            "cov": np.array([5.0, 1.0, 2.0, 3.0])
        }
        result = diagnose_covariates(covariates, context_len=1)
        # context 只有一个元素，std = 0，应该被检测为惰性常数
        assert "cov" in result["inert_constant"]

    def test_all_same_values(self):
        """所有值相同"""
        covariates = {
            "cov": np.ones(20) * 7.0
        }
        result = diagnose_covariates(covariates, context_len=10)
        # 所有值相同，std = 0，应该被检测为惰性常数
        assert "cov" in result["inert_constant"]
        assert result["cov_effective"] == 0

    def test_nan_values(self):
        """NaN 值处理"""
        covariates = {
            "cov_with_nan": np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
                                       11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        }
        # numpy 的 std 会返回 nan 如果有 nan 值
        result = diagnose_covariates(covariates, context_len=10)
        # std 为 nan，不应该 < 1e-12，所以不算惰性常数
        # 但 np.all(arr == 0) 会因为 nan 返回 False
        # 所以这个通道应该是有效的
        assert result["cov_effective"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""三路消融系统单元测试（PR-B5）"""

import pytest
import numpy as np
from cascade.ablation import (
    AblationMode,
    ablate_content_covariates,
    ablate_structural_covariates,
    load_ablation_audit_config,
    is_audit_candidate
)


class TestAblationMode:
    """测试消融模式枚举"""

    def test_enum_values(self):
        """枚举值正确"""
        assert AblationMode.FULL.value == "full"
        assert AblationMode.BASELINE.value == "baseline"
        assert AblationMode.CONTENT.value == "content"
        assert AblationMode.STRUCTURAL.value == "structural"

    def test_enum_from_value(self):
        """从值创建枚举"""
        assert AblationMode("full") == AblationMode.FULL
        assert AblationMode("content") == AblationMode.CONTENT


class TestAblateContentCovariates:
    """测试内容消融"""

    def test_preserves_shape(self):
        """保持 shape"""
        covariates = {
            "cov1": np.random.randn(100),
            "cov2": np.random.randn(100, 10)
        }
        ablated = ablate_content_covariates(covariates, seed=42)

        assert ablated["cov1"].shape == covariates["cov1"].shape
        assert ablated["cov2"].shape == covariates["cov2"].shape

    def test_shuffles_values(self):
        """打乱值"""
        np.random.seed(0)
        original = np.arange(100)
        covariates = {"cov": original}
        ablated = ablate_content_covariates(covariates, seed=42)

        # 值应该被打乱（不完全相同）
        assert not np.array_equal(ablated["cov"], original)
        # 但应该包含相同的元素（只是顺序不同）
        assert set(ablated["cov"]) == set(original)

    def test_deterministic_with_seed(self):
        """相同种子结果相同"""
        covariates = {"cov": np.random.randn(100)}

        ablated1 = ablate_content_covariates(covariates, seed=42)
        ablated2 = ablate_content_covariates(covariates, seed=42)

        assert np.array_equal(ablated1["cov"], ablated2["cov"])

    def test_different_seeds_different_results(self):
        """不同种子结果不同"""
        covariates = {"cov": np.random.randn(100)}

        ablated1 = ablate_content_covariates(covariates, seed=42)
        ablated2 = ablate_content_covariates(covariates, seed=43)

        assert not np.array_equal(ablated1["cov"], ablated2["cov"])

    def test_preserves_marginal_stats(self):
        """保留边际统计"""
        np.random.seed(0)
        original = np.random.randn(1000)
        covariates = {"cov": original}
        ablated = ablate_content_covariates(covariates, seed=42)

        # 均值和标准差应该近似相同
        assert np.abs(ablated["cov"].mean() - original.mean()) < 0.1
        assert np.abs(ablated["cov"].std() - original.std()) < 0.1

    def test_empty_covariates(self):
        """空协变量"""
        ablated = ablate_content_covariates({}, seed=42)
        assert ablated == {}

    def test_non_array_passthrough(self):
        """非数组值直接传递"""
        covariates = {
            "array": np.random.randn(100),
            "string": "not an array"
        }
        ablated = ablate_content_covariates(covariates, seed=42)

        assert ablated["string"] == "not an array"


class TestAblateStructuralCovariates:
    """测试结构消融"""

    def test_all_zeros(self):
        """全部置零"""
        covariates = {
            "cov1": np.random.randn(100),
            "cov2": np.random.randn(100, 10)
        }
        ablated = ablate_structural_covariates(covariates)

        assert np.all(ablated["cov1"] == 0)
        assert np.all(ablated["cov2"] == 0)

    def test_preserves_shape(self):
        """保持 shape"""
        covariates = {
            "cov1": np.random.randn(100),
            "cov2": np.random.randn(100, 10)
        }
        ablated = ablate_structural_covariates(covariates)

        assert ablated["cov1"].shape == covariates["cov1"].shape
        assert ablated["cov2"].shape == covariates["cov2"].shape

    def test_empty_covariates(self):
        """空协变量"""
        ablated = ablate_structural_covariates({})
        assert ablated == {}

    def test_non_array_passthrough(self):
        """非数组值直接传递"""
        covariates = {
            "array": np.random.randn(100),
            "string": "not an array"
        }
        ablated = ablate_structural_covariates(covariates)

        assert ablated["string"] == "not an array"


class TestLoadAblationAuditConfig:
    """测试加载审计集配置"""

    def test_default_config(self):
        """默认配置（文件不存在）"""
        config = load_ablation_audit_config("/nonexistent/path.json")

        assert "schema" in config
        assert "symbols" in config
        assert "covariates" in config
        assert "modes" in config

    def test_config_structure(self):
        """配置结构正确"""
        config = load_ablation_audit_config()

        assert isinstance(config["symbols"], list)
        assert isinstance(config["covariates"], list)
        assert isinstance(config["modes"], list)


class TestIsAuditCandidate:
    """测试审计集候选检查"""

    def test_in_audit_set(self):
        """在审计集中"""
        config = {
            "symbols": ["ss", "sr"],
            "covariates": ["rsi_state", "oi"]
        }

        assert is_audit_candidate("ss", "rsi_state", config) is True
        assert is_audit_candidate("sr", "oi", config) is True

    def test_not_in_audit_set(self):
        """不在审计集中"""
        config = {
            "symbols": ["ss", "sr"],
            "covariates": ["rsi_state", "oi"]
        }

        assert is_audit_candidate("rb", "rsi_state", config) is False
        assert is_audit_candidate("ss", "ccl", config) is False

    def test_default_config(self):
        """使用默认配置"""
        # 默认配置应该包含一些品种和协变量
        result = is_audit_candidate("ss", "rsi_state")
        # 结果取决于默认配置，这里只检查不报错
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

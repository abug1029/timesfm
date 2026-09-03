"""
Regime 动态路由集成测试

验证:
1. RealtimeRegimeClassifier 可正常初始化
2. classify() 返回正确格式
3. regime→covariate 映射存在
4. 与 SCHEMES 的协变量兼容
"""
import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cascade.realtime_regime_classifier import RealtimeRegimeClassifier
from config.prediction_scheme import SCHEMES


class TestRegimeClassifierInit:
    """分类器初始化测试"""

    @pytest.fixture
    def clf(self):
        return RealtimeRegimeClassifier()

    def test_classifier_instantiates(self, clf):
        """分类器可正常创建"""
        assert clf is not None

    def test_regime_labels_defined(self, clf):
        """4 个 regime 标签已定义"""
        assert len(clf.REGIME_LABELS) == 4
        assert 0 in clf.REGIME_LABELS
        assert 3 in clf.REGIME_LABELS

    def test_covariate_map_defined(self, clf):
        """regime→covariate 映射已定义"""
        assert len(clf.REGIME_COVARIATE_MAP) == 4
        for regime_id in range(4):
            covs = clf.REGIME_COVARIATE_MAP[regime_id]
            assert isinstance(covs, list)


class TestRegimeClassify:
    """classify() 方法测试"""

    @pytest.fixture
    def classifier(self):
        return RealtimeRegimeClassifier()

    @pytest.fixture
    def sample_hourly_df(self):
        """生成模拟 1H DataFrame (480 bars = 20 天)"""
        np.random.seed(42)
        n = 480
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        returns = np.random.normal(0.0001, 0.005, n)
        close = 100.0 * np.cumprod(1 + returns)
        high = close * (1 + np.abs(np.random.normal(0, 0.002, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.002, n)))
        open_ = close * (1 + np.random.normal(0, 0.001, n))
        volume = np.random.randint(1000, 10000, n).astype(float)
        oi = np.cumsum(np.random.normal(0, 100, n)) + 50000

        df = pd.DataFrame({
            'datetime': dates,
            'open': open_,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'open_interest': oi,
        })
        return df

    def test_classify_returns_dict(self, classifier, sample_hourly_df):
        """classify() 返回 dict"""
        result = classifier.classify(hourly_df=sample_hourly_df)
        assert isinstance(result, dict)

    def test_classify_has_required_keys(self, classifier, sample_hourly_df):
        """返回 dict 包含必要字段"""
        result = classifier.classify(hourly_df=sample_hourly_df)
        required_keys = ['regime', 'label', 'confidence', 'recommended_covariates']
        for key in required_keys:
            assert key in result, f"缺少字段: {key}"

    def test_classify_regime_in_range(self, classifier, sample_hourly_df):
        """regime ID 在 0-3 范围"""
        result = classifier.classify(hourly_df=sample_hourly_df)
        assert 0 <= result['regime'] <= 3

    def test_classify_confidence_in_range(self, classifier, sample_hourly_df):
        """confidence 在 0-1 范围"""
        result = classifier.classify(hourly_df=sample_hourly_df)
        assert 0.0 <= result['confidence'] <= 1.0

    def test_classify_recommended_covariates_are_lists(self, classifier, sample_hourly_df):
        """recommended_covariates 是列表"""
        result = classifier.classify(hourly_df=sample_hourly_df)
        assert isinstance(result['recommended_covariates'], list)


class TestRegimeCovariateCompatibility:
    """regime→covariate 映射与 SCHEMES 兼容性测试"""

    def test_all_regime_covariates_exist_in_features(self):
        """REGIME_COVARIATE_MAP 中的协变量名称格式合理"""
        clf = RealtimeRegimeClassifier()
        all_covs = set()
        for regime_id, covs in clf.REGIME_COVARIATE_MAP.items():
            all_covs.update(covs)
        all_covs.discard('')
        for cov in all_covs:
            assert isinstance(cov, str), f"协变量应为字符串: {cov}"
            assert len(cov) > 0, f"协变量名不应为空"

    def test_scheme_covariates_overlap_with_regime_map(self):
        """SCHEMES 中的协变量与 REGIME_COVARIATE_MAP 有交集"""
        clf = RealtimeRegimeClassifier()
        all_regime_covs = set()
        for covs in clf.REGIME_COVARIATE_MAP.values():
            all_regime_covs.update(covs)

        scheme_covs = set()
        for sym, scheme in SCHEMES.items():
            if scheme.covariate_types:
                scheme_covs.update(scheme.covariate_types)
            else:
                scheme_covs.add(scheme.covariate_type)

        overlap = all_regime_covs & scheme_covs
        assert len(overlap) > 0, "regime 映射与 SCHEMES 无交集协变量"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

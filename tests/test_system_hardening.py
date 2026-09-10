import numpy as np
import pytest
from task_FM.evaluations.fm_eval.evaluator import effective_sample_size


class TestSPEC004EffectiveSampleSize:
    """SPEC-004: Bartlett full-kernel effective sample size"""

    def test_default_rho09_returns_71(self):
        """H=24, S=2, K=11, VIF~8.237 -> n_eff=71"""
        assert effective_sample_size(589, 24, 2) == 71

    def test_no_overlap_returns_nominal(self):
        assert effective_sample_size(100, 24, 24) == 100

    def test_monotonicity_higher_rho_lower_neff(self):
        n_high = effective_sample_size(589, 24, 2, 0.9)
        n_low = effective_sample_size(589, 24, 2, 0.5)
        assert n_high < n_low

    def test_rho05_range(self):
        n_eff = effective_sample_size(589, 24, 2, 0.5)
        assert 120 <= n_eff <= 250

    def test_minimum_is_one(self):
        assert effective_sample_size(1, 24, 2) >= 1


class TestSPEC005ConfidenceBand:
    """SPEC-005: Col 0 isolated log monotonic confidence band"""

    def test_no_crossing_col1_to_col9(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        for t in range(24):
            for i in range(1, 9):
                assert adjusted[t, i] <= adjusted[t, i + 1]

    def test_col0_unchanged(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 0], q[:, 0], rtol=1e-6)

    def test_all_positive(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        assert np.all(adjusted > 0)

    def test_median_unchanged(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 2.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_allclose(adjusted[:, 5], q[:, 5], rtol=1e-6)

    def test_mult_1_passthrough(self):
        from config.prediction_scheme import confidence_band, VarietyScheme
        q = np.tile([100, 102, 104, 106, 108, 110, 112, 114, 116, 118], (24, 1))
        scheme = VarietyScheme.__new__(VarietyScheme)
        scheme.confidence_multiplier = 1.0
        adjusted = confidence_band(q, scheme)
        np.testing.assert_array_equal(adjusted, q)

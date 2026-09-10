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

"""Tests for diversity_alert: KL/JS divergence + minimum sample gate."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from diversity_alert import (
    compute_diversity_alert,
    compute_js_divergence,
    compute_kl_divergence,
)


# --- KL divergence ---

def test_kl_identical_distributions():
    kl = compute_kl_divergence([0.25, 0.25, 0.25, 0.25], [0.25, 0.25, 0.25, 0.25])
    assert abs(kl) < 1e-6


def test_kl_with_zero_probability():
    p = [0.5, 0.5, 0.0]
    q = [0.33, 0.33, 0.34]
    kl = compute_kl_divergence(p, q, epsilon=1e-3)
    assert not math.isnan(kl)
    assert not math.isinf(kl)
    assert kl > 0


def test_kl_mismatched_lengths_returns_zero():
    assert compute_kl_divergence([0.5, 0.5], [0.33, 0.33, 0.34]) == 0.0


def test_kl_empty_returns_zero():
    assert compute_kl_divergence([], []) == 0.0


def test_kl_nonnegative():
    kl = compute_kl_divergence([10, 1, 1], [1, 1, 10])
    assert kl >= 0


# --- JS divergence ---

def test_js_identical_distributions():
    js = compute_js_divergence([0.5, 0.5], [0.5, 0.5])
    assert abs(js) < 1e-6


def test_js_symmetric():
    p, q = [3, 1], [1, 3]
    assert abs(compute_js_divergence(p, q) - compute_js_divergence(q, p)) < 1e-9


def test_js_bounded():
    js = compute_js_divergence([100, 1], [1, 100])
    assert 0 <= js <= math.log(2) + 1e-6


# --- diversity alert gate ---

def test_minimum_sample_size_not_triggered():
    feedback = [{"cov_family": "basis"}] * 10 + [{"cov_family": "momentum"}] * 5
    alert = compute_diversity_alert(feedback)
    assert alert["triggered"] is False
    assert alert["reason"] == "sample_size_too_small"
    assert alert["n"] == 15


def test_single_bin_is_uniform():
    feedback = [{"cov_family": "basis"}] * 30
    alert = compute_diversity_alert(feedback, threshold=0.0)
    # single bin = perfectly uniform, KL=0, strict > 0.0 means not triggered
    assert alert["triggered"] is False
    assert alert["n_samples"] == 30


def test_uniform_distribution_not_triggered():
    # 4 families, 25 each = 100 total, perfectly uniform -> KL=0
    feedback = []
    for fam in ["a", "b", "c", "d"]:
        feedback.extend([{"cov_family": fam}] * 25)
    alert = compute_diversity_alert(feedback, threshold=0.01)
    assert alert["triggered"] is False
    assert alert["kl_divergence"] < 0.01


def test_skewed_distribution_triggers():
    # 90% in one bin -> high KL vs uniform
    feedback = [{"cov_family": "basis"}] * 90
    for fam in ["b", "c", "d", "e"]:
        feedback.extend([{"cov_family": fam}] * 2 + [{"cov_family": fam}])
    # total: 90 + 5*3 = 105, heavily skewed
    alert = compute_diversity_alert(feedback, threshold=0.1)
    assert alert["triggered"] is True
    assert alert["kl_divergence"] > 0.1


def test_no_valid_keys():
    feedback = [{"other_field": "x"}] * 50
    alert = compute_diversity_alert(feedback)
    assert alert["triggered"] is False
    assert alert["reason"] == "no_valid_keys"

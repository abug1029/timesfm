# tests/test_evaluation_metrics.py
from __future__ import annotations
import numpy as np
from cascade.evaluation_metrics import safe_path_corr

def test_safe_path_corr_normal_case():
    pred = [1.0, 2.0, 3.0, 4.0, 5.0]
    real = [1.1, 2.1, 3.1, 4.1, 5.1]
    result = safe_path_corr(pred, real)
    assert result is not None
    assert 0.99 < result <= 1.0

def test_safe_path_corr_none_input():
    assert safe_path_corr(None, [1, 2, 3]) is None
    assert safe_path_corr([1, 2, 3], None) is None

def test_safe_path_corr_short_or_mismatch():
    assert safe_path_corr([1.0], [2.0]) is None
    assert safe_path_corr([], []) is None
    assert safe_path_corr([1.0, 2.0], [1.0, 2.0, 3.0]) is None

def test_safe_path_corr_nan_and_zero_variance():
    assert safe_path_corr([1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 3.0, 4.0]) == 0.0
    assert safe_path_corr([5.0, 5.0, 5.0, 5.0], [1.0, 2.0, 3.0, 4.0]) == 0.0

def test_safe_path_corr_2d_ravel():
    pred = np.array([[1.0], [2.0], [3.0], [4.0]])
    real = np.array([[1.1], [2.1], [3.1], [4.1]])
    result = safe_path_corr(pred, real)
    assert result is not None and 0.99 < result <= 1.0

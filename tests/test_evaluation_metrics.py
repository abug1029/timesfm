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

from cascade.evaluation_metrics import calc_prediction_quality, fallback_n_eff

def test_fallback_n_eff_nonoverlap_step24():
    # 与 backtest_config.STEP=24 一致: h=1, factor=1, n_eff=n
    assert fallback_n_eff(588, horizon=24, step=24) == 588

def test_fallback_n_eff_spec_example_step2():
    # 规格公式在 step=2 时约 72；本仓库默认不用这条，但迁移若误传 step=2 必须可复现
    n_eff = fallback_n_eff(588, horizon=24, step=2)
    assert 70 <= n_eff <= 75

def test_calc_prediction_quality_endpoint_only():
    result = calc_prediction_quality(
        [100.0, 200.0, 300.0, 400.0],
        [105.0, 195.0, 310.0, 390.0],
        [100.0, 200.0, 300.0, 400.0],
    )
    assert result["n"] == 4
    assert 0.0 <= result["dir_acc"] <= 1.0
    assert result["endpoint_mape"] >= 0.0
    assert result["path_corr"] is None
    assert result["mae"] is None and result["mape"] is None and result["decay"] is None

def test_calc_prediction_quality_dir_ok_zero_delta():
    # base=[100,200,300]; real deltas = 0, +5, 0; pred deltas = +5, +5, 0
    # 点1 真实无变动 → False; 点2 同号 → True; 点3 真实无变动 → False → 1/3
    result = calc_prediction_quality(
        [105.0, 205.0, 300.0],
        [100.0, 205.0, 300.0],
        [100.0, 200.0, 300.0],
    )
    assert abs(result["dir_acc"] - 1.0 / 3.0) < 1e-6

def test_calc_prediction_quality_endpoint_mape_floor():
    result = calc_prediction_quality([0.5, 0.6], [0.4, 0.5], [0.5, 0.6])
    assert abs(result["endpoint_mape"] - 10.0) < 1e-6

def test_calc_prediction_quality_weighted_dir_acc_all_flat():
    result = calc_prediction_quality([100.0, 100.0], [100.0, 100.0], [100.0, 100.0])
    assert abs(result["weighted_dir_acc"] - 0.5) < 1e-6

def test_calc_prediction_quality_length_mismatch_raises():
    try:
        calc_prediction_quality([100.0, 200.0], [105.0], [100.0, 200.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_calc_prediction_quality_path_length_mismatch():
    """Path count != endpoint count should raise ValueError, not IndexError"""
    pred_paths = np.arange(100.0, 124.0).reshape(1, 24)  # 1 path
    real_paths = pred_paths + 0.5
    try:
        calc_prediction_quality(
            [123.0, 123.0],  # 2 endpoints
            [123.5, 123.5],
            [100.0, 100.0],
            pred_paths,  # 1 path != 2 endpoints
            real_paths,
        )
    except ValueError as e:
        assert "pred_paths length" in str(e)
        return
    raise AssertionError("expected ValueError for path length mismatch")


def test_calc_prediction_quality_real_path_length_mismatch():
    """real_paths count != endpoint count should raise ValueError"""
    pred_paths = np.arange(100.0, 124.0).reshape(2, 12)  # 2 paths
    real_paths = np.arange(100.0, 112.0).reshape(1, 12)  # 1 path
    try:
        calc_prediction_quality(
            [123.0, 123.0],  # 2 endpoints
            [123.5, 123.5],
            [100.0, 100.0],
            pred_paths,
            real_paths,  # 1 path != 2 endpoints
        )
    except ValueError as e:
        assert "real_paths length" in str(e)
        return
    raise AssertionError("expected ValueError for real_paths length mismatch")

def test_calc_prediction_quality_with_paths():
    pred_paths = np.tile(np.arange(100.0, 124.0), (2, 1))
    real_paths = pred_paths + 0.5
    result = calc_prediction_quality(
        [123.0, 123.0], [123.5, 123.5], [100.0, 100.0],
        pred_paths, real_paths,
    )
    assert result["path_corr"] is not None
    assert result["mae"] is not None and result["decay"] is not None


def test_fallback_n_eff_default_from_config():
    """Default should read from backtest_config (WSL: STEP=2)"""
    # WSL: HORIZON=24, STEP=2 → h=12, factor≈8.03, n_eff≈73
    n_eff = fallback_n_eff(588)
    assert 70 <= n_eff <= 75, f"Expected n_eff≈73 for STEP=2, got {n_eff}"

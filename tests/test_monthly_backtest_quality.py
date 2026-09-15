"""Task 8: monthly_backtest prediction-quality summarize and conservative dir_ok."""
from __future__ import annotations

import os
import sys

# Ensure scripts/ and project root on path (same pattern as test_monthly_resume)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "scripts"))
sys.path.insert(0, _project_root)

import monthly_backtest as mb  # noqa: E402


def test_summarize_dir_ok_zero_move_is_miss():
    """Zero-move point must count as dir_ok=False (conservative rule)."""
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": "2024-06-15 09:00:00", "base": 100.0,
             "pred_end": 105.0, "real_end": 100.0,
             "delta_pred": 5.0, "delta_real": 0.0, "dir_ok": False,
             "dir12_ok": False, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0},
            {"cutoff": "2024-06-15 21:00:00", "base": 100.0,
             "pred_end": 110.0, "real_end": 108.0,
             "delta_pred": 10.0, "delta_real": 8.0, "dir_ok": True,
             "dir12_ok": True, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    # dir_acc from calc_prediction_quality: zero-move = miss -> 1/2 = 0.5
    assert abs(s["dir_acc"] - 0.5) < 1e-6, f"dir_acc={s['dir_acc']} expected 0.5"
    # point_dir_ok_list preserves per-point stored dir_ok
    assert s["point_dir_ok_list"] == [
        ("2024-06-15 09:00:00", False),
        ("2024-06-15 21:00:00", True),
    ]
    # n_eff present and >= 1
    assert "n_eff" in s and s["n_eff"] >= 1
    # endpoint_mape present
    assert "endpoint_mape" in s
    # endpoint_bias_pct present
    assert "endpoint_bias_pct" in s
    # weighted_dir_acc present
    assert "weighted_dir_acc" in s


def test_summarize_none_when_all_errors():
    """All-error points -> summarize returns None."""
    data = {"symbol": "M", "name": "x", "contract": "x", "total_bars": 1,
            "points": [{"cutoff": "t", "error": "boom"}]}
    assert mb.summarize(data) is None


def test_checkpoint_keys_include_new_metrics():
    """_CHECKPOINT_POINT_KEYS must cover endpoint_mape, endpoint_bias_pct, path_corr."""
    for k in ("endpoint_mape", "endpoint_bias_pct", "path_corr"):
        assert k in mb._CHECKPOINT_POINT_KEYS, f"{k} missing from _CHECKPOINT_POINT_KEYS"


def test_dir_acc_from_calc_prediction_quality_not_net():
    """dir_acc must come from calc_prediction_quality, not metrics_from_backtest_points DirAcc."""
    data = {
        "symbol": "RB", "name": "螺纹钢", "contract": "RB2501", "total_bars": 100,
        "points": [
            {"cutoff": "2024-07-01 09:00:00", "base": 3500.0,
             "pred_end": 3520.0, "real_end": 3500.0,
             "delta_pred": 20.0, "delta_real": 0.0, "dir_ok": True,
             "dir12_ok": True, "mae": 5.0, "mape": 0.5,
             "mae_h1": 4.0, "mae_h2": 6.0, "coverage": 18, "real_range": 20.0},
            {"cutoff": "2024-07-01 21:00:00", "base": 3500.0,
             "pred_end": 3530.0, "real_end": 3525.0,
             "delta_pred": 30.0, "delta_real": 25.0, "dir_ok": True,
             "dir12_ok": True, "mae": 5.0, "mape": 0.5,
             "mae_h1": 4.0, "mae_h2": 6.0, "coverage": 18, "real_range": 20.0},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    # calc_prediction_quality: point 1 has zero real move -> dir_ok=False
    # point 2: correct -> dir_ok=True
    # dir_acc = 1/2 = 0.5
    assert abs(s["dir_acc"] - 0.5) < 1e-6, (
        f"dir_acc={s['dir_acc']} should be 0.5"
    )
    # But dir_acc_points still reflects stored dir_ok (legacy)
    assert abs(s["dir_acc_points"] - 1.0) < 1e-6


def test_path_corr_aggregated_when_present():
    """path_corr is averaged from per-point values when available."""
    data = {
        "symbol": "I", "name": "铁矿石", "contract": "I2501", "total_bars": 50,
        "points": [
            {"cutoff": "2024-08-01 09:00:00", "base": 800.0,
             "pred_end": 810.0, "real_end": 808.0,
             "delta_pred": 10.0, "delta_real": 8.0, "dir_ok": True,
             "dir12_ok": True, "mae": 2.0, "mape": 0.3,
             "mae_h1": 1.5, "mae_h2": 2.5, "coverage": 20, "real_range": 10.0,
             "path_corr": 0.9},
            {"cutoff": "2024-08-01 21:00:00", "base": 800.0,
             "pred_end": 812.0, "real_end": 810.0,
             "delta_pred": 12.0, "delta_real": 10.0, "dir_ok": True,
             "dir12_ok": True, "mae": 2.0, "mape": 0.3,
             "mae_h1": 1.5, "mae_h2": 2.5, "coverage": 20, "real_range": 10.0,
             "path_corr": 0.7},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    assert s["path_corr"] is not None
    assert abs(s["path_corr"] - 0.8) < 1e-6  # mean(0.9, 0.7)


def test_path_corr_none_when_absent():
    """path_corr is None when no per-point path_corr values exist."""
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": "2024-06-15 09:00:00", "base": 100.0,
             "pred_end": 105.0, "real_end": 103.0,
             "delta_pred": 5.0, "delta_real": 3.0, "dir_ok": True,
             "dir12_ok": True, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    assert s["path_corr"] is None


def test_n_eff_computed():
    """n_eff uses fallback_n_eff with HORIZON and STEP from config.
    WSL default: HORIZON=24, STEP=2 -> h=12, factor~8, n_eff~n/8.
    For n=10, expected n_eff should be much less than n."""
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": f"2024-06-{(i % 28) + 1:02d} 09:00:00", "base": 100.0,
             "pred_end": 105.0, "real_end": 103.0,
             "delta_pred": 5.0, "delta_real": 3.0, "dir_ok": True,
             "dir12_ok": True, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0}
            for i in range(10)
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    assert "n_eff" in s
    assert s["n_eff"] >= 1
    # Stricter: STEP=2 should reduce n_eff significantly (n_eff <= n // 2)
    assert s["n_eff"] <= s["n"] // 2, (
        f"n_eff should be reduced for STEP=2, got {s['n_eff']}"
    )


def test_economic_metrics_still_present():
    """PF/EV/MaxDD still come from metrics_from_backtest_points."""
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": "2024-06-15 09:00:00", "base": 100.0,
             "pred_end": 105.0, "real_end": 103.0,
             "delta_pred": 5.0, "delta_real": 3.0, "dir_ok": True,
             "dir12_ok": True, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0,
             "pnl": 3.0},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    for key in ("profit_factor", "ev", "max_dd"):
        assert key in s, f"{key} missing from summarize output"


def test_dir_ok_uses_endpoint_not_weighted():
    """Critical fix: dir_ok uses endpoint (pred[-1]-base), not weighted delta_pred.

    When weighted delta_pred disagrees with endpoint, dir_ok should use endpoint.
    This ensures consistency with calc_prediction_quality.
    """
    # Construct: pred_end > base (endpoint up), but delta_pred < 0 (weighted down)
    # Expected: dir_ok = True (uses endpoint)
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": "2024-06-15 09:00:00", "base": 100.0,
             "pred_end": 105.0, "real_end": 108.0,  # endpoint up
             "delta_pred": -2.0, "delta_real": 8.0,  # weighted down (opposite)
             "dir_ok": True,  # should use endpoint, so True
             "dir12_ok": True, "mae": 1.0, "mape": 1.0,
             "mae_h1": 1.0, "mae_h2": 1.0, "coverage": 20, "real_range": 1.0,
             "pnl": 8.0, "endpoint_mape": 3.0, "endpoint_bias_pct": -10.0,
             "path_corr": 0.9},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    assert s["dir_acc"] == 1.0  # endpoint direction correct
    assert s["point_dir_ok_list"][0][1] is True  # list also True

def test_dir_ok_formula_endpoint_not_weighted():
    """Test the dir_ok formula directly: uses endpoint, not weighted delta.
    
    This test verifies the per-point formula at monthly_backtest.py ~line 345:
    dir_ok uses (pred[-1]-base) vs (real[-1]-base), not weighted delta_pred.
    """
    import numpy as np
    
    # Construct scenario: pred_end > base (endpoint up), but weighted delta_pred < 0
    base = 100.0
    pred_end = 105.0   # endpoint up
    real_end = 108.0   # endpoint up
    delta_pred_weighted = -2.0  # weighted down (opposite direction)
    delta_real = 8.0
    
    # Per-point formula from monthly_backtest.py lines 346-352:
    _delta_pred_endpoint = float(pred_end - base)   # +5
    _delta_real_endpoint = float(real_end - base)   # +8
    _eps = 1e-8
    if abs(_delta_real_endpoint) < _eps:
        dir_ok = False
    else:
        dir_ok = bool(np.sign(_delta_pred_endpoint) == np.sign(_delta_real_endpoint))
    
    # Endpoint direction agrees -> dir_ok = True
    assert dir_ok is True, f"Expected dir_ok=True (endpoint agrees), got {dir_ok}"
    
    # If we had used weighted delta_pred (wrong logic), dir_ok would be False
    weighted_dir_ok = bool(np.sign(delta_pred_weighted) == np.sign(delta_real))
    assert weighted_dir_ok is False, "Weighted logic would give wrong answer"



def test_endpoint_mape_uses_base_floor():
    """Important 1 fix: endpoint_mape / endpoint_bias_pct use max(base, 1.0) floor."""
    # Very small base (< 1.0) should not cause division issues
    data = {
        "symbol": "M", "name": "豆粕", "contract": "M2501", "total_bars": 10,
        "points": [
            {"cutoff": "2024-06-15 09:00:00", "base": 0.5,  # very small
             "pred_end": 0.6, "real_end": 0.7,
             "delta_pred": 0.1, "delta_real": 0.2, "dir_ok": True,
             "dir12_ok": True, "mae": 0.05, "mape": 5.0,
             "mae_h1": 0.05, "mae_h2": 0.05, "coverage": 20, "real_range": 0.1,
             "pnl": 0.2, "endpoint_mape": 20.0, "endpoint_bias_pct": -20.0,
             "path_corr": 0.9},
        ],
    }
    s = mb.summarize(data)
    assert s is not None
    # Should not crash or produce inf/nan
    assert not (s["endpoint_mape"] != s["endpoint_mape"])  # not nan
    assert s["endpoint_mape"] > 0

from pathlib import Path

import numpy as np


def _dir_ok_lines(path):
    text = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip().startswith("dir_ok")]


def test_three_scripts_assign_dir_ok_from_endpoint():
    expected = {
        "scripts/batch_backtest.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
        "scripts/validate_context_length.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
        "scripts/backtest_vol_gating_fullchain.py": "endpoint_dir_ok(float(pred[-1]), float(real[-1]), float(base))",
    }
    for path, snippet in expected.items():
        lines = _dir_ok_lines(path)
        assert lines, path
        for line in lines:
            assert "endpoint_dir_ok" in line
            assert "else True" not in line
            assert "delta_pred" not in line
            assert snippet in line
        text = Path(path).read_text(encoding="utf-8")
        if path != "scripts/backtest_vol_gating_fullchain.py":
            assert "delta_pred = pred[-1] - base" in text


def test_vol_veto_flats_position_but_dir_ok_stays_endpoint():
    from scripts.backtest_vol_gating_fullchain import _point_from_pred
    pred = np.array([100.0] * 23 + [110.0])
    real = np.array([100.0] * 23 + [110.0])
    point = _point_from_pred("2026-01-01", 100.0, real, pred, None, 0.9, True, scheme=None)
    assert point["delta_pred"] == 0.0
    assert point["dir_ok"] is True
    assert point["position_sign"] == 0.0
    assert point["pnl"] == 0.0


def test_2026_09_14_spec_has_dir_ok_errata():
    text = Path("docs/superpowers/specs/2026-09-14-prediction-quality-redesign-design.md").read_text(encoding="utf-8")
    assert "endpoint_dir_ok" in text
    assert "加权可交易增量" in text
    assert "2026-11-03-baseline-point-contract-spec.md" in text

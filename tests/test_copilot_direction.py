"""CF-01 A: Copilot card tradable direction is weighted 1H; daily is regime only."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from config.prediction_scheme import VarietyScheme
from cascade.signal_contract import position_from_forecast
from scripts.copilot import (
    CopilotCard,
    copilot_trade_signal,
    generate_risk_bounds,
    write_markdown,
    _render_cli_plain,
)


def _full_scheme(**kw) -> VarietyScheme:
    defaults = dict(
        symbol="xx", name="test", scheme_type="trend",
        use_full_signal=True, short_horizon_only=False, decay=1.35,
        trend_threshold_pct=0.1,
    )
    defaults.update(kw)
    return VarietyScheme(**defaults)


def test_trade_direction_is_weighted_1h_regime_is_daily():
    """CF-01 A: 可交易方向=1H 加权；日线 thr 只进 regime_direction。"""
    scheme = _full_scheme(trend_threshold_pct=0.1)
    fc = np.linspace(100, 105, 24)
    # slope 0.0005 fraction/day → 0.05 %/day < 0.1 thr → regime 中性
    sig = copilot_trade_signal(fc, 100.0, scheme, daily_slope=0.0005)
    assert sig["direction"].startswith("看多"), sig["direction"]
    assert sig["regime_direction"] is not None
    assert sig["regime_direction"].startswith("中性"), sig["regime_direction"]

    ref = position_from_forecast(fc, 100.0, scheme=scheme, daily_slope=0.0005)
    expected_pct = (float(ref["weighted_pred"]) / 100.0 - 1.0) * 100.0
    endpoint_pct = (105.0 / 100.0 - 1.0) * 100.0
    assert abs(sig["delta_pct"] - expected_pct) < 1e-10
    assert abs(sig["delta_pct"] - endpoint_pct) > 1e-6
    assert abs(sig["weighted_pred"] - float(ref["weighted_pred"])) < 1e-10


def test_risk_bounds_follow_tradable_not_regime():
    """止损跟可交易 1H 方向，不跟日线中性。"""
    scheme = _full_scheme(trend_threshold_pct=0.1)
    fc = np.linspace(100, 105, 24)
    sig = copilot_trade_signal(fc, 100.0, scheme, daily_slope=0.0005)
    lines = generate_risk_bounds(sig["direction"], p10=99.0, p90=106.0, tick_size=1.0)
    assert any("多头防线" in l for l in lines)
    assert not any("观望" in l for l in lines)


def _card(**kw) -> CopilotCard:
    defaults = dict(
        symbol="xx",
        name="test",
        current_price=100.0,
        direction="看多 ↑",
        t4=101.0,
        t12=102.0,
        t24=105.0,
        delta_pct=1.5,
        point_forecast=[100.0 + i * 0.2 for i in range(24)],
        p10=[99.0] * 24,
        p90=[106.0] * 24,
        daily_slope=0.05,
        cov_label="ccl",
        scheme_type="trend",
        vol={"high_vol": False, "vol_prob": 0.1, "message": "正常"},
        kb={},
        regime_direction="中性 →",
    )
    defaults.update(kw)
    return CopilotCard(**defaults)


def test_markdown_prints_tradable_and_regime(tmp_path: Path):
    path = tmp_path / "copilot.md"
    write_markdown([_card()], "2026-09-11", path)
    text = path.read_text(encoding="utf-8")
    assert "可交易方向" in text
    assert "日线状态" in text
    assert "看多" in text
    assert "中性" in text


def test_cli_plain_prints_tradable_and_regime(capsys):
    _render_cli_plain([_card()], "2026-09-11")
    out = capsys.readouterr().out
    assert "可交易方向" in out
    assert "日线状态" in out
    assert "看多" in out
    assert "中性" in out

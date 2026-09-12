import pytest
import numpy as np
from scripts.copilot import quantize_price, _price_format, generate_risk_bounds, craft_advisory


def test_risk_bounds_long():
    lines = generate_risk_bounds('看多 ↑', p10=14380, p90=14660, tick_size=5.0)
    assert any('多头防线' in l for l in lines)
    assert any('P10' in l for l in lines)


def test_risk_bounds_short():
    lines = generate_risk_bounds('看空 ↓', p10=14380, p90=14660, tick_size=5.0)
    assert any('空头防线' in l for l in lines)
    assert any('P90' in l for l in lines)


def test_risk_bounds_neutral():
    lines = generate_risk_bounds('中性 →', p10=14380, p90=14660, tick_size=5.0)
    assert any('观望' in l for l in lines)


def test_risk_bounds_tick_snapping_long():
    lines = generate_risk_bounds('看多 ↑', p10=14382.4, p90=14663.2, tick_size=5.0)
    assert any('14370' in l for l in lines), 'Long stop not snapped to tick grid'
    assert not any('14372' in l for l in lines), 'Illegal non-tick price in output'


def test_risk_bounds_tick_snapping_short():
    lines = generate_risk_bounds('看空 ↓', p10=14382.4, p90=14663.2, tick_size=5.0)
    assert any('14675' in l for l in lines), 'Short stop not snapped to tick grid'


def test_risk_bounds_floor_protection():
    lines = generate_risk_bounds('看多 ↑', p10=3.0, p90=5.0, tick_size=2.0, stop_buffer_ticks=2)
    assert any('2' in l for l in lines), 'Stop should be floored to tick_size'
    for l in lines:
        if '止损' in l:
            assert '-' not in l, f'Stop price should not be negative: {l}'


def test_quantize_price_floor():
    assert quantize_price(14372.4, 5.0, 'floor') == 14370.0
    assert quantize_price(14370.0, 5.0, 'floor') == 14370.0
    assert quantize_price(580.25, 0.02, 'floor') == 580.24


def test_quantize_price_ceil():
    assert quantize_price(14372.4, 5.0, 'ceil') == 14375.0
    assert quantize_price(14375.0, 5.0, 'ceil') == 14375.0


def test_quantize_price_round():
    assert quantize_price(14372.4, 5.0, 'round') == 14370.0
    assert quantize_price(14373.0, 5.0, 'round') == 14375.0


def test_price_format_integer_tick():
    assert _price_format(14380.0, 5.0) == '14380'
    assert _price_format(580.24, 0.02) == '580.24'


def test_price_format_decimal_tick():
    assert _price_format(14500.5, 0.1) == '14500.5'


def test_craft_advisory_weighted_not_t24():
    lines = craft_advisory("xx", {}, "看多 ↑", 1.5, {"high_vol": False}, "trend")
    joined = "\n".join(lines)
    assert "加权涨跌" in joined
    assert "T+24 预期" not in joined

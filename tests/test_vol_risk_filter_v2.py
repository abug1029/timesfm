import numpy as np
import pytest
from cascade.vol_risk_filter import apply_neutral_override_v2


def test_neutral_override_quantile_spread():
    point = np.array([100.0] * 24)
    quant = np.tile([95,98,99,99.5,100,100,100.5,101,103,106], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=2.0, tick_size=1.0)
    assert np.all(flat_p == 100.0)
    assert flat_q.shape == (24, 10)
    for t in range(24):
        for i in range(1, 9):
            assert flat_q[t, i] <= flat_q[t, i+1], f'Bar {t}: col{i} > col{i+1}'
    ci_width = flat_q[-1, -1] - flat_q[-1, 1]
    assert ci_width > 0, f'CI width should be > 0, got {ci_width}'


def test_neutral_override_median_strict_unmoved():
    point = np.array([100.0] * 24)
    quant = np.tile([95, 98, 99, 99.5, 100, 100, 100.5, 101, 102, 106], (24, 1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=4.0, tick_size=1.0)
    assert np.allclose(flat_q[:, 5], 100.0), f'P50 drift: {flat_q[:, 5]}'


def test_neutral_override_col0_is_mean():
    point = np.array([100.0] * 24)
    quant = np.tile([95, 98, 99, 99.5, 100, 100, 100.5, 101, 102, 106], (24, 1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=4.0, tick_size=1.0)
    assert np.allclose(flat_q[:, 0], 100.0), f'Col 0 drift: {flat_q[:, 0]}'


def test_neutral_override_full_symmetric_layers():
    point = np.array([100.0] * 24)
    quant = np.tile([95, 98, 99, 99.5, 100, 100, 100.5, 101, 102, 106], (24, 1))
    _, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=4.0, tick_size=1.0)
    for delta in range(1, 5):
        down = flat_q[:, 5] - flat_q[:, 5 - delta]
        up = flat_q[:, 5 + delta] - flat_q[:, 5]
        assert np.allclose(down, up, rtol=1e-5), f'delta={delta} asymmetric: down={down[0]:.4f}, up={up[0]:.4f}'


def test_neutral_override_no_internal_gap():
    point = np.array([100.0] * 24)
    quant = np.tile([95, 98, 99, 99.5, 100, 100, 100.5, 101, 102, 106], (24, 1))
    _, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=4.0, tick_size=1.0)
    gap_left = flat_q[0, 5] - flat_q[0, 4]
    gap_right = flat_q[0, 6] - flat_q[0, 5]
    ratio = gap_right / gap_left if gap_left > 0 else 0.0
    assert 0.9 <= ratio <= 1.1, f'Internal gap! left={gap_left:.4f}, right={gap_right:.4f}, ratio={ratio:.2f}'


def test_neutral_override_price_floor():
    point = np.array([50.0] * 24)
    quant = np.tile([45,47,48,49,50,51,52,53,55,58], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 50.0, quant, atr=10.0, tick_size=0.5)
    assert np.all(flat_q >= 0.5), 'Price must not go below tick_size'


def test_neutral_override_none_quantile():
    point = np.array([100.0] * 24)
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, None, atr=2.0, tick_size=1.0)
    assert flat_q is None


def test_neutral_override_atr_zero():
    point = np.array([100.0] * 24)
    quant = np.tile([95,98,99,99.5,100,100.5,101,102,103,106], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=0.0, tick_size=1.0)
    assert np.allclose(flat_q, 100.0)


def test_neutral_override_atr_nan():
    point = np.array([100.0] * 24)
    quant = np.tile([95,98,99,99.5,100,100.5,101,102,103,106], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=float('nan'), tick_size=1.0)
    assert np.allclose(flat_q, 100.0)


def test_neutral_override_dynamic_columns():
    point = np.array([100.0] * 24)
    quant_5col = np.tile([98,99,100,101,102], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant_5col, atr=2.0, tick_size=1.0)
    assert flat_q.shape[1] == 5, f'Expected 5 columns, got {flat_q.shape[1]}'


def test_neutral_override_even_columns():
    """Even n_q should NOT force middle column to z=0"""
    point = np.array([100.0] * 24)
    quant_4col = np.tile([97, 99, 101, 103], (24, 1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant_4col, atr=2.0, tick_size=1.0)
    assert flat_q.shape[1] == 4
    # For even n_q=4, no column should be forced to exactly base_price
    # (unless z-score naturally lands there). Check monotonicity holds.
    for t in range(24):
        for i in range(3):
            assert flat_q[t, i] <= flat_q[t, i+1], f"Bar {t}: col{i} > col{i+1}"


def test_neutral_override_zero_columns():
    """Zero-column quantile forecast should return None"""
    point = np.array([100.0] * 24)
    quant_0col = np.empty((24, 0))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant_0col, atr=2.0, tick_size=1.0)
    assert flat_q is None


def test_neutral_override_atr_inf():
    """Inf ATR should be treated same as NaN/zero"""
    point = np.array([100.0] * 24)
    quant = np.tile([95,98,99,99.5,100,100.5,101,102,103,106], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=float('inf'), tick_size=1.0)
    assert np.allclose(flat_q, 100.0)


def test_neutral_override_even_columns():
    """Even n_q should NOT force middle column to z=0"""
    point = np.array([100.0] * 24)
    quant_4col = np.tile([97, 99, 101, 103], (24, 1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant_4col, atr=2.0, tick_size=1.0)
    assert flat_q.shape[1] == 4
    # For even n_q=4, no column should be forced to exactly base_price
    # (unless z-score naturally lands there). Check monotonicity holds.
    for t in range(24):
        for i in range(3):
            assert flat_q[t, i] <= flat_q[t, i+1], f"Bar {t}: col{i} > col{i+1}"


def test_neutral_override_zero_columns():
    """Zero-column quantile forecast should return None"""
    point = np.array([100.0] * 24)
    quant_0col = np.empty((24, 0))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant_0col, atr=2.0, tick_size=1.0)
    assert flat_q is None


def test_neutral_override_atr_inf():
    """Inf ATR should be treated same as NaN/zero"""
    point = np.array([100.0] * 24)
    quant = np.tile([95,98,99,99.5,100,100.5,101,102,103,106], (24,1))
    flat_p, flat_q = apply_neutral_override_v2(point, 100.0, quant, atr=float("inf"), tick_size=1.0)
    assert np.allclose(flat_q, 100.0)

"""Tests for statistical tests module."""
import numpy as np
from cascade.statistical_tests import safe_normalize_cutoff, pair_dir_ok_series


def test_safe_normalize_cutoff_naive_shanghai():
    ts = safe_normalize_cutoff("2024-06-15 09:00:00")
    assert ts == safe_normalize_cutoff("2024-06-15T09:00:00")
    assert ts is not None


def test_safe_normalize_cutoff_unix_seconds_not_ns():
    # 1718413200 = 2024-06-15 01:00:00 UTC = 09:00 Asia/Shanghai
    assert safe_normalize_cutoff(1718413200) == 1718413200
    assert safe_normalize_cutoff(1718413200000) == 1718413200  # ms
    assert safe_normalize_cutoff("1718413200") == 1718413200


def test_safe_normalize_cutoff_tz_aware_converts():
    utc = safe_normalize_cutoff("2024-06-15 01:00:00+00:00")
    local = safe_normalize_cutoff("2024-06-15 09:00:00")
    assert utc == local


def test_safe_normalize_cutoff_none():
    assert safe_normalize_cutoff(None) is None
    assert safe_normalize_cutoff("not-a-time") is None


def test_pair_dir_ok_inner_join_sorted():
    variant = [
        ("2024-06-15 11:00:00", True),
        ("2024-06-15 09:00:00", False),
        ("2024-06-15 10:00:00", True),
    ]
    baseline = [
        {"cutoff": "2024-06-15 09:00:00", "dir_ok": True},
        {"cutoff": "2024-06-15 11:00:00", "dir_ok": False},
        {"cutoff": "2024-06-15 12:00:00", "dir_ok": True},  # variant missing, discard
    ]
    v, b = pair_dir_ok_series(variant, baseline)
    assert v == [0, 1]  # 09:00 False, 11:00 True (sorted by time)
    assert b == [1, 0]


def test_safe_normalize_cutoff_numpy_scalar():
    """numpy 0-d array / numpy scalar should be converted via .item()."""
    val = np.int64(1718413200)
    assert safe_normalize_cutoff(val) == 1718413200

    val_ms = np.float64(1718413200000)
    assert safe_normalize_cutoff(val_ms) == 1718413200


def test_safe_normalize_cutoff_float_input():
    """Plain float seconds / milliseconds should work."""
    assert safe_normalize_cutoff(1718413200.0) == 1718413200
    assert safe_normalize_cutoff(1718413200000.0) == 1718413200


def test_safe_normalize_cutoff_empty_string():
    """Empty / garbage strings return None."""
    assert safe_normalize_cutoff("") is None
    assert safe_normalize_cutoff("not-a-time") is None


def test_safe_normalize_cutoff_none_explicit():
    assert safe_normalize_cutoff(None) is None


def test_safe_normalize_cutoff_z_suffix():
    """Trailing 'Z' should be treated as UTC."""
    z_result = safe_normalize_cutoff("2024-06-15T01:00:00Z")
    plus_result = safe_normalize_cutoff("2024-06-15T01:00:00+00:00")
    assert z_result == plus_result


def test_safe_normalize_cutoff_z_not_in_middle():
    """'Z' only replaced at end, not mid-string."""
    # A string with Z in the middle should fail to parse
    assert safe_normalize_cutoff("2024Z06-15T09:00:00") is None


def test_pair_dir_ok_series_duplicate_timestamps():
    """Later entries for the same cutoff overwrite earlier ones (dict semantics)."""
    variant = [
        ("2024-06-15 09:00:00", False),
        ("2024-06-15 09:00:00", True),  # overwrite
    ]
    baseline = [
        ("2024-06-15 09:00:00", True),
    ]
    v, b = pair_dir_ok_series(variant, baseline)
    assert v == [1]  # last-write-wins: True
    assert b == [1]


def test_pair_dir_ok_series_empty_lists():
    """Empty inputs produce empty outputs."""
    v, b = pair_dir_ok_series([], [])
    assert v == []
    assert b == []


def test_pair_dir_ok_series_missing_dict_keys():
    """Dict points missing required keys are skipped."""
    variant = [
        {"cutoff": "2024-06-15 09:00:00"},  # missing dir_ok
        {"dir_ok": True},  # missing cutoff
        {"cutoff": "2024-06-15 10:00:00", "dir_ok": True},  # valid
    ]
    baseline = [
        {"cutoff": "2024-06-15 10:00:00", "dir_ok": False},
    ]
    v, b = pair_dir_ok_series(variant, baseline)
    assert v == [1]
    assert b == [0]


def test_pair_dir_ok_series_short_tuple():
    """Tuples shorter than 2 elements are skipped."""
    variant = [
        ("2024-06-15 09:00:00",),  # too short
        ("2024-06-15 10:00:00", True),  # valid
    ]
    baseline = [
        ("2024-06-15 10:00:00", False),
    ]
    v, b = pair_dir_ok_series(variant, baseline)
    assert v == [1]
    assert b == [0]

from cascade.statistical_tests import diebold_mariano_p


def test_diebold_mariano_p_identical_is_one():
    x = [1, 0, 1, 0] * 50  # T=200
    assert diebold_mariano_p(x, x) == 1.0


def test_diebold_mariano_p_worse_is_one():
    baseline = [1] * 200
    variant = [0] * 200
    assert diebold_mariano_p(variant, baseline) == 1.0


def test_diebold_mariano_p_length_or_short():
    assert diebold_mariano_p([1, 0, 1], [1, 0]) == 1.0
    assert diebold_mariano_p([1, 0] * 40, [0, 1] * 40) == 1.0  # T=80 < 100


def test_diebold_mariano_p_clear_improvement():
    baseline = [0] * 200
    variant = [1] * 200
    p = diebold_mariano_p(variant, baseline, horizon=24, step=24)
    assert 0.0 <= p < 0.01


def test_diebold_mariano_p_zero_variance_ones():
    ones = [1] * 200
    assert diebold_mariano_p(ones, ones) == 1.0

from cascade.statistical_tests import bh_fdr_promote


def _v(vid, symbol, p, gate=True):
    return {"variant_id": vid, "symbol": symbol, "p_value": p, "gate_pass": gate}


def test_bh_fdr_promote_empty():
    assert bh_fdr_promote([]) == {}


def test_bh_fdr_small_batch_bonferroni():
    updates = bh_fdr_promote([
        _v("var_0", "p", 0.01),
        _v("var_1", "p", 0.02),
        _v("var_2", "p", 0.03),
    ])
    assert updates["var_0"]["fdr_pass"] is True
    assert updates["var_1"]["fdr_pass"] is True
    assert updates["var_2"]["fdr_pass"] is False


def test_bh_fdr_gate_fail_never_passes():
    updates = bh_fdr_promote([
        _v("ok", "p", 0.001, True),
        _v("bad", "p", 0.001, False),
        _v("c", "p", 0.20),
        _v("d", "p", 0.20),
    ], fdr_q=0.10)
    assert updates["ok"]["fdr_pass"] is True
    assert updates["bad"]["fdr_pass"] is False


def test_bh_fdr_per_symbol_independent():
    # 每品种 4 个独立 id
    verdicts = []
    for i in range(4):
        verdicts.append(_v(f"p_{i}", "p", 0.01 + i * 0.01))
        verdicts.append(_v(f"cu_{i}", "cu", 0.20))
    updates = bh_fdr_promote(verdicts, fdr_q=0.10)
    assert any(updates[f"p_{i}"]["fdr_pass"] for i in range(4))
    assert not any(updates[f"cu_{i}"]["fdr_pass"] for i in range(4))


def test_bh_fdr_monotonic():
    verdicts = [_v(f"var_{i}", "p", 0.01 + i * 0.01) for i in range(10)]
    updates = bh_fdr_promote(verdicts, fdr_q=0.10)
    passed = [updates[f"var_{i}"]["fdr_pass"] for i in range(10)]
    for i in range(9):
        if passed[i + 1]:
            assert passed[i] is True


def test_bh_fdr_duplicate_keeps_last():
    verdicts = [
        _v("var_0", "p", 0.01),
        _v("var_0", "p", 0.90),  # 后写
        _v("var_1", "p", 0.02),
        _v("var_2", "p", 0.03),
    ]
    updates = bh_fdr_promote(verdicts)
    assert set(updates) == {"var_0", "var_1", "var_2"}
    assert updates["var_0"]["fdr_pass"] is False  # p=0.90 Bonferroni

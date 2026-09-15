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

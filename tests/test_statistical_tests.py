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

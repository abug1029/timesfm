"""最后一席。只在回放 decision 为 reserve_last_seat 时加入。"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import sup_harvest


def _row(family, score, vid, in_pool=True):
    return {
        "variant_id": vid,
        "_family": family,
        "_score": score,
        "_tier": 0,
        "_pool_family": in_pool,
    }


def test_low_count_family_takes_last_seat():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(rows, 3, set(), {"alpha": 5, "beta": 5, "gamma": 5, "delta": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "d"]


def test_dead_family_does_not_take_reserved_seat():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(
        rows, 3, {"delta"}, {"alpha": 5, "beta": 5, "gamma": 5, "delta": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_top_k_one_uses_current_two_pass():
    rows = [_row("alpha", 40, "a"), _row("beta", 30, "b")]
    picked = sup_harvest.fill_seats(rows, 1, set(), {"alpha": 0, "beta": 0})
    assert [row["variant_id"] for row in picked] == ["a"]


def test_all_zero_counts_match_current_pass_one():
    rows = [
        _row("alpha", 40, "a"),
        _row("beta", 30, "b"),
        _row("gamma", 20, "c"),
        _row("delta", 10, "d"),
    ]
    picked = sup_harvest.fill_seats(rows, 3, set(), {})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_one_family_still_fills_three_seats():
    rows = [_row("alpha", 40, "a"), _row("alpha", 30, "b"), _row("alpha", 20, "c")]
    picked = sup_harvest.fill_seats(rows, 3, set(), {"alpha": 0})
    assert [row["variant_id"] for row in picked] == ["a", "b", "c"]


def test_exact_48h_counts_and_aware_rows_do_not():
    now = datetime(2026, 11, 18, 12, 0, 0)
    exact = (now - timedelta(hours=48)).isoformat()
    early = (now - timedelta(hours=48) - timedelta(microseconds=1)).isoformat()
    late = (now + timedelta(microseconds=1)).isoformat()
    aware = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    text = "".join(
        json.dumps(row) + "\n"
        for row in (
            {"cov_override": "oi", "enqueued_at": exact},
            {"cov_override": "ccl", "enqueued_at": early},
            {"cov_override": "nvi", "enqueued_at": late},
            {"cov_override": "calendar_cyclical", "enqueued_at": aware},
            {"cov_override": "missing", "enqueued_at": exact},
        )
    )
    path = "/tmp/proposal-followup-done.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    pool = {
        "oi": {"family": "alpha"},
        "ccl": {"family": "beta"},
        "nvi": {"family": "gamma"},
        "calendar_cyclical": {"family": "delta"},
    }
    counts = sup_harvest._recent_done_family_counts(path, pool, now)
    assert counts == {"alpha": 1}
    aware_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert sup_harvest._recent_done_family_counts(path, pool, aware_now) is None


def test_seat_functions_do_not_name_inventory_or_calendar():
    import inspect
    for fn in (
        sup_harvest.fill_seats,
        sup_harvest._two_pass_select,
        sup_harvest._recent_done_family_counts,
    ):
        src = inspect.getsource(fn)
        assert "inventory" not in src
        assert "calendar" not in src

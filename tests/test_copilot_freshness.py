"""C6: Copilot must not fall back to stale symbols after freshness check."""
from scripts.copilot import select_copilot_symbols


def test_empty_valid_never_falls_back_to_requested():
    requested = ["ss", "fu"]
    assert select_copilot_symbols(requested, []) == []
    assert requested == ["ss", "fu"]


def test_partial_skip_runs_valid_only():
    requested = ["ss", "fu", "rb"]
    assert select_copilot_symbols(requested, ["ss", "fu"]) == ["ss", "fu"]


def test_all_valid_keeps_valid():
    requested = ["ss", "fu"]
    assert select_copilot_symbols(requested, ["ss", "fu"]) == ["ss", "fu"]

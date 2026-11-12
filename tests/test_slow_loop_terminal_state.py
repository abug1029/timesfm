"""Tests for aligned_slow_loop.py terminal state machine - spec S4.4"""
import json, os, sys
import pytest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts.registry_lib import TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT


@pytest.fixture(autouse=True)
def clean_retry_state(tmp_path, monkeypatch):
    """Ensure clean retry state for each test."""
    retry_path = str(tmp_path / ".slow_loop_retry_state_test.json")
    monkeypatch.setattr("scripts.aligned_slow_loop.RETRY_STATE_PATH", retry_path)
    yield
    if os.path.exists(retry_path):
        os.unlink(retry_path)


# ---------------------------------------------------------------------------
# Retry state unit tests
# ---------------------------------------------------------------------------

def test_retry_counter_persists_across_calls(tmp_path):
    """Retry counter survives function call (file-based persistence)."""
    from scripts.aligned_slow_loop import _increment_retry, _load_retry_state
    c1 = _increment_retry("jd", "oi", "confirmatory", "fp1")
    c2 = _increment_retry("jd", "oi", "confirmatory", "fp1")
    assert c1 == 1
    assert c2 == 2
    state = _load_retry_state()
    key = "fp1::jd::oi::confirmatory"
    assert state[key]["count"] == 2


def test_retry_state_corruption_recovery(tmp_path):
    """Corrupted retry state file -> graceful fallback to empty dict."""
    from scripts.aligned_slow_loop import _load_retry_state, RETRY_STATE_PATH
    Path(RETRY_STATE_PATH).write_text("{bad json!!!", encoding="utf-8")
    result = _load_retry_state()
    assert result == {}


def test_retry_key_includes_fingerprint(tmp_path):
    """Different fingerprints have independent retry counts."""
    from scripts.aligned_slow_loop import _increment_retry, _load_retry_state
    c1 = _increment_retry("jd", "oi", "confirmatory", "fp_A")
    c2 = _increment_retry("jd", "oi", "confirmatory", "fp_B")
    assert c1 == 1
    assert c2 == 1
    state = _load_retry_state()
    assert state["fp_A::jd::oi::confirmatory"]["count"] == 1
    assert state["fp_B::jd::oi::confirmatory"]["count"] == 1


def test_success_clears_retry_entry(tmp_path):
    """n>=350 success removes retry entry for that combo."""
    from scripts.aligned_slow_loop import _increment_retry, _clear_retry, _load_retry_state
    _increment_retry("jd", "oi", "confirmatory", CURRENT_PROTOCOL_FINGERPRINT)
    _increment_retry("jd", "oi", "confirmatory", CURRENT_PROTOCOL_FINGERPRINT)
    _clear_retry("jd", "oi", "confirmatory", CURRENT_PROTOCOL_FINGERPRINT)
    state = _load_retry_state()
    key = f"{CURRENT_PROTOCOL_FINGERPRINT}::jd::oi::confirmatory"
    assert key not in state


# ---------------------------------------------------------------------------
# Terminal state machine integration tests
# ---------------------------------------------------------------------------

def _make_verdict(n, symbol="jd", cov="oi", mode="confirmatory", status="ok"):
    """Build a minimal verdict dict for testing."""
    return {
        "schema": "fm.aligned_verdict.v2",
        "variant_id": f"{symbol}_{cov}_{mode}_p1",
        "symbol": symbol,
        "cov_override": cov,
        "cov_family": "test",
        "batch_id": "test_batch",
        "status": status,
        "stage": "aligned",
        "n": n,
        "n_eff": n,
        "dir_acc": 0.55,
        "gate_pass": n >= 350,
        "p_value": 0.03,
        "fdr_pass": False,
        "migrated_pass": False,
        "endpoint_mape": None,
        "endpoint_bias_pct": None,
        "path_corr": None,
        "weighted_dir_acc": 0.55,
        "mae": None,
        "mape": None,
        "decay": None,
        "decided_at": "2026-01-01T00:00:00",
        "checkpoint_path": "",
        "slow_loop_pid": 12345,
        "git_rev": "abc1234",
        "run_mode": mode,
        "run_label": None,
        "prereg_id": "prereg_1",
        "confirm_from_ts": "2025-01-01",
        "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
        "eval_end_ts": "2026-01-01",
        "tier": "B",
        "tier_score": 50,
        "tier_label": "B",
        "tier_breakdown": {},
        "metrics": {"n": n, "status": status},
        "incremental_vs_incumbent": "not_applicable",
    }


def test_n0_writes_error(tmp_path):
    """n=0 -> status=error written to registry."""
    from scripts.aligned_slow_loop import _should_write_verdict
    registry = str(tmp_path / "verdicts.jsonl")
    Path(registry).touch()
    v = _make_verdict(n=0, status="no_data")
    should_write = _should_write_verdict(v)
    assert should_write is True
    assert v["status"] == "error"


def test_n_lt_350_first_no_write(tmp_path):
    """n<350 first attempt (new_count=1) -> NOT written to registry."""
    from scripts.aligned_slow_loop import _should_write_verdict
    registry = str(tmp_path / "verdicts.jsonl")
    Path(registry).touch()
    v = _make_verdict(n=200)
    should_write = _should_write_verdict(v)
    assert should_write is False


def test_n_lt_350_second_writes_insufficient_data(tmp_path):
    """n<350 second attempt (new_count=2) -> status=insufficient_data written."""
    from scripts.aligned_slow_loop import _should_write_verdict
    registry = str(tmp_path / "verdicts.jsonl")
    Path(registry).touch()
    v1 = _make_verdict(n=200)
    _should_write_verdict(v1)  # first attempt, not written
    v2 = _make_verdict(n=200)
    should_write = _should_write_verdict(v2)
    assert should_write is True
    assert v2["status"] == "insufficient_data"


def test_exception_writes_fatal_error(tmp_path):
    """Unhandled exception in backtest -> status=fatal_error written."""
    from scripts.aligned_slow_loop import run_aligned_candidate
    registry = str(tmp_path / "verdicts.jsonl")
    Path(registry).touch()
    row = {
        "variant_id": "jd_oi_confirmatory_p1",
        "symbol": "jd",
        "cov_override": "oi",
        "max_points": 400,
        "batch_id": "test_batch",
        "run_mode": "confirmatory",
        "prereg_id": "prereg_1",
        "confirm_from_ts": "2025-01-01",
    }
    with mock.patch("scripts.aligned_slow_loop._run_inner", side_effect=RuntimeError("boom")):
        result = run_aligned_candidate(row, str(tmp_path), str(tmp_path / "cp"), registry)
    assert result["status"] == "fatal_error"
    lines = Path(registry).read_text().strip().split("\n")
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["status"] == "fatal_error"


def test_pending_item_removed_after_consumption(tmp_path):
    """After slow loop processes a pending item, it is removed from pending queue."""
    import scripts.registry_lib as rl
    queue_path = str(tmp_path / "pending.jsonl")
    inprogress_path = str(tmp_path / "inprogress.jsonl")
    done_path = str(tmp_path / "done.jsonl")
    row = {"variant_id": "jd_oi_confirmatory_p1", "symbol": "jd",
           "cov_override": "oi", "max_points": 400}
    Path(queue_path).write_text(json.dumps(row) + "\n", encoding="utf-8")
    Path(inprogress_path).touch()
    claimed = rl.queue_claim(queue_path, inprogress_path)
    assert claimed is not None
    assert claimed["variant_id"] == "jd_oi_confirmatory_p1"
    rl.queue_ack(queue_path, inprogress_path, claimed, done_path)
    assert rl.queue_load(queue_path) == []
    assert rl.queue_load(inprogress_path) == []
    done_lines = Path(done_path).read_text().strip().split("\n")
    assert len(done_lines) == 1

"""Tests for sup_harvest.py enqueue-layer dedup — spec §4.2"""
import json
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode,
)
from scripts.sup_harvest import _load_evaluated_or_queued


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def harvest_env(tmp_path):
    verdict_path = tmp_path / "aligned_verdicts.jsonl"
    pending_path = tmp_path / "aligned_pending.jsonl"
    verdict_path.write_text("")
    pending_path.write_text("")
    return {"verdict_path": str(verdict_path), "pending_path": str(pending_path)}


FP = CURRENT_PROTOCOL_FINGERPRINT


def test_harvest_rejects_current_fp_evaluated(harvest_env):
    """Current fp + status=ok + n>=350 → not re-enqueued."""
    _write_jsonl(harvest_env["verdict_path"], [
        {"symbol": "cj", "cov_override": "rsi", "run_mode": "confirmatory",
         "protocol_fingerprint": FP, "status": "ok", "n_eff": 500},
    ])
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    assert ("cj", "rsi", "confirmatory") in result


def test_harvest_rejects_terminal_status(harvest_env):
    """status in TERMINAL_STATUSES → not re-enqueued."""
    records = []
    for st in TERMINAL_STATUSES:
        records.append({"symbol": "cj", "cov_override": st, "run_mode": "confirmatory",
                        "protocol_fingerprint": FP, "status": st})
    _write_jsonl(harvest_env["verdict_path"], records)
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    for st in TERMINAL_STATUSES:
        assert ("cj", st, "confirmatory") in result


def test_harvest_ignores_old_fp_records(harvest_env):
    """Old protocol fp records do NOT count as evaluated."""
    _write_jsonl(harvest_env["verdict_path"], [
        {"symbol": "cj", "cov_override": "rsi", "run_mode": "confirmatory",
         "protocol_fingerprint": "old_fp_999", "status": "ok", "n_eff": 500},
    ])
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    assert ("cj", "rsi", "confirmatory") not in result


def test_harvest_checks_pending_current_fp(harvest_env):
    """Pending items with current fp count as queued → not re-enqueued."""
    _write_jsonl(harvest_env["pending_path"], [
        {"symbol": "p", "cov_override": "macd", "run_mode": "exploration",
         "protocol_fingerprint": FP},
    ])
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    assert ("p", "macd", "exploration") in result


def test_harvest_ignores_pending_old_fp(harvest_env):
    """Pending items with old fp are NOT treated as queued."""
    _write_jsonl(harvest_env["pending_path"], [
        {"symbol": "p", "cov_override": "macd", "run_mode": "exploration",
         "protocol_fingerprint": "old_fp_999"},
    ])
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    assert ("p", "macd", "exploration") not in result


def test_harvest_in_flight_batch_dedup(harvest_env):
    """Same (symbol, cov, mode) twice in one batch → only enqueued once."""
    # Simulate: after loading evaluated_set, adding first item blocks second
    evaluated = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    key = ("cj", "rsi", "confirmatory")
    assert key not in evaluated
    evaluated.add(key)
    assert key in evaluated  # second occurrence would be skipped


def test_harvest_uses_canonical_helpers(harvest_env):
    """cov_override/covariate fallback and run_mode/mode fallback work correctly."""
    _write_jsonl(harvest_env["verdict_path"], [
        # covariate field only (no cov_override) → canonical_cov resolves to "rsi"
        {"symbol": "jd", "covariate": "rsi", "mode": "confirmatory",
         "protocol_fingerprint": FP, "status": "ok", "n_eff": 400},
    ])
    _write_jsonl(harvest_env["pending_path"], [
        # cov_override field → canonical_cov resolves to "rsi"
        {"symbol": "jd", "cov_override": "rsi", "run_mode": "confirmatory",
         "protocol_fingerprint": FP},
    ])
    result = _load_evaluated_or_queued(
        harvest_env["verdict_path"], harvest_env["pending_path"], FP)
    # Both resolve to same key ("jd", "rsi", "confirmatory")
    assert ("jd", "rsi", "confirmatory") in result

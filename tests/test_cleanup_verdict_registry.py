"""Tests for scripts/cleanup_verdict_registry.py - spec 4.1"""
import json, os, sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.registry_lib import (
    TERMINAL_STATUSES, CURRENT_PROTOCOL_FINGERPRINT,
    canonical_cov, canonical_mode, effective_n,
)
from scripts.cleanup_verdict_registry import main as cleanup_main


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


@pytest.fixture
def cleanup_env(tmp_path):
    verdict_path = tmp_path / "aligned_verdicts.jsonl"
    pending_path = tmp_path / "aligned_pending.jsonl"
    verdict_path.write_text("")
    pending_path.write_text("")
    return {
        "verdict_path": str(verdict_path),
        "pending_path": str(pending_path),
        "tmp_path": tmp_path,
    }


def _run_cleanup(cleanup_env, **kwargs):
    with patch("scripts.cleanup_verdict_registry.check_process_guard"):
        cleanup_main(
            verdict_path=cleanup_env["verdict_path"],
            pending_path=cleanup_env["pending_path"],
            **kwargs,
        )


def test_current_protocol_valid_kept(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["status"] == "ok"


def test_current_protocol_terminal_kept(cleanup_env):
    records = [
        {"symbol": "jd", "cov_override": "stddev", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "error", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["status"] == "error"


def test_old_protocol_archived(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": "old_fp",
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
        {"symbol": "jd", "cov_override": "vor", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["symbol"] == "jd"
    archives = list(cleanup_env["tmp_path"].glob("aligned_verdicts.archive.*.jsonl"))
    assert len(archives) == 1


def test_old_protocol_terminal_archived(cleanup_env):
    records = [
        {"symbol": "jd", "cov_override": "stddev", "protocol_fingerprint": "old_fp",
         "n": 500, "n_eff": 70, "status": "error", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 0


def test_current_protocol_n0_completed_canonicalized(cleanup_env):
    records = [
        {"symbol": "p", "cov_override": "macd", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 0, "n_eff": 0, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-07T10:00:00"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["status"] == "error"


def test_current_protocol_n0_incomplete_quarantined(cleanup_env):
    records = [
        {"symbol": "a", "cov_override": "boll", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 0, "n_eff": 0, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 0


def test_cleanup_dedup_by_latest(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-01T10:00:00"},
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-05T10:00:00"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["decided_at"] == "2026-11-05T10:00:00"


def test_cleanup_no_gate_pass_bias(cleanup_env):
    records = [
        {"symbol": "jm", "cov_override": "atr", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-01T10:00:00", "gate_pass": True},
        {"symbol": "jm", "cov_override": "atr", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-10T10:00:00", "gate_pass": False},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 1
    assert kept[0]["gate_pass"] is False


def test_cleanup_cov_field_fallback(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "covariate": "macd",
         "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
        {"symbol": "a",
         "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 2
    covs = {v["symbol"]: v["cov_override"] for v in kept}
    assert covs["ss"] == "rsi"
    assert covs["a"] == "UNKNOWN"


def test_cleanup_mode_field_fallback(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "run_mode": "exploration", "mode": "confirmation",
         "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok"},
        {"symbol": "a", "cov_override": "macd",
         "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    kept = _read_jsonl(cleanup_env["verdict_path"])
    assert len(kept) == 2
    modes = {v["symbol"]: v["run_mode"] for v in kept}
    assert modes["ss"] == "exploration"
    assert modes["a"] == "confirmatory"


def test_cleanup_dedups_pending_queue(cleanup_env):
    verdicts = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], verdicts)
    pending = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 0, "run_mode": "exploration"},
        {"symbol": "jd", "cov_override": "vor", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 0, "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["pending_path"], pending)
    _run_cleanup(cleanup_env)
    kept_pending = _read_jsonl(cleanup_env["pending_path"])
    assert len(kept_pending) == 1
    assert kept_pending[0]["symbol"] == "jd"


def test_cleanup_pending_fingerprint_filtered(cleanup_env):
    pending = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 0, "run_mode": "exploration"},
        {"symbol": "jd", "cov_override": "vor", "protocol_fingerprint": "old_fp",
         "n": 0, "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["pending_path"], pending)
    _run_cleanup(cleanup_env)
    kept_pending = _read_jsonl(cleanup_env["pending_path"])
    assert len(kept_pending) == 1
    assert kept_pending[0]["protocol_fingerprint"] == CURRENT_PROTOCOL_FINGERPRINT


def test_cleanup_atomic_write(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    assert not os.path.exists(cleanup_env["verdict_path"] + ".tmp")


def test_cleanup_idempotent(cleanup_env):
    records = [
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-05T10:00:00"},
        {"symbol": "ss", "cov_override": "rsi", "protocol_fingerprint": CURRENT_PROTOCOL_FINGERPRINT,
         "n": 500, "n_eff": 70, "status": "ok", "run_mode": "exploration",
         "decided_at": "2026-11-01T10:00:00"},
    ]
    _write_jsonl(cleanup_env["verdict_path"], records)
    _run_cleanup(cleanup_env)
    first_run = _read_jsonl(cleanup_env["verdict_path"])
    assert len(first_run) == 1
    _run_cleanup(cleanup_env)
    second_run = _read_jsonl(cleanup_env["verdict_path"])
    assert second_run[0] == first_run[0]

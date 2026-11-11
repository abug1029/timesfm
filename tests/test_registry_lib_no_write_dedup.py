"""Test that write-layer dedup has been removed — spec §4.3"""
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.registry_lib import append_verdict


def _make_verdict(batch_id, variant_id):
    """Create a minimal valid verdict dict."""
    return {
        "schema": "fm.aligned_verdict.v1",
        "symbol": "ss",
        "cov_override": "rsi",
        "run_mode": "exploration",
        "batch_id": batch_id,
        "variant_id": variant_id,
        "protocol_fingerprint": "f02b2a43",
        "status": "ok",
        "n": 500,
        "pf": 1.5,
        "ev": 0.1,
        "maxdd": -0.05,
        "dir_acc": 0.55,
        "gate_pass": True,
        "ic": 0.02,
        "max_points": 100,
        "decided_at": "2026-11-11T00:00:00Z",
        "checkpoint_path": "/tmp/test.jsonl",
        "slow_loop_pid": 12345,
        "git_rev": "abc123",
    }


def test_append_verdict_allows_duplicates(tmp_path):
    """Two verdicts with same (symbol, cov, mode) but different batch_id → both written."""
    verdict_file = tmp_path / "test_verdicts.jsonl"
    verdict_file.write_text("")

    v1 = _make_verdict("batch_1", "ss_rsi_abc123")
    v2 = _make_verdict("batch_2", "ss_rsi_def456")

    append_verdict(str(verdict_file), v1)
    append_verdict(str(verdict_file), v2)

    lines = [json.loads(l) for l in verdict_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 2, f"Expected 2 records, got {len(lines)}"
    assert lines[0]["batch_id"] == "batch_1"
    assert lines[1]["batch_id"] == "batch_2"

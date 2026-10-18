"""Phase 4: proposal withdraw mechanism tests."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import proposal_status as ps


def _write_status(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_withdraw_nonexistent(tmp_path):
    path = str(tmp_path / "status.jsonl")
    assert ps.withdraw_proposal(path, "no_such_proposal") is False


def test_withdraw_idempotent(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "queued", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p1", 1) is True
    assert ps.withdraw_proposal(path, "p1", 1) is True  # idempotent


def test_withdraw_draft(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "draft", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p1", 1) is True


def test_withdraw_queued(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "queued", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p1", 1) is True


def test_withdraw_evaluating(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "evaluating", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p1", 1) is True


def test_withdraw_verdicted_rejected(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "verdicted", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p1", 1) is False

    _write_status(path, [
        {"proposal_id": "p2", "version": 1, "status": "rejected", "run_id": "r1"}
    ])
    assert ps.withdraw_proposal(path, "p2", 1) is False


def test_withdraw_version_none(tmp_path):
    """version=None withdraws the latest version."""
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "queued", "run_id": "r1"},
        {"proposal_id": "p1", "version": 2, "status": "queued", "run_id": "r2"},
    ])
    assert ps.withdraw_proposal(path, "p1") is True
    # Verify the withdrawn record is for version 2 (latest)
    latest = ps.get_latest_status(path, "p1")
    assert latest["status"] == "withdrawn"
    assert latest["version"] == 2


def test_get_latest_status(tmp_path):
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "queued", "run_id": "r1"},
        {"proposal_id": "p1", "version": 1, "status": "verdicted", "run_id": "r1"},
    ])
    rec = ps.get_latest_status(path, "p1", 1)
    assert rec["status"] == "verdicted"

    # No match
    assert ps.get_latest_status(path, "no_such") is None
    assert ps.get_latest_status(path, "p1", 99) is None


def test_withdrawn_written_to_file(tmp_path):
    """Withdraw should append a withdrawn line to the status file."""
    path = str(tmp_path / "status.jsonl")
    _write_status(path, [
        {"proposal_id": "p1", "version": 1, "status": "queued", "run_id": "r1", "variant_id": "vid1"}
    ])
    ps.withdraw_proposal(path, "p1", 1, reason="test_reason")
    lines = [json.loads(l) for l in open(path) if l.strip()]
    assert len(lines) == 2
    assert lines[1]["status"] == "withdrawn"
    assert lines[1]["reason"] == "test_reason"
    assert lines[1]["proposal_id"] == "p1"

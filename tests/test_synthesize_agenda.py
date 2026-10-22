"""Tests for B2 offline synthesizer (synthesize_agenda_from_feedback)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from synthesize_agenda_from_feedback import synthesize_agenda, load_feedback


def test_synthesize_agenda_basic():
    feedback = [
        {"symbol": "jm", "family": "momentum", "reward": 1.0, "enqueued_at": "2026-10-21T02:15:30Z"},
        {"symbol": "jm", "family": "momentum", "reward": 0.0, "enqueued_at": "2026-10-21T02:16:01Z"},
        {"symbol": "lh", "family": "oi", "reward": 0.0, "enqueued_at": "2026-10-21T02:16:30Z"},
        {"symbol": "cj", "family": "volatility", "reward": 1.0, "enqueued_at": "2026-10-21T02:17:00Z"},
    ]
    agenda = synthesize_agenda(feedback)
    assert "bucket_weights" in agenda
    assert agenda["total_pulls"] == 4
    assert agenda["bucket_weights"]["momentum"] == 0.5
    assert agenda["bucket_weights"]["oi"] == 0.0
    assert agenda["bucket_weights"]["volatility"] == 1.0
    assert agenda["bucket_weights"]["momentum"] > agenda["bucket_weights"]["oi"]


def test_synthesize_agenda_empty():
    agenda = synthesize_agenda([])
    assert agenda["bucket_weights"] == {}
    assert agenda["total_pulls"] == 0


def test_synthesize_agenda_arm_stats():
    feedback = [
        {"symbol": "jm", "family": "momentum", "reward": 1.0, "enqueued_at": "2026-10-21T02:15:30Z"},
        {"symbol": "lh", "family": "momentum", "reward": 1.0, "enqueued_at": "2026-10-21T02:16:01Z"},
        {"symbol": "cj", "family": "momentum", "reward": 0.0, "enqueued_at": "2026-10-21T02:16:30Z"},
    ]
    agenda = synthesize_agenda(feedback)
    stats = agenda["arm_stats"]["momentum"]
    assert stats["pulls"] == 3
    assert stats["successes"] == 2
    assert stats["success_rate"] == round(2 / 3, 4)


def test_load_feedback_missing_file(tmp_path):
    records = load_feedback(str(tmp_path / "nonexistent.jsonl"))
    assert records == []


def test_load_feedback_valid(tmp_path):
    fpath = tmp_path / "feedback.jsonl"
    lines = [
        json.dumps({"symbol": "jm", "family": "momentum", "reward": 1.0, "enqueued_at": "2026-10-21T02:15:30Z"}),
        json.dumps({"symbol": "lh", "family": "oi", "reward": 0.0, "enqueued_at": "2026-10-21T02:16:01Z"}),
    ]
    fpath.write_text("\n".join(lines) + "\n")
    records = load_feedback(str(fpath))
    assert len(records) == 2
    assert records[0]["family"] == "momentum"

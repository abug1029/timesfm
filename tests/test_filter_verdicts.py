import pytest
from pathlib import Path
from datetime import datetime
from scripts.scan_proposals import ProposalInfo
from scripts.filter_verdicts import filter_existing_verdicts


def test_filter_existing_verdicts(tmp_path):
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text(
        '{"variant_id": "ta_momentum", "status": "ok"}\n'
        '{"variant_id": "sh_basis", "status": "ok"}\n'
    )

    proposals = [
        ProposalInfo("ta", "momentum", "ta_momentum", Path("/p1.json"), datetime.now(), "run1"),
        ProposalInfo("sh", "basis", "sh_basis", Path("/p2.json"), datetime.now(), "run1"),
        ProposalInfo("i", "oi", "i_oi", Path("/p3.json"), datetime.now(), "run1"),
    ]

    result = filter_existing_verdicts(proposals, verdict_file)

    assert len(result) == 1
    assert result[0].variant_id == "i_oi"


def test_filter_verdict_file_not_exists(tmp_path):
    verdict_file = tmp_path / "nonexistent.jsonl"
    proposals = [
        ProposalInfo("ta", "momentum", "ta_momentum", Path("/p1.json"), datetime.now(), "run1"),
    ]
    result = filter_existing_verdicts(proposals, verdict_file)
    assert len(result) == 1


def test_filter_verdict_corrupted_lines(tmp_path):
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text(
        '{"variant_id": "ta_momentum", "status": "ok"}\n'
        '{bad json\n'
        '{"no_variant_id": true}\n'
        '{"variant_id": "sh_basis", "status": "ok"}\n'
    )

    proposals = [
        ProposalInfo("ta", "momentum", "ta_momentum", Path("/p1.json"), datetime.now(), "run1"),
        ProposalInfo("sh", "basis", "sh_basis", Path("/p2.json"), datetime.now(), "run1"),
        ProposalInfo("i", "oi", "i_oi", Path("/p3.json"), datetime.now(), "run1"),
    ]

    result = filter_existing_verdicts(proposals, verdict_file)
    assert len(result) == 1
    assert result[0].variant_id == "i_oi"


def test_filter_empty_verdict_file(tmp_path):
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text("")
    proposals = [
        ProposalInfo("ta", "momentum", "ta_momentum", Path("/p1.json"), datetime.now(), "run1"),
    ]
    result = filter_existing_verdicts(proposals, verdict_file)
    assert len(result) == 1


def test_filter_empty_proposals(tmp_path):
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text('{"variant_id": "ta_momentum"}\n')
    result = filter_existing_verdicts([], verdict_file)
    assert result == []

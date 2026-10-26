import pytest
from pathlib import Path
from datetime import datetime
from scripts.scan_proposals import scan_proposals, ProposalInfo


def test_scan_valid_proposals(tmp_path):
    """Test scanning valid proposal files."""
    proposal1 = tmp_path / "prop1.json"
    proposal1.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    proposal2 = tmp_path / "prop2.json"
    proposal2.write_text('{"symbol": "sh", "cov_override": "basis"}')
    
    result = scan_proposals([proposal1, proposal2])
    
    assert len(result) == 2
    assert result[0].symbol == "ta"
    assert result[0].cov_override == "momentum"
    assert result[0].variant_id == "ta_momentum"
    assert result[0].src_run == "unknown"
    assert isinstance(result[0].mtime, datetime)
    
    assert result[1].symbol == "sh"
    assert result[1].cov_override == "basis"
    assert result[1].variant_id == "sh_basis"


def test_scan_corrupted_files(tmp_path):
    """Test handling corrupted JSON files."""
    valid = tmp_path / "valid.json"
    valid.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    corrupted = tmp_path / "corrupted.json"
    corrupted.write_text("{invalid json")
    
    result = scan_proposals([valid, corrupted])
    
    assert len(result) == 1
    assert result[0].symbol == "ta"


def test_scan_missing_fields(tmp_path):
    """Test handling files missing required fields."""
    valid = tmp_path / "valid.json"
    valid.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    missing_symbol = tmp_path / "missing_symbol.json"
    missing_symbol.write_text('{"cov_override": "momentum"}')
    
    missing_cov = tmp_path / "missing_cov.json"
    missing_cov.write_text('{"symbol": "sh"}')
    
    result = scan_proposals([valid, missing_symbol, missing_cov])
    
    assert len(result) == 1
    assert result[0].symbol == "ta"


def test_extract_src_run_from_path(tmp_path):
    """Test extracting src_run from path."""
    run_dir = tmp_path / "run_2026-10-24_06-23-48_primary_task_FM" / "results" / "proposals"
    run_dir.mkdir(parents=True)
    
    proposal = run_dir / "ta_momentum.json"
    proposal.write_text('{"symbol": "ta", "cov_override": "momentum"}')
    
    result = scan_proposals([proposal])
    
    assert len(result) == 1
    assert result[0].src_run == "run_2026-10-24_06-23-48_primary_task_FM"


# Task 2: Deduplication tests
def test_deduplicate_by_variant_id():
    """Deduplicate by variant_id, keep latest mtime."""
    from scripts.scan_proposals import deduplicate_proposals
    
    prop1 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/old/run_2026-10-01/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 1),
        src_run="run_2026-10-01"
    )
    
    prop2 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/new/run_2026-10-20/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 20),
        src_run="run_2026-10-20"
    )
    
    result = deduplicate_proposals([prop1, prop2])
    
    assert len(result) == 1
    assert result[0].mtime == datetime(2026, 10, 20)
    assert result[0].src_run == "run_2026-10-20"


def test_deduplicate_no_duplicates():
    """No duplicates returns original list."""
    from scripts.scan_proposals import deduplicate_proposals
    
    prop1 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/p1.json"),
        mtime=datetime(2026, 10, 1),
        src_run="run1"
    )
    
    prop2 = ProposalInfo(
        symbol="sh",
        cov_override="basis",
        variant_id="sh_basis",
        file_path=Path("/p2.json"),
        mtime=datetime(2026, 10, 2),
        src_run="run2"
    )
    
    result = deduplicate_proposals([prop1, prop2])
    
    assert len(result) == 2


def test_deduplicate_all_duplicates():
    """All duplicates keeps only one."""
    from scripts.scan_proposals import deduplicate_proposals
    
    prop1 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/old/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 1),
        src_run="run_2026-10-01"
    )
    
    prop2 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/mid/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 10),
        src_run="run_2026-10-10"
    )
    
    prop3 = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/new/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 20),
        src_run="run_2026-10-20"
    )
    
    result = deduplicate_proposals([prop1, prop2, prop3])
    
    assert len(result) == 1
    assert result[0].mtime == datetime(2026, 10, 20)
    assert result[0].src_run == "run_2026-10-20"

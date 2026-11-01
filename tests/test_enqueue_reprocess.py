import json
from pathlib import Path
from datetime import datetime
from scripts.scan_proposals import ProposalInfo
from scripts.enqueue_reprocess import construct_queue_row, main


def test_construct_queue_row():
    proposal = ProposalInfo(
        symbol="ta",
        cov_override="ao_accel",
        variant_id="ta_ao_accel",
        file_path=Path("/path/to/proposals/ta_ao_accel.json"),
        mtime=datetime(2026, 10, 26, 12, 0, 0),
        src_run="run_2026-10-24_06-23-48_primary_task_FM"
    )
    
    row = construct_queue_row(proposal, batch_id="reprocess_20261026")
    
    assert row["variant_id"] == "ta_ao_accel"
    assert row["symbol"] == "ta"
    assert row["cov_override"] == "ao_accel"
    assert row["max_points"] == 600
    assert row["stage"] == "aligned"
    assert row["source"] == "reprocess_20261026"
    assert row["src_run"] == "run_2026-10-24_06-23-48_primary_task_FM"
    assert "enqueued_at" in row
    assert row["checkpoint_path"] == ""


def test_main_orchestration(tmp_path):
    """Test main() integrates scan -> dedup -> filter -> construct -> write."""
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir()

    # run1: one proposal (ta_ao_accel, older)
    run1 = exp_dir / "run_2026-10-01" / "results" / "gen_0" / "gen0_peer0" / "proposals"
    run1.mkdir(parents=True)
    (run1 / "ta_ao_accel.json").write_text('{"symbol": "ta", "cov_override": "ao_accel"}')

    # run2: two proposals (ta_ao_accel duplicate newer + sh_basis_momentum new)
    run2 = exp_dir / "run_2026-10-20" / "results" / "gen_0" / "gen0_peer0" / "proposals"
    run2.mkdir(parents=True)
    (run2 / "ta_ao_accel.json").write_text('{"symbol": "ta", "cov_override": "ao_accel"}')
    (run2 / "sh_basis_momentum.json").write_text('{"symbol": "sh", "cov_override": "basis_momentum"}')

    # ta_ao_accel already has a verdict
    verdict_file = tmp_path / "verdicts.jsonl"
    verdict_file.write_text('{"variant_id": "ta_ao_accel", "status": "ok"}\n')

    queue_file = tmp_path / "queue.jsonl"

    stats = main(exp_dir, verdict_file, queue_file, "reprocess_20261026")

    assert stats["total_files"] == 3
    assert stats["unique_proposals"] == 2
    assert stats["already_verdict"] == 1
    assert stats["to_enqueue"] == 1
    assert stats["enqueued"] == 1
    assert stats["failed"] == 0

    # Verify queue file contents
    lines = [l for l in queue_file.read_text().strip().split("\n") if l]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["variant_id"] == "sh_basis_momentum"
    assert row["symbol"] == "sh"
    assert row["source"] == "reprocess_20261026"


def test_main_filters_invalid_covariates(tmp_path):
    """Test that family names and unregistered covariates are filtered."""
    # Setup: create proposals with invalid covariates
    experiments_dir = tmp_path / "experiments"
    run_dir = experiments_dir / "run_test" / "results" / "gen_0" / "gen0_peer1" / "proposals"
    run_dir.mkdir(parents=True)
    
    # 1. Family name (should be filtered)
    family_prop = {
        "symbol": "ta",
        "cov_override": "momentum",  # family name, not covariate
        "variant_id": "ta_momentum"
    }
    (run_dir / "ta_momentum.json").write_text(json.dumps(family_prop))
    
    # 2. Unregistered covariate (should be filtered)
    unreg_prop = {
        "symbol": "sh",
        "cov_override": "macro_sentiment_composite",  # not in registry
        "variant_id": "sh_macro_sentiment_composite"
    }
    (run_dir / "sh_macro_sentiment_composite.json").write_text(json.dumps(unreg_prop))
    
    # 3. Valid covariate (should be enqueued)
    valid_prop = {
        "symbol": "m",
        "cov_override": "vor",  # valid active covariate
        "variant_id": "m_vor"
    }
    (run_dir / "m_vor.json").write_text(json.dumps(valid_prop))
    
    # Create empty verdict file
    verdict_path = tmp_path / "verdicts.jsonl"
    verdict_path.touch()
    
    # Create queue file
    queue_path = tmp_path / "queue.jsonl"
    queue_path.touch()
    
    # Run main
    stats = main(experiments_dir, verdict_path, queue_path, "test_filter")
    
    # Assertions
    assert stats["invalid_covariate"] == 2, f"Expected 2 invalid, got {stats['invalid_covariate']}"
    assert stats["to_enqueue"] == 1, f"Expected 1 to_enqueue, got {stats['to_enqueue']}"
    assert stats["enqueued"] == 1, f"Expected 1 enqueued, got {stats['enqueued']}"
    
    # Verify queue content
    lines = queue_path.read_text().strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["cov_override"] == "vor"

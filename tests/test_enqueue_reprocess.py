from pathlib import Path
from datetime import datetime
from scripts.scan_proposals import ProposalInfo
from scripts.enqueue_reprocess import construct_queue_row


def test_construct_queue_row():
    proposal = ProposalInfo(
        symbol="ta",
        cov_override="momentum",
        variant_id="ta_momentum",
        file_path=Path("/path/to/proposals/ta_momentum.json"),
        mtime=datetime(2026, 10, 26, 12, 0, 0),
        src_run="run_2026-10-24_06-23-48_primary_task_FM"
    )
    
    row = construct_queue_row(proposal, batch_id="reprocess_20261026")
    
    assert row["variant_id"] == "ta_momentum"
    assert row["symbol"] == "ta"
    assert row["cov_override"] == "momentum"
    assert row["max_points"] == 600
    assert row["stage"] == "aligned"
    assert row["source"] == "reprocess_20261026"
    assert row["src_run"] == "run_2026-10-24_06-23-48_primary_task_FM"
    assert "enqueued_at" in row
    assert row["checkpoint_path"] == ""

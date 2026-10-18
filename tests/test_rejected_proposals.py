import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_write_rejected_proposal_creates_file():
    """写入拒收记录时创建文件"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(
            rejected_file=rejected_file,
            proposal_id="test_prop",
            version=1,
            reject_reason="schema_mismatch",
            quality_score=-12.5,
            run_id="test_run"
        )

        assert os.path.exists(rejected_file)
        with open(rejected_file) as f:
            line = f.readline()
            record = json.loads(line)
            assert record["proposal_id"] == "test_prop"
            assert record["reject_reason"] == "schema_mismatch"
            assert record["quality_score"] == -12.5
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_write_rejected_proposal_with_breakdown():
    """写入拒收记录时可携带详细分解"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(
            rejected_file=rejected_file,
            proposal_id="test_prop",
            version=1,
            reject_reason="quality_below_threshold",
            quality_score=-5.0,
            run_id="test_run",
            breakdown={
                "mechanism_score": -2.0,
                "novelty_score": -3.0,
            }
        )

        with open(rejected_file) as f:
            record = json.loads(f.readline())
            assert record["breakdown"]["mechanism_score"] == -2.0
            assert record["breakdown"]["novelty_score"] == -3.0
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_write_rejected_proposal_dedup():
    """SPEC §4.5 去重：相同记录只写一次"""
    from rejected_proposals import write_rejected_proposal

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        rejected_file = f.name

    try:
        write_rejected_proposal(rejected_file, "p1", 1, "schema_mismatch", -10.0, "run1")
        write_rejected_proposal(rejected_file, "p1", 1, "schema_mismatch", -10.0, "run1")

        with open(rejected_file) as f:
            lines = f.readlines()
            assert len(lines) == 1
    finally:
        if os.path.exists(rejected_file):
            os.remove(rejected_file)
        lock_file = rejected_file + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

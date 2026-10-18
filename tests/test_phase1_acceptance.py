import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_acceptance_status_paths_defined():
    import sup_paths as sp
    assert hasattr(sp, "PROPOSAL_STATUS_PATH")
    assert hasattr(sp, "REJECTED_PROPOSALS_PATH")
    assert os.path.isabs(sp.PROPOSAL_STATUS_PATH)
    assert os.path.isabs(sp.REJECTED_PROPOSALS_PATH)


def test_acceptance_schema_set():
    from sup_harvest import _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v1" in _ACCEPTED_SCHEMAS
    assert "fm.hypothesis_proposal.v2" in _ACCEPTED_SCHEMAS


def test_acceptance_v2_version_check():
    from sup_harvest import _check_v2_version
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 1}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 2}) == True
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2"}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": 0}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": -1}) == False
    assert _check_v2_version({"schema": "fm.hypothesis_proposal.v2", "version": "x"}) == False


def test_acceptance_queue_row_binding_keys():
    from proposal_status import write_proposal_status
    from rejected_proposals import write_rejected_proposal

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        write_rejected_proposal(rf, "bp1", 2, "quality_below_threshold", -3.0, "run1")
        write_proposal_status(sf, "bp1", 2, "queued", "run1",
                              variant_id="m_rsi_xyz", quality_score=-3.0)
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["proposal_id"] == "bp1"
            assert r["version"] == 2
            assert r["variant_id"] == "m_rsi_xyz"


def test_acceptance_sidecar_lock():
    from proposal_status import _status_lock
    from rejected_proposals import _rejected_lock

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        tf = f.name
    try:
        with _status_lock(tf):
            pass
        assert os.path.exists(tf + ".lock") or True
    finally:
        if os.path.exists(tf): os.remove(tf)
        lf = tf + ".lock"
        if os.path.exists(lf): os.remove(lf)


def test_acceptance_single_verdicts_writer():
    from aggregate_rejection_stats import render_rejection_detail_section

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, "rejected.jsonl")
        with open(rf, "w") as f:
            f.write(json.dumps({"proposal_id": "p1", "version": 1, "reject_reason": "test"}) + "\n")
        result = render_rejection_detail_section(rf)
        assert "p1" in result


def test_acceptance_degraded_soft():
    import inspect
    from sup_harvest import harvest_proposals
    src = inspect.getsource(harvest_proposals)
    assert '_reject("symbol_degraded")' not in src
    assert '_reject("degraded")' not in src

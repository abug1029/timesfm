"""Tests for P3.2+P3.3: proposal_id+version dedup and version_dup reject reason.

Spec §3.5.3: same proposal_id+version already in proposal_status.jsonl → reject
as version_dup. Higher version of same proposal_id is allowed.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ── helper unit tests ──

def test_has_proposal_version_status_empty():
    """No status file → not duplicate."""
    from sup_harvest import _has_proposal_version_status
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    os.remove(path)  # ensure file does not exist
    try:
        assert _has_proposal_version_status(path, "p1", 1) is False
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_has_proposal_version_status_match():
    """Exact proposal_id+version in status → duplicate."""
    from sup_harvest import _has_proposal_version_status
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"proposal_id": "p1", "version": 1, "status": "queued"}) + "\n")
        f.write(json.dumps({"proposal_id": "p2", "version": 1, "status": "rejected"}) + "\n")
        path = f.name
    try:
        assert _has_proposal_version_status(path, "p1", 1) is True
        assert _has_proposal_version_status(path, "p2", 1) is True
        assert _has_proposal_version_status(path, "p1", 2) is False  # different version
        assert _has_proposal_version_status(path, "p3", 1) is False  # different id
    finally:
        os.remove(path)


def test_has_proposal_version_status_status_filter():
    """Status filter: only count when status matches."""
    from sup_harvest import _has_proposal_version_status
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"proposal_id": "p1", "version": 1, "status": "rejected"}) + "\n")
        path = f.name
    try:
        # No filter → any status counts
        assert _has_proposal_version_status(path, "p1", 1) is True
        # Filter includes "rejected"
        assert _has_proposal_version_status(path, "p1", 1, statuses={"rejected"}) is True
        # Filter excludes "rejected"
        assert _has_proposal_version_status(path, "p1", 1, statuses={"queued"}) is False
    finally:
        os.remove(path)


# ── integration tests (harvest_proposals) ──

def _make_proposal_dir(tmpdir, proposal_id="test_prop", version=None):
    """Create minimal proposal fixture directory."""
    run_dir = Path(tmpdir) / "task_FM" / "experiments" / "run_001"
    proposal_dir = run_dir / "results" / "gen_0" / "gen0_peer0" / "proposals"
    proposal_dir.mkdir(parents=True)
    p = {
        "schema": "fm.hypothesis_proposal.v1",
        "proposal_id": proposal_id,
        "symbol": "m",
        "cov_override": "ma20",
        "covariate_family": "momentum",
        "mechanism": "x" * 50,
        "symbol_fit": "test",
        "predicted_direction": "up",
        "kill_condition": "test",
        "promote_condition": "test",
    }
    if version is not None:
        p["version"] = version
    (proposal_dir / f"{proposal_id}.json").write_text(json.dumps(p))
    return run_dir


def _patch_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir):
    """Configure harvest_proposals mocks."""
    mock_sp.PROPOSAL_STATUS_PATH = os.path.join(tmpdir, "proposal_status.jsonl")
    mock_sp.REJECTED_PROPOSALS_PATH = os.path.join(tmpdir, "rejected_proposals.jsonl")
    mock_sp.SEARCH_COMMITMENTS_PATH = os.path.join(tmpdir, "search_commits.json")
    mock_sp.RETEST_GATE_N = 50
    mock_ev._load_evaluator.return_value = None
    mock_ev.load_symbol_status.return_value = {}
    mock_ev._symbol_has_current_nocov_baseline.return_value = True
    mock_ev._dead_families.return_value = set()
    mock_ev._has_prior_failure.return_value = False
    mock_ev._experiment_fp_for.return_value = "test_fp"
    mock_ev._success_delta_gate.return_value = (None, "pass")
    mock_st.SearchGuard.load.return_value = None
    mock_ef.build_variant_id.return_value = "m_momentum_test_fp"
    mock_ev._verdict_sort_key = lambda v: v.get("decided_at", "")
    mock_ev._is_confirmable_failure = lambda v: False
    mock_lc._now_iso.return_value = "2026-10-18T00:00:00Z"
    mock_lc._SHUTDOWN_REQUESTED = False
    mock_lc._log_decision = MagicMock()


def test_version_dup_rejected():
    """Same proposal_id+version in status → rejected as version_dup."""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_proposal_dir(tmpdir, proposal_id="dup_prop", version=1)

        # Pre-seed status file with same proposal_id+version
        status_path = os.path.join(tmpdir, "proposal_status.jsonl")
        with open(status_path, "w") as f:
            f.write(json.dumps({
                "proposal_id": "dup_prop", "version": 1,
                "status": "queued", "queued_at": "2026-10-17T00:00:00Z"
            }) + "\n")

        with patch("sup_harvest.sup_paths") as mock_sp,              patch("sup_harvest.sup_evidence") as mock_ev,              patch("sup_harvest.sup_lifecycle") as mock_lc,              patch("sup_harvest.st") as mock_st,              patch("sup_harvest.ef") as mock_ef:
            _patch_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)
            # Use different vid so vid dedup does NOT trigger
            mock_ef.build_variant_id.return_value = "m_momentum_different_fp"

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            assert len(cands) == 0, "version_dup should reject the proposal"
            assert stats["rejected"] >= 1
            assert "version_dup" in stats["reject_reasons"]


def test_higher_version_allowed():
    """Same proposal_id but higher version NOT in status → allowed past version_dup."""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        # v2 proposal
        _make_proposal_dir(tmpdir, proposal_id="v_prop", version=2)

        # Pre-seed status with v1 only
        status_path = os.path.join(tmpdir, "proposal_status.jsonl")
        with open(status_path, "w") as f:
            f.write(json.dumps({
                "proposal_id": "v_prop", "version": 1,
                "status": "rejected", "queued_at": "2026-10-17T00:00:00Z"
            }) + "\n")

        with patch("sup_harvest.sup_paths") as mock_sp,              patch("sup_harvest.sup_evidence") as mock_ev,              patch("sup_harvest.sup_lifecycle") as mock_lc,              patch("sup_harvest.st") as mock_st,              patch("sup_harvest.ef") as mock_ef:
            _patch_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)
            # Unique vid so vid dedup does not interfere
            mock_ef.build_variant_id.return_value = "m_momentum_v2_fp"

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            # v2 should NOT be rejected as version_dup (only v1 is in status)
            assert "version_dup" not in stats.get("reject_reasons", {}),                 "v2 should not be rejected as version_dup when only v1 is in status"


def test_prompt_has_version_guidance():
    """prompt_base.jinja2 should mention version fields for v2 schema."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "task_FM", "prompt_base.jinja2")
    content = open(prompt_path, encoding="utf-8").read()
    assert "version" in content.lower()
    assert "version_note" in content or "version note" in content.lower()


def test_version_comparison_enhanced(tmp_path):
    """_version_comparison_lines should show outcome per version."""
    import sup_evidence as se
    import sup_paths as sp

    status_path = str(tmp_path / "proposal_status.jsonl")
    verdicts_path = str(tmp_path / "aligned_verdicts.jsonl")

    with open(status_path, "w") as f:
        f.write(json.dumps({"proposal_id": "m_crack", "version": 1, "status": "rejected", "reject_reason": "quality_below_threshold"}) + "\n")
        f.write(json.dumps({"proposal_id": "m_crack", "version": 2, "status": "verdicted", "variant_id": "vid_v2"}) + "\n")

    with open(verdicts_path, "w") as f:
        f.write(json.dumps({"variant_id": "vid_v2", "gate_pass": True, "fdr_pass": True}) + "\n")

    orig = sp.REGISTRY
    try:
        sp.REGISTRY = verdicts_path
        lines = se._version_comparison_lines(status_path)
        assert len(lines) == 1
        assert "m_crack" in lines[0]
        assert "v1" in lines[0]
        assert "v2" in lines[0]
        assert "rejected" in lines[0]
        assert "verdicted" in lines[0]
    finally:
        sp.REGISTRY = orig


def test_tree_member_has_version(tmp_path):
    """_Tree.member_pid_ver should store version from commitment records."""
    import search_trees as st
    commitments_path = str(tmp_path / "search_commitments.jsonl")
    with open(commitments_path, "w") as f:
        f.write(json.dumps({
            "tree_id": "tree_A", "event": "accept",
            "symbol": "m", "family": "momentum",
            "proposal_id": "m_crack", "variant_id": "vid_1",
            "version": 2, "search_role": "root",
            "schema": "fm.search_commitments.v1", "B": 4, "tau": 0.04
        }) + "\n")
    index = st.load_tree_index(commitments_path)
    tree = index.trees["tree_A"]
    assert tree.member_pid_ver.get("m_crack") == 2


def test_append_commitment_carries_version(tmp_path):
    """append_commitment should write version field when provided."""
    import search_trees as st
    path = str(tmp_path / "commitments.jsonl")
    st.append_commitment(path, "accept", "tree_A",
                         symbol="m", family="momentum",
                         proposal_id="m_crack", variant_id="vid_1",
                         version=3)
    content = open(path).read().strip()
    rec = json.loads(content)
    assert rec["version"] == 3

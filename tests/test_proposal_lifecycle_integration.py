# tests/test_proposal_lifecycle_integration.py
"""Phase 1 Task 7: 端到端集成测试

验证完整提案生命周期：
- v1 schema 无 version 字段时，入队行 version = 1
- 被拒提案同时写入 proposal_status.jsonl (rejected) 和 rejected_proposals.jsonl
- 入队行包含 proposal_id 和 version（P0-1 绑定键）
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from test_harvest_status_integration import (
    _make_minimal_harvest_fixtures,
    _patch_harvest_deps,
)


def test_v1_without_version_defaults_to_1():
    """v1 schema 无 version 字段时，入队行 version = 1"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        status_file = os.path.join(tmpdir, "proposal_status.jsonl")
        _make_minimal_harvest_fixtures(tmpdir, proposal_id="no_ver")

        with patch("sup_harvest.sup_paths") as mock_sp,             patch("sup_harvest.sup_evidence") as mock_ev,             patch("sup_harvest.sup_lifecycle") as mock_lc,             patch("sup_harvest.st") as mock_st,             patch("sup_harvest.ef") as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10, priority_symbols=[]
            )
            assert len(cands) >= 1
            assert cands[0]["version"] == 1, "v1 无 version → 应为 1"


def test_rejected_proposal_written_to_both_files():
    """被拒提案同时写入 proposal_status.jsonl (rejected) 和 rejected_proposals.jsonl"""
    from proposal_status import write_proposal_status
    from rejected_proposals import write_rejected_proposal

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")

        write_rejected_proposal(
            rf, "rp1", 1, "schema_mismatch", None, "run1",
            symbol="m", cov_override="ma20", covariate_family="momentum"
        )
        write_proposal_status(
            sf, "rp1", 1, "rejected", "run1",
            reject_reason="schema_mismatch", quality_score=None
        )

        with open(sf) as f:
            sr = json.loads(f.readline())
            assert sr["status"] == "rejected"
            assert sr["proposal_id"] == "rp1"
        with open(rf) as f:
            rr = json.loads(f.readline())
            assert rr["reject_reason"] == "schema_mismatch"
            assert rr["quality_score"] is None  # 质量门前被拒


def test_queue_row_has_binding_keys():
    """入队行包含 proposal_id 和 version（P0-1 绑定键）"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "status.jsonl")
        _make_minimal_harvest_fixtures(
            tmpdir, schema="fm.hypothesis_proposal.v2", proposal_id="v2_prop", version=2
        )

        with patch("sup_harvest.sup_paths") as mock_sp,             patch("sup_harvest.sup_evidence") as mock_ev,             patch("sup_harvest.sup_lifecycle") as mock_lc,             patch("sup_harvest.st") as mock_st,             patch("sup_harvest.ef") as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10, priority_symbols=[]
            )
            assert len(cands) >= 1
            c = cands[0]
            assert c["proposal_id"] == "v2_prop", "queue 行 proposal_id 不匹配"
            assert c["version"] == 2, "queue 行 version 不匹配"

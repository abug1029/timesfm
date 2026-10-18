import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_materialize_includes_verdict_causal_chain():
    """物化包含 verdict 因果链（status=verdicted ⋈ aligned_verdicts）"""
    from sup_evidence import _proposal_verdict_causal_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")

        with open(sf, "w") as f:
            f.write(json.dumps({
                "proposal_id": "p1", "version": 1, "status": "verdicted",
                "run_id": "run1", "variant_id": "m_momentum_abc",
                "ts": "2026-10-18T00:00:00Z"
            }) + "\n")

        with open(vf, "w") as f:
            f.write(json.dumps({
                "variant_id": "m_momentum_abc", "symbol": "m",
                "gate_pass": True, "fdr_pass": True
            }) + "\n")

        lines = _proposal_verdict_causal_lines(sf, vf)
        assert len(lines) >= 1
        assert "p1" in lines[0]
        assert "m_momentum_abc" in lines[0]
        assert "gate" in lines[0].lower() or "fdr" in lines[0].lower()


def test_materialize_includes_rejection_details():
    """物化包含拒收详情节（从 rejected_proposals.jsonl）"""
    from aggregate_rejection_stats import render_rejection_detail_section

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, "rejected.jsonl")
        with open(rf, "w") as f:
            f.write(json.dumps({
                "proposal_id": "rp1", "version": 1,
                "reject_reason": "quality_below_threshold",
                "quality_score": -5.0, "symbol": "m"
            }) + "\n")

        section = render_rejection_detail_section(rf)
        assert "rp1" in section
        assert "quality_below_threshold" in section


def test_materialize_respects_row_budget():
    """物化遵守行预算：因果链 ≤ 25 行，拒收 ≤ 20 行，版本比较 ≤ 10 行"""
    from sup_evidence import (
        _proposal_verdict_causal_lines,
        _rejection_detail_lines,
        _version_comparison_lines,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")

        # 生成 50 条 verdicted status + verdicts
        with open(sf, "w") as f:
            for i in range(50):
                f.write(json.dumps({
                    "proposal_id": "p%d" % i, "version": 1,
                    "status": "verdicted", "variant_id": "vid_%d" % i,
                }) + "\n")
        with open(vf, "w") as f:
            for i in range(50):
                f.write(json.dumps({
                    "variant_id": "vid_%d" % i, "gate_pass": True, "fdr_pass": True,
                }) + "\n")
        # 生成 30 条 rejected
        with open(rf, "w") as f:
            for i in range(30):
                f.write(json.dumps({
                    "proposal_id": "rp%d" % i, "version": 1,
                    "reject_reason": "quality", "quality_score": -1, "symbol": "m",
                }) + "\n")

        causal = _proposal_verdict_causal_lines(sf, vf)
        assert len(causal) <= 25

        rej = _rejection_detail_lines(rf)
        assert len(rej) <= 20

        # 生成 20 个多版本 proposal
        with open(sf, "w") as f:
            for pid in range(20):
                for ver in range(3):
                    f.write(json.dumps({
                        "proposal_id": "mp%d" % pid, "version": ver,
                        "status": "proposed",
                    }) + "\n")
        ver = _version_comparison_lines(sf)
        assert len(ver) <= 10

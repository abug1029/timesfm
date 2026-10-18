# tests/test_cross_run_feedback.py
"""Phase 2 Task 1: 跨 Run 反馈通道测试

验证 _proposal_evolution_lines() 和端到端 materialize_known_verdicts() 集成。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _write_jsonl(path, records):
    """Helper: write list of dicts as JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_proposal_evolution_lines():
    """多版本提案演化轨迹正确展示"""
    from sup_evidence import _proposal_evolution_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")

        # m_crack: v1 rejected, v2 verdicted(PASS), v3 queued
        _write_jsonl(sf, [
            {"proposal_id": "m_crack", "version": 1, "status": "rejected",
             "run_id": "run1", "reject_reason": "quality_below_threshold"},
            {"proposal_id": "m_crack", "version": 2, "status": "verdicted",
             "run_id": "run2", "variant_id": "m_crack_v2"},
            {"proposal_id": "m_crack", "version": 3, "status": "queued",
             "run_id": "run3"},
        ])
        _write_jsonl(rf, [
            {"proposal_id": "m_crack", "version": 1,
             "reject_reason": "quality_below_threshold",
             "quality_score": -3.0, "symbol": "m"},
        ])
        _write_jsonl(vf, [
            {"variant_id": "m_crack_v2", "gate_pass": True, "fdr_pass": True},
        ])

        lines = _proposal_evolution_lines(sf, rf, vf)
        assert len(lines) == 1
        assert "m_crack" in lines[0]
        assert "v1 rejected(quality_below_threshold)" in lines[0]
        assert "v2 verdicted(gate=True,fdr=True)" in lines[0]
        assert "v3 queued" in lines[0]


def test_proposal_evolution_empty():
    """空数据返回 []"""
    from sup_evidence import _proposal_evolution_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")

        # 空文件
        _write_jsonl(sf, [])
        _write_jsonl(rf, [])
        _write_jsonl(vf, [])

        assert _proposal_evolution_lines(sf, rf, vf) == []

        # 文件不存在
        assert _proposal_evolution_lines(
            os.path.join(tmpdir, "nonexistent.jsonl"), rf, vf) == []

        # 只有单版本（不满足 >= 2）
        _write_jsonl(sf, [
            {"proposal_id": "single", "version": 1, "status": "queued"},
        ])
        assert _proposal_evolution_lines(sf, rf, vf) == []


def test_proposal_evolution_budget():
    """max_lines 截断生效"""
    from sup_evidence import _proposal_evolution_lines

    with tempfile.TemporaryDirectory() as tmpdir:
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")

        # 生成 20 个多版本提案
        records = []
        for i in range(20):
            records.append({"proposal_id": "p%d" % i, "version": 1, "status": "queued"})
            records.append({"proposal_id": "p%d" % i, "version": 2, "status": "rejected"})
        _write_jsonl(sf, records)
        _write_jsonl(rf, [])
        _write_jsonl(vf, [])

        # 默认 max_lines=15
        lines = _proposal_evolution_lines(sf, rf, vf)
        assert len(lines) == 15

        # 自定义 max_lines=3
        lines = _proposal_evolution_lines(sf, rf, vf, max_lines=3)
        assert len(lines) == 3


def test_end_to_end_cross_run_feedback():
    """端到端：materialize_known_verdicts 包含因果链 + 拒收详情 + 演化视图"""
    from sup_evidence import materialize_known_verdicts
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        # 设置夹具文件
        sf = os.path.join(tmpdir, "proposal_status.jsonl")
        rf = os.path.join(tmpdir, "rejected.jsonl")
        vf = os.path.join(tmpdir, "aligned_verdicts.jsonl")
        dest = os.path.join(tmpdir, "output", "known_verdicts.inc.md")

        # m_crack: v1 rejected, v2 verdicted
        _write_jsonl(sf, [
            {"proposal_id": "m_crack", "version": 1, "status": "rejected",
             "run_id": "run1", "reject_reason": "quality_below_threshold"},
            {"proposal_id": "m_crack", "version": 2, "status": "verdicted",
             "run_id": "run2", "variant_id": "m_crack_v2"},
        ])
        _write_jsonl(rf, [
            {"proposal_id": "m_crack", "version": 1,
             "reject_reason": "quality_below_threshold",
             "quality_score": -3.0, "symbol": "m",
             "cov_override": "crack_spread", "covariate_family": "energy"},
        ])
        _write_jsonl(vf, [
            {"variant_id": "m_crack_v2", "gate_pass": True, "fdr_pass": True,
             "symbol": "m", "status": "ok"},
        ])

        # Mock sup_paths to point to our temp files
        import sup_paths as real_sup_paths
        with patch.object(real_sup_paths, "PROPOSAL_STATUS_PATH", sf),              patch.object(real_sup_paths, "REJECTED_PROPOSALS_PATH", rf),              patch.object(real_sup_paths, "REGISTRY", vf),              patch.object(real_sup_paths, "FM_ROOT", tmpdir),              patch.object(real_sup_paths, "QUEUE", os.path.join(tmpdir, "queue.jsonl")),              patch.object(real_sup_paths, "INPROGRESS", os.path.join(tmpdir, "inprogress.jsonl")),              patch.object(real_sup_paths, "POOL_PATH", os.path.join(tmpdir, "pool.jsonl")),              patch.object(real_sup_paths, "SYMBOL_STATUS_PATH", os.path.join(tmpdir, "status.jsonl")),              patch.object(real_sup_paths, "SEARCH_COMMITMENTS_PATH", os.path.join(tmpdir, "commitments.jsonl")):

            # 创建空文件避免其他函数报错
            for p in [real_sup_paths.QUEUE, real_sup_paths.INPROGRESS,
                      real_sup_paths.POOL_PATH, real_sup_paths.SYMBOL_STATUS_PATH,
                      real_sup_paths.SEARCH_COMMITMENTS_PATH]:
                if not os.path.exists(p):
                    _write_jsonl(p, [])

            materialize_known_verdicts(
                snapshot={"m_crack_v2": {"variant_id": "m_crack_v2", "gate_pass": True,
                                          "fdr_pass": True, "status": "ok"}},
                dest_path=dest,
            )

        assert os.path.exists(dest)
        content = open(dest, encoding="utf-8").read()

        # 验证因果链节
        assert "Proposal-Verdict Causal Chain" in content
        assert "m_crack" in content

        # 验证拒收详情节
        assert "m_crack" in content
        assert "quality_below_threshold" in content

        # 验证演化视图节
        assert "Proposal Evolution" in content
        assert "m_crack" in content
        assert "v1 rejected" in content
        assert "v2 verdicted" in content


def test_render_open_trees_verdict_annotation(tmp_path):
    """render_open_trees should annotate member lines with verdict status."""
    import search_trees as st

    # Create a simple tree index
    commitments_path = str(tmp_path / "search_commitments.jsonl")
    with open(commitments_path, "w") as f:
        f.write(json.dumps({
            "schema": "fm.search_commitments.v1",
            "tree_id": "tree_A", "event": "accept",
            "symbol": "m", "family": "momentum",
            "search_role": "root"
        }) + "\n")
        f.write(json.dumps({
            "schema": "fm.search_commitments.v1",
            "tree_id": "tree_A", "event": "accept",
            "symbol": "m", "family": "momentum",
            "variant_id": "vid_1", "search_role": "exploit"
        }) + "\n")

    index = st.load_tree_index(commitments_path)

    # snapshot: vid_1 has a passing verdict
    snapshot = {
        "vid_1": {
            "variant_id": "vid_1",
            "status": "ok",
            "gate_pass": True,
            "fdr_pass": True,
            "dir_acc": 0.15,
            "effective_min": 0.10,
        }
    }

    lines = st.render_open_trees(index, snapshot)
    # Find vid_1 line
    vid_line = None
    for line in lines:
        if "vid_1" in line:
            vid_line = line
            break
    assert vid_line is not None, "vid_1 line not found"
    assert "PASS" in vid_line, f"Expected PASS annotation in: {vid_line}"


def test_prompt_has_proposal_feedback_section():
    """prompt_base.jinja2 should contain Proposal Feedback guidance."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "task_FM", "prompt_base.jinja2")
    content = open(prompt_path, encoding="utf-8").read()
    assert "Proposal Feedback" in content
    assert "known_verdicts.inc.md" in content
    assert "historical" in content.lower()

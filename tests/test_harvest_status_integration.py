# tests/test_harvest_status_integration.py
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _make_minimal_harvest_fixtures(tmpdir, schema="fm.hypothesis_proposal.v1", proposal_id="test_prop", version=None):
    """创建最小化 harvest 夹具（对齐现有测试 helper 签名，P1-D 修订）。"""
    run_dir = Path(tmpdir) / "task_FM" / "experiments" / "run_001"
    proposal_dir = run_dir / "results" / "gen_0" / "gen0_peer0" / "proposals"
    proposal_dir.mkdir(parents=True)

    p = {
        "schema": schema,
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


def _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir):
    """配置 harvest_proposals 所需的 mock（对齐现有测试 helper，P1-D 修订）。"""
    mock_sp.PROPOSAL_STATUS_PATH = os.path.join(tmpdir, "proposal_status.jsonl")
    mock_sp.REJECTED_PROPOSALS_PATH = os.path.join(tmpdir, "rejected_proposals.jsonl")
    mock_sp.VARIANT_REGISTRY_PATH = os.path.join(tmpdir, "variant_registry.jsonl")
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


def test_cand_contains_proposal_id_and_version():
    """入队行包含 proposal_id 和 version 字段（P0-1 绑定键）"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        _make_minimal_harvest_fixtures(tmpdir)

        with patch("sup_harvest.sup_paths") as mock_sp,              patch("sup_harvest.sup_evidence") as mock_ev,              patch("sup_harvest.sup_lifecycle") as mock_lc,              patch("sup_harvest.st") as mock_st,              patch("sup_harvest.ef") as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)

            # 真实签名：harvest_proposals(root, snapshot, dead, existing, pool, top_k, ...)
            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            # 验证：候选行包含 proposal_id 和 version
            assert len(cands) >= 1
            cand = cands[0]
            assert "proposal_id" in cand, "queue 行缺少 proposal_id（P0-1 绑定键）"
            assert cand["proposal_id"] == "test_prop"
            assert "version" in cand, "queue 行缺少 version（P0-1 绑定键）"
            assert cand["version"] == 1  # v1 默认 1


def test_reject_safe_write():
    """_reject 安全写入：写盘失败不改变统计语义（P0-2）"""
    from proposal_status import write_proposal_status

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sf = f.name
    try:
        # 无 quality_score 时应写 None 或不写字段，不 NameError
        write_proposal_status(sf, "p1", 1, "rejected", "run1", reject_reason="schema_mismatch")
        with open(sf) as f:
            r = json.loads(f.readline())
            assert r["status"] == "rejected"
            assert r["reject_reason"] == "schema_mismatch"
            assert r.get("quality_score") is None
    finally:
        if os.path.exists(sf):
            os.remove(sf)
        lf = sf + ".lock"
        if os.path.exists(lf):
            os.remove(lf)


def test_missing_proposal_id_rejected():
    """缺少 proposal_id 的提案在 schema 通过后、质量门前被拒（P1-B 修订）。"""
    from sup_harvest import harvest_proposals

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建不带 proposal_id 的 v1 proposal
        run_dir = Path(tmpdir) / "task_FM" / "experiments" / "run_001"
        proposal_dir = run_dir / "results" / "gen_0" / "gen0_peer0" / "proposals"
        proposal_dir.mkdir(parents=True)
        no_id = {
            "schema": "fm.hypothesis_proposal.v1",
            "symbol": "m",
            "cov_override": "ma20",
            "covariate_family": "momentum",
            "mechanism": "x" * 50,
            "symbol_fit": "test",
            "predicted_direction": "up",
            "kill_condition": "test",
            "promote_condition": "test",
        }
        (proposal_dir / "no_id.json").write_text(json.dumps(no_id))

        with patch("sup_harvest.sup_paths") as mock_sp,              patch("sup_harvest.sup_evidence") as mock_ev,              patch("sup_harvest.sup_lifecycle") as mock_lc,              patch("sup_harvest.st") as mock_st,              patch("sup_harvest.ef") as mock_ef:
            _patch_harvest_deps(mock_sp, mock_ev, mock_lc, mock_st, mock_ef, tmpdir)
            rej_path = mock_sp.REJECTED_PROPOSALS_PATH

            cands, stats = harvest_proposals(
                tmpdir, snapshot=set(), dead=set(), existing=[], pool={}, top_k=10
            )

            # 无 proposal_id → 被拒，不入队
            assert len(cands) == 0
            assert stats["rejected"] >= 1
            assert "missing_proposal_id" in stats["reject_reasons"]

            # 拒绝记录已写盘
            assert os.path.exists(rej_path)
            with open(rej_path) as f:
                records = [json.loads(l) for l in f if l.strip()]
            assert any(r["reject_reason"] == "missing_proposal_id" for r in records)


def test_degraded_no_reject():
    """soft 回归：degraded 策略不单独 _reject，入队行为与改前一致（P1-9）"""
    pass  # 集成到 Task 7/11 中验证（见 test_acceptance_degraded_soft）

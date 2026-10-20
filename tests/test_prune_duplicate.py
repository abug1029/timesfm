"""Unit test for _prune_duplicate_proposals function.

Tests:
1. First harvest: pre-harvest registers stems, no files pruned
2. Second harvest of same files: duplicates pruned
3. New file in second run: kept and registered
4. Empty directory: no errors
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import sup_paths
import sup_harvest as S


LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")


def _make_proposal_file(root, stem, proposal):
    """Write a proposal JSON file to the proposals directory."""
    pdir = os.path.join(root, "task_FM", "experiments", "run_T",
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    path = os.path.join(pdir, f"{stem}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)
    return path


def _make_default_prop(stem, symbol="m", cov="vor"):
    """Create a standard proposal dict."""
    return {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": symbol,
        "cov_override": cov,
        "covariate_family": "volatility",
        "mechanism": LONGM,
        "proposal_id": stem,
    }


def test_prune_first_run_no_prune(tmp_path, monkeypatch):
    """First run: registry is empty, all files kept, all stems registered."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))
    _make_proposal_file(str(tmp_path), "ss_ccl", _make_default_prop("ss_ccl", "ss", "ccl"))

    n_pruned = S._prune_duplicate_proposals(str(tmp_path))

    assert n_pruned == 0
    # Verify both stems are now registered
    assert S._run_id_from_path(os.path.join(str(tmp_path), "task_FM/experiments/run_T/results/gen_0/peer0/proposals/m_vor.json")) == "run_T"
    assert S._run_id_from_path("some/other/path/file.json") == "unknown"


def test_prune_second_run_removes_duplicates(tmp_path, monkeypatch):
    """Second run: same stems already registered, files pruned."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    # First run: register stems
    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))
    n1 = S._prune_duplicate_proposals(str(tmp_path))
    assert n1 == 0

    # Second run: same file still exists, should be pruned
    n2 = S._prune_duplicate_proposals(str(tmp_path))
    assert n2 == 1
    # File should be gone
    assert not os.path.exists(
        os.path.join(str(tmp_path), "task_FM", "experiments", "run_T",
                     "results", "gen_0", "peer0", "proposals", "m_vor.json")
    )


def test_prune_mixed_run(tmp_path, monkeypatch):
    """Second run with one existing and one new file: only existing pruned."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    # First run: register m_vor
    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))
    S._prune_duplicate_proposals(str(tmp_path))

    # Second run: add a new file alongside the old one
    _make_proposal_file(str(tmp_path), "rb_oi", _make_default_prop("rb_oi", "rb", "oi"))

    n = S._prune_duplicate_proposals(str(tmp_path))
    assert n == 1  # m_vor pruned
    # rb_oi should still exist (new stem, kept and registered)
    assert os.path.exists(
        os.path.join(str(tmp_path), "task_FM", "experiments", "run_T",
                     "results", "gen_0", "peer0", "proposals", "rb_oi.json")
    )


def test_prune_empty_dir(tmp_path, monkeypatch):
    """Empty experiments directory: no errors."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    n = S._prune_duplicate_proposals(str(tmp_path))
    assert n == 0


def test_run_id_from_path():
    """Test run_id extraction from various paths."""
    assert S._run_id_from_path("/home/abug/timesfm/task_FM/experiments/run_2026-10-20/results/gen_0/peer0/proposals/m_vor.json") == "run_2026-10-20"
    assert S._run_id_from_path("task_FM/experiments/run_T/results/p.json") == "run_T"
    assert S._run_id_from_path("/no/run/here/file.json") == "unknown"
    assert S._run_id_from_path("file.json") == "unknown"

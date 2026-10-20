"""Unit test for _prune_duplicate_proposals function.

Tests:
1. First harvest: prune does NOT register, no files pruned (empty registry)
2. After simulated harvest registration: duplicates pruned on second prune
3. New file alongside registered stem: only registered one pruned
4. Empty directory: no errors
5. run_id extraction
6. Prune does not register stems (new test for P1-1 fix)
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


def _simulate_harvest_registration(reg_path, stems):
    """Simulate what harvest does after queuing: write stems to registry."""
    from datetime import datetime, timezone
    with open(reg_path, "a", encoding="utf-8") as f:
        for stem in stems:
            rec = {"stem": stem, "first_seen": datetime.now(timezone.utc).isoformat(),
                   "run_id": "run_T"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _file_exists(root, stem):
    """Check if a proposal file exists."""
    return os.path.exists(
        os.path.join(root, "task_FM", "experiments", "run_T",
                     "results", "gen_0", "peer0", "proposals", f"{stem}.json"))


def test_prune_first_run_no_prune(tmp_path, monkeypatch):
    """First run: registry is empty, prune does NOT register, no files pruned."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))
    _make_proposal_file(str(tmp_path), "ss_ccl", _make_default_prop("ss_ccl", "ss", "ccl"))

    n_pruned = S._prune_duplicate_proposals(str(tmp_path))

    assert n_pruned == 0
    # Files still exist (prune does NOT register)
    assert _file_exists(str(tmp_path), "m_vor")
    assert _file_exists(str(tmp_path), "ss_ccl")
    # Registry is empty (prune does NOT register)
    assert not os.path.exists(reg_path)


def test_prune_does_not_register_stems(tmp_path, monkeypatch):
    """P1-1: prune must NOT register any stems."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))

    S._prune_duplicate_proposals(str(tmp_path))

    # Registry should not exist (prune does NOT call try_register or register)
    assert not os.path.exists(reg_path)


def test_prune_second_run_removes_duplicates(tmp_path, monkeypatch):
    """After harvest registration: prune removes duplicate files."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    # Create proposal file
    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))

    # Simulate harvest having registered this stem (what harvest does after queue)
    _simulate_harvest_registration(reg_path, ["m_vor"])

    # Now prune should remove the file (stem is already registered)
    n = S._prune_duplicate_proposals(str(tmp_path))
    assert n == 1
    # File should be gone
    assert not _file_exists(str(tmp_path), "m_vor")


def test_prune_mixed_run(tmp_path, monkeypatch):
    """Prune with one registered and one new stem: only registered one pruned."""
    reg_path = str(tmp_path / "variant_registry.jsonl")
    monkeypatch.setattr(sup_paths, "VARIANT_REGISTRY_PATH", reg_path)

    # Simulate harvest having registered m_vor
    _simulate_harvest_registration(reg_path, ["m_vor"])

    # Create files: one already registered, one new
    _make_proposal_file(str(tmp_path), "m_vor", _make_default_prop("m_vor"))
    _make_proposal_file(str(tmp_path), "rb_oi", _make_default_prop("rb_oi", "rb", "oi"))

    n = S._prune_duplicate_proposals(str(tmp_path))
    assert n == 1  # m_vor pruned
    # rb_oi should still exist (new stem, not in registry)
    assert _file_exists(str(tmp_path), "rb_oi")
    # m_vor should be gone
    assert not _file_exists(str(tmp_path), "m_vor")


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

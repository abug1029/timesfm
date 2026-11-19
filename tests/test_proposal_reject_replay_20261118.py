"""只读回放与分类函数。规格 2026-11-18-proposal-followup-design.md 第 1 步。"""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import sup_evidence
import sup_harvest

LONGM = (
    "波动率范围压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
    "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。"
)


def _kwargs(seen=None, evaluated=None):
    return dict(
        proposal_path="x.json",
        root="/tmp/replay-unit",
        pool={"vor": {"family": "volatility"}},
        snapshot={},
        dead=set(),
        existing=set(),
        passing_ids=set(),
        seen_vids=set() if seen is None else seen,
        evaluated=set() if evaluated is None else evaluated,
        status_map={},
        archived={},
        valid_covs={"vor"},
        allowed_syms={"m"},
        sg_cache={},
        search_check=lambda *args: (None, None),
    )


def test_classify_rejects_short_mechanism(monkeypatch):
    monkeypatch.setattr(
        sup_evidence, "_symbol_has_current_nocov_baseline", lambda symbol, root: True)
    proposal = {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": "m",
        "cov_override": "vor",
        "mechanism": "too short",
        "covariate_family": "volatility",
    }
    kind, reason, extra = sup_harvest.classify_loaded_proposal(proposal, **_kwargs())
    assert kind == "reject"
    assert reason == "mechanism_too_short"
    assert extra["bumps"] == []
    assert extra["success_state"] is None


import sup_paths
import registry_lib as rl

GOAL_TEXT = (
    "goal:\n"
    "  search_policy: \"shadow\"\n"
    "  cadence:\n"
    "    survivors_per_cycle: 3\n"
    "    aligned_max_points: 600\n"
)


def _install_fakes(monkeypatch):
    monkeypatch.setattr(
        sup_evidence, "_symbol_has_current_nocov_baseline", lambda symbol, root: True)
    monkeypatch.setattr(sup_evidence, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup_evidence, "_dead_families", lambda snapshot, min_ok=4: set())
    monkeypatch.setattr(sup_evidence, "_has_prior_failure", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        sup_evidence, "_success_delta_gate",
        lambda *args, **kwargs: (None, "no_prior_success"))
    monkeypatch.setattr(sup_evidence, "_active_protocol_snapshot", lambda path: {})
    monkeypatch.setattr(rl, "dead_variants", lambda snap: set())
    monkeypatch.setattr(rl, "in_flight_ids", lambda queue, inprogress: set())
    monkeypatch.setattr(rl, "pass_variants", lambda snap: [])
    monkeypatch.setattr(
        sup_harvest, "_load_evaluated_or_queued", lambda *args, **kwargs: set())
    monkeypatch.setattr(sup_evidence, "load_covariate_pool", lambda: {"vor": {"family": "volatility"}})
    monkeypatch.setattr(sup_evidence, "load_symbol_status", lambda: {})
    monkeypatch.setattr(sup_evidence, "_load_evaluator", lambda: None)
    monkeypatch.setattr(sup_harvest, "_proposal_priority_score", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(sup_harvest, "_cross_run_repeat_counts", lambda *args, **kwargs: {})


def _write_goal(root):
    path = root / "goal.yaml"
    path.write_text(GOAL_TEXT, encoding="utf-8")
    return str(path)


def _write_proposal(root, run_id, name, mechanism, mtime_ns):
    dest = root / "task_FM" / "experiments" / run_id / "results" / "gen_0" / "peer0" / "proposals"
    dest.mkdir(parents=True)
    payload = {
        "schema": "fm.hypothesis_proposal.v1",
        "symbol": "m",
        "cov_override": "vor",
        "covariate_family": "positioning",
        "mechanism": mechanism,
    }
    file_path = dest / name
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    # dest 是 proposals 目录，parents[3] 是 run 目录。
    os.utime(dest.parents[3], ns=(mtime_ns, mtime_ns))
    return file_path


def test_replay_short_mechanism_and_skips_prescreen(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    _write_proposal(tmp_path, RUN_IDS[0], "m_vor.json", "too short", 2_000_000_000_000_000_000)
    prescreen = (
        tmp_path / "task_FM" / "experiments" / RUN_IDS[0]
        / "results" / "gen_0" / "peer0" / "proposals" / "m_vor.prescreen.json")
    prescreen.write_text('{"status":"degraded"}', encoding="utf-8")
    out = tmp_path / "out.json"
    code = replay(str(tmp_path), str(out), goal)
    assert code == 0
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["failure_delta_rule"] == "length_only"
    reasons = [row["reason"] for row in body["files"]]
    assert reasons == ["mechanism_too_short"]
    assert body["proposal_json_excluding_prescreen"] == 1
    assert body["dominant_reject_inventory_calendar"] is None


def test_newer_directory_occupies_variant_id(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    # 目录新旧只看 mtime，不看目录名里的日期。
    _write_proposal(tmp_path, RUN_IDS[0], "new.json", LONGM, 2_000_000_000_000_000_000)
    _write_proposal(tmp_path, RUN_IDS[1], "old.json", LONGM, 1_000_000_000_000_000_000)
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    by_name = {Path(row["path"]).name: row for row in rows}
    assert by_name["new.json"]["kind"] == "ok"
    assert by_name["old.json"]["reason"] == "dedup"


def test_same_proposal_id_with_different_variant_is_not_dedup(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    newer = _write_proposal(tmp_path, RUN_IDS[0], "m.json", LONGM, 2_000_000_000_000_000_000)
    older = _write_proposal(tmp_path, RUN_IDS[1], "rb.json", LONGM, 1_000_000_000_000_000_000)
    for path, symbol in ((newer, "m"), (older, "rb")):
        body = json.loads(path.read_text(encoding="utf-8"))
        body["symbol"] = symbol
        body["proposal_id"] = "same-proposal-id"
        path.write_text(json.dumps(body), encoding="utf-8")
    # 改文件会带动目录 mtime。文件再往上 4 层才是 run 目录，写完再钉一次。
    os.utime(newer.parents[4], ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    os.utime(older.parents[4], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    assert sorted(row["kind"] for row in rows) == ["ok", "ok"]
    assert all(row["reason"] is None for row in rows)


def test_later_reject_still_occupies_variant_id(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(
        sup_harvest, "_sector_filter_check", lambda symbol, snapshot: (True, "x", []))
    goal = _write_goal(tmp_path)
    from proposal_reject_replay import RUN_IDS, replay
    _write_proposal(tmp_path, RUN_IDS[0], "new.json", LONGM, 2_000_000_000_000_000_000)
    _write_proposal(tmp_path, RUN_IDS[1], "old.json", LONGM, 1_000_000_000_000_000_000)
    out = tmp_path / "out.json"
    assert replay(str(tmp_path), str(out), goal) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))["files"]
    by_name = {Path(row["path"]).name: row for row in rows}
    assert by_name["new.json"]["reason"] == "sector_blocked"
    assert by_name["old.json"]["reason"] == "dedup"


def test_existing_output_is_left_byte_identical(tmp_path):
    goal = _write_goal(tmp_path)
    out = tmp_path / "out.json"
    out.write_bytes(b'{"keep":true}\n')
    before = out.read_bytes()
    marker = tmp_path / "not-a-directory"
    marker.write_text("x", encoding="utf-8")
    from proposal_reject_replay import replay
    assert replay(str(marker), str(out), goal) == 0
    assert out.read_bytes() == before


def test_replay_script_does_not_call_harvest_side_effects():
    path = Path(ROOT) / "scripts" / "proposal_reject_replay.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"harvest_proposals", "_prescreen_async", "_append_backlog", "_harvest_rows"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name not in banned
    supervised = list(Path(ROOT, "scripts").glob("sup_*.py"))
    supervised.append(Path(ROOT, "scripts", "praxist_supervisor.py"))
    for script in supervised:
        text = script.read_text(encoding="utf-8")
        assert "proposal_reject_replay" not in text
        assert "proposal_quality_census" not in text

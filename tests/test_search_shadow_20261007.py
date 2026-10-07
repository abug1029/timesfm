"""P2.9 shadow（spec 2026-10-05 §6.1 / §7 T1 后半）。

shadow 下树检查照常求值。本会拒绝的原因进入计数和决策日志。
入队结果与 off 相同。不写 search_commitments.jsonl。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402

LONGM = ("波动率范围(VOR)压缩后突破：该品种在低波区积蓄动能后常随放量突破，"
         "此微观结构机制在所选品种上有明确的持仓与季节性支撑，低波蓄能后的方向最可信。")
FP_TEST = "ab" * 32


def _make_run(root, proposal, filename=None):
    symbol = str(proposal.get("symbol", "m")).lower()
    cov = proposal.get("cov_override") or "newcov"
    pdir = os.path.join(root, "task_FM", "experiments", "run_T",
                        "results", "gen_0", "peer0", "proposals")
    os.makedirs(pdir, exist_ok=True)
    fn = filename or ("%s_%s.json" % (symbol, cov))
    with open(os.path.join(pdir, fn), "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False)


def _prop(**over):
    family = over.pop("family", "volatility")
    p = {"schema": "fm.hypothesis_proposal.v1", "symbol": "m",
         "cov_override": "vor", "covariate_family": family,
         "mechanism": LONGM, "symbol_fit": "该品种适配该协变量",
         "kill_condition": "ev<0", "promote_condition": "gate"}
    p.update(over)
    return p


def _harvest(root, policy, snap=None):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(
        root, snap or {}, set(), set(), pool, top_k=5,
        search_policy=policy)


def test_shadow_counts_missing_role_and_keeps_enqueue(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(tmp_path / "symbol_status.json"))
    (tmp_path / "symbol_status.json").write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    commitments = tmp_path / "search_commitments.jsonl"
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", str(commitments))
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    symbol = "m"
    base = config / ("baseline_points_%s_nocov.jsonl" % symbol)
    base.write_text(json.dumps({
        "protocol_fingerprint": "current-protocol",
        "cutoff": "2026-01-01 00:00:00",
        "dir_ok": True,
    }) + "\n", encoding="utf-8")
    root = str(tmp_path)
    _make_run(root, _prop())
    rows_off, stats_off = _harvest(root, "off")
    _make_run(root, _prop())
    rows_sh, stats_sh = _harvest(root, "shadow")
    assert [r["variant_id"] for r in rows_sh] == [r["variant_id"] for r in rows_off]
    assert stats_off["selected"] == stats_sh["selected"] == 1
    assert "search_role" not in rows_sh[0]
    assert stats_sh["search_would_reject"].get("search_role_missing") == 1
    assert any(item.startswith("search_role_missing") for item in stats_sh["search_shadow_log"])
    for reason in stats_sh["reject_reasons"]:
        assert not str(reason).startswith("search_")
    assert not commitments.exists()


def test_shadow_does_not_write_commitments_for_a_legal_root(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(tmp_path / "symbol_status.json"))
    (tmp_path / "symbol_status.json").write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    commitments = tmp_path / "search_commitments.jsonl"
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", str(commitments))
    config = tmp_path / "task_FM" / "config"
    config.mkdir(parents=True)
    (config / "baseline_points_m_nocov.jsonl").write_text(json.dumps({
        "protocol_fingerprint": "current-protocol",
        "cutoff": "2026-01-01 00:00:00",
        "dir_ok": True,
    }) + "\n", encoding="utf-8")
    _make_run(str(tmp_path), _prop(
        search_role="root", search_parent_id="", tree_id=""))
    rows, stats = _harvest(str(tmp_path), "shadow")
    assert stats["selected"] == 1
    assert rows[0].get("search_role") is None
    assert stats["search_would_reject"] == {}
    assert not commitments.exists()

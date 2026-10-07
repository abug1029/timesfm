"""P2.7 晋升（spec 2026-10-05 §6.6 / §7 T8 T15 T16）。

六条件同时成立才晋升：树尚未因预算或上界停止、δ_post 最大且 > 0、
n_required(途径 B) 不超过该品种已锁定样本量、incremental 为 pass 或
not_applicable、gate_pass 为真、eval_end_ts 存在。追加恰好一行预注册，
n 继承锁定值，既有行不变。eval_end_ts 缺失则不晋升。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import praxist_supervisor as S  # noqa: E402
import search_promote as P  # noqa: E402
import search_trees as st  # noqa: E402
from cascade.statistical_tests import n_required  # noqa: E402

FP = "ab" * 32


def _lock(symbol="jd", n=1199, confirm_from="2026-10-03 00:00:00"):
    return {
        "prereg_id": "lock-" + symbol,
        "symbol": symbol,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"], "n_channels": 2,
                            "hash_version": "cov_matrix_hash_v1"},
        "model_fingerprint": {"weights_sha256": "778773a8e8bcbb23", "n_files": 1,
                              "hash_version": "v1"},
        "predict_params": {"context_bars": 480, "horizon_days": 22},
        "horizon": 24,
        "metric_version": "v1",
        "n_confirm_required": n,
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": confirm_from,
        "delta_star": 0.08,
        "power": 0.8,
        "alpha": 0.05,
        "var_lr": 1.24,
        "kill_condition": {"field": "d_mean", "threshold": 0.0},
        "promote_condition": {"field": "d_mean", "threshold": 0.08},
        "mechanism": "locked",
        "predicted_direction": "locked",
        "terminal_state": None,
    }


def _row(vid, **over):
    row = {
        "variant_id": vid,
        "symbol": "jd",
        "cov_override": "rsi_state",
        "cov_family": "momentum",
        "status": "ok",
        "gate_pass": True,
        "dir_acc": 0.62,
        "baseline_dir_acc": 0.50,
        "delta_post_shrunk": 0.096,
        "search_var_lr": 0.2352,
        "incremental_vs_incumbent": "not_applicable",
        "eval_end_ts": "2026-10-04 00:00:00",
        "protocol_fingerprint": FP,
        "cov_fingerprint": {"keys": ["daily_slope", "rsi_state"],
                            "matrix_sha256": "abc", "n_channels": 2,
                            "hash_version": "cov_matrix_hash_v1"},
    }
    row.update(over)
    return row


def _tree(tmp_path, vid="jd_mom_1"):
    path = str(tmp_path / "search_commitments.jsonl")
    st.append_commitment(
        path, "accept", tree_id="jd::momentum::root",
        symbol="jd", family="momentum",
        proposal_id=str(tmp_path / "proposal.json"),
        variant_id=vid, search_role="root")
    index = st.load_tree_index(path)
    return path, index.trees["jd::momentum::root"]


def _proposal(path):
    path.write_text(json.dumps({
        "schema": "fm.hypothesis_proposal.v1",
        "mechanism": "鸡蛋低波压缩后的持仓变化领先节日需求突破，这次用 rsi 而不是 vor。",
        "predicted_direction": "rsi_turn -> long",
    }, ensure_ascii=False), encoding="utf-8")


def test_T16_missing_eval_end_ts_does_not_promote(tmp_path):
    vid = "jd_mom_1"
    _path, tree = _tree(tmp_path, vid)
    snap = {vid: _row(vid, eval_end_ts=None)}
    assert P.evaluate_tree_promotion(tree, snap, [_lock()]) is None


def test_does_not_promote_when_n_required_exceeds_locked_sample(tmp_path):
    vid = "jd_mom_1"
    _path, tree = _tree(tmp_path, vid)
    snap = {vid: _row(vid, delta_post_shrunk=0.0384, search_var_lr=0.5292)}
    n = n_required(var_d=0.5292, vif=1.0, z_alpha=1.645, z_beta=0.842,
                  delta=0.0384)
    assert n > 1199
    assert P.evaluate_tree_promotion(tree, snap, [_lock()]) is None


def test_does_not_promote_without_a_symbol_lock(tmp_path):
    vid = "m_mom_1"
    path = str(tmp_path / "search_commitments.jsonl")
    st.append_commitment(path, "accept", tree_id="m::momentum::root",
                         symbol="m", family="momentum",
                         proposal_id="p", variant_id=vid, search_role="root")
    tree = st.load_tree_index(path).trees["m::momentum::root"]
    snap = {vid: _row(vid, symbol="m")}
    assert P.evaluate_tree_promotion(tree, snap, [_lock("jd")]) is None


def test_does_not_promote_when_incremental_fails(tmp_path):
    vid = "jd_mom_1"
    _path, tree = _tree(tmp_path, vid)
    snap = {vid: _row(vid, incremental_vs_incumbent="fail")}
    assert P.evaluate_tree_promotion(tree, snap, [_lock()]) is None


def test_T8_promotion_appends_one_row_and_keeps_existing(tmp_path, monkeypatch):
    vid = "jd_mom_1"
    commitments, tree = _tree(tmp_path, vid)
    proposal = tmp_path / "proposal.json"
    _proposal(proposal)
    snap = {vid: _row(vid)}
    registry = [_lock(), _lock("sr", n=986)]
    decision = P.evaluate_tree_promotion(tree, snap, registry)
    assert decision is not None
    n = n_required(var_d=0.2352, vif=1.0, z_alpha=1.645, z_beta=0.842,
                  delta=0.096)
    assert n <= 1199
    assert decision["n_required"] == n
    assert decision["n_confirm_required"] == 1199
    assert decision["confirm_from_ts"] == "2026-10-04 00:00:00"
    mechanism, direction = P.read_proposal_copy(str(tmp_path), decision["proposal_id"])
    row = P.build_promotion_prereg(
        decision, mechanism=mechanism, predicted_direction=direction,
        registered_at="2026-10-07T00:00:00+00:00", prereg_id="new-id")
    extra = [k for k in row["cov_fingerprint"]["keys"] if k != "daily_slope"]
    assert extra == ["rsi_state"]
    assert row["n_confirm_required"] == 1199
    assert row["var_lr"] == pytest.approx(0.2352)
    assert row["mechanism"].startswith("鸡蛋低波")
    assert row["predicted_direction"] == "rsi_turn -> long"
    assert row["delta_star"] == 0.08
    assert row["kill_condition"]["threshold"] == 0.0

    prereg = tmp_path / "preregistry.jsonl"
    prereg.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registry),
        encoding="utf-8")
    before = prereg.read_text(encoding="utf-8")
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", commitments)
    monkeypatch.setattr(S, "PREREGISTRY_PATH", str(prereg))
    monkeypatch.setattr(S, "FM_ROOT", str(tmp_path))
    n_promoted = S._sweep_search_promotions(
        {"search_policy": "enforce"}, [], snap)
    assert n_promoted == 1
    lines = [ln for ln in prereg.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3
    assert prereg.read_text(encoding="utf-8").startswith(before)
    added = json.loads(lines[-1])
    assert added["n_confirm_required"] == 1199
    assert [k for k in added["cov_fingerprint"]["keys"] if k != "daily_slope"] == ["rsi_state"]
    assert json.loads(lines[0])["prereg_id"] == "lock-jd"
    assert json.loads(lines[1])["prereg_id"] == "lock-sr"
    events = [json.loads(ln) for ln in open(commitments, encoding="utf-8") if ln.strip()]
    assert [e["event"] for e in events] == ["accept", "promote"]
    assert events[-1]["stop_reason"] == "promoted"
    assert events[-1]["n_required"] == n


def test_T15_appended_row_is_dispatched(tmp_path, monkeypatch):
    vid = "jd_mom_1"
    commitments, _tree_obj = _tree(tmp_path, vid)
    _proposal(tmp_path / "proposal.json")
    prereg = tmp_path / "preregistry.jsonl"
    prereg.write_text(json.dumps(_lock(), ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", commitments)
    monkeypatch.setattr(S, "PREREGISTRY_PATH", str(prereg))
    monkeypatch.setattr(S, "FM_ROOT", str(tmp_path))
    snap = {vid: _row(vid)}
    assert S._sweep_search_promotions({"search_policy": "enforce"}, [], snap) == 1
    registry = S.load_preregistry(str(prereg))
    out = S.due_confirmations(
        registry, "2026-10-08 00:00:00", set(), set(),
        fingerprint_for=lambda symbol, cov: FP,
        family_for=lambda cov: "momentum")
    matched = [r for r in out if r["cov_override"] == "rsi_state"]
    assert len(matched) == 1
    assert matched[0]["n_confirm_required"] == 1199
    assert matched[0]["run_mode"] == "confirmation"
    assert matched[0]["symbol"] == "jd"


def test_off_policy_does_not_append(tmp_path, monkeypatch):
    vid = "jd_mom_1"
    commitments, _tree_obj = _tree(tmp_path, vid)
    prereg = tmp_path / "preregistry.jsonl"
    prereg.write_text(json.dumps(_lock()) + "\n", encoding="utf-8")
    before = prereg.read_bytes()
    monkeypatch.setattr(S, "SEARCH_COMMITMENTS_PATH", commitments)
    monkeypatch.setattr(S, "PREREGISTRY_PATH", str(prereg))
    assert S._sweep_search_promotions(
        {"search_policy": "off"}, [], {vid: _row(vid)}) == 0
    assert prereg.read_bytes() == before

def test_finite_rejects_bool():
    assert P._finite(True) is None
    assert P._finite(0.096) == 0.096


def test_mismatched_cov_keys_do_not_keep_the_other_matrix_hash():
    decision = {
        "symbol": "jd",
        "cov_override": "oi",
        "n_confirm_required": 1199,
        "confirm_from_ts": "2026-10-04 00:00:00",
        "var_lr": 0.2352,
        "lock": _lock(),
        "cov_fingerprint": {
            "keys": ["daily_slope", "oi_pct_change"],
            "n_channels": 2,
            "hash_version": "cov_matrix_hash_v1",
            "matrix_sha256": "abc",
        },
    }
    row = P.build_promotion_prereg(
        decision, mechanism="持仓变化对应方向", predicted_direction="oi up -> long",
        registered_at="2026-10-07T00:00:00", prereg_id="p-alias")
    assert row["cov_fingerprint"]["keys"] == ["daily_slope", "oi"]
    assert "matrix_sha256" not in row["cov_fingerprint"]

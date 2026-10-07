"""确认运行接线：窗口、checkpoint 命名空间、分派与终结。

不调用模型，不读 TimesFM 权重。索引只走 select_eval_indices。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from config.backtest_config import (  # noqa: E402
    CONTEXT_BARS, EVAL_WINDOW_BARS, HORIZON, STEP,
)

import monthly_backtest as mb  # noqa: E402
import preregistry as pr  # noqa: E402
import aligned_slow_loop as asl  # noqa: E402
import praxist_supervisor as sv  # noqa: E402


def _legacy_indices(total, max_points=None):
    eval_start = max(CONTEXT_BARS, total - EVAL_WINDOW_BARS)
    indices = list(range(eval_start, total - HORIZON + 1, STEP))
    if max_points is not None:
        indices = indices[:max_points]
    return indices


def _dts(n):
    return (
        pd.date_range("2024-01-01", periods=n, freq="h")
        .strftime("%Y-%m-%d %H:%M:%S")
        .tolist()
    )


def _close(dt):
    return (pd.Timestamp(dt) + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def _passing_row(**overrides):
    row = {
        "run_mode": "confirmation",
        "contaminated": False,
        "early_sealed": False,
        "n_confirm_actual": 1199,
        "n_confirm_required": 1199,
        "common_insufficient": False,
        "meets_min_info": True,
        "gate_pass": True,
        "p_value": 0.01,
        "covariates_used": True,
        "pairing_valid": True,
        "missingness_admissible": True,
        "protocol_compatible": True,
        "dm_significant": True,
        "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d",
        "fdr_pass": None,
        "variant_id": "jd_vor_abc",
        "admissibility_rule": "edge_continuous_block_30d",   # 步③ B
    }
    row.update(overrides)
    return row


def _member(variant_id, status="registered"):
    registered = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return {
        "family_key": sv.family_key_for("jd"),
        "symbol": "jd",
        "variant_id": variant_id,
        "registered_at": registered.isoformat(),
        "status": status,
        "p_value": None,
        "p_value_family_adjusted": None,
    }


# ── 评估索引 ──────────────────────────────────────────────────


def test_no_eval_start_ts_matches_legacy_tail_window():
    total = CONTEXT_BARS + EVAL_WINDOW_BARS + 80
    dts = _dts(total)
    assert mb.select_eval_indices(dts) == _legacy_indices(total)
    assert mb.select_eval_indices(dts, eval_start_ts=None) == _legacy_indices(total)
    assert mb.select_eval_indices(dts, max_points=7) == _legacy_indices(total, 7)


def test_eval_start_ts_drops_prior_bars_and_takes_forward_prefix():
    total = CONTEXT_BARS + EVAL_WINDOW_BARS + 80
    dts = _dts(total)
    # 501 不在从 CONTEXT_BARS 起、步长 STEP 的网格上，左边界必须是这一根。
    boundary = CONTEXT_BARS + 21
    assert boundary % STEP != CONTEXT_BARS % STEP
    start = _close(dts[boundary])
    got = mb.select_eval_indices(dts, eval_start_ts=start, max_points=4)
    assert boundary - 1 not in got
    assert got == list(range(boundary, boundary + 4 * STEP, STEP))
    tail_prefix = _legacy_indices(total, 4)
    assert got != tail_prefix
    assert got[0] < tail_prefix[0]
    assert max(got) <= total - HORIZON


def test_eval_start_before_context_still_starts_at_context_bars():
    total = CONTEXT_BARS + EVAL_WINDOW_BARS + 80
    dts = _dts(total)
    got = mb.select_eval_indices(dts, eval_start_ts="2000-01-01 00:00:00", max_points=3)
    assert got == list(range(CONTEXT_BARS, CONTEXT_BARS + 3 * STEP, STEP))
    assert got != _legacy_indices(total, 3)


# ── checkpoint 文件名 ─────────────────────────────────────────


def test_checkpoint_filename_namespaces_prereg_id():
    assert pr.checkpoint_filename("jd_vor", None) == "jd_vor.jsonl"
    assert pr.checkpoint_filename("jd_vor", "") == "jd_vor.jsonl"
    assert (
        pr.checkpoint_filename("jd_vor", "abcdef0123456789")
        == "jd_vor__prereg_abcdef01.jsonl"
    )


def _row(**overrides):
    row = {
        "variant_id": "m_rsi_state",
        "symbol": "m",
        "cov_override": "rsi_state",
        "max_points": 400,
        "stage": "aligned",
    }
    row.update(overrides)
    return row


def _install_slow_fakes(monkeypatch, tmp_path, summary):
    captured = {}

    def _bt(*args, **kwargs):
        captured["bt_args"] = args
        captured["bt_kwargs"] = kwargs
        return {"contract": "M", "points": [{"dir_ok": True}]}

    monkeypatch.setattr(mb, "run_symbol_backtest", _bt)
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 1, "dir_acc": 0.5})
    monkeypatch.setattr(asl, "_get_models", lambda: (_Sentinel("daily"), _Sentinel("hourly")))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    monkeypatch.setattr(asl, "build_summary", summary)
    return captured


class _Sentinel:
    def __init__(self, name):
        self.name = name


def _summary_factory(n, classify=False):
    def _summary(s, cand, **kwargs):
        verdict = {
            "schema": "fm.aligned_verdict.v2",
            "status": "ok",
            "stage": "aligned",
            "symbol": cand["symbol"],
            "cov_override": cand["cov_override"],
            "batch_id": kwargs.get("batch_id"),
            "n": n,
            "n_eff": n,
            "dir_acc": 0.55,
            "gate_pass": True,
            "p_value": 0.01,
            "fdr_pass": None,
            "run_mode": kwargs.get("run_mode", "exploration"),
            "run_label": (
                "exploratory_unconfirmed"
                if kwargs.get("run_mode", "exploration") == "exploration"
                else None
            ),
        }
        if classify:
            verdict.update({
                "contaminated": False,
                "early_sealed": False,
                "common_insufficient": False,
                "meets_min_info": True,
                "covariates_used": True,
                "pairing_valid": True,
                "missingness_admissible": True,
                "protocol_compatible": True,
                "dm_significant": True,
                "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d",
            })
        return verdict

    return _summary


def test_exploration_keeps_plain_checkpoint_and_omits_eval_start(tmp_path, monkeypatch):
    captured = _install_slow_fakes(
        monkeypatch, tmp_path, _summary_factory(400),
    )
    verdict = asl.run_aligned_candidate(
        _row(confirm_from_ts="2026-10-01 00:00:00", n_confirm_required=50),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )
    assert "eval_start_ts" not in captured["bt_kwargs"]
    assert captured["bt_kwargs"]["max_points"] == 400
    assert (tmp_path / "cp" / "m_rsi_state.jsonl").is_file()
    assert verdict["run_label"] == "exploratory_unconfirmed"
    assert verdict["fdr_pass"] is not True
    assert not list((tmp_path / "cp").glob("*__prereg_*"))


def test_confirmation_uses_prereg_checkpoint_window_and_label(tmp_path, monkeypatch):
    prereg_id = "abcdef0123456789"
    captured = _install_slow_fakes(
        monkeypatch, tmp_path, _summary_factory(30, classify=True),
    )
    verdict = asl.run_aligned_candidate(
        _row(
            run_mode="confirmation",
            prereg_id=prereg_id,
            confirm_from_ts="2026-10-01 00:00:00",
            n_confirm_required=30,
            max_points=4,
        ),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )
    assert captured["bt_kwargs"]["eval_start_ts"] == "2026-10-01 00:00:00"
    assert captured["bt_kwargs"]["max_points"] == 30
    assert (tmp_path / "cp" / "m_rsi_state__prereg_abcdef01.jsonl").is_file()
    assert not (tmp_path / "cp" / "m_rsi_state.jsonl").exists()
    assert verdict["run_mode"] == "confirmation"
    assert verdict["run_label"] == "confirmed"
    assert verdict["fdr_pass"] is not True


def _build_summary_shaped(**extra):
    def _summary(s, cand, **kwargs):
        verdict = {
            "schema": "fm.aligned_verdict.v2",
            "status": "ok",
            "stage": "aligned",
            "symbol": cand["symbol"],
            "cov_override": cand["cov_override"],
            "batch_id": kwargs.get("batch_id"),
            "n": 30,
            "n_eff": 30,
            "dir_acc": 0.55,
            "gate_pass": True,
            "p_value": 0.01,
            "d_bar_le_zero": False,
            "fdr_pass": None,
            "run_mode": kwargs.get("run_mode", "exploration"),
            "run_label": None,
            "dm_status": "ok", "admissibility_rule": "edge_continuous_block_30d",
            "pairing_valid": True,
            "missingness_admissible": True,
            "covariates_used": True,
            "n_confirm_actual": 30,
            "n_confirm_required": 30,
        }
        verdict.update(extra)
        return verdict

    return _summary


def _run_shaped_confirmation(tmp_path, monkeypatch, **extra):
    _install_slow_fakes(monkeypatch, tmp_path, _build_summary_shaped(**extra))
    return asl.run_aligned_candidate(
        _row(
            run_mode="confirmation",
            prereg_id="abcdef0123456789",
            confirm_from_ts="2026-10-01 00:00:00",
            n_confirm_required=30,
        ),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )


def test_build_summary_shape_without_meets_min_info_stays_underpowered(tmp_path, monkeypatch):
    verdict = _run_shaped_confirmation(tmp_path, monkeypatch)
    assert "meets_min_info" not in verdict
    assert verdict["run_label"] == "underpowered"
    assert verdict["fdr_pass"] is not True


def test_build_summary_shape_with_meets_min_info_is_confirmed(tmp_path, monkeypatch):
    verdict = _run_shaped_confirmation(tmp_path, monkeypatch, meets_min_info=True)
    assert verdict["meets_min_info"] is True
    assert verdict["run_label"] == "confirmed"
    assert verdict["fdr_pass"] is not True


def _checkpoint_line(symbol, cutoff, anchor):
    return json.dumps({
        "symbol": symbol,
        "cutoff": cutoff,
        "eval_end_ts": anchor,
        "protocol_fingerprint": asl.compute_protocol_fingerprint(),
        "delta_pred": 1.0,
        "delta_real": 1.0,
    }, ensure_ascii=False)


def test_confirmation_admits_bars_after_anchor_until_sample_fills(tmp_path, monkeypatch):
    n_short = CONTEXT_BARS + HORIZON + 8
    short = _dts(n_short)
    grown = _dts(n_short + 40)
    anchor = _close(short[-1])
    confirm_from = _close(short[CONTEXT_BARS + 4])
    # 锚等于短序列末根收盘。按 dt < 锚 截断后，新 bar 全部消失。
    pinned = [dt for dt in grown if dt < anchor]
    assert pinned == short
    pinned_idx = mb.select_eval_indices(pinned, eval_start_ts=confirm_from)
    assert pinned_idx
    assert all(i < n_short for i in pinned_idx)

    # 确认样本未满：不传锚，右边界留在加长后的数据末端。
    assert asl._eval_end_ts_for_run("confirmation", anchor, 1, 30) is None
    eligible = mb.select_eval_indices(grown, eval_start_ts=confirm_from, max_points=30)
    assert any(i >= n_short for i in eligible)
    # 样本已满才重新钉住锚。
    assert asl._eval_end_ts_for_run("confirmation", anchor, 30, 30) == anchor

    fp_dir = tmp_path / "cp"
    fp_dir.mkdir()
    (fp_dir / "m_rsi_state.jsonl").write_text(
        _checkpoint_line("m", confirm_from, anchor) + "\n", encoding="utf-8")
    captured = _install_slow_fakes(monkeypatch, tmp_path, _summary_factory(4))
    asl.run_aligned_candidate(
        _row(),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(fp_dir),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )
    assert captured["bt_kwargs"]["eval_end_ts"] == anchor

    conf_dir = tmp_path / "cp2"
    conf_dir.mkdir()
    (conf_dir / "m_rsi_state__prereg_abcdef01.jsonl").write_text(
        _checkpoint_line("m", confirm_from, anchor) + "\n", encoding="utf-8")
    captured_conf = _install_slow_fakes(
        monkeypatch, tmp_path, _summary_factory(1, classify=True),
    )
    asl.run_aligned_candidate(
        _row(
            run_mode="confirmation",
            prereg_id="abcdef0123456789",
            confirm_from_ts=confirm_from,
            n_confirm_required=30,
        ),
        daily_cache_dir=str(tmp_path / "dc2"),
        checkpoint_dir=str(conf_dir),
        registry_path=str(tmp_path / "verdicts2.jsonl"),
    )
    assert captured_conf["bt_kwargs"]["eval_end_ts"] is None
    assert captured_conf["bt_kwargs"]["eval_start_ts"] == confirm_from
    assert captured_conf["bt_kwargs"]["max_points"] == 30
    assert len(captured_conf["bt_kwargs"]["completed"]) == 1


def test_confirmation_short_sample_does_not_write_label(tmp_path, monkeypatch):
    captured = _install_slow_fakes(
        monkeypatch, tmp_path, _summary_factory(3, classify=True),
    )
    verdict = asl.run_aligned_candidate(
        _row(
            run_mode="confirmation",
            prereg_id="abcdef0123456789",
            confirm_from_ts="2026-10-01 00:00:00",
            n_confirm_required=30,
        ),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )
    assert captured["bt_kwargs"]["max_points"] == 30
    assert verdict["run_label"] is None
    assert verdict["run_label"] != "confirmed"
    assert verdict["fdr_pass"] is not True


# ── 监督器分派与终结 ──────────────────────────────────────────


def _registry(prereg_id="abcdef0123456789"):
    return [{
        "prereg_id": prereg_id,
        "registered_at": "2026-10-01T00:00:00+00:00",
        "symbol": "jd",
    }]


def test_dispatch_rejects_missing_id_without_family_register():
    members = []
    out = sv.dispatch_confirmation(
        {"symbol": "jd", "variant_id": "jd_vor_abc"},
        _registry(),
        members,
    )
    assert out["accepted"] is False
    assert out["reason"] == "no_prereg_id"
    assert out["members"] is members
    assert members == []


def test_dispatch_accepts_locked_id_and_registers_family():
    prereg_id = "abcdef0123456789"
    out = sv.dispatch_confirmation(
        {
            "prereg_id": prereg_id,
            "symbol": "jd",
            "variant_id": "jd_vor_abc",
        },
        _registry(prereg_id),
        [],
    )
    assert out["accepted"] is True
    assert out["reason"] is None
    assert len(out["members"]) == 1
    member = out["members"][0]
    assert member["variant_id"] == "jd_vor_abc"
    assert member["symbol"] == "jd"
    assert member["status"] == "registered"
    assert member["family_key"] == sv.family_key_for("jd")


def test_finalize_short_sample_returns_peek_audit_and_not_confirmed():
    members = [_member("jd_vor_abc")]
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    row = _passing_row(n_confirm_actual=10, n_confirm_required=1199, run_label=None)
    out = sv.finalize_confirmation(row, members, now)
    assert out["audit"]["event"] == "no_peek_rejected"
    assert out["audit"]["n_actual"] == 10
    assert out["audit"]["n_required"] == 1199
    assert out["run_label"] is None
    assert out["run_label"] != "confirmed"
    assert out["sealed"] is False
    assert out["members"] is members
    assert members[0]["status"] == "registered"


def test_finalize_early_seal_underpowered_seals_with_adjusted_p_one():
    members = [_member("jd_vor_abc")]
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    row = _passing_row(
        n_confirm_actual=10,
        n_confirm_required=1199,
        request_early_seal=True,
        p_value=0.01,
    )
    out = sv.finalize_confirmation(row, members, now)
    assert out["run_label"] == "underpowered"
    assert out["audit"] is None
    assert out["sealed"] is True
    assert out["members"][0]["status"] == "underpowered"
    assert out["members"][0]["p_value_family_adjusted"] == 1.0
    assert out["members"][0]["family_sealed_at"]
    assert out.get("fdr_pass") is not True
    assert out["members"][0].get("fdr_pass") is not True


def test_finalize_seals_only_when_every_member_is_terminal():
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    row = _passing_row()
    partial = [_member("jd_vor_abc"), _member("jd_other")]
    held = sv.finalize_confirmation(row, partial, now)
    assert held["run_label"] == "confirmed"
    assert held["sealed"] is False
    assert held["members"][0]["status"] == "confirmed"
    assert held["members"][1]["status"] == "registered"
    assert "family_sealed_at" not in held["members"][0]
    assert held["members"][0].get("fdr_pass") is not True

    ready = [_member("jd_vor_abc"), _member("jd_other", status="refuted")]
    sealed = sv.finalize_confirmation(row, ready, now)
    assert sealed["run_label"] == "confirmed"
    assert sealed["sealed"] is True
    assert sealed["members"][0]["status"] == "confirmed"
    assert sealed["members"][0]["family_sealed_at"]
    assert sealed["members"][1]["status"] == "refuted"
    assert sealed["members"][0].get("fdr_pass") is not True
    assert sealed["members"][1].get("fdr_pass") is not True


def test_due_confirmation_row_uses_the_locked_preregistration():
    jd = {
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "symbol": "jd",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    sr = {
        "prereg_id": "ef908a2214e141abaa2d480ca82b53bb",
        "symbol": "sr",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 986,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vwap_deviation"]},
    }
    early = dict(jd)
    early["prereg_id"] = "too-early"
    early["confirm_from_ts"] = "2026-10-04 00:00:00"
    assert sv._requested_covariate(jd) == "vor"
    assert sv._requested_covariate({"cov_fingerprint": {"keys": ["daily_slope"]}}) is None
    due = sv.due_confirmations(
        [jd, sr, early],
        "2026-10-03 12:00:00",
        blocked_ids=set(),
        already_ran_ids=set(),
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert [row["symbol"] for row in due] == ["jd", "sr"]
    assert due[0]["run_mode"] == "confirmation"
    assert due[0]["variant_id"] == "jd_momentum_" + ("ab" * 32)[:12]
    assert due[0]["cov_override"] == "vor"
    assert due[0]["prereg_id"] == jd["prereg_id"]
    assert due[0]["confirm_from_ts"] == "2026-10-03 00:00:00"
    assert due[0]["n_confirm_required"] == 1199
    assert due[0]["max_points"] == 1199
    assert due[0]["source"] == "confirmation"
    assert "request_early_seal" not in due[0]
    blocked = sv.due_confirmations(
        [jd], "2026-10-03 12:00:00",
        blocked_ids={due[0]["variant_id"]},
        already_ran_ids=set(),
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert blocked == []
    ran = sv.due_confirmations(
        [jd], "2026-10-03 12:00:00",
        blocked_ids=set(),
        already_ran_ids={jd["prereg_id"]},
        fingerprint_for=lambda symbol, cov: "ab" * 32,
        family_for=lambda cov: "momentum",
    )
    assert ran == []


def test_enqueue_due_confirmation_then_peek_does_not_seal(tmp_path, monkeypatch):
    prereg_path = tmp_path / "preregistry.jsonl"
    family_path = tmp_path / "family_registry.jsonl"
    queue_path = tmp_path / "pending.jsonl"
    jd = {
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "symbol": "jd",
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    prereg_path.write_text(json.dumps(jd) + "\n", encoding="utf-8")
    monkeypatch.setattr(sv, "PREREGISTRY_PATH", str(prereg_path))
    monkeypatch.setattr(sv, "FAMILY_REGISTRY", str(family_path))
    monkeypatch.setattr(sv, "QUEUE", str(queue_path))
    monkeypatch.setattr(sv, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sv, "_experiment_fp_for", lambda symbol, cov: "ab" * 32)
    # 2026-10-03：数据闸门（D1）桩——确认集数据未越过 confirm_from_ts 时不派发
    # （否则空评估 + no_data 墓碑 + 去重失效 = 每轮重复入队）。本测试关注
    # 「派发 → peek」链路，故显式放行；闸门本身由 test_confirm_bugs_20261003.py 覆盖。
    monkeypatch.setattr(sv, "_confirm_data_ready", lambda s, t: True)
    monkeypatch.setattr(sv, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sv, "_active_protocol_snapshot", lambda path: {})
    sv._CONFIRM_REDISPATCH.clear()   # 2026-10-04（E2）：重派节流是进程内状态，测试间必须清
    n = sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00")
    assert n == 1
    queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert queued[0]["run_mode"] == "confirmation"
    assert queued[0]["max_points"] == 1199
    members = sv.load_family_members(str(family_path))
    assert len(members) == 1
    assert members[0]["status"] == "registered"
    # 同一 vid 已在队里，第二轮不再入队，也不抢占。
    assert sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00") == 0
    verdict = {
        "variant_id": queued[0]["variant_id"],
        "run_mode": "confirmation",
        "prereg_id": jd["prereg_id"],
        "n": 10,
        "n_confirm_required": 1199,
        "p_value": 0.01,
        "gate_pass": True,
        "dm_status": "set_mismatch_descriptive",
        "missingness_admissible": False,
    }
    out = sv._finalize_confirmation_verdict(verdict, members, datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert out["audit"]["event"] == "no_peek_rejected"
    assert out["sealed"] is False
    assert out.get("fdr_pass") is not True
    assert out["run_label"] != "confirmed"


def test_enqueue_due_jd_and_sr_registers_each_family(tmp_path, monkeypatch):
    prereg_path = tmp_path / "preregistry.jsonl"
    family_path = tmp_path / "family_registry.jsonl"
    queue_path = tmp_path / "pending.jsonl"
    jd = {
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "symbol": "jd",
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    sr = {
        "prereg_id": "ef908a2214e141abaa2d480ca82b53bb",
        "symbol": "sr",
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 986,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vwap_deviation"]},
    }
    prereg_path.write_text(json.dumps(jd) + "\n" + json.dumps(sr) + "\n", encoding="utf-8")
    monkeypatch.setattr(sv, "PREREGISTRY_PATH", str(prereg_path))
    monkeypatch.setattr(sv, "FAMILY_REGISTRY", str(family_path))
    monkeypatch.setattr(sv, "QUEUE", str(queue_path))
    monkeypatch.setattr(sv, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sv, "_experiment_fp_for", lambda symbol, cov: "ab" * 32)
    # 2026-10-03：数据闸门（D1）桩——确认集数据未越过 confirm_from_ts 时不派发
    # （否则空评估 + no_data 墓碑 + 去重失效 = 每轮重复入队）。本测试关注
    # 「派发 → peek」链路，故显式放行；闸门本身由 test_confirm_bugs_20261003.py 覆盖。
    monkeypatch.setattr(sv, "_confirm_data_ready", lambda s, t: True)
    monkeypatch.setattr(sv, "load_covariate_pool", lambda: {
        "vor": {"family": "momentum"},
        "vwap_deviation": {"family": "momentum"},
    })
    monkeypatch.setattr(sv, "_active_protocol_snapshot", lambda path: {})
    sv._CONFIRM_REDISPATCH.clear()   # 2026-10-04（E2）：同上，进程内节流状态隔离
    n = sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00")
    assert n == 2
    queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert [row["symbol"] for row in queued] == ["jd", "sr"]
    assert [row["run_mode"] for row in queued] == ["confirmation", "confirmation"]
    assert queued[0]["max_points"] == 1199
    assert queued[1]["max_points"] == 986
    members = sv.load_family_members(str(family_path))
    by_symbol = {member["symbol"]: member for member in members}
    assert sorted(by_symbol) == ["jd", "sr"]
    assert by_symbol["jd"]["status"] == "registered"
    assert by_symbol["sr"]["status"] == "registered"
    assert by_symbol["jd"]["family_key"] == sv.family_key_for("jd")
    assert by_symbol["sr"]["family_key"] == sv.family_key_for("sr")
    assert sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00") == 0


def test_stamp_confirmation_verdict_writes_prereg_fields():
    row = {
        "run_mode": "confirmation",
        "prereg_id": "6f944c74e2c94ca5a5b70e64676e518b",
        "n_confirm_required": 1199,
    }
    verdict = {"run_mode": "confirmation", "n": 10, "run_label": None}
    asl._stamp_confirmation_verdict(verdict, row)
    assert verdict["prereg_id"] == row["prereg_id"]
    assert verdict["n_confirm_required"] == 1199
    assert verdict["n_confirm_actual"] == 10
    kept = {"run_mode": "confirmation", "n": 10, "n_confirm_actual": 4}
    asl._stamp_confirmation_verdict(kept, row)
    assert kept["n_confirm_actual"] == 4
    assert kept["prereg_id"] == row["prereg_id"]
    assert kept["n_confirm_required"] == 1199
    no_data = {"status": "no_data", "n": 0, "run_mode": None, "run_label": None, "fdr_pass": False}
    asl._stamp_confirmation_verdict(no_data, row)
    assert no_data["prereg_id"] == row["prereg_id"]
    assert no_data["n_confirm_required"] == 1199
    assert no_data["run_label"] is None
    assert no_data["fdr_pass"] is False


def test_snapshot_prereg_id_blocks_second_enqueue(tmp_path, monkeypatch):
    prereg_path = tmp_path / "preregistry.jsonl"
    family_path = tmp_path / "family_registry.jsonl"
    queue_path = tmp_path / "pending.jsonl"
    prereg_id = "6f944c74e2c94ca5a5b70e64676e518b"
    jd = {
        "prereg_id": prereg_id,
        "symbol": "jd",
        "registered_at": "2026-10-02T00:00:00+00:00",
        "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199,
        "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }
    prereg_path.write_text(json.dumps(jd) + "\n", encoding="utf-8")
    vid = "jd_momentum_" + ("ab" * 32)[:12]
    member = {
        "family_key": sv.family_key_for("jd"),
        "symbol": "jd",
        "variant_id": vid,
        "registered_at": "2026-10-02T00:00:00+00:00",
        "status": "registered",
    }
    family_path.write_text(json.dumps(member) + "\n", encoding="utf-8")
    monkeypatch.setattr(sv, "PREREGISTRY_PATH", str(prereg_path))
    monkeypatch.setattr(sv, "FAMILY_REGISTRY", str(family_path))
    monkeypatch.setattr(sv, "QUEUE", str(queue_path))
    monkeypatch.setattr(sv, "INPROGRESS", str(tmp_path / "inprogress.jsonl"))
    monkeypatch.setattr(sv, "_experiment_fp_for", lambda symbol, cov: "ab" * 32)
    monkeypatch.setattr(sv, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sv, "_active_protocol_snapshot", lambda path: {
        # 2026-10-04（E1）：阻断条件收紧为「满样终态裁决」——fixture 补上
        # status=ok 与满样 n_confirm 戳；未满样 peek 不再永久阻断。
        vid: {"variant_id": vid, "prereg_id": prereg_id, "run_mode": "confirmation",
              "status": "ok", "n_confirm_actual": 1199, "n_confirm_required": 1199},
    })
    sv._CONFIRM_REDISPATCH.clear()
    n = sv._maybe_enqueue_confirmations(str(tmp_path / "decisions.jsonl"), "2026-10-03 12:00:00")
    assert n == 0
    assert not queue_path.exists() or queue_path.read_text(encoding="utf-8").strip() == ""
    raw = [
        json.loads(line)
        for line in family_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(raw) == 1
    assert raw[0]["symbol"] == "jd"
    assert raw[0]["variant_id"] == vid
    assert raw[0]["status"] == "registered"

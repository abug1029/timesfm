"""2026-10-03 五项修复的回归测试（#1/#2/#3/#4/#5）。

每项锁定一个此前确实出错的行为：
#1 family member 落 run_mode（可审计）
#2 confirmation_not_enqueued 节流（6h 内不重复记账）
#3 harvest_proposals 遇停机标志立即中止且不返回半份候选
#4 _has_prior_failure 不认描述性失败
#5 _sector_filter_check 板块失败数只认可确认的 DM
"""
import os
import sys
import json
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import praxist_supervisor as sup  # noqa: E402
import cascade.research_family as rf  # noqa: E402


# ── #1 ────────────────────────────────────────────────────────────
def test_family_member_persists_run_mode_for_audit():
    """member 记录里必须留 run_mode='confirmation'，便于审计「只有确认检验进 family」。

    正确性由 make_member 的 raise 保证；本测试锁的是可追溯性——此前该字段不落盘，
    读family_registry.jsonl 时无法判断成员是不是确认检验。
    """
    import datetime as _dt
    m = rf.make_member("jd|dir|24|abc", "jd", "jd_momentum_abc123abc123",
                       _dt.datetime(2026, 10, 3, tzinfo=_dt.timezone.utc))
    assert m["run_mode"] == "confirmation"
    # 探索期仍必须被拒（原有守卫不回归）
    with pytest.raises(ValueError):
        rf.make_member("k", "jd", "v", _dt.datetime(2026, 10, 3, tzinfo=_dt.timezone.utc),
                       run_mode="exploration")


# ── #4 ────────────────────────────────────────────────────────────
def _snap(rows):
    return {r["variant_id"]: r for r in rows}


def test_has_prior_failure_ignores_descriptive_dm():
    """描述性 DM / 无共同 cutoff 的失败不是检验结论，不能否决新提案。

    修复前：任何 ok+unpassed 行都算失败 → 单轮拒收 1,922 份提案、可用候选 7 轮内 123→47。
    """
    descriptive = _snap([
        {"variant_id": "a", "status": "ok", "gate_pass": False,
         "dm_status": "set_mismatch_descriptive", "symbol": "jd", "cov_override": "vor"},
        {"variant_id": "b", "status": "ok", "gate_pass": False,
         "dm_status": "no_common_cutoff", "symbol": "jd", "cov_override": "vor"},
    ])
    assert sup._has_prior_failure(descriptive, "jd", "vor") is False

    confirmable = _snap([
        {"variant_id": "c", "status": "ok", "gate_pass": False,
         "dm_status": "set_mismatch_ok", "symbol": "jd", "cov_override": "vor"},
    ])
    assert sup._has_prior_failure(confirmable, "jd", "vor") is True
    # 同 symbol 不同协变量也仍算（原有的「同 symbol 或同 cov」语义保留，只是限定为确认失败）
    assert sup._has_prior_failure(confirmable, "jd", "other") is True


# ── #5 ────────────────────────────────────────────────────────────
def test_sector_filter_counts_only_confirmable_failures(monkeypatch):
    """板块失败数只认可确认的 DM；否则确认产出前全板块都会被判失败并触发断路器。"""
    from config.sector_map import SECTORS, sector_of
    sector = "agri"
    members = SECTORS[sector]
    # 该板块所有成员都有一条「描述性失败」：修复前会被判成全失败 → 断路器拦下所有提案
    snap = _snap([
        {"variant_id": f"{s}_x", "status": "ok", "gate_pass": False,
         "dm_status": "set_mismatch_descriptive", "symbol": s, "cov_override": "vor"}
        for s in members
    ])
    blocked, sec, n_failed = sup._sector_filter_check(members[0], snap)
    assert n_failed == 0, f"描述性失败不应计入板块失败数（实际 {n_failed}）"
    assert blocked is False

    # 全部成员都「确认失败」时，仍应拦（断路器语义保留）
    snap2 = _snap([
        {"variant_id": f"{s}_y", "status": "ok", "gate_pass": False,
         "dm_status": "set_mismatch_ok", "symbol": s, "cov_override": "vor"}
        for s in members
    ])
    blocked2, _sec, n2 = sup._sector_filter_check(members[0], snap2)
    assert n2 == len(members)
    assert blocked2 is True


def test_is_confirmable_failure_predicate():
    assert sup._is_confirmable_failure({"gate_pass": False, "dm_status": "ok"}) is True
    assert sup._is_confirmable_failure({"gate_pass": False, "dm_status": "set_mismatch_ok"}) is True
    assert sup._is_confirmable_failure({"gate_pass": False, "dm_status": "set_mismatch_descriptive"}) is False
    assert sup._is_confirmable_failure({"gate_pass": False, "dm_status": "no_common_cutoff"}) is False
    assert sup._is_confirmable_failure({"gate_pass": True, "dm_status": "ok"}) is False


# ── #2 ────────────────────────────────────────────────────────────
def test_confirmation_not_enqueued_is_throttled(tmp_path, monkeypatch):
    """同一prereg 6h 内只记一次账；确认通道要跑 1.2–2.0 年，无节流会写出 30–40 万条/年。"""
    prereg = tmp_path / "preregistry.jsonl"
    reg = [{
        "prereg_id": "p1", "symbol": "jd", "confirm_from_ts": "2026-10-03 00:00:00",
        "n_confirm_required": 1199, "terminal_state": None,
        "cov_fingerprint": {"keys": ["daily_slope", "vor"]},
    }]
    prereg.write_text(json.dumps(reg[0]) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "PREREGISTRY_PATH", str(prereg))
    monkeypatch.setattr(sup, "FAMILY_REGISTRY", str(tmp_path / "family.jsonl"))
    monkeypatch.setattr(sup, "QUEUE", str(tmp_path / "q.jsonl"))
    monkeypatch.setattr(sup, "INPROGRESS", str(tmp_path / "i.jsonl"))
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    # vid 已在队里 → 不再派发，走到 not_enqueued 分支
    monkeypatch.setattr(sup, "rl", type("RL", (), {
        "in_flight_ids": staticmethod(lambda q, i: {"jd_momentum_" + ("ab" * 32)[:12]}),
        "queue_enqueue": staticmethod(lambda *a, **k: 0),
        "load_snapshot": staticmethod(lambda path, only_protocol=None: {}),
    }))
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp-current")
    sup._CONFIRMATION_NOTICE.clear()
    log = str(tmp_path / "decisions.jsonl")

    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:00:00") == 0
    n1 = sum(1 for l in open(log, encoding="utf-8") if "confirmation_not_enqueued" in l)
    # 第二轮：未过 TTL → 不再记账
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:05:00") == 0
    n2 = sum(1 for l in open(log, encoding="utf-8") if "confirmation_not_enqueued" in l)
    assert n2 == n1, f"节流失效：{n1} -> {n2}"
    # 把 TTL 拨到过去 → 重新记账（证明是节流而非永久静音）
    sup._CONFIRMATION_NOTICE["p1"] = time.time() - sup._CONFIRMATION_NOTICE_TTL_S - 1
    assert sup._maybe_enqueue_confirmations(log, "2026-10-03 12:10:00") == 0
    n3 = sum(1 for l in open(log, encoding="utf-8") if "confirmation_not_enqueued" in l)
    assert n3 == n1 + 1, f"TTL 到期后应重新记账：{n1} -> {n3}"


# ── #3 ────────────────────────────────────────────────────────────
def test_harvest_aborts_on_shutdown_flag(monkeypatch, tmp_path):
    """停机标志置位时收割立即中止，且不返回半份候选（避免停机途中入队）。"""
    ev = sup._load_evaluator()
    # 最小可用替身：只提供 VALID_COVARIATES / ALLOWED_SYMBOLS / ARCHIVED_COVARIATES
    monkeypatch.setattr(sup, "_load_evaluator", lambda: type("EV", (), {
        "VALID_COVARIATES": {"vor"}, "ALLOWED_SYMBOLS": {"jd"}, "ARCHIVED_COVARIATES": {},
    })())
    monkeypatch.setattr(sup, "load_covariate_pool", lambda: {"vor": {"family": "momentum"}})
    monkeypatch.setattr(sup, "_experiment_fp_for", lambda s, c: "ab" * 32)
    monkeypatch.setattr(sup, "load_symbol_status", lambda: {})
    monkeypatch.setattr(sup, "_dead_families", lambda snap: set())

    run_dir = tmp_path / "task_FM" / "experiments" / "run_x"
    (run_dir / "results" / "gen_0" / "proposals").mkdir(parents=True)
    for i in range(3):
        (run_dir / "results" / "gen_0" / "proposals" / f"jd_vor{i}.json").write_text(
            json.dumps({"schema": "fm.hypothesis_proposal.v1", "symbol": "jd",
                        "cov_override": "vor", "mechanism": "x" * 60}), encoding="utf-8")

    # Task 5 的座位门要求当前协议的 nocov 基线在位，否则一律 no_current_baseline
    cfg = tmp_path / "task_FM" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "baseline_points_jd_nocov.jsonl").write_text(
        json.dumps({"protocol_fingerprint": "fp-current", "cutoff": "2026-01-01 00:00:00",
                    "dir_ok": True}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sup, "_current_protocol_fingerprint", lambda: "fp-current")

    monkeypatch.setattr(sup, "_SHUTDOWN_REQUESTED", False)
    rows, stats = sup.harvest_proposals(str(tmp_path), {}, set(), set(),
                                        {"vor": {"family": "momentum"}}, top_k=3)
    assert rows, f"对照组：未置标志时应能入队（stats={stats}）"

    sup._SHUTDOWN_REQUESTED = True
    try:
        rows2, stats2 = sup.harvest_proposals(str(tmp_path), {}, set(), set(),
                                              {"vor": {"family": "momentum"}}, top_k=3)
    finally:
        sup._SHUTDOWN_REQUESTED = False
    assert rows2 == [], "停机时不得返回半份候选"
    assert stats2.get("aborted_by_shutdown") is True
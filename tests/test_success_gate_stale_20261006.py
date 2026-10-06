"""数据冻结旁路：上海日历年龄 > STALE_DATA_DAYS 时同窗复跑不再因空 success_delta 被拒。

年龄 == 3（周五收盘到下周一）仍拒收。读不到 kline 不放行。
窗口已平移时不读 kline。新 bar 已到、snapshot 锚仍旧时旁路关闭。
"""
import json
import logging
import os
import sys
from datetime import date

import pytest

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
    config = os.path.join(root, "task_FM", "config")
    os.makedirs(config, exist_ok=True)
    base = os.path.join(config, "baseline_points_%s_nocov.jsonl" % symbol)
    if not os.path.exists(base):
        with open(base, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "protocol_fingerprint": "current-protocol",
                "cutoff": "2026-01-01 00:00:00",
                "dir_ok": True,
            }) + "\n")


def _prop(symbol="m", cov="vor", **over):
    p = {"schema": "fm.hypothesis_proposal.v1", "symbol": symbol,
         "cov_override": cov, "covariate_family": over.pop("family", "volatility"),
         "mechanism": LONGM, "symbol_fit": "该品种适配该协变量",
         "kill_condition": "ev<0", "promote_condition": "gate"}
    p.update(over)
    return p


def _sv(vid, symbol, cov, *, gate_pass=True, eval_end_ts=None, extra=None):
    v = {"schema": "fm.aligned_verdict.v2", "variant_id": vid,
         "symbol": symbol, "cov_override": cov, "status": "ok",
         "gate_pass": gate_pass, "dir_acc": 0.55 if gate_pass else 0.42,
         "n": 350, "decided_at": "2026-10-01T08:00:00",
         "protocol_fingerprint": "current-protocol"}
    if eval_end_ts is not None:
        v["eval_end_ts"] = eval_end_ts
    if extra:
        v.update(extra)
    return v


@pytest.fixture
def tmproot(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "BACKLOG_PATH", str(tmp_path / "backlog.jsonl"))
    status_path = tmp_path / "symbol_status.json"
    status_path.write_text(
        '{"schema": "fm.symbol_status.v1", "symbols": {}}', encoding="utf-8")
    monkeypatch.setattr(S, "SYMBOL_STATUS_PATH", str(status_path))
    monkeypatch.setattr(S, "_experiment_fp_for", lambda s, c: FP_TEST)
    monkeypatch.setattr(S, "_current_protocol_fingerprint", lambda: "current-protocol")
    return str(tmp_path)


def _harvest(root, **kw):
    pool = S.load_covariate_pool()
    return S.harvest_proposals(root, kw.get("snap", {}),
                               kw.get("dead", set()), kw.get("existing", set()),
                               pool, top_k=kw.get("top_k", 5),
                               aligned_max_points=kw.get("max_points", 600))


def test_national_day_gap_fail_open(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    prior = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    _make_run(tmproot, _prop(symbol="rb", cov="vor"))
    rows, stats = _harvest(tmproot, snap={"rb_volatility_prior": prior})
    assert stats["success_gate_states"]["data_stale"] == 1
    assert "no_success_delta" not in stats["success_gate_states"]
    assert "no_success_delta" not in stats["reject_reasons"]
    assert len(rows) == 1


def test_age_three_days_still_rejects(tmproot, monkeypatch):
    # 2026-10-09 周五 → 2026-10-12 周一，日历差正好 3，不放行。
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 12))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-09 14:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-10-09 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert reason == "no_success_delta"
    assert state == "no_success_delta"


def test_age_four_days_opens(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 14))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-10 14:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-10-10 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert reason is None
    assert state == "data_stale"


def test_fresh_bar_same_anchor_still_rejects(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 8))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-10-08 10:00:00")
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert (reason, state) == ("no_success_delta", "no_success_delta")


def test_window_moved_does_not_read_kline(tmproot, monkeypatch):
    def _boom(symbol):
        raise AssertionError("window_moved 不应读 kline")
    monkeypatch.setattr(S, "_kline_1h_max_dt", _boom)
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-23 15:00:00")
    other = _sv("jd_volatility_other", "jd", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor",
        {"m_volatility_prior": prior, "jd_volatility_other": other},
        tmproot, cache={})
    assert (reason, state) == (None, "window_moved")


def test_unreadable_kline_stays_closed(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: None)
    prior = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    reason, state = S._success_delta_gate(
        _prop(), "m", "vor", {"m_volatility_prior": prior}, tmproot, cache={})
    assert (reason, state) == ("no_success_delta", "no_success_delta")


def test_stale_is_per_symbol(tmproot, monkeypatch):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))

    def _max(symbol):
        return "2026-09-30 14:00:00" if symbol == "rb" else "2026-10-06 14:00:00"

    monkeypatch.setattr(S, "_kline_1h_max_dt", _max)
    rb = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
             eval_end_ts="2026-09-30 15:00:00")
    m = _sv("m_volatility_prior", "m", "vor", gate_pass=True,
            eval_end_ts="2026-09-30 15:00:00")
    snap = {"rb_volatility_prior": rb, "m_volatility_prior": m}
    cache = {}
    assert S._success_delta_gate(
        _prop(symbol="rb"), "rb", "vor", snap, tmproot, cache)[1] == "data_stale"
    assert S._success_delta_gate(
        _prop(), "m", "vor", snap, tmproot, cache)[1] == "no_success_delta"


def test_stale_warning_once_per_symbol(tmproot, monkeypatch, caplog):
    monkeypatch.setattr(S, "_today_shanghai", lambda: date(2026, 10, 6))
    monkeypatch.setattr(S, "_kline_1h_max_dt", lambda symbol: "2026-09-30 14:00:00")
    prior = _sv("rb_volatility_prior", "rb", "vor", gate_pass=True,
                eval_end_ts="2026-09-30 15:00:00")
    snap = {"rb_volatility_prior": prior}
    cache = {}
    with caplog.at_level(logging.WARNING):
        S._success_delta_gate(_prop(symbol="rb"), "rb", "vor", snap, tmproot, cache)
        S._success_delta_gate(_prop(symbol="rb"), "rb", "vor", snap, tmproot, cache)
    warns = [r for r in caplog.records if "data_stale" in r.getMessage()]
    assert len(warns) == 1
    assert "rb" in warns[0].getMessage()
    assert "2026-09-30" in warns[0].getMessage()
    assert "已 6 天" in warns[0].getMessage()


def test_today_shanghai_falls_back_to_utc_when_zoneinfo_fails(monkeypatch):
    """ZoneInfo 失败时回退 UTC 日历日。防御路径，不是预期失败。"""
    import zoneinfo
    from datetime import datetime, timezone

    def _boom(key):
        raise zoneinfo.ZoneInfoNotFoundError(str(key))

    monkeypatch.setattr(zoneinfo, "ZoneInfo", _boom)
    assert S._today_shanghai() == datetime.now(timezone.utc).date()

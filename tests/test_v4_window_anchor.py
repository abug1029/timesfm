"""v4 收口 2.8 — 窗口锚语义 + checkpoint 身份测试（发现 B）。

配对不变量（计划 2.8）：同一锚下，数据末端 +1 bar 的两次运行，
评估 cutoff 集合必须逐点相同 —— 评估窗口是锚的纯函数，数据增长不再平移窗口。

数据**短缺**（锚时刻之后缺 bar）不在本不变量内：窗口尾部收缩、短缺点全量
重算（fail-visible），与「增长不变」是两种语义。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

import monthly_backtest as mb  # noqa: E402
import aligned_slow_loop as asl  # noqa: E402
from task_FM.evaluations.fm_eval import evaluator as ev  # noqa: E402


# ── v4 指纹：窗口锚语义入指纹 ────────────────────────────────


def test_fingerprint_changes_when_window_anchor_changes():
    base = ev.compute_protocol_fingerprint()
    assert ev.PROTOCOL_FINGERPRINT_VERSION == "protocol_v4"
    assert base != ev.compute_protocol_fingerprint(window_anchor="legacy_sliding_v3")


def test_fingerprint_deterministic_v4():
    assert ev.compute_protocol_fingerprint() == ev.compute_protocol_fingerprint()


# ── checkpoint 身份：指纹门 + (symbol, cutoff) 主键 + 锚还原 ──


def _ckpt_line(cutoff, *, fp="FPNOW", anchor="2026-09-30 00:00:00",
               symbol="ss", error=None):
    rec = {"symbol": symbol, "idx": 1, "cutoff": cutoff,
           "eval_end_ts": anchor, "protocol_fingerprint": fp,
           "ablation_mode": "full"}
    if error is None:
        rec.update({"delta_pred": 1.0, "delta_real": 1.0, "dir_ok": True,
                    "base": 100.0})
    else:
        rec["error"] = error
    return rec


def test_load_checkpoint_state_fp_gate(tmp_path):
    fp_now = ev.compute_protocol_fingerprint()
    cp = tmp_path / "v.jsonl"
    lines = [
        _ckpt_line("2026-09-29 22:00:00", fp=fp_now),                     # 复用
        _ckpt_line("2026-09-29 23:00:00", fp="protocol_v3_legacy_hash"),  # 丢弃
        _ckpt_line("2026-09-30 00:00:00", fp=fp_now, error="boom"),       # 完成但不含经济字段
        _ckpt_line("2026-09-30 01:00:00", fp=None),                       # 丢弃(无指纹)
    ]
    cp.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    completed, resumed, anchor, legacy = asl._load_checkpoint_state(str(cp), fp_now)
    assert len(completed) == 2
    assert ("ss", "2026-09-29 22:00:00") in completed
    assert ("ss", "2026-09-30 00:00:00") in completed
    assert ("ss", "2026-09-29 22:00:00") in resumed
    assert len(resumed) == 1
    assert anchor == "2026-09-30 00:00:00"
    assert legacy == 2


def test_load_checkpoint_state_missing_file(tmp_path):
    completed, resumed, anchor, legacy = asl._load_checkpoint_state(
        str(tmp_path / "none.jsonl"), "FP")
    assert completed == set() and resumed == {} and anchor is None and legacy == 0


# ── 配对不变量：同锚 + 数据 +1 bar → cutoff 集合不变 ─────────


class _FakeStore:
    def __init__(self, h1, daily):
        self._h1, self._daily = h1, daily

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_main_contract_1h(self, limit=1023):
        return self._h1

    def get_main_continuous(self, start_date=None, end_date=None, limit=None):
        return self._daily


def _hourly_df(n):
    dt = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "dt": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "close_price": [100.0 + i for i in range(n)],
        "contract_code": ["SS_MAIN"] * n,
    })


def _daily_df():
    days = pd.date_range("2025-01-01", periods=150, freq="D")
    return pd.DataFrame({"dt": days.strftime("%Y-%m-%d")})


def _run_all_resumed(monkeypatch, h1, cutoffs, anchor):
    """全部点已 completed → 零模型调用; 返回 run_symbol_backtest 的 data dict。"""
    monkeypatch.setattr(mb, "DataStore", lambda symbol: _FakeStore(h1, _daily_df()))
    monkeypatch.setattr(mb, "CONTEXT_BARS", 20)
    monkeypatch.setattr(mb, "CONTEXT_DAYS", 10)
    monkeypatch.setattr(mb, "HORIZON", 4)
    monkeypatch.setattr(mb, "HORIZON_DAYS", 2)
    monkeypatch.setattr(mb, "STEP", 5)
    monkeypatch.setattr(mb, "EVAL_WINDOW_BARS", 40)
    completed, resumed = set(), {}
    for c in cutoffs:
        rec = {"symbol": "ss", "idx": 0, "cutoff": c, "base": 100.0,
               "pred_end": 101.0, "real_end": 101.0, "delta_pred": 1.0,
               "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
               "mae": 1.0, "mape": 1.0, "mae_h1": 1.0, "mae_h2": 1.0,
               "coverage": 4, "pnl": 1.0, "real_range": 2.0,
               "roll_in_horizon": False, "endpoint_mape": 1.0,
               "endpoint_bias_pct": 0.0, "path_corr": None,
               "covariates_used": False, "context_hash": "a" * 16,
               "ablation_mode": "full"}
        completed.add(("ss", c))
        resumed[("ss", c)] = rec
    kwargs = dict(cov_override="none", completed=completed,
                  resumed_points=resumed)
    if anchor is not None:
        kwargs["eval_end_ts"] = anchor
    data = mb.run_symbol_backtest("ss", None, None, **kwargs)
    assert data is not None
    return data


def _expected_cutoffs(n=80, start=40, horizon=4, step=5):
    h1 = _hourly_df(n)
    out = []
    for idx in range(start, n - horizon + 1, step):
        bar = pd.Timestamp(h1["dt"].iloc[idx])
        out.append((bar + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))
    return out


def test_anchor_pins_window_against_data_growth(monkeypatch):
    """配对不变量：同锚两次运行, 第二次数据末端 +1 bar → cutoff 集合逐点相同。"""
    cutoffs = _expected_cutoffs()  # 8 点: idx 40..75 step 5
    assert len(cutoffs) == 8
    anchor = "2026-01-04 08:00:00"  # 80 根 bar 的末根收盘 (= dt[79]+1h)
    run_a = _run_all_resumed(monkeypatch, _hourly_df(80), cutoffs, anchor)
    assert run_a["eval_end_ts"] == anchor
    got_a = [p["cutoff"] for p in run_a["points"]]
    assert got_a == cutoffs
    # 数据 +1 bar: v3 语义下窗口会平移 1 bar; v4 锚定 → 截断 → 集合不变
    run_b = _run_all_resumed(monkeypatch, _hourly_df(81), cutoffs, anchor)
    got_b = [p["cutoff"] for p in run_b["points"]]
    assert got_b == cutoffs, "同锚下数据增长不得平移评估窗口"


def test_anchor_reported_when_not_given(monkeypatch):
    """未传锚 → 取当前数据末端为锚（向后兼容），并落进返回值供上层持久化。"""
    cutoffs = _expected_cutoffs()
    run = _run_all_resumed(monkeypatch, _hourly_df(80), cutoffs, anchor=None)
    assert run["eval_end_ts"] == "2026-01-04 08:00:00"

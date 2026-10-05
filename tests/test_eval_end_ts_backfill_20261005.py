"""T2d (2026-10-05): 裁决行 eval_end_ts 的 checkpoint 兜底（首跑）。

背景（spec 2026-10-05 §6.6 条件 6 / 实施计划 P1）：
首跑（无当前协议 checkpoint 历史）锚还原为 None → 回测侧把解析出的窗口锚
（数据末端）逐行落 checkpoint（mb `_anchor`），但裁决行 `v["eval_end_ts"]`
写的是还原前的 None（asl :311）→ 行不自含：6.6 条件 6 fail-closed，
行的直读者看不到评估窗右边界。

T2d：裁决行落章时，锚还原为 None 的，回读本 variant checkpoint 末行当前
协议锚回填。字节级损坏照 T2c 文件级异常面（OSError/ValueError）→ 不可读
前缀行保留、全文件不可读 → None（行 fail-closed 不猜）。

设计语义钉死（不得被过度实现破坏）：
- 确认未满**有历史**（锚已还原、`_eval_end_ts_for_run` 压 None）不回填
  ——右边界跟数据末端是确认窗口自身语义，不是首跑。
- 空 checkpoint（本轮未写行）→ 无锚可回填 → None。
- 旧协议/无指纹行不参与（指纹门与 `_load_checkpoint_state` 同一）。

不调用模型，不读 TimesFM 权重。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

import monthly_backtest as mb  # noqa: E402
import aligned_slow_loop as asl  # noqa: E402


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


class _Sentinel:
    def __init__(self, name):
        self.name = name


def _summary_factory():
    def _summary(s, cand, **kwargs):
        return {
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
            "fdr_pass": None,
            "run_mode": kwargs.get("run_mode", "exploration"),
            "run_label": None,
        }

    return _summary


def _bt_writing(anchor, *, n_rows=2, torn_tail=False, write_rows=True):
    """假 run_symbol_backtest：按 mb 契约把锚逐行写进 checkpoint
    （rec 携带 eval_end_ts/protocol_fingerprint）；可选拼接非 UTF-8 撕裂
    尾巴（崩溃场景）。返回值携带 eval_end_ts（mb 同款）。"""

    def _bt(*args, **kwargs):
        fp = kwargs["checkpoint_fp"]
        pf = kwargs["protocol_fingerprint"]
        if write_rows:
            for i in range(n_rows):
                rec = {"symbol": "m", "idx": i,
                       "cutoff": "2026-10-05 1%d:00:00" % i,
                       "eval_end_ts": anchor,
                       "protocol_fingerprint": pf,
                       "ablation_mode": "full",
                       "delta_pred": 1.0, "delta_real": 1.0, "dir_ok": True,
                       "base": 100.0}
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fp.flush()
        if torn_tail:
            with open(fp.name, "ab") as raw:
                raw.write(b"\xff\xfe torn tail\n")
        return {"contract": "M", "points": [{"dir_ok": True}],
                "eval_end_ts": anchor}

    return _bt


def _run(tmp_path, monkeypatch, bt, **row_over):
    monkeypatch.setattr(mb, "run_symbol_backtest", bt)
    monkeypatch.setattr(mb, "summarize", lambda data: {"n": 1, "dir_acc": 0.5})
    monkeypatch.setattr(asl, "_get_models",
                        lambda: (_Sentinel("daily"), _Sentinel("hourly")))
    monkeypatch.setattr(asl, "_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    monkeypatch.setattr(asl, "build_summary", _summary_factory())
    return asl.run_aligned_candidate(
        _row(**row_over),
        daily_cache_dir=str(tmp_path / "dc"),
        checkpoint_dir=str(tmp_path / "cp"),
        registry_path=str(tmp_path / "verdicts.jsonl"),
    )


# ── 单元：_checkpoint_last_anchor ────────────────────────────


def test_checkpoint_last_anchor_unit(tmp_path):
    cp = tmp_path / "cp.jsonl"
    # 文件不存在 → None
    assert asl._checkpoint_last_anchor(str(cp), "FP") is None
    # 指纹门：旧协议行不参与，末行当前协议锚胜出
    lines = [
        {"eval_end_ts": "2026-09-01 11:00:00", "protocol_fingerprint": "protocol_v3_old"},
        {"eval_end_ts": "2026-10-05 14:00:00", "protocol_fingerprint": "FP"},
        {"eval_end_ts": "2026-10-05 15:00:00", "protocol_fingerprint": "FP"},
        {"eval_end_ts": "2026-10-06 99:00:00", "protocol_fingerprint": "other"},
    ]
    cp.write_text("\n".join(json.dumps(x) for x in lines) + "\n",
                  encoding="utf-8")
    assert asl._checkpoint_last_anchor(str(cp), "FP") == "2026-10-05 15:00:00"
    # 无当前协议行 → None
    assert asl._checkpoint_last_anchor(str(cp), "FP2") is None
    # 空文件 → None
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert asl._checkpoint_last_anchor(str(empty), "FP") is None


# ── 集成：裁决行落章兜底 ─────────────────────────────────────


def test_first_run_backfills_verdict_anchor_from_checkpoint_tail(tmp_path, monkeypatch):
    """首跑（无历史）→ 行回填本轮 checkpoint 末行锚（= 本轮数据末端）。"""
    v = _run(tmp_path, monkeypatch, _bt_writing("2026-10-05 15:00:00"))
    assert v["status"] == "ok"
    assert v["eval_end_ts"] == "2026-10-05 15:00:00"


def test_backfill_ignores_legacy_rows_takes_current_protocol_tail(tmp_path, monkeypatch):
    """checkpoint 头部有旧协议行（无当前协议历史 → 仍算首跑）：回填只认
    当前协议末行锚，不得被 legacy 行污染。"""
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    legacy = {"symbol": "m", "idx": 0, "cutoff": "2026-09-01 10:00:00",
              "eval_end_ts": "2026-09-01 11:00:00",
              "protocol_fingerprint": "protocol_v3_legacy_hash",
              "ablation_mode": "full"}
    (cp_dir / "m_rsi_state.jsonl").write_text(
        json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")
    v = _run(tmp_path, monkeypatch, _bt_writing("2026-10-05 15:00:00"))
    assert v["eval_end_ts"] == "2026-10-05 15:00:00"


def test_backfill_fails_closed_on_torn_checkpoint(tmp_path, monkeypatch):
    """撕裂 checkpoint（非 UTF-8 尾巴）：小文件单块解码 → 全文件不可读
    → 保持 None（T2c 语义，fail-closed 不猜）。"""
    v = _run(tmp_path, monkeypatch,
             _bt_writing("2026-10-05 15:00:00", torn_tail=True))
    assert v["eval_end_ts"] is None


def test_backfill_none_when_run_wrote_no_rows(tmp_path, monkeypatch):
    """本轮未写 checkpoint 行 → 无锚可回填 → None。"""
    v = _run(tmp_path, monkeypatch,
             _bt_writing("2026-10-05 15:00:00", write_rows=False))
    assert v["eval_end_ts"] is None


def test_confirmation_unfull_with_history_keeps_none(tmp_path, monkeypatch):
    """确认未满**有历史**：锚已还原、`_eval_end_ts_for_run` 压 None——
    右边界跟数据末端是确认窗口自身语义，不是首跑，不回填。"""
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    hist = {"symbol": "m", "idx": 0, "cutoff": "2026-09-30 14:00:00",
            "eval_end_ts": "2026-09-30 15:00:00",
            "protocol_fingerprint": asl.compute_protocol_fingerprint(),
            "ablation_mode": "full",
            "delta_pred": 1.0, "delta_real": 1.0}
    (cp_dir / "m_rsi_state__prereg_abcdef01.jsonl").write_text(
        json.dumps(hist, ensure_ascii=False) + "\n", encoding="utf-8")
    v = _run(tmp_path, monkeypatch, _bt_writing("2026-10-05 16:00:00"),
             run_mode="confirmation",
             prereg_id="abcdef0123456789",
             confirm_from_ts="2026-10-01 00:00:00",
             n_confirm_required=30)
    assert v["eval_end_ts"] is None

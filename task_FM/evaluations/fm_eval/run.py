#!/usr/bin/env python3
"""PRAXIST 评估入口 (平台经 task_entrypoints 调度) v23 2026-09-16

用法: run.py --output-dir <dir> --candidate <candidate.json>
候选: {symbol, cov_override, max_points[, stage=diagnostic|aligned]}
stage=diagnostic: max_points 1..6 (快筛, 结构性不过硬门)
stage=aligned:    max_points 350..600 (近全量 walk-forward, 可过硬门)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))
sys.path.insert(0, HERE)

from evaluator import (build_summary, validate_candidate, load_baseline_points,  # noqa: E402
                       attach_gated_metrics)


_HELD_EVAL_SLOT = None


def _ensure_eval_slot():
    """Belt-and-suspenders flock: skip if parent protected_pids hook already holds."""
    global _HELD_EVAL_SLOT
    if os.environ.get("FM_EVAL_SLOT_HELD", "").strip() in ("1", "true", "yes"):
        return None
    import mem_guard as mg  # noqa: WPS433
    _HELD_EVAL_SLOT = mg.acquire_slot(apply_limit=False, block=False)
    mg.log_capacity_action(
        f"run.py: acquired slot={_HELD_EVAL_SLOT.slot} (no FM_EVAL_SLOT_HELD)"
    )
    return _HELD_EVAL_SLOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--candidate", required=True)
    a = ap.parse_args()
    _ensure_eval_slot()
    os.makedirs(a.output_dir, exist_ok=True)
    with open(a.candidate, encoding="utf-8") as f:
        cand = json.load(f)
    ok, why = validate_candidate(cand)
    if not ok:
        out = {"status": "invalid_candidate", "reason": why,
               "variant_name": _variant_name(cand)}
        _write(out, a.output_dir)
        sys.exit(2)
    result = do_evaluate(cand)
    _write(result["summary"], a.output_dir)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


def _variant_name(cand):
    if not isinstance(cand, dict):
        return "unknown"
    return "{}_{}_{}_p{}".format(
        cand.get("symbol", "?"), cand.get("cov_override", "?"),
        cand.get("stage", "diagnostic"), cand.get("max_points", "?"),
    )


def _write(obj, out_dir):
    with open(os.path.join(out_dir, "evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def do_evaluate(cand):
    from monthly_backtest import run_symbol_backtest, DailyModel, HourlyModel, summarize
    d = DailyModel()
    h = HourlyModel()
    stage = cand.get("stage", "diagnostic")
    data = run_symbol_backtest(
        cand["symbol"].upper(), d, h,
        cov_override=cand["cov_override"],
        max_points=cand.get("max_points", 6 if stage == "diagnostic" else 400),
    )
    if data is None:
        return {"summary": {"status": "no_data", "usage_unknown": True,
                            "variant_name": _variant_name(cand), "stage": stage}}
    s = summarize(data)
    if s is None:
        return {"summary": {"status": "no_scoreable_points", "usage_unknown": True,
                            "variant_name": _variant_name(cand), "stage": "aligned"}}
    s = dict(s)
    # v23: new metric keys (PF/EV/MaxDD retired)
    s.setdefault("dir_acc", s.get("DirAcc", 0.5))
    s.setdefault("n_eff", s.get("n", 0))
    s.setdefault("endpoint_mape", 0.0)
    s.setdefault("endpoint_bias_pct", 0.0)
    s.setdefault("path_corr", 0.0)
    s.setdefault("weighted_dir_acc", s.get("dir_acc", 0.5))
    s.setdefault("mae", 0.0)
    s.setdefault("mape", 0.0)
    s.setdefault("decay", 1.0)

    # gated 协变量: 注入 Active Mask 统计 (spec §5 Active DirAcc; 非 gated 路径零改动)
    attach_gated_metrics(s, cand["cov_override"], data["points"])

    # Load baseline for DM test (aligned stage only)
    baseline_points = None
    baseline_dir_acc = None
    if stage == "aligned":
        baseline_points = load_baseline_points(cand["symbol"])
        if baseline_points:
            ok_count = sum(1 for pt in baseline_points if pt.get("dir_ok"))
            baseline_dir_acc = ok_count / len(baseline_points) if baseline_points else None

    return {"summary": build_summary(
        s, cand,
        baseline_points=baseline_points,
        baseline_dir_acc=baseline_dir_acc,
    )}


if __name__ == "__main__":
    main()

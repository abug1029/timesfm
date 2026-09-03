#!/usr/bin/env python3
"""PRAXIST 评估入口 (平台经 task_entrypoints 调度)

用法: run.py --output-dir <dir> --candidate <candidate.json>
候选: {symbol, cov_override, max_points[, stage=diagnostic|aligned]}
stage=diagnostic: max_points 1..6 (快筛, 结构性不过硬门)
stage=aligned:    max_points 350..500 (近全量 walk-forward, 可过硬门)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(FM_ROOT, "scripts"))
sys.path.insert(0, HERE)

from evaluator import build_summary, validate_candidate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--candidate", required=True)
    a = ap.parse_args()
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
    s.setdefault("PF", s.get("profit_factor", 0.0))
    s.setdefault("EV", s.get("ev", 0.0))
    s.setdefault("MaxDD", s.get("max_dd", 0.0))
    s.setdefault("DirAcc", s.get("dir_acc", 0.5))
    return {"summary": build_summary(s, cand)}


if __name__ == "__main__":
    main()

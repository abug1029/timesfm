#!/usr/bin/env python3
"""
从 by_symbol 产物重建 Neutral A/B 报告。

不重新跑 TimesFM。评分/门禁/写出全部委托 cascade.neutral_ab_report。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.neutral_ab_report import (  # noqa: E402
    load_results_from_by_symbol,
    score_and_write,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Neutral A/B report from by_symbol")
    parser.add_argument(
        "--out-dir",
        default="reports/phase1/full_universe_neutral",
    )
    parser.add_argument(
        "--eligibility",
        default="reports/phase1/universe_eligibility.json",
        help="若存在则按 l1_symbols 顺序；否则扫描 by_symbol 目录",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="默认 <out-dir>/summary.md",
    )
    parser.add_argument(
        "--oos-start", default="2026-04-01",
    )
    parser.add_argument(
        "--oos-end", default="2026-07-31",
    )
    parser.add_argument("--thr", type=float, default=0.55)
    parser.add_argument("--step", type=int, default=24)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    by_dir = out_dir / "by_symbol"
    if not by_dir.is_dir():
        raise SystemExit(f"missing by_symbol dir: {by_dir}")

    symbols = None
    elig_path = Path(args.eligibility)
    if elig_path.exists():
        elig = json.loads(elig_path.read_text(encoding="utf-8"))
        symbols = [s.lower() for s in elig.get("l1_symbols") or []]
        if not symbols:
            symbols = None

    symbols, results = load_results_from_by_symbol(by_dir, symbols)
    report_path = Path(args.report) if args.report else out_dir / "summary.md"

    score = score_and_write(
        symbols,
        results,
        report_path,
        meta={
            "thr": args.thr,
            "oos_start": args.oos_start,
            "oos_end": args.oos_end,
            "step": args.step,
            "by_symbol_dir": str(by_dir).replace("\\", "/"),
            "source": "rebuild_from_by_symbol",
        },
    )
    print(f"Report: {report_path}")
    print(f"JSON:   {report_path.with_suffix('.json')}")
    print(f"VERDICT: {score.engineering_verdict}")
    print(f"GATE:    {score.production_gate}")
    print(f"R1:      {score.domain['r1_trigger']} "
          f"(extreme={len(score.domain['extreme_strict_non_black'])})")
    c = score.counts
    print(
        f"HELPS={c['HELPS']} MIXED={c['MIXED']} HURTS={c['HURTS']} "
        f"NEUTRAL={c['NEUTRAL']}"
    )
    print(
        f"ΔEV={c['delta_EV']:+.3f} ΔΣPnL={c['delta_sum_NetPnL']:+.1f} "
        f"ΔmeanDD={c['delta_MaxDD']:+.4f}"
    )


if __name__ == "__main__":
    main()

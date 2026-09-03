#!/usr/bin/env python3
"""Phase S helper: live ledger health stats + weak-cov candidates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cascade.live_ledger import LiveLedger, export_candidates, health_stats  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Live covariate health from live_ledger")
    ap.add_argument("--min-vol", type=float, default=None)
    ap.add_argument("--max-diracc", type=float, default=0.50)
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    led = LiveLedger(args.db) if args.db else LiveLedger()
    stats = health_stats(led, min_vol_prob=args.min_vol, source=None)
    cands = export_candidates(led, max_diracc=args.max_diracc, min_n=args.min_n)

    print("# live_cov_health")
    print(f"stats_rows={len(stats)} candidates={len(cands)}")
    print("| symbol | cov | n | diracc_t24 | mae_t24% | mean_vol |")
    print("|--------|-----|--:|----------:|---------:|---------:|")
    for r in stats[:50]:
        da = r.get("diracc_t24")
        da_s = f"{float(da):.2%}" if da is not None else "—"
        mae = r.get("mae_t24_pct")
        mae_s = f"{float(mae):.2f}" if mae is not None else "—"
        mv = r.get("mean_vol_prob")
        mv_s = f"{float(mv):.2f}" if mv is not None else "—"
        print(
            f"| {r.get('symbol')} | {r.get('cov_used')} | {r.get('n')} | "
            f"{da_s} | {mae_s} | {mv_s} |"
        )
    if cands:
        print("\n## candidates (weak live diracc)")
        for c in cands:
            print(
                f"- {c['symbol']} cov={c['cov_used']} n={c['n']} "
                f"diracc={c['diracc_t24']:.2%}"
            )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {"stats": stats, "candidates": cands},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Backfill live_ledger actuals from per-symbol kline_1h (market DBs)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cascade.live_ledger import LiveLedger, backfill_run_from_1h  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill live_ledger from 1H market data")
    ap.add_argument("--uuid", help="single run uuid")
    ap.add_argument("--symbol", help="backfill all unfilled for symbol")
    ap.add_argument("--all-unfilled", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--db", default=None, help="ledger path override")
    args = ap.parse_args()

    led = LiveLedger(args.db) if args.db else LiveLedger()
    targets: list[str] = []
    if args.uuid:
        targets = [args.uuid]
    else:
        rows = led.query(
            symbol=args.symbol,
            unfilled_only=True,
            limit=args.limit,
        )
        if not args.all_unfilled and not args.symbol:
            print("Specify --uuid, --symbol, or --all-unfilled")
            return 2
        if args.all_unfilled or args.symbol:
            targets = [r["uuid"] for r in rows]

    n_ok = n_fill = 0
    for uid in targets:
        r = backfill_run_from_1h(led, uid)
        n_ok += 1 if r.get("ok") else 0
        n_fill += 1 if r.get("filled") else 0
        print(f"{uid[:8]}… ok={r.get('ok')} filled={r.get('filled')} {r.get('reason', '')}")

    print(f"done attempted={len(targets)} ok={n_ok} filled={n_fill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

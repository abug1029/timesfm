#!/usr/bin/env python3
"""Paper-trading loop: ledger status / backfill / live health.

Does not run TimesFM. Does not change SCHEMES.
See docs/paper_trading.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cascade.live_ledger import (  # noqa: E402
    LiveLedger,
    backfill_run_from_1h,
    export_candidates,
    health_stats,
)
from config.prediction_scheme import list_by_stars  # noqa: E402

# G005-E 可辩护弱正（n 较足）。观察仓经济尚可但 n<350。
CORE = ("ss", "sr", "m", "jd")
WATCH = ("cj", "lh")
# --three-star 还会带上边界 EG/RB，纸面主盘不要用那条 CLI。


def _led(db: str | None) -> LiveLedger:
    return LiveLedger(db) if db else LiveLedger()


def cmd_next() -> int:
    core = " ".join(CORE)
    watch = " ".join(WATCH)
    print("# 下一步（盘中记一笔，不要用 --three-star）")
    print(f"python scripts/copilot.py {core}")
    print(f"# 观察仓（可选）: python scripts/copilot.py {watch} --no-refresh")
    print("python scripts/paper_loop.py backfill")
    print("python scripts/paper_loop.py health")
    return 0


def cmd_status(led: LiveLedger) -> int:
    rows = led.query(limit=5000)
    filled = [r for r in rows if r.get("actual_t24") is not None]
    unfilled = [r for r in rows if r.get("actual_t24") is None]
    by: dict[str, dict] = {}
    for r in rows:
        k = f"{r.get('symbol')}/{r.get('source')}"
        slot = by.setdefault(k, {"n": 0, "filled": 0, "last_asof": ""})
        slot["n"] += 1
        if r.get("actual_t24") is not None:
            slot["filled"] += 1
        asof = str(r.get("asof_ts") or "")
        if asof > slot["last_asof"]:
            slot["last_asof"] = asof

    two_star = list_by_stars(2)
    print("# paper_loop status")
    print(f"ledger={led.path}")
    print(f"rows={len(rows)} filled_t24={len(filled)} unfilled={len(unfilled)}")
    print(f"core={','.join(CORE)}  watch={','.join(WATCH)}")
    print(f"list_by_stars(2)={','.join(two_star)}  # 含边界 EG/RB，主盘勿全跑")
    print("| symbol/source | n | filled | last_asof |")
    print("|---------------|--:|-------:|-----------|")
    for k in sorted(by):
        s = by[k]
        print(f"| {k} | {s['n']} | {s['filled']} | {s['last_asof']} |")
    if unfilled:
        print(f"\n# {len(unfilled)} 笔待回填 → python scripts/paper_loop.py backfill")
    else:
        print("\n# 无待回填。盘中: python scripts/paper_loop.py next")
    return 0


def cmd_backfill(led: LiveLedger, *, symbol: str | None, limit: int) -> int:
    rows = led.query(symbol=symbol, unfilled_only=True, limit=limit)
    n_ok = n_fill = 0
    for r in rows:
        out = backfill_run_from_1h(led, r["uuid"])
        n_ok += 1 if out.get("ok") else 0
        n_fill += 1 if out.get("filled") else 0
        reason = out.get("reason") or ""
        print(
            f"{r['uuid'][:8]}… {r['symbol']} asof={r['asof_ts']} "
            f"ok={out.get('ok')} filled={out.get('filled')} {reason}"
        )
    print(f"done attempted={len(rows)} ok={n_ok} filled={n_fill}")
    return 0


def cmd_health(
    led: LiveLedger,
    *,
    max_diracc: float,
    min_n: int,
    json_out: Path | None,
    source: str | None,
) -> int:
    # 纸面只看 copilot 行。cascade 的 asof 是墙钟，会污染 DirAcc。
    stats = health_stats(led, source=source)
    cands = [
        c
        for c in export_candidates(led, max_diracc=max_diracc, min_n=min_n)
        if source is None
        or any(
            s.get("symbol") == c["symbol"] and s.get("cov_used") == c["cov_used"]
            for s in stats
        )
    ]
    print("# live_cov_health  (dir_correct = sign(pred_t24-base)，非加权1H)")
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
        print("\n## candidates (live diracc 弱，只报警，不改 SCHEMES)")
        for c in cands:
            print(
                f"- {c['symbol']} cov={c['cov_used']} n={c['n']} "
                f"diracc={c['diracc_t24']:.2%}"
            )
    else:
        print("\n# 无弱候选（n 不够或 live DirAcc 未跌破门槛）")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {"stats": stats, "candidates": cands, "core": list(CORE), "watch": list(WATCH)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {json_out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Copilot paper loop: status / backfill / health")
    ap.add_argument(
        "cmd",
        nargs="?",
        default="status",
        choices=("status", "backfill", "health", "next"),
    )
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--max-diracc", type=float, default=0.50)
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument(
        "--source",
        default="copilot",
        help="health 默认只看 copilot；传 all 看全部来源",
    )
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    if args.cmd == "next":
        return cmd_next()
    led = _led(args.db)
    if args.cmd == "status":
        return cmd_status(led)
    if args.cmd == "backfill":
        return cmd_backfill(led, symbol=args.symbol, limit=args.limit)
    src = None if args.source in ("all", "*", "") else args.source
    return cmd_health(
        led,
        max_diracc=args.max_diracc,
        min_n=args.min_n,
        json_out=args.json_out,
        source=src,
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
全品种准入扫描 (S0)

输出合格 / 跳过清单，供 fullchain --universe 使用。

用法:
  python scripts/universe_eligibility.py
  python scripts/universe_eligibility.py --out reports/phase1/universe_eligibility.json
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from config.backtest_config import (
    CONTEXT_BARS, CONTEXT_DAYS, HORIZON, HORIZON_DAYS, STEP, SYMBOLS,
)
from config.prediction_scheme import SCHEMES, list_solidified, get_scheme
from config.sector_map import sector_of
from data.data_store import DataStore

OOS_START = "2026-04-01"
OOS_END = "2026-07-31"
MIN_OOS_POINTS = 8


def list_db_symbols() -> list[str]:
    db_dir = project_root / "db"
    return sorted(
        p.stem.replace("futures_", "")
        for p in db_dir.glob("futures_*.db")
    )


def count_oos_eval_points(symbol: str, oos_start: str, oos_end: str, step: int) -> dict:
    """粗算 OOS 窗内评估点数（与 fullchain 过滤对齐的简化版）。"""
    with DataStore(symbol) as store:
        all_1h = store.get_main_contract_1h(limit=99999)
        daily_df = store.get_main_continuous(limit=99999)

    if all_1h is None or all_1h.empty:
        return {"n_1h": 0, "n_daily": 0, "n_oos": 0, "last_1h": None}

    all_1h = all_1h.copy()
    all_1h["dt"] = pd.to_datetime(all_1h["dt"])
    n_1h = len(all_1h)
    n_daily = 0 if daily_df is None or daily_df.empty else len(daily_df)
    last_1h = str(all_1h["dt"].iloc[-1])

    if n_1h < CONTEXT_BARS + HORIZON:
        return {"n_1h": n_1h, "n_daily": n_daily, "n_oos": 0, "last_1h": last_1h}

    oos_start_ts = pd.Timestamp(oos_start)
    oos_end_ts = pd.Timestamp(oos_end) + pd.Timedelta(hours=23, minutes=59)
    total = n_1h
    eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, step))

    if n_daily > 0:
        import bisect
        daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
        min_daily_required = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
        eval_indices = [
            idx for idx in eval_indices
            if bisect.bisect_right(daily_dates, str(all_1h["dt"].iloc[idx])[:10])
            >= min_daily_required
        ]

    eval_indices = [
        idx for idx in eval_indices
        if oos_start_ts <= all_1h["dt"].iloc[idx] <= oos_end_ts
    ]
    return {
        "n_1h": n_1h,
        "n_daily": n_daily,
        "n_oos": len(eval_indices),
        "last_1h": last_1h,
    }


def classify_symbol(sym: str, oos_start: str, oos_end: str, step: int) -> dict:
    solid = list_solidified()
    in_scheme = sym in SCHEMES
    universe = "l1" if sym in solid else ("l2" if not in_scheme else "l1")
    # solid == scheme keys in practice
    if in_scheme:
        universe = "l1"
    else:
        universe = "l2"

    try:
        stats = count_oos_eval_points(sym, oos_start, oos_end, step)
    except Exception as e:
        return {
            "symbol": sym,
            "eligible": False,
            "universe": universe,
            "sector": sector_of(sym),
            "skip_reason": f"SKIP_ERROR:{e}",
            "in_scheme": in_scheme,
            "solidified": sym in solid,
        }

    reasons = []
    if stats["n_1h"] < CONTEXT_BARS + HORIZON:
        reasons.append("SKIP_DATA_1H")
    if stats["n_daily"] < max(CONTEXT_DAYS - HORIZON_DAYS, 100):
        reasons.append("SKIP_DATA_DAILY")
    if stats["last_1h"] is None or pd.Timestamp(stats["last_1h"]) < pd.Timestamp(oos_start):
        reasons.append("SKIP_STALE")
    if stats["n_oos"] < MIN_OOS_POINTS:
        reasons.append("SKIP_OOS_SPARSE")

    scheme = get_scheme(sym) if in_scheme else None
    if scheme and scheme.covariate_types and len(scheme.covariate_types) > 1:
        cov = "+".join(scheme.covariate_types)
    elif scheme:
        cov = scheme.covariate_type
    else:
        cov = "ha_body"  # L2 default

    return {
        "symbol": sym,
        "eligible": len(reasons) == 0,
        "universe": universe,
        "sector": sector_of(sym),
        "skip_reason": ",".join(reasons) if reasons else None,
        "in_scheme": in_scheme,
        "solidified": sym in solid,
        "cov_label": cov,
        **stats,
    }


def main():
    parser = argparse.ArgumentParser(description="全品种准入扫描 S0")
    parser.add_argument("--oos-start", default=OOS_START)
    parser.add_argument("--oos-end", default=OOS_END)
    parser.add_argument("--step", type=int, default=STEP)
    parser.add_argument(
        "--out",
        default="reports/phase1/universe_eligibility.json",
    )
    args = parser.parse_args()

    symbols = list_db_symbols()
    rows = []
    print(f"Scanning {len(symbols)} DBs ...")
    for s in symbols:
        row = classify_symbol(s, args.oos_start, args.oos_end, args.step)
        rows.append(row)
        flag = "OK" if row["eligible"] else row["skip_reason"]
        print(
            f"  {s.upper():3} {row['universe']} {row['sector']:12} "
            f"1h={row.get('n_1h', 0):5} oos={row.get('n_oos', 0):3} "
            f"cov={row.get('cov_label')} → {flag}"
        )

    eligible = [r for r in rows if r["eligible"]]
    l1 = [r["symbol"] for r in eligible if r["universe"] == "l1"]
    l2 = [r["symbol"] for r in eligible if r["universe"] == "l2"]
    skipped = [r for r in rows if not r["eligible"]]

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "oos_start": args.oos_start,
        "oos_end": args.oos_end,
        "step": args.step,
        "min_oos_points": MIN_OOS_POINTS,
        "n_db": len(symbols),
        "n_eligible": len(eligible),
        "n_l1": len(l1),
        "n_l2": len(l2),
        "n_skipped": len(skipped),
        "l1_symbols": l1,
        "l2_symbols": l2,
        "all_eligible": [r["symbol"] for r in eligible],
        "skipped": skipped,
        "rows": rows,
        "vol_model_note": (
            "R0 uses models/vol_risk_filter_v2.pkl trained on "
            "rb,i,jm,ss,sr,fu,m — watch domain shift if veto% is 0% or 100% "
            "on chem/agri; trigger R1 sector models if needed."
        ),
    }

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEligible L1 ({len(l1)}): {l1}")
    print(f"Eligible L2 ({len(l2)}): {l2}")
    print(f"Skipped ({len(skipped)}): {[r['symbol'] for r in skipped]}")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

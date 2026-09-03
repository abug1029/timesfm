#!/usr/bin/env python3
"""
Option B: thr 网格扫描（离线）。

内核：cascade.vol_gating_replay
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.sector_map import sector_of  # noqa: E402
from cascade.vol_gating_replay import (  # noqa: E402
    HEALTHY_VETO_BAND,
    scan_thr_grid,
)
from cascade.neutral_ab_report import atomic_write_json, atomic_write_text  # noqa: E402

DEFAULT_SYMBOLS = ["sr", "fu", "eg", "ma", "m", "cf"]
DEFAULT_THRS = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
SHORT = {"energy_chem": "chem", "agri": "agri", "black_metals": "black", "other": "other"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--by-dir", default="reports/phase1/r1_smoke/by_symbol")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--thrs", nargs="+", type=float, default=DEFAULT_THRS)
    parser.add_argument("--out-dir", default="reports/phase1/r1")
    args = parser.parse_args()

    by_dir = Path(args.by_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for sym in args.symbols:
        sym = sym.lower()
        d = json.loads((by_dir / f"{sym}.json").read_text(encoding="utf-8"))
        results[sym] = scan_thr_grid(
            d.get("points_off") or [],
            args.thrs,
            symbol=sym,
        )
        results[sym]["sector"] = sector_of(sym)

    lo, hi = HEALTHY_VETO_BAND
    lines = [
        "# R1 Option B — thr 网格扫描（离线）",
        "",
        f"**生成**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**数据**: `{by_dir}`",
        f"**内核**: `cascade.vol_gating_replay`",
        f"**thr**: {args.thrs}",
        f"**健康 veto 带**: {lo:.0%}–{hi:.0%}",
        "",
        "## OOS vol_prob 分布",
        "",
        "| 品种 | 板块 | n | min | p50 | p80 | p90 | max | mean |",
        "|------|------|--:|----:|----:|----:|----:|----:|-----:|",
    ]
    for sym in args.symbols:
        sym = sym.lower()
        s = results[sym]["vol_stats"]
        sec = SHORT.get(results[sym]["sector"], results[sym]["sector"])
        lines.append(
            f"| {sym.upper()} | {sec} | {s['n']} | "
            f"{s['min']:.3f} | {s['p50']:.3f} | {s['p80']:.3f} | "
            f"{s['p90']:.3f} | {s['max']:.3f} | {s['mean']:.3f} |"
        )

    lines.extend([
        "",
        "## veto_rate 热力表",
        "",
        "| 品种 | 板块 | " + " | ".join(f"{t:.2f}" for t in args.thrs) + " |",
        "|------|------|" + "|".join(["------:" for _ in args.thrs]) + "|",
    ])
    for sym in args.symbols:
        sym = sym.lower()
        sec = SHORT.get(results[sym]["sector"], results[sym]["sector"])
        cells = []
        for thr in args.thrs:
            cell = results[sym]["by_thr"][f"{thr:.2f}"]
            vr = cell["veto_rate"]
            mark = f"**{vr:.0%}**" if cell["band"] == "HEALTHY" else f"{vr:.0%}"
            cells.append(mark)
        lines.append(f"| {sym.upper()} | {sec} | " + " | ".join(cells) + " |")

    for thr in args.thrs:
        lines.extend([
            "",
            f"### thr = {thr:.2f}",
            "",
            "| 品种 | veto | band | EV_off | EV_on | ΔEV | MaxDD_on | ΔMaxDD | NetPnL_on | tag |",
            "|------|------:|------|-------:|------:|----:|---------:|-------:|----------:|-----|",
        ])
        for sym in args.symbols:
            sym = sym.lower()
            cell = results[sym]["by_thr"][f"{thr:.2f}"]
            m, mo = cell["metrics"], cell["metrics_off"]
            lines.append(
                f"| {sym.upper()} | {cell['veto_rate']:.0%} | {cell['band']} | "
                f"{mo['EV']:.2f} | {m['EV']:.2f} | {cell['delta_EV']:+.2f} | "
                f"{m['MaxDD']:.4f} | {cell['delta_MaxDD']:+.4f} | "
                f"{m['NetPnL']:.0f} | {cell['tag']} |"
            )

    # sector thr heuristic
    lines.extend(["", "## 板块建议 thr（启发式）", ""])
    sector_members = {
        "energy_chem": [s for s in args.symbols if sector_of(s) == "energy_chem"],
        "agri": [s for s in args.symbols if sector_of(s) == "agri"],
    }
    for sec, members in sector_members.items():
        if not members:
            continue
        best_thr, best_score = None, -1e9
        for thr in args.thrs:
            healthy = sum(
                1 for s in members
                if results[s.lower()]["by_thr"][f"{thr:.2f}"]["band"] == "HEALTHY"
            )
            dev = sum(
                results[s.lower()]["by_thr"][f"{thr:.2f}"]["delta_EV"]
                for s in members
            )
            score = healthy * 100 + dev
            if score > best_score:
                best_score, best_thr = score, thr
        lines.append(
            f"- **{SHORT.get(sec, sec)}** (`{sec}`): thr≈**{best_thr:.2f}**"
        )
        for s in members:
            c = results[s.lower()]["by_thr"][f"{best_thr:.2f}"]
            lines.append(
                f"  - {s.upper()}: veto={c['veto_rate']:.0%} "
                f"ΔEV={c['delta_EV']:+.2f} band={c['band']}"
            )

    lines.append("")
    md_path = out_dir / "THR_SCAN_SMOKE.md"
    atomic_write_text(md_path, "\n".join(lines))
    atomic_write_json(out_dir / "thr_scan_smoke.json", {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "thrs": args.thrs,
        "results": results,
    })
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()

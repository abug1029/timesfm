#!/usr/bin/env python3
"""
离线重算 6 品种 Neutral A/B（不重跑 TimesFM）。

阈值决议：ThrPolicy（与 fullchain 同一契约）。
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
from cascade.vol_risk_filter import ThrPolicy, VolRiskFilter  # noqa: E402
from cascade.vol_gating_replay import recompute_neutral_at_thr  # noqa: E402
from cascade.neutral_ab_report import atomic_write_json, atomic_write_text  # noqa: E402
from config.backtest_config import TICK_SIZES  # noqa: E402

SYMBOLS = ["sr", "fu", "eg", "ma", "m", "cf"]
BY_DIR = Path("reports/phase1/r1_smoke/by_symbol")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["calibrated", "grid", "fixed"],
        default="calibrated",
        help="calibrated=IS p80 元数据默认; grid=--thr-chem/agri; fixed=--thr",
    )
    parser.add_argument("--thr", type=float, default=None)
    parser.add_argument("--thr-chem", type=float, default=None)
    parser.add_argument("--thr-agri", type=float, default=None)
    parser.add_argument("--out", default="reports/phase1/r1/RESMOKE_CALIBRATED.md")
    parser.add_argument("--no-calibrated-fallback", action="store_true",
                        help="grid/fixed 时禁止落到 calibrated_is")
    args = parser.parse_args()

    if args.mode == "grid":
        thr_chem = args.thr_chem if args.thr_chem is not None else 0.65
        thr_agri = args.thr_agri if args.thr_agri is not None else 0.45
        policy = ThrPolicy.from_cli(
            thr=None, thr_chem=thr_chem, thr_agri=thr_agri,
            allow_calibrated=not args.no_calibrated_fallback,
        )
    elif args.mode == "fixed":
        policy = ThrPolicy.from_cli(
            thr=args.thr if args.thr is not None else 0.55,
            allow_calibrated=False,
        )
    else:
        # calibrated: 无 CLI，落到 pkl calibrated_is
        policy = ThrPolicy(allow_calibrated=True, allow_operational=True)

    # 预载 pkl 元数据（用于报告）
    chem = VolRiskFilter.load("models/vol_risk_filter_chem.pkl")
    agri = VolRiskFilter.load("models/vol_risk_filter_agri.pkl")
    meta = {
        "energy_chem": {
            "calibrated_thr": chem.calibrated_thr,
            "operational_thr": chem.operational_thr,
        },
        "agri": {
            "calibrated_thr": agri.calibrated_thr,
            "operational_thr": agri.operational_thr,
        },
    }

    rows = []
    for sym in SYMBOLS:
        d = json.loads((BY_DIR / f"{sym}.json").read_text(encoding="utf-8"))
        sec = sector_of(sym)
        base = chem if sec == "energy_chem" else agri
        thr, src = policy.resolve(
            sym,
            calibrated_thr=base.calibrated_thr,
            operational_thr=base.operational_thr,
        )
        tick = TICK_SIZES.get(sym, 1.0)
        r = recompute_neutral_at_thr(d.get("points_off") or [], thr, tick_size=tick)
        rows.append({
            "sym": sym,
            "sector": sec,
            "thr": thr,
            "thr_source": src,
            "veto": r["veto_rate"],
            "ev_off": r["metrics_off"]["EV"],
            "ev_on": r["metrics"]["EV"],
            "dd_off": r["metrics_off"]["MaxDD"],
            "dd_on": r["metrics"]["MaxDD"],
            "pnl_off": r["metrics_off"]["NetPnL"],
            "pnl_on": r["metrics"]["NetPnL"],
            "tag": r["tag"],
            "band": r["band"],
        })

    by = {r["sym"]: r for r in rows}
    eg_ok = by["eg"]["veto"] < 0.40
    ma_ok = by["ma"]["veto"] < 0.40
    cf_ok = by["cf"]["veto"] > 0.10
    sr_ok = by["sr"]["veto"] > 0.10
    helps = [r for r in rows if r["tag"] == "HELPS"]
    gate_l1 = eg_ok and ma_ok and cf_ok and sr_ok and len(helps) >= 1

    lines = [
        f"# R1 离线重冒烟 — mode={args.mode}",
        "",
        f"**生成**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**阈值契约**: `ThrPolicy` → 单一 `threshold`",
        f"**内核**: `cascade.vol_gating_replay.recompute_neutral_at_thr`",
        f"**pkl meta**: chem cal={meta['energy_chem']['calibrated_thr']:.4f} "
        f"agri cal={meta['agri']['calibrated_thr']:.4f}",
        "",
        "## 结果",
        "",
        "| 品种 | 板块 | thr | source | veto | EV_off→on | ΔEV | tag |",
        "|------|------|----:|--------|-----:|----------:|----:|-----|",
    ]
    for r in rows:
        lines.append(
            f"| {r['sym'].upper()} | {r['sector']} | {r['thr']:.3f} | {r['thr_source']} | "
            f"{r['veto']:.0%} | {r['ev_off']:.2f}→{r['ev_on']:.2f} | "
            f"{r['ev_on']-r['ev_off']:+.2f} | **{r['tag']}** |"
        )

    lines.extend([
        "",
        "## L1 自动放行门槛",
        "",
        "| 条件 | 实际 | 过? |",
        "|------|------|:--:|",
        f"| EG veto < 40% | {by['eg']['veto']:.0%} | {'Y' if eg_ok else 'N'} |",
        f"| MA veto < 40% | {by['ma']['veto']:.0%} | {'Y' if ma_ok else 'N'} |",
        f"| CF veto > 10% | {by['cf']['veto']:.0%} | {'Y' if cf_ok else 'N'} |",
        f"| SR veto > 10% | {by['sr']['veto']:.0%} | {'Y' if sr_ok else 'N'} |",
        f"| ≥1 HELPS | {len(helps)} | {'Y' if helps else 'N'} |",
        f"| **L1 全量** |  | **{'YES' if gate_l1 else 'NO'}** |",
        "",
        f"**L1_AUTO_GATE={gate_l1}**",
        "",
    ])

    out = Path(args.out)
    atomic_write_text(out, "\n".join(lines))
    atomic_write_json(out.with_suffix(".json"), {
        "mode": args.mode,
        "meta": meta,
        "rows": rows,
        "gate_l1": gate_l1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    })
    print(f"Wrote {out}")
    print(f"L1_AUTO_GATE={gate_l1}")
    for r in rows:
        print(
            f"  {r['sym']}: thr={r['thr']:.3f}({r['thr_source']}) "
            f"veto={r['veto']:.0%} tag={r['tag']}"
        )


if __name__ == "__main__":
    main()

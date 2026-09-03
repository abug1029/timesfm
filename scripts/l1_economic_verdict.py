#!/usr/bin/env python3
"""
L1 全量经济门禁（D3 放宽后标准）。

标准（人工 2026-07-25 授权）:
  - HURTS 率 ≤ 15%
  - 全局等权 mean EV: ON ≥ OFF
  - mean |MaxDD| 收窄或持平（|MaxDD_on| ≤ |MaxDD_off| + eps）
不再使用 SR/EG veto% 硬门禁。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.neutral_ab_report import (  # noqa: E402
    atomic_write_json,
    atomic_write_text,
    load_results_from_by_symbol,
    score_universe,
)

HURTS_MAX = 0.15
EPS_DD = 1e-9


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--by-dir",
        default="reports/phase1/full_universe_neutral_r1_ops/by_symbol",
    )
    parser.add_argument(
        "--eligibility",
        default="reports/phase1/universe_eligibility.json",
    )
    parser.add_argument(
        "--out",
        default="reports/phase1/full_universe_neutral_r1_ops/ECONOMIC_VERDICT.md",
    )
    args = parser.parse_args()

    elig = json.loads(Path(args.eligibility).read_text(encoding="utf-8"))
    symbols = [s.lower() for s in elig.get("l1_symbols", [])]
    symbols, results = load_results_from_by_symbol(args.by_dir, symbols)
    score = score_universe(
        symbols, results,
        meta={"source": "l1_economic_verdict", "thr_note": "operational 0.65/0.45"},
    )

    n = len(score.rows) or 1
    hurts_rate = score.counts["HURTS"] / n
    mean_ev_off = score.pool_off["mean_EV"]
    mean_ev_on = score.pool_on["mean_EV"]
    mean_dd_off = score.pool_off["mean_MaxDD"]
    mean_dd_on = score.pool_on["mean_MaxDD"]
    # MaxDD 为负；|MaxDD| 收窄 ⇔ MaxDD_on 更大（更接近 0）
    dd_ok = mean_dd_on >= mean_dd_off - EPS_DD
    ev_ok = mean_ev_on >= mean_ev_off - 1e-9
    hurts_ok = hurts_rate <= HURTS_MAX + 1e-12
    pass_all = hurts_ok and ev_ok and dd_ok

    lines = [
        "# L1 全量经济判决书（Operational thr）",
        "",
        f"**生成**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**品种 n**: {len(score.rows)}",
        f"**thr**: chem=0.65 / agri=0.45 / black=0.55（operational）",
        f"**工程裁决**: `{score.engineering_verdict}`",
        f"**生产门禁(旧 scorer)**: `{score.production_gate}`",
        "",
        "## 经济门禁（D3 授权标准）",
        "",
        "| 条件 | 阈值 | 实际 | 过? |",
        "|------|------|------|:--:|",
        f"| HURTS 率 | ≤ {HURTS_MAX:.0%} | {hurts_rate:.1%} "
        f"({score.counts['HURTS']}/{n}) | {'**Y**' if hurts_ok else '**N**'} |",
        f"| mean EV ON ≥ OFF | ΔEV ≥ 0 | "
        f"OFF={mean_ev_off:.4f} ON={mean_ev_on:.4f} "
        f"Δ={mean_ev_on-mean_ev_off:+.4f} | {'**Y**' if ev_ok else '**N**'} |",
        f"| mean MaxDD 收窄/持平 | MaxDD_on ≥ MaxDD_off | "
        f"OFF={mean_dd_off:.4f} ON={mean_dd_on:.4f} "
        f"Δ={mean_dd_on-mean_dd_off:+.4f} | {'**Y**' if dd_ok else '**N**'} |",
        "",
        f"## 最终判决: **{'PASS — 具备风控网关候选资格' if pass_all else 'FAIL — 未达经济门禁'}**",
        "",
        "## 分品种标签",
        "",
        f"HELPS={score.counts['HELPS']} MIXED={score.counts['MIXED']} "
        f"HURTS={score.counts['HURTS']} NEUTRAL={score.counts['NEUTRAL']}",
        "",
        "| 品种 | sector | veto | EV_off | EV_on | ΔEV | MaxDD_on | tag |",
        "|------|--------|-----:|-------:|------:|----:|---------:|-----|",
    ]
    for r in score.rows:
        lines.append(
            f"| {r['sym'].upper()} | {r['sector']} | {r['veto']:.0%} | "
            f"{r['ev_off']:.2f} | {r['ev_on']:.2f} | {r['ev_on']-r['ev_off']:+.2f} | "
            f"{r['dd_on']:.4f} | **{r['tag']}** |"
        )

    lines.extend([
        "",
        "## 说明",
        "",
        "- 已废弃 SR/EG veto% 硬门禁；veto=0 在低波期可视为正确。",
        "- 主看 HELPS 切断亏损与宇宙 EV/MaxDD。",
        f"- by_symbol: `{args.by_dir}`",
        "",
    ])

    out = Path(args.out)
    atomic_write_text(out, "\n".join(lines))
    atomic_write_json(out.with_suffix(".json"), {
        "pass": pass_all,
        "hurts_rate": hurts_rate,
        "mean_ev_off": mean_ev_off,
        "mean_ev_on": mean_ev_on,
        "mean_dd_off": mean_dd_off,
        "mean_dd_on": mean_dd_on,
        "counts": score.counts,
        "rows": score.rows,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    })
    print(f"Wrote {out}")
    print(f"ECONOMIC_PASS={pass_all} hurts={hurts_rate:.1%} "
          f"dEV={mean_ev_on-mean_ev_off:+.4f} dDD={mean_dd_on-mean_dd_off:+.4f}")


if __name__ == "__main__":
    main()

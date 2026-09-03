#!/usr/bin/env python3
"""
two_star_critic.py - 2星->3星 候选结果 critic + v2 判定 + 3星检查

解析 reports/two_star_results.jsonl, 每品种以 baseline (同窗口) 为参照,
对每个候选应用 v2 固化判据 (复用 phase4d_parse_results.verdict), 并检查
3 星晋级条件 (DirAcc>=65% + PF>=1.15)。

输出:
  - 控制台: 每品种候选对比表 + v2 verdict + 3星检查
  - reports/two_star_critic_report.md: 完整报告

用法:
  python scripts/two_star_critic.py
  python scripts/two_star_critic.py --sym fu rb   # 仅指定品种
"""
from __future__ import annotations

import io
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
os.chdir(FM_ROOT)

from phase4d_parse_results import verdict, N_MIN  # noqa: E402

RESULTS_JSONL = os.path.join(FM_ROOT, "reports", "two_star_results.jsonl")
REPORT_MD = os.path.join(FM_ROOT, "reports", "two_star_critic_report.md")

TIER_A = {"fu", "rb", "fg", "ta", "lh"}
TIER_B = {"m", "cf", "eg", "cj", "jd"}
TIER_C = {"jm", "i", "bu", "p", "ao"}


def to_vdict(rec: dict) -> dict:
    """runner JSONL 记录 -> verdict() 所需 dict (diracc/maxdd 转百分点)。"""
    return {
        "n": int(rec["n"]),
        "diracc": round(rec["dir_acc"] * 100),
        "mape": float(rec["mape"]),
        "ev": float(rec["ev_ratio"]),
        "pf": float(rec["profit_factor"]),
        "maxdd": round(rec["max_dd"] * 100, 2),
        "wr": round(rec["win_rate"] * 100),
        "decay": float(rec["decay"]),
    }


def three_star_score(rec: dict) -> tuple[int, float, str]:
    """复刻 build_knowledge_base._stars_from_metrics。返回 (stars, score, 说明)。"""
    da = rec["dir_acc"]
    pf = rec["profit_factor"]
    score = 0.0
    if da >= 0.65:
        score += 2
    elif da >= 0.55:
        score += 1
    if pf >= 1.4:
        score += 1
    elif pf >= 1.15:
        score += 0.5
    if 0 < pf < 0.95:
        score = max(0, score - 1)
    stars = int(round(min(3, score)))
    note = f"DirAcc={da:.0%}({'+2' if da>=0.65 else '+1' if da>=0.55 else '+0'}) + PF={pf:.2f}({'+1' if pf>=1.4 else '+0.5' if pf>=1.15 else '+0'}) = {score}"
    return stars, score, note


def load_results() -> dict:
    """sym -> {label: rec} (仅 status=OK)。"""
    rows = {}
    if not os.path.exists(RESULTS_JSONL):
        return rows
    with open(RESULTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") != "OK":
                continue
            rows.setdefault(rec["sym"], {})[rec["label"]] = rec
    return rows


def fmt_v2(status: str) -> str:
    """v2 状态缩写。"""
    return {
        "PASS": "PASS",
        "GREEN-EV": "G-EV",
        "GREEN-MAXDD": "G-DD",
        "FAIL": "FAIL",
        "UNDERPOWERED": "UNDER",
    }.get(status, status)


def main():
    args = sys.argv[1:]
    sym_filter = None
    if "--sym" in args:
        idx = args.index("--sym")
        sym_filter = {s.lower() for s in args[idx + 1:]}

    rows = load_results()
    if not rows:
        print("无结果 (reports/two_star_results.jsonl 为空或不存在)")
        return

    # 品种优先级: A -> B -> C, 各组内按 scheme DirAcc 降序
    def sym_sort(sym):
        if sym in TIER_A:
            return (0, sym)
        if sym in TIER_B:
            return (1, sym)
        return (2, sym)

    syms = sorted(rows.keys(), key=sym_sort)
    if sym_filter:
        syms = [s for s in syms if s in sym_filter]

    lines_md = [
        "# 2星->3星 协变量优化 Critic 报告",
        "",
        f"**结果源**: `reports/two_star_results.jsonl`",
        f"**品种数**: {len(syms)}",
        "",
        "---",
        "",
    ]
    print("=" * 90)
    print(f"2星->3星 Critic | {len(syms)} 品种")
    print("=" * 90)

    promote_candidates = []  # 达 3 星的候选
    solidify_candidates = []  # v2 PASS (无论是否 3 星)

    for sym in syms:
        recs = rows[sym]
        base = recs.get("baseline")
        tier = "A" if sym in TIER_A else "B" if sym in TIER_B else "C"

        print(f"\n{'─' * 90}")
        print(f"  {sym.upper()} (Tier {tier})")
        print(f"{'─' * 90}")

        if not base:
            print(f"  ⚠️ 无 baseline, 跳过")
            lines_md.extend([f"## {sym.upper()} (Tier {tier})", "", "> ⚠️ 无 baseline, 无法判定", ""])
            continue

        b_stars, b_score, b_note = three_star_score(base)
        print(f"  baseline: DirAcc={base['dir_acc']:.1%} MAPE={base['mape']:.2f}% "
              f"EV={base['ev_ratio']:+.3f} PF={base['profit_factor']:.2f} "
              f"MaxDD={base['max_dd']:.2%} n={base['n']} | {b_stars}星 ({b_note})")

        lines_md.extend([
            f"## {sym.upper()} (Tier {tier})",
            "",
            f"**baseline** [{base['covs']}]: DirAcc={base['dir_acc']:.1%} "
            f"MAPE={base['mape']:.2f}% EV={base['ev_ratio']:+.3f} PF={base['profit_factor']:.2f} "
            f"MaxDD={base['max_dd']:.2%} n={base['n']} -> **{b_stars}星** ({b_note})",
            "",
            "| 候选 | DirAcc | MAPE | EV | PF | MaxDD | ΔDirAcc | v2 | 3星 | verdict理由 |",
            "|------|:------:|:----:|:--:|:--:|:-----:|:------:|:--:|:---:|------------|",
        ])

        bv = to_vdict(base)
        best_cand = None  # (rec, status, stars)
        for label, rec in recs.items():
            if label == "baseline":
                continue
            cv = to_vdict(rec)
            status, tag, reasons = verdict(bv, cv)
            c_stars, c_score, _ = three_star_score(rec)
            da_delta = round((rec["dir_acc"] - base["dir_acc"]) * 100)
            v2s = fmt_v2(status)
            star_mark = "⭐3" if c_stars == 3 else f"{c_stars}★"

            print(f"  {label:34} DirAcc={rec['dir_acc']:.1%}(Δ{da_delta:+d}pp) "
                  f"PF={rec['profit_factor']:.2f} EV={rec['ev_ratio']:+.3f} "
                  f"MaxDD={rec['max_dd']:.2%} | v2={v2s:5} {star_mark}")

            reason_str = "; ".join(reasons) if reasons else ""
            lines_md.append(
                f"| {label} | {rec['dir_acc']:.1%} | {rec['mape']:.2f}% | "
                f"{rec['ev_ratio']:+.3f} | {rec['profit_factor']:.2f} | "
                f"{rec['max_dd']:.2%} | {da_delta:+d}pp | {v2s} | {star_mark} | {reason_str} |"
            )

            # 记录 v2 PASS 候选
            if status in ("PASS", "GREEN-EV", "GREEN-MAXDD"):
                solidify_candidates.append((sym, label, rec, status, tag, c_stars))
            # 记录 3 星候选
            if c_stars == 3:
                promote_candidates.append((sym, label, rec, status, tag))

            # 选最佳候选 (3星优先, 否则 v2 PASS + DirAcc 最高)
            if best_cand is None:
                best_cand = (rec, status, c_stars)
            else:
                _, _, bs = best_cand
                if c_stars > bs or (c_stars == bs and rec["dir_acc"] > best_cand[0]["dir_acc"]):
                    best_cand = (rec, status, c_stars)

        lines_md.append("")

    # ── 汇总 ──
    print("\n" + "=" * 90)
    print("汇总")
    print("=" * 90)

    if promote_candidates:
        print(f"\n⭐⭐⭐ 达 3 星候选: {len(promote_candidates)}")
        for sym, label, rec, status, tag in promote_candidates:
            print(f"  {sym.upper():4} {label:34} DirAcc={rec['dir_acc']:.1%} PF={rec['profit_factor']:.2f} "
                  f"(v2={status}) -> 建议固化晋级 3星")
    else:
        print("\n⭐⭐⭐ 达 3 星候选: 0 (DirAcc>=65% 未达成)")

    if solidify_candidates:
        print(f"\n✅ v2 PASS 候选 (可固化): {len(solidify_candidates)}")
        for sym, label, rec, status, tag, stars in solidify_candidates:
            star_str = f"-> 3星晋级" if stars == 3 else f"维持 {stars}星 (改善)"
            print(f"  {sym.upper():4} {label:34} DirAcc={rec['dir_acc']:.1%} PF={rec['profit_factor']:.2f} "
                  f"v2={status} {star_str}")

    # 写 MD 报告
    lines_md.extend([
        "---",
        "",
        "## 汇总",
        "",
    ])
    if promote_candidates:
        lines_md.append(f"### ⭐⭐⭐ 达 3 星候选 ({len(promote_candidates)})")
        lines_md.append("")
        lines_md.append("| 品种 | 候选 | DirAcc | PF | v2 |")
        lines_md.append("|------|------|:------:|:--:|:--:|")
        for sym, label, rec, status, tag in promote_candidates:
            lines_md.append(f"| {sym.upper()} | {label} | {rec['dir_acc']:.1%} | {rec['profit_factor']:.2f} | {status} |")
        lines_md.append("")
    else:
        lines_md.append("> ⭐⭐⭐ 达 3 星候选: **0** (DirAcc>=65% 未达成, 受限于品种可预测性天花板)")
        lines_md.append("")

    if solidify_candidates:
        lines_md.append(f"### ✅ v2 PASS 可固化 ({len(solidify_candidates)})")
        lines_md.append("")
        lines_md.append("| 品种 | 候选 | DirAcc | ΔDirAcc | PF | v2 | 结果 |")
        lines_md.append("|------|------|:------:|:------:|:--:|:--:|------|")
        for sym, label, rec, status, tag, stars in solidify_candidates:
            star_str = "3星晋级" if stars == 3 else f"{stars}星改善"
            lines_md.append(f"| {sym.upper()} | {label} | {rec['dir_acc']:.1%} | - | {rec['profit_factor']:.2f} | {status} | {star_str} |")
        lines_md.append("")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_md))
    print(f"\n报告: {REPORT_MD}")


if __name__ == "__main__":
    main()

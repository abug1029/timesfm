#!/usr/bin/env python3
"""
three_star_verify_critic.py - 3 星新鲜度验证 + MA 优化结果分析

读 reports/three_star_verify_results.jsonl, 输出:
  1. 3 星品种 (SS/UR/SP/SR) scheme dir_acc vs 新鲜 baseline 漂移表
  2. MA 候选 A/B (vs MA baseline), v2 verdict, 最优配置推荐
  3. 需更新的 scheme dir_acc 清单
"""
from __future__ import annotations
import io, json, os, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.prediction_scheme import SCHEMES  # noqa: E402

RESULTS = ROOT / "reports" / "three_star_verify_results.jsonl"
REPORT = ROOT / "reports" / "three_star_verify_critic_report.md"


def load_results():
    recs = {}
    if not RESULTS.exists():
        return recs
    with open(RESULTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("status") == "OK":
                recs[(r["sym"], r["label"])] = r
    return recs


def main():
    recs = load_results()
    if not recs:
        print("无结果。"); return

    lines = ["# 3 星新鲜度验证 + MA 优化 结果分析\n"]
    lines.append(f"**结果源**: `{RESULTS}`\n**作业数**: {len(recs)}\n\n---\n")

    # ── 3 星品种新鲜度 ──
    lines.append("## 1. 3 星品种新鲜度验证\n")
    lines.append("| 品种 | scheme DirAcc | 新鲜 DirAcc | 漂移 | scheme MAPE | 新鲜 MAPE | PF | MaxDD | 状态 |\n")
    lines.append("|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|\n")
    stale = []
    for sym in ["ss", "ur", "sp", "sr"]:
        r = recs.get((sym, "baseline"))
        sc = SCHEMES[sym]
        if not r:
            lines.append(f"| {sym.upper()} | {sc.dir_acc:.1%} | - | - | {sc.mape:.2f}% | - | - | - | 缺数据 |\n")
            continue
        delta = r["dir_acc"] - sc.dir_acc
        status = "STALE" if abs(delta) > 0.05 else ("微漂移" if abs(delta) > 0.02 else "OK")
        if abs(delta) > 0.05:
            stale.append((sym, sc.dir_acc, r["dir_acc"], delta))
        lines.append(f"| {sym.upper()} | {sc.dir_acc:.1%} | {r['dir_acc']:.1%} | {delta:+.1%} | "
                     f"{sc.mape:.2f}% | {r['mape']:.2f}% | {r['profit_factor']:.2f} | "
                     f"{r['max_dd']:.1%} | {status} |\n")

    if stale:
        lines.append(f"\n**⚠️ {len(stale)} 个 3 星品种 dir_acc 显著 stale (>5pp)**\n")
        for sym, old, new, d in stale:
            lines.append(f"- {sym.upper()}: {old:.1%} -> {new:.1%} ({d:+.1%})\n")

    # ── MA 优化 ──
    lines.append("\n## 2. MA 甲醇再优化\n")
    ma_base = recs.get(("ma", "baseline"))
    if ma_base:
        lines.append(f"**Baseline** (scheme: {SCHEMES['ma'].covariate_types}): "
                     f"DirAcc={ma_base['dir_acc']:.1%} PF={ma_base['profit_factor']:.2f} "
                     f"MaxDD={ma_base['max_dd']:.1%} EV={ma_base['ev_ratio']:+.3f}\n\n")
        lines.append("| 候选 | DirAcc | Δ | PF | Δ | MaxDD | EV | 推荐 |\n")
        lines.append("|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|\n")
        best = None
        for label in ["ha_body", "ha_body+hourly_slope", "bb_squeeze", "bb_squeeze+ha_body", "ao_accel", "vor"]:
            r = recs.get(("ma", label))
            if not r:
                lines.append(f"| {label} | - | - | - | - | - | - | 缺数据 |\n")
                continue
            d_da = r["dir_acc"] - ma_base["dir_acc"]
            d_pf = r["profit_factor"] - ma_base["profit_factor"]
            pf_gain = (r["profit_factor"] / ma_base["profit_factor"] - 1) if ma_base["profit_factor"] > 0 else 0
            recommend = "★" if (d_da > 0 and d_pf > 0) else ""
            if d_da > 0 and d_pf > 0 and (best is None or d_pf > best[1]):
                best = (label, d_pf, r)
            lines.append(f"| {label} | {r['dir_acc']:.1%} | {d_da:+.1%} | {r['profit_factor']:.2f} | "
                         f"{d_pf:+.2f} | {r['max_dd']:.1%} | {r['ev_ratio']:+.3f} | {recommend} |\n")
        if best:
            lines.append(f"\n**MA 最优候选**: {best[0]} (DirAcc {best[2]['dir_acc']:.1%}, "
                         f"PF {best[2]['profit_factor']:.2f})\n")
            pf_gain = best[2]["profit_factor"] / ma_base["profit_factor"] - 1
            if pf_gain >= 0.10:
                lines.append(f"- PF 提升 {pf_gain:+.1%} >= 10% -> **v2 ordinary PASS 候选**, 可考虑固化\n")
            else:
                lines.append(f"- PF 提升 {pf_gain:+.1%} < 10% -> v2 未达, 维持 1 星\n")

    # ── 需更新清单 ──
    lines.append("\n## 3. Scheme dir_acc 更新清单\n")
    if stale:
        lines.append("以下 3 星品种 scheme dir_acc 需更新为新鲜值:\n")
        for sym, old, new, d in stale:
            lines.append(f"- {sym.upper()}: {old:.3f} -> {new:.3f}\n")
    else:
        lines.append("无 3 星品种需更新 (全部 OK 或微漂移)\n")

    REPORT.write_text("".join(lines), encoding="utf-8")
    print("".join(lines))
    print(f"\n报告: {REPORT}")


if __name__ == "__main__":
    main()

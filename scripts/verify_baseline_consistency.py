"""核实各品种 baseline PF 来源的一致性

Phase 15 审核修复 Task 2: 基线 PF 核实与统一
- 来源 1: prediction_scheme.py G005 系列注释中的 PF 值 (权威 walk-forward 回测)
- 来源 2: reports/history/<sym>/predictions.json (最近预测的 pf 字段,通常为 0)
- 来源 3: STATE.md Phase 15 结果表格 (人工写入的 baseline PF)

用途: 识别不同来源间的 PF 差异,确保报告/文档引用一致的基线值.

关键区分:
- dir_acc (方向准确率): ~0.47-0.58, 不是 PF
- PF (Profit Factor): 盈亏比, baseline 通常 0.70-1.50
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"

from config.prediction_scheme import SCHEMES

# Phase 15 测试的 6 个品种
VARIETIES = ["jm", "ma", "ur", "fg", "cf", "ao"]

print("=" * 80)
print("Baseline PF 来源核实 (Phase 15 Task 2)")
print("=" * 80)

# =========================================================================
# 来源 1: prediction_scheme.py G005 注释中的 PF 值
# =========================================================================
# 从 G005 系列注释中提取的真实 PF (walk-forward 回测):
#   JM: G005-D "PF=0.85" -> 但 STATE.md 用 0.90 (可能来自更早回测)
#   MA: G005-E "PF=0.71" -> 但 STATE.md 用 1.00 (严重不一致)
#   UR: G005-E "PF=0.84" -> 但 STATE.md 用 0.97
#   FG: G005-D "PF=0.91" -> 但 STATE.md 用 0.93
#   CF: G005-C short "PF=0.80" -> 但 STATE.md 用 0.90
#   AO: G005-E "PF=0.86" -> 但 STATE.md 用 0.95
#
# 这些 PF 值来自 prediction_scheme.py 注释中的 G005 系列回测结果.
# 但 STATE.md 表格中的值与之有差异,可能是引用了不同版本的回测.

g005_pf_from_scheme = {
    "jm": 0.85,   # G005-D: "PF=0.85 -> 降1星"
    "ma": 0.71,   # G005-E: "PF=0.71 维持1星"
    "ur": 0.84,   # G005-E: "PF=0.84 n=303 underpowered"
    "fg": 0.91,   # G005-D: "PF=0.91 -> 降1星"
    "cf": 0.80,   # G005-C: "short PF=0.80"
    "ao": 0.86,   # G005-E: "PF=0.86 n=193"
}

# 同时提取 dir_acc 供对照
dir_acc_values = {}
for sym in VARIETIES:
    scheme = SCHEMES.get(sym)
    if scheme:
        dir_acc_values[sym] = scheme.dir_acc

print("\n来源 1: prediction_scheme.py (G005 系列回测注释)")
print("-" * 80)
print(f"{'品种':4s}  {'PF(G005)':>8}  {'dir_acc':>7}  {'星星':>4s}  协变量")
print("-" * 80)
for sym in VARIETIES:
    scheme = SCHEMES.get(sym)
    if scheme:
        pf = g005_pf_from_scheme[sym]
        da = dir_acc_values[sym]
        stars = scheme.stars
        cov = scheme.covariate_type
        print(f"{sym.upper():4s}  {pf:>8.2f}  {da:>6.3f}  {stars:>2d}★   {cov}")
    else:
        print(f"{sym.upper():4s}  {'未固化':>8s}")

# =========================================================================
# 来源 2: predictions.json (最近预测的 pf 字段)
# =========================================================================
print("\n来源 2: reports/history/<sym>/predictions.json (最近预测 pf)")
print("-" * 80)
for sym in VARIETIES:
    pred_file = Path(f"reports/history/{sym}/predictions.json")
    if pred_file.exists():
        with open(pred_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            recent = data.get("predictions", [])[-5:]
        elif isinstance(data, list):
            recent = data[-5:]
        else:
            recent = []

        if recent:
            pf_values = [p.get("pf", 0) for p in recent if "pf" in p]
            if pf_values and any(v != 0 for v in pf_values):
                avg = sum(pf_values) / len(pf_values)
                print(f"{sym.upper():4s}: 最近 {len(pf_values)} 次平均 pf={avg:.3f}")
            else:
                print(f"{sym.upper():4s}: pf 全为 0 (单点预测无实际盈亏, 非回测)")
        else:
            print(f"{sym.upper():4s}: 无预测记录")
    else:
        print(f"{sym.upper():4s}: predictions.json 不存在")

# =========================================================================
# 来源 3: STATE.md Phase 15 结果表格
# =========================================================================
print("\n来源 3: STATE.md Phase 15 结果表格 (第 469-476 行)")
print("-" * 80)
state_md_baseline = {
    "jm": 0.90,
    "ma": 1.00,
    "ur": 0.97,
    "fg": 0.93,
    "cf": 0.90,
    "ao": 0.95,
}
for sym in VARIETIES:
    print(f"{sym.upper():4s}: baseline PF={state_md_baseline[sym]:.2f}")

# =========================================================================
# 差异分析
# =========================================================================
print("\n" + "=" * 80)
print("差异分析: G005 回测 PF (scheme.py 注释) vs STATE.md")
print("=" * 80)
print(f"{'品种':4s}  {'G005 PF':>8}  {'STATE.md':>8}  {'delta':>6}  {'|delta|>0.05?':12s}  结论")
print("-" * 80)
discrepancies = []
for sym in VARIETIES:
    g005 = g005_pf_from_scheme.get(sym)
    state = state_md_baseline.get(sym)
    if g005 is not None and state is not None:
        delta = state - g005
        flag = "YES" if abs(delta) > 0.05 else "OK"
        conclusion = "不一致" if abs(delta) > 0.05 else "一致"
        if abs(delta) > 0.05:
            discrepancies.append(sym)
            print(f"{sym.upper():4s}  {g005:>8.2f}  {state:>8.2f}  {delta:>+6.2f}  {flag:>12s}  {conclusion}")
        else:
            print(f"{sym.upper():4s}  {g005:>8.2f}  {state:>8.2f}  {delta:>+6.2f}  {flag:>12s}  {conclusion}")

if discrepancies:
    print(f"\n结论: {len(discrepancies)}/{len(VARIETIES)} 个品种 baseline PF 不一致 (差异 > 0.05)")
    print(f"  涉及品种: {', '.join(s.upper() for s in discrepancies)}")
    print("\n根因: STATE.md 表格中的 baseline PF 与 G005 系列回测注释不一致.")
    print("      可能原因: 引用了不同版本/不同参数的回测结果.")
    print("\n建议:")
    print("  1. 统一以 monthly_backtest.py 最新全量回测结果为准")
    print("  2. STATE.md 的 baseline PF 列应标注来源 (如 'G005-D 2026-08-08')")
    print("  3. 后续报告/文档引用 baseline 时注明回测批次编号")
    print("\n修正参考值 (G005 系列):")
    for sym in discrepancies:
        g005 = g005_pf_from_scheme[sym]
        state = state_md_baseline[sym]
        print(f"  {sym.upper()}: STATE.md {state:.2f} -> G005 {g005:.2f} (delta={g005-state:+.2f})")
else:
    print("\n✅ 所有品种 baseline PF 一致 (差异 <= 0.05)")

print("\n" + "=" * 80)
print("核实完成")
print("=" * 80)

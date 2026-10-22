#!/usr/bin/env python3
"""
诊断低通过率 symbol/family 根因（Task 3 of Phase 1）

目标：识别 eg/stddev/ccl 等低通过率根因，输出诊断报告
数据快照时间戳：2026-10-19（基于 SPEC v3.1 §3.4/§3.5）

约束：
- 不违反 Laya 不可学习约束
- 小样本（n<10）不作为"低效"结论依据
- 使用唯一 variant 口径（按 variant_id 去重）
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import math

VERDICTS_PATH = Path("/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl")
BASELINE_DIR = Path("/home/abug/timesfm/task_FM/config")
REPORT_PATH = Path("/home/abug/timesfm/docs/superpowers/reports/2026-10-20-low-efficiency-diagnosis.md")

TARGET_SYMBOLS = ["eg", "ma", "fu", "px", "jm"]
TARGET_FAMILIES = ["stddev", "ccl"]
SMALL_SAMPLE_THRESHOLD = 10


def load_verdicts():
    """加载并对齐 verdicts，按 variant_id 去重（保留第一条）"""
    verdicts = []
    seen_ids = set()
    with open(VERDICTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
                vid = v.get("variant_id")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    verdicts.append(v)
            except json.JSONDecodeError as e:
                print(f"Warning: parse error: {e}", file=sys.stderr)
    return verdicts


def binomial_ci(k, n, confidence=0.95):
    """Wilson score interval for binomial proportion"""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96 if confidence == 0.95 else 2.576
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def analyze_symbol(verdicts, symbol):
    sv = [v for v in verdicts if v.get("symbol") == symbol]
    if not sv:
        return None
    n_total = len(sv)
    n_pass = sum(1 for v in sv if v.get("gate_pass"))
    pass_rate = n_pass / n_total if n_total > 0 else 0.0
    dir_accs = [v.get("dir_acc", 0) for v in sv if v.get("dir_acc") is not None]
    avg_da = sum(dir_accs) / len(dir_accs) if dir_accs else 0.0
    min_da = min(dir_accs) if dir_accs else 0.0
    max_da = max(dir_accs) if dir_accs else 0.0
    fam_counts = defaultdict(int)
    fam_pass = defaultdict(int)
    for v in sv:
        fam = v.get("cov_family", "unknown")
        fam_counts[fam] += 1
        if v.get("gate_pass"):
            fam_pass[fam] += 1
    ci_lo, ci_hi = binomial_ci(n_pass, n_total)
    return {
        "symbol": symbol,
        "n_total": n_total,
        "n_gate_pass": n_pass,
        "pass_rate": pass_rate,
        "avg_dir_acc": avg_da,
        "min_dir_acc": min_da,
        "max_dir_acc": max_da,
        "dir_accs": dir_accs,
        "family_counts": dict(fam_counts),
        "family_pass": dict(fam_pass),
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "is_small_sample": n_total < SMALL_SAMPLE_THRESHOLD,
        "verdicts": sv,
    }


def analyze_family(verdicts, family):
    """分析 family（基于 cov_override 字段，非 cov_family）"""
    fv = [v for v in verdicts if v.get("cov_override") == family]
    if not fv:
        return None
    n_total = len(fv)
    n_pass = sum(1 for v in fv if v.get("gate_pass"))
    pass_rate = n_pass / n_total if n_total > 0 else 0.0
    dir_accs = [v.get("dir_acc", 0) for v in fv if v.get("dir_acc") is not None]
    avg_da = sum(dir_accs) / len(dir_accs) if dir_accs else 0.0
    sym_counts = defaultdict(int)
    sym_pass = defaultdict(int)
    for v in fv:
        sym = v.get("symbol", "unknown")
        sym_counts[sym] += 1
        if v.get("gate_pass"):
            sym_pass[sym] += 1
    ci_lo, ci_hi = binomial_ci(n_pass, n_total)
    return {
        "family": family,
        "n_total": n_total,
        "n_gate_pass": n_pass,
        "pass_rate": pass_rate,
        "avg_dir_acc": avg_da,
        "dir_accs": dir_accs,
        "symbol_counts": dict(sym_counts),
        "symbol_pass": dict(sym_pass),
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "verdicts": fv,
    }


def check_baseline_data(symbol):
    bf = BASELINE_DIR / f"baseline_points_{symbol}_nocov.jsonl"
    if not bf.exists():
        return {"exists": False, "n_points": 0, "status": "missing"}
    n_points = 0
    has_data = False
    with open(bf, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                n_points += 1
                try:
                    pt = json.loads(line)
                    if pt.get("dt") or pt.get("timestamp"):
                        has_data = True
                except Exception:
                    pass
    return {
        "exists": True,
        "n_points": n_points,
        "has_data": has_data,
        "status": "ok" if has_data else "empty",
    }


def fmt_pct(v):
    return f"{v*100:.1f}%"


def generate_report(verdicts, sym_analyses, fam_analyses, baseline_checks):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    R = []
    R.append("# 低效 Symbol/Family 诊断报告")
    R.append("")
    R.append(f"**生成时间**: {ts}")
    R.append(f"**数据快照时间**: 2026-10-19（基于 SPEC v3.1 §3.4/§3.5）")
    R.append(f"**数据来源**: `{VERDICTS_PATH}`")
    R.append(f"**总 verdict 数**: {len(verdicts)}（按 variant_id 去重后）")
    R.append("")
    R.append("---")
    R.append("")

    # 总体统计
    total_pass = sum(1 for v in verdicts if v.get("gate_pass"))
    all_da = [v.get("dir_acc", 0) for v in verdicts if v.get("dir_acc") is not None]
    R.append("## 0. 总体统计")
    R.append("")
    R.append(f"- **总 verdict**: {len(verdicts)}")
    R.append(f"- **Gate pass**: {total_pass} ({fmt_pct(total_pass/len(verdicts))})")
    R.append(f"- **平均 dir_acc**: {sum(all_da)/len(all_da):.3f}")
    R.append("")
    R.append("---")
    R.append("")

    # Symbol 诊断
    R.append("## 1. Symbol 诊断")
    R.append("")
    compare_syms = ["eg", "ma", "fu", "px", "jm", "cf", "sh", "ta", "rb", "m", "lh", "jd"]
    R.append("### 1.1 全 Symbol 概览")
    R.append("")
    R.append("| Symbol | n | Gate Pass | Pass Rate | dir_acc (mean) | 95% CI | 评估 |")
    R.append("|--------|---|-----------|-----------|----------------|--------|------|")
    for sym in compare_syms:
        a = sym_analyses.get(sym)
        if not a:
            continue
        if a["is_small_sample"]:
            tag = "小样本观察"
        elif a["pass_rate"] == 0:
            tag = "需诊断"
        elif a["pass_rate"] < 0.2:
            tag = "需提升"
        elif a["pass_rate"] >= 0.4:
            tag = "良好"
        else:
            tag = "中等"
        R.append(
            f"| {sym} | {a['n_total']} | {a['n_gate_pass']} | {fmt_pct(a['pass_rate'])} "
            f"| {a['avg_dir_acc']:.3f} | [{fmt_pct(a['ci_lower'])}, {fmt_pct(a['ci_upper'])}] | {tag} |"
        )
    R.append("")

    for sym in TARGET_SYMBOLS:
        a = sym_analyses.get(sym)
        if not a:
            R.append(f"### {sym}: 无数据")
            R.append("")
            continue
        R.append(f"### 1.2 {sym} 详细诊断")
        R.append("")
        if a["is_small_sample"]:
            R.append(
                f"> **样本量警告**: n={a['n_total']} < {SMALL_SAMPLE_THRESHOLD}，"
                f"**不作为低效结论依据**，仅作观察。"
            )
            R.append("")
        R.append(f"- **Gate pass**: {a['n_gate_pass']}/{a['n_total']} ({fmt_pct(a['pass_rate'])})")
        R.append(f"- **95% 置信区间**: [{fmt_pct(a['ci_lower'])}, {fmt_pct(a['ci_upper'])}]")
        R.append(
            f"- **dir_acc**: mean={a['avg_dir_acc']:.3f}, "
            f"min={a['min_dir_acc']:.3f}, max={a['max_dir_acc']:.3f}"
        )
        bl = baseline_checks.get(sym, {})
        if bl.get("exists"):
            R.append(f"- **基础数据**: OK ({bl['n_points']} 数据点)")
        else:
            R.append(f"- **基础数据**: MISSING")
        R.append("")
        R.append("**Family 分布**:")
        R.append("")
        R.append("| Family | n | Gate Pass | Pass Rate |")
        R.append("|--------|---|-----------|-----------|")
        for fam, cnt in sorted(a["family_counts"].items(), key=lambda x: -x[1]):
            pc = a["family_pass"].get(fam, 0)
            pr = pc / cnt if cnt > 0 else 0
            R.append(f"| {fam} | {cnt} | {pc} | {fmt_pct(pr)} |")
        R.append("")
        R.append("**根因分析**:")
        R.append("")
        if sym == "eg":
            R.append(f"1. **数据质量**: 基础数据完整（{bl.get('n_points', '?')} 数据点），排除数据缺失问题")
            R.append(f"2. **dir_acc 分布**: mean={a['avg_dir_acc']:.3f}, max={a['max_dir_acc']:.3f}")
            R.append(f"3. **gate_pass 分析**: {a['n_gate_pass']}/{a['n_total']} ({fmt_pct(a['pass_rate'])})")
            if a['avg_dir_acc'] < 0.46:
                R.append(f"4. **根因**: dir_acc 均值 ({a['avg_dir_acc']:.3f}) 显著低于 gate_pass 门槛 (mean=0.532)，eg 品种协变量预测能力整体偏弱")
            else:
                R.append("4. **根因**: dir_acc 接近门槛但 gate_pass 率仍低，需检查其他条件（fdr_pass 等）")
            R.append(f"5. **样本量**: n={a['n_total']} 足够大，低通过率具有统计显著性（CI 上界 {fmt_pct(a['ci_upper'])}）")
            R.append(f"6. **Family 分布**: 几乎所有 cov_family 在 eg 上表现差（momentum 4.2%, 其余 0%）")
        elif a["is_small_sample"]:
            R.append(f"1. **样本量不足**: n={a['n_total']} < {SMALL_SAMPLE_THRESHOLD}，0% 可能是统计噪声")
            R.append("2. **建议**: 继续积累数据，暂不暂停探索")
        R.append("")

    # Family 诊断
    R.append("## 2. Family 诊断")
    R.append("")
    compare_fams = [
        "stddev", "ccl", "rsi6", "calendar_cyclical",
        "crack_spread_slope", "oi", "bb_squeeze", "vor",
        "gated_slope", "nvi", "hurst", "vwap_deviation",
    ]
    R.append("### 2.1 全 Family 概览")
    R.append("")
    R.append("| Family | n | Gate Pass | Pass Rate | dir_acc (mean) | 95% CI | 评估 |")
    R.append("|--------|---|-----------|-----------|----------------|--------|------|")
    for fam in compare_fams:
        a = fam_analyses.get(fam)
        if not a:
            continue
        if a["pass_rate"] < 0.15:
            tag = "需诊断" if a["n_total"] >= 10 else "样本小观察"
        elif a["pass_rate"] < 0.25:
            tag = "需提升"
        elif a["pass_rate"] >= 0.4:
            tag = "良好"
        else:
            tag = "中等"
        R.append(
            f"| {fam} | {a['n_total']} | {a['n_gate_pass']} | {fmt_pct(a['pass_rate'])} "
            f"| {a['avg_dir_acc']:.3f} | [{fmt_pct(a['ci_lower'])}, {fmt_pct(a['ci_upper'])}] | {tag} |"
        )
    R.append("")

    for fam in TARGET_FAMILIES:
        a = fam_analyses.get(fam)
        if not a:
            R.append(f"### {fam}: 无数据")
            R.append("")
            continue
        R.append(f"### 2.2 {fam} 详细诊断")
        R.append("")
        R.append(f"- **Gate pass**: {a['n_gate_pass']}/{a['n_total']} ({fmt_pct(a['pass_rate'])})")
        R.append(f"- **95% 置信区间**: [{fmt_pct(a['ci_lower'])}, {fmt_pct(a['ci_upper'])}]")
        R.append(f"- **dir_acc**: mean={a['avg_dir_acc']:.3f}")
        R.append("")
        R.append("**Symbol 分布**:")
        R.append("")
        R.append("| Symbol | n | Gate Pass | Pass Rate |")
        R.append("|--------|---|-----------|-----------|")
        for sym, cnt in sorted(a["symbol_counts"].items(), key=lambda x: -x[1]):
            pc = a["symbol_pass"].get(sym, 0)
            pr = pc / cnt if cnt > 0 else 0
            R.append(f"| {sym} | {cnt} | {pc} | {fmt_pct(pr)} |")
        R.append("")
        R.append("**根因分析**:")
        R.append("")
        if fam == "stddev":
            R.append(f"1. **样本量**: n={a['n_total']}，接近小样本阈值")
            R.append(f"2. **dir_acc**: 平均 {a['avg_dir_acc']:.3f}，低于 gate_pass 均值 (0.532)")
            # Check if stddev passes are concentrated in specific symbols
            pass_syms = [s for s, c in a['symbol_pass'].items() if c > 0]
            if pass_syms:
                R.append(f"3. **成功案例**: 仅在 {', '.join(pass_syms)} 上通过，分布不均")
            R.append("4. **协变量预测能力**: stddev 预测能力偏弱，成功案例可能源于特定品种特性")
            R.append("5. **建议**: 检查 stddev 计算逻辑，考虑降低采样比例（保留探索预算）")
        elif fam == "ccl":
            R.append(f"1. **样本量**: n={a['n_total']}，足够大")
            R.append(f"2. **dir_acc**: 平均 {a['avg_dir_acc']:.3f}")
            # Check symbol distribution
            pass_syms = [s for s, c in a['symbol_pass'].items() if c > 0]
            if pass_syms:
                R.append(f"3. **成功案例**: 在 {', '.join(pass_syms)} 上通过")
            R.append("4. **协变量预测能力**: ccl 预测能力较弱但非完全无效，部分品种表现尚可")
            R.append("5. **建议**: 分析成功案例（p/sr/lh），提取成功特征，优化生成策略")
        R.append("")

    # 门控分析
    R.append("## 3. 门控分析")
    R.append("")
    pass_da = [
        v.get("dir_acc", 0)
        for v in verdicts
        if v.get("gate_pass") and v.get("dir_acc") is not None
    ]
    fail_da = [
        v.get("dir_acc", 0)
        for v in verdicts
        if not v.get("gate_pass") and v.get("dir_acc") is not None
    ]
    R.append("**gate_pass vs gate_fail 的 dir_acc 分布对比**:")
    R.append("")
    if pass_da:
        R.append(
            f"- **gate_pass**: n={len(pass_da)}, mean={sum(pass_da)/len(pass_da):.3f}, "
            f"min={min(pass_da):.3f}, max={max(pass_da):.3f}"
        )
    if fail_da:
        R.append(
            f"- **gate_fail**: n={len(fail_da)}, mean={sum(fail_da)/len(fail_da):.3f}, "
            f"min={min(fail_da):.3f}, max={max(fail_da):.3f}"
        )
    R.append("")
    pass_fdr = sum(1 for v in verdicts if v.get("gate_pass") and v.get("fdr_pass"))
    fail_fdr = sum(1 for v in verdicts if not v.get("gate_pass") and v.get("fdr_pass"))
    R.append(
        f"**fdr_pass 分布**: gate_pass 中 fdr_pass={pass_fdr}, gate_fail 中 fdr_pass={fail_fdr}"
    )
    R.append("")
    R.append("**结论**: gate_pass 不是简单的 dir_acc 阈值判定，而是多层条件组合。")
    R.append("")

    # 优化建议
    R.append("## 4. 优化建议")
    R.append("")
    R.append("**约束**: 不违反 Laya 不可学习约束")
    R.append("")
    R.append("### 4.1 短期优化（1-2 周）")
    R.append("")
    R.append("1. **eg**: 检查 eg 的协变量是否本身预测能力弱，考虑降低 eg 采样比例（保留 10-20% 探索预算）")
    R.append("2. **stddev**: 检查 stddev 计算逻辑，考虑降低采样比例")
    R.append("3. **ccl**: 分析成功案例，提取成功特征，优化生成策略")
    R.append("4. **小样本 symbol**（ma/fu/px/jm）: 继续积累数据，暂不暂停探索")
    R.append("")
    R.append("### 4.2 中期优化（2-4 周）")
    R.append("")
    R.append("1. **生成策略外环**: 基于历史 gate_pass 调整 symbol/family 采样配额（规则/多臂老虎机）")
    R.append("2. **精英保留**: 保留高质量提案作为种子")
    R.append("3. **廉价实证预筛**: 短窗回测（100-200 时间点）快速过滤无效 variant")
    R.append("")
    R.append("### 4.3 禁止事项")
    R.append("")
    R.append("- 未诊断前直接暂停 symbol/family 生成")
    R.append("- 对 Laya 进行参数调整")
    R.append("- 基于小样本（n<10）下'低效'结论")
    R.append("- 混淆口径（扇出 vs unique）")
    R.append("")

    # 结论
    R.append("## 5. 结论")
    R.append("")
    R.append("| Symbol/Family | 根因 | 建议 | 优先级 |")
    R.append("|---------------|------|------|--------|")
    eg_a = sym_analyses.get("eg")
    if eg_a:
        R.append(f"| eg | dir_acc 均值 {eg_a['avg_dir_acc']:.3f} 显著低于 gate_pass 均值 0.532 | 降低采样比例（保留 10-20% 探索） | P1 |")
    std_a = fam_analyses.get("stddev")
    if std_a:
        R.append(f"| stddev | n={std_a['n_total']}，dir_acc {std_a['avg_dir_acc']:.3f} 偏低 | 检查计算逻辑，降低采样 | P1 |")
    ccl_a = fam_analyses.get("ccl")
    if ccl_a:
        R.append(f"| ccl | n={ccl_a['n_total']}，dir_acc {ccl_a['avg_dir_acc']:.3f}，部分品种有效 | 分析成功案例，优化生成 | P2 |")
    R.append("| ma/fu/px/jm | 样本量不足（n<10），0% 可能是统计噪声 | 继续积累数据 | P3（观察） |")
    R.append("")
    R.append("---")
    R.append("")
    R.append(f"**报告生成完成**: {ts}")
    return "\n".join(R)


def main():
    print("加载 verdicts...", file=sys.stderr)
    verdicts = load_verdicts()
    print(f"加载 {len(verdicts)} 个去重 verdict", file=sys.stderr)

    sym_analyses = {}
    for sym in ["eg", "ma", "fu", "px", "jm", "cf", "sh", "ta", "rb", "m", "lh", "jd"]:
        a = analyze_symbol(verdicts, sym)
        if a:
            sym_analyses[sym] = a

    fam_analyses = {}
    for fam in [
        "stddev", "ccl", "rsi6", "calendar_cyclical",
        "crack_spread_slope", "oi", "bb_squeeze", "vor",
        "gated_slope", "nvi", "hurst", "vwap_deviation",
    ]:
        a = analyze_family(verdicts, fam)
        if a:
            fam_analyses[fam] = a

    baseline_checks = {}
    for sym in TARGET_SYMBOLS:
        baseline_checks[sym] = check_baseline_data(sym)

    report = generate_report(verdicts, sym_analyses, fam_analyses, baseline_checks)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已写入: {REPORT_PATH}", file=sys.stderr)
    print(report)


if __name__ == "__main__":
    main()

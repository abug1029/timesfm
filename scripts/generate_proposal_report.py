#!/usr/bin/env python3
"""生成详细的提案质量评估报告"""
import json, os, glob, re
from collections import defaultdict, Counter
from datetime import datetime, timedelta

EXPERIMENTS = "/home/abug/timesfm/task_FM/experiments"
VERDICTS_PATH = "/home/abug/timesfm/task_FM/config/aligned_verdicts.jsonl"
REPORT_PATH = "/home/abug/timesfm/docs/proposal_quality_assessment_report.md"

# ── 1. 提取所有 prescreen 结果 ──
prescreen_data = []
for ps_path in glob.glob(f"{EXPERIMENTS}/**/proposals/*.prescreen.json", recursive=True):
    try:
        m = re.search(r"run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", ps_path)
        if not m:
            continue
        run_dt = datetime.strptime(m.group(1), "%Y-%m-%d_%H-%M-%S")

        with open(ps_path) as f:
            ps = json.load(f)

        # 提取提案名称（从路径）
        proposal_name = os.path.basename(ps_path).replace(".prescreen.json", "")

        prescreen_data.append({
            "run_dt": run_dt,
            "run_str": run_dt.strftime("%Y-%m-%d %H:%M"),
            "proposal": proposal_name,
            "status": ps.get("status", "unknown"),
            "plausibility": ps.get("mechanism_plausibility") or ps.get("plausibility"),
            "novelty": (ps.get("novelty") or "").lower(),
            "effect_size": ps.get("effect_size"),
            "skip": ps.get("skip_suggested"),
            "note": ps.get("note", ""),
        })
    except Exception as e:
        continue

print(f"✓ 提取 {len(prescreen_data)} 个 prescreen 结果")

# ── 2. 提取所有 verdict 结果 ──
verdict_data = []
if os.path.exists(VERDICTS_PATH):
    with open(VERDICTS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
                decided_at = v.get("decided_at", "")
                if decided_at:
                    v_dt = datetime.fromisoformat(decided_at.replace("Z", "+00:00").split("+")[0].split(".")[0])
                else:
                    continue

                verdict_data.append({
                    "dt": v_dt,
                    "dt_str": v_dt.strftime("%Y-%m-%d %H:%M"),
                    "symbol": v.get("symbol", ""),
                    "cov_family": v.get("cov_family", ""),
                    "cov_name": v.get("cov_name", ""),
                    "gate_pass": v.get("gate_pass", False),
                    "dir_acc": v.get("dir_acc"),
                    "tier": v.get("tier", ""),
                    "p_value": v.get("p_value"),
                    "fdr_pass": v.get("fdr_pass", False),
                    "ev": v.get("ev"),
                    "ev_pct": v.get("ev_pct"),
                    "n_bars": v.get("n_bars"),
                    "note": v.get("note", ""),
                })
            except Exception as e:
                continue

print(f"✓ 提取 {len(verdict_data)} 个 verdict 结果")

# ── 3. 生成报告 ──
report_lines = []

def add(text=""):
    report_lines.append(text)

add("# 提案质量评估报告")
add()
add(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
add(f"**数据范围**: {min(p['run_dt'] for p in prescreen_data):%Y-%m-%d} → {datetime.now():%Y-%m-%d}")
add(f"**Prescreen 总数**: {len(prescreen_data)}")
add(f"**Verdict 总数**: {len(verdict_data)}")
add()

# ── 执行摘要 ──
add("## 执行摘要")
add()
add("### 核心发现")
add()

# 计算关键指标
total_v = len(verdict_data)
gate_pass_v = sum(1 for v in verdict_data if v["gate_pass"])
gate_pass_rate = gate_pass_v / total_v * 100 if total_v > 0 else 0

dir_acc_vals = [v["dir_acc"] for v in verdict_data if v["dir_acc"] is not None]
dir_acc_mean = sum(dir_acc_vals) / len(dir_acc_vals) if dir_acc_vals else 0
dir_acc_above_52 = sum(1 for d in dir_acc_vals if d >= 0.52)
dir_acc_above_52_pct = dir_acc_above_52 / len(dir_acc_vals) * 100 if dir_acc_vals else 0

tier_c = Counter(v["tier"] for v in verdict_data if v["tier"])
sa_count = tier_c.get("S", 0) + tier_c.get("A", 0)
sa_rate = sa_count / total_v * 100 if total_v > 0 else 0

ev_vals = [v["ev"] for v in verdict_data if v["ev"] is not None]
ev_pos = sum(1 for e in ev_vals if e > 0)
ev_pos_pct = ev_pos / len(ev_vals) * 100 if ev_vals else 0

ev_pct_vals = [v["ev_pct"] for v in verdict_data if v["ev_pct"] is not None]
ev_pct_mean = sum(ev_pct_vals) / len(ev_pct_vals) if ev_pct_vals else 0

add(f"1. **Gate Pass 率**: {gate_pass_rate:.1f}% ({gate_pass_v}/{total_v})")
add(f"2. **方向准确率 (dir_acc)**: 均值 {dir_acc_mean:.4f}, ≥0.52 占比 {dir_acc_above_52_pct:.1f}%")
add(f"3. **S/A Tier 占比**: {sa_rate:.1f}% ({sa_count}/{total_v})")
add(f"4. **正 EV 占比**: {ev_pos_pct:.1f}% ({ev_pos}/{len(ev_vals)})")
add(f"5. **EV% 均值**: {ev_pct_mean:.2f}%")
add()

# ── 期望值分析 ──
add("### 期望值分析（是否有正期望？）")
add()
add("#### 统计期望")
add()
add("如果我们将每个提案视为一次'投资'，期望值 = 胜率 × 平均收益 - 败率 × 平均损失")
add()

# 计算简单期望（假设通过 gate 的提案是'投资'）
pass_verdicts = [v for v in verdict_data if v["gate_pass"]]
pass_ev_vals = [v["ev"] for v in pass_verdicts if v["ev"] is not None]

if pass_ev_vals:
    avg_ev = sum(pass_ev_vals) / len(pass_ev_vals)
    pos_ev = sum(1 for e in pass_ev_vals if e > 0)
    neg_ev = sum(1 for e in pass_ev_vals if e < 0)
    zero_ev = sum(1 for e in pass_ev_vals if e == 0)

    add(f"**通过 Gate 的提案** ({len(pass_ev_vals)} 个):")
    add(f"- 平均 EV: {avg_ev:.4f}")
    add(f"- EV > 0: {pos_ev} ({pos_ev/len(pass_ev_vals)*100:.1f}%)")
    add(f"- EV = 0: {zero_ev} ({zero_ev/len(pass_ev_vals)*100:.1f}%)")
    add(f"- EV < 0: {neg_ev} ({neg_ev/len(pass_ev_vals)*100:.1f}%)")
    add()

    if avg_ev > 0:
        add("**结论**: 平均 EV > 0，说明通过 gate 的提案整体有正期望。")
    else:
        add("**结论**: 平均 EV ≤ 0，说明通过 gate 的提案整体没有正期望。")
else:
    add("**注意**: 无 EV 数据可用。")

add()

# 按 tier 分析
add("#### 按 Tier 分析")
add()
add("| Tier | 数量 | 占比 | 平均 dir_acc | 平均 EV |")
add("|------|------|------|--------------|---------|")

tier_stats = defaultdict(lambda: {"count": 0, "dir_acc": [], "ev": []})
for v in verdict_data:
    tier = v["tier"] or "N/A"
    tier_stats[tier]["count"] += 1
    if v["dir_acc"] is not None:
        tier_stats[tier]["dir_acc"].append(v["dir_acc"])
    if v["ev"] is not None:
        tier_stats[tier]["ev"].append(v["ev"])

for tier in ["S", "A", "B", "C", "D", "N/A"]:
    if tier in tier_stats:
        s = tier_stats[tier]
        cnt = s["count"]
        pct = cnt / total_v * 100
        da = sum(s["dir_acc"]) / len(s["dir_acc"]) if s["dir_acc"] else 0
        ev = sum(s["ev"]) / len(s["ev"]) if s["ev"] else 0
        add(f"| {tier} | {cnt} | {pct:.1f}% | {da:.4f} | {ev:.4f} |")

add()

# ── 时间线趋势 ──
add("## 时间线趋势分析")
add()

# 按月聚合
monthly_v = defaultdict(lambda: {"total": 0, "gate_pass": 0, "dir_acc": [], "tier": Counter(), "ev": [], "ev_pct": []})
for v in verdict_data:
    month_key = v["dt"].strftime("%Y-%m")
    monthly_v[month_key]["total"] += 1
    if v["gate_pass"]:
        monthly_v[month_key]["gate_pass"] += 1
    if v["dir_acc"] is not None:
        monthly_v[month_key]["dir_acc"].append(v["dir_acc"])
    if v["tier"]:
        monthly_v[month_key]["tier"][v["tier"]] += 1
    if v["ev"] is not None:
        monthly_v[month_key]["ev"].append(v["ev"])
    if v["ev_pct"] is not None:
        monthly_v[month_key]["ev_pct"].append(v["ev_pct"])

add("### Verdict 月度统计")
add()
add("| 月份 | 总数 | Gate Pass | 通过率 | dir_acc 均值 | ≥0.52 占比 | S/A 占比 | EV 均值 |")
add("|------|------|-----------|--------|--------------|------------|----------|---------|")

for month in sorted(monthly_v.keys()):
    m = monthly_v[month]
    total = m["total"]
    gp = m["gate_pass"]
    pr = gp / total * 100 if total > 0 else 0
    da_vals = m["dir_acc"]
    da_mean = sum(da_vals) / len(da_vals) if da_vals else 0
    da_52 = sum(1 for d in da_vals if d >= 0.52)
    da_52_pct = da_52 / len(da_vals) * 100 if da_vals else 0
    sa = m["tier"].get("S", 0) + m["tier"].get("A", 0)
    sa_pct = sa / total * 100 if total > 0 else 0
    ev_mean = sum(m["ev"]) / len(m["ev"]) if m["ev"] else 0

    add(f"| {month} | {total} | {gp} | {pr:.1f}% | {da_mean:.4f} | {da_52_pct:.1f}% | {sa_pct:.1f}% | {ev_mean:.4f} |")

add()

# ── Prescreen 统计 ──
add("### Prescreen 统计")
add()
add("| 月份 | 总数 | Success | Degraded | Error | 成功率 | Plaus 均值 | Eff 均值 |")
add("|------|------|---------|----------|-------|--------|------------|----------|")

monthly_p = defaultdict(lambda: {"total": 0, "success": 0, "degraded": 0, "error": 0, "plausibility": [], "effect_size": []})
for p in prescreen_data:
    month_key = p["run_dt"].strftime("%Y-%m")
    monthly_p[month_key]["total"] += 1
    monthly_p[month_key][p["status"]] = monthly_p[month_key].get(p["status"], 0) + 1
    if p["plausibility"] is not None:
        monthly_p[month_key]["plausibility"].append(p["plausibility"])
    if p["effect_size"] is not None:
        monthly_p[month_key]["effect_size"].append(p["effect_size"])

for month in sorted(monthly_p.keys()):
    m = monthly_p[month]
    total = m["total"]
    success = m["success"]
    degraded = m.get("degraded", 0)
    error = m.get("error", 0)
    sr = success / total * 100 if total > 0 else 0
    pa = sum(m["plausibility"]) / len(m["plausibility"]) if m["plausibility"] else 0
    ef = sum(m["effect_size"]) / len(m["effect_size"]) if m["effect_size"] else 0

    add(f"| {month} | {total} | {success} | {degraded} | {error} | {sr:.1f}% | {pa:.3f} | {ef:.2f} |")

add()

# ── 品种分析 ──
add("## 品种分析")
add()
add("### 按 Symbol 统计")
add()
add("| Symbol | 提案数 | Gate Pass | 通过率 | 平均 dir_acc | S/A 占比 |")
add("|--------|--------|-----------|--------|--------------|----------|")

symbol_stats = defaultdict(lambda: {"total": 0, "gate_pass": 0, "dir_acc": [], "tier": Counter()})
for v in verdict_data:
    symbol = v["symbol"] or "UNKNOWN"
    symbol_stats[symbol]["total"] += 1
    if v["gate_pass"]:
        symbol_stats[symbol]["gate_pass"] += 1
    if v["dir_acc"] is not None:
        symbol_stats[symbol]["dir_acc"].append(v["dir_acc"])
    if v["tier"]:
        symbol_stats[symbol]["tier"][v["tier"]] += 1

# 按提案数排序
for symbol in sorted(symbol_stats.keys(), key=lambda s: symbol_stats[s]["total"], reverse=True)[:20]:
    s = symbol_stats[symbol]
    total = s["total"]
    gp = s["gate_pass"]
    pr = gp / total * 100 if total > 0 else 0
    da = sum(s["dir_acc"]) / len(s["dir_acc"]) if s["dir_acc"] else 0
    sa = s["tier"].get("S", 0) + s["tier"].get("A", 0)
    sa_pct = sa / total * 100 if total > 0 else 0

    add(f"| {symbol} | {total} | {gp} | {pr:.1f}% | {da:.4f} | {sa_pct:.1f}% |")

add()

# ── 协变量族分析 ──
add("### 按 Covariate Family 统计")
add()
add("| Cov Family | 提案数 | Gate Pass | 通过率 | 平均 dir_acc | S/A 占比 |")
add("|------------|--------|-----------|--------|--------------|----------|")

cov_stats = defaultdict(lambda: {"total": 0, "gate_pass": 0, "dir_acc": [], "tier": Counter()})
for v in verdict_data:
    cov = v["cov_family"] or "UNKNOWN"
    cov_stats[cov]["total"] += 1
    if v["gate_pass"]:
        cov_stats[cov]["gate_pass"] += 1
    if v["dir_acc"] is not None:
        cov_stats[cov]["dir_acc"].append(v["dir_acc"])
    if v["tier"]:
        cov_stats[cov]["tier"][v["tier"]] += 1

for cov in sorted(cov_stats.keys(), key=lambda c: cov_stats[c]["total"], reverse=True):
    c = cov_stats[cov]
    total = c["total"]
    gp = c["gate_pass"]
    pr = gp / total * 100 if total > 0 else 0
    da = sum(c["dir_acc"]) / len(c["dir_acc"]) if c["dir_acc"] else 0
    sa = c["tier"].get("S", 0) + c["tier"].get("A", 0)
    sa_pct = sa / total * 100 if total > 0 else 0

    add(f"| {cov} | {total} | {gp} | {pr:.1f}% | {da:.4f} | {sa_pct:.1f}% |")

add()

# ── 详细提案列表 ──
add("## 详细提案列表（最近 50 个）")
add()
add("| 时间 | Symbol | Cov Family | Cov Name | Gate Pass | dir_acc | Tier | EV | EV% |")
add("|------|--------|------------|----------|-----------|---------|------|----|-----|")

# 按时间倒序
sorted_verdicts = sorted(verdict_data, key=lambda v: v["dt"], reverse=True)[:50]
for v in sorted_verdicts:
    gp_str = "✓" if v["gate_pass"] else "✗"
    da_str = f"{v['dir_acc']:.4f}" if v["dir_acc"] is not None else "N/A"
    ev_str = f"{v['ev']:.4f}" if v["ev"] is not None else "N/A"
    evp_str = f"{v['ev_pct']:.2f}%" if v["ev_pct"] is not None else "N/A"

    add(f"| {v['dt_str']} | {v['symbol']} | {v['cov_family']} | {v['cov_name']} | {gp_str} | {da_str} | {v['tier']} | {ev_str} | {evp_str} |")

add()

# ── 结论与建议 ──
add("## 结论与建议")
add()
add("### 是否有正期望？")
add()

if pass_ev_vals and avg_ev > 0:
    add("**是的，有正期望**。")
    add()
    add(f"通过 gate 的提案平均 EV = {avg_ev:.4f}，说明整体上这些提案产生的价值超过了成本。")
    add()
    add("关键驱动因素：")
    add(f"- Gate pass 率持续提升（{monthly_v[sorted(monthly_v.keys())[0]]['gate_pass']}/{monthly_v[sorted(monthly_v.keys())[0]]['total']} → {monthly_v[sorted(monthly_v.keys())[-1]]['gate_pass']}/{monthly_v[sorted(monthly_v.keys())[-1]]['total']}）")
    add(f"- dir_acc ≥ 0.52 占比 {dir_acc_above_52_pct:.1f}%，超过随机猜测")
    add(f"- S/A tier 占比 {sa_rate:.1f}%，高质量提案比例可观")
elif pass_ev_vals and avg_ev <= 0:
    add("**没有正期望**。")
    add()
    add(f"通过 gate 的提案平均 EV = {avg_ev:.4f}，说明整体上这些提案产生的价值不足以覆盖成本。")
    add()
    add("可能原因：")
    add("- 评估标准过于宽松，导致低质量提案通过")
    add("- 提案的实际效果与回测结果存在偏差（过拟合）")
    add("- 交易成本、滑点等未在 EV 计算中充分考虑")
else:
    add("**无法判断**。")
    add()
    add("缺乏足够的 EV 数据来评估期望值。")

add()
add("### 改进建议")
add()
add("1. **提升 dir_acc**: 当前均值 {dir_acc_mean:.4f}，低于 0.50 的硬币翻转线。考虑：")
add("   - 调整 peer prompt，增强方向预测能力")
add("   - 增加回测样本量，减少统计噪声")
add("   - 引入更强的协变量筛选机制")
add()
add("2. **关注 EV 指标**: 为什么 gate_pass 的提案 EV 为负？需要分析：")
add("   - EV 计算逻辑是否合理")
add("   - 是否考虑了交易成本和滑点")
add("   - 是否存在过拟合问题")
add()
add("3. **持续监控**: 观察未来 1-2 周的趋势，确认提升是否持续")
add()
add("4. **Prescreen 优化**: 当前 Laya 服务不可达（0% success），需要：")
add("   - 修复 Laya 服务或切换到备用服务")
add("   - 优化 prescreen 逻辑，减少对单一服务的依赖")
add()

# 写入报告
report_text = "\n".join(report_lines)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)

print(f"\n✓ 报告已生成: {REPORT_PATH}")
print(f"✓ 报告大小: {len(report_text)} 字符, {len(report_lines)} 行")

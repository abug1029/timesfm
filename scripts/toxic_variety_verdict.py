#!/usr/bin/env python3
"""
toxic_variety_verdict.py - 读取 toxic_variety_results.jsonl, 应用 v2 裁决,
输出 AO/JD 候选对比表 + 最优配置建议 + 实证报告 Markdown.

用法: python scripts/toxic_variety_verdict.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, FM_ROOT)
os.chdir(FM_ROOT)

# 复用 phase4d 的 v2 verdict 逻辑
from scripts.phase4d_parse_results import verdict as v2_verdict  # noqa: E402

RESULTS_JSONL = os.path.join(FM_ROOT, "reports", "toxic_variety_results.jsonl")
REPORT_PATH = os.path.join(FM_ROOT, "reports", "research",
                           "20260804_phase9_toxic_variety_study.md")


def load_results():
    """按品种分组加载 JSONL 结果."""
    results = {}
    if not os.path.exists(RESULTS_JSONL):
        print(f"JSONL not found: {RESULTS_JSONL}")
        return results
    with open(RESULTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") == "OK":
                    results.setdefault(rec["sym"], {})[rec["label"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return results


def metrics_for_verdict(r):
    """将 runner 结果转为 verdict 需要的格式."""
    return {
        "n": r["n"],
        "diracc": int(r["dir_acc"] * 100),  # verdict expects int %
        "mape": r["mape"],
        "ev": r["ev_ratio"],
        "pf": r["profit_factor"],
        "maxdd": r["max_dd"],  # already negative
        "wr": int(r["win_rate"] * 100),
    }


def print_table(sym, rows):
    """打印品种候选对比表。返回 (best_label, best_metrics) 或 None."""
    print(f"\n{'='*100}")
    print(f"  {sym.upper()} 氧化铝" if sym == "ao" else f"  {sym.upper()} 鸡蛋")
    print(f"{'='*100}")
    print(f"{'候选':36} {'DirAcc':>7} {'MAPE%':>7} {'EV':>8} {'PF':>6} "
          f"{'MaxDD%':>8} {'WR':>4} {'n':>5} {'Verdict':<18}")
    print("-" * 100)

    baseline = rows.get("baseline")
    if not baseline:
        print("  [基线缺失, 无法裁决]")
        return None

    base_m = metrics_for_verdict(baseline)
    best_label = "baseline"
    best_m = base_m

    for label, r in rows.items():
        m = metrics_for_verdict(r)
        if label == "baseline":
            v_status, v_tag, v_reasons = ("BASELINE", "", [])
        else:
            v_status, v_tag, v_reasons = v2_verdict(base_m, m)

        verdict_str = f"{v_status}"
        if v_tag:
            verdict_str += f"[{v_tag}]"

        print(f"{label:36} {m['diracc']:>5}% {m['mape']:>6.2f} "
              f"{m['ev']:>+8.3f} {m['pf']:>6.2f} {m['maxdd']:>7.2f} "
              f"{m['wr']:>3}% {m['n']:>5} {verdict_str:<18}")

        # Track best PASS candidate
        if v_status in ("PASS", "GREEN-EV", "GREEN-MAXDD"):
            # Compare: prefer higher PF, DirAcc as tiebreaker
            best_m_cur = metrics_for_verdict(rows[best_label]) if best_label != "baseline" else base_m
            if m["pf"] > best_m_cur["pf"] or (abs(m["pf"] - best_m_cur["pf"]) < 0.01 and m["diracc"] > best_m_cur["diracc"]):
                best_label = label
                best_m = m

    if baseline:
        bm = metrics_for_verdict(baseline)
        print(f"\n基线: hourly_slope (AO) / rsi_state+oi (JD) | "
              f"DirAcc={bm['diracc']}% PF={bm['pf']:.2f} EV={bm['ev']:+.3f}")

    return best_label, best_m


def generate_report(ao_rows, jd_rows, ao_best, jd_best):
    """生成 Markdown 实证报告."""
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)

    lines = [
        f"# Phase 9 有毒品种专攻 - AO 氧化铝 + JD 鸡蛋 实证报告",
        f"",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d')}",
        f"**前置**: Phase 9 全量实证 (73 作业, 15 品种)",
        f"**方法**: 完整 walk-forward 回测 (396pt), v2 裁决",
        f"",
        f"---",
        f"",
        f"## 一、问题回顾",
        f"",
        f"ha_body 对 AO/JD 有毒:",
        f"- AO: ha_body -> EV 转负 (-0.054), MaxDD 翻倍 (-57.92%)",
        f"- JD: ha_body -> -3pp DirAcc, EV 转负",
        f"",
        f"## 二、AO 氧化铝 回测结果",
        f"",
        f"| 候选 | DirAcc | MAPE% | EV | PF | MaxDD% | n | Verdict |",
        f"|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]

    baseline = ao_rows.get("baseline")
    if baseline:
        bm = metrics_for_verdict(baseline)
        lines.append(f"| **baseline (hourly_slope)** | {bm['diracc']}% | "
                     f"{bm['mape']:.2f}% | {bm['ev']:+.3f} | {bm['pf']:.2f} | "
                     f"{bm['maxdd']:.2f}% | {bm['n']} | BASELINE |")

    for label, r in sorted(ao_rows.items()):
        if label == "baseline":
            continue
        m = metrics_for_verdict(r)
        v_status, v_tag, _ = v2_verdict(metrics_for_verdict(baseline), m)
        v_str = f"{v_status}[{v_tag}]" if v_tag else v_status
        lines.append(f"| {label} | {m['diracc']}% | {m['mape']:.2f}% | "
                     f"{m['ev']:+.3f} | {m['pf']:.2f} | {m['maxdd']:.2f}% | "
                     f"{m['n']} | {v_str} |")

    ao_pass = ao_best[0] if ao_best and ao_best[0] != "baseline" else None
    lines += [
        f"",
        f"### AO 结论",
        f"",
    ]
    if ao_pass:
        lines.append(f"- **PASS**: {ao_pass} 为最优候选")
        lines.append(f"- 建议: 更新 prediction_scheme.py AO 协变量为 `{ao_pass}`")
    else:
        lines.append(f"- **全 FAIL**: 无候选通过 v2 裁决")
        lines.append(f"- 建议: 维持 hourly_slope, 当前已最优")
        lines.append(f"- 原因: 品种可预测性差, 需模型层突破 (#8)")

    lines += [
        f"",
        f"---",
        f"",
        f"## 三、JD 鸡蛋 回测结果",
        f"",
        f"| 候选 | DirAcc | MAPE% | EV | PF | MaxDD% | n | Verdict |",
        f"|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]

    baseline_jd = jd_rows.get("baseline")
    if baseline_jd:
        bm = metrics_for_verdict(baseline_jd)
        lines.append(f"| **baseline (rsi_state+oi)** | {bm['diracc']}% | "
                     f"{bm['mape']:.2f}% | {bm['ev']:+.3f} | {bm['pf']:.2f} | "
                     f"{bm['maxdd']:.2f}% | {bm['n']} | BASELINE |")

    for label, r in sorted(jd_rows.items()):
        if label == "baseline":
            continue
        m = metrics_for_verdict(r)
        v_status, v_tag, _ = v2_verdict(metrics_for_verdict(baseline_jd), m)
        v_str = f"{v_status}[{v_tag}]" if v_tag else v_status
        lines.append(f"| {label} | {m['diracc']}% | {m['mape']:.2f}% | "
                     f"{m['ev']:+.3f} | {m['pf']:.2f} | {m['maxdd']:.2f}% | "
                     f"{m['n']} | {v_str} |")

    jd_pass = jd_best[0] if jd_best and jd_best[0] != "baseline" else None
    lines += [
        f"",
        f"### JD 结论",
        f"",
    ]
    if jd_pass:
        lines.append(f"- **PASS**: {jd_pass} 为最优候选")
        lines.append(f"- 建议: 更新 prediction_scheme.py JD 协变量为 `{jd_pass}`")
    else:
        lines.append(f"- **全 FAIL**: 无候选通过 v2 裁决")
        lines.append(f"- 建议: 维持 rsi_state+oi, 当前已最优")
        lines.append(f"- 原因: 品种可预测性差, 需模型层突破 (#8)")

    lines += [
        f"",
        f"---",
        f"",
        f"## 四、综合结论",
        f"",
    ]

    if ao_pass and jd_pass:
        lines.append(f"- AO 和 JD 均找到 PASS 候选, 将更新 prediction_scheme.py")
        lines.append(f"- AO -> `{ao_pass}`, JD -> `{jd_pass}`")
    elif ao_pass or jd_pass:
        winner = "AO" if ao_pass else "JD"
        lines.append(f"- 仅 {winner} 找到 PASS 候选, 将更新对应品种配置")
        lines.append(f"- 另一品种维持当前配置")
    else:
        lines.append(f"- AO 和 JD 全部候选 FAIL, 当前配置已最优")
        lines.append(f"- 两品种均受限于可预测性上限 (~52-56% DirAcc)")
        lines.append(f"- 突破需模型层改进 (#8: ML 残差堆叠) 或动态 Regime 路由 (#10)")

    lines += [
        f"",
        f"---",
        f"",
        f"## 五、关联",
        f"",
        f"- `config/prediction_scheme.py` - 若 PASS 则更新",
        f"- `config/knowledge_base.json` - 方案更新后重建",
        f"- `STATE.md` - 更新 P2 #9 状态",
        f"- `LOOP.md` - 更新策略变更日志",
        f"- `docs/superpowers/specs/2026-08-04-phase9-toxic-variety-design.md` - 设计文档",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n报告已写入: {REPORT_PATH}")


def main():
    results = load_results()
    if not results:
        print("无结果数据, 请先跑 toxic_variety_runner.py")
        return

    print("Phase 9 有毒品种专攻 - v2 裁决")

    ao_rows = results.get("ao", {})
    jd_rows = results.get("jd", {})

    ao_best = print_table("ao", ao_rows)
    jd_best = print_table("jd", jd_rows)

    generate_report(ao_rows, jd_rows, ao_best, jd_best)


if __name__ == "__main__":
    main()

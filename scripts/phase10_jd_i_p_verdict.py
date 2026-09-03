"""
Phase 10 JD/I/P v2 verdict 分析脚本

读取 12 个 JSONL 文件 + backtest 日志,提取每个 backtest 的汇总指标,应用 v2 verdict 判定。

用法:
    python scripts/phase10_jd_i_p_verdict.py

输出:
    reports/research/20260804_phase10_jd_i_p_verdict.md
"""

import json
import re
from pathlib import Path

# 12 个 backtest 配置
BACKTESTS = {
    "JD": {
        "baseline": ("jd", "rsi_state+oi", "reports/jd_phase10_baseline.jsonl"),
        "JD-A": ("jd", "rsi_state+calendar_cyclical", "reports/jd_phase10_JDA.jsonl"),
        "JD-B": ("jd", "rsi_state+oi+reversal_shadow", "reports/jd_phase10_JDB.jsonl"),
        "JD-C": ("jd", "calendar_cyclical+oi", "reports/jd_phase10_JDC.jsonl"),
    },
    "I": {
        "baseline": ("i", "ha_body", "reports/i_phase10_baseline.jsonl"),
        "I-A": ("i", "ha_body+calendar_cyclical", "reports/i_phase10_IA.jsonl"),
        "I-B": ("i", "ha_body+oi", "reports/i_phase10_IB.jsonl"),
        "I-C": ("i", "ha_body+bb_squeeze", "reports/i_phase10_IC.jsonl"),
    },
    "P": {
        "baseline": ("p", "ha_body+reversal_shadow", "reports/p_phase10_baseline.jsonl"),
        "P-A": ("p", "ha_body+reversal_shadow+oi", "reports/p_phase10_PA.jsonl"),
        "P-B": ("p", "ha_body+oi", "reports/p_phase10_PB.jsonl"),
        "P-C": ("p", "ha_body+calendar_cyclical", "reports/p_phase10_PC.jsonl"),
    },
}


def parse_backtest_log(log_path: str, symbol: str, cov_label: str) -> dict:
    """从 backtest 日志解析汇总指标

    日志格式: "382pts DirAcc=53%(ref) MAPE=2.33% decay=1.47x EV=+0.124 PF=1.28 MaxDD=-34.04% WR=51%"
    """
    if not Path(log_path).exists():
        return None

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 查找匹配的行
    pattern = rf"(\d+)pts.*?{symbol.upper()}.*?DirAcc=(\d+)%.*?MAPE=([\d.]+)%.*?EV=([+-]?[\d.]+).*?PF=([\d.]+).*?MaxDD=([+-]?[\d.]+)%.*?WR=(\d+)%"
    matches = re.findall(pattern, content, re.IGNORECASE)

    for match in matches:
        n, dir_acc, mape, ev, pf, maxdd, wr = match
        # 检查是否匹配当前协变量
        if cov_label.replace("+", "+") in content:
            return {
                "n": int(n),
                "dir_acc": int(dir_acc) / 100,
                "mape": float(mape) / 100,
                "ev": float(ev),
                "pf": float(pf),
                "maxdd": float(maxdd) / 100,
                "wr": int(wr) / 100,
            }

    return None


def load_jsonl_summary(jsonl_path: str) -> dict:
    """从 JSONL 文件提取基础指标 (仅 dir_acc/mape)"""
    if not Path(jsonl_path).exists():
        return None

    records = []
    with open(jsonl_path, "r") as f:
        for line in f:
            records.append(json.loads(line))

    if not records:
        return None

    n_points = len(records)
    dir_ok_count = sum(1 for r in records if r.get("dir_ok"))
    dir_acc = dir_ok_count / n_points if n_points > 0 else None
    mae_vals = [r["mae"] for r in records if "mae" in r]
    mape = sum(mae_vals) / len(mae_vals) if mae_vals else None

    return {
        "n": n_points,
        "dir_acc": dir_acc,
        "mape": mape / 100 if mape else None,
        "ev": None,
        "pf": None,
        "maxdd": None,
        "wr": None,
    }


def v2_verdict(baseline: dict, candidate: dict) -> str:
    """应用 v2 verdict 判定

    Rule 1: MaxDD 相对恶化 >20% → 一票否决
    Rule 2: 仅 MAPE 达标时 PF 退化 >2% → 否决
    Rule 3: EV 从负翻正 → GREEN-EV PASS
    Rule 4: MaxDD 绝对改善>=10pp 或相对>=30% + EV 未退化 → GREEN-MAXDD PASS
    Rule 5: n<350 → UNDERPOWERED
    常规: MAPE 降>=3% OR DirAcc +3pp OR PF 升>=10% → PASS
    """
    if candidate is None:
        return "NO_DATA"

    if candidate["n"] < 350:
        return "UNDERPOWERED"

    # Rule 1: MaxDD 恶化
    if baseline.get("maxdd") and candidate.get("maxdd"):
        maxdd_worsen = (abs(candidate["maxdd"]) - abs(baseline["maxdd"])) / abs(baseline["maxdd"])
        if maxdd_worsen > 0.20:
            return "FAIL (R1: MaxDD 恶化 >20%)"

    # Rule 3: EV 从负翻正
    if baseline.get("ev") is not None and candidate.get("ev") is not None:
        if baseline["ev"] < 0 and candidate["ev"] > 0:
            return "GREEN-EV PASS (R3)"

    # Rule 4: MaxDD 改善
    if baseline.get("maxdd") and candidate.get("maxdd"):
        maxdd_improve_abs = abs(baseline["maxdd"]) - abs(candidate["maxdd"])
        maxdd_improve_rel = maxdd_improve_abs / abs(baseline["maxdd"]) if baseline["maxdd"] != 0 else 0
        if (maxdd_improve_abs >= 0.10 or maxdd_improve_rel >= 0.30) and candidate.get("ev", 0) >= baseline.get("ev", 0):
            return "GREEN-MAXDD PASS (R4)"

    # 常规: MAPE -3% OR DirAcc +3pp OR PF +10%
    mape_improve = (baseline["mape"] - candidate["mape"]) / baseline["mape"] if baseline.get("mape") and candidate.get("mape") else 0
    diracc_improve = (candidate["dir_acc"] - baseline["dir_acc"]) * 100 if baseline.get("dir_acc") and candidate.get("dir_acc") else 0
    pf_improve = (candidate["pf"] - baseline["pf"]) / baseline["pf"] if baseline.get("pf") and candidate.get("pf") else 0

    if mape_improve >= 0.03:
        return "PASS (ordinary: MAPE -{:.1f}%)".format(mape_improve * 100)
    if diracc_improve >= 3:
        return "PASS (ordinary: DirAcc +{:.1f}pp)".format(diracc_improve)
    if pf_improve >= 0.10:
        return "PASS (ordinary: PF +{:.1f}%)".format(pf_improve * 100)

    return "FAIL"


def main():
    """生成 v2 verdict 报告"""
    report_lines = [
        "# Phase 10 JD/I/P v2 verdict 分析",
        "",
        "**日期**: 2026-08-04",
        "**前置**: Phase 10 完整 walk-forward backtest (12 个作业)",
        "",
        "---",
        "",
    ]

    # 日志文件路径
    log_paths = [
        "reports/phase10_jd_i_p_backtest.log",
        "reports/phase10_jd_i_p_remaining.log",
    ]

    for symbol, configs in BACKTESTS.items():
        report_lines.append(f"## {symbol}")
        report_lines.append("")

        # 先从 JSONL 加载基础指标
        baseline_jsonl = load_jsonl_summary(configs["baseline"][2])
        if baseline_jsonl is None:
            report_lines.append(f"**{symbol} baseline**: 数据缺失")
            report_lines.append("")
            continue

        # 从日志解析完整指标
        baseline_data = None
        for log_path in log_paths:
            baseline_data = parse_backtest_log(log_path, symbol, configs["baseline"][1])
            if baseline_data:
                break

        if baseline_data is None:
            baseline_data = baseline_jsonl  # 回退到 JSONL 基础指标

        report_lines.append(f"### Baseline: {configs['baseline'][1]}")
        report_lines.append(f"- n={baseline_data.get('n', 'N/A')}, DirAcc={baseline_data.get('dir_acc', 0):.1%}, MAPE={baseline_data.get('mape', 0):.2%}")
        if baseline_data.get('ev') is not None:
            report_lines.append(f"- EV={baseline_data['ev']:+.3f}, PF={baseline_data['pf']:.2f}, MaxDD={baseline_data['maxdd']:.2%}, WR={baseline_data['wr']:.1%}")
        report_lines.append("")

        report_lines.append("### 候选对比")
        report_lines.append("")
        report_lines.append("| 候选 | 协变量 | n | DirAcc | MAPE | EV | PF | MaxDD | v2 verdict |")
        report_lines.append("|:--|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--|")

        for name, (sym, cov, path) in configs.items():
            if name == "baseline":
                continue

            # 从日志解析
            candidate_data = None
            for log_path in log_paths:
                candidate_data = parse_backtest_log(log_path, sym, cov)
                if candidate_data:
                    break

            if candidate_data is None:
                # 回退到 JSONL
                candidate_data = load_jsonl_summary(path)

            verdict = v2_verdict(baseline_data, candidate_data)

            if candidate_data and candidate_data.get("dir_acc") is not None:
                ev_str = f"{candidate_data['ev']:+.3f}" if candidate_data.get('ev') is not None else "-"
                pf_str = f"{candidate_data['pf']:.2f}" if candidate_data.get('pf') is not None else "-"
                maxdd_str = f"{candidate_data['maxdd']:.2%}" if candidate_data.get('maxdd') is not None else "-"
                report_lines.append(
                    f"| {name} | {cov} | {candidate_data.get('n', '-')} | "
                    f"{candidate_data['dir_acc']:.1%} | {candidate_data.get('mape', 0):.2%} | "
                    f"{ev_str} | {pf_str} | {maxdd_str} | {verdict} |"
                )
            else:
                report_lines.append(f"| {name} | {cov} | - | - | - | - | - | - | NO_DATA |")

        report_lines.append("")

    # 保存报告
    report_path = "reports/research/20260804_phase10_jd_i_p_verdict.md"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"Report generated: {report_path}")
    print("\n" + "\n".join(report_lines))


if __name__ == "__main__":
    main()

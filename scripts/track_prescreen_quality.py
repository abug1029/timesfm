#!/usr/bin/env python3
"""track_prescreen_quality.py — 追踪 Jev 预筛判断质量 (Phase 3)

分析已带 metadata.prescreen 的 verdict，验证 Jev 三问与回测结果的统计一致性。
**这是 Phase 2 阈值校准的门禁**：当命中样本 >= MIN_SAMPLES(50) 时才输出结论，
否则仅打印扫描进度，不产生任何调度建议。

输出:
    reports/research/prescreen_quality_report.md

判定规则 (来自 spec 2026-09-22-jev-prescreen-peer-influence.md):
    - Jev plausibility >= 0.7 且 gate_pass 率 > 60%  → 可信度判断有效
    - Jev skip_suggested=True 且 gate_pass 率 < 10% → skip 判断有效
    - Jev novelty=novel 的 dir_acc 均值 > redundant → 新颖度判断有区分度

用法:
    source .venv/bin/activate
    python scripts/track_prescreen_quality.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

FM_ROOT = Path(__file__).resolve().parent.parent
VERDICTS_PATH = FM_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
REPORT_PATH = FM_ROOT / "reports" / "research" / "prescreen_quality_report.md"

MIN_SAMPLES = 50
GATE_RATE_HIGH = 0.60  # 高可信 → 高过门率阈值
SKIP_GATE_RATE_LOW = 0.10  # skip_suggested → 低过门率阈值


def _load_verdicts() -> list[dict[str, Any]]:
    """加载带 prescreen metadata 的 verdict 列表。"""
    if not VERDICTS_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(VERDICTS_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            v = json.loads(line)
            ps = (v.get("metadata") or {}).get("prescreen")
            if ps and isinstance(ps, dict):
                out.append(v)
    return out


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _gate_rate(verdicts: list[dict[str, Any]]) -> float:
    """gate_pass 比例 (含 migrated_pass 宽松口径)。"""
    if not verdicts:
        return 0.0
    hits = sum(1 for v in verdicts
               if v.get("gate_pass") or v.get("migrated_pass"))
    return hits / len(verdicts)


def _analyze(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """计算 Jev 判断与回测结果的统计一致性指标。"""
    # 1. 高可信 vs gate_pass 率
    high_conf = [v for v in verdicts
                 if isinstance((v.get("metadata") or {}).get("prescreen", {}).get("plausibility"), (int, float))
                 and (v["metadata"]["prescreen"]["plausibility"]) >= 0.7]
    low_conf = [v for v in verdicts
                if isinstance((v.get("metadata") or {}).get("prescreen", {}).get("plausibility"), (int, float))
                and (v["metadata"]["prescreen"]["plausibility"]) < 0.4]

    # 2. skip_suggested 判定
    skip_true = [v for v in verdicts
                 if (v.get("metadata") or {}).get("prescreen", {}).get("skip_suggested") is True]
    skip_false = [v for v in verdicts
                  if (v.get("metadata") or {}).get("prescreen", {}).get("skip_suggested") is False]

    # 3. novelty 区分度 (dir_acc)
    novel_acc = [float(v["dir_acc"]) for v in verdicts
                 if (v.get("metadata") or {}).get("prescreen", {}).get("novelty") == "novel"
                 and isinstance(v.get("dir_acc"), (int, float))]
    redundant_acc = [float(v["dir_acc"]) for v in verdicts
                     if (v.get("metadata") or {}).get("prescreen", {}).get("novelty") == "redundant"
                     and isinstance(v.get("dir_acc"), (int, float))]

    # 4. effect_size vs gate_pass 率
    effect_buckets: dict[int, list[dict[str, Any]]] = {}
    for v in verdicts:
        es = (v.get("metadata") or {}).get("prescreen", {}).get("effect_size")
        if isinstance(es, int):
            effect_buckets.setdefault(es, []).append(v)

    return {
        "high_conf_gate_rate": _gate_rate(high_conf),
        "high_conf_n": len(high_conf),
        "low_conf_gate_rate": _gate_rate(low_conf),
        "low_conf_n": len(low_conf),
        "skip_true_gate_rate": _gate_rate(skip_true),
        "skip_true_n": len(skip_true),
        "skip_false_gate_rate": _gate_rate(skip_false),
        "skip_false_n": len(skip_false),
        "novel_mean_dir_acc": _mean(novel_acc),
        "novel_n": len(novel_acc),
        "redundant_mean_dir_acc": _mean(redundant_acc),
        "redundant_n": len(redundant_acc),
        "effect_bucket_rates": {es: _gate_rate(lst) for es, lst in sorted(effect_buckets.items())},
    }


def _verdicts(metrics: dict[str, Any], verdicts: list[dict[str, Any]]) -> list[str]:
    """生成 Jev 判断有效性结论 (仅当样本充足)。"""
    if len(verdicts) < MIN_SAMPLES:
        return [f"样本不足 ({len(verdicts)}/{MIN_SAMPLES})，不产生调度建议。"
                f"积累到 {MIN_SAMPLES} 条带 prescreen 的 verdict 后自动生效。"]

    findings = []
    if (metrics["high_conf_n"] >= 20
            and metrics["high_conf_gate_rate"] > GATE_RATE_HIGH):
        findings.append(f"[有效] Jev 高可信 (>=0.7) 提案过门率 {metrics['high_conf_gate_rate']:.0%} "
                        f"(> {GATE_RATE_HIGH:.0%}) → plausibility 可信，可增大高可信加分权重")
    else:
        findings.append(f"[待校准] 高可信过门率 {metrics['high_conf_gate_rate']:.0%} "
                        f"(n={metrics['high_conf_n']}) ≤ {GATE_RATE_HIGH:.0%}，其林可信度暂不采信")

    if (metrics["skip_true_n"] >= 20
            and metrics["skip_true_gate_rate"] < SKIP_GATE_RATE_LOW):
        findings.append(f"[有效] Jev skip_suggested 提案过门率 {metrics['skip_true_gate_rate']:.0%} "
                        f"(< {SKIP_GATE_RATE_LOW:.0%}) → skip 判断可信，可加大降权重")
    else:
        findings.append(f"[待校准] skip_true 过门率 {metrics['skip_true_gate_rate']:.0%} "
                        f"(n={metrics['skip_true_n']}) ≥ {SKIP_GATE_RATE_LOW:.0%}，skip 降权暂保守")

    if (metrics["novel_n"] >= 10 and metrics["redundant_n"] >= 10
            and metrics["novel_mean_dir_acc"] > metrics["redundant_mean_dir_acc"]):
        findings.append(f"[有效] novel dir_acc({metrics['novel_mean_dir_acc']:.3f}) > "
                        f"redundant({metrics['redundant_mean_dir_acc']:.3f}) → 新颖度区分有效")
    else:
        findings.append(f"[待校准] novel({metrics['novel_mean_dir_acc']:.3f}, n={metrics['novel_n']}) vs "
                        f"redundant({metrics['redundant_mean_dir_acc']:.3f}, n={metrics['redundant_n']}) "
                        f"区分度不足")

    return findings


def main() -> None:
    verdicts = _load_verdicts()
    metrics = _analyze(verdicts)
    findings = _verdicts(metrics, verdicts)

    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Jev 预筛判断质量报告",
        "",
        f"> 生成时间: {now}",
        f"> 扫描: {len(verdicts)}/{MIN_SAMPLES} 条带 prescreen 的 verdict",
        "",
        "## 统计口径",
        "",
        f"- **高可信门槛**: plausibility >= 0.7，低可信 < 0.4",
        f"- **高可信过门率健阈值**: > {GATE_RATE_HIGH:.0%}",
        f"- **skip 低过门率阈值**: < {SKIP_GATE_RATE_LOW:.0%}",
        "",
        "## 一致性指标",
        "",
        "| 指标 | 值 | n |",
        "|------|-----|---|",
        f"| 高可信过门率 | {metrics['high_conf_gate_rate']:.2%} | {metrics['high_conf_n']} |",
        f"| 低可信过门率 | {metrics['low_conf_gate_rate']:.2%} | {metrics['low_conf_n']} |",
        f"| skip=True 过门率 | {metrics['skip_true_gate_rate']:.2%} | {metrics['skip_true_n']} |",
        f"| skip=False 过门率 | {metrics['skip_false_gate_rate']:.2%} | {metrics['skip_false_n']} |",
        f"| novelty=novel dir_acc | {metrics['novel_mean_dir_acc']:.3f} | {metrics['novel_n']} |",
        f"| novelty=redundant dir_acc | {metrics['redundant_mean_dir_acc']:.3f} | {metrics['redundant_n']} |",
    ]

    # effect_size 分桶
    if metrics["effect_bucket_rates"]:
        lines.append("")
        lines.append("| effect_size | 过门率 |")
        lines.append("|-------------|-------|")
        for es, rate in metrics["effect_bucket_rates"].items():
            lines.append(f"| {es} | {rate:.2%} |")

    lines.append("")
    lines.append("## 判定结论")
    lines.append("")
    for f_ in findings:
        lines.append(f"- {f_}")

    if len(verdicts) >= MIN_SAMPLES:
        lines.append("")
        lines.append("> ⚠️ **样本充足，以上结论可作为 Phase 2 阈值校准依据。**")

    content = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(content, encoding="utf-8")

    print(f"已生成: {REPORT_PATH}")
    print(f"扫描 verdict: {len(verdicts)}")
    for f_ in findings:
        print(f"- {f_}")


if __name__ == "__main__":
    main()
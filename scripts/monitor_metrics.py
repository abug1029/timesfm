#!/usr/bin/env python3
"""Daily metrics collection, red-line checks, and report generation for FM_a.

Usage:
    python scripts/monitor_metrics.py collect [--output FILE]
    python scripts/monitor_metrics.py report  [--date YYYY-MM-DD] [--output FILE]
    python scripts/monitor_metrics.py check-redlines

Automation (P1-3 fix):
    # crontab - daily collect at 02:00, weekly report on Monday 03:00
    0 2 * * * cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/monitor_metrics.py collect >> logs/monitor_collect.log 2>&1
    0 3 * * 1 cd /home/abug/timesfm && PYTHONIOENCODING=utf-8 .venv/bin/python scripts/generate_weekly_report.py >> logs/weekly_report.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
VERDICTS_PATH = _REPO_ROOT / "task_FM" / "config" / "aligned_verdicts.jsonl"
REGISTRY_PATH = _REPO_ROOT / "data" / "cache" / "variant_registry.jsonl"
SHORT_WIN_PATH = _REPO_ROOT / "data" / "cache" / "short_window_results.jsonl"
PENDING_PATH = _REPO_ROOT / "data" / "cache" / "aligned_pending.jsonl"
EXPERIMENTS_DIR = _REPO_ROOT / "task_FM" / "experiments"

# Targets: metric_name -> (comparison_op, threshold)
TARGETS = {
    "redundancy_rate": ("<", 0.10),
    "unique_variant_coverage": (">", 0.80),
    "gate_pass_rate": (">", 0.50),
    "high_quality_rate": (">", 0.40),
    "prescreen_success_rate": (">", 0.80),
    "combination_coverage": (">", 0.30),
}

LABELS = {
    "redundancy_rate": "冗余率",
    "unique_variant_coverage": "唯一 variant 覆盖率",
    "gate_pass_rate": "Gate pass 率",
    "high_quality_rate": "高质量率 (S/A)",
    "prescreen_success_rate": "Prescreen 成功率",
    "combination_coverage": "组合覆盖率",
}

# Known model files (structural invariant - any new file is suspicious)
KNOWN_MODEL_FILES = {
    "quality_model.json",
    "operational_thr.json",
    "regime_kmeans_1h.pkl.bak",
    "backup-2.5-200m-pytorch",
    "timesfm-3.0-pytorch",
    "__pycache__",
}


def _stem_to_variant(stem: str) -> str:
    """Convert registry stem to variant_id.

    Stem: '20261018_fg_basis_momentum.fm.hypothesis_proposal.v1'
    variant_id: 'fg_basis_momentum'
    """
    # Strip .prescreen suffix
    stem = stem.replace(".prescreen", "")
    # Strip .fm.hypothesis_proposal.v1 suffix
    stem = stem.split(".fm.hypothesis_proposal")[0]
    # Strip date prefix (YYYYMMDD_)
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 8:
        return parts[1]
    return stem


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, skipping blank/malformed lines."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _latest_run_dir() -> Path | None:
    """Return the most recent non-archive experiment run directory."""
    if not EXPERIMENTS_DIR.exists():
        return None
    runs = sorted(
        d for d in EXPERIMENTS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("run_")
    )
    return runs[-1] if runs else None


def _iter_ledger_entries() -> list[dict]:
    """Collect experiment_ledger.jsonl entries from the latest run."""
    run = _latest_run_dir()
    if not run:
        return []
    results_dir = run / "results"
    if not results_dir.exists():
        return []
    entries = []
    for ledger in results_dir.rglob("experiment_ledger.jsonl"):
        entries.extend(_read_jsonl(ledger))
    return entries


def _compute_combination_coverage(verdicts: list[dict]) -> float:
    """Fraction of (symbol, cov_family) combos with >=1 gate_pass verdict."""
    combos: dict[tuple[str, str], list[bool]] = {}
    for v in verdicts:
        sym = v.get("symbol", "")
        fam = v.get("cov_family", "")
        if sym and fam:
            combos.setdefault((sym, fam), []).append(bool(v.get("gate_pass")))
    if not combos:
        return 0.0
    return sum(1 for passes in combos.values() if any(passes)) / len(combos)


def collect_daily_metrics(date_str: str | None = None) -> dict:
    """Collect all daily metrics. Returns dict with metric values and status."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    verdicts = _read_jsonl(VERDICTS_PATH)
    registry = _read_jsonl(REGISTRY_PATH)
    short_win = _read_jsonl(SHORT_WIN_PATH)
    pending = _read_jsonl(PENDING_PATH)

    # 1. Redundancy rate: fraction of registry stems appearing >1 time
    stem_counts = Counter(r.get("stem", "") for r in registry if r.get("stem"))
    total_stems = len(stem_counts)
    dup_stems = sum(1 for c in stem_counts.values() if c > 1)
    redundancy_rate = dup_stems / total_stems if total_stems else 0.0

    # Registry has proposal stems and .prescreen stems. Separate them.
    proposal_stems = {s for s in stem_counts if ".prescreen" not in s}
    prescreen_stems = {s for s in stem_counts if ".prescreen" in s}

    # 2. Unique variant coverage: fraction of proposal stems that reached verdict
    verdict_ids = {v.get("variant_id", "") for v in verdicts if v.get("variant_id")}
    reached_verdict = sum(1 for s in proposal_stems if _stem_to_variant(s) in verdict_ids)
    unique_coverage = reached_verdict / len(proposal_stems) if proposal_stems else 0.0

    # 3. Gate pass rate
    gate_pass_count = sum(1 for v in verdicts if v.get("gate_pass"))
    gate_pass_rate = gate_pass_count / len(verdicts) if verdicts else 0.0

    # 4. High quality rate (S or A tier)
    high_quality = sum(1 for v in verdicts if v.get("tier") in ("S", "A"))
    high_quality_rate = high_quality / len(verdicts) if verdicts else 0.0

    # 5. Prescreen success rate: fraction of prescreened stems that reached verdict
    #    (prescreen_stems have .prescreen suffix; verdict_ids are the survivors)
    prescreen_total = len(prescreen_stems)
    prescreen_survived = sum(
        1 for s in prescreen_stems
        if _stem_to_variant(s) in verdict_ids
    )
    prescreen_success = prescreen_survived / prescreen_total if prescreen_total else 0.0

    # 6. Combination coverage
    combo_coverage = _compute_combination_coverage(verdicts)

    metrics = {
        "date": date_str,
        "redundancy_rate": round(redundancy_rate, 4),
        "unique_variant_coverage": round(unique_coverage, 4),
        "gate_pass_rate": round(gate_pass_rate, 4),
        "high_quality_rate": round(high_quality_rate, 4),
        "prescreen_success_rate": round(prescreen_success, 4),
        "combination_coverage": round(combo_coverage, 4),
        "raw_counts": {
            "total_verdicts": len(verdicts),
            "gate_pass": gate_pass_count,
            "high_quality_S_A": high_quality,
            "registry_stems": total_stems,
            "dup_stems": dup_stems,
            "pending_total": prescreen_total,
            "pending_ok": prescreen_survived,
            "short_window_results": len(short_win),
        },
        "status": "ok",
        "alerts": [],
    }

    # Determine overall status
    for key, (op, target) in TARGETS.items():
        val = metrics[key]
        miss = (val >= target) if op == "<" else (val <= target)
        if miss:
            metrics["status"] = "warning"

    return metrics


def check_red_lines(metrics: dict | None = None) -> list[str]:
    """Check red-line indicators. Returns list of alert strings."""
    alerts: list[str] = []

    # 1. Laya weight update: any unknown files in models/
    models_dir = _REPO_ROOT / "models"
    if models_dir.exists():
        current = {p.name for p in models_dir.iterdir()}
        unknown = current - KNOWN_MODEL_FILES
        if unknown:
            alerts.append(f"CRITICAL: Unknown model files detected: {unknown}")

    # 2. Queue duplicate variants
    registry = _read_jsonl(REGISTRY_PATH)
    stem_counts = Counter(r.get("stem", "") for r in registry if r.get("stem"))
    dups = {s: c for s, c in stem_counts.items() if c > 1}
    if dups:
        alerts.append(
            f"WARNING: {len(dups)} duplicate stems in registry "
            f"(max count: {max(dups.values())})"
        )

    # 3. Fan-out path mixing: variant_name with multiple covariates
    ledger = _iter_ledger_entries()
    variant_covs: dict[str, set[str]] = {}
    for e in ledger:
        vid = e.get("variant_name", "")
        cov = e.get("covariate", "")
        if vid and cov:
            variant_covs.setdefault(vid, set()).add(cov)
    mixed = {v: list(covs) for v, covs in variant_covs.items() if len(covs) > 1}
    if mixed:
        sample = dict(list(mixed.items())[:3])
        alerts.append(
            f"WARNING: {len(mixed)} variants with mixed covariates: {sample}"
        )

    return alerts


def generate_report(metrics: dict, output_format: str = "markdown") -> str:
    """Generate a status report from collected metrics."""
    alerts = metrics.get("alerts") or check_red_lines(metrics)
    metrics["alerts"] = alerts

    if output_format == "json":
        return json.dumps(metrics, indent=2, ensure_ascii=False)

    status_icon = {"ok": "✅", "warning": "⚠️", "critical": "🔴"}.get(
        metrics["status"], "?"
    )
    lines = [
        f"# FM_a 监控报告 - {metrics['date']}",
        "",
        f"**状态**: {status_icon} {metrics['status'].upper()}",
        "",
        "## 核心指标",
        "",
        "| 指标 | 当前值 | 目标 | 状态 |",
        "|------|--------|------|------|",
    ]

    for key, label in LABELS.items():
        val = metrics.get(key, 0)
        op, target = TARGETS[key]
        ok = (val < target) if op == "<" else (val > target)
        target_str = f"<{target:.0%}" if op == "<" else f">{target:.0%}"
        icon = "✅" if ok else "❌"
        lines.append(f"| {label} | {val:.1%} | {target_str} | {icon} |")

    rc = metrics.get("raw_counts", {})
    if rc:
        lines += [
            "",
            "## 原始计数",
            "",
            f"- 总 verdicts: {rc.get('total_verdicts', 0)}",
            f"- Gate pass: {rc.get('gate_pass', 0)}",
            f"- 高质量 (S/A): {rc.get('high_quality_S_A', 0)}",
            f"- Registry 唯一 stems: {rc.get('registry_stems', 0)}",
            f"- 重复 stems: {rc.get('dup_stems', 0)}",
            f"- Pending 总量: {rc.get('pending_total', 0)}",
            f"- Pending ok: {rc.get('pending_ok', 0)}",
            f"- 短窗结果: {rc.get('short_window_results', 0)}",
        ]

    lines += ["", "## 告警", ""]
    if alerts:
        for a in alerts:
            lines.append(f"- **{a}**")
    else:
        lines.append("无告警。")

    return "\n".join(lines)


def compute_trend(values: list[float]) -> str:
    """Compute trend direction from a list of values. Returns up/down/stable."""
    if len(values) < 2:
        return "stable"
    n = len(values)
    q = max(1, n // 4)
    first_avg = sum(values[:q]) / q
    last_avg = sum(values[-q:]) / q
    diff = last_avg - first_avg
    if abs(diff) < 0.01:
        return "stable"
    return "up" if diff > 0 else "down"


def main():
    parser = argparse.ArgumentParser(description="FM_a monitoring metrics")
    sub = parser.add_subparsers(dest="command")

    p_collect = sub.add_parser("collect", help="Collect daily metrics")
    p_collect.add_argument("--output", "-o", help="Output JSON file")
    p_collect.add_argument("--date", help="Date string (default: today UTC)")

    p_report = sub.add_parser("report", help="Generate report")
    p_report.add_argument("--date", help="Date for report")
    p_report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_report.add_argument("--output", "-o", help="Output file")

    sub.add_parser("check-redlines", help="Check red-line indicators")

    args = parser.parse_args()

    if args.command == "collect":
        metrics = collect_daily_metrics(date_str=args.date)
        metrics["alerts"] = check_red_lines(metrics)
        out = json.dumps(metrics, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            print(f"Written to {args.output}")
        else:
            print(out)

    elif args.command == "report":
        metrics = collect_daily_metrics(date_str=args.date)
        report = generate_report(metrics, output_format=args.format)
        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
            print(f"Report written to {args.output}")
        else:
            print(report)

    elif args.command == "check-redlines":
        metrics = collect_daily_metrics()
        alerts = check_red_lines(metrics)
        if alerts:
            for a in alerts:
                print(a)
            sys.exit(1)
        else:
            print("No red-line violations.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

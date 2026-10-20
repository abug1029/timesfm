#!/usr/bin/env python3
"""Weekly report generator for FM_a monitoring.

Aggregates daily metrics from a metrics history directory and generates
a weekly summary with trend analysis.

Usage:
    python scripts/generate_weekly_report.py --week 2026-W43 [--output FILE]
    python scripts/generate_weekly_report.py --days 7 [--output FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from monitor_metrics import (
    collect_daily_metrics,
    check_red_lines,
    compute_trend,
    generate_report as generate_daily_report,
    TARGETS,
    LABELS,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_METRICS_DIR = _REPO_ROOT / "data" / "cache" / "metrics_history"


def _load_daily_metrics(date_str: str) -> dict | None:
    """Load a previously collected daily metrics JSON."""
    path = _METRICS_DIR / f"metrics_{date_str}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_daily_metrics(metrics: dict) -> Path:
    """Save daily metrics to the history directory."""
    _METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = _METRICS_DIR / f"metrics_{metrics['date']}.json"
    path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _get_dates_for_week(year: int, week: int) -> list[str]:
    """Return list of date strings for a given ISO week."""
    # ISO week: Monday is day 1
    jan4 = datetime(year, 1, 4).date()
    start = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=week - 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def collect_weekly_metrics(dates: list[str]) -> list[dict]:
    """Collect or load metrics for each date. Collects fresh if not cached."""
    results = []
    for d in dates:
        cached = _load_daily_metrics(d)
        if cached:
            results.append(cached)
        else:
            metrics = collect_daily_metrics(date_str=d)
            metrics["alerts"] = check_red_lines(metrics)
            _save_daily_metrics(metrics)
            results.append(metrics)
    return results


def generate_weekly_report(dates: list[str], week_label: str = "") -> str:
    """Generate a weekly summary report from daily metrics."""
    daily_data = collect_weekly_metrics(dates)

    if not daily_data:
        return f"# 周报 - {week_label}\n\n无数据。\n"

    # Compute trends for each metric
    metric_keys = list(TARGETS.keys())
    trends = {}
    for key in metric_keys:
        values = [d.get(key, 0) for d in daily_data]
        trends[key] = compute_trend(values)

    # Averages
    averages = {}
    for key in metric_keys:
        values = [d.get(key, 0) for d in daily_data]
        averages[key] = sum(values) / len(values) if values else 0.0

    # Latest status
    latest = daily_data[-1]

    # Count alerts across the week
    all_alerts = []
    for d in daily_data:
        for a in d.get("alerts", []):
            all_alerts.append((d["date"], a))

    # Build report
    trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}
    lines = [
        f"# FM_a 周报 - {week_label or dates[0] + ' ~ ' + dates[-1]}",
        "",
        f"**周期**: {dates[0]} ~ {dates[-1]} ({len(daily_data)} 天)",
        f"**最新状态**: {latest['status'].upper()}",
        "",
        "## 指标趋势",
        "",
        "| 指标 | 周平均 | 最新值 | 趋势 | 目标 |",
        "|------|--------|--------|------|------|",
    ]

    for key in metric_keys:
        label = LABELS[key]
        avg = averages[key]
        val = latest.get(key, 0)
        tr = trends[key]
        op, target = TARGETS[key]
        target_str = f"<{target:.0%}" if op == "<" else f">{target:.0%}"
        lines.append(
            f"| {label} | {avg:.1%} | {val:.1%} | {trend_icon.get(tr, '?')} {tr} | {target_str} |"
        )

    # Daily breakdown
    lines += [
        "",
        "## 每日摘要",
        "",
        "| 日期 | 状态 | Gate Pass | 高质量率 | 告警数 |",
        "|------|------|-----------|----------|--------|",
    ]
    for d in daily_data:
        n_alerts = len(d.get("alerts", []))
        lines.append(
            f"| {d['date']} | {d['status']} | {d['gate_pass_rate']:.1%} "
            f"| {d['high_quality_rate']:.1%} | {n_alerts} |"
        )

    # Alerts section
    lines += ["", "## 本周告警", ""]
    if all_alerts:
        for date, alert in all_alerts:
            lines.append(f"- **{date}**: {alert}")
    else:
        lines.append("无告警。")

    # Recommendations
    lines += ["", "## 建议", ""]
    recs = _generate_recommendations(averages, trends)
    if recs:
        for r in recs:
            lines.append(f"- {r}")
    else:
        lines.append("各项指标正常，无需特别操作。")

    return "\n".join(lines)


def _generate_recommendations(averages: dict, trends: dict) -> list[str]:
    """Generate actionable recommendations based on metric trends."""
    recs = []
    if averages["gate_pass_rate"] < TARGETS["gate_pass_rate"][1]:
        recs.append("Gate pass 率低于目标，考虑放宽预筛阈值或增加高质量协变量搜索")
    if averages["high_quality_rate"] < TARGETS["high_quality_rate"][1]:
        recs.append("高质量率 (S/A) 低于目标，检查质量预测模型是否需要重新校准")
    if averages["prescreen_success_rate"] < TARGETS["prescreen_success_rate"][1]:
        recs.append("Prescreen 成功率低于目标，检查 Laya 预筛状态和队列健康")
    if averages["combination_coverage"] < TARGETS["combination_coverage"][1]:
        recs.append("组合覆盖率不足，需扩大搜索覆盖面（品种/协变量族组合）")
    if trends["redundancy_rate"] == "up":
        recs.append("冗余率呈上升趋势，检查 harvest 去重逻辑")
    return recs


def main():
    parser = argparse.ArgumentParser(description="FM_a weekly report generator")
    parser.add_argument("--week", help="ISO week label (e.g. 2026-W43)")
    parser.add_argument("--days", type=int, help="Number of days to include (from today back)")
    parser.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args()

    if args.week:
        # Parse ISO week: "2026-W43"
        parts = args.week.split("-W")
        if len(parts) != 2:
            print("Error: week format should be YYYY-Www (e.g. 2026-W43)", file=sys.stderr)
            sys.exit(1)
        year, week = int(parts[0]), int(parts[1])
        dates = _get_dates_for_week(year, week)
        week_label = args.week
    elif args.days:
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(args.days - 1, -1, -1)]
        week_label = f"最近 {args.days} 天"
    else:
        # Default: last 7 days
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        week_label = f"最近 7 天"

    report = generate_weekly_report(dates, week_label=week_label)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

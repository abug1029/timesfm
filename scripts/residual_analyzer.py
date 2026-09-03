#!/usr/bin/env python3
"""
residual_analyzer.py — FM_a 残差分析

收集历史预测残差，按时间段/品种/交易时段分组，检测系统性偏差。

用法:
    python scripts/residual_analyzer.py
"""

import json
import re
import sqlite3
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from collections import defaultdict
from datetime import datetime
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
DB_DIR = FM_ROOT / "db"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES

# 系统性偏差阈值
BIAS_THRESHOLD = 0.5  # 均值偏差 > 0.5% → 标记为系统性偏差


def parse_cascade_hourly(cascade_path: Path, report_dt: datetime) -> list[dict]:
    """从 cascade_*.md 提取逐小时预测。"""
    rows = []
    if not cascade_path.exists():
        return rows

    text = cascade_path.read_text(encoding="utf-8")
    in_table = False

    for line in text.splitlines():
        line = line.strip()
        if "逐小时预测" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if line:
                break
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        if len(cells) < 2 or re.match(r"^[-:]+$", cells[0]):
            continue
        # 跳过表头 (兼容新旧格式)
        if cells[0] in ("Hour", "小时") or (len(cells) > 1 and cells[1] in ("Hour", "小时")):
            continue

        # 动态查找 T+N 列 (兼容有时间列的新格式)
        hour_idx = None
        for ci, cell in enumerate(cells):
            if re.match(r"T\+(\d+)", cell):
                hour_idx = ci
                break
        if hour_idx is None:
            continue
        try:
            hour = int(re.match(r"T\+(\d+)", cells[hour_idx]).group(1))
            pred = float(cells[hour_idx + 1].replace(",", ""))
        except (ValueError, TypeError):
            continue

        rows.append({
            "hour": hour,
            "pred": pred,
            "report_dt": report_dt,
        })
    return rows


def get_actual_1h(symbol: str, target_dt: datetime) -> float:
    """获取指定时间的 1H 实际收盘价。"""
    db_path = DB_DIR / f"futures_{symbol}.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        date_str = target_dt.strftime("%Y-%m-%d")
        hour_str = target_dt.strftime("%H")
        cur.execute(
            """SELECT close_price FROM kline_1h
               WHERE dt LIKE ? AND contract_code LIKE '%_MAIN'
               LIMIT 1""",
            (f"{date_str} {hour_str}:%",),
        )
        row = cur.fetchone()
        conn.close()
        return float(row[0]) if row and row[0] else None
    except Exception:
        return None


def collect_residuals() -> list[dict]:
    """收集所有历史预测的残差。"""
    residuals = []
    if not REPORTS_DIR.exists():
        return residuals

    for d in sorted(REPORTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r"^(\d{8})_(\d{4})$", d.name)
        if not m:
            continue
        try:
            report_dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M")
        except ValueError:
            continue

        for cascade_file in d.glob("cascade_*.md"):
            sym_match = re.match(r"cascade_(\w+)\.md", cascade_file.name)
            if not sym_match:
                continue
            symbol = sym_match.group(1).lower()

            hourly = parse_cascade_hourly(cascade_file, report_dt)
            for h in hourly:
                # 简化: 只分析 T+1~T+6（近期预测更可靠）
                if h["hour"] > 6:
                    continue
                actual = get_actual_1h(symbol, report_dt)
                if actual is None:
                    continue
                err_pct = (h["pred"] - actual) / actual * 100
                session = "night" if report_dt.hour >= 21 or report_dt.hour < 3 else "day"

                residuals.append({
                    "symbol": symbol,
                    "hour": h["hour"],
                    "predicted": h["pred"],
                    "actual": actual,
                    "err_pct": round(err_pct, 4),
                    "abs_err_pct": round(abs(err_pct), 4),
                    "session": session,
                    "date": report_dt.strftime("%Y-%m-%d"),
                })

    return residuals


def analyze_by_period(residuals: list[dict]) -> dict:
    """按时间段分组分析。"""
    periods = {"T+1~T+6": [], "T+7~T+12": [], "T+13~T+18": [], "T+19~T+24": []}
    for r in residuals:
        h = r["hour"]
        if h <= 6:
            periods["T+1~T+6"].append(r)
        elif h <= 12:
            periods["T+7~T+12"].append(r)
        elif h <= 18:
            periods["T+13~T+18"].append(r)
        else:
            periods["T+19~T+24"].append(r)

    results = {}
    for period, res_list in periods.items():
        if not res_list:
            results[period] = {"count": 0, "mean_bias": 0, "mape": 0, "std": 0}
            continue
        errors = [r["err_pct"] for r in res_list]
        mean_bias = sum(errors) / len(errors)
        mape = sum(abs(e) for e in errors) / len(errors)
        variance = sum((e - mean_bias) ** 2 for e in errors) / len(errors)
        std = variance ** 0.5
        results[period] = {
            "count": len(res_list),
            "mean_bias": round(mean_bias, 4),
            "mape": round(mape, 4),
            "std": round(std, 4),
        }
    return results


def analyze_by_symbol(residuals: list[dict]) -> dict:
    """按品种分组分析。"""
    by_sym = defaultdict(list)
    for r in residuals:
        by_sym[r["symbol"]].append(r)

    results = {}
    for sym, res_list in by_sym.items():
        errors = [r["err_pct"] for r in res_list]
        mean_bias = sum(errors) / len(errors)
        mape = sum(abs(e) for e in errors) / len(errors)
        results[sym] = {
            "name": SYMBOL_NAMES.get(sym, sym),
            "count": len(res_list),
            "mean_bias": round(mean_bias, 4),
            "mape": round(mape, 4),
            "systematic_bias": abs(mean_bias) > BIAS_THRESHOLD,
            "bias_direction": "高估" if mean_bias > 0 else "低估",
        }
    return results


def analyze_by_session(residuals: list[dict]) -> dict:
    """按交易时段分组分析。"""
    by_session = defaultdict(list)
    for r in residuals:
        by_session[r["session"]].append(r)

    results = {}
    for session, res_list in by_session.items():
        if not res_list:
            continue
        errors = [r["err_pct"] for r in res_list]
        mean_bias = sum(errors) / len(errors)
        mape = sum(abs(e) for e in errors) / len(errors)
        results[session] = {
            "count": len(res_list),
            "mean_bias": round(mean_bias, 4),
            "mape": round(mape, 4),
        }
    return results


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 📊 残差分析报告\n")
    print(f"**时间**: {now_str}\n")

    residuals = collect_residuals()
    if not residuals:
        print("> 无足够残差数据（需要历史预测 + 实际 1H 数据对比）\n")
        json.dump({"status": "no_data"}, sys.stderr, ensure_ascii=False)
        return

    print(f"**残差样本数**: {len(residuals)}\n")

    # 按时间段分析
    by_period = analyze_by_period(residuals)
    print("## 按预测时段\n")
    print("| 时段 | 样本数 | 均值偏差 | MAPE | 标准差 | 系统性偏差 |")
    print("|------|:------:|:--------:|:----:|:------:|:---------:|")
    for period, d in by_period.items():
        flag = "⚠️" if abs(d["mean_bias"]) > BIAS_THRESHOLD else "—"
        print(
            f"| {period} | {d['count']} "
            f"| {d['mean_bias']:+.3f}% | {d['mape']:.3f}% "
            f"| {d['std']:.3f}% | {flag} |"
        )

    # 按品种分析
    by_symbol = analyze_by_symbol(residuals)
    systematic = {s: d for s, d in by_symbol.items() if d["systematic_bias"]}

    if systematic:
        print(f"\n## ⚠️ 系统性偏差 ({len(systematic)} 个品种)\n")
        print("| 品种 | 名称 | 样本数 | 均值偏差 | MAPE | 方向 |")
        print("|------|------|:------:|:--------:|:----:|:----:|")
        for sym, d in sorted(systematic.items(), key=lambda x: -abs(x[1]["mean_bias"])):
            print(
                f"| `{sym}` | {d['name']} "
                f"| {d['count']} | {d['mean_bias']:+.3f}% "
                f"| {d['mape']:.3f}% | {d['bias_direction']} |"
            )
    else:
        print("\n## ✅ 无系统性偏差\n")

    # 按交易时段分析
    by_session = analyze_by_session(residuals)
    if by_session:
        print(f"\n## 按交易时段\n")
        print("| 时段 | 样本数 | 均值偏差 | MAPE |")
        print("|------|:------:|:--------:|:----:|")
        for session, d in by_session.items():
            label = "日盘" if session == "day" else "夜盘"
            print(f"| {label} | {d['count']} | {d['mean_bias']:+.3f}% | {d['mape']:.3f}% |")

    # 汇总
    all_errors = [r["err_pct"] for r in residuals]
    overall_mean = sum(all_errors) / len(all_errors)
    overall_mape = sum(abs(e) for e in all_errors) / len(all_errors)

    print(f"\n## 汇总\n")
    print(f"- 总残差样本: {len(residuals)}")
    print(f"- 总体均值偏差: {overall_mean:+.3f}%")
    print(f"- 总体 MAPE: {overall_mape:.3f}%")
    print(f"- 系统性偏差品种: {len(systematic)}")

    json.dump({
        "total_residuals": len(residuals),
        "overall_mean_bias": round(overall_mean, 4),
        "overall_mape": round(overall_mape, 4),
        "systematic_count": len(systematic),
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

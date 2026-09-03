#!/usr/bin/env python3
"""
drift_detector.py — FM_a 模型退化预警

滑动窗口追踪每个品种的预测精度，与固化方案基线对比。
持久化到 reports/drift_tracking.json。

用法:
    python scripts/drift_detector.py
"""

import json
import os
import re
import sqlite3
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

FM_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = FM_ROOT / "reports"
DB_DIR = FM_ROOT / "db"
DRIFT_FILE = REPORTS_DIR / "drift_tracking.json"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES

# 滑动窗口大小
WINDOW_SIZE = 20
# 告警阈值
MAPE_WARNING_RATIO = 1.5      # 滑动 MAPE > 基线 × 1.5 → Warning
DIRACC_ALERT_DROP = 0.08      # 滑动 DirAcc < 基线 - 8pp → Alert
BIAS_STREAK = 5               # 连续 N 次同方向偏差 → Warning


def load_drift_tracking() -> dict:
    """加载持久化的滑动窗口数据。"""
    if DRIFT_FILE.exists():
        try:
            return json.loads(DRIFT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"symbols": {}, "last_updated": None}


def save_drift_tracking(data: dict):
    """持久化滑动窗口数据。"""
    data["last_updated"] = datetime.now().isoformat()
    DRIFT_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_scheme_baselines() -> dict:
    """从 prediction_scheme.py 加载各品种的基线指标。"""
    baselines = {}
    try:
        scheme_path = FM_ROOT / "config" / "prediction_scheme.py"
        text = scheme_path.read_text(encoding="utf-8")
        # 简单解析: 找每个 symbol 的 dir_acc 和 mape
        for m in re.finditer(
            r'symbol=["\'](\w+)["\'].*?dir_acc=([\d.]+).*?mape=([\d.]+)',
            text, re.DOTALL
        ):
            sym = m.group(1).lower()
            baselines[sym] = {
                "dir_acc": float(m.group(2)),
                "mape": float(m.group(3)),
            }
    except Exception:
        pass
    return baselines


def parse_all_predictions() -> list[dict]:
    """扫描所有报告目录，提取 T+1 预测记录。"""
    records = []
    if not REPORTS_DIR.exists():
        return records

    for d in sorted(REPORTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r"^(\d{8})_(\d{4})$", d.name)
        if not m:
            continue
        try:
            dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M")
        except ValueError:
            continue

        summary = d / "summary.md"
        if not summary.exists():
            continue

        text = summary.read_text(encoding="utf-8")
        dir_map = {"↑": "bull", "↓": "bear", "→": "neutral"}

        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            if len(cells) < 4:
                continue
            if re.match(r"^[-:]+$", cells[0]):
                continue
            if cells[0] in ("品种", "字段"):
                continue

            sym_match = re.match(r"([A-Za-z0-9]+)", cells[0])
            if not sym_match:
                continue
            symbol = sym_match.group(1).lower()

            direction = "neutral"
            for arrow, d_name in dir_map.items():
                if arrow in cells[1]:
                    direction = d_name
                    break

            try:
                t1_value = float(cells[2].replace(",", ""))
            except (ValueError, TypeError):
                continue

            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "dt": dt.isoformat(),
                "symbol": symbol,
                "direction": direction,
                "t1_value": t1_value,
            })

    return records


def get_actual_close(symbol: str, date_str: str) -> float:
    """获取指定品种在指定日期的下一交易日主力收盘价。"""
    db_path = DB_DIR / f"futures_{symbol}.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        cur.execute(
            "SELECT dt, close_price FROM main_continuous_1d WHERE dt > ? ORDER BY dt ASC LIMIT 1",
            (date_str,),
        )
        row = cur.fetchone()
        conn.close()
        if row and row[1] is not None:
            return float(row[1])
    except Exception:
        pass
    return None


def compute_drift(records: list[dict], baselines: dict, tracking: dict) -> dict:
    """计算每个品种的滑动窗口漂移指标。"""
    # 按品种分组
    by_symbol = {}
    for r in records:
        sym = r["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(r)

    results = {}
    for sym, preds in by_symbol.items():
        preds.sort(key=lambda x: x["dt"])

        # 加载已有窗口
        prev_window = tracking.get("symbols", {}).get(sym, {}).get("window", [])
        seen_dates = {p["date"] for p in prev_window}

        # 添加新预测
        for p in preds:
            if p["date"] in seen_dates:
                continue
            actual = get_actual_close(sym, p["date"])
            if actual is None:
                continue
            err_pct = (p["t1_value"] - actual) / actual * 100
            pred_dir = p["direction"]
            actual_dir = "bull" if actual > p["t1_value"] * 1.001 else (
                "bear" if actual < p["t1_value"] * 0.999 else "neutral"
            )
            dir_correct = pred_dir == actual_dir

            prev_window.append({
                "date": p["date"],
                "predicted": p["t1_value"],
                "actual": actual,
                "err_pct": round(err_pct, 4),
                "dir_correct": dir_correct,
                "direction": pred_dir,
            })
            seen_dates.add(p["date"])

        # 保留最近 WINDOW_SIZE 条
        window = prev_window[-WINDOW_SIZE:]

        # 计算滑动指标
        if not window:
            continue

        mape = sum(abs(w["err_pct"]) for w in window) / len(window)
        dir_acc = sum(1 for w in window if w["dir_correct"]) / len(window)

        # 连续偏差方向检测
        streak = 0
        if len(window) >= BIAS_STREAK:
            last_direction = None
            for w in reversed(window):
                bias_dir = "over" if w["err_pct"] > 0.1 else ("under" if w["err_pct"] < -0.1 else "neutral")
                if last_direction is None:
                    last_direction = bias_dir
                if bias_dir == last_direction and bias_dir != "neutral":
                    streak += 1
                else:
                    break

        # 与基线对比
        baseline = baselines.get(sym, {"dir_acc": 0.5, "mape": 3.0})
        baseline_da = baseline["dir_acc"]
        baseline_mape = baseline["mape"]

        # 告警判断
        status = "ok"
        alerts = []

        if mape > baseline_mape * MAPE_WARNING_RATIO:
            status = "warning"
            alerts.append(f"MAPE {mape:.2f}% > 基线 {baseline_mape:.2f}% × {MAPE_WARNING_RATIO}")

        if dir_acc < baseline_da - DIRACC_ALERT_DROP:
            status = "alert"
            alerts.append(f"DirAcc {dir_acc:.1%} < 基线 {baseline_da:.1%} - {DIRACC_ALERT_DROP:.0%}")

        if streak >= BIAS_STREAK:
            if status == "ok":
                status = "warning"
            bias_dir = "高估" if window[-1]["err_pct"] > 0 else "低估"
            alerts.append(f"连续 {streak} 次{bias_dir}")

        results[sym] = {
            "name": SYMBOL_NAMES.get(sym, sym),
            "window_size": len(window),
            "mape": round(mape, 3),
            "dir_acc": round(dir_acc, 4),
            "baseline_dir_acc": baseline_da,
            "baseline_mape": baseline_mape,
            "status": status,
            "alerts": alerts,
            "bias_streak": streak,
            "window": window[-5:],  # 只保留最近 5 条摘要
        }

    return results


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 📈 退化预警报告\n")
    print(f"**时间**: {now_str}  ")
    print(f"**窗口大小**: {WINDOW_SIZE} 次预测\n")

    # 加载数据
    tracking = load_drift_tracking()
    baselines = load_scheme_baselines()
    records = parse_all_predictions()

    if not records:
        print("> 无历史预测记录可分析\n")
        save_drift_tracking(tracking)
        return

    if not baselines:
        print("> 无固化方案基线可对比\n")

    # 计算漂移
    drift_results = compute_drift(records, baselines, tracking)

    # 更新 tracking
    for sym, data in drift_results.items():
        if sym not in tracking.get("symbols", {}):
            tracking.setdefault("symbols", {})[sym] = {}
        tracking["symbols"][sym]["window"] = data["window"]
        tracking["symbols"][sym]["status"] = data["status"]
        tracking["symbols"][sym]["mape"] = data["mape"]
        tracking["symbols"][sym]["dir_acc"] = data["dir_acc"]
        tracking["symbols"][sym]["last_updated"] = now_str

    save_drift_tracking(tracking)

    # 输出报告
    alerts = {s: d for s, d in drift_results.items() if d["status"] == "alert"}
    warnings = {s: d for s, d in drift_results.items() if d["status"] == "warning"}
    ok = {s: d for s, d in drift_results.items() if d["status"] == "ok"}

    if alerts:
        print("## 🔴 退化告警\n")
        print("| 品种 | 名称 | 滑动DirAcc | 基线DirAcc | 滑动MAPE | 基线MAPE | 告警 |")
        print("|------|------|:---------:|:---------:|:--------:|:--------:|------|")
        for sym, d in sorted(alerts.items()):
            print(
                f"| `{sym}` | {d['name']} "
                f"| {d['dir_acc']:.1%} | {d['baseline_dir_acc']:.1%} "
                f"| {d['mape']:.2f}% | {d['baseline_mape']:.2f}% "
                f"| {'; '.join(d['alerts'])} |"
            )

    if warnings:
        print("\n## 🟡 预警\n")
        print("| 品种 | 名称 | 滑动DirAcc | 滑动MAPE | 告警 |")
        print("|------|------|:---------:|:--------:|------|")
        for sym, d in sorted(warnings.items()):
            print(
                f"| `{sym}` | {d['name']} "
                f"| {d['dir_acc']:.1%} | {d['mape']:.2f}% "
                f"| {'; '.join(d['alerts'])} |"
            )

    if ok:
        print(f"\n## ✅ 正常 ({len(ok)} 个品种)\n")

    print(f"\n## 汇总\n")
    print(f"- 分析品种: {len(drift_results)}")
    print(f"- 🔴 告警: {len(alerts)}")
    print(f"- 🟡 预警: {len(warnings)}")
    print(f"- ✅ 正常: {len(ok)}")

    # JSON to stderr
    json.dump({
        "alert_count": len(alerts),
        "warning_count": len(warnings),
        "ok_count": len(ok),
        "details": {s: {k: v for k, v in d.items() if k != "window"}
                    for s, d in drift_results.items()},
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

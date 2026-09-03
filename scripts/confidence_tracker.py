#!/usr/bin/env python3
"""
confidence_tracker.py — FM_a 预测置信度追踪

追踪各品种的滚动预测精度，按信号权重分桶，输出置信度等级。
持久化到 reports/confidence_tracking.json。

用法:
    python scripts/confidence_tracker.py
"""

import json
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
CONFIDENCE_FILE = REPORTS_DIR / "confidence_tracking.json"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES

# 置信度阈值
HIGH_CONFIDENCE = 0.9    # 信号权重 ≥ 0.9
MED_CONFIDENCE = 0.7     # 信号权重 0.7 ~ 0.9
# < 0.7 → 低信心

# 滚动窗口
ROLLING_WINDOW = 10


def parse_hourly_with_weights(cascade_path: Path) -> list[dict]:
    """从 cascade_*.md 提取逐小时预测 + 信号权重。"""
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
        if len(cells) < 6:
            continue
        if re.match(r"^[-:]+$", cells[0]):
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
            weight = float(cells[hour_idx + 5]) if len(cells) > hour_idx + 5 else 0.5
        except (ValueError, TypeError):
            continue

        rows.append({"hour": hour, "pred": pred, "weight": weight})
    return rows


def load_confidence_tracking() -> dict:
    if CONFIDENCE_FILE.exists():
        try:
            return json.loads(CONFIDENCE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"symbols": {}, "last_updated": None}


def save_confidence_tracking(data: dict):
    data["last_updated"] = datetime.now().isoformat()
    CONFIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIDENCE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_reports() -> dict:
    """扫描所有报告，按品种提取逐小时预测和信号权重。"""
    by_symbol = {}
    if not REPORTS_DIR.exists():
        return by_symbol

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

        # 找 cascade_*.md 文件
        for cascade_file in d.glob("cascade_*.md"):
            sym_match = re.match(r"cascade_(\w+)\.md", cascade_file.name)
            if not sym_match:
                continue
            symbol = sym_match.group(1).lower()

            hourly = parse_hourly_with_weights(cascade_file)
            if hourly:
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "dt": dt.isoformat(),
                    "hourly": hourly,
                })

    return by_symbol


def compute_confidence(all_predictions: dict, tracking: dict) -> dict:
    """计算每个品种的置信度等级。"""
    results = {}

    for sym, predictions in all_predictions.items():
        predictions.sort(key=lambda x: x["dt"])

        # 计算平均信号权重（最近 ROLLING_WINDOW 次预测）
        recent = predictions[-ROLLING_WINDOW:]
        if not recent:
            continue

        all_weights = []
        for p in recent:
            for h in p["hourly"]:
                all_weights.append(h["weight"])

        if not all_weights:
            continue

        avg_weight = sum(all_weights) / len(all_weights)
        min_weight = min(all_weights) if all_weights else 0

        # 置信度等级
        if avg_weight >= HIGH_CONFIDENCE:
            level = "high"
        elif avg_weight >= MED_CONFIDENCE:
            level = "medium"
        else:
            level = "low"

        # 加载历史记录
        prev = tracking.get("symbols", {}).get(sym, {})
        history = prev.get("history", [])
        history.append({
            "date": recent[-1]["date"],
            "avg_weight": round(avg_weight, 3),
            "level": level,
        })
        history = history[-20:]  # 保留最近 20 条

        results[sym] = {
            "name": SYMBOL_NAMES.get(sym, sym),
            "avg_weight": round(avg_weight, 3),
            "min_weight": round(min_weight, 3),
            "level": level,
            "predictions_count": len(predictions),
            "history": history,
        }

    return results


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 🎯 预测置信度报告\n")
    print(f"**时间**: {now_str}  ")
    print(f"**滚动窗口**: 最近 {ROLLING_WINDOW} 次预测\n")

    tracking = load_confidence_tracking()
    all_predictions = scan_reports()

    if not all_predictions:
        print("> 无历史报告可分析\n")
        save_confidence_tracking(tracking)
        return

    results = compute_confidence(all_predictions, tracking)

    # 更新 tracking
    for sym, data in results.items():
        tracking.setdefault("symbols", {})[sym] = {
            "level": data["level"],
            "avg_weight": data["avg_weight"],
            "history": data["history"],
        }
    save_confidence_tracking(tracking)

    # 按等级分组
    high = {s: d for s, d in results.items() if d["level"] == "high"}
    medium = {s: d for s, d in results.items() if d["level"] == "medium"}
    low = {s: d for s, d in results.items() if d["level"] == "low"}

    print("## 置信度总览\n")
    print("| 品种 | 名称 | 等级 | 平均权重 | 最低权重 | 预测次数 |")
    print("|------|------|:----:|:--------:|:--------:|:--------:|")

    for sym, d in sorted(results.items(), key=lambda x: -x[1]["avg_weight"]):
        icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(d["level"], "⚪")
        print(
            f"| `{sym}` | {d['name']} "
            f"| {icon} {d['level']} "
            f"| {d['avg_weight']:.3f} | {d['min_weight']:.3f} "
            f"| {d['predictions_count']} |"
        )

    print(f"\n## 汇总\n")
    print(f"- 🟢 高信心 (≥{HIGH_CONFIDENCE}): {len(high)} 个 — {', '.join(f'`{s}`' for s in high)}")
    print(f"- 🟡 中信心 ({MED_CONFIDENCE}~{HIGH_CONFIDENCE}): {len(medium)} 个 — {', '.join(f'`{s}`' for s in medium)}")
    print(f"- 🔴 低信心 (<{MED_CONFIDENCE}): {len(low)} 个 — {', '.join(f'`{s}`' for s in low)}")

    if high:
        print(f"\n## ✅ 建议参与决策\n")
        names = ", ".join(f"**{s}**({results[s]['name']})" for s in high)
        print(names)

    if low:
        print(f"\n## ⚠️ 低信心排除\n")
        print("以下品种信号权重低，建议不作为决策依据:")
        names = ", ".join(f"`{s}`({results[s]['name']})" for s in low)
        print(names)

    json.dump({
        "high_count": len(high),
        "medium_count": len(medium),
        "low_count": len(low),
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

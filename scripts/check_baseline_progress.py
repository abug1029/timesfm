#!/usr/bin/env python3
"""检查基线重生进度。读取 task_FM/config/（工作目录）而非 cycle 快照。

用法:
  python scripts/check_baseline_progress.py
"""

import json
from pathlib import Path
from datetime import datetime

FM_ROOT = Path(__file__).resolve().parent.parent
CONFIRM_WINDOW_START = datetime(2026, 10, 3, 0, 0, 0)

def check_progress():
    """检查所有品种的基线重生进度"""
    config_dir = FM_ROOT / "task_FM" / "config"

    if not config_dir.exists():
        print("ERROR: task_FM/config 目录不存在")
        return

    completed = []
    pending = []

    for bl_file in sorted(config_dir.glob("baseline_points_*_nocov.jsonl")):
        # 跳过归档文件
        if ".archive_" in bl_file.name:
            continue

        # 提取品种名
        parts = bl_file.name.split("_")
        if len(parts) >= 3:
            symbol = parts[2].upper()
        else:
            continue

        # 读取最后一行
        lines = bl_file.read_text().strip().split("\n")
        if lines:
            last_line = lines[-1]
            try:
                data = json.loads(last_line)
                dt_str = data.get("cutoff", "")
                data_dt = None

                # 尝试多种时间格式
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]:
                    try:
                        data_dt = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue

                if data_dt:
                    if data_dt >= CONFIRM_WINDOW_START:
                        completed.append((symbol, data_dt))
                    else:
                        pending.append((symbol, data_dt))
            except Exception as e:
                pass

    total = len(completed) + len(pending)
    pct = round(100 * len(completed) / total, 1) if total > 0 else 0

    print(f"Progress: {len(completed)}/{total} ({pct}%)")
    print(f"确认窗起点: {CONFIRM_WINDOW_START.strftime('%Y-%m-%d %H:%M')}")
    print()

    if completed:
        print("✅ 已完成 (>= 确认窗):")
        for sym, dt in sorted(completed):
            print(f"  {sym:4s}: {dt.strftime('%Y-%m-%d %H:%M')}")
        print()

    if pending:
        print("⏳ 未完成 (< 确认窗):")
        for sym, dt in sorted(pending):
            gap_hours = int((CONFIRM_WINDOW_START - dt).total_seconds() / 3600)
            print(f"  {sym:4s}: {dt.strftime('%Y-%m-%d %H:%M')} (差距 {gap_hours}h)")

if __name__ == "__main__":
    check_progress()

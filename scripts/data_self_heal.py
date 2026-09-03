#!/usr/bin/env python3
"""
data_self_heal.py — FM_a 数据采集自愈

检测过期品种并自动采集 1H 数据。在交易时段内运行时自动修复。

用法:
    python scripts/data_self_heal.py          # 检测 + 尝试修复
    python scripts/data_self_heal.py --dry-run # 仅检测不修复
"""

import json
import os
import re
import subprocess
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FM_ROOT = SCRIPT_DIR.parent
REPORTS_DIR = FM_ROOT / "reports"


def is_trading_hours() -> bool:
    """判断当前是否在交易时段（可以采集数据）。"""
    now = datetime.now()
    # 周末不采集
    if now.weekday() >= 5:
        return False
    h = now.hour
    # 日盘: 9:00-15:00, 夜盘: 21:00-次日 02:30
    return (9 <= h < 15) or (21 <= h <= 23) or (0 <= h < 3)


def run_health_check() -> dict:
    """运行 data_health_check.py 并解析 JSON 输出。"""
    script = SCRIPT_DIR / "data_health_check.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30, cwd=FM_ROOT,
        )
        # JSON 在 stderr
        for line in result.stderr.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        # 尝试解析整个 stderr
        try:
            return json.loads(result.stderr.strip())
        except (json.JSONDecodeError, ValueError):
            pass
    except Exception:
        pass
    return {}


def find_stale_symbols(health_data: dict) -> list[dict]:
    """从健康检查结果中提取过期品种。"""
    stale = []
    for db in health_data.get("databases", []):
        issues = db.get("issues", [])
        has_1h_stale = any("1H 数据过期" in i for i in issues)
        has_1d_stale = any("日线数据过期" in i for i in issues)
        has_1d_short = any("日线数据不足" in i for i in issues)
        if has_1h_stale or has_1d_stale or has_1d_short:
            stale.append({
                "symbol": db["symbol"],
                "name": db["name"],
                "1h_stale": has_1h_stale,
                "1d_stale": has_1d_stale,
                "1d_short": has_1d_short,
                "issues": issues,
            })
    return stale


def heal_symbol(symbol: str, needs_daily: bool) -> dict:
    """对单个品种执行数据采集修复。"""
    result = {"symbol": symbol, "actions": [], "success": False}

    if needs_daily:
        # 日线 + 1H 全量更新
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "daily_update.py"), symbol],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120, cwd=FM_ROOT,
            )
            result["actions"].append(f"daily_update.py {symbol} → exit={proc.returncode}")
            result["success"] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            result["actions"].append("daily_update.py 超时 (120s)")
        except Exception as e:
            result["actions"].append(f"daily_update.py 异常: {e}")
    else:
        # 仅 1H 更新
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "collect_1h.py"), symbol],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, cwd=FM_ROOT,
            )
            result["actions"].append(f"collect_1h.py {symbol} → exit={proc.returncode}")
            result["success"] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            result["actions"].append("collect_1h.py 超时 (60s)")
        except Exception as e:
            result["actions"].append(f"collect_1h.py 异常: {e}")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="仅检测不修复")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trading = is_trading_hours()

    print(f"# 数据采集自愈报告\n")
    print(f"**时间**: {now_str}  ")
    print(f"**交易时段**: {'是' if trading else '否'}  ")
    print(f"**模式**: {'仅检测 (dry-run)' if args.dry_run else '自动修复'}\n")

    # Step 1: 运行健康检查
    health_data = run_health_check()
    if not health_data:
        print("> 健康检查未返回有效数据\n")
        json.dump({"status": "error", "message": "health check failed"},
                   sys.stderr, ensure_ascii=False)
        return

    # Step 2: 找到过期品种
    stale = find_stale_symbols(health_data)
    if not stale:
        print("✅ 所有品种数据正常，无需修复。\n")
        json.dump({"status": "healthy", "stale_count": 0, "healed": []},
                   sys.stderr, ensure_ascii=False)
        return

    print(f"**过期品种**: {len(stale)} 个\n")

    # Step 3: 尝试修复
    healed = []
    skipped = []

    for s in stale:
        needs_daily = s["1d_stale"] or s["1d_short"]

        if args.dry_run or not trading:
            skipped.append(s)
            continue

        result = heal_symbol(s["symbol"], needs_daily)
        healed.append(result)

    # Step 4: 输出结果
    if healed:
        print("## 修复结果\n")
        print("| 品种 | 操作 | 成功 |")
        print("|------|------|:----:|")
        for h in healed:
            actions = "; ".join(h["actions"])
            mark = "✅" if h["success"] else "❌"
            print(f"| {h['symbol']} | {actions} | {mark} |")

    if skipped:
        reason = "dry-run 模式" if args.dry_run else "非交易时段"
        print(f"\n## ⏸️ 跳过修复 ({reason})\n")
        for s in skipped:
            needs = "日线+1H" if (s["1d_stale"] or s["1d_short"]) else "1H"
            print(f"- `{s['symbol']}` ({s['name']}): 需要更新 {needs}")

    success_count = sum(1 for h in healed if h["success"])
    print(f"\n## 汇总\n")
    print(f"- 过期品种: {len(stale)}")
    print(f"- 已修复: {success_count}/{len(healed)}")
    print(f"- 跳过: {len(skipped)}")

    json.dump({
        "status": "healed" if success_count > 0 else ("skipped" if skipped else "no_action"),
        "stale_count": len(stale),
        "healed_count": success_count,
        "skipped_count": len(skipped),
        "details": healed + [{"symbol": s["symbol"], "skipped": True} for s in skipped],
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

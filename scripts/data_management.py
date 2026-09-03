#!/usr/bin/env python3
"""
data_management.py — FM_a 主动数据完善 + 验证

智能数据管理脚本，根据时段自动决定采集策略：
  --auto       根据当前时间自动判断（默认）
  --1h         强制采集 1H 数据
  --daily      强制采集日线数据
  --validate   仅验证数据完整性和正确性
  --backfill   补齐历史数据缺口

用法:
  python scripts/data_management.py              # 自动模式
  python scripts/data_management.py --1h         # 强制 1H 采集
  python scripts/data_management.py --daily      # 强制日线采集
  python scripts/data_management.py --validate   # 仅验证
  python scripts/data_management.py --backfill   # 补齐缺口
"""

import json
import sqlite3
import subprocess
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FM_ROOT = SCRIPT_DIR.parent
DB_DIR = FM_ROOT / "db"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES, DEFAULT_SYMBOLS

# 数据量要求
MIN_DAILY_ROWS = 250     # 日线预测需要 250 日 context
MIN_1H_ROWS = 480        # 1H 级联需要 480 根 K 线
# 验证阈值
MAX_NULL_RATIO = 0.01    # NULL close_price 比例 > 1% 告警
MAX_GAP_DAYS = 5         # 日线最大间隔天数（交易日除外）
PRICE_CHANGE_LIMIT = 0.2 # 单日涨跌超 20% 视为异常
MAX_1H_GAP_HOURS = 20    # 1H 最大间隔小时（无夜盘品种隔夜 19h 正常）


def get_session_type() -> str:
    """判断当前交易时段。

    Returns: 'day', 'night', 'post_close', 'off_hours'
    """
    now = datetime.now()
    weekday = now.weekday()
    h = now.hour

    if weekday >= 5:
        return "off_hours"
    if 9 <= h < 15:
        return "day"
    if h == 15:
        return "post_close"
    if 21 <= h <= 23 or 0 <= h < 3:
        return "night"
    return "off_hours"


# ── 数据采集 ──────────────────────────────────────────

def _timeout_for(script_name: str, n_symbols: int) -> int:
    """按品种数动态超时（秒），带上下限，避免全品种 300s 假失败。"""
    n = max(1, int(n_symbols))
    if script_name == "collect_1h.py":
        return min(3600, max(600, 45 * n))
    if script_name == "pull_history_1h.py":
        return min(3600, max(600, 60 * n))
    if script_name == "daily_update.py":
        return min(3600, max(900, 50 * n))
    return min(3600, max(600, 45 * n))


def run_script(script_name: str, args: list[str] = None, timeout: int = 300) -> dict:
    """运行子脚本并捕获结果。cwd 固定 FM_ROOT，避免相对路径漂移。"""
    script = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script)] + (args or [])
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=FM_ROOT,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        has_output = len(stdout.strip()) > 10
        has_tqsdk_cleanup_error = (
            "Event loop is closed" in stderr or "Task was destroyed" in stderr
        )
        # 成功判定（根因：不可仅凭 stdout 非空）
        #  0 → 成功
        #  2 → 策略/guard 显式失败（如 future_bar_guard）
        #  其它非 0 + 仅 TqSdk 清理噪音且有业务输出 → 兼容为成功
        if proc.returncode == 0:
            success = True
        elif proc.returncode == 2:
            success = False
        elif has_tqsdk_cleanup_error and has_output:
            success = True
        else:
            success = False
        return {
            "script": script_name,
            "exit_code": proc.returncode,
            "timeout_s": timeout,
            "stdout_tail": stdout[-500:],
            "stderr_tail": stderr[-300:],
            "success": success,
        }
    except subprocess.TimeoutExpired:
        return {
            "script": script_name,
            "exit_code": -1,
            "success": False,
            "timeout_s": timeout,
            "stdout_tail": "",
            "stderr_tail": (
                f"超时 ({timeout}s)。建议直调: "
                f"python scripts/{script_name} ..."
            ),
        }
    except Exception as e:
        return {"script": script_name, "exit_code": -1, "success": False,
                "timeout_s": timeout, "stdout_tail": "", "stderr_tail": str(e)}


def collect_1h(symbols: list[str] = None) -> list[dict]:
    """采集 1H 数据。"""
    syms = symbols or DEFAULT_SYMBOLS
    n = len(syms)
    results = []

    # 1. 增量采集（从各合约）
    t1 = _timeout_for("collect_1h.py", n)
    print(f"[INFO] Starting 1H collection for {n} symbols (timeout set to {t1}s)...")
    r = run_script("collect_1h.py", syms, timeout=t1)
    results.append(r)

    # 2. 拉取主力连续历史 1H（{_MAIN} 合约，用于回测和精度对比）
    t2 = _timeout_for("pull_history_1h.py", n)
    print(f"[INFO] Starting pull_history_1h for {n} symbols (timeout set to {t2}s)...")
    r2 = run_script("pull_history_1h.py", syms, timeout=t2)
    results.append(r2)

    return results


def collect_daily(symbols: list[str] = None) -> list[dict]:
    """采集日线：委托 daily_update（内部唯一调用 future_bar_guard）。"""
    syms = symbols or DEFAULT_SYMBOLS
    n = len(syms)
    results = []

    t = _timeout_for("daily_update.py", n)
    print(f"[INFO] Starting daily_update for {n} symbols (timeout set to {t}s)...")
    # purge 唯一由 daily_update 内部 run_guard 执行，此处不再二次 purge
    r = run_script("daily_update.py", syms, timeout=t)
    results.append(r)
    return results


def backfill_gaps() -> list[dict]:
    """补齐日线 < 250 或 1H < 480 的品种。"""
    results = []
    short_daily = []
    short_1h = []

    for symbol in SYMBOL_NAMES:
        db_path = DB_DIR / f"futures_{symbol}.db"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM main_continuous_1d")
            daily_rows = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM kline_1h WHERE contract_code LIKE '%_MAIN'")
            main_1h_rows = cur.fetchone()[0]

            conn.close()

            if daily_rows < MIN_DAILY_ROWS:
                short_daily.append(symbol)
            if main_1h_rows < MIN_1H_ROWS:
                short_1h.append(symbol)
        except Exception:
            continue

    if short_daily:
        print(f"  日线不足 {MIN_DAILY_ROWS}: {', '.join(short_daily)}")
        r = run_script("daily_update.py", short_daily, timeout=300)
        results.append(r)

    if short_1h:
        print(f"  1H (MAIN) 不足 {MIN_1H_ROWS}: {', '.join(short_1h)}")
        r = run_script("pull_history_1h.py", short_1h, timeout=300)
        results.append(r)

    if not short_daily and not short_1h:
        print("  所有品种数据量充足")

    return results


# ── 数据验证 ──────────────────────────────────────────

def validate_all() -> dict:
    """对所有品种进行数据完整性和正确性验证。"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_symbols": 0,
        "healthy": 0,
        "issues": [],
        "symbols": {},
    }

    for symbol in SYMBOL_NAMES:
        db_path = DB_DIR / f"futures_{symbol}.db"
        if not db_path.exists():
            report["issues"].append({"symbol": symbol, "type": "missing_db"})
            continue

        report["total_symbols"] += 1
        sym_issues = []

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()

            # ── 1. 日线验证 ──

            # 行数
            cur.execute("SELECT COUNT(*) FROM main_continuous_1d")
            daily_rows = cur.fetchone()[0]
            if daily_rows < MIN_DAILY_ROWS:
                sym_issues.append({
                    "type": "daily_insufficient",
                    "detail": f"{daily_rows}/{MIN_DAILY_ROWS}",
                    "severity": "warning",
                })

            # NULL 检查
            cur.execute("""
                SELECT COUNT(*) FROM main_continuous_1d
                WHERE close_price IS NULL OR close_price = 0
            """)
            null_count = cur.fetchone()[0]
            null_ratio = null_count / daily_rows if daily_rows > 0 else 0
            if null_ratio > MAX_NULL_RATIO:
                sym_issues.append({
                    "type": "daily_null_close",
                    "detail": f"{null_count}/{daily_rows} ({null_ratio:.1%})",
                    "severity": "error",
                })

            # 数据间隔检查
            cur.execute("""
                SELECT dt FROM main_continuous_1d
                ORDER BY dt DESC LIMIT 10
            """)
            recent_dates = [row[0][:10] for row in cur.fetchall()]
            if len(recent_dates) >= 2:
                try:
                    d1 = datetime.strptime(recent_dates[0], "%Y-%m-%d")
                    d2 = datetime.strptime(recent_dates[1], "%Y-%m-%d")
                    gap = (d1 - d2).days
                    if gap > MAX_GAP_DAYS:
                        sym_issues.append({
                            "type": "daily_gap",
                            "detail": f"最新 {recent_dates[0]}，上一条 {recent_dates[1]}，间隔 {gap} 天",
                            "severity": "warning",
                        })
                except ValueError:
                    pass

            # 价格异常检查（单日涨跌超 20%）
            cur.execute("""
                SELECT dt, close_price, change_pct
                FROM main_continuous_1d
                WHERE change_pct IS NOT NULL
                ORDER BY dt DESC LIMIT 30
            """)
            for row in cur.fetchall():
                dt_str, price, change = row
                if abs(change) > PRICE_CHANGE_LIMIT * 100:
                    sym_issues.append({
                        "type": "price_spike",
                        "detail": f"{dt_str}: {change:+.1f}%",
                        "severity": "warning",
                    })
                    break  # 只报第一个

            # ── 2. 1H 验证 ──

            # kline_1h 行数（所有合约）
            cur.execute("SELECT COUNT(*) FROM kline_1h")
            total_1h = cur.fetchone()[0]

            # _MAIN 合约 1H 行数（用于级联预测）
            cur.execute("SELECT COUNT(*) FROM kline_1h WHERE contract_code LIKE '%_MAIN'")
            main_1h = cur.fetchone()[0]
            if main_1h < MIN_1H_ROWS:
                sym_issues.append({
                    "type": "1h_main_insufficient",
                    "detail": f"_MAIN: {main_1h}/{MIN_1H_ROWS}",
                    "severity": "warning",
                })

            # 1H NULL 检查
            cur.execute("""
                SELECT COUNT(*) FROM kline_1h
                WHERE contract_code LIKE '%_MAIN'
                  AND (close_price IS NULL OR close_price = 0)
            """)
            null_1h = cur.fetchone()[0]
            if main_1h > 0 and null_1h / main_1h > MAX_NULL_RATIO:
                sym_issues.append({
                    "type": "1h_null_close",
                    "detail": f"{null_1h}/{main_1h}",
                    "severity": "error",
                })

            # 1H 时间连续性检查
            cur.execute("""
                SELECT dt FROM kline_1h
                WHERE contract_code LIKE '%_MAIN'
                ORDER BY dt DESC LIMIT 5
            """)
            recent_1h = [row[0] for row in cur.fetchall()]
            if len(recent_1h) >= 2:
                # 检查最近两条是否在同一交易日（间隔应 ≤ 2 小时）
                try:
                    t1 = datetime.strptime(recent_1h[0][:16], "%Y-%m-%d %H:%M")
                    t2 = datetime.strptime(recent_1h[1][:16], "%Y-%m-%d %H:%M")
                    gap_hours = (t1 - t2).total_seconds() / 3600
                    if gap_hours > MAX_1H_GAP_HOURS:  # 超过阈值说明有数据缺失
                        sym_issues.append({
                            "type": "1h_gap",
                            "detail": f"最近: {recent_1h[0]} vs {recent_1h[1]}, 间隔 {gap_hours:.0f}h",
                            "severity": "warning",
                        })
                except ValueError:
                    pass

            # ── 3. 合约表验证 ──
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}

            if "contracts" in tables:
                cur.execute("SELECT COUNT(*) FROM contracts")
                contract_count = cur.fetchone()[0]
                if contract_count == 0:
                    sym_issues.append({
                        "type": "no_contracts",
                        "detail": "contracts 表为空",
                        "severity": "info",
                    })

            conn.close()

        except sqlite3.Error as e:
            sym_issues.append({"type": "db_error", "detail": str(e), "severity": "error"})

        # 汇总
        has_error = any(i["severity"] == "error" for i in sym_issues)
        has_warning = any(i["severity"] == "warning" for i in sym_issues)

        if not sym_issues:
            report["healthy"] += 1
        else:
            report["issues"].extend([
                {"symbol": symbol, **issue} for issue in sym_issues
            ])

        report["symbols"][symbol] = {
            "status": "error" if has_error else ("warning" if has_warning else "ok"),
            "issue_count": len(sym_issues),
            "issues": sym_issues,
        }

    return report


# ── 主入口 ──────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FM_a 数据管理")
    parser.add_argument("--auto", action="store_true", default=True, help="自动模式")
    parser.add_argument("--1h", dest="hourly", action="store_true", help="强制 1H 采集")
    parser.add_argument("--daily", action="store_true", help="强制日线采集")
    parser.add_argument("--validate", action="store_true", help="仅验证")
    parser.add_argument("--backfill", action="store_true", help="补齐历史缺口")
    parser.add_argument("--symbols", nargs="*", help="指定品种")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = get_session_type()
    symbols = args.symbols  # None = all DEFAULT_SYMBOLS

    print(f"# 📦 数据管理报告\n")
    print(f"**时间**: {now_str}  ")
    print(f"**时段**: {session}\n")

    results = {"collected": [], "validated": None}

    # 仅验证模式：无采集时仍做一次数据层卫生（唯一入口 run_guard）
    if args.validate:
        print("## 🧹 future_bar_guard（会话感知）\n")
        from data.future_bar_guard import run_guard
        guard = run_guard(symbols, quiet=False)
        results["guard"] = {
            "ok": guard.get("ok"),
            "max_legal": guard.get("max_legal"),
            "total_removed": guard.get("total_removed"),
            "errors": guard.get("errors"),
        }
        print("## 🔍 数据验证\n")
        report = validate_all()
        results["validated"] = report
        _print_validation_report(report)
        _output_json(results)
        if not guard.get("ok", False):
            sys.exit(2)
        return

    # 强制模式
    if args.hourly:
        print("## 📥 1H 数据采集\n")
        r = collect_1h(symbols)
        results["collected"].extend(r)
        _print_collection_results(r, "1H")

    if args.daily:
        print("\n## 📥 日线数据采集\n")
        r = collect_daily(symbols)
        results["collected"].extend(r)
        _print_collection_results(r, "日线")

    if args.backfill:
        print("\n## 🔧 补齐历史缺口\n")
        r = backfill_gaps()
        results["collected"].extend(r)
        _print_collection_results(r, "补齐")

    # 自动模式
    if args.auto and not args.hourly and not args.daily and not args.backfill:
        if session == "day":
            print("## 📥 日盘 1H 数据采集\n")
            r = collect_1h(symbols)
            results["collected"].extend(r)
            _print_collection_results(r, "1H")

        elif session == "night":
            print("## 📥 夜盘 1H 数据采集\n")
            r = collect_1h(symbols)
            results["collected"].extend(r)
            _print_collection_results(r, "1H")

        elif session == "post_close":
            print("## 📥 收盘后日线采集\n")
            r = collect_daily(symbols)
            results["collected"].extend(r)
            _print_collection_results(r, "日线")

            print("\n## 📥 收盘后 1H 数据采集\n")
            r2 = collect_1h(symbols)
            results["collected"].extend(r2)
            _print_collection_results(r2, "1H")

        else:
            print("> 非交易时段，仅验证数据\n")

        # 无论什么时段，都做验证
        print("\n## 🔍 数据验证\n")
        report = validate_all()
        results["validated"] = report
        _print_validation_report(report)

    _output_json(results)


def _print_collection_results(results: list[dict], label: str):
    """打印采集结果。"""
    if not results:
        print(f"  无采集任务\n")
        return
    print(f"| 脚本 | 状态 |")
    print(f"|------|:----:|")
    for r in results:
        icon = "✅" if r["success"] else "❌"
        print(f"| {r['script']} | {icon} |")
    print()


def _print_validation_report(report: dict):
    """打印验证报告。"""
    error_count = sum(1 for i in report["issues"] if i["severity"] == "error")
    warning_count = sum(1 for i in report["issues"] if i["severity"] == "warning")

    print(f"**验证结果**: {report['total_symbols']} 品种, "
          f"{report['healthy']} 健康, "
          f"{error_count} 错误, {warning_count} 告警\n")

    errors = [i for i in report["issues"] if i["severity"] == "error"]
    warnings = [i for i in report["issues"] if i["severity"] == "warning"]

    if errors:
        print("### ❌ 错误\n")
        for i in errors:
            print(f"- `{i['symbol']}` — {i['type']}: {i['detail']}")
        print()

    if warnings:
        print("### ⚠️ 告警\n")
        for i in warnings[:20]:  # 最多显示 20 条
            print(f"- `{i['symbol']}` — {i['type']}: {i['detail']}")
        if len(warnings) > 20:
            print(f"- ... 共 {len(warnings)} 条告警")
        print()

    if not errors and not warnings:
        print("✅ 所有品种数据完整且正确\n")


def _output_json(results: dict):
    """输出 JSON 摘要到 stderr。"""
    summary = {
        "collections": len(results.get("collected", [])),
        "collection_success": all(r["success"] for r in results.get("collected", [])),
    }
    if results.get("validated"):
        v = results["validated"]
        summary["validation"] = {
            "total": v["total_symbols"],
            "healthy": v["healthy"],
            "error_count": sum(1 for i in v["issues"] if i["severity"] == "error"),
            "warning_count": sum(1 for i in v["issues"] if i["severity"] == "warning"),
        }
    json.dump(summary, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

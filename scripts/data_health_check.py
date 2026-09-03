#!/usr/bin/env python3
"""
数据健康检查 — FM_a 期货版

扫描 db/ 下所有 futures_*.db，检查主力连续日线和 1H K 线数据完整性。

退出码: 0 = 全部健康, 1 = 存在问题
标准输出: 人类可读 Markdown
标准错误: 紧凑 JSON 摘要（供机器消费）
"""

import glob
import json
import os
import re
import sqlite3
import sys

# Windows UTF-8 输出修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径设置 ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
FM_ROOT = SCRIPT_DIR.parent
DB_DIR = FM_ROOT / "db"

# 导入 data/config.py 中的 SYMBOL_NAMES
sys.path.insert(0, str(FM_ROOT))
try:
    from data.config import SYMBOL_NAMES
except ImportError:
    SYMBOL_NAMES = {}


def check_db(db_path: Path) -> dict:
    """检查单个 SQLite 数据库，返回检查结果字典。"""
    result = {
        "file": db_path.name,
        "symbol": "",
        "name": "",
        "readable": False,
        "main_1d_exists": False,
        "kline_1h_exists": False,
        "contracts_exists": False,
        "main_1d_rows": 0,
        "kline_1h_rows": 0,
        "contract_count": 0,
        "latest_main_1d": None,
        "latest_1h": None,
        "null_close_count": 0,
        "errors": [],
    }

    # 从文件名提取 symbol: futures_rb.db -> rb
    m = re.match(r"futures_(.+)\.db$", db_path.name)
    if not m:
        result["errors"].append("无法从文件名解析品种代码 (期望 futures_*.db)")
        return result

    symbol = m.group(1)
    result["symbol"] = symbol
    result["name"] = SYMBOL_NAMES.get(symbol, "")

    # 1. 可读性
    try:
        with open(db_path, "rb") as f:
            f.read(16)
    except OSError as e:
        result["errors"].append(f"文件不可读: {e}")
        return result
    result["readable"] = True

    # 2. 连接数据库（m2 fix: 添加超时，防止 DB 锁等待）
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    except sqlite3.Error as e:
        result["errors"].append(f"连接失败: {e}")
        return result

    # 3. 获取所有表名
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cur.fetchall()}

    # 4. main_continuous_1d 检查（主力连续日线）
    if "main_continuous_1d" in tables:
        result["main_1d_exists"] = True
        try:
            cur.execute("SELECT COUNT(*) AS cnt FROM main_continuous_1d")
            result["main_1d_rows"] = cur.fetchone()["cnt"]

            cur.execute("SELECT dt FROM main_continuous_1d ORDER BY dt DESC LIMIT 1")
            row = cur.fetchone()
            result["latest_main_1d"] = row["dt"] if row else None

            # NULL close_price in last 30 rows
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM main_continuous_1d
                WHERE dt IN (SELECT dt FROM main_continuous_1d ORDER BY dt DESC LIMIT 30)
                  AND (close_price IS NULL OR close_price = 0)
            """)
            result["null_close_count"] = cur.fetchone()["cnt"]
        except sqlite3.Error as e:
            result["errors"].append(f"main_continuous_1d 查询失败: {e}")
    else:
        result["errors"].append("缺少 main_continuous_1d 表")

    # 5. kline_1h 检查（小时 K 线）
    if "kline_1h" in tables:
        result["kline_1h_exists"] = True
        try:
            cur.execute("SELECT COUNT(*) AS cnt FROM kline_1h")
            result["kline_1h_rows"] = cur.fetchone()["cnt"]

            cur.execute("SELECT dt FROM kline_1h ORDER BY dt DESC LIMIT 1")
            row = cur.fetchone()
            result["latest_1h"] = row["dt"] if row else None
        except sqlite3.Error as e:
            result["errors"].append(f"kline_1h 查询失败: {e}")
    else:
        result["errors"].append("缺少 kline_1h 表")

    # 6. contracts 检查（合约信息）
    if "contracts" in tables:
        result["contracts_exists"] = True
        try:
            cur.execute("SELECT COUNT(*) AS cnt FROM contracts")
            result["contract_count"] = cur.fetchone()["cnt"]
        except sqlite3.Error:
            pass

    conn.close()
    return result


def is_stale(dt_str: str, max_days: int = 3) -> bool:
    """判断日期字符串是否过期。

    期货周末无交易，日线数据 ≤3 个自然日算正常。
    支持日期时间格式 (2026-06-30 14:00:00) 和纯日期格式 (2026-06-30)。
    """
    if not dt_str:
        return True
    try:
        # 取前10个字符作为日期
        dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        cutoff = datetime.now() - timedelta(days=max_days)
        return dt < cutoff
    except ValueError:
        return True


def is_1h_stale(dt_str: str) -> bool:
    """判断 1H 数据是否过期。

    1H 数据应在当日交易时段内有更新。
    交易时段: 日盘 9:00-15:00, 夜盘 21:00-次日凌晨。

    m1 fix: 考虑夜盘跨日和周一场景:
    - 周一: 周五的数据算新鲜（周五夜盘到周六凌晨）
    - 周二~周五: 昨天夜盘数据也算新鲜（21:00 后）
    - 当前时间 < 9:00 时，昨天的数据也算新鲜
    """
    if not dt_str:
        return True
    try:
        dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        now = datetime.now()
        today = now.date()

        # 周末不检查 1H 陈旧度
        if now.weekday() >= 5:
            return False

        days_diff = (today - dt.date()).days

        # 周一: 允许 3 天前的数据（周五）
        if now.weekday() == 0:
            return days_diff > 3

        # 周二~周五: 允许 1 天前的数据（昨天夜盘）
        # 如果当前时间 < 9:00（日盘未开），允许 2 天前
        if now.hour < 9:
            return days_diff > 2

        return days_diff > 1
    except ValueError:
        return True


def format_status(result: dict) -> tuple[str, list[str]]:
    """返回 (状态标记, 问题列表)。"""
    issues = []

    if not result["readable"]:
        issues.append("❌ 文件不可读")
    if not result["main_1d_exists"]:
        issues.append("❌ 缺少 main_continuous_1d 表")
    if not result["kline_1h_exists"]:
        issues.append("❌ 缺少 kline_1h 表")
    if result["main_1d_exists"] and result["main_1d_rows"] == 0:
        issues.append("❌ main_continuous_1d 为空")
    if result["kline_1h_exists"] and result["kline_1h_rows"] == 0:
        issues.append("❌ kline_1h 为空")

    # 日线预测需要至少 250 日 context
    if result["main_1d_exists"] and 0 < result["main_1d_rows"] < 250:
        issues.append(f"⚠️  日线数据不足 ({result['main_1d_rows']}/250)")

    # 日线陈旧度 (≤3 个自然日)
    if result["main_1d_exists"] and is_stale(result["latest_main_1d"], max_days=3):
        issues.append(f"⚠️  日线数据过期: {result['latest_main_1d']}")

    # 1H 陈旧度 (当日)
    if result["kline_1h_exists"] and is_1h_stale(result["latest_1h"]):
        issues.append(f"⚠️  1H 数据过期: {result['latest_1h']}")

    if result["null_close_count"] > 0:
        issues.append(f"⚠️  近30行有 {result['null_close_count']} 条 NULL/0 close_price")

    status = "✅" if not issues else ("🟡" if any("⚠️" in i for i in issues) else "❌")
    return status, issues


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# 数据健康检查报告 (FM_a 期货版)\n")
    print(f"**扫描时间**: {now_str}  ")
    print(f"**数据库目录**: `{DB_DIR}`\n")

    if not DB_DIR.exists():
        print(f"❌ 数据库目录不存在: `{DB_DIR}`\n")
        summary = {"status": "error", "message": "DB_DIR not found", "databases": []}
        print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    # 扫描所有 futures_*.db 文件
    db_files = sorted(glob.glob(str(DB_DIR / "futures_*.db")))
    if not db_files:
        print("❌ 未找到任何 `futures_*.db` 文件\n")
        summary = {"status": "error", "message": "no db files found", "databases": []}
        print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    results = []
    for db_path_str in db_files:
        results.append(check_db(Path(db_path_str)))

    # 检查缺失品种
    found_symbols = {r["symbol"] for r in results}
    # 只检查默认跟踪品种 (有 DB 的品种才算在跟踪)
    # 但如果有 config 中定义但没 DB 的，也报告
    expected_symbols = set(SYMBOL_NAMES.keys())
    missing_symbols = expected_symbols - found_symbols

    # ── Markdown 输出 ──────────────────────────────────────────────────────────
    print(f"**发现数据库**: {len(results)} 个  ")
    if missing_symbols:
        print(f"**缺失品种**: {len(missing_symbols)} 个 (config 中有定义但无 DB)")
    print()

    # 表头
    print("| 状态 | 品种 | 名称 | 日线行数 | 1H行数 | 合约数 | 最新日线 | 最新1H | 问题 |")
    print("|------|------|------|---------|--------|--------|---------|--------|------|")

    total_issues = 0
    summary_list = []

    for r in results:
        status, issues = format_status(r)
        issue_str = "<br>".join(issues) if issues else "—"
        if issues:
            total_issues += 1

        print(
            f"| {status} | `{r['symbol']}` | {r['name']} "
            f"| {r['main_1d_rows']} | {r['kline_1h_rows']} "
            f"| {r['contract_count']} "
            f"| {r['latest_main_1d'] or '—'} | {r['latest_1h'] or '—'} "
            f"| {issue_str} |"
        )

        summary_list.append({
            "symbol": r["symbol"],
            "name": r["name"],
            "status": "healthy" if not issues else ("warning" if status == "🟡" else "error"),
            "main_1d_rows": r["main_1d_rows"],
            "kline_1h_rows": r["kline_1h_rows"],
            "contract_count": r["contract_count"],
            "latest_main_1d": r["latest_main_1d"],
            "latest_1h": r["latest_1h"],
            "null_close_count": r["null_close_count"],
            "issues": issues,
        })

    # 缺失品种
    if missing_symbols:
        print("\n## ⚠️  缺失的品种数据库\n")
        for sym in sorted(missing_symbols):
            name = SYMBOL_NAMES.get(sym, "")
            print(f"- `{sym}` ({name})")

    # 汇总
    healthy_count = len(results) - total_issues
    print(f"\n## 汇总\n")
    print(f"- 总数据库: {len(results)}")
    print(f"- 健康: {healthy_count}")
    print(f"- 存在问题: {total_issues}")
    print(f"- 缺失品种: {len(missing_symbols)}")

    # 退出码
    has_problems = total_issues > 0 or len(missing_symbols) > 0
    print()
    if has_problems:
        print("**结果**: ❌ 存在数据问题，需要关注。")
    else:
        print("**结果**: ✅ 全部健康。")

    # ── JSON 输出到 stderr ──────────────────────────────────────────────────────
    summary = {
        "scan_time": now_str,
        "db_dir": str(DB_DIR),
        "total": len(results),
        "healthy": healthy_count,
        "issues": total_issues,
        "missing": sorted(list(missing_symbols)),
        "databases": summary_list,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)

    sys.exit(1 if has_problems else 0)


if __name__ == "__main__":
    main()

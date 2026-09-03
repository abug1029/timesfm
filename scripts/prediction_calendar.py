#!/usr/bin/env python3
"""
prediction_calendar.py — FM_a 交易日历

显示当日交易时段状态、交割预警、夜盘品种列表。

用法:
    python scripts/prediction_calendar.py
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
DB_DIR = FM_ROOT / "db"

sys.path.insert(0, str(FM_ROOT))
from data.config import SYMBOL_NAMES, SYMBOL_EXCHANGE_MAP


# 夜盘品种（有夜盘的品种列表）
# 大部分期货品种都有夜盘，这里列出例外（无夜盘的品种）
NO_NIGHT_SESSION = {"jd", "lh", "cj"}  # 鸡蛋、生猪、红枣无夜盘


def get_session_status() -> dict:
    """判断当前处于哪个交易时段。"""
    now = datetime.now()
    weekday = now.weekday()
    h, m = now.hour, now.minute
    t = h + m / 60.0

    if weekday >= 5:
        return {"status": "休市", "next": "周一 09:00", "color": "🔴"}

    if 8 <= t < 9:
        return {"status": "盘前", "next": "09:00 开盘", "color": "🟡"}
    elif 9 <= t < 10.25:
        return {"status": "日盘第一节", "next": "10:15 休息", "color": "🟢"}
    elif 10.25 <= t < 10.5:
        return {"status": "午休", "next": "10:30 继续", "color": "🟡"}
    elif 10.5 <= t < 11.5:
        return {"status": "日盘第二节", "next": "11:30 午休", "color": "🟢"}
    elif 11.5 <= t < 13.5:
        return {"status": "午间休市", "next": "13:30 开盘", "color": "🟡"}
    elif 13.5 <= t < 15:
        return {"status": "日盘第三节", "next": "15:00 收盘", "color": "🟢"}
    elif 15 <= t < 21:
        return {"status": "盘后", "next": "21:00 夜盘", "color": "🟡"}
    elif 21 <= t < 23.99:
        return {"status": "夜盘", "next": "次日 09:00", "color": "🟢"}
    elif 0 <= t < 2.5:
        # 凌晨属于前一日夜盘
        return {"status": "夜盘（尾段）", "next": "09:00 日盘", "color": "🟢"}
    else:
        return {"status": "未知", "next": "—", "color": "⚪"}


def check_delivery_warnings() -> list[dict]:
    """检查交割月临近的品种。"""
    now = datetime.now()
    current_ym = now.year * 100 + now.month
    warnings = []

    for symbol in SYMBOL_NAMES:
        db_path = DB_DIR / f"futures_{symbol}.db"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            # 查找主力合约的交割月
            cur.execute("""
                SELECT contract_code, contract_month, delivery_year
                FROM contracts
                WHERE is_active = 1 AND product = ?
                ORDER BY is_main DESC, contract_code ASC
                LIMIT 5
            """, (symbol.lower(),))
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                contract_code, contract_month, delivery_year = row
                if delivery_year and contract_month:
                    delivery_ym = delivery_year * 100 + contract_month
                    months_left = (delivery_ym - current_ym)
                    if 0 < months_left <= 2:
                        warnings.append({
                            "symbol": symbol,
                            "name": SYMBOL_NAMES.get(symbol, ""),
                            "contract": contract_code,
                            "delivery": f"{delivery_year}/{contract_month:02d}",
                            "months_left": months_left,
                        })
                    elif months_left <= 0 and months_left >= -1:
                        warnings.append({
                            "symbol": symbol,
                            "name": SYMBOL_NAMES.get(symbol, ""),
                            "contract": contract_code,
                            "delivery": f"{delivery_year}/{contract_month:02d}",
                            "months_left": 0,
                        })
        except Exception:
            continue

    return warnings


def main():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = get_session_status()
    delivery_warnings = check_delivery_warnings()

    print(f"# 📅 交易日历\n")
    print(f"**时间**: {now_str}  ")
    print(f"**当前时段**: {session['color']} {session['status']}  ")
    print(f"**下一时段**: {session['next']}\n")

    # 夜盘品种
    night_symbols = [s for s in SYMBOL_NAMES if s not in NO_NIGHT_SESSION]
    no_night = [s for s in SYMBOL_NAMES if s in NO_NIGHT_SESSION]

    print(f"## 品种分类\n")
    print(f"- **有夜盘**: {len(night_symbols)} 个品种")
    print(f"- **无夜盘**: {len(no_night)} 个 — {', '.join(f'{s}({SYMBOL_NAMES[s]})' for s in no_night)}\n")

    # 交割预警
    if delivery_warnings:
        print(f"## ⚠️ 交割预警 ({len(delivery_warnings)} 个)\n")
        print("| 品种 | 名称 | 合约 | 交割月 | 剩余月数 |")
        print("|------|------|------|--------|:--------:|")
        for w in sorted(delivery_warnings, key=lambda x: x["months_left"]):
            urgency = "🔴" if w["months_left"] == 0 else "🟡"
            print(
                f"| {urgency} `{w['symbol']}` | {w['name']} "
                f"| {w['contract']} | {w['delivery']} "
                f"| {w['months_left']} |"
            )
    else:
        print("## ✅ 无交割预警\n")

    # JSON 输出到 stderr
    json.dump({
        "time": now_str,
        "session": session["status"],
        "next_session": session["next"],
        "delivery_warnings": delivery_warnings,
        "total_symbols": len(SYMBOL_NAMES),
        "night_session_count": len(night_symbols),
    }, sys.stderr, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

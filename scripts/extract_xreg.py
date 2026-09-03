"""
从 main_continuous_1d 提取技术指标到 xreg_factors 表作为协变量

支持的指标因子:
  rsi6, rsi12, rsi24        — RSI 相对强弱
  macd_dif, macd_dea, macd_bar — MACD
  ma5, ma10, ma20, ma60     — 均线
  boll_upper, boll_mid, boll_lower — 布林带
  atr14                      — 波动率
  oi_change, oi_trend_5d, volume_oi_ratio, oi_signal — 持仓分析

用法:
  python scripts/extract_xreg.py              # 全部品种
  python scripts/extract_xreg.py cf rb        # 指定品种
  python scripts/extract_xreg.py --all-indicators  # 全部指标（默认只提取 RSI）
"""

import sys
import argparse
import sqlite3
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.db import get_conn
from data.config import DEFAULT_SYMBOLS

# RSI 因子（默认提取）
RSI_FACTORS = ["rsi6", "rsi12", "rsi24"]

# 全部可用因子
ALL_FACTOR_GROUPS = {
    "rsi": ["rsi6", "rsi12", "rsi24"],
    "macd": ["macd_dif", "macd_dea", "macd_bar"],
    "ma": ["ma5", "ma10", "ma20", "ma60"],
    "boll": ["boll_upper", "boll_mid", "boll_lower"],
    "volatility": ["atr14"],
    "oi": ["oi_change", "oi_trend_5d", "volume_oi_ratio"],
    "ccl": ["ccl_value"],
}


def extract_factors(symbol: str, factors: list[str]) -> int:
    """从 main_continuous_1d 提取指标到 xreg_factors"""
    conn = get_conn(symbol)
    total = 0

    for factor in factors:
        # 读取该因子的数据
        sql = f"SELECT dt, {factor} FROM main_continuous_1d WHERE {factor} IS NOT NULL ORDER BY dt"
        df = pd.read_sql_query(sql, conn)

        if df.empty:
            print(f"  {symbol.upper()}/{factor}: 无数据")
            continue

        # 批量写入 xreg_factors
        rows = [(row["dt"], symbol, factor, float(row[factor]))
                for _, row in df.iterrows()]

        try:
            conn.executemany(
                "INSERT OR REPLACE INTO xreg_factors (dt, symbol, factor_name, factor_value) VALUES (?, ?, ?, ?)",
                rows
            )
            conn.commit()
            total += len(rows)
            print(f"  {symbol.upper()}/{factor}: {len(rows)} 条")
        except Exception as e:
            print(f"  {symbol.upper()}/{factor}: 失败 - {e}")
            conn.rollback()

    conn.close()
    return total


def main():
    parser = argparse.ArgumentParser(description="提取技术指标到 xreg_factors")
    parser.add_argument("symbols", nargs="*", help="品种代码（不填则全部）")
    parser.add_argument("--all-indicators", action="store_true",
                        help="提取全部指标（默认只提取 RSI）")
    args = parser.parse_args()

    # 确定品种
    if args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    if not symbols:
        print("无数据库")
        return

    # 确定因子
    if args.all_indicators:
        factors = []
        for group in ALL_FACTOR_GROUPS.values():
            factors.extend(group)
    else:
        factors = RSI_FACTORS

    print(f"品种: {len(symbols)} 个")
    print(f"因子: {factors}")
    print()

    grand_total = 0
    for sym in symbols:
        count = extract_factors(sym, factors)
        grand_total += count

    print(f"\n合计: {grand_total} 条协变量写入 xreg_factors")


if __name__ == "__main__":
    main()

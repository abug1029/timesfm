"""
从 main_continuous_1d 提取技术指标到 xreg_factors 表作为协变量

支持的指标因子:
  rsi6, rsi12, rsi24        — RSI 相对强弱
  macd_dif, macd_dea, macd_bar — MACD
  ma5, ma10, ma20, ma60     — 均线
  boll_upper, boll_mid, boll_lower — 布林带
  atr14                      — 波动率
  oi_gated_momentum          — OI 门控动量 (index_continuous_1d 总持仓 + main 价格,
                               经 cascade.oi_gated_momentum 计算, gated 评估口径)
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
    "oi_gated": ["oi_gated_momentum"],
}


def extract_factors(symbol: str, factors: list[str]) -> int:
    """从 main_continuous_1d 提取指标到 xreg_factors"""
    conn = get_conn(symbol)
    total = 0

    for factor in factors:
        # oi_gated_momentum: 特殊注册路径 (双表数据源 + 冻结参数模块计算)
        if factor == "oi_gated_momentum":
            total += extract_oi_gated_momentum(symbol, conn)
            continue
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


def extract_oi_gated_momentum(symbol: str, conn=None) -> int:
    """注册 oi_gated_momentum 协变量 (spec §4 调用方)。

    数据源: main_continuous_1d.close_price + index_continuous_1d.open_interest
    (KQ.i@m 全市场总持仓), 经 cascade.oi_gated_momentum.compute_oi_gated_momentum
    计算 (冻结默认参数, 禁运行时注入) → xreg_factors。

    日历对齐 (spec §3.4): 价格日历为基准 left join; 持仓缺失日不跨接、不 ffill —
    缺失日及其后定标窗口信号 NaN → 不落表 (fail-closed)。
    """
    from cascade.oi_gated_momentum import compute_oi_gated_momentum

    if conn is None:
        conn = get_conn(symbol)
    price_df = pd.read_sql_query(
        "SELECT dt, close_price FROM main_continuous_1d WHERE close_price IS NOT NULL ORDER BY dt",
        conn)
    oi_df = pd.read_sql_query(
        "SELECT dt, open_interest FROM index_continuous_1d ORDER BY dt", conn)
    if price_df.empty or oi_df.empty:
        print(f"  {symbol.upper()}/oi_gated_momentum: 无数据")
        return 0
    merged = price_df.merge(oi_df, on="dt", how="left")
    price = pd.Series(merged["close_price"].values,
                      index=pd.DatetimeIndex(merged["dt"]))
    total_oi = pd.Series(merged["open_interest"].values, index=price.index)
    signal = compute_oi_gated_momentum(price, total_oi)
    rows = [
        (dt, symbol, "oi_gated_momentum", float(v))
        for dt, v in zip(merged["dt"], signal.values)
        if not pd.isna(v)
    ]
    if not rows:
        print(f"  {symbol.upper()}/oi_gated_momentum: 无有效信号")
        return 0
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO xreg_factors (dt, symbol, factor_name, factor_value) VALUES (?, ?, ?, ?)",
            rows)
        conn.commit()
        print(f"  {symbol.upper()}/oi_gated_momentum: {len(rows)} 条")
        return len(rows)
    except Exception as e:
        print(f"  {symbol.upper()}/oi_gated_momentum: 失败 - {e}")
        conn.rollback()
        return 0


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

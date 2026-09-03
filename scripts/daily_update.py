"""
每日增量更新脚本

用法:
  python scripts/daily_update.py              # 所有品种
  python scripts/daily_update.py cf rb        # 指定品种
  python scripts/daily_update.py --full       # 强制全量 (回退到旧行为)
"""

import sys
import argparse
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.config import DEFAULT_SYMBOLS
from data.tqsdk_fetcher import UnifiedFetcher
from data.indicator_calculator import IndicatorCalculator
from data.data_store import DataStore
from data.main_chain import MainChainBuilder


# XReg 指标因子列表 (与 predict.py 保持一致)
XREG_FACTORS = [
    "rsi6", "rsi12", "rsi24",
    "macd_dif", "macd_dea", "macd_bar",
    "ma5", "ma10", "ma20", "ma60",
    "boll_upper", "boll_mid", "boll_lower",
    "atr14",
    "oi_change", "oi_trend_5d", "volume_oi_ratio",
    "ccl_value",
]


def collect_daily_klines_incremental(symbol, fetcher, calculator, store, full=False):
    """增量采集主力连续合约日线 (_CONT)"""
    cont_code = f"{symbol.upper()}_CONT"
    df = fetcher.get_main_continuous_kline(symbol, dur_sec=86400, data_length=3000)
    if df.empty:
        return 0

    # TqSdk 返回 dt 列, 统一为 date
    if "dt" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"dt": "date"})

    # 修复 (2026-09-01): 先在全量历史上算指标再截断新行。
    # 原逻辑先过滤 date > last_date 再 calculate_all, 滚动指标 (ma20/ema/macd/kdj/boll/atr/cci)
    # 在只有 1~2 行的切片上永远为 NaN —— kline_1d 长回看指标列自 2026-07-10 起 NULL 的根因。
    df['contract_code'] = cont_code
    df = calculator.calculate_all(df)

    if not full:
        last_date = store.get_latest_date(cont_code)
        if last_date:
            df = df[df["date"] > last_date]

    if df.empty:
        return 0

    # IndicatorCalculator 需要 open/close 列名；入库前再 rename
    df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})
    stored = store.store_klines(cont_code, df)

    return stored


def fetch_main_continuous_incremental(symbol, fetcher, calculator, store, full=False):
    """同步主力连续日线数据 (kline_1d _CONT → main_continuous_1d)

    Returns: (stored_count, new_dates_list)
    """
    try:
        builder = MainChainBuilder(symbol)
        rebuilt = builder.build()
        return rebuilt, []
    except Exception as e:
        print(f"  [WARN] MainChainBuilder 失败: {e}")
        return 0, []


def backfill_ccl_incremental(symbol, store, new_dates=None):
    """只给最新的行计算CCL (需要足够lookback)"""
    # 读最后60行 (足够计算所有指标的lookback)
    df = pd.read_sql_query(
        "SELECT dt, open_price, high, low, close_price, volume, open_interest "
        "FROM main_continuous_1d ORDER BY dt DESC LIMIT 60",
        store.conn
    )
    if df.empty:
        return 0
    df = df.sort_values("dt").reset_index(drop=True)

    calc = IndicatorCalculator()
    df_calc = df.rename(columns={"open_price": "open", "close_price": "close", "dt": "date"})
    df_calc = calc.calculate_all(df_calc)

    # 如果指定了 new_dates, 只更新这些行
    if new_dates:
        df_calc = df_calc[df_calc["date"].isin(new_dates)]

    updates = []
    for _, row in df_calc.iterrows():
        cv = row.get("ccl_value")
        if cv is not None and not pd.isna(cv):
            updates.append((float(cv), row.get("ccl_label", ""), row["date"]))

    if updates:
        store.conn.executemany(
            "UPDATE main_continuous_1d SET ccl_value = ?, ccl_label = ? WHERE dt = ?",
            updates
        )
        store.conn.commit()
    return len(updates)


def extract_xreg_incremental(symbol, store, dates=None):
    """只提取指定日期的因子"""
    total = 0
    for factor in XREG_FACTORS:
        try:
            if dates:
                placeholders = ",".join(["?"] * len(dates))
                df = pd.read_sql_query(
                    f"SELECT dt, {factor} FROM main_continuous_1d "
                    f"WHERE dt IN ({placeholders}) AND {factor} IS NOT NULL",
                    store.conn, params=list(dates)
                )
            else:
                df = pd.read_sql_query(
                    f"SELECT dt, {factor} FROM main_continuous_1d WHERE {factor} IS NOT NULL",
                    store.conn
                )

            if df.empty:
                continue

            rows = [(row["dt"], symbol, factor, float(row[factor]))
                    for _, row in df.iterrows()]
            store.conn.executemany(
                "INSERT OR REPLACE INTO xreg_factors (dt, symbol, factor_name, factor_value) VALUES (?, ?, ?, ?)",
                rows
            )
            store.conn.commit()
            total += len(rows)
        except Exception as e:
            print(f"    [WARN] {factor} 提取失败: {e}")
    return total


def collect_1h_main_only(symbol, fetcher, calculator, store):
    """只采集主力合约的 1H 数据 (TqSdk)

    2026-07-02: 数据已切换为 _CONT 格式, 直接采集 _MAIN 到 kline_1h。
    """
    # 使用 _MAIN 标记存储主力连续 1H
    main_code = f"{symbol.upper()}_MAIN"
    df = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
    if not df.empty:
        df = df.rename(columns={'dt': 'date'})
        df['contract_code'] = main_code
        df = calculator.calculate_all(df)
        df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})
        # 清空旧 _MAIN 数据, 写入新数据
        store.conn.execute('DELETE FROM kline_1h WHERE contract_code = ?', (main_code,))
        return store.store_klines_1h(main_code, df)

    return 0


def update_symbol(symbol, fetcher, calculator, full=False):
    """增量更新单个品种"""
    print(f"\n{'='*60}")
    print(f"[{symbol.upper()}] 增量更新")
    print(f"{'='*60}")

    summary = {}

    with DataStore(symbol) as store:
        # 1. 合约日线 (增量)
        print(f"  [1/5] 合约日线...")
        kline_new = collect_daily_klines_incremental(symbol, fetcher, calculator, store, full)
        summary["kline_1d"] = kline_new
        print(f"    新增 {kline_new} 条" if kline_new else "    无新数据")

        # 2. 主力连续 (增量)
        print(f"  [2/5] 主力连续...")
        main_new, new_dates = fetch_main_continuous_incremental(symbol, fetcher, calculator, store, full)
        summary["main_continuous"] = main_new
        print(f"    新增 {main_new} 条" if main_new else "    无新数据")

        # 3. CCL 增量更新 (仅当主链有新数据时)
        if main_new > 0:
            print(f"  [3/5] CCL 指标...")
            ccl_count = backfill_ccl_incremental(symbol, store, new_dates)
            summary["ccl"] = ccl_count
            print(f"    更新 {ccl_count} 条" if ccl_count else "    无新数据")
        else:
            summary["ccl"] = 0
            print(f"  [3/5] CCL 指标... 跳过 (主链无新数据)")

        # 4. XReg 因子提取 (增量, 仅当主链有新数据时)
        if main_new > 0:
            print(f"  [4/5] XReg 因子...")
            xreg_count = extract_xreg_incremental(symbol, store, new_dates)
            summary["xreg"] = xreg_count
            print(f"    新增 {xreg_count} 条" if xreg_count else "    无新数据")
        else:
            summary["xreg"] = 0
            print(f"  [4/5] XReg 因子... 跳过 (主链无新数据)")

        # 5. 1H K线 (主力合约, 仅当主链有新数据时)
        if main_new > 0:
            print(f"  [5/5] 1H K线 (主力合约)...")
            h1_count = collect_1h_main_only(symbol, fetcher, calculator, store)
            summary["kline_1h"] = h1_count
            print(f"    新增 {h1_count} 条" if h1_count else "    无新数据")
        else:
            summary["kline_1h"] = 0
            print(f"  [5/5] 1H K线... 跳过 (主链无新数据)")

        # 更新元数据: 主链重建 (从 kline 数据, 增量)
        if kline_new > 0:
            print(f"  [*] 重建主链 (从 kline 数据)...")
            builder = MainChainBuilder(symbol)
            builder.build()

    return summary


def main():
    parser = argparse.ArgumentParser(description="每日增量更新")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--all", action="store_true", help="所有已采集品种")
    parser.add_argument("--full", action="store_true", help="强制全量更新")
    args = parser.parse_args()

    if args.all:
        symbols = list(DEFAULT_SYMBOLS)
        if not symbols:
            print("暂无数据，请先运行 collect")
            return
    elif args.symbols:
        symbols = [s.lower() for s in args.symbols]
    else:
        # 默认: 核心品种池
        symbols = list(DEFAULT_SYMBOLS)
        if not symbols:
            print("暂无数据库")
            return

    fetcher = UnifiedFetcher()
    calculator = IndicatorCalculator()

    print(f"品种: {', '.join(s.upper() for s in symbols)}")
    print(f"模式: {'全量' if args.full else '增量'}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    all_summaries = {}
    for symbol in symbols:
        try:
            summary = update_symbol(symbol, fetcher, calculator, args.full)
            all_summaries[symbol] = summary
        except Exception as e:
            print(f"  [ERROR] {symbol.upper()}: {e}")
            all_summaries[symbol] = {"error": str(e)}

    # 打印汇总表
    print(f"\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    print(f"| 品种 | 日线 | 主链 | CCL | XReg | 1H |")
    print(f"|------|-----:|-----:|----:|-----:|---:|")
    for sym, summary in all_summaries.items():
        if "error" in summary:
            print(f"| {sym.upper()} | ERROR: {summary['error']} |")
        else:
            print(
                f"| {sym.upper()} "
                f"| {summary.get('kline_1d', 0)} "
                f"| {summary.get('main_continuous', 0)} "
                f"| {summary.get('ccl', 0)} "
                f"| {summary.get('xreg', 0)} "
                f"| {summary.get('kline_1h', 0)} |"
            )

    # 数据层唯一 purge 入口（会话感知交易日上界；失败 → 非零退出）
    from data.future_bar_guard import run_guard

    print(f"\n{'='*60}")
    print("future_bar_guard（会话感知 · 幽灵 K 线）")
    print(f"{'='*60}")
    guard = run_guard(symbols, quiet=False)
    if not guard.get("ok", False):
        print("[ERROR] future_bar_guard failed — see errors above")
        raise SystemExit(2)

    print(f"\n完成!")


if __name__ == "__main__":
    main()

"""CLI 命令行入口

用法:
  python -m data.cli collect rb              # 采集 RB 主力连续合约
  python -m data.cli collect rb cf p         # 多品种
  python -m data.cli collect --all           # 所有品种
  python -m data.cli status                  # 所有品种状态
  python -m data.cli status rb               # RB 详细状态
  python -m data.cli contracts rb            # 查看合约列表
  python -m data.cli query rb --days 30      # 查询主链数据
  python -m data.cli timesfm rb --days 100   # 导出 TimesFM 输入

数据架构 (2026-07-02):
  kline_1d / main_continuous_1d: 主力连续合约 _CONT 格式
  kline_1h: 主力连续 1H _MAIN 格式
  数据源: TqSdk KQ.m@ (主力连续合约)
"""

import sys
import os
import re
import argparse
from pathlib import Path

# 确保能 import data 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_collect(args):
    """采集数据"""
    from data.config import DEFAULT_SYMBOLS, get_name
    from data.tqsdk_fetcher import UnifiedFetcher
    from data.indicator_calculator import IndicatorCalculator
    from data.data_store import DataStore
    from data.main_chain import MainChainBuilder

    symbols = args.symbols
    if args.all:
        symbols = DEFAULT_SYMBOLS

    fetcher = UnifiedFetcher(prefer_tqsdk=True)
    calculator = IndicatorCalculator()

    for symbol in symbols:
        symbol = symbol.lower()
        name = get_name(symbol)
        print(f"\n{'='*60}")
        print(f"[采集] {symbol.upper()} ({name})")
        print(f"{'='*60}")

        # [H2] 使用 context manager 防止连接泄漏
        with DataStore(symbol) as store:

            # 1. 采集主力连续合约日线 (_CONT)
            print(f"\n[1/3] 采集主力连续日线 (_CONT)...")
            cont_code = f"{symbol.upper()}_CONT"
            df = fetcher.get_main_continuous_kline(symbol, dur_sec=86400, data_length=3000)
            if df.empty:
                print(f"  [SKIP] 无法获取日线数据")
            else:
                # 统一列名: TqSdk 返回 dt, 统一为 date
                if "dt" in df.columns and "date" not in df.columns:
                    df = df.rename(columns={"dt": "date"})

                # 增量模式: 只追加新数据
                if not args.force:
                    latest_db = store.get_latest_date(cont_code)
                    if latest_db:
                        df = df[df["date"] > latest_db]

                if df.empty:
                    print(f"  {cont_code}: 已是最新")
                else:
                    df['contract_code'] = cont_code
                    df = calculator.calculate_all(df)
                    if args.force:
                        store.conn.execute('DELETE FROM kline_1d WHERE contract_code = ?', (cont_code,))
                    stored = store.store_klines(cont_code, df)
                    latest_date = df["date"].iloc[-1] if not df.empty else "?"
                    print(f"  {cont_code}: +{stored} 条 (至 {latest_date})")

            # 2. 主链同步 (kline_1d _CONT → main_continuous_1d)
            print(f"\n[2/3] 同步主链...")
            builder = MainChainBuilder(symbol)
            rebuilt = builder.build()
            print(f"  主链同步: {rebuilt} 条")

            # 3. 采集 1H K线 (主力连续 → _MAIN)
            print(f"\n[3/3] 采集 1H K线...")
            main_code = f"{symbol.upper()}_MAIN"
            df_1h = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
            if not df_1h.empty:
                df_1h = df_1h.rename(columns={'dt': 'date'})
                df_1h['contract_code'] = main_code
                df_1h = calculator.calculate_all(df_1h)
                df_1h = df_1h.rename(columns={'open': 'open_price', 'close': 'close_price'})
                store.conn.execute('DELETE FROM kline_1h WHERE contract_code = ?', (main_code,))
                h1_stored = store.store_klines_1h(main_code, df_1h)
                print(f"  1H 写入: {h1_stored} 条 ({main_code})")
            else:
                print(f"  [SKIP] 无法获取 1H 数据")

            # 状态
            status = store.get_status()
            print(f"\n  K线合约数:   {status['contracts']}")
            print(f"  K线记录:     {status['kline_records']}")
            print(f"  主链记录:    {status['main_continuous_records']}")
            print(f"  最新日期:    {status['latest_date']}")

    # 关闭 TqSdk 连接
    fetcher.close()

    print(f"\n{'='*60}")
    print("采集完成")
    print(f"{'='*60}")


def cmd_status(args):
    """查看数据状态"""
    from data.data_store import DataStore
    from data.config import get_name, DEFAULT_SYMBOLS

    if args.symbols:
        for symbol in args.symbols:
            symbol = symbol.lower()
            with DataStore(symbol) as store:
                status = store.get_status()
                name = get_name(symbol)
                print(f"\n{'─'*50}")
                print(f"  {symbol.upper()} ({name})")
                print(f"{'─'*50}")
                print(f"  K线合约数:    {status['contracts']}")
                print(f"  K线记录:      {status['kline_records']}")
                print(f"  主链记录:     {status['main_continuous_records']}")
                print(f"  最新日期:     {status['latest_date'] or '无数据'}")
                if status["contract_list"]:
                    print(f"  合约列表:     {', '.join(c.upper() for c in status['contract_list'][:10])}")
                    if len(status["contract_list"]) > 10:
                        print(f"                ... 共 {len(status['contract_list'])} 个")
    else:
        # 全部核心品种
        dbs = list(DEFAULT_SYMBOLS)
        if not dbs:
            print("暂无数据。使用 collect 命令采集数据。")
            return

        print(f"\n{'品种':<8} {'名称':<8} {'K线':>8} {'主链':>8} {'最新日期':<12}")
        print("─" * 50)
        for symbol in dbs:
            with DataStore(symbol) as store:
                status = store.get_status()
                name = get_name(symbol)
                print(
                    f"{symbol.upper():<8} {name:<8} "
                    f"{status['kline_records']:>8} {status['main_continuous_records']:>8} "
                    f"{(status['latest_date'] or '无'): <12}"
                )


def cmd_contracts(args):
    """查看合约信息"""
    from data.contract_manager import ContractManager

    for symbol in args.symbols:
        symbol = symbol.lower()
        with ContractManager(symbol) as cm:
            info = cm.get_all_info()
        print(f"\n{'='*50}")
        print(f"  {symbol.upper()} 合约列表")
        print(f"{'='*50}")
        print(f"  主力: {info['main_contract'].upper() if info['main_contract'] else '未识别'}")
        print(f"  次主力: {info['secondary_contract'].upper() if info['secondary_contract'] else '无'}")
        print(f"  活跃合约: {len(info['contracts'])} 个\n")
        for c in info["contracts"]:
            marker = "★ 主力" if c.get("is_main") else ""
            print(f"    {c['contract_code']:<12} {c.get('exchange',''):<8} "
                  f"月:{c.get('contract_month','?')}  {marker}")


def cmd_query(args):
    """查询主链数据"""
    from data.data_store import DataStore

    symbol = args.symbols[0].lower()
    with DataStore(symbol) as store:
        df = store.get_main_continuous(limit=args.days)

    if df.empty:
        print(f"  {symbol.upper()}: 无主链数据")
        return

    # 显示关键列
    display_cols = ["dt", "contract_code", "open_price", "high", "low", "close_price",
                    "volume", "ma5", "ma20", "rsi6", "macd_dif", "boll_upper", "boll_lower"]
    display_cols = [c for c in display_cols if c in df.columns]
    print(df[display_cols].tail(args.days).to_string(index=False))


def cmd_timesfm(args):
    """导出 TimesFM 输入"""
    from data.data_store import DataStore
    import numpy as np

    symbol = args.symbols[0].lower()
    with DataStore(symbol) as store:
        arr = store.get_timesfm_input(days=args.days)

    if len(arr) == 0:
        print(f"  {symbol.upper()}: 无数据")
        return

    print(f"\n{symbol.upper()} 最近 {len(arr)} 日收盘价 (TimesFM 输入):")
    print(f"  shape: {arr.shape}")
    print(f"  dtype: {arr.dtype}")
    print(f"  最新:  {arr[-1]:.1f}")
    print(f"  数据:  {arr[:5]}... {arr[-5:]}")


def main():
    parser = argparse.ArgumentParser(
        description="FM 期货数据管理 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # collect
    p_collect = subparsers.add_parser("collect", help="采集数据")
    p_collect.add_argument("symbols", nargs="*", help="品种代码")
    p_collect.add_argument("--all", action="store_true", help="所有品种")
    p_collect.add_argument("--full", action="store_true", help="全量重拉 (覆盖 _CONT 数据)")
    p_collect.add_argument("--force", action="store_true", help="强制覆盖 (忽略增量检查)")
    p_collect.set_defaults(func=cmd_collect)

    # status
    p_status = subparsers.add_parser("status", help="查看状态")
    p_status.add_argument("symbols", nargs="*", help="品种代码 (不填则全部)")
    p_status.set_defaults(func=cmd_status)

    # contracts
    p_contracts = subparsers.add_parser("contracts", help="合约列表")
    p_contracts.add_argument("symbols", nargs="+", help="品种代码")
    p_contracts.set_defaults(func=cmd_contracts)

    # query
    p_query = subparsers.add_parser("query", help="查询主链数据")
    p_query.add_argument("symbols", nargs=1, help="品种代码")
    p_query.add_argument("--days", type=int, default=30, help="天数")
    p_query.set_defaults(func=cmd_query)

    # timesfm
    p_timesfm = subparsers.add_parser("timesfm", help="导出 TimesFM 输入")
    p_timesfm.add_argument("symbols", nargs=1, help="品种代码")
    p_timesfm.add_argument("--days", type=int, default=250, help="天数")
    p_timesfm.set_defaults(func=cmd_timesfm)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()

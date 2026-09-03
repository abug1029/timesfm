"""
拉取 TqSdk 主力连续合约历史 1H 数据

从 KQ.m@ 连续合约拉取 10000 根 1H bar (约 2020-07 起)
存入 kline_1h 表, contract_code 为 {SYMBOL}_MAIN

用法:
  python scripts/pull_history_1h.py              # 所有 20 品种
  python scripts/pull_history_1h.py cf rb ss     # 指定品种
"""

import sys
import os
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.config import DEFAULT_SYMBOLS, get_name
from data.tqsdk_fetcher import TqSdkFetcher, to_tqsdk_main_symbol
from data.data_store import DataStore


def pull_symbol_1h(fetcher: TqSdkFetcher, symbol: str, data_length: int = 10000) -> dict:
    """拉取单个品种的主力连续 1H 数据"""
    tq_symbol = to_tqsdk_main_symbol(symbol)
    contract_code = f"{symbol.upper()}_MAIN"

    # 获取 1H K线
    api = fetcher._api
    if api is None:
        fetcher._connect()
        api = fetcher._api

    klines = api.get_kline_serial(tq_symbol, 3600, data_length=data_length)

    # 等待数据填充
    deadline = time.time() + 30
    while not api.wait_update(deadline=deadline):
        if len(klines) > 0 and klines.iloc[-1]["datetime"] > 0:
            break

    # 处理数据
    df = fetcher._process_klines(klines, daily=False)
    if df.empty:
        return {"symbol": symbol, "error": "no data returned"}

    # 统计
    earliest = df["dt"].iloc[0]
    latest = df["dt"].iloc[-1]
    n_records = len(df)

    # 写入数据库
    with DataStore(symbol) as store:
        # 先删除旧的 _MAIN 数据
        deleted = store.conn.execute(
            "DELETE FROM kline_1h WHERE contract_code = ?", (contract_code,)
        ).rowcount
        store.conn.commit()

        # 写入新数据
        stored = store.store_klines_1h(contract_code, df)

    return {
        "symbol": symbol,
        "name": get_name(symbol),
        "contract_code": contract_code,
        "records": stored,
        "deleted_old": deleted,
        "earliest": earliest,
        "latest": latest,
        "years": round(n_records / (250 * 10), 1),  # 约 250 天/年 × 10 bars/天
    }


def main():
    parser = argparse.ArgumentParser(description="拉取 TqSdk 历史 1H 数据")
    parser.add_argument("symbols", nargs="*", help="品种代码 (不填则全部)")
    parser.add_argument("--data-length", type=int, default=10000, help="数据长度 (默认 10000)")
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else list(DEFAULT_SYMBOLS)

    print(f"=" * 70)
    print(f"TqSdk 主力连续 1H 历史数据拉取")
    print(f"品种: {len(symbols)} 个")
    print(f"数据长度: {args.data_length} bars/品种")
    print(f"=" * 70)

    fetcher = TqSdkFetcher()
    results = []

    try:
        for i, symbol in enumerate(symbols, 1):
            symbol = symbol.lower()
            print(f"\n[{i}/{len(symbols)}] {symbol.upper()} ({get_name(symbol)})...", end=" ", flush=True)

            try:
                result = pull_symbol_1h(fetcher, symbol, args.data_length)
                results.append(result)
                if "error" in result:
                    print(f"ERROR: {result['error']}")
                else:
                    print(f"{result['records']:,} bars  [{result['earliest'][:10]} ~ {result['latest'][:10]}]")
            except Exception as e:
                print(f"FAILED: {e}")
                results.append({"symbol": symbol, "error": str(e)})

    finally:
        try:
            fetcher._disconnect()
        except Exception:
            pass

    # 汇总
    print(f"\n{'=' * 70}")
    print(f"拉取完成")
    print(f"{'=' * 70}")

    total_records = 0
    success = 0
    failed = 0
    for r in results:
        if "error" in r:
            failed += 1
        else:
            success += 1
            total_records += r["records"]

    print(f"成功: {success} 品种")
    print(f"失败: {failed} 品种")
    print(f"总记录: {total_records:,} bars")

    # 详情表
    print(f"\n{'品种':<8} {'名称':<8} {'记录数':>8} {'最早日期':<12} {'最新日期':<12} {'约年数':>6}")
    print("-" * 60)
    for r in results:
        if "error" not in r:
            print(f"{r['symbol'].upper():<8} {r['name']:<8} {r['records']:>8,} "
                  f"{r['earliest'][:10]:<12} {r['latest'][:10]:<12} {r['years']:>6.1f}")


if __name__ == "__main__":
    main()

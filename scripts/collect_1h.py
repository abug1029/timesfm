"""
采集 1H (1小时) K线数据并计算指标

用法:
  python scripts/collect_1h.py              # 所有品种
  python scripts/collect_1h.py cf rb        # 指定品种
  python scripts/collect_1h.py ss --with-basis  # 采集 1H + 基差合约
"""

import sys
import argparse
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.config import DEFAULT_SYMBOLS
from data.tqsdk_fetcher import UnifiedFetcher
from data.indicator_calculator import IndicatorCalculator
from data.data_store import DataStore
from data.contract_manager import ContractManager


def collect_1h_for_symbol(symbol: str, fetcher: UnifiedFetcher,
                          calculator: IndicatorCalculator, store: DataStore) -> int:
    """采集某品种的 1H 数据

    2026-07-02: 数据已切换为 _CONT 格式, 直接采集主力连续到 _MAIN。
    """
    # 采集 TqSdk 主力连续 1H 数据, 存为 {SYMBOL}_MAIN
    main_code = f"{symbol.upper()}_MAIN"
    df = fetcher.get_main_continuous_kline(symbol, dur_sec=3600, data_length=10000)
    if df.empty:
        return 0

    df = df.rename(columns={'dt': 'date'})
    df['contract_code'] = main_code
    df = calculator.calculate_all(df)
    df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})

    # 数据量保护: TqSdk 网络异常可能返回部分数据，避免用少量数据覆盖历史
    # store_klines_1h 内部用 INSERT OR REPLACE，增量更新是安全的；
    # 但全量 DELETE 后再 INSERT 会丢失历史，因此仅在新数据覆盖完整区间时才清空。
    MIN_1H_ROWS = 500  # 健康的主力连续 1H 数据应远超此阈值
    stored = store.store_klines_1h(main_code, df)  # INSERT OR REPLACE，安全增量
    if stored > 0:
        print(f"  {main_code} 1H: +{stored} 条")
        # 仅当新数据量充足时清理可能残留的旧合约脏数据 (INSERT OR REPLACE 已覆盖主键，此处为防御性清理)
        if stored >= MIN_1H_ROWS:
            # 清除比新数据最新日期更靠后的异常未来 bar (理论上不应存在，防御性)
            new_max = df['date'].max() if 'date' in df.columns else None
            if new_max is not None:
                store.conn.execute(
                    "DELETE FROM kline_1h WHERE contract_code = ? AND dt > ?",
                    (main_code, str(new_max))
                )

    return stored


def collect_basis_contracts_for_symbol(symbol: str, fetcher: UnifiedFetcher,
                                        calculator: IndicatorCalculator,
                                        store: DataStore) -> int:
    """采集基差所需的月度合约 1H 数据 (probe → select → full fetch)

    2026-07-29 fix: 不再从 DB 查询已有合约（kline_1h 只有 _MAIN，
    导致返回空集）。改为用 ContractManager 生成未来 18 个月候选，
    TqSdk probe 200 行取 OI，选 OI 最高的两个未过期合约（近月+次近月），
    然后全量抓取写入 kline_1h。
    """
    from datetime import datetime

    symbol_lower = symbol.lower()

    # Step 1: 生成未来 18 个月候选合约代码
    with ContractManager(symbol_lower) as cm:
        candidate_codes = cm.generate_contract_codes()

    if not candidate_codes:
        print(f"  [basis] 无候选合约, 跳过")
        return 0

    # Step 2: 过滤已过期合约，解析月份用于排序
    current_ym = int(datetime.now().strftime("%Y%m"))
    valid_candidates = []
    for code in candidate_codes:
        # code 格式: e.g. "ta2609" → 提取末尾 4 位数字
        suffix = code.replace(symbol_lower, "")
        if len(suffix) != 4 or not suffix.isdigit():
            continue
        ym = 200000 + int(suffix)
        if ym >= current_ym:
            valid_candidates.append((code, suffix, ym))

    if len(valid_candidates) < 2:
        print(f"  [basis] 不足 2 个未过期候选, 跳过")
        return 0

    # Step 3: 对每个候选 probe 200 行 1H 数据，提取平均 OI
    print(f"  [basis] 候选合约 {len(valid_candidates)} 个, probe OI...")
    oi_results = []
    for code, suffix, ym in valid_candidates:
        try:
            df_probe = fetcher.get_kline_1h(code, data_length=200)
            if df_probe.empty:
                continue
            avg_oi = df_probe["open_interest"].mean()
            if avg_oi > 0:
                oi_results.append((code, suffix, ym, avg_oi))
        except Exception as e:
            # 某些合约可能不存在（如非活跃月份），静默跳过
            continue

    if len(oi_results) < 2:
        print(f"  [basis] probe 后不足 2 个有效合约 (OI>0), 跳过")
        return 0

    # Step 4: 按 OI 降序排列，取最高的两个
    oi_results.sort(key=lambda x: x[3], reverse=True)
    # 按月份排序选中的两个（近月在前）
    selected = sorted(oi_results[:2], key=lambda x: x[2])
    near_code, near_suffix, _, _ = selected[0]
    far_code, far_suffix, _, _ = selected[1]
    print(f"  [basis] near={near_code.upper()} far={far_code.upper()}")

    # Step 5: 对选中的两个合约全量抓取（默认 8000 行）
    total = 0
    for code in [near_code, far_code]:
        try:
            df = fetcher.get_kline_1h(code)  # 默认 8000 行
            if df.empty:
                print(f"  [basis] {code}: 空数据")
                continue

            df = df.rename(columns={'dt': 'date'})
            df['contract_code'] = code.upper()
            df = calculator.calculate_all(df)
            df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})

            stored = store.store_klines_1h(code.upper(), df)
            if stored > 0:
                print(f"  [basis] {code.upper()}: +{stored} 条")
                total += stored
        except Exception as e:
            print(f"  [basis] {code} 全量抓取失败: {e}")
            continue

    return total


def backfill_ccl_for_daily(symbol: str, store: DataStore):
    """给已有的日线和主链数据补充 CCL 指标"""
    import pandas as pd
    from data.config import get_db_path
    import sqlite3

    conn = sqlite3.connect(str(get_db_path(symbol)))
    calculator = IndicatorCalculator()
    total = 0

    # 1. kline_1d 回填 (新格式: 只有 _CONT 合约)
    contracts = pd.read_sql_query(
        "SELECT DISTINCT contract_code FROM kline_1d", conn
    )["contract_code"].tolist()

    for contract in contracts:
        df = pd.read_sql_query(
            f"SELECT dt, open_price, high, low, close_price, volume, open_interest "
            f"FROM kline_1d WHERE contract_code = '{contract}' ORDER BY dt",
            conn
        )
        if df.empty:
            continue
        df_calc = df.rename(columns={"open_price": "open", "close_price": "close", "dt": "date"})
        df_calc = calculator.calculate_all(df_calc)
        if "ccl_value" not in df_calc.columns:
            continue

        # 批量 UPDATE
        updates = []
        for _, row in df_calc.iterrows():
            cv = row.get("ccl_value")
            if cv is not None and not pd.isna(cv):
                updates.append((float(cv), row.get("ccl_label", ""), row["date"], contract))
        if updates:
            conn.executemany(
                "UPDATE kline_1d SET ccl_value = ?, ccl_label = ? WHERE dt = ? AND contract_code = ?",
                updates
            )
            total += len(updates)

    # 2. [C1 fix] main_continuous_1d 回填
    main_df = pd.read_sql_query(
        "SELECT dt, open_price, high, low, close_price, volume, open_interest "
        "FROM main_continuous_1d ORDER BY dt",
        conn
    )
    if not main_df.empty:
        main_calc = main_df.rename(columns={"open_price": "open", "close_price": "close", "dt": "date"})
        main_calc = calculator.calculate_all(main_calc)
        if "ccl_value" in main_calc.columns:
            updates = []
            for _, row in main_calc.iterrows():
                cv = row.get("ccl_value")
                if cv is not None and not pd.isna(cv):
                    updates.append((float(cv), row.get("ccl_label", ""), row["date"]))
            if updates:
                conn.executemany(
                    "UPDATE main_continuous_1d SET ccl_value = ?, ccl_label = ? WHERE dt = ?",
                    updates
                )
                total += len(updates)
                print(f"    主链 CCL: {len(updates)} 条")

    conn.commit()
    conn.close()
    return total


def main():
    parser = argparse.ArgumentParser(description="采集 1H K线数据")
    parser.add_argument("symbols", nargs="*", help="品种代码")
    parser.add_argument("--ccl-only", action="store_true", help="只补充日线 CCL")
    parser.add_argument("--with-basis", action="store_true",
                        help="后置采集基差合约 (近月/远月 1H 全量)")
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else list(DEFAULT_SYMBOLS)
    if not symbols:
        print("无数据")
        return

    fetcher = UnifiedFetcher()
    calculator = IndicatorCalculator()

    for symbol in symbols:
        symbol = symbol.lower()
        print(f"\n{'='*50}")
        print(f"[{symbol.upper()}]")

        with DataStore(symbol) as store:
            if not args.ccl_only:
                # 采集 1H
                print(f"  采集 1H K线...")
                total = collect_1h_for_symbol(symbol, fetcher, calculator, store)
                print(f"  1H 合计: {total} 条")

                # Bug 2 fix: 主力 _MAIN 采集后立即 commit, 再做 [basis] 采集
                # 确保 _MAIN 数据持久化后再进行基差合约采集 (独立 commit 隔离)
                store.conn.commit()

                # Phase 6: 后置采集基差合约
                if args.with_basis:
                    print(f"  采集基差合约 1H...")
                    try:
                        basis_total = collect_basis_contracts_for_symbol(
                            symbol, fetcher, calculator, store)
                        print(f"  基差合约合计: {basis_total} 条")
                    except Exception as e:
                        print(f"  [WARN] 基差采集失败: {e}")
                    # 基差采集独立 commit (store_klines_1h 内部已 commit,
                    # 此处确保防御性清理等也被持久化)
                    store.conn.commit()

            # 补充日线 CCL
            print(f"  补充日线 CCL...")
            ccl_count = backfill_ccl_for_daily(symbol, store)
            print(f"  CCL 更新: {ccl_count} 条")

    print(f"\n完成!")


if __name__ == "__main__":
    main()

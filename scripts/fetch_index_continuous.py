"""KQ.i@<sym> 指数合约日线回填/增量同步 (spec: docs/2026-09-18-oi-gated-momentum-spec.md §3.1)

指数合约 open_interest = 全市场总持仓 —— 杜绝主力换月污染 (主力单合约口径 ΔOI_5d max=154%)。

用法:
  python scripts/fetch_index_continuous.py                 # 全量回填 (该品种价格日历首日 → 今)
  python scripts/fetch_index_continuous.py --incremental   # 增量: 只补表中最新日期之后
  python scripts/fetch_index_continuous.py --verify        # 拉数 + 回退线判定, 不写库
  python scripts/fetch_index_continuous.py --symbol rb     # 指定品种 (默认 m; 全品种见 SYMBOL_EXCHANGE_MAP)

回退触发线 (宿主量化要求; 起始日/硬线按**各品种价格日历首日**取, 非硬编码 2016 —— 否则 2016 后上市的新品种被误杀):
  - 首根有效数据日期 > 价格日历首日 + 容差, 或
  - 相对交易日历 (main_continuous_1d) 连续缺失 > 3 天
  -> 打印结构化报告并 exit 78。**不**自行执行逐合约回退 (需宿主重新评审)。
"""

import argparse
import json
import sqlite3
import sys
import warnings
from itertools import groupby
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data.config import get_db_path  # noqa: E402
from data.tqsdk_fetcher import TqSdkFetcher, to_tqsdk_index_symbol  # noqa: E402

DEFAULT_SYMBOL = "m"
SYMBOL = DEFAULT_SYMBOL  # 运行时被 --symbol 覆盖
TQ_INDEX_SYMBOL = "KQ.i@DCE.m"  # 运行时被 --symbol 重算 (显示用)
# 品种特有基线: 起始日与回退硬线按各品种价格日历首日起始 (main 取 calendar[0]),
# 不硬编码 2016 (那是 m 的上市历史)。容差沿用 m 原口径 ~2 个月 (2016-01-05→2016-03-01)。
FIRST_DATE_TOLERANCE_DAYS = 60
MAX_CONSECUTIVE_MISSING_DAYS = 3
DATA_LENGTH = 4000  # 2016→2026 约 2620 交易日, 留余量

INDEX_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS index_continuous_1d ("
    "dt TEXT PRIMARY KEY, close_price REAL, volume REAL, open_interest REAL)"
)


def load_main_calendar(conn: sqlite3.Connection) -> list:
    """价格日历基准 (spec §3.4): main_continuous_1d 的 dt 列表 (升序)。"""
    rows = conn.execute("SELECT dt FROM main_continuous_1d ORDER BY dt").fetchall()
    return [r[0] for r in rows]


def compute_quality(df: pd.DataFrame, calendar: list) -> dict:
    """回退线判定 + 质量统计。df 需升序, dt 已过滤 >= 该品种价格日历首日。"""
    dates = df["dt"].tolist()
    date_set = set(dates)
    first = dates[0] if dates else None
    last = dates[-1] if dates else None
    expected = [d for d in calendar if dates and d <= last]
    missing = [d for d in expected if d not in date_set]
    runs = [(k, len(list(g))) for k, g in groupby(missing)]
    over_limit = [k for k, n in runs if n > MAX_CONSECUTIVE_MISSING_DAYS]
    return {
        "first_valid_date": first,
        "last_date": last,
        "n_rows": len(dates),
        "n_missing_total": len(missing),
        "max_consecutive_missing": max((n for _, n in runs), default=0),
        "missing_runs_over_limit": over_limit,
    }


def rollback_verdict(q: dict, price_start: str) -> list:
    """回退触发线判定。返回触发的检查列表 (空 = 通过)。

    硬线按**该品种**价格日历首日 price_start + 容差取 (非硬编码 2016),
    否则 2016 年后上市的新品种 (ss/eg/lh/cj/sp/ur/sh/ao) 会被误杀。
    """
    limit = (pd.Timestamp(price_start) + pd.Timedelta(days=FIRST_DATE_TOLERANCE_DAYS)).strftime("%Y-%m-%d")
    triggered = []
    if q["first_valid_date"] is None:
        triggered.append("no_data")
    elif q["first_valid_date"] > limit:
        triggered.append(
            f"first_valid_date {q['first_valid_date']} > {limit} "
            f"(价格日历起始 {price_start} + {FIRST_DATE_TOLERANCE_DAYS}d, 指数合约历史深度不足, "
            f"须回退逐合约回填方案)"
        )
    if q["max_consecutive_missing"] > MAX_CONSECUTIVE_MISSING_DAYS:
        triggered.append(
            f"max_consecutive_missing {q['max_consecutive_missing']} > "
            f"{MAX_CONSECUTIVE_MISSING_DAYS} 天, 起始日 {q['missing_runs_over_limit']}"
        )
    return triggered


def fetch_df(fetcher: TqSdkFetcher, start_date: str) -> pd.DataFrame:
    print(f"[1/3] 拉取 {TQ_INDEX_SYMBOL} 日线 (data_length={DATA_LENGTH}) ...")
    df = fetcher.get_index_kline(SYMBOL, dur_sec=86400, data_length=DATA_LENGTH)
    if df.empty:
        return df
    df = df[df["dt"] >= start_date].sort_values("dt").reset_index(drop=True)
    df = df[["dt", "close", "volume", "open_interest"]].rename(
        columns={"close": "close_price"}
    )
    print(f"      拉取 {len(df)} 行, 区间 {df['dt'].min()} → {df['dt'].max()}")
    return df


def upsert(conn: sqlite3.Connection, df: pd.DataFrame, incremental: bool) -> int:
    conn.execute(INDEX_TABLE_DDL)
    if incremental:
        row = conn.execute(
            "SELECT MAX(dt) FROM index_continuous_1d"
        ).fetchone()
        last = row[0] if row else None
        if last:
            df = df[df["dt"] > last]
    if df.empty:
        return 0
    rows = [
        (r["dt"], float(r["close_price"]), float(r["volume"]), float(r["open_interest"]))
        for _, r in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO index_continuous_1d "
        "(dt, close_price, volume, open_interest) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="KQ.i@<sym> 指数合约日线回填/增量同步")
    parser.add_argument("--incremental", action="store_true", help="只补表中最新日期之后")
    parser.add_argument("--verify", action="store_true", help="只跑回退线判定, 不写库")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="品种代码 (默认 m), 如 rb/ss/cf ...")
    args = parser.parse_args()
    global SYMBOL, TQ_INDEX_SYMBOL
    SYMBOL = str(args.symbol).lower()
    TQ_INDEX_SYMBOL = to_tqsdk_index_symbol(SYMBOL)

    db_path = get_db_path(SYMBOL)
    conn = sqlite3.connect(str(db_path))
    try:
        calendar = load_main_calendar(conn)
        if not calendar:
            print("[ERROR] main_continuous_1d 为空, 无法提供交易日历基准", file=sys.stderr)
            return 1

        price_start = calendar[0]  # 品种特有基线 (替代 m 的 2016-01-05)
        fetcher = TqSdkFetcher()
        try:
            df = fetch_df(fetcher, price_start)
        finally:
            fetcher._disconnect()

        if df.empty:
            print("[ERROR] TqSdk 返回空数据 (凭据/网络/合约?)", file=sys.stderr)
            return 1

        q = compute_quality(df, calendar)
        triggered = rollback_verdict(q, price_start)
        print("[2/3] 回退线判定:")
        print(json.dumps({
            "triggered": triggered,
            "quality": {k: v for k, v in q.items() if k != "missing_runs_over_limit"},
        }, ensure_ascii=False, indent=2))
        if triggered:
            print("[ROLLBACK-LINE] 触发回退线 —— 结构化报告如上, exit 78。", file=sys.stderr)
            print("后续动作: 交宿主重新评审逐合约回填方案; 本脚本不自行回退。", file=sys.stderr)
            return 78

        if args.verify:
            print("[verify] 通过, 未写库")
            return 0

        n = upsert(conn, df, args.incremental)
        print(f"[3/3] 入库 {n} 行 (mode={'incremental' if args.incremental else 'full'})")
        print("完成!")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

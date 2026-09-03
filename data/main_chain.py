"""主链数据构建

DEPRECATED (2026-07-02): 数据已切换为 TqSdk 主力连续合约直接入库。
kline_1d 和 main_continuous_1d 均存储 _CONT 格式的主力连续数据。
MainChainBuilder 保留仅用于兼容性, 新采集流程不再调用。
"""

import pandas as pd
import numpy as np

from .data_store import DataStore
from .indicator_calculator import IndicatorCalculator


class MainChainBuilder:
    """主链数据构建器 (DEPRECATED)

    数据来源已切换为 TqSdk 主力连续合约 (KQ.m@) 直接入库。
    kline_1d 和 main_continuous_1d 均存储 _CONT 格式的主力连续数据,
    不再需要通过 OI 排名选主力。

    此类的 build() 方法现在仅做数据同步:
    kline_1d (_CONT) → main_continuous_1d
    """

    def __init__(self, symbol: str):
        self.symbol = symbol.lower()
        self.store = DataStore(symbol)
        self.calculator = IndicatorCalculator()

    def build(self, start_date: str = None) -> int:
        """
        同步 kline_1d → main_continuous_1d

        DEPRECATED: 新流程中 kline_1d 和 main_continuous_1d 已由采集脚本直接写入,
        此方法仅用于兼容旧流程。
        """
        sql = """
            SELECT dt, contract_code, open_price, high, low, close_price,
                   volume, open_interest
            FROM kline_1d
            WHERE 1=1
        """
        params = []
        if start_date:
            sql += " AND dt >= ?"
            params.append(start_date)
        sql += " ORDER BY dt"

        df = pd.read_sql_query(sql, self.store.conn, params=params)
        if df.empty:
            print(f"  [WARN] {self.symbol}: kline_1d 无数据")
            return 0

        # 重命名回 open/close 供 indicator_calculator 使用
        df = df.rename(columns={
            "open_price": "open",
            "close_price": "close",
            "dt": "date",
        })

        # 技术指标
        df = self.calculator.calculate_all(df)

        # 写回
        stored = self.store.store_main_continuous(df)
        return stored

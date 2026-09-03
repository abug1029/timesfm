"""合约发现与主力识别

2026-07-02 更新: 数据已切换为 TqSdk 主力连续合约 (_CONT 格式)。
kline_1d 只存储主力连续数据, 不再存储多个具体合约。
合约管理简化为直接返回 _CONT 标记。
"""

import re
import pandas as pd
from typing import List, Dict, Optional

from .config import get_exchange, parse_contract_info
from .data_store import DataStore


class ContractManager:
    """合约管理器 (适配 _CONT 格式)"""

    def __init__(self, symbol: str):
        self.symbol = symbol.lower()
        self.store = DataStore(symbol)

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def identify_main_contract(self) -> str:
        """
        识别当前主力合约

        新格式: 直接返回 {symbol}_cont (主力连续合约标记)。
        """
        # 检查 kline_1d 是否有 _CONT 数据
        result = self.store.conn.execute("""
            SELECT DISTINCT contract_code FROM kline_1d
            WHERE contract_code LIKE '%_CONT'
            LIMIT 1
        """).fetchone()
        if result:
            return result[0].lower()
        # 回退: 返回 _CONT 标记
        return f"{self.symbol}_cont"

    def discover_contracts_from_kline(self) -> List[str]:
        """从已存储的 kline 数据中发现合约

        新格式: 返回 [_cont] (只有一个主力连续合约)。
        """
        result = self.store.conn.execute("""
            SELECT DISTINCT contract_code FROM kline_1d
            ORDER BY contract_code
        """).fetchall()
        return [r[0].lower() for r in result]

    def generate_contract_codes(self) -> List[str]:
        """根据当前日期生成可能的合约代码 (保留兼容)"""
        from datetime import datetime
        now = datetime.now()
        codes = []

        for month_offset in range(0, 18):
            year = now.year + (now.month + month_offset - 1) // 12
            month = (now.month + month_offset - 1) % 12 + 1
            yy = year % 100
            code = f"{self.symbol}{yy:02d}{month:02d}"
            codes.append(code)

        return codes

    def sync_contracts(self) -> List[dict]:
        """同步合约信息到 contracts 表 (适配 _CONT)"""
        main_contract = self.identify_main_contract()
        known = self.discover_contracts_from_kline()

        records = []
        for code in known:
            info = parse_contract_info(code)
            is_main = 1 if code.lower() == main_contract.lower() else 0
            records.append({
                "contract_code": code.upper(),
                "product": self.symbol,
                "exchange": get_exchange(self.symbol),
                "contract_month": info.get("month"),
                "delivery_year": info.get("year"),
                "is_active": 1,
                "is_main": is_main,
            })

        if records:
            self.store.store_contracts(records)
        return records

    def get_all_info(self) -> Dict:
        """获取合约完整信息"""
        self.sync_contracts()
        contracts_df = self.store.get_contracts()
        main = self.identify_main_contract()

        return {
            "symbol": self.symbol,
            "main_contract": main if main else None,
            "secondary_contract": None,
            "contracts": contracts_df.to_dict("records") if not contracts_df.empty else [],
        }

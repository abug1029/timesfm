"""
TqSdk 数据获取器 — 精确 1H/日线数据

唯一数据源: TqSdk (天勤量化)
"""

import os
import time
import pandas as pd
import numpy as np
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from .config import SYMBOL_EXCHANGE_MAP


def to_tqsdk_main_symbol(symbol: str) -> str:
    """内部品种代码转 TqSdk 主力连续合约格式

    rb → KQ.m@SHFE.rb
    CF → KQ.m@CZCE.CF
    i → KQ.m@DCE.i
    """
    product = symbol.upper()
    exchange = SYMBOL_EXCHANGE_MAP.get(product, SYMBOL_EXCHANGE_MAP.get(product.lower(), ""))
    if not exchange:
        raise ValueError(f"无法识别品种 {product}")
    if exchange in ("CZCE", "CFFEX"):
        product_part = product
    else:
        product_part = product.lower()
    return f"KQ.m@{exchange}.{product_part}"


def to_tqsdk_symbol(contract_code: str) -> str:
    """
    内部合约代码转 TqSdk 格式

    rb2609 → SHFE.rb2609
    CF2609 → CZCE.CF609   (郑商所 3 位数字)
    i2609  → DCE.i2609
    CF_CONT → KQ.m@CZCE.CF  (主力连续合约)
    """
    code = contract_code.upper()

    # 处理 _CONT / _MAIN 格式: 主力连续合约
    if code.endswith('_CONT') or code.endswith('_MAIN'):
        product = code.rsplit('_', 1)[0]
        return to_tqsdk_main_symbol(product)

    m = re.match(r'^([A-Z]+)(\d+)$', code)
    if not m:
        raise ValueError(f"无法解析合约代码: {contract_code}")
    product = m.group(1)
    month_str = m.group(2)
    # 查交易所: 先试大写 (CFFEX), 再试小写
    exchange = SYMBOL_EXCHANGE_MAP.get(product, SYMBOL_EXCHANGE_MAP.get(product.lower(), ""))
    if not exchange:
        raise ValueError(f"无法识别品种 {product} 的交易所")

    # 郑商所: 3 位数字 (CF2609 → CF609)
    if exchange == "CZCE" and len(month_str) == 4:
        month_str = month_str[1:]

    # 品种代码: CZCE/CFFEX 保持大写, 其他小写
    if exchange in ("CZCE", "CFFEX"):
        symbol_part = product
    else:
        symbol_part = product.lower()
    return f"{exchange}.{symbol_part}{month_str}"


class TqSdkFetcher:
    """TqSdk 数据获取器"""

    def __init__(self, account: str = None, password: str = None):
        # 从 .env 文件加载凭证 (如果环境变量未设置)
        if not os.environ.get("TQSDK_ACCOUNT"):
            self._load_dotenv()
        # 从环境变量加载凭证
        self.account = account or os.environ.get("TQSDK_ACCOUNT", "")
        self.password = password or os.environ.get("TQSDK_PASSWORD", "")
        if not self.account or not self.password:
            raise ValueError("TqSdk 凭证未配置: 请设置 TQSDK_ACCOUNT 和 TQSDK_PASSWORD 环境变量")
        self._api = None

    @staticmethod
    def _load_dotenv():
        """从 .env 文件加载环境变量"""
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

    def _connect(self):
        if self._api is None:
            from tqsdk import TqApi, TqAuth
            self._api = TqApi(auth=TqAuth(self.account, self.password))

    def _disconnect(self):
        if self._api is not None:
            try:
                self._api.close()
            except Exception:
                pass
            self._api = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, *args):
        self._disconnect()

    def get_kline_1h(self, contract_code: str, data_length: int = 8000) -> pd.DataFrame:
        """获取 1H K线"""
        self._connect()
        tq_symbol = to_tqsdk_symbol(contract_code)
        klines = self._api.get_kline_serial(tq_symbol, 3600, data_length=data_length)
        # 等待数据到达
        deadline = time.time() + 10  # 10秒超时
        while not self._api.wait_update(deadline=deadline):
            if klines.iloc[-1].datetime > 0:
                break
        return self._process_klines(klines)

    def get_daily(self, contract_code: str, data_length: int = 3000) -> pd.DataFrame:
        """获取日线"""
        self._connect()
        tq_symbol = to_tqsdk_symbol(contract_code)
        klines = self._api.get_kline_serial(tq_symbol, 86400, data_length=data_length)
        # 等待数据到达
        deadline = time.time() + 10  # 10秒超时
        while not self._api.wait_update(deadline=deadline):
            if klines.iloc[-1].datetime > 0:
                break
        return self._process_klines(klines, daily=True)

    def get_main_continuous_kline(self, symbol: str, dur_sec: int = 86400,
                                   data_length: int = 3000) -> pd.DataFrame:
        """获取主力连续合约 K 线 (使用 TqSdk 内置 KQ.m@ 符号)"""
        self._connect()
        tq_symbol = to_tqsdk_main_symbol(symbol)
        klines = self._api.get_kline_serial(tq_symbol, dur_sec, data_length=data_length)
        deadline = time.time() + 10
        while not self._api.wait_update(deadline=deadline):
            if klines.iloc[-1].datetime > 0:
                break
        return self._process_klines(klines, daily=(dur_sec >= 86400))

    def get_realtime_quote(self, contract_code: str) -> Dict:
        """获取实时行情"""
        self._connect()
        tq_symbol = to_tqsdk_symbol(contract_code)
        quote = self._api.get_quote(tq_symbol)
        return {
            "symbol": contract_code,
            "last_price": float(quote.last_price) if quote.last_price else None,
            "volume": int(quote.volume) if quote.volume else 0,
            "open_interest": int(quote.open_oi) if quote.open_oi else 0,
            "bid1": float(quote.bid_price1) if quote.bid_price1 else None,
            "ask1": float(quote.ask_price1) if quote.ask_price1 else None,
        }

    def _process_klines(self, klines, daily=False) -> pd.DataFrame:
        """处理 K 线原始数据为标准化 DataFrame"""
        df = klines.copy()
        if df.empty or df["close"].isna().all():
            return pd.DataFrame()

        fmt = "%Y-%m-%d" if daily else "%Y-%m-%d %H:%M"
        df["dt"] = df["datetime"].apply(lambda ts: TqSdkFetcher._ts_to_str(ts, fmt))

        result = pd.DataFrame({
            "dt": df["dt"],
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int),
            "open_interest": pd.to_numeric(df.get("close_oi", df.get("open_oi", pd.Series([0]*len(df)))), errors="coerce").fillna(0).astype(int),
        })
        # 过滤无效数据
        result = result[(result["volume"] > 0) & (result["close"] > 0) & (result["dt"] != "")]
        return result.reset_index(drop=True)

    @staticmethod
    def _ts_to_str(ts, fmt="%Y-%m-%d %H:%M"):
        try:
            dt = datetime.fromtimestamp(ts / 1e9) if ts > 1e15 else datetime.fromtimestamp(ts / 1e6)
            return dt.strftime(fmt)
        except Exception:
            return ""


# ════════════════════════════════════════════════════════
#  统一数据源: TqSdk
# ════════════════════════════════════════════════════════

class UnifiedFetcher:
    """
    统一数据获取器

    唯一数据源: TqSdk
    日线数据通过 KQ.m@ 获取主力连续合约 (_CONT 格式)
    1H 数据通过 KQ.m@ 获取主力连续合约 (_MAIN 格式)
    """

    def __init__(self, prefer_tqsdk: bool = True):
        self._fetcher = None

    @property
    def fetcher(self):
        if self._fetcher is None:
            try:
                self._fetcher = TqSdkFetcher()
            except Exception as e:
                print(f"  [ERROR] TqSdk 初始化失败: {e}")
        return self._fetcher

    def get_daily_kline(self, contract_code: str) -> pd.DataFrame:
        """获取日线 (TqSdk)"""
        if self.fetcher:
            try:
                return self.fetcher.get_daily(contract_code)
            except Exception as e:
                print(f"  [WARN] TqSdk 日线 {contract_code} 失败: {e}")
        return pd.DataFrame()

    def get_kline_1h(self, contract_code: str, data_length: int = 8000) -> pd.DataFrame:
        """获取 1H K线 (TqSdk)"""
        if self.fetcher:
            try:
                return self.fetcher.get_kline_1h(contract_code, data_length)
            except Exception as e:
                print(f"  [WARN] TqSdk 1H {contract_code} 失败: {e}")
        return pd.DataFrame()

    def get_main_continuous_kline(self, symbol: str, dur_sec: int = 86400, data_length: int = 3000) -> pd.DataFrame:
        """获取主力连续合约日线 (TqSdk KQ.m@)"""
        if self.fetcher:
            try:
                return self.fetcher.get_main_continuous_kline(symbol, dur_sec=dur_sec, data_length=data_length)
            except Exception as e:
                print(f"  [WARN] TqSdk 主力连续 {symbol} 失败: {e}")
        return pd.DataFrame()

    def get_realtime_quote(self, contract_code: str) -> Dict:
        """获取实时行情 (TqSdk)"""
        if self.fetcher:
            try:
                return self.fetcher.get_realtime_quote(contract_code)
            except Exception as e:
                print(f"  [WARN] TqSdk 实时行情 {contract_code} 失败: {e}")
        return {}

    def close(self):
        """关闭连接"""
        if self._fetcher:
            self._fetcher._disconnect()
            self._fetcher = None


def detect_roll_events(kline_df: pd.DataFrame) -> list:
    """Detect main contract roll events by contract_code change + ATR gap filter.

    Works on DataFrames with columns: dt, contract_code, close (or close_price),
    and optionally atr14.  Used by the data-loading pipeline in data_store to
    build roll records for backward adjustment.
    """
    if kline_df.empty:
        return []

    # Flexible column access
    cc_col = "contract_code" if "contract_code" in kline_df.columns else None
    if cc_col is None:
        return []

    close_col = "close" if "close" in kline_df.columns else ("close_price" if "close_price" in kline_df.columns else None)
    if close_col is None:
        return []

    atr_col = "atr14" if "atr14" in kline_df.columns else None

    rolls = []
    prev_contract = None
    for i in kline_df.index:
        cur_contract = kline_df.at[i, cc_col]
        if prev_contract is not None and cur_contract != prev_contract:
            gap = abs(kline_df.at[i, close_col] - kline_df.at[i - 1 if i > 0 else i, close_col])
            if atr_col and atr_col in kline_df.columns:
                window = kline_df.loc[max(kline_df.index[0], i - 14):i, atr_col]
                atr = window.mean() if len(window) > 0 else 0.0
                if atr > 0 and gap > 2 * atr:
                    roll_ratio = kline_df.at[i, "roll_ratio"] if "roll_ratio" in kline_df.columns else 1.0
                    rolls.append({
                        "dt": kline_df.at[i, "dt"],
                        "old_contract": prev_contract,
                        "new_contract": cur_contract,
                        "roll_ratio": roll_ratio,
                    })
            else:
                roll_ratio = kline_df.at[i, "roll_ratio"] if "roll_ratio" in kline_df.columns else 1.0
                rolls.append({
                    "dt": kline_df.at[i, "dt"],
                    "old_contract": prev_contract,
                    "new_contract": cur_contract,
                    "roll_ratio": roll_ratio,
                })
        prev_contract = cur_contract
    return rolls

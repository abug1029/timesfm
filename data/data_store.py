"""SQLite 数据读写层"""

import re
import sqlite3
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Optional, Dict, List
from datetime import datetime

from .config import get_db_path, get_exchange, parse_contract_info
from .db import init_db

logger = logging.getLogger(__name__)


# kline_1d / main_continuous_1d 列名
KLINE_COLUMNS = [
    "dt", "contract_code",
    "open_price", "high", "low", "close_price", "volume", "open_interest", "settle", "change_pct",
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "macd_dif", "macd_dea", "macd_bar",
    "rsi6", "rsi12", "rsi24",
    "kdj_k", "kdj_d", "kdj_j",
    "boll_upper", "boll_mid", "boll_lower",
    "atr14", "cci14",
    "oi_change", "oi_trend_5d", "oi_price_corr", "volume_oi_ratio", "oi_signal",
    "ccl_value", "ccl_label",
]

KLINE_1H_COLUMNS = [
    "dt", "contract_code",
    "open_price", "high", "low", "close_price", "volume", "open_interest", "change_pct",
    "ma5", "ma10", "ma20",
    "ema12", "ema26",
    "macd_dif", "macd_dea", "macd_bar",
    "rsi6", "rsi12", "rsi24",
    "boll_upper", "boll_mid", "boll_lower",
    "atr14",
    "oi_change", "volume_oi_ratio", "oi_signal",
    "ccl_value", "ccl_label",
]

MAIN_COLUMNS = [
    "dt", "contract_code",
    "open_price", "high", "low", "close_price", "volume", "open_interest", "change_pct",
    "raw_open", "raw_high", "raw_low", "raw_close", "adjustment_factor",
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "macd_dif", "macd_dea", "macd_bar",
    "rsi6", "rsi12", "rsi24",
    "kdj_k", "kdj_d", "kdj_j",
    "boll_upper", "boll_mid", "boll_lower",
    "atr14", "cci14",
    "oi_change", "oi_trend_5d", "oi_price_corr", "volume_oi_ratio", "oi_signal",
    "ccl_value", "ccl_label",
]


def _clean_val(val):
    """清理值用于 SQLite 写入"""
    if val is None:
        return None
    try:
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            v = float(val)
            return None if np.isnan(v) else v
        if isinstance(val, float) and np.isnan(val):
            return None
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        return None
    return val



def get_safe_daily(
    symbol: str,
    limit: int = 500,
    now_dt: datetime | None = None,
    store: Any | None = None,
) -> pd.DataFrame:
    """生产路径同构防护: 向量化收盘掩码, 防御夜盘跨日穿透.

    规则:
    - date < today  → 历史已收盘, 保留
    - date == today 且 hour >= 15 → 当日已收盘, 保留
    - date == today 且 hour < 15  → 当日未收盘, 剔除
    - date > today → 未来交易日 (夜盘跨日标签), 无条件剔除
    """
    if now_dt is None:
        now_dt = datetime.now()

    if store is not None:
        df = store.get_main_continuous(limit=limit)
    else:
        with DataStore(symbol) as ds:
            df = ds.get_main_continuous(limit=limit)

    if df is None or df.empty:
        return pd.DataFrame()

    df_dates = pd.to_datetime(df["dt"]).dt.date
    today = now_dt.date()

    closed_mask = (df_dates < today) | ((df_dates == today) & (now_dt.hour >= 15))
    safe_df = df[closed_mask].copy().reset_index(drop=True)
    trimmed_rows = len(df) - len(safe_df)

    if trimmed_rows > 0:
        logger.warning(
            f"[{symbol}] 检测到 {trimmed_rows} 行未收盘/未来交易日日线, "
            f"当前系统时间 {now_dt.strftime('%Y-%m-%d %H:%M')}, "
            f"已透明回退至最新已收盘日线"
        )

    return safe_df


class DataStore:
    """SQLite 数据读写"""

    def __init__(self, symbol: str):
        self.symbol = symbol.lower()
        self.db_path = get_db_path(self.symbol)
        self.conn = init_db(self.db_path)

    def close(self):
        if self.conn:
            self.conn.close()

    # [H2] context manager 防止连接泄漏
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ══════════════════════════════════════════════════
    #  写入
    # ══════════════════════════════════════════════════

    def store_klines(self, contract_code: str, df: pd.DataFrame) -> int:
        """写入合约日线 (executemany 批量写入)"""
        if df.empty:
            return 0

        contract_code = contract_code.upper()
        df = self._map_columns(df)
        df["contract_code"] = contract_code

        cols = [c for c in KLINE_COLUMNS if c in df.columns]
        if "contract_code" not in cols:
            cols.append("contract_code")
            df["contract_code"] = contract_code

        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO kline_1d ({col_names}) VALUES ({placeholders})"

        # [M4] executemany 批量写入，替代逐行 insert
        rows = []
        for _, row in df.iterrows():
            rows.append(tuple(_clean_val(row.get(c)) for c in cols))

        try:
            self.conn.executemany(sql, rows)
            self.conn.commit()
            stored = len(rows)
        except Exception as e:
            logger.error(f"store_klines({contract_code}) failed: {e}")
            self.conn.rollback()
            stored = 0

        self._update_meta(f"last_collect_{contract_code}", datetime.now().strftime("%Y-%m-%d"))
        return stored

    def store_klines_1h(self, contract_code: str, df: pd.DataFrame) -> int:
        """写入 1 小时 K 线数据"""
        if df.empty:
            return 0

        contract_code = contract_code.upper()
        df = self._map_columns(df)
        df["contract_code"] = contract_code

        cols = [c for c in KLINE_1H_COLUMNS if c in df.columns]
        if "contract_code" not in cols:
            cols.append("contract_code")
            df["contract_code"] = contract_code

        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO kline_1h ({col_names}) VALUES ({placeholders})"

        rows = []
        for _, row in df.iterrows():
            rows.append(tuple(_clean_val(row.get(c)) for c in cols))

        try:
            self.conn.executemany(sql, rows)
            self.conn.commit()
            stored = len(rows)
        except Exception as e:
            logger.error(f"store_klines_1h({contract_code}) failed: {e}")
            self.conn.rollback()
            stored = 0

        if stored > 0:
            self._update_meta(f"1h_latest_{contract_code}",
                              datetime.now().strftime("%Y-%m-%d %H:%M"))

        return stored

    def store_main_continuous(self, df: pd.DataFrame) -> int:
        """写入主力连续合约"""
        if df.empty:
            return 0

        df = self._map_columns(df)

        # 确保 contract_code 有值
        if "contract_code" not in df.columns or df["contract_code"].isna().all():
            df = df.copy()
            df["contract_code"] = f"{self.symbol.upper()}_CONT"

        cols = [c for c in MAIN_COLUMNS if c in df.columns]
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO main_continuous_1d ({col_names}) VALUES ({placeholders})"

        rows = []
        for _, row in df.iterrows():
            rows.append(tuple(_clean_val(row.get(c)) for c in cols))

        try:
            self.conn.executemany(sql, rows)
            self.conn.commit()
            stored = len(rows)
        except Exception as e:
            logger.error(f"store_main_continuous failed: {e}")
            self.conn.rollback()
            stored = 0

        self._update_meta("main_continuous_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
        return stored

    def store_contracts(self, contracts: List[dict]) -> int:
        """写入合约信息"""
        stored = 0
        for c in contracts:
            try:
                self.conn.execute(
                    """INSERT OR REPLACE INTO contracts
                       (contract_code, product, exchange, contract_month, delivery_year,
                        is_active, is_main, main_since, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (c.get("contract_code", "").upper(),
                     c.get("product", self.symbol),
                     c.get("exchange", get_exchange(self.symbol)),
                     c.get("contract_month"), c.get("delivery_year"),
                     c.get("is_active", 1), c.get("is_main", 0), c.get("main_since"))
                )
                stored += 1
            except Exception as e:
                logger.warning(f"store_contracts failed for {c.get('contract_code')}: {e}")
        self.conn.commit()
        return stored

    def store_xreg_factor(self, factor_name: str, df: pd.DataFrame) -> int:
        """写入 XReg 因子"""
        if df.empty:
            return 0
        stored = 0
        for _, row in df.iterrows():
            dt = row.get("date") or row.get("dt")
            val = row.get("factor_value") or row.get("value")
            if dt is None or pd.isna(val):
                continue
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO xreg_factors (dt, symbol, factor_name, factor_value) VALUES (?, ?, ?, ?)",
                    (str(dt), self.symbol, factor_name, float(val))
                )
                stored += 1
            except Exception as e:
                logger.warning(f"store_xreg_factor failed: {e}")
        self.conn.commit()
        return stored

    # ══════════════════════════════════════════════════
    #  读取
    # ══════════════════════════════════════════════════

    def get_klines(self, contract_code: str, start_date=None, end_date=None) -> pd.DataFrame:
        """读取合约日线（含技术指标）"""
        sql = "SELECT * FROM kline_1d WHERE contract_code = ?"
        params = [contract_code.upper()]
        if start_date:
            sql += " AND dt >= ?"; params.append(start_date)
        if end_date:
            sql += " AND dt <= ?"; params.append(end_date)
        sql += " ORDER BY dt"
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_main_continuous(self, start_date=None, end_date=None, limit=None) -> pd.DataFrame:
        """读取主力连续数据

        [H4 fix] LIMIT 返回最近 N 条，不是最旧 N 条
        """
        if limit:
            # 子查询: 先倒序取最近 N 条，再正序返回
            inner = "SELECT * FROM main_continuous_1d WHERE 1=1"
            params = []
            if start_date:
                inner += " AND dt >= ?"; params.append(start_date)
            if end_date:
                inner += " AND dt <= ?"; params.append(end_date)
            inner += " ORDER BY dt DESC LIMIT ?"
            params.append(int(limit))
            sql = f"SELECT * FROM ({inner}) ORDER BY dt"
            return pd.read_sql_query(sql, self.conn, params=params)
        else:
            sql = "SELECT * FROM main_continuous_1d WHERE 1=1"
            params = []
            if start_date:
                sql += " AND dt >= ?"; params.append(start_date)
            if end_date:
                sql += " AND dt <= ?"; params.append(end_date)
            sql += " ORDER BY dt"
            return pd.read_sql_query(sql, self.conn, params=params)

    def get_xreg_factors(self, factor_names=None, start_date=None) -> pd.DataFrame:
        """读取 XReg 因子"""
        sql = "SELECT * FROM xreg_factors WHERE symbol = ?"
        params = [self.symbol]
        if factor_names:
            ph = ", ".join(["?"] * len(factor_names))
            sql += f" AND factor_name IN ({ph})"; params.extend(factor_names)
        if start_date:
            sql += " AND dt >= ?"; params.append(start_date)
        sql += " ORDER BY dt, factor_name"
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_contracts(self, active_only=True) -> pd.DataFrame:
        """读取合约列表"""
        sql = "SELECT * FROM contracts WHERE product = ?"
        params = [self.symbol]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY contract_code"
        return pd.read_sql_query(sql, self.conn, params=params)

    def discover_contracts_from_kline(self) -> List[str]:
        """从已存储的 kline 数据中发现合约"""
        sql = "SELECT DISTINCT contract_code FROM kline_1d ORDER BY contract_code"
        result = self.conn.execute(sql).fetchall()
        return [r[0].lower() for r in result]

    def get_latest_date(self, contract_code: str) -> Optional[str]:
        """查询某合约最新日期"""
        r = self.conn.execute(
            "SELECT MAX(dt) FROM kline_1d WHERE contract_code = ?",
            (contract_code.upper(),)
        ).fetchone()
        return r[0] if r and r[0] else None

    # ── 1H 数据读取 ─────────────────────────────────

    def get_klines_1h(self, contract_code: str = None,
                      start_date=None, end_date=None,
                      limit=None) -> pd.DataFrame:
        """读取 1H K线数据 (含指标)"""
        sql = "SELECT * FROM kline_1h WHERE 1=1"
        params = []
        if contract_code:
            sql += " AND contract_code = ?"; params.append(contract_code.upper())
        if start_date:
            sql += " AND dt >= ?"; params.append(start_date)
        if end_date:
            sql += " AND dt <= ?"; params.append(end_date)

        if limit:
            # 取最新的 N 条，然后按时间正序返回
            sql += " ORDER BY dt DESC LIMIT ?"
            params.append(int(limit))
            sql = f"SELECT * FROM ({sql}) ORDER BY dt"
        else:
            sql += " ORDER BY dt"

        return pd.read_sql_query(sql, self.conn, params=params)

    def get_main_contract_1h(self, limit=1023) -> pd.DataFrame:
        """
        获取主力连续合约的 1H 数据

        数据来源优先级:
        1. {SYMBOL}_MAIN — TqSdk 主力连续 1H (含夜盘, 最完整)
        2. {SYMBOL}_CONT — 本地连续合约 1H (如果 _MAIN 不存在)
        """
        symbol = self.symbol.upper() if hasattr(self, 'symbol') else None
        if not symbol:
            db_path = self.conn.execute("PRAGMA database_list").fetchone()
            symbol = "UNKNOWN"

        # Case 0: {SYMBOL}_MAIN (主力连续, 含夜盘, 最完整)
        main_code = f"{symbol}_MAIN"
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM kline_1h WHERE contract_code = ?", (main_code,)
        ).fetchone()[0]
        if cnt > 0:
            return self.get_klines_1h(contract_code=main_code, limit=limit)

        # Case 1: {SYMBOL}_CONT (本地连续合约)
        cont_code = f"{symbol}_CONT"
        cnt = self.conn.execute(
            "SELECT COUNT(*) FROM kline_1h WHERE contract_code = ?", (cont_code,)
        ).fetchone()[0]
        if cnt > 0:
            return self.get_klines_1h(contract_code=cont_code, limit=limit)

        # Case 2: 回退 — 从 kline_1h 找近期活跃合约 (排除连续合约标记)
        r = self.conn.execute("""
            SELECT contract_code FROM kline_1h
            WHERE contract_code NOT LIKE '%_CONT'
              AND contract_code NOT LIKE '%_MAIN'
            GROUP BY contract_code
            HAVING MAX(dt) >= date('now', '-7 days')
            ORDER BY MAX(dt) DESC, AVG(open_interest) DESC
            LIMIT 1
        """).fetchone()
        if r:
            return self.get_klines_1h(contract_code=r[0], limit=limit)

        return pd.DataFrame()

    def get_basis_1h(self, near_contract: str = None, far_contract: str = None,
                     limit: int = 1023) -> pd.DataFrame:
        """
        获取 1H 基差数据 (近月 - 远月)

        自动识别近月 (OI 最高) 和远月 (OI 次高) 合约，
        计算 Basis = (Close_near - Close_far) / Close_far

        Args:
            near_contract: 近月合约代码 (None=自动识别)
            far_contract: 远月合约代码 (None=自动识别)
            limit: 返回最大 bar 数

        Returns:
            DataFrame with columns: dt, basis, near_close, far_close, near_oi, far_oi
        """
        # 自动识别合约
        if near_contract is None or far_contract is None:
            # 找到 OI 最高的具体合约 (排除连续合约 _CONT/_MAIN)
            contracts = self.conn.execute("""
                SELECT contract_code, AVG(open_interest) as avg_oi
                FROM kline_1h
                WHERE contract_code NOT LIKE '%_CONT'
                  AND contract_code NOT LIKE '%_MAIN'
                GROUP BY contract_code
                ORDER BY avg_oi DESC
                LIMIT 6
            """).fetchall()
            if len(contracts) < 2:
                return pd.DataFrame()

            # 按合约月份排序, 过滤已过期的合约
            # 合约月份格式: YYMM, e.g. 2609 = 2026年9月
            current_ym = int(datetime.now().strftime("%Y%m"))
            contract_months = []
            for c in contracts:
                code = c[0]
                m = re.search(r'(\d{4})$', code)
                if m:
                    ym = int(m.group(1))
                    # YYMM → YYYYMM: 2609 → 202609
                    full_ym = 200000 + ym
                    if full_ym >= current_ym:  # 排除已过期合约
                        contract_months.append((code, ym, full_ym))
            contract_months.sort(key=lambda x: x[1])

            if len(contract_months) >= 2:
                # near = 最近月 (未过期), far = 次近月
                near_contract = contract_months[0][0]
                near_month = contract_months[0][1]

                # far = 月份 > near_month 的下一个合约
                far_contract = None
                for code, month, _ in contract_months:
                    if month > near_month and code != near_contract:
                        far_contract = code
                        break

                if far_contract is None:
                    # fallback: 月份第二近
                    far_contract = contract_months[1][0]

        # 查询重叠数据
        sql = """
            SELECT a.dt,
                   a.close_price as near_close,
                   b.close_price as far_close,
                   a.open_interest as near_oi,
                   b.open_interest as far_oi
            FROM kline_1h a
            INNER JOIN kline_1h b ON a.dt = b.dt
            WHERE a.contract_code = ? AND b.contract_code = ?
              AND a.close_price IS NOT NULL AND b.close_price IS NOT NULL
              AND a.close_price > 0 AND b.close_price > 0
            ORDER BY a.dt DESC
            LIMIT ?
        """
        params = [near_contract.upper(), far_contract.upper(), int(limit)]
        df = pd.read_sql_query(sql, self.conn, params=params)

        if df.empty:
            return df

        # 正序排列
        df = df.iloc[::-1].reset_index(drop=True)

        # 计算基差
        df["basis"] = (df["near_close"] - df["far_close"]) / df["far_close"]

        # ── 历史 OI 过滤 (2026-07-29 方向 2): 合约自身百分位法 ──
        # 防止 TqSdk 对过期合约返回的"伪有效"远端 K 线 (零成交/挂单价) 污染长程回测
        # 合约自身 P95 × 5% 为门槛;低于则该 bar basis 置 NaN (不删行,保留时间轴)
        OI_FLOOR_RATIO = 0.05

        def _p95_oi(contract_code: str):
            oi_rows = self.conn.execute(
                "SELECT open_interest FROM kline_1h "
                "WHERE contract_code = ? AND open_interest IS NOT NULL",
                [contract_code.upper()],
            ).fetchall()
            if not oi_rows:
                return None
            oi_arr = np.array([r[0] for r in oi_rows], dtype=float)
            return float(np.percentile(oi_arr, 95))

        near_p95 = _p95_oi(near_contract)
        far_p95 = _p95_oi(far_contract)
        near_floor = near_p95 * OI_FLOOR_RATIO if near_p95 is not None else 0.0
        far_floor = far_p95 * OI_FLOOR_RATIO if far_p95 is not None else 0.0

        valid = (df["near_oi"] >= near_floor) & (df["far_oi"] >= far_floor)
        df["valid"] = valid
        df.loc[~valid, "basis"] = np.nan

        return df

    def get_status(self) -> Dict:
        """数据状态概览"""
        # [M3 fix] 用 kline_1d 中的实际合约数，不是 contracts 表的注册数
        kline_contracts = self.conn.execute(
            "SELECT COUNT(DISTINCT contract_code) FROM kline_1d"
        ).fetchone()[0]
        kline_count = self.conn.execute("SELECT COUNT(*) FROM kline_1d").fetchone()[0]
        main_count = self.conn.execute("SELECT COUNT(*) FROM main_continuous_1d").fetchone()[0]
        latest = self.conn.execute("SELECT MAX(dt) FROM main_continuous_1d").fetchone()[0]
        contract_list = self.conn.execute(
            "SELECT DISTINCT contract_code FROM kline_1d ORDER BY contract_code"
        ).fetchall()
        return {
            "symbol": self.symbol,
            "contracts": kline_contracts,
            "kline_records": kline_count,
            "main_continuous_records": main_count,
            "latest_date": latest,
            "contract_list": [c[0] for c in contract_list],
        }

    # ══════════════════════════════════════════════════
    #  TimesFM / XReg
    # ══════════════════════════════════════════════════

    def get_timesfm_input(self, days: int = 250) -> np.ndarray:
        """输出 TimesFM 收盘价数组

        [C2 fix] 过滤 NaN，确保输入模型的数据完整
        """
        df = self.get_main_continuous(limit=days)
        if df.empty:
            return np.array([])
        arr = df["close_price"].dropna().values.astype(np.float64)
        if len(arr) == 0:
            logger.warning(f"get_timesfm_input: all close_price values are NaN for {self.symbol}")
        return arr

    def get_xreg_matrix(self, days: int = 250) -> pd.DataFrame:
        """输出多因子矩阵"""
        main_df = self.get_main_continuous(limit=days)
        if main_df.empty:
            return pd.DataFrame()
        xreg_df = self.get_xreg_factors()
        if not xreg_df.empty:
            xreg_pivot = xreg_df.pivot_table(
                index="dt", columns="factor_name", values="factor_value"
            ).reset_index()
            # [M5 fix] 移除无意义的 rename
            main_df = main_df.merge(xreg_pivot, on="dt", how="left")
        return main_df

    # ══════════════════════════════════════════════════
    #  内部方法
    # ══════════════════════════════════════════════════

    @staticmethod
    def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
        """统一列名: open→open_price, close→close_price, date→dt"""
        df = df.copy()
        rename_map = {
            "open": "open_price",
            "close": "close_price",
            "date": "dt",
        }
        for old, new in rename_map.items():
            if old in df.columns and new not in df.columns:
                df = df.rename(columns={old: new})
        return df

    def _update_meta(self, key: str, value: str):
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata (meta_key, meta_value) VALUES (?, ?)",
                (key, value)
            )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"_update_meta failed: {e}")

    def get_metadata(self, key: str) -> Optional[str]:
        r = self.conn.execute(
            "SELECT meta_value FROM metadata WHERE meta_key = ?", (key,)
        ).fetchone()
        return r[0] if r else None

    def get_latest_main_date(self) -> Optional[str]:
        """获取主力连续合约最新日期"""
        return self.get_metadata("main_continuous_latest")


# ─────────────────────────────────────────────────────────
# BacktestDataStore: 支持时刻截断的 DataStore (bar-exact)
# ─────────────────────────────────────────────────────────

def normalize_backtest_cutoff(cutoff) -> tuple[str, str]:
    """将 cutoff 规范为 (cutoff_ts, cutoff_day)。

    - cutoff_ts: 1H 截断上界 (含该时刻 bar)，字符串可与 SQLite TEXT dt 比较
    - cutoff_day: 日历日 YYYY-MM-DD，用于日线截断

    若传入仅日期 (无时刻)，按 **当日 00:00:00** 处理并打日志警告——
    调用方应传入评估 bar 的完整时间戳，否则会丢掉当日日盘数据。
    旧行为 (date + 23:59) 会造成同日 1H lookahead，已移除。
    """
    if cutoff is None:
        raise ValueError("cutoff is required")
    s = str(cutoff).strip()
    ts = pd.Timestamp(s)
    if pd.isna(ts):
        raise ValueError(f"invalid cutoff: {cutoff!r}")
    # 仅日期 (无显式时刻): pandas 解析为 00:00:00
    has_time = bool(re.search(r"\d{1,2}:\d{2}", s)) or ("T" in s and len(s) > 10)
    if not has_time:
        logger.warning(
            "BacktestDataStore: date-only cutoff %r treated as 00:00:00; "
            "pass full bar timestamp to include same-day bars up to eval time",
            s,
        )
    cutoff_ts = ts.strftime("%Y-%m-%d %H:%M:%S")
    cutoff_day = ts.strftime("%Y-%m-%d")
    return cutoff_ts, cutoff_day


class BacktestDataStore(DataStore):
    """支持 **bar 级时刻截断** 的 DataStore，用于 walk-forward 回测。

    Args:
        symbol: 品种代码
        cutoff_date: 评估时刻。推荐 ``YYYY-MM-DD HH:MM:SS`` (或带 T 的 ISO)。
            1H / 合约选择使用完整时刻；日线使用日历日。

    属性:
        cutoff_ts: 1H 截断时刻 (含)
        cutoff_date: 兼容旧代码；**现为完整 cutoff_ts**，供 feedstock 透传
        cutoff_day: 日历日 YYYY-MM-DD
    """

    def __init__(self, symbol: str, cutoff_date: str):
        super().__init__(symbol)
        self.cutoff_ts, self.cutoff_day = normalize_backtest_cutoff(cutoff_date)
        # 兼容 hasattr(store, 'cutoff_date') 与 feedstock 透传：存完整时刻
        self.cutoff_date = self.cutoff_ts

    def get_main_continuous(self, limit=None, **kwargs):
        """日线数据: 根据 cutoff 时刻决定是否包含当日日线（防止日内前视）
        
        - 15:00 及之后（含夜盘）：当天日线已定型，安全可用
        - 15:00 之前（日盘进行中）：严格回退至前一日历日
        """
        cutoff_hour = pd.Timestamp(self.cutoff_ts).hour
        if cutoff_hour >= 15:
            target_day = self.cutoff_day
        else:
            target_day = (pd.Timestamp(self.cutoff_day) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        
        return super().get_main_continuous(
            end_date=target_day, limit=limit, **kwargs
        )

    def get_main_contract_1h(self, limit=480):
        """1H 数据: 截断到 cutoff_ts (含)，优先 {SYM}_MAIN 与标签序列对齐。"""
        symbol = self.symbol.upper()
        for code in (f"{symbol}_MAIN", f"{symbol}_CONT"):
            cnt = self.conn.execute(
                "SELECT COUNT(*) FROM kline_1h WHERE contract_code = ? AND dt <= ?",
                (code, self.cutoff_ts),
            ).fetchone()[0]
            if cnt > 0:
                return self.get_klines_1h(
                    contract_code=code,
                    end_date=self.cutoff_ts,
                    limit=limit,
                )
        contract_code = self._get_main_contract_at_cutoff()
        if not contract_code:
            return pd.DataFrame()
        return self.get_klines_1h(
            contract_code=contract_code,
            end_date=self.cutoff_ts,
            limit=limit,
        )

    def _get_main_contract_at_cutoff(self):
        """查询 **cutoff_ts 时刻** 持仓量最大的具体合约 (排除 _MAIN/_CONT)。"""
        row = self.conn.execute(
            "SELECT contract_code, open_interest FROM ("
            "  SELECT contract_code, open_interest, dt,"
            "    ROW_NUMBER() OVER (PARTITION BY contract_code ORDER BY dt DESC) as rn"
            "  FROM kline_1h WHERE dt <= ?"
            "    AND contract_code NOT LIKE '%_MAIN'"
            "    AND contract_code NOT LIKE '%_CONT'"
            ") WHERE rn = 1 ORDER BY open_interest DESC LIMIT 1",
            (self.cutoff_ts,),
        ).fetchone()
        return row[0] if row and row[0] else None

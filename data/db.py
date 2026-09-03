"""SQLite 数据库管理"""

import sqlite3
from pathlib import Path
from typing import Optional

from .config import get_db_path


def _migrate(conn: sqlite3.Connection):
    """增量迁移: 给已有表添加新列"""
    # 获取已有列
    def _get_columns(table):
        try:
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return {row[1] for row in info}
        except Exception:
            return set()

    # kline_1d 新列
    kline_cols = _get_columns("kline_1d")
    if kline_cols and "ccl_value" not in kline_cols:
        conn.execute("ALTER TABLE kline_1d ADD COLUMN ccl_value REAL")
        conn.execute("ALTER TABLE kline_1d ADD COLUMN ccl_label TEXT")
    if kline_cols and "settle" not in kline_cols:
        conn.execute("ALTER TABLE kline_1d ADD COLUMN settle REAL")

    # kline_1h 新列
    kline_1h_cols = _get_columns("kline_1h")
    if kline_1h_cols and "ccl_value" not in kline_1h_cols:
        conn.execute("ALTER TABLE kline_1h ADD COLUMN ccl_value REAL")
        conn.execute("ALTER TABLE kline_1h ADD COLUMN ccl_label TEXT")
    main_cols = _get_columns("main_continuous_1d")
    if main_cols and "ccl_value" not in main_cols:
        conn.execute("ALTER TABLE main_continuous_1d ADD COLUMN ccl_value REAL")
        conn.execute("ALTER TABLE main_continuous_1d ADD COLUMN ccl_label TEXT")


def _create_tables(conn: sqlite3.Connection):
    """创建所有表"""
    c = conn.cursor()

    # ── kline_1d ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS kline_1d (
            dt              TEXT NOT NULL,
            contract_code   TEXT NOT NULL,
            open_price      REAL,
            high            REAL,
            low             REAL,
            close_price     REAL,
            volume          INTEGER,
            open_interest   INTEGER,
            settle          REAL,
            change_pct      REAL,
            ma5  REAL, ma10 REAL, ma20 REAL, ma60 REAL,
            ema12 REAL, ema26 REAL,
            macd_dif REAL, macd_dea REAL, macd_bar REAL,
            rsi6 REAL, rsi12 REAL, rsi24 REAL,
            kdj_k REAL, kdj_d REAL, kdj_j REAL,
            boll_upper REAL, boll_mid REAL, boll_lower REAL,
            atr14 REAL, cci14 REAL,
            oi_change       INTEGER,
            oi_trend_5d     REAL,
            oi_price_corr   REAL,
            volume_oi_ratio REAL,
            oi_signal       TEXT,
            ccl_value       REAL,
            ccl_label       TEXT,
            updated_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (dt, contract_code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline_contract ON kline_1d(contract_code, dt)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline_dt ON kline_1d(dt)")

    # ── kline_1h ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS kline_1h (
            dt              TEXT NOT NULL,
            contract_code   TEXT NOT NULL,
            open_price      REAL,
            high            REAL,
            low             REAL,
            close_price     REAL,
            volume          INTEGER,
            open_interest   INTEGER,
            change_pct      REAL,
            ma5  REAL, ma10 REAL, ma20 REAL,
            ema12 REAL, ema26 REAL,
            macd_dif REAL, macd_dea REAL, macd_bar REAL,
            rsi6 REAL, rsi12 REAL, rsi24 REAL,
            boll_upper REAL, boll_mid REAL, boll_lower REAL,
            atr14 REAL,
            oi_change       INTEGER,
            volume_oi_ratio REAL,
            oi_signal       TEXT,
            ccl_value       REAL,
            ccl_label       TEXT,
            updated_at      TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (dt, contract_code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline1h_contract ON kline_1h(contract_code, dt)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kline1h_dt ON kline_1h(dt)")

    # ── main_continuous_1d ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS main_continuous_1d (
            dt              TEXT NOT NULL PRIMARY KEY,
            contract_code   TEXT NOT NULL,
            open_price      REAL,
            high            REAL,
            low             REAL,
            close_price     REAL,
            volume          INTEGER,
            open_interest   INTEGER,
            change_pct      REAL,
            raw_open        REAL,
            raw_high        REAL,
            raw_low         REAL,
            raw_close       REAL,
            adjustment_factor REAL DEFAULT 0,
            ma5  REAL, ma10 REAL, ma20 REAL, ma60 REAL,
            ema12 REAL, ema26 REAL,
            macd_dif REAL, macd_dea REAL, macd_bar REAL,
            rsi6 REAL, rsi12 REAL, rsi24 REAL,
            kdj_k REAL, kdj_d REAL, kdj_j REAL,
            boll_upper REAL, boll_mid REAL, boll_lower REAL,
            atr14 REAL, cci14 REAL,
            oi_change INTEGER, oi_trend_5d REAL,
            oi_price_corr REAL, volume_oi_ratio REAL,
            oi_signal TEXT,
            ccl_value       REAL,
            ccl_label       TEXT,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── contracts ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            contract_code   TEXT PRIMARY KEY,
            product         TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            contract_month  INTEGER,
            delivery_year   INTEGER,
            is_active       INTEGER DEFAULT 1,
            is_main         INTEGER DEFAULT 0,
            main_since      TEXT,
            first_listed    TEXT,
            last_trading    TEXT,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── xreg_factors ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS xreg_factors (
            dt          TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            factor_name TEXT NOT NULL,
            factor_value REAL,
            PRIMARY KEY (dt, symbol, factor_name)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_xreg ON xreg_factors(symbol, dt)")

    # ── metadata ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            meta_key    TEXT PRIMARY KEY,
            meta_value  TEXT
        )
    """)

    conn.commit()

    # 迁移: 给已有表添加新列
    _migrate(conn)


def init_db(db_path: Path) -> sqlite3.Connection:
    """初始化数据库，创建所有表"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _create_tables(conn)
    return conn


def get_conn(symbol: str) -> sqlite3.Connection:
    """获取品种数据库连接（自动初始化）"""
    db_path = get_db_path(symbol)
    return init_db(db_path)


def list_all_dbs() -> list[str]:
    """列出所有已创建的品种数据库"""
    from .config import DB_DIR
    if not DB_DIR.exists():
        return []
    return sorted([
        f.stem.replace("futures_", "")
        for f in DB_DIR.glob("futures_*.db")
    ])

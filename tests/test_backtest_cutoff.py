"""Bar-exact BacktestDataStore: mid-session cutoff must not include later same-day 1H bars."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data.db import init_db  # noqa: E402
from data.data_store import BacktestDataStore, normalize_backtest_cutoff  # noqa: E402


def _seed_1h_db(db_path: Path, symbol: str = "zz") -> None:
    """Create minimal schema + same-day morning/afternoon bars + MAIN series."""
    conn = init_db(db_path)
    code = f"{symbol.upper()}_MAIN"
    rows = [
        ("2026-03-10 09:00:00", code, 100.0, 1000),
        ("2026-03-10 10:00:00", code, 101.0, 1100),
        ("2026-03-10 11:00:00", code, 102.0, 1200),  # after eval @ 10:00 — must NOT appear
        ("2026-03-10 14:00:00", code, 103.0, 1300),  # afternoon leak under old 23:59 cutoff
        ("2026-03-11 09:00:00", code, 104.0, 1400),
    ]
    for dt, cc, px, oi in rows:
        conn.execute(
            "INSERT INTO kline_1h (dt, contract_code, open_price, high, low, close_price, "
            "volume, open_interest) VALUES (?,?,?,?,?,?,?,?)",
            (dt, cc, px, px, px, px, 1, oi),
        )
    # daily
    for d, px in (("2026-03-09", 99.0), ("2026-03-10", 101.0), ("2026-03-11", 104.0)):
        conn.execute(
            "INSERT INTO main_continuous_1d (dt, contract_code, close_price) VALUES (?,?,?)",
            (d, f"{symbol.upper()}_CONT", px),
        )
    # specific contract (higher OI later in day) — selection must not use post-cutoff OI
    for dt, oi in (
        ("2026-03-10 10:00:00", 500),
        ("2026-03-10 14:00:00", 99999),
    ):
        conn.execute(
            "INSERT INTO kline_1h (dt, contract_code, open_price, high, low, close_price, "
            "volume, open_interest) VALUES (?,?,?,?,?,?,?,?)",
            (dt, "ZZ2605", 100.0, 100.0, 100.0, 100.0, 1, oi),
        )
    conn.commit()
    conn.close()


class TestNormalizeCutoff(unittest.TestCase):
    def test_full_timestamp(self):
        ts, day = normalize_backtest_cutoff("2026-03-10 10:00:00")
        self.assertEqual(ts, "2026-03-10 10:00:00")
        self.assertEqual(day, "2026-03-10")

    def test_iso_t(self):
        ts, day = normalize_backtest_cutoff("2026-03-10T10:00:00")
        self.assertEqual(day, "2026-03-10")
        self.assertIn("10:00:00", ts)

    def test_date_only_is_midnight_not_eod(self):
        """Date-only must NOT expand to 23:59 (old lookahead)."""
        ts, day = normalize_backtest_cutoff("2026-03-10")
        self.assertEqual(day, "2026-03-10")
        self.assertTrue(ts.endswith("00:00:00"), msg=ts)


class TestBarExactCutoff(unittest.TestCase):
    def test_midday_excludes_later_same_day_bars(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_zz.db"
            _seed_1h_db(db, "zz")
            with mock.patch("data.data_store.get_db_path", return_value=db):
                store = BacktestDataStore("zz", "2026-03-10 10:00:00")
                try:
                    df = store.get_main_contract_1h(limit=100)
                    self.assertFalse(df.empty, "expected 1H rows up to 10:00")
                    max_dt = pd.Timestamp(df["dt"].max())
                    self.assertLessEqual(max_dt, pd.Timestamp("2026-03-10 10:00:00"))
                    dts = set(pd.to_datetime(df["dt"]).dt.strftime("%Y-%m-%d %H:%M:%S"))
                    self.assertIn("2026-03-10 10:00:00", dts)
                    self.assertNotIn("2026-03-10 11:00:00", dts)
                    self.assertNotIn("2026-03-10 14:00:00", dts)
                    self.assertNotIn("2026-03-11 09:00:00", dts)
                finally:
                    store.close()

    def test_old_date_only_eod_behavior_removed(self):
        """Using date-only midnight must not include 14:00 (proves 23:59 gone)."""
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_zz.db"
            _seed_1h_db(db, "zz")
            with mock.patch("data.data_store.get_db_path", return_value=db):
                store = BacktestDataStore("zz", "2026-03-10")  # → 00:00:00
                try:
                    df = store.get_main_contract_1h(limit=100)
                    # At 00:00:00 no bars that day exist in seed (first is 09:00)
                    if not df.empty:
                        max_dt = pd.Timestamp(df["dt"].max())
                        self.assertLess(max_dt, pd.Timestamp("2026-03-10 09:00:00"))
                finally:
                    store.close()

    def test_daily_includes_cutoff_calendar_day(self):
        """10:00 cutoff (hour < 15) must not include same-day daily."""
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_zz.db"
            _seed_1h_db(db, "zz")
            with mock.patch("data.data_store.get_db_path", return_value=db):
                store = BacktestDataStore("zz", "2026-03-10 10:00:00")
                try:
                    daily = store.get_main_continuous(limit=100)
                    days = set(pd.to_datetime(daily["dt"]).dt.strftime("%Y-%m-%d"))
                    self.assertNotIn("2026-03-10", days)
                    self.assertIn("2026-03-09", days)
                    self.assertNotIn("2026-03-11", days)
                finally:
                    store.close()

    def test_daily_includes_same_day_at_15(self):
        """15:00 cutoff (hour >= 15) includes same-day daily."""
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_zz.db"
            _seed_1h_db(db, "zz")
            with mock.patch("data.data_store.get_db_path", return_value=db):
                store = BacktestDataStore("zz", "2026-03-10 15:00:00")
                try:
                    daily = store.get_main_continuous(limit=100)
                    days = set(pd.to_datetime(daily["dt"]).dt.strftime("%Y-%m-%d"))
                    self.assertIn("2026-03-10", days)
                    self.assertIn("2026-03-09", days)
                    self.assertNotIn("2026-03-11", days)
                finally:
                    store.close()

    def test_cutoff_date_attr_is_full_ts_for_feedstock(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_zz.db"
            _seed_1h_db(db, "zz")
            with mock.patch("data.data_store.get_db_path", return_value=db):
                store = BacktestDataStore("zz", "2026-03-10 10:00:00")
                try:
                    self.assertEqual(store.cutoff_date, store.cutoff_ts)
                    self.assertEqual(store.cutoff_ts, "2026-03-10 10:00:00")
                    self.assertEqual(store.cutoff_day, "2026-03-10")
                finally:
                    store.close()


if __name__ == "__main__":
    unittest.main()

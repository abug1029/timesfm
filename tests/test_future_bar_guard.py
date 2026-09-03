"""会话感知幽灵 K 线防护 + 交易日语义。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data.trading_calendar import (  # noqa: E402
    max_allowed_daily_label,
    open_trading_day_label,
    last_closed_trading_day,
)
from data.future_bar_guard import purge_future_bars, run_guard  # noqa: E402


def _make_db(path: Path, daily_dates: list[str], h1_dates: list[str] | None = None) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE kline_1d (dt TEXT, close_price REAL, contract_code TEXT)"
    )
    conn.execute("CREATE TABLE main_continuous_1d (dt TEXT, close_price REAL)")
    conn.execute(
        "CREATE TABLE xreg_factors (dt TEXT, symbol TEXT, factor_name TEXT, factor_value REAL)"
    )
    conn.execute(
        "CREATE TABLE kline_1h (dt TEXT, close_price REAL, contract_code TEXT)"
    )
    for d in daily_dates:
        conn.execute("INSERT INTO kline_1d VALUES (?,?,?)", (d, 100.0, "SS_CONT"))
        conn.execute("INSERT INTO main_continuous_1d VALUES (?,?)", (d, 100.0))
        conn.execute(
            "INSERT INTO xreg_factors VALUES (?,?,?,?)", (d, "ss", "rsi6", 1.0)
        )
    for d in h1_dates or []:
        conn.execute(
            "INSERT INTO kline_1h VALUES (?,?,?)", (d, 100.0, "SS_MAIN")
        )
    conn.commit()
    conn.close()


class TestTradingCalendar(unittest.TestCase):
    def test_friday_night_allows_monday_label(self):
        # 周五 23:00 夜盘 → 交易日标签下周一
        fri_night = datetime(2026, 7, 24, 23, 0)
        self.assertEqual(open_trading_day_label(fri_night), date(2026, 7, 27))
        self.assertEqual(max_allowed_daily_label(fri_night), date(2026, 7, 27))

    def test_saturday_max_is_friday(self):
        sat = datetime(2026, 7, 25, 12, 0)
        self.assertIsNone(open_trading_day_label(sat))
        self.assertEqual(max_allowed_daily_label(sat), date(2026, 7, 24))
        self.assertEqual(last_closed_trading_day(sat), date(2026, 7, 24))

    def test_monday_day_session_allows_monday(self):
        mon = datetime(2026, 7, 27, 10, 30)
        self.assertEqual(open_trading_day_label(mon), date(2026, 7, 27))
        self.assertEqual(max_allowed_daily_label(mon), date(2026, 7, 27))


class TestFutureBarGuard(unittest.TestCase):
    def test_friday_night_keeps_monday_daily(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_ss.db"
            _make_db(db, ["2026-07-24", "2026-07-27"])
            r = purge_future_bars(
                "ss",
                db_path=db,
                now=datetime(2026, 7, 24, 23, 0),
            )
            self.assertTrue(r["ok"])
            self.assertEqual(r["kline_1d"], 0)
            conn = sqlite3.connect(str(db))
            n = conn.execute("SELECT COUNT(*) FROM kline_1d").fetchone()[0]
            conn.close()
            self.assertEqual(n, 2)

    def test_saturday_purges_incomplete_monday(self):
        """周末：未完成周一 partial 必须清除。"""
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_ss.db"
            _make_db(
                db,
                ["2026-07-24", "2026-07-27"],
                h1_dates=["2026-07-24 22:00", "2026-07-27 00:00"],
            )
            r = purge_future_bars(
                "ss",
                db_path=db,
                now=datetime(2026, 7, 25, 12, 0),  # Saturday
            )
            self.assertTrue(r["ok"])
            self.assertEqual(r["kline_1d"], 1)
            self.assertEqual(r["kline_1h"], 1)
            conn = sqlite3.connect(str(db))
            daily = [
                row[0]
                for row in conn.execute("SELECT dt FROM kline_1d ORDER BY dt")
            ]
            h1 = [
                row[0]
                for row in conn.execute("SELECT dt FROM kline_1h ORDER BY dt")
            ]
            conn.close()
            self.assertEqual(daily, ["2026-07-24"])
            self.assertEqual(h1, ["2026-07-24 22:00"])

    def test_run_guard_aggregates_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "futures_ss.db"
            _make_db(db, ["2026-07-24", "2026-07-28"])  # 28 永远非法
            summary = run_guard(
                ["ss"],
                db_dir=root,
                now=datetime(2026, 7, 24, 23, 0),
                quiet=True,
            )
            # Fri night max=Mon 27 → 28 removed
            self.assertTrue(summary["ok"])
            self.assertGreaterEqual(summary["total_removed"], 1)

    def test_dry_run_no_delete(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "futures_ss.db"
            _make_db(db, ["2026-07-24", "2026-07-30"])
            r = purge_future_bars(
                "ss",
                db_path=db,
                now=datetime(2026, 7, 25, 12, 0),
                dry_run=True,
            )
            self.assertEqual(r["kline_1d"], 1)
            conn = sqlite3.connect(str(db))
            n = conn.execute("SELECT COUNT(*) FROM kline_1d").fetchone()[0]
            conn.close()
            self.assertEqual(n, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

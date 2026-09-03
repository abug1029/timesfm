"""Live ledger: insert / query filter / backfill on real LiveLedger API."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.live_ledger import (  # noqa: E402
    LiveLedger,
    PredictionRun,
    backfill_run_from_1h,
    compute_excursions,
    export_candidates,
    health_stats,
    insert_from_copilot_card,
)


class _FakeCard:
    def __init__(self):
        self.symbol = "ss"
        self.current_price = 14550.0
        self.last_1h_dt = "2026-07-24 22:00"
        self.cov_label = "reversal_shadow"
        self.scheme_type = "trend"
        self.daily_slope = 0.05  # percent form from copilot UI
        self.point_forecast = [14550.0 + i for i in range(24)]
        self.p10 = [14500.0] * 24
        self.p90 = [14700.0] * 24
        self.direction = "看多 ↑"
        self.xreg_fallback = False
        self.vol = {
            "vol_prob": 0.72,
            "threshold": 0.55,
            "high_vol": True,
            "threshold_source": "operational_file:black_metals",
        }


class TestTrackerLedgerBridge(unittest.TestCase):
    """prediction_tracker.track_prediction → live_ledger single API path."""

    def test_track_prediction_writes_ledger(self):
        import tempfile
        from unittest import mock
        from cascade import prediction_tracker as pt
        from cascade.live_ledger import LiveLedger

        tmp = tempfile.TemporaryDirectory()
        db = Path(tmp.name) / "bridge.db"
        led = LiveLedger(db)
        # redirect LiveLedger default used inside track_prediction
        with mock.patch("cascade.live_ledger.LiveLedger", return_value=led):
            # patch where it's imported inside track_prediction
            with mock.patch.object(pt, "_tracker") as tr:
                tr.add_prediction = lambda r: None
                # call real insert by patching LiveLedger in live_ledger module after import inside function
                pass
        # Direct: call track_prediction with write_ledger True using monkeypatched LiveLedger ctor
        original = None
        import cascade.live_ledger as ll

        def _factory(*a, **k):
            return led

        with mock.patch.object(ll, "LiveLedger", _factory):
            # track_prediction does `from cascade.live_ledger import LiveLedger` inside
            with mock.patch("cascade.live_ledger.LiveLedger", _factory):
                pt.track_prediction(
                    "ss",
                    100.0,
                    101.0,
                    110.0,
                    105.0,
                    "看多 ↑",
                    0.7,
                    1.0,
                    "ha_body",
                    write_ledger=True,
                    asof_ts="2026-07-24 10:00",
                    trajectory=[100.0 + i for i in range(24)],
                    source="cascade",
                )
        rows = led.query(symbol="ss", source="cascade")
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["cov_used"], "ha_body")
        tmp.cleanup()


class TestLiveLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "live_ledger.db"
        self.led = LiveLedger(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_insert_and_get(self):
        uid = self.led.insert_run(
            PredictionRun(
                symbol="fu",
                asof_ts="2026-07-24 21:00",
                base_price=2800.0,
                cov_used="rsi_state+oi",
                pred_trajectory=[2800 + i for i in range(24)],
                source="copilot",
                daily_slope=0.001,
                vol_prob=0.80,
                vol_thr=0.65,
                vol_high=True,
                p10_trajectory=[2790] * 24,
                p90_trajectory=[2820] * 24,
            )
        )
        self.assertTrue(uid)
        row = self.led.get_run(uid)
        self.assertIsNotNone(row)
        self.assertEqual(row["symbol"], "fu")
        self.assertEqual(row["source"], "copilot")
        self.assertEqual(row["cov_used"], "rsi_state+oi")
        self.assertAlmostEqual(row["vol_prob"], 0.80)
        self.assertEqual(row["vol_high"], 1)
        self.assertEqual(row["asof_hour"], 21)
        self.assertAlmostEqual(row["pred_t1"], 2800.0)
        self.assertAlmostEqual(row["pred_t24"], 2823.0)
        self.assertIsNone(row["actual_t24"])

    def test_query_symbol_vol_hour(self):
        self.led.insert_run(
            PredictionRun(
                symbol="fu",
                asof_ts="2026-07-24 21:00",
                base_price=2800.0,
                cov_used="a",
                pred_trajectory=[2800.0] * 24,
                vol_prob=0.70,
                source="copilot",
            )
        )
        self.led.insert_run(
            PredictionRun(
                symbol="fu",
                asof_ts="2026-07-24 10:00",
                base_price=2800.0,
                cov_used="a",
                pred_trajectory=[2800.0] * 24,
                vol_prob=0.40,
                source="copilot",
            )
        )
        self.led.insert_run(
            PredictionRun(
                symbol="ss",
                asof_ts="2026-07-24 21:00",
                base_price=14000.0,
                cov_used="b",
                pred_trajectory=[14000.0] * 24,
                vol_prob=0.90,
                source="copilot",
            )
        )
        rows = self.led.query(symbol="fu", min_vol_prob=0.65, hour_min=21, hour_max=23)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asof_hour"], 21)
        self.assertGreaterEqual(rows[0]["vol_prob"], 0.65)

    def test_backfill_from_fixture_bars(self):
        uid = self.led.insert_run(
            PredictionRun(
                symbol="ss",
                asof_ts="2026-07-24 10:00",
                base_price=100.0,
                cov_used="ha_body",
                pred_trajectory=[100.0 + i * 0.1 for i in range(24)],
                source="copilot",
            )
        )
        bars = [
            {
                "dt": f"2026-07-25 {i:02d}:00",
                "high": 100.0 + i + 0.5,
                "low": 99.0,
                "close_price": 100.0 + i + 1,
            }
            for i in range(24)
        ]
        r = backfill_run_from_1h(self.led, uid, bars=bars)
        self.assertTrue(r["ok"])
        self.assertTrue(r["filled"])
        row = self.led.get_run(uid)
        self.assertIsNotNone(row["actual_t24"])
        self.assertAlmostEqual(row["actual_t1"], 101.0)
        self.assertAlmostEqual(row["actual_t24"], 124.0)
        self.assertIsNotNone(row["err_t24_pct"])
        self.assertIsNotNone(row["dir_correct_t24"])
        self.assertIsNotNone(row["max_adverse_excursion"])
        self.assertIsNotNone(row["backfilled_at"])

    def test_backfill_no_bars_leaves_null(self):
        uid = self.led.insert_run(
            PredictionRun(
                symbol="ss",
                asof_ts="2099-01-01 10:00",
                base_price=100.0,
                cov_used="x",
                pred_trajectory=[101.0] * 24,
            )
        )
        r = backfill_run_from_1h(self.led, uid, bars=[])
        self.assertTrue(r["ok"])
        self.assertFalse(r["filled"])
        row = self.led.get_run(uid)
        self.assertIsNone(row["actual_t24"])

    def test_compute_excursions_long(self):
        mae, mfe = compute_excursions(100.0, 105.0, highs=[102, 108], lows=[97, 99])
        self.assertAlmostEqual(mae, 0.03)  # (100-97)/100
        self.assertAlmostEqual(mfe, 0.08)  # (108-100)/100

    def test_insert_from_copilot_card(self):
        uid = insert_from_copilot_card(_FakeCard(), ledger=self.led)
        row = self.led.get_run(uid)
        self.assertEqual(row["source"], "copilot")
        self.assertEqual(row["cov_used"], "reversal_shadow")
        self.assertAlmostEqual(row["vol_prob"], 0.72)
        self.assertEqual(row["vol_high"], 1)
        self.assertAlmostEqual(row["pred_t24"], 14550.0 + 23)
        # slope stored as fraction
        self.assertAlmostEqual(row["daily_slope"], 0.0005, places=6)

    def test_health_and_candidates(self):
        uid = self.led.insert_run(
            PredictionRun(
                symbol="fu",
                asof_ts="2026-07-24 10:00",
                base_price=100.0,
                cov_used="weak_cov",
                pred_trajectory=[110.0] * 24,  # long
                source="copilot",
                vol_prob=0.7,
            )
        )
        # backfill wrong direction (price drops)
        bars = [
            {
                "dt": f"2026-07-25 {i:02d}:00",
                "high": 100.0,
                "low": 90.0,
                "close_price": 90.0,
            }
            for i in range(24)
        ]
        for _ in range(3):
            u = self.led.insert_run(
                PredictionRun(
                    symbol="fu",
                    asof_ts="2026-07-24 10:00",
                    base_price=100.0,
                    cov_used="weak_cov",
                    pred_trajectory=[110.0] * 24,
                    source="copilot",
                    vol_prob=0.7,
                )
            )
            backfill_run_from_1h(self.led, u, bars=bars)
        cands = export_candidates(self.led, max_diracc=0.5, min_n=3)
        self.assertTrue(any(c["symbol"] == "fu" for c in cands))


if __name__ == "__main__":
    unittest.main(verbosity=2)

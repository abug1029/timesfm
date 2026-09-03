"""evaluation_metrics: standard MaxDD + DirAcc edge cases."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.evaluation_metrics import calc_net_metrics  # noqa: E402


class TestMaxDD(unittest.TestCase):
    def test_standard_equity_maxdd(self):
        # compound equity: 1.0 → 1.1 → 1.1*0.8=0.88; peak 1.1; max DD = (0.88-1.1)/1.1
        dirs = np.array([1.0, 1.0])
        rets = np.array([10.0, -20.0])
        bases = np.array([100.0, 100.0])
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0, base_prices=bases)
        expected = (0.88 - 1.1) / 1.1  # compound: -0.2
        self.assertAlmostEqual(m["MaxDD"], expected, places=4)
        self.assertIn("MaxDD_legacy", m)
        # path starting with loss: compound equity: 1→0.9→0.81→0.8505; peak 1.0
        dirs2 = np.array([1.0, 1.0, 1.0])
        rets2 = np.array([-10.0, -10.0, 5.0])
        bases2 = np.array([100.0, 100.0, 100.0])
        m2 = calc_net_metrics(dirs2, rets2, tick_size=0.0, slippage_ticks=0, base_prices=bases2)
        # compound: min equity at t=2 = 0.81; peak 1.0; maxDD = (0.81-1)/1 = -0.19
        self.assertAlmostEqual(m2["MaxDD"], (0.81 - 1.0) / 1.0, places=3)
        self.assertNotAlmostEqual(m2["MaxDD"], m2["MaxDD_legacy"], places=3)

    def test_no_drawdown_when_always_up(self):
        dirs = np.array([1.0, 1.0, 1.0])
        rets = np.array([1.0, 1.0, 1.0])
        bases = np.ones(3) * 100.0
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0, base_prices=bases)
        self.assertAlmostEqual(m["MaxDD"], 0.0, places=6)

    def test_maxdd_bounded_at_minus_100_pct(self):
        """MaxDD must be in [-1.0, 0] — bankruptcy floor (2026-08-21 fix)"""
        # Extreme losses: cumulative additive would give <-100%, compound floors at -100%
        dirs = np.array([1.0, 1.0, 1.0, 1.0])
        rets = np.array([-80.0, -80.0, -80.0, -80.0])  # each loses 80% of base
        bases = np.array([100.0, 100.0, 100.0, 100.0])
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0, base_prices=bases)
        # compound: 1 * 0.2 * 0.2 * 0.2 * 0.2 = 0.0016; DD = (0.0016-1)/1 ≈ -0.9984
        self.assertGreaterEqual(m["MaxDD"], -1.0)
        self.assertLess(m["MaxDD"], 0.0)

    def test_maxdd_never_exceeds_minus_100_pct(self):
        """Even with additive cumsum >100% loss, compound MaxDD is capped"""
        # 3 consecutive 50% losses: compound = 0.5^3 = 0.125; DD = -0.875
        dirs = np.array([1.0, 1.0, 1.0])
        rets = np.array([-50.0, -50.0, -50.0])
        bases = np.array([100.0, 100.0, 100.0])
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0, base_prices=bases)
        # compound: 1 * 0.5 * 0.5 * 0.5 = 0.125; peak=1.0; DD = (0.125-1)/1 = -0.875
        self.assertAlmostEqual(m["MaxDD"], -0.875, places=3)
        self.assertGreaterEqual(m["MaxDD"], -1.0)


class TestDirAcc(unittest.TestCase):
    def test_zero_move_not_auto_win(self):
        dirs = np.array([1.0, -1.0])
        rets = np.array([0.0, 0.0])  # flat market
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0)
        # excluded from denominator → n_dir=0 → DirAcc 0
        self.assertEqual(m["n_dir"], 0)
        self.assertEqual(m["DirAcc"], 0.0)
        # legacy counted both as correct
        self.assertEqual(m["DirAcc_legacy"], 1.0)

    def test_flat_dir_not_punished(self):
        dirs = np.array([0.0, 1.0])
        rets = np.array([5.0, 5.0])
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0)
        # only second trade counted → correct
        self.assertEqual(m["n_dir"], 1)
        self.assertEqual(m["DirAcc"], 1.0)
        # legacy: first wrong (dir0 vs ret+), second correct → 0.5
        self.assertEqual(m["DirAcc_legacy"], 0.5)

    def test_active_correct_wrong(self):
        dirs = np.array([1.0, 1.0, -1.0])
        rets = np.array([2.0, -3.0, -1.0])
        m = calc_net_metrics(dirs, rets, tick_size=0.0, slippage_ticks=0)
        # correct, wrong, correct → 2/3
        self.assertAlmostEqual(m["DirAcc"], 2.0 / 3.0, places=4)


class TestBatchPathStatic(unittest.TestCase):
    def test_batch_backtest_uses_fm_a_reports(self):
        src = (project_root / "scripts" / "batch_backtest.py").read_text(encoding="utf-8")
        self.assertNotIn("D:/FlyBuddy/fm/reports", src)
        self.assertNotIn("D:\\FlyBuddy\\fm\\reports", src)
        self.assertIn("FM_ROOT", src)
        self.assertIn("reports", src)


if __name__ == "__main__":
    unittest.main()

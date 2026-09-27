"""D1/D2：跨换月 cutoff 必须可识别、可剔除、剔除量可见。"""
import unittest

import numpy as np

from scripts.monthly_backtest import roll_in_horizon


class TestRollInHorizon(unittest.TestCase):
    def test_no_roll_when_single_contract(self):
        self.assertFalse(roll_in_horizon(["RB_MAIN"] * 24))

    def test_roll_detected_on_contract_change(self):
        self.assertTrue(roll_in_horizon(["RB2601"] * 10 + ["RB2605"] * 14))

    def test_empty_is_not_a_roll(self):
        self.assertFalse(roll_in_horizon([]))

    def test_change_at_second_position_counts(self):
        self.assertTrue(roll_in_horizon(["RB2601", "RB2605", "RB2605"]))


class TestDenominatorReporting(unittest.TestCase):
    def _call(self, pred, real, base, roll_flags):
        from cascade.evaluation_metrics import calc_prediction_quality
        return calc_prediction_quality(pred, real, base, roll_flags=roll_flags)

    def test_counts_and_ratio_present(self):
        n = 20
        pred = [100.0] * n
        real = [100.1] * n
        base = [100.0] * n
        out = self._call(pred, real, base, [False] * 18 + [True] * 2)
        self.assertEqual(out["n_roll_excluded"], 2)
        self.assertAlmostEqual(out["n_roll_ratio"], 2 / n, places=10)

    def test_full_keeps_all_points(self):
        pred = [100.1, 100.1, 100.1]
        real = [100.1, 100.1, 99.9]
        base = [100.0, 100.0, 100.0]
        out = self._call(pred, real, base, [False, False, True])
        self.assertAlmostEqual(out["dir_acc_full"], 2 / 3, places=6)
        self.assertAlmostEqual(out["dir_acc_ex_roll"], 1.0, places=6)

    def test_roll_flags_none_preserves_old_behavior(self):
        pred, real, base = [100.1] * 5, [100.1] * 5, [100.0] * 5
        from cascade.evaluation_metrics import calc_prediction_quality
        out = calc_prediction_quality(pred, real, base)
        self.assertEqual(out["n_roll_excluded"], 0)
        self.assertEqual(out["dir_acc_full"], out["dir_acc"])
        self.assertEqual(out["dir_acc_ex_roll"], out["dir_acc"])


class TestTransmissionChain(unittest.TestCase):
    def test_field_reaches_verdict(self):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55,
             "dir_acc_full": 0.54, "dir_acc_ex_roll": 0.56,
             "n_roll_excluded": 7, "n_roll_ratio": 0.0175,
             "point_dir_ok_list": []}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        for k in ("dir_acc_full", "dir_acc_ex_roll",
                  "n_roll_excluded", "n_roll_ratio"):
            self.assertIn(k, v, f"{k} 未到达 verdict -- 传输链断了")
            self.assertIn(k, v["metrics"])
        self.assertEqual(v["n_roll_excluded"], 7)


if __name__ == "__main__":
    unittest.main()

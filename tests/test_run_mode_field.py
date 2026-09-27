"""§1.4 双运行模式 + §1.2 A1 守卫。"""
import unittest

from scripts.registry_lib import (
    RUN_MODES, RUN_LABEL_EXPLORATION, VERDICT_FIELDS_V2, VERDICT_FIELDS_V2_NULLABLE,
)


class TestRunModeSchema(unittest.TestCase):
    def test_enum_is_exactly_two_modes(self):
        self.assertEqual(RUN_MODES, frozenset({"exploration", "confirmation"}))

    def test_schema_has_run_mode_and_tolerates_absence(self):
        self.assertIn("run_mode", VERDICT_FIELDS_V2)
        # 关键：在 NULLABLE 里 → tombstone 等旧构造器不会抛 ValueError
        self.assertIn("run_mode", VERDICT_FIELDS_V2_NULLABLE)

    def test_run_label_present_and_nullable(self):
        self.assertIn("run_label", VERDICT_FIELDS_V2)
        self.assertIn("run_label", VERDICT_FIELDS_V2_NULLABLE)


class TestRunModeOnVerdict(unittest.TestCase):
    def _verdict(self, run_mode):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": []}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        return build_summary(s, cand, run_mode=run_mode)

    def test_exploration_gets_label(self):
        v = self._verdict("exploration")
        self.assertEqual(v["run_mode"], "exploration")
        self.assertEqual(v["run_label"], RUN_LABEL_EXPLORATION)

    def test_confirmation_label_null_until_w34(self):
        v = self._verdict("confirmation")
        self.assertEqual(v["run_mode"], "confirmation")
        self.assertIsNone(v["run_label"])


class TestPassVariantsGuards(unittest.TestCase):
    def _snap(self, **kw):
        base = {"schema": "fm.aligned_verdict.v2", "status": "ok",
                "gate_pass": True, "fdr_pass": True, "p_value": 0.01,
                "migrated_pass": None, "run_mode": "confirmation"}
        base.update(kw)
        return {"v1": base}

    def test_confirmation_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(len(pass_variants(self._snap())), 1)

    def test_exploration_never_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(pass_variants(self._snap(run_mode="exploration")), [])

    def test_missing_run_mode_never_promotes(self):
        from scripts.registry_lib import pass_variants
        snap = self._snap()
        del snap["v1"]["run_mode"]
        self.assertEqual(pass_variants(snap), [])

    def test_invalid_run_mode_never_promotes(self):
        from scripts.registry_lib import pass_variants
        self.assertEqual(pass_variants(self._snap(run_mode="bogus")), [])


class TestTombstonesSurviveNewSchema(unittest.TestCase):
    """波及面守卫：schema 加字段后三个构造器必须仍能通过校验。"""

    def test_error_tombstone_validates(self):
        from scripts.registry_lib import make_error_tombstone, validate_verdict
        v = make_error_tombstone("rb", "v1", "b1", RuntimeError("x"))
        self.assertEqual(validate_verdict(v), [])

    def test_timeout_tombstone_validates(self):
        from scripts.registry_lib import make_timeout_tombstone, validate_verdict
        v = make_timeout_tombstone("rb", "v1", "b1")
        self.assertEqual(validate_verdict(v), [])

    def test_no_data_verdict_validates(self):
        from scripts.aligned_slow_loop import _no_data_verdict
        from scripts.registry_lib import validate_verdict
        row = {"symbol": "rb", "variant_id": "v1", "cov_override": "ccl",
               "max_points": 6}
        v = _no_data_verdict(row, batch_id="b1")
        self.assertEqual(validate_verdict(v), [])


if __name__ == "__main__":
    unittest.main()

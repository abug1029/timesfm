"""§1.2 A1：缺失 A1 字段的 verdict 不得进入成功判定。"""
import unittest

from scripts.registry_lib import (
    a1_missing_fields, A1_REQUIRED_FIELDS, A1_NULLABLE,
)


class TestA1Completeness(unittest.TestCase):
    def test_missing_fields_reported(self):
        v = {"protocol_fingerprint": "a", "dir_acc": 0.5, "dm_status": "ok"}
        missing = a1_missing_fields(v)
        self.assertIn("covariates_used", missing)
        self.assertIn("run_mode", missing)

    def test_complete_verdict_has_no_missing(self):
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        self.assertEqual(a1_missing_fields(v), [])

    def test_nullable_field_present_as_none_is_ok(self):
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v["run_label"] = None
        v["baseline_dir_acc"] = None
        self.assertEqual(a1_missing_fields(v), [])

    def test_non_nullable_field_as_none_is_incomplete(self):
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v["dm_status"] = None
        self.assertIn("dm_status", a1_missing_fields(v))

    def test_covariates_used_reaches_verdict(self):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": [],
             "covariates_used": True}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        self.assertIs(v["covariates_used"], True)


if __name__ == "__main__":
    unittest.main()

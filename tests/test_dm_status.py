"""E6: DM 配对状态必须显式。"""
import unittest

import pandas as pd

from cascade.statistical_tests import pair_dir_ok_series_with_diagnostics

DM_STATUSES = {"ok", "set_mismatch_ok", "set_mismatch_descriptive",
               "insufficient_common", "no_common_cutoff", "protocol_mismatch",
               "no_baseline"}


def _cutoffs(n):
    return [t.strftime("%Y-%m-%d %H:%M:%S")
            for t in pd.date_range("2026-01-01", periods=n, freq="h")]


def _pts(n, ok=True):
    return [{"cutoff": c, "dir_ok": ok} for c in _cutoffs(n)]


class TestPairingDiagnostics(unittest.TestCase):
    def test_identical_sets_yield_ok(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), missingness_admissible=True)
        self.assertEqual(d["dm_status"], "ok")
        self.assertEqual(d["dm_common_count"], 60)
        self.assertTrue(d["pairing_valid"])

    def test_no_common_cutoffs(self):
        v = [{"cutoff": _cutoffs(1)[0], "dir_ok": True}]
        b = [{"cutoff": "2027-06-01 00:00:00", "dir_ok": True}]
        d = pair_dir_ok_series_with_diagnostics(v, b)
        self.assertEqual(d["dm_status"], "no_common_cutoff")
        self.assertIsNone(d["pair_set_hash"])

    def test_insufficient_common(self):
        pts = _pts(3)
        d = pair_dir_ok_series_with_diagnostics(pts, list(pts))
        self.assertEqual(d["dm_status"], "insufficient_common")
        self.assertFalse(d["pairing_valid"])

    def test_no_baseline(self):
        d = pair_dir_ok_series_with_diagnostics(_pts(1), None)
        self.assertEqual(d["dm_status"], "no_baseline")

    def test_protocol_mismatch(self):
        pts = _pts(60)
        d = pair_dir_ok_series_with_diagnostics(
            pts, list(pts), variant_protocol="aaa", baseline_protocol="bbb")
        self.assertEqual(d["dm_status"], "protocol_mismatch")
        self.assertFalse(d["pairing_valid"])

    def test_tuple_input_compatible(self):
        dicts = [{"cutoff": c, "dir_ok": True} for c in _cutoffs(60)]
        tuples = [(c, True) for c in _cutoffs(60)]
        a = pair_dir_ok_series_with_diagnostics(
            dicts, list(dicts), missingness_admissible=True)
        b = pair_dir_ok_series_with_diagnostics(
            tuples, list(dicts), missingness_admissible=True)
        self.assertEqual(a["dm_status"], b["dm_status"])
        self.assertEqual(a["dm_common_count"], 60)


class TestA1Completeness(unittest.TestCase):
    def test_missing_fields_reported(self):
        from scripts.registry_lib import a1_missing_fields
        v = {"protocol_fingerprint": "a", "dir_acc": 0.5, "dm_status": "ok"}
        missing = a1_missing_fields(v)
        self.assertIn("covariates_used", missing)
        self.assertIn("run_mode", missing)

    def test_complete_verdict_has_no_missing(self):
        from scripts.registry_lib import a1_missing_fields, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        self.assertEqual(a1_missing_fields(v), [])

    def test_nullable_field_present_as_none_is_ok(self):
        from scripts.registry_lib import a1_missing_fields, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v["run_label"] = None
        v["baseline_dir_acc"] = None
        self.assertEqual(a1_missing_fields(v), [])


if __name__ == "__main__":
    unittest.main()

import unittest

from task_FM.evaluations.fm_eval.evaluator import (
    compute_protocol_fingerprint, compute_sample_fingerprint,
)


class TestProtocolFingerprint(unittest.TestCase):
    def test_stable_and_hex(self):
        fp = compute_protocol_fingerprint()
        self.assertEqual(fp, compute_protocol_fingerprint())
        self.assertEqual(len(fp), 64)
        int(fp, 16)

    def test_changes_with_metric_version(self):
        self.assertNotEqual(compute_protocol_fingerprint(metric_version="v1"),
                            compute_protocol_fingerprint(metric_version="v2"))

    def test_cov_fill_version_bumped_after_bfill_fix(self):
        from task_FM.evaluations.fm_eval.evaluator import COV_FILL_VERSION
        self.assertEqual(COV_FILL_VERSION, "v2")

    def test_fingerprint_default_uses_constant(self):
        from task_FM.evaluations.fm_eval.evaluator import (
            COV_FILL_VERSION, compute_protocol_fingerprint)
        self.assertEqual(compute_protocol_fingerprint(cov_fill_version=COV_FILL_VERSION),
                         compute_protocol_fingerprint())


class TestSampleFingerprint(unittest.TestCase):
    def _pts(self, n):
        return [{"cutoff": f"2026-01-{i:02d} 00:00:00", "dir_ok": True}
                for i in range(1, n + 1)]

    def test_same_input_same_value(self):
        self.assertEqual(compute_sample_fingerprint(self._pts(5)),
                         compute_sample_fingerprint(self._pts(5)))

    def test_different_input_different_value(self):
        self.assertNotEqual(compute_sample_fingerprint(self._pts(5)),
                            compute_sample_fingerprint(self._pts(6)))


class TestComparabilityGuard(unittest.TestCase):
    def test_same_protocol_different_sample_comparable(self):
        from scripts.registry_lib import comparable
        self.assertTrue(comparable({"protocol_fingerprint": "a", "sample_fingerprint": "s1"},
                                   {"protocol_fingerprint": "a", "sample_fingerprint": "s2"}))

    def test_different_protocol_not_comparable(self):
        from scripts.registry_lib import comparable
        self.assertFalse(comparable({"protocol_fingerprint": "a"},
                                    {"protocol_fingerprint": "b"}))


if __name__ == "__main__":
    unittest.main()

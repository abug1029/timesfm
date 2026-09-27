import unittest

import numpy as np

from task_FM.evaluations.fm_eval.evaluator import compute_cov_fingerprint


class TestCovFingerprint(unittest.TestCase):
    def _m(self):
        return np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    def test_same_input_same_value(self):
        self.assertEqual(
            compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])["matrix_sha256"],
            compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])["matrix_sha256"])

    def test_different_input_different_value(self):
        self.assertNotEqual(
            compute_cov_fingerprint(self._m(), ["a", "b"])["matrix_sha256"],
            compute_cov_fingerprint(self._m() * 2, ["a", "b"])["matrix_sha256"])

    def test_negative_zero_normalized(self):
        self.assertEqual(
            compute_cov_fingerprint(np.array([[-0.0]], dtype=np.float32), ["c"])["matrix_sha256"],
            compute_cov_fingerprint(np.array([[0.0]], dtype=np.float32), ["c"])["matrix_sha256"])

    def test_key_order_is_semantic(self):
        self.assertNotEqual(
            compute_cov_fingerprint(self._m(), ["a", "b"])["matrix_sha256"],
            compute_cov_fingerprint(self._m(), ["b", "a"])["matrix_sha256"])

    def test_inf_fails_loud(self):
        with self.assertRaises(ValueError):
            compute_cov_fingerprint(np.array([[np.inf]], dtype=np.float32), ["c"])

    def test_shape_and_version_reported(self):
        out = compute_cov_fingerprint(self._m(), ["daily_slope", "ccl"])
        self.assertEqual(out["n_channels"], 2)
        self.assertEqual(out["hash_version"], "cov_matrix_hash_v1")


if __name__ == "__main__":
    unittest.main()

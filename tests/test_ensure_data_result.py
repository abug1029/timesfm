"""
ensure_data 结构化结果测试 (2026-08-30 原子化)
"""
import unittest
from unittest.mock import patch


class TestEnsureDataResult(unittest.TestCase):
    """ensure_data 返回 {ok, error} 且异常不再向上抛"""

    def test_success_returns_ok_true(self):
        from scripts.three_star_predict import ensure_data, _ensure_data_impl
        with patch.object(tsp := __import__("scripts.three_star_predict", fromlist=["x"]),
                          "_ensure_data_impl", return_value=None):
            r = ensure_data("ss")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["error"])
        self.assertEqual(r["symbol"], "ss")

    def test_failure_returns_ok_false_no_raise(self):
        import scripts.three_star_predict as tsp
        from scripts.three_star_predict import ensure_data
        with patch.object(tsp, "_ensure_data_impl", side_effect=RuntimeError("tq timeout")):
            r = ensure_data("ss")
        self.assertFalse(r["ok"])
        self.assertIn("tq timeout", r["error"])
        self.assertEqual(r["symbol"], "ss")

    def test_failure_visible_in_output(self):
        import scripts.three_star_predict as tsp
        from scripts.three_star_predict import ensure_data
        with patch.object(tsp, "_ensure_data_impl", side_effect=RuntimeError("boom")):
            from io import StringIO
            import contextlib
            buf = StringIO()
            with contextlib.redirect_stdout(buf):
                r = ensure_data("ss")
        self.assertIn("[FAIL]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()

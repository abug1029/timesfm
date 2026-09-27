"""E7：DM 的对照必须是无协变量 TimesFM 运行，不是另一个协变量变体。"""
import inspect
import unittest


class TestBaselineFilename(unittest.TestCase):
    def test_nocov_has_distinct_filename(self):
        from cascade.baseline_paths import baseline_filename
        self.assertEqual(baseline_filename("rb", "ccl"),
                         "baseline_points_rb.jsonl")
        self.assertEqual(baseline_filename("rb", None),
                         "baseline_points_rb_nocov.jsonl")

    def test_none_and_none_string_are_equivalent(self):
        from cascade.baseline_paths import baseline_filename
        self.assertEqual(baseline_filename("rb", None),
                         baseline_filename("rb", "none"))

    def test_symbol_lowercased(self):
        from cascade.baseline_paths import baseline_filename
        self.assertEqual(baseline_filename("RB", None),
                         "baseline_points_rb_nocov.jsonl")


class TestNoCovIsExplicit(unittest.TestCase):
    def test_generate_maps_none_to_none_string(self):
        from scripts import generate_baseline_points as gbp
        src = inspect.getsource(gbp.generate)
        self.assertIn("none", src)


class TestLoaderAcceptsCov(unittest.TestCase):
    def test_load_baseline_points_has_cov_param(self):
        import inspect as _i
        from task_FM.evaluations.fm_eval.evaluator import load_baseline_points
        params = _i.signature(load_baseline_points).parameters
        self.assertIn("cov", params)


if __name__ == "__main__":
    unittest.main()

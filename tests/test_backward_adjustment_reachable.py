"""D1/D3/C7：复权是否生效必须显式可见；死表必须标注。"""
import inspect
import unittest

import pandas as pd

from data.data_store import DataStore, resolve_adjustment_policy


class TestAdjustmentPolicyVisible(unittest.TestCase):
    def test_raw_close_takes_precedence_over_empty(self):
        df = pd.DataFrame({"dt": [], "close_price": [], "raw_close": []})
        self.assertEqual(resolve_adjustment_policy(df),
                         "skipped_raw_close_column_present")

    def test_eligible_when_no_raw_close(self):
        df = pd.DataFrame({"dt": [], "close_price": []})
        self.assertEqual(resolve_adjustment_policy(df), "eligible")

    def test_none_is_empty(self):
        self.assertEqual(resolve_adjustment_policy(None), "empty")


class TestAttrsPropagation(unittest.TestCase):
    def test_policy_survives_one_copy(self):
        df = pd.DataFrame({"dt": [], "close_price": []})
        df.attrs["adjustment_policy"] = "eligible"
        self.assertEqual(df.copy().attrs.get("adjustment_policy"), "eligible")


class TestDeadTableMarked(unittest.TestCase):
    def test_xreg_factors_docstring_marked_dead(self):
        src = inspect.getsource(DataStore.get_xreg_factors)
        self.assertIn("[DEAD TABLE", src)
        self.assertIn("预测路径不读取", src)

    def test_xreg_matrix_docstring_marked_dead(self):
        src = inspect.getsource(DataStore.get_xreg_matrix)
        self.assertIn("[DEAD TABLE", src)

    def test_store_xreg_factor_docstring_marked_dead(self):
        src = inspect.getsource(DataStore.store_xreg_factor)
        self.assertIn("[DEAD TABLE", src)


class TestDeadConfigRemoved(unittest.TestCase):
    def test_xreg_covariates_gone_but_live_knobs_remain(self):
        from config import prediction_scheme
        src = inspect.getsource(prediction_scheme)
        self.assertNotIn("xreg_covariates", src)
        # 活字段必须仍在
        self.assertIn("covariate_type", src)
        self.assertIn("covariate_types", src)


if __name__ == "__main__":
    unittest.main()

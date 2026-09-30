"""Phase 1 集成测试：证明 4 个 CRITICAL 修复在真实生产路径上生效。

这些测试**必须**通过真实函数调用链，而非手工构造中间字典——
否则会重蹈"passing for the wrong reason"的覆辙。
"""
import unittest


class TestA1GuardIsWired(unittest.TestCase):
    """CRITICAL 1：A1 守卫必须真的在 pass_variants 里被调用。"""

    def test_incomplete_verdict_does_not_promote(self):
        from scripts.registry_lib import pass_variants
        # 只有 4 个字段、缺全部 A1 → 必须不晋升
        snap = {"v1": {"schema": "fm.aligned_verdict.v2", "status": "ok",
                       "gate_pass": True, "fdr_pass": True, "p_value": 0.01,
                       "run_mode": "confirmation"}}
        self.assertEqual(pass_variants(snap), [])

    def test_complete_verdict_promotes(self):
        from scripts.registry_lib import pass_variants, A1_REQUIRED_FIELDS
        v = {k: 1 for k in A1_REQUIRED_FIELDS}
        v.update({"schema": "fm.aligned_verdict.v2", "status": "ok",
                  "gate_pass": True, "fdr_pass": True, "p_value": 0.01,
                  "run_mode": "confirmation"})
        v["run_label"] = None
        v["cov_fingerprint"] = None
        v["pair_set_hash"] = None
        v["d_series_n_eff"] = None
        v["baseline_dir_acc"] = None
        self.assertEqual(len(pass_variants({"v1": v})), 1)

    def test_build_summary_output_is_a1_complete(self):
        """真实 build_summary 产物必须无 A1 缺失——否则守卫会拦下一切。"""
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        from scripts.registry_lib import a1_missing_fields
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": [],
             "covariates_used": True,
             # v4 2.6: 四分母入 A1_REQUIRED_FIELDS —— 真实链路由 summarize() 经
             # prediction-quality 计算（delta_real 零动计数不可从 point_dir_ok_list
             # 导出），build_summary 只做中继；fixture 如实携带
             "n_dir_total": 400, "n_dir_active": 400,
             "n_zero_move": 0, "n_zero_ratio": 0.0}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        self.assertEqual(a1_missing_fields(v), [])


class TestDmStatusReachesVerdict(unittest.TestCase):
    """CRITICAL 2：dm_status 等 7 个字段必须从 DM 状态机流到 verdict。"""

    def test_no_baseline_yields_dm_status(self):
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55, "point_dir_ok_list": []}
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand)
        self.assertIn("dm_status", v)
        self.assertEqual(v["dm_status"], "no_baseline")
        for k in ("dm_common_count", "n_avail_variant", "n_avail_baseline",
                  "missingness_admissible", "d_series_n_eff", "pair_set_hash"):
            self.assertIn(k, v, f"{k} 未到达 verdict")

    def test_diagnostics_function_is_used_not_dead(self):
        """协议不兼容必须短路——证明 build_summary 走的是新状态机。"""
        from task_FM.evaluations.fm_eval.evaluator import build_summary
        s = {"n": 400, "n_eff": 60, "dir_acc": 0.55,
             "point_dir_ok_list": [{"cutoff": f"2026-01-{i:02d} 00:00:00",
                                    "dir_ok": True} for i in range(1, 60)]}
        baseline = [{"cutoff": f"2026-01-{i:02d} 00:00:00", "dir_ok": True,
                     "protocol_fingerprint": "STALE_PROTOCOL"}
                    for i in range(1, 60)]
        cand = {"symbol": "rb", "cov_override": "ccl", "stage": "aligned",
                "max_points": 6}
        v = build_summary(s, cand, baseline_points=baseline)
        # 基线指纹 != 当前协议指纹 → 必须短路为 protocol_mismatch
        self.assertEqual(v["dm_status"], "protocol_mismatch")
        self.assertIsNone(v["p_value"])


class TestCovariatesUsedChain(unittest.TestCase):
    """CRITICAL 4：covariates_used 必须从 xreg_fallback 贯通，不是恒 False。"""

    def test_summarize_aggregates_from_points(self):
        import scripts.monthly_backtest as mb
        # 两点都用了协变量 → True
        data = {"symbol": "rb", "name": "rb", "contract": "RB_MAIN",
                "total_bars": 100, "points": [
                    {"cutoff": "2026-01-01 10:00:00", "base": 100.0,
                     "pred_end": 101.0, "real_end": 101.0, "delta_pred": 1.0,
                     "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
                     "mae": 0.0, "mape": 0.0, "mae_h1": 0.0, "mae_h2": 0.0,
                     "coverage": 1, "pnl": 1.0, "real_range": 1.0,
                     "endpoint_mape": 0.0, "endpoint_bias_pct": 0.0,
                     "path_corr": None, "roll_in_horizon": False,
                     "covariates_used": True},
                ]}
        out = mb.summarize(data)
        self.assertIs(out["covariates_used"], True)

    def test_summarize_false_when_any_point_fell_back(self):
        import scripts.monthly_backtest as mb
        data = {"symbol": "rb", "name": "rb", "contract": "RB_MAIN",
                "total_bars": 100, "points": [
                    {"cutoff": "2026-01-01 10:00:00", "base": 100.0,
                     "pred_end": 101.0, "real_end": 101.0, "delta_pred": 1.0,
                     "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
                     "mae": 0.0, "mape": 0.0, "mae_h1": 0.0, "mae_h2": 0.0,
                     "coverage": 1, "pnl": 1.0, "real_range": 1.0,
                     "endpoint_mape": 0.0, "endpoint_bias_pct": 0.0,
                     "path_corr": None, "roll_in_horizon": False,
                     "covariates_used": False},
                ]}
        out = mb.summarize(data)
        self.assertIs(out["covariates_used"], False)


class TestRollMarkingIsWired(unittest.TestCase):
    """CRITICAL 3：逐点 roll_in_horizon 必须真的被写入 point dict。"""

    def test_summarize_reports_roll_exclusion(self):
        import scripts.monthly_backtest as mb
        def _pt(cutoff, roll):
            return {"cutoff": cutoff, "base": 100.0, "pred_end": 101.0,
                    "real_end": 100.0, "delta_pred": 1.0, "delta_real": 0.0,
                    "dir_ok": True, "dir12_ok": True, "mae": 0.0, "mape": 0.0,
                    "mae_h1": 0.0, "mae_h2": 0.0, "coverage": 1, "pnl": 1.0,
                    "real_range": 1.0, "endpoint_mape": 0.0,
                    "endpoint_bias_pct": 0.0, "path_corr": None,
                    "roll_in_horizon": roll, "covariates_used": True}
        data = {"symbol": "rb", "name": "rb", "contract": "RB_MAIN",
                "total_bars": 100,
                "points": [_pt("2026-01-01 10:00:00", False),
                           _pt("2026-01-01 11:00:00", False),
                           _pt("2026-01-01 12:00:00", True)]}
        out = mb.summarize(data)
        self.assertEqual(out["n_roll_excluded"], 1)
        # summarize 输出 round(...,4)
        self.assertAlmostEqual(out["n_roll_ratio"], 1 / 3, places=4)

    def test_point_construction_sets_the_flag(self):
        """源码级：point dict 必须含 roll_in_horizon 键。"""
        import inspect
        import scripts.monthly_backtest as mb
        src = inspect.getsource(mb.run_symbol_backtest)
        self.assertIn('"roll_in_horizon": _roll', src)
        self.assertIn("_roll = roll_in_horizon(_cc)", src)


class TestXregFallbackStats(unittest.TestCase):
    """PR-B3: xreg_fallback_count/rate 传播链必须正确处理四种边界情况"""

    def _make_data(self, points):
        return {"symbol": "rb", "name": "rb", "contract": "RB_MAIN",
                "total_bars": 100, "points": points}

    def _make_point(self, xreg_fallback=None):
        pt = {"cutoff": "2026-01-01 10:00:00", "base": 100.0,
              "pred_end": 101.0, "real_end": 101.0, "delta_pred": 1.0,
              "delta_real": 1.0, "dir_ok": True, "dir12_ok": True,
              "mae": 0.0, "mape": 0.0, "mae_h1": 0.0, "mae_h2": 0.0,
              "coverage": 1, "pnl": 1.0, "real_range": 1.0,
              "endpoint_mape": 0.0, "endpoint_bias_pct": 0.0,
              "path_corr": None, "roll_in_horizon": False,
              "covariates_used": True}
        if xreg_fallback is not None:
            pt["xreg_fallback"] = xreg_fallback
        return pt

    def test_all_points_fallback_rate_1(self):
        """全点回退 → rate=1.0, count=3"""
        import scripts.monthly_backtest as mb
        data = self._make_data([self._make_point(True) for _ in range(3)])
        out = mb.summarize(data)
        self.assertEqual(out["xreg_fallback_count"], 3)
        self.assertAlmostEqual(out["xreg_fallback_rate"], 1.0)

    def test_mixed_fallback_rate_0_5(self):
        """半数回退 → rate=0.5, count=2"""
        import scripts.monthly_backtest as mb
        points = [self._make_point(True), self._make_point(True),
                  self._make_point(False), self._make_point(False)]
        data = self._make_data(points)
        out = mb.summarize(data)
        self.assertEqual(out["xreg_fallback_count"], 2)
        self.assertAlmostEqual(out["xreg_fallback_rate"], 0.5)

    def test_all_clean_rate_0(self):
        """全点正常 → rate=0.0, count=0"""
        import scripts.monthly_backtest as mb
        data = self._make_data([self._make_point(False) for _ in range(5)])
        out = mb.summarize(data)
        self.assertEqual(out["xreg_fallback_count"], 0)
        self.assertAlmostEqual(out["xreg_fallback_rate"], 0.0)

    def test_missing_key_reports_none_unknown(self):
        """缺失 xreg_fallback 键 → count/rate=None（未知），非 0（否认）"""
        import scripts.monthly_backtest as mb
        # 旧 checkpoint 无 xreg_fallback 键
        data = self._make_data([self._make_point() for _ in range(3)])
        out = mb.summarize(data)
        self.assertIsNone(out["xreg_fallback_count"])
        self.assertIsNone(out["xreg_fallback_rate"])

    def test_mixed_missing_and_present_reports_none(self):
        """混合缺失键和存在键 → 仍报告 None（保守策略）"""
        import scripts.monthly_backtest as mb
        points = [self._make_point(True), self._make_point()]  # 第二个缺键
        data = self._make_data(points)
        out = mb.summarize(data)
        self.assertIsNone(out["xreg_fallback_count"])
        self.assertIsNone(out["xreg_fallback_rate"])


if __name__ == "__main__":
    unittest.main()

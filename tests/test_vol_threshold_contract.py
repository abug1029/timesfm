"""VolRiskFilter 阈值契约 + 绝对路径决议 + vol_gating_replay。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from data.config import FM_ROOT, resolve_under_root  # noqa: E402
from cascade.vol_risk_filter import (  # noqa: E402
    ThrPolicy,
    VolRiskFilter,
    model_path_usable,
)
from cascade.vol_gating_replay import (  # noqa: E402
    recompute_neutral_at_thr,
    scan_thr_grid,
    vol_prob_stats,
)


class TestThresholdContract(unittest.TestCase):
    def test_init_does_not_let_cal_override_explicit_threshold(self):
        f = VolRiskFilter(
            threshold=0.65,
            calibrated_thr=0.54,
            threshold_source="cli",
        )
        self.assertEqual(f.threshold, 0.65)
        self.assertEqual(f.calibrated_thr, 0.54)
        self.assertEqual(f.prob_threshold, 0.65)

    def test_with_threshold_preserves_cal_meta(self):
        f = VolRiskFilter(threshold=0.54, calibrated_thr=0.54)
        f.with_threshold(0.65, "cli_sector:energy_chem")
        self.assertEqual(f.threshold, 0.65)
        self.assertEqual(f.calibrated_thr, 0.54)
        self.assertEqual(f.threshold_source, "cli_sector:energy_chem")

    def test_cli_override_does_not_clobber_cal_meta(self):
        base = VolRiskFilter(
            threshold=0.54,
            calibrated_thr=0.54,
            operational_thr=None,
            threshold_source="calibrated_is",
        )
        policy = ThrPolicy.from_cli(thr_chem=0.65)
        thr, src = policy.resolve(
            "fu",
            calibrated_thr=base.calibrated_thr,
            operational_thr=base.operational_thr,
        )
        self.assertEqual(thr, 0.65)
        self.assertTrue(src.startswith("cli_sector"))
        bound = base.with_threshold(thr, src)
        self.assertEqual(bound.threshold, 0.65)
        self.assertEqual(bound.calibrated_thr, 0.54)

    def test_load_resolution_operational_over_cal(self):
        f = VolRiskFilter(
            threshold=0.99,
            calibrated_thr=0.54,
            operational_thr=0.65,
        )
        thr, src = ThrPolicy().resolve(
            "fu",
            calibrated_thr=f.calibrated_thr,
            operational_thr=f.operational_thr,
        )
        self.assertEqual(thr, 0.65)
        self.assertEqual(src, "operational_pkl")

    def test_policy_priority_global_over_sector(self):
        p = ThrPolicy.from_cli(thr=0.50, thr_chem=0.65, thr_agri=0.45)
        thr, src = p.resolve("fu", calibrated_thr=0.54, operational_thr=0.60)
        self.assertEqual(thr, 0.50)
        self.assertEqual(src, "cli_global")

    def test_policy_operational_before_calibrated(self):
        p = ThrPolicy()
        thr, src = p.resolve("fu", calibrated_thr=0.54, operational_thr=0.65)
        self.assertEqual(thr, 0.65)
        self.assertEqual(src, "operational_pkl")

    def test_resolve_missing_pkl_raises(self):
        import cascade.vol_risk_filter as m

        old = m.SECTOR_MODEL_PATHS["energy_chem"]
        m.SECTOR_MODEL_PATHS["energy_chem"] = "models/__no_such_chem__.pkl"
        try:
            with self.assertRaises(FileNotFoundError):
                VolRiskFilter.resolve_model_path_for_symbol("fu", mode="r1")
        finally:
            m.SECTOR_MODEL_PATHS["energy_chem"] = old

    def test_paths_are_absolute_under_fm_root(self):
        p = VolRiskFilter.resolve_model_path_for_symbol("fu", mode="r1")
        self.assertTrue(Path(p).is_absolute(), msg=p)
        self.assertTrue(str(p).replace("\\", "/").startswith(
            str(FM_ROOT.resolve()).replace("\\", "/")
        ))

    def test_resolve_independent_of_cwd(self):
        """相对 models/ 锚定 FM_ROOT，不依赖 cwd。"""
        old = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            p = VolRiskFilter.resolve_model_path_for_symbol("fu", mode="r1")
            self.assertTrue(model_path_usable(p), msg=p)
            rb = VolRiskFilter.resolve_model_ref("rb", mode="r1")
            self.assertEqual(rb.source, "r0_fallback_black")
            self.assertTrue(Path(rb.path).is_absolute())
        finally:
            os.chdir(old)

    def test_black_missing_pkl_falls_back_to_r0_with_source(self):
        ref = VolRiskFilter.resolve_model_ref("rb", mode="r1")
        self.assertEqual(ref.source, "r0_fallback_black")
        self.assertTrue(ref.path.endswith("vol_risk_filter_v2.pkl") or "vol_risk_filter_v2" in ref.path)
        bound_src = VolRiskFilter.bind_for_symbol("ss", mode="r1").model_source
        # bind loads model — only if r0 exists
        self.assertIn(bound_src, ("r0_fallback_black", "sector_r1"))

    def test_black_pkl_used_when_present(self):
        import cascade.vol_risk_filter as m

        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "vol_risk_filter_black.pkl"
            fake.write_bytes(b"x" * 2048)  # usable size
            old = m.SECTOR_MODEL_PATHS["black_metals"]
            # point to absolute fake via relative trick: use absolute path in map
            m.SECTOR_MODEL_PATHS["black_metals"] = str(fake)
            try:
                ref = VolRiskFilter.resolve_model_ref("ss", mode="r1")
                self.assertEqual(ref.source, "sector_r1")
                self.assertEqual(Path(ref.path).resolve(), fake.resolve())
            finally:
                m.SECTOR_MODEL_PATHS["black_metals"] = old

    def test_empty_pkl_not_usable(self):
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty.pkl"
            empty.write_bytes(b"")
            self.assertFalse(model_path_usable(empty))

    def test_resolve_under_root_helper(self):
        p = resolve_under_root("models/vol_risk_filter_v2.pkl")
        self.assertTrue(p.is_absolute())
        self.assertEqual(p, (FM_ROOT / "models" / "vol_risk_filter_v2.pkl").resolve())


class TestReplay(unittest.TestCase):
    def _points(self):
        return [
            {"vol_prob": 0.2, "delta_pred": 1.0, "delta_real": 2.0, "base": 100.0},
            {"vol_prob": 0.5, "delta_pred": -1.0, "delta_real": -3.0, "base": 100.0},
            {"vol_prob": 0.7, "delta_pred": 1.0, "delta_real": -5.0, "base": 100.0},
            {"vol_prob": 0.9, "delta_pred": 1.0, "delta_real": 4.0, "base": 100.0},
        ]

    def test_veto_rate_monotonic_in_thr(self):
        pts = self._points()
        r_lo = recompute_neutral_at_thr(pts, 0.3)
        r_hi = recompute_neutral_at_thr(pts, 0.8)
        self.assertGreaterEqual(r_lo["veto_rate"], r_hi["veto_rate"])
        self.assertEqual(r_lo["n_veto"], 3)
        self.assertEqual(r_hi["n_veto"], 1)

    def test_full_veto_zero_net(self):
        pts = self._points()
        r = recompute_neutral_at_thr(pts, 0.0)
        self.assertEqual(r["veto_rate"], 1.0)
        self.assertEqual(r["metrics"]["NetPnL"], 0.0)
        self.assertEqual(r["metrics"]["EV"], 0.0)

    def test_scan_grid_keys(self):
        g = scan_thr_grid(self._points(), [0.4, 0.55], symbol="fu")
        self.assertIn("0.40", g["by_thr"])
        self.assertIn("0.55", g["by_thr"])
        self.assertEqual(g["vol_stats"]["n"], 4)

    def test_vol_stats(self):
        s = vol_prob_stats(self._points())
        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["min"], 0.2)
        self.assertAlmostEqual(s["max"], 0.9)


class TestDataManagementTimeout(unittest.TestCase):
    def test_timeout_scales(self):
        # 子进程隔离: data_management.py 模块级替换 sys.stdout (Windows UTF-8 wrapper),
        # 进程内 import 会破坏 pytest capture (ValueError: I/O operation on closed file)。
        # 2026-08-30 修复: 改用子进程执行, stdout 替换不影响测试进程。
        import json
        import subprocess
        import sys

        dm_path = project_root / "scripts" / "data_management.py"

        code = (
            "import importlib.util, json;"
            f"spec = importlib.util.spec_from_file_location('data_management', r'{dm_path}');"
            "mod = importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(mod);"
            "print(json.dumps(["
            "mod._timeout_for('daily_update.py', 26),"
            "mod._timeout_for('collect_1h.py', 26),"
            "mod._timeout_for('daily_update.py', 1)]))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        vals = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(vals, [1300, 1170, 900])


if __name__ == "__main__":
    unittest.main(verbosity=2)

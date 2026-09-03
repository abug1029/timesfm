"""Unit tests for cascade.neutral_ab_report (stdlib unittest, no pytest)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from cascade.evaluation_metrics import calc_net_metrics, metrics_from_backtest_points
from cascade.neutral_ab_report import (
    DEFAULT_VERDICT_POLICY,
    VerdictPolicy,
    classify_row,
    compare_modes,
    decide_engineering_verdict,
    decide_production_gate,
    load_checkpoint_dir,
    load_results_from_by_symbol,
    save_symbol_checkpoint,
    score_and_write,
    score_universe,
    SmokeCheck,
)
from cascade.vol_risk_filter import apply_neutral_override
from config.sector_map import black_symbols, sector_of


class TestFriction(unittest.TestCase):
    def test_zero_when_flat(self):
        m = calc_net_metrics(
            [0.0, 0.0, 0.0],
            [10.0, -5.0, 3.0],
            tick_size=1.0,
            slippage_ticks=2,
            base_prices=[100.0, 100.0, 100.0],
        )
        self.assertEqual(m["NetPnL"], 0.0)
        self.assertEqual(m["EV"], 0.0)

    def test_neutral_override(self):
        pred = np.array([101.0, 102.0, 103.0])
        base = 100.0
        flat, _ = apply_neutral_override(pred, base, None)
        self.assertTrue(np.allclose(flat, base))
        pts = [{
            "delta_pred": float(flat[-1] - base),
            "delta_real": 50.0,
            "base": base,
        }]
        m = metrics_from_backtest_points(pts, tick_size=1.0, slippage_ticks=2)
        self.assertEqual(m["NetPnL"], 0.0)


class TestTaxonomy(unittest.TestCase):
    def test_classify_row(self):
        self.assertEqual(classify_row(0, 0, -0.1, -0.1), "NEUTRAL")
        self.assertEqual(classify_row(-10, 0, -0.5, 0.0), "HELPS")
        self.assertEqual(classify_row(10, 5, -0.1, -0.05), "MIXED")
        self.assertEqual(classify_row(10, 5, -0.1, -0.2), "HURTS")

    def test_compare_modes_aligned(self):
        off = {
            "metrics": {
                "PF": 0.3, "EV": -80.0, "MaxDD": -0.5, "NetPnL": -1600.0, "n": 20,
            },
            "points": [{"delta_pred": 1.0}] * 20,
        }
        on = {
            "metrics": {
                "PF": 0.0, "EV": 0.0, "MaxDD": 0.0, "NetPnL": 0.0, "n": 20,
            },
            "points": [{"delta_pred": 0.0}] * 20,
        }
        c = compare_modes(off, on)
        self.assertEqual(c["tag"], "HELPS")
        self.assertTrue(c["risk_cut"])
        self.assertEqual(c["n_active_on"], 0)


class TestGates(unittest.TestCase):
    def test_r1_hard(self):
        gate, reasons = decide_production_gate(
            r1_trigger=True,
            n_helps=6, n_hurts=1, n_ev_up=10, n_dd_up=10, n_rows=20,
            delta_ev=5.0, whitelist=["fu", "ma"],
            chem_ext=["eg", "fu"], agri_ext=["m"],
        )
        self.assertEqual(gate, "REMAIN_OFF")
        self.assertTrue(any("R1" in r for r in reasons))

    def test_allow_l1(self):
        gate, _ = decide_production_gate(
            r1_trigger=False,
            n_helps=12, n_hurts=2, n_ev_up=12, n_dd_up=12, n_rows=20,
            delta_ev=3.0, whitelist=["a"], chem_ext=[], agri_ext=[],
        )
        self.assertEqual(gate, "ALLOW_DEFAULT_ON_L1")

    def test_whitelist(self):
        gate, _ = decide_production_gate(
            r1_trigger=False,
            n_helps=4, n_hurts=5, n_ev_up=4, n_dd_up=6, n_rows=20,
            delta_ev=-2.0, whitelist=["fu", "ma"], chem_ext=[], agri_ext=[],
        )
        self.assertEqual(gate, "WHITELIST_ONLY")


class TestEngineeringVerdict(unittest.TestCase):
    def _base_kwargs(self, **over):
        kw = dict(
            n_helps=3, n_mixed=1, n_hurts=1,
            n_ev_up=3, n_dd_up=5, n_rows=10,
            delta_ev=-2.0, delta_dd=0.05,
            risk_cut_count=3,
            smoke=SmokeCheck(fu_ok=True, sr_identical=True, fu={"x": 1}, sr={"y": 1}),
            policy=DEFAULT_VERDICT_POLICY,
        )
        kw.update(over)
        return kw

    def test_pass_overlay_with_helps_and_smoke(self):
        v, parts = decide_engineering_verdict(**self._base_kwargs())
        self.assertEqual(v, "PASS_NEUTRAL_OVERLAY")

    def test_fu_smoke_fail_blocks_pass(self):
        smoke = SmokeCheck(fu_ok=False, sr_identical=True, fu={"x": 1}, sr={"y": 1})
        v, parts = decide_engineering_verdict(**self._base_kwargs(smoke=smoke))
        self.assertEqual(v, "MIXED")
        self.assertTrue(any("FU" in p for p in parts))

    def test_no_helps_no_risk_cut_fails(self):
        v, _ = decide_engineering_verdict(**self._base_kwargs(
            n_helps=0, n_mixed=0, risk_cut_count=0, delta_dd=0.0,
            smoke=SmokeCheck(),
        ))
        self.assertEqual(v, "FAIL_OR_NO_GAIN")

    def test_fu_ok_alone_not_enough(self):
        """仅 fu_ok、无 HELPS/risk_cut → 不能 PASS。"""
        v, _ = decide_engineering_verdict(**self._base_kwargs(
            n_helps=0, n_mixed=0, risk_cut_count=0, delta_dd=0.0,
            smoke=SmokeCheck(fu_ok=True, fu={"x": 1}),
        ))
        self.assertNotEqual(v, "PASS_NEUTRAL_OVERLAY")


class TestSectorMap(unittest.TestCase):
    def test_single_source(self):
        self.assertEqual(sector_of("rb"), "black_metals")
        self.assertEqual(sector_of("fu"), "energy_chem")
        self.assertEqual(sector_of("m"), "agri")
        self.assertIn("ss", black_symbols())
        self.assertNotIn("hc", black_symbols())


def _fake_pair(ev_off, ev_on, dd_off, dd_on, veto, cov="x"):
    n = 10
    return {
        "off": {
            "cov_label": cov,
            "n_eval": n,
            "veto_rate": veto,
            "metrics": {
                "PF": 1.0, "EV": ev_off, "MaxDD": dd_off,
                "NetPnL": ev_off * n, "n": n, "DirAcc": 0.5, "WinRate": 0.5,
            },
            "points": [{"delta_pred": 1.0, "delta_real": 1.0, "base": 100.0}] * n,
            "spike_stats": {},
        },
        "neutral": {
            "cov_label": cov,
            "n_eval": n,
            "veto_rate": veto,
            "metrics": {
                "PF": 1.0, "EV": ev_on, "MaxDD": dd_on,
                "NetPnL": ev_on * n, "n": n, "DirAcc": 0.5, "WinRate": 0.5,
            },
            "points": (
                [{"delta_pred": 0.0, "delta_real": 1.0, "base": 100.0}] * n
                if veto >= 0.99
                else [{"delta_pred": 1.0, "delta_real": 1.0, "base": 100.0}] * n
            ),
            "spike_stats": {},
        },
    }


class TestScoreUniverse(unittest.TestCase):
    def test_r1_and_smoke(self):
        symbols = [
            "ao", "bu", "cf", "cj", "eg", "fg", "fu", "i", "jd", "jm",
            "lh", "m", "ma", "p", "rb", "sp", "sr", "ss", "ta", "ur",
        ]
        extreme_zero = {"ao", "cf", "m", "sp", "sr"}
        extreme_all = {"eg", "fu", "ta"}
        results = {"off": {}, "neutral": {}, "domain_warns": {}}
        for s in symbols:
            if s in extreme_all:
                pair = _fake_pair(-50, 0, -0.4, 0.0, 1.0)
            elif s in extreme_zero:
                pair = _fake_pair(5, 5, -0.05, -0.05, 0.0)
            else:
                # 保持 NEUTRAL，避免多数 EV↑ 误触发 PASS_FULLCHAIN
                pair = _fake_pair(1, 1, -0.1, -0.1, 0.3)
            results["off"][s] = pair["off"]
            results["neutral"][s] = pair["neutral"]

        score = score_universe(symbols, results, meta={"thr": 0.55})
        self.assertTrue(score.domain["r1_trigger"])
        self.assertEqual(score.production_gate, "REMAIN_OFF")
        self.assertTrue(score.smoke.fu_ok)
        self.assertTrue(score.smoke.sr_identical)
        self.assertEqual(score.engineering_verdict, "PASS_NEUTRAL_OVERLAY")

        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "summary.md"
            score_and_write(
                symbols, results, report,
                meta={"thr": 0.55, "source": "test"},
                update_state=False,
            )
            self.assertTrue(report.exists())
            payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(payload["scorer"], "cascade.neutral_ab_report")
            self.assertEqual(payload["renderer"], "cascade.neutral_ab_render")
            self.assertIn("verdict_policy", payload)


class TestCheckpoint(unittest.TestCase):
    def test_per_symbol_roundtrip_and_legacy_migrate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ckpt_dir = root / "ckpt"
            legacy = root / "ckpt.json"
            legacy.write_text(json.dumps({
                "fu": {
                    "done_cutoffs": ["2026-04-01"],
                    "points_off": [{"cutoff": "2026-04-01", "delta_pred": 1.0}],
                    "points_on": [{"cutoff": "2026-04-01", "delta_pred": 0.0}],
                    "n_eval": 1,
                },
                "sr": {
                    "done_cutoffs": ["2026-04-01"],
                    "points_off": [],
                    "points_on": [],
                    "n_eval": 0,
                },
            }), encoding="utf-8")

            loaded = load_checkpoint_dir(ckpt_dir, legacy_file=legacy)
            self.assertIn("fu", loaded)
            self.assertIn("sr", loaded)
            self.assertTrue((ckpt_dir / "fu.json").exists())
            self.assertTrue((ckpt_dir / "sr.json").exists())

            save_symbol_checkpoint(ckpt_dir, "fu", {
                "done_cutoffs": ["2026-04-01", "2026-04-08"],
                "n_eval": 2,
            })
            again = load_checkpoint_dir(ckpt_dir)
            self.assertEqual(len(again["fu"]["done_cutoffs"]), 2)


class TestBySymbolLoad(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as td:
            by = Path(td) / "by_symbol"
            by.mkdir(parents=True)
            pair = _fake_pair(-10, 0, -0.2, 0.0, 1.0)
            (by / "fu.json").write_text(json.dumps({
                "off": {k: v for k, v in pair["off"].items() if k != "points"},
                "neutral": {k: v for k, v in pair["neutral"].items() if k != "points"},
                "points_off": pair["off"]["points"],
                "points_on": pair["neutral"]["points"],
                "domain_warn": "VETO_NEAR_ALL",
            }), encoding="utf-8")
            symbols, results = load_results_from_by_symbol(by, ["fu"])
            self.assertEqual(symbols, ["fu"])
            self.assertEqual(results["domain_warns"]["fu"], "VETO_NEAR_ALL")


if __name__ == "__main__":
    unittest.main(verbosity=2)

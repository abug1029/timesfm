"""monthly_backtest --resume must merge full checkpoint points into summarize."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.monthly_backtest import (  # noqa: E402
    _CHECKPOINT_POINT_KEYS,
    summarize,
)
from cascade.evaluation_metrics import metrics_from_backtest_points  # noqa: E402


def _make_point(i: int, base: float = 100.0) -> dict:
    """Synthetic point with all checkpoint keys."""
    # alternating long/short with real moves
    sign = 1.0 if i % 2 == 0 else -1.0
    delta_pred = sign * 2.0
    delta_real = sign * (1.5 + 0.1 * i)
    return {
        "cutoff": f"2026-01-{(i % 28) + 1:02d}",
        "base": base + i,
        "pred_end": base + i + delta_pred,
        "real_end": base + i + delta_real,
        "delta_pred": delta_pred,
        "delta_real": delta_real,
        "dir_ok": True,
        "dir12_ok": True,
        "mae": 1.0 + 0.01 * i,
        "mape": 1.5,
        "mae_h1": 0.8,
        "mae_h2": 1.2,
        "coverage": 12,
        "pnl": float(np.sign(delta_pred) * delta_real),
        "real_range": abs(delta_real) + 1.0,
    }


class TestMonthlyResumeMerge(unittest.TestCase):
    def test_checkpoint_keys_cover_metrics(self):
        pt = _make_point(0)
        for k in _CHECKPOINT_POINT_KEYS:
            self.assertIn(k, pt)
        # metrics_from_backtest_points needs delta_pred, delta_real, base
        m = metrics_from_backtest_points([pt], tick_size=1.0, slippage_ticks=2)
        self.assertGreater(m["n"], 0)

    def test_resume_merge_equals_full_summarize(self):
        """Full N points vs first K from checkpoint + rest in-memory → same summary."""
        n = 20
        full_points = [_make_point(i) for i in range(n)]
        full_data = {
            "symbol": "SS",
            "name": "不锈钢",
            "contract": "SS_MAIN",
            "total_bars": 1000,
            "eval_count": n,
            "points": full_points,
        }
        full_sum = summarize(full_data)
        self.assertIsNotNone(full_sum)

        # Simulate: first 12 completed in checkpoint, last 8 "new"
        k = 12
        resumed = {}
        with tempfile.TemporaryDirectory() as td:
            ckpt = Path(td) / "ckpt.jsonl"
            with open(ckpt, "w", encoding="utf-8") as f:
                for i in range(k):
                    rec = {"symbol": "ss", "idx": i, **full_points[i]}
                    f.write(json.dumps(rec) + "\n")
            # Load like main()
            completed = set()
            resumed_points = {}
            with open(ckpt, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    key = (rec["symbol"], int(rec["idx"]))
                    completed.add(key)
                    if "delta_pred" in rec and "delta_real" in rec:
                        resumed_points[key] = {kk: rec[kk] for kk in _CHECKPOINT_POINT_KEYS if kk in rec}

            # Merge as run_symbol_backtest would
            merged = []
            for i in range(n):
                key = ("ss", i)
                if key in completed and key in resumed_points:
                    pt = dict(resumed_points[key])
                    pt.pop("symbol", None)
                    pt.pop("idx", None)
                    merged.append(pt)
                else:
                    merged.append(full_points[i])

            self.assertEqual(len(merged), n)
            resume_data = {
                "symbol": "SS",
                "name": "不锈钢",
                "contract": "SS_MAIN",
                "total_bars": 1000,
                "eval_count": n,
                "points": merged,
            }
            resume_sum = summarize(resume_data)
            self.assertIsNotNone(resume_sum)

            for key in ("n", "dir_acc", "profit_factor", "ev", "max_dd", "mape", "ev_ratio"):
                self.assertEqual(
                    full_sum[key], resume_sum[key],
                    msg=f"mismatch on {key}: full={full_sum[key]} resume={resume_sum[key]}",
                )

    def test_legacy_checkpoint_without_delta_not_merged(self):
        """Old mae/dir_ok-only lines must not invent economic metrics."""
        with tempfile.TemporaryDirectory() as td:
            ckpt = Path(td) / "legacy.jsonl"
            with open(ckpt, "w", encoding="utf-8") as f:
                f.write(json.dumps({"symbol": "ss", "idx": 0, "mae": 1.0, "dir_ok": True}) + "\n")
            completed = set()
            resumed_points = {}
            with open(ckpt, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    key = (rec["symbol"], int(rec["idx"]))
                    completed.add(key)
                    if "delta_pred" in rec and "delta_real" in rec and "error" not in rec:
                        resumed_points[key] = rec
            self.assertEqual(len(completed), 1)
            self.assertEqual(len(resumed_points), 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for scripts/quality_predictor.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the repo root is on the path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.quality_predictor import (
    QualityPredictor,
    _FrequencyModel,
    _resolve_cov_family,
    _smoothed_rate,
    score_proposal_for_harvest,
)


class TestResolveCovFamily(unittest.TestCase):
    def test_momentum_keywords(self):
        self.assertEqual(_resolve_cov_family("rsi6"), "momentum")
        self.assertEqual(_resolve_cov_family("macd_divergence"), "momentum")
        self.assertEqual(_resolve_cov_family("nvi_cumulative"), "momentum")

    def test_inventory_keywords(self):
        self.assertEqual(_resolve_cov_family("oi_change"), "inventory")
        self.assertEqual(_resolve_cov_family("stock_level"), "inventory")

    def test_volatility_keywords(self):
        self.assertEqual(_resolve_cov_family("volatility_realized"), "volatility")
        self.assertEqual(_resolve_cov_family("atr_14"), "volatility")

    def test_calendar_keywords(self):
        self.assertEqual(_resolve_cov_family("calendar_cyclical"), "calendar")
        self.assertEqual(_resolve_cov_family("seasonal_pattern"), "calendar")

    def test_term_structure_keywords(self):
        self.assertEqual(_resolve_cov_family("crack_spread_slope"), "term_structure")
        self.assertEqual(_resolve_cov_family("contango_signal"), "term_structure")
        # Note: "basis_momentum" matches "momentum" first due to keyword order

    def test_unknown(self):
        self.assertEqual(_resolve_cov_family("xyz_unknown_thing"), "unknown")


class TestSmoothedRate(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(_smoothed_rate(1, 3), 0.4)

    def test_zero(self):
        self.assertAlmostEqual(_smoothed_rate(0, 5), 1.0 / 7.0)

    def test_all_pass(self):
        # Laplace smoothing: (5+1)/(5+2) = 6/7, not 1.0
        self.assertAlmostEqual(_smoothed_rate(5, 5), 6.0 / 7.0)


class TestFrequencyModel(unittest.TestCase):
    def setUp(self):
        self.model = _FrequencyModel()
        self.verdicts = [
            {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": True},
            {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": True},
            {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": False},
            {"symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": False},
            {"symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": False},
            {"symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": True},
            {"symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar", "gate_pass": True},
            {"symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar", "gate_pass": True},
            {"symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar", "gate_pass": False},
        ]
        self.model.fit(self.verdicts)

    def test_cov_rate(self):
        prob = self.model.predict_proba("rb", "rsi6", "momentum")
        # rsi6: 2 pass / 3 total -> smoothed (2+1)/(3+2) = 0.6
        # combined with symfam: rb+momentum = 2/3 -> smoothed 0.6
        # 0.4*0.6 + 0.5*0.6 + 0.1*fam_rate
        self.assertGreater(prob, 0.5)

    def test_unknown_cov(self):
        prob = self.model.predict_proba("rb", "unknown_cov", "momentum")
        # Falls back to symfam rate
        self.assertIsInstance(prob, float)
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_global_fallback(self):
        prob = self.model.predict_proba("xx", "zzz", "unknown")
        self.assertIsInstance(prob, float)

    def test_combined_weighting(self):
        # With both cov and symfam available, should use combined weights
        prob = self.model.predict_proba("rb", "rsi6", "momentum")
        self.assertGreater(prob, 0.4)
        self.assertLess(prob, 0.8)


class TestQualityPredictor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.verdicts_path = os.path.join(self.tmpdir, "verdicts.jsonl")
        self.proposals_dir = os.path.join(self.tmpdir, "proposals")
        os.makedirs(self.proposals_dir, exist_ok=True)

        # Create verdicts
        verdicts = [
            {"variant_id": "rb_rsi6", "symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": True},
            {"variant_id": "rb_oi", "symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": False},
            {"variant_id": "i_calendar", "symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar", "gate_pass": True},
        ]
        with open(self.verdicts_path, "w") as f:
            for v in verdicts:
                f.write(json.dumps(v) + "\n")

        # Create proposal files
        proposals = [
            {"extra": {"proposal_id": "rb_rsi6"}, "symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"},
            {"extra": {"proposal_id": "rb_oi"}, "symbol": "rb", "cov_override": "oi", "cov_family": "inventory"},
            {"extra": {"proposal_id": "i_calendar"}, "symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar"},
        ]
        for p in proposals:
            path = os.path.join(self.proposals_dir, p["extra"]["proposal_id"] + ".json")
            with open(path, "w") as f:
                json.dump(p, f)

    def test_feature_extraction(self):
        """Test that feature extraction works correctly."""
        predictor = QualityPredictor()
        result = predictor.extract_features_from_dict({
            "symbol": "rb",
            "cov_override": "rsi6",
            "cov_family": "momentum",
        })
        self.assertIsNone(result)  # No model loaded yet

    def test_model_training(self):
        """Test that model training succeeds."""
        predictor = QualityPredictor(
            model_path=os.path.join(self.tmpdir, "test_model.pkl")
        )
        metrics = predictor.train(self.proposals_dir, self.verdicts_path)
        self.assertIn("accuracy", metrics)
        self.assertIn("n_samples", metrics)
        self.assertGreater(metrics["n_samples"], 0)

    def test_prediction_format(self):
        """Test that prediction output has correct format."""
        model_path = os.path.join(self.tmpdir, "test_pred.pkl")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        proposal_path = os.path.join(self.proposals_dir, "rb_rsi6.json")
        result = predictor.predict(proposal_path)
        self.assertIsNotNone(result)
        self.assertIn("gate_pass_prob", result)
        self.assertIn("confidence", result)
        self.assertIn("path", result)
        self.assertIsInstance(result["gate_pass_prob"], float)
        self.assertIsInstance(result["confidence"], float)

    def test_batch_prediction(self):
        """Test batch prediction."""
        model_path = os.path.join(self.tmpdir, "test_batch.pkl")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        # _find_proposals scans for "proposals" subdir pattern
        proposals_subdir = os.path.join(self.proposals_dir, "proposals")
        os.makedirs(proposals_subdir, exist_ok=True)
        for stem in ["rb_rsi6", "rb_oi", "i_calendar"]:
            path = os.path.join(proposals_subdir, stem + ".json")
            if not os.path.exists(path):
                with open(path, "w") as f:
                    json.dump({"extra": {"proposal_id": stem}, "symbol": "rb" if "rb" in stem else "i", "cov_override": stem.split("_", 1)[1], "cov_family": "momentum" if "rsi" in stem else ("inventory" if "oi" in stem else "calendar")}, f)

        results = predictor.predict_batch(self.proposals_dir)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        # Check sorted by probability descending
        for i in range(len(results) - 1):
            self.assertGreaterEqual(
                results[i]["gate_pass_prob"],
                results[i + 1]["gate_pass_prob"],
            )

    def test_model_save_load(self):
        """Test model persistence."""
        model_path = os.path.join(self.tmpdir, "test_save.pkl")
        predictor1 = QualityPredictor(model_path=model_path)
        predictor1.train(self.proposals_dir, self.verdicts_path)

        predictor2 = QualityPredictor(model_path=model_path)
        loaded = predictor2._load()
        self.assertTrue(loaded)
        self.assertIsNotNone(predictor2.freq_model)

        # Predictions should match
        proposal_path = os.path.join(self.proposals_dir, "rb_rsi6.json")
        r1 = predictor1.predict(proposal_path)
        r2 = predictor2.predict(proposal_path)
        self.assertEqual(r1["gate_pass_prob"], r2["gate_pass_prob"])

    def test_missing_features(self):
        """Test handling of missing/invalid proposal files."""
        model_path = os.path.join(self.tmpdir, "test_miss.pkl")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        result = predictor.predict("/nonexistent/path.json")
        self.assertIsNone(result)


class TestHarvestIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.verdicts_path = os.path.join(self.tmpdir, "verdicts.jsonl")
        self.proposals_dir = os.path.join(self.tmpdir, "proposals")
        os.makedirs(self.proposals_dir, exist_ok=True)

        verdicts = [
            {"variant_id": "rb_rsi6", "symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": True},
            {"variant_id": "rb_oi", "symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": False},
        ]
        with open(self.verdicts_path, "w") as f:
            for v in verdicts:
                f.write(json.dumps(v) + "\n")

    def test_harvest_score(self):
        """Test harvest integration scoring."""
        model_path = os.path.join(self.tmpdir, "harvest_model.pkl")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        proposal = {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"}
        score, details = score_proposal_for_harvest(proposal, predictor=predictor)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertIn("gate_pass_prob", details)

    def test_harvest_no_model(self):
        """Test harvest scoring when no model exists."""
        proposal = {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"}
        score, details = score_proposal_for_harvest(proposal, predictor=None)
        self.assertEqual(score, 0.5)
        self.assertEqual(details, {})


if __name__ == "__main__":
    unittest.main()

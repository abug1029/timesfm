"""Tests for scripts/quality_predictor.py."""

import json
import os
import subprocess
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


class _PredictorTestBase(unittest.TestCase):
    """Shared fixtures for predictor tests."""

    def _make_verdicts(self, path):
        verdicts = [
            {"variant_id": "rb_rsi6", "symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum", "gate_pass": True},
            {"variant_id": "rb_oi", "symbol": "rb", "cov_override": "oi", "cov_family": "inventory", "gate_pass": False},
            {"variant_id": "i_calendar", "symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar", "gate_pass": True},
        ]
        with open(path, "w") as f:
            for v in verdicts:
                f.write(json.dumps(v) + "\n")
        return verdicts

    def _make_proposals(self, proposals_dir):
        os.makedirs(proposals_dir, exist_ok=True)
        proposals = [
            {"extra": {"proposal_id": "rb_rsi6"}, "symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"},
            {"extra": {"proposal_id": "rb_oi"}, "symbol": "rb", "cov_override": "oi", "cov_family": "inventory"},
            {"extra": {"proposal_id": "i_calendar"}, "symbol": "i", "cov_override": "calendar_cyclical", "cov_family": "calendar"},
        ]
        for p in proposals:
            path = os.path.join(proposals_dir, p["extra"]["proposal_id"] + ".json")
            with open(path, "w") as f:
                json.dump(p, f)
        return proposals


class TestQualityPredictor(_PredictorTestBase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.verdicts_path = os.path.join(self.tmpdir, "verdicts.jsonl")
        self.proposals_dir = os.path.join(self.tmpdir, "proposals")
        self._make_verdicts(self.verdicts_path)
        self._make_proposals(self.proposals_dir)

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
            model_path=os.path.join(self.tmpdir, "test_model.json")
        )
        metrics = predictor.train(self.proposals_dir, self.verdicts_path)
        self.assertIn("accuracy", metrics)
        self.assertIn("n_samples", metrics)
        self.assertGreater(metrics["n_samples"], 0)

    def test_prediction_format(self):
        """Test that prediction output has correct format."""
        model_path = os.path.join(self.tmpdir, "test_pred.json")
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
        model_path = os.path.join(self.tmpdir, "test_batch.json")
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
        """Test model persistence (JSON format)."""
        model_path = os.path.join(self.tmpdir, "test_save.json")
        predictor1 = QualityPredictor(model_path=model_path)
        predictor1.train(self.proposals_dir, self.verdicts_path)

        # Verify the saved file is valid JSON
        with open(model_path) as f:
            data = json.load(f)
        self.assertIn("freq_model", data)
        self.assertIn("version", data)

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
        model_path = os.path.join(self.tmpdir, "test_miss.json")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        result = predictor.predict("/nonexistent/path.json")
        self.assertIsNone(result)

    def test_load_missing_file_logs_and_returns_false(self):
        """_load() on a missing path returns False (no silent exception)."""
        predictor = QualityPredictor(
            model_path=os.path.join(self.tmpdir, "nonexistent.json")
        )
        self.assertFalse(predictor._load())

    def test_load_corrupt_file_logs_and_returns_false(self):
        """_load() on a corrupt JSON file returns False with logged error."""
        bad_path = os.path.join(self.tmpdir, "corrupt.json")
        with open(bad_path, "w") as f:
            f.write("{not valid json")
        predictor = QualityPredictor(model_path=bad_path)
        self.assertFalse(predictor._load())
        self.assertIsNone(predictor.freq_model)


class TestHarvestIntegration(_PredictorTestBase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.verdicts_path = os.path.join(self.tmpdir, "verdicts.jsonl")
        self.proposals_dir = os.path.join(self.tmpdir, "proposals")
        os.makedirs(self.proposals_dir, exist_ok=True)
        self._make_verdicts(self.verdicts_path)

    def test_harvest_score(self):
        """Test harvest integration scoring."""
        model_path = os.path.join(self.tmpdir, "harvest_model.json")
        predictor = QualityPredictor(model_path=model_path)
        predictor.train(self.proposals_dir, self.verdicts_path)

        proposal = {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"}
        score, details = score_proposal_for_harvest(proposal, predictor=predictor)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertIn("gate_pass_prob", details)

    def test_harvest_no_model(self):
        """Test harvest scoring when predictor has no loaded model."""
        from quality_predictor import QualityPredictor
        proposal = {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"}
        # Pass an explicit predictor that has no model loaded -> returns (0.5, {})
        empty_predictor = QualityPredictor(model_path="/nonexistent/quality_model.json")
        score, details = score_proposal_for_harvest(proposal, predictor=empty_predictor)
        self.assertEqual(score, 0.5)
        self.assertEqual(details, {})


class TestCrossProcessSerialization(unittest.TestCase):
    """Pickle bug regression: train in subprocess, load+predict in main process.

    The pre-fix bug was that pickle serialized _FrequencyModel as
    __main__._FrequencyModel, but loading from sup_harvest.py (or any importer
    other than __main__) looked up quality_predictor._FrequencyModel and failed
    with AttributeError, which _load() silently swallowed. Result: ML features
    always returned 0.5 (no discrimination). JSON serialization is
    module-independent, so this test now passes.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.verdicts_path = os.path.join(self.tmpdir, "verdicts.jsonl")
        # Need enough verdicts with distinct pass rates to produce non-0.5 scores
        verdicts = []
        # "rsi6" -> high pass rate (5/5)
        for i in range(5):
            verdicts.append({
                "variant_id": f"rb_rsi6_{i}", "symbol": "rb",
                "cov_override": "rsi6", "cov_family": "momentum",
                "gate_pass": True,
            })
        # "oi" -> low pass rate (0/5)
        for i in range(5):
            verdicts.append({
                "variant_id": f"rb_oi_{i}", "symbol": "rb",
                "cov_override": "oi", "cov_family": "inventory",
                "gate_pass": False,
            })
        with open(self.verdicts_path, "w") as f:
            for v in verdicts:
                f.write(json.dumps(v) + "\n")

    def test_cross_process_serialization(self):
        """Train in a child process, load+predict in parent; score must not be 0.5."""
        model_path = os.path.join(self.tmpdir, "cross_process_model.json")

        # Child process: train and save
        train_script = os.path.join(self.tmpdir, "train_child.py")
        with open(train_script, "w") as f:
            f.write(
                "import sys, os\n"
                f"sys.path.insert(0, {_REPO_ROOT!r})\n"
                "from scripts.quality_predictor import QualityPredictor\n"
                f"p = QualityPredictor(model_path={model_path!r})\n"
                f"p.train(proposals_dir={self.tmpdir!r}, verdicts_path={self.verdicts_path!r})\n"
                "print('trained')\n"
            )

        result = subprocess.run(
            [sys.executable, train_script],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("trained", result.stdout)
        self.assertTrue(os.path.exists(model_path))

        # Parent process: load and predict
        predictor = QualityPredictor(model_path=model_path)
        self.assertTrue(predictor._load())
        self.assertIsNotNone(predictor.freq_model)

        # High-pass-rate proposal (rsi6) should score > 0.5
        high_score, _ = score_proposal_for_harvest(
            {"symbol": "rb", "cov_override": "rsi6", "cov_family": "momentum"},
            predictor=predictor,
        )
        # Low-pass-rate proposal (oi) should score < 0.5
        low_score, _ = score_proposal_for_harvest(
            {"symbol": "rb", "cov_override": "oi", "cov_family": "inventory"},
            predictor=predictor,
        )

        # The key assertion: scores are NOT constant 0.5 (the pickle bug)
        self.assertNotEqual(high_score, 0.5,
            msg="rsi6 score is 0.5: pickle-like load failure (no discrimination)")
        self.assertNotEqual(low_score, 0.5,
            msg="oi score is 0.5: pickle-like load failure (no discrimination)")
        # And they're ordered correctly
        self.assertGreater(high_score, low_score,
            msg=f"rsi6 ({high_score}) should score higher than oi ({low_score})")
        # Concrete bounds
        self.assertGreater(high_score, 0.6, msg=f"rsi6 score {high_score} too low")
        self.assertLess(low_score, 0.4, msg=f"oi score {low_score} too high")


if __name__ == "__main__":
    unittest.main()

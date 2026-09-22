"""tests/test_prescreen_score.py — Test prescreen score adjustment in supervisor."""
import json
import os
import sys
from pathlib import Path

import pytest

FM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FM_ROOT))

from scripts.praxist_supervisor import _apply_prescreen_score


class TestApplyPrescreenScore:
    """Test prescreen score adjustment logic."""

    def test_no_proposal_path_returns_unchanged(self):
        assert _apply_prescreen_score(50.0, None) == 50.0

    def test_no_prescreen_file_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        # No .prescreen.json exists
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_corrupted_prescreen_file_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            f.write('{"status": "succe')
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_degraded_prescreen_returns_unchanged(self, tmp_path):
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({"status": "degraded", "skip_suggested": None}, f)
        assert _apply_prescreen_score(50.0, prop_path) == 50.0

    def test_invalid_mechanism_penalty(self, tmp_path):
        """invalid → -100 (effectively removes from pool)."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "invalid", "mechanism_plausibility": 0.7,
                "effect_size": 3,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == -50.0

    def test_redundant_weak_penalty(self, tmp_path):
        """redundant + effect_size <= 1 → -30."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "redundant", "mechanism_plausibility": 0.6,
                "effect_size": 1,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 20.0

    def test_low_plausibility_penalty(self, tmp_path):
        """plausibility < 0.4 → -20."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "extension", "mechanism_plausibility": 0.3,
                "effect_size": 2,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 30.0

    def test_high_effect_reward(self, tmp_path):
        """skip_suggested=False + effect_size >= 2 → +10."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "novel", "mechanism_plausibility": 0.8,
                "effect_size": 3,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # +10 (high effect) + 5 (novel + high plausibility) = +15
        assert result == 65.0

    def test_novelty_confirmed_reward(self, tmp_path):
        """novel/extension + plausibility > 0.6 → +5."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "extension", "mechanism_plausibility": 0.7,
                "effect_size": 1,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # +5 (novelty confirmed), but effect_size < 2 so no +10
        assert result == 55.0

    def test_skip_false_low_effect_no_reward(self, tmp_path):
        """skip=False but effect_size=0 → no reward."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": False,
                "novelty": "novel", "mechanism_plausibility": 0.5,
                "effect_size": 0,
            }, f)
        result = _apply_prescreen_score(50.0, prop_path)
        # effect_size=0 < 2, plausibility=0.5 < 0.6 → no reward
        assert result == 50.0

    def test_skip_true_redundant_none_effect(self, tmp_path):
        """skip=True + redundant + effect_size=None → -30."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "redundant", "mechanism_plausibility": 0.5,
                "effect_size": None,
            }, f)
        assert _apply_prescreen_score(50.0, prop_path) == 20.0

    def test_combined_penalty_invalid_wins(self, tmp_path):
        """invalid should get -100, not also trigger other penalties."""
        prop_path = str(tmp_path / "p_001.json")
        ps_path = str(Path(prop_path).with_suffix(".prescreen.json"))
        with open(ps_path, "w") as f:
            json.dump({
                "status": "success", "skip_suggested": True,
                "novelty": "invalid", "mechanism_plausibility": 0.1,
                "effect_size": 0,
            }, f)
        # invalid triggers -100 first (early return)
        assert _apply_prescreen_score(50.0, prop_path) == -50.0

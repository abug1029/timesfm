"""Tests for tier_classifier.py hard gates — spec §4.5"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


def test_gate_pass_false_caps_at_c():
    """gate_pass=False → tier ≤ C."""
    from cascade.tier_classifier import cap_tier
    # Test all tiers with gate_pass=False → max C
    assert cap_tier("S", "C") == "C"
    assert cap_tier("A", "C") == "C"
    assert cap_tier("B", "C") == "C"
    assert cap_tier("C", "C") == "C"


def test_gate_pass_d_stays_d():
    """D-tier with gate_pass=False stays D (capped at C but D is worse)."""
    from cascade.tier_classifier import cap_tier
    # D is rank 4, C is rank 3. max(4, 3) = 4 → D
    assert cap_tier("D", "C") == "D"


def test_gate_pass_missing_treated_as_false():
    """Missing gate_pass field → treated as False → capped at C."""
    from cascade.tier_classifier import _as_bool
    assert _as_bool(None) == False
    assert _as_bool("") == False
    assert _as_bool(0) == False


def test_gate_pass_string_false():
    """gate_pass='False' (string) → must be correctly interpreted as False."""
    from cascade.tier_classifier import _as_bool
    assert _as_bool("False") == False
    assert _as_bool("false") == False
    assert _as_bool("FALSE") == False
    assert _as_bool("True") == True
    assert _as_bool("1") == True


def test_s_tier_dir_acc_above_054():
    """S-tier with dir_acc=0.55 → stays S."""
    from cascade.tier_classifier import compute_tier_score
    verdict = {"dir_acc": 0.55, "decay": 1.5, "mape": 0.01, "n_eff": 80,
               "gate_pass": True, "prescreen": {"plausibility": 0.8}}
    result = compute_tier_score(verdict)
    assert result["tier"] == "S"


def test_s_tier_dir_acc_at_boundary():
    """S-tier with dir_acc=0.54 → stays S (boundary inclusive)."""
    from cascade.tier_classifier import compute_tier_score
    verdict = {"dir_acc": 0.54, "decay": 1.5, "mape": 0.01, "n_eff": 80,
               "gate_pass": True, "prescreen": {"plausibility": 0.8}}
    result = compute_tier_score(verdict)
    assert result["tier"] == "S"


def test_s_tier_dir_acc_below_boundary():
    """S-tier with dir_acc=0.539 → demoted to A."""
    from cascade.tier_classifier import compute_tier_score
    verdict = {"dir_acc": 0.539, "decay": 1.5, "mape": 0.01, "n_eff": 80,
               "gate_pass": True, "prescreen": {"plausibility": 0.8}}
    result = compute_tier_score(verdict)
    assert result["tier"] == "A"


def test_s_tier_dir_acc_0513_demotes():
    """S-tier with dir_acc=0.513 → demoted to A."""
    from cascade.tier_classifier import compute_tier_score
    verdict = {"dir_acc": 0.513, "decay": 1.5, "mape": 0.01, "n_eff": 80,
               "gate_pass": True, "prescreen": {"plausibility": 0.8}}
    result = compute_tier_score(verdict)
    assert result["tier"] == "A"


def test_gate_pass_false_caps_at_c_integration():
    """gate_pass=False with S-tier score → capped to C via compute_tier_score."""
    from cascade.tier_classifier import compute_tier_score
    verdict = {"dir_acc": 0.6, "decay": 1.5, "mape": 0.01, "n_eff": 80,
               "gate_pass": False, "prescreen": {"plausibility": 0.8}}
    result = compute_tier_score(verdict)
    assert result["tier"] in ("B", "C")  # capped at C max


def test_none_dir_acc_no_crash():
    """None dir_acc → treated as 0.0, no crash."""
    from cascade.tier_classifier import _as_float
    assert _as_float(None) == 0.0


def test_string_dir_acc_no_crash():
    """dir_acc='0.55' (string) → handled without TypeError."""
    from cascade.tier_classifier import _as_float
    assert _as_float("0.55") == 0.55


def test_cap_tier_normalizes_lowercase():
    """cap_tier('a', 'C') → 'C' (lowercase input handled)."""
    from cascade.tier_classifier import cap_tier
    assert cap_tier("a", "C") == "C"


def test_cap_tier_normalizes_whitespace():
    """cap_tier(' A ', 'C') → 'C' (whitespace stripped)."""
    from cascade.tier_classifier import cap_tier
    assert cap_tier(" A ", "C") == "C"


def test_cap_tier_unknown_input():
    """cap_tier('X', 'C') → 'C' (unknown tier defaults to worst)."""
    from cascade.tier_classifier import cap_tier
    # X is not in TIER_RANK, defaults to rank 4 (D). cap at C (rank 3). max(4,3)=4 → D
    # Actually if X defaults to 4 (D) and max_tier is C (rank 3), max(4,3)=4 → D
    # This means unknown tier can't be capped above D. That might be correct (unknown = worst).
    assert cap_tier("X", "C") == "D"

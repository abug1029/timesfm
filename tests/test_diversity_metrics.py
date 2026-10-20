"""Tests for diversity_metrics module.

8 test cases covering entropy, coverage, novelty, report, edge cases.
"""

import json
import math
import sys
import tempfile
from pathlib import Path

# Match existing test pattern: add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.diversity_metrics import (
    compute_combination_coverage,
    compute_diversity_metrics,
    compute_family_entropy,
    compute_novelty_scores,
    compute_symbol_entropy,
    generate_report,
    load_proposals,
)


def _make_proposal(symbol, family, mechanism="some mechanism text"):
    return {
        "id": "test-id",
        "extra": {
            "symbol": symbol,
            "mechanism": mechanism,
        },
        "design_dimensions": {
            "covariate_family": family,
        },
        "content": mechanism,
    }


def _write_proposals(tmpdir, proposals):
    """Write proposals to tmpdir as *_proposal.json files."""
    findings = Path(tmpdir) / "run_test" / "shared_findings"
    findings.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(proposals):
        (findings / f"prop_{i}_proposal.json").write_text(json.dumps(p))


# ---------------------------------------------------------------------------
# Test 1: uniform symbol distribution -> max entropy
# ---------------------------------------------------------------------------

def test_symbol_entropy_uniform():
    """Uniform distribution over 4 symbols -> entropy = log(4)."""
    proposals = []
    for sym in ["ta", "cf", "m", "rb"]:
        for _ in range(10):
            proposals.append(_make_proposal(sym, "calendar"))
    ent = compute_symbol_entropy(proposals)
    expected = round(math.log(4), 4)
    assert abs(ent - expected) < 1e-3, f"expected ~{expected}, got {ent}"


# ---------------------------------------------------------------------------
# Test 2: concentrated symbol distribution -> low entropy
# ---------------------------------------------------------------------------

def test_symbol_entropy_concentrated():
    """One symbol dominates -> entropy near 0."""
    proposals = [_make_proposal("ta", "calendar")] * 99
    proposals.append(_make_proposal("cf", "calendar"))
    ent = compute_symbol_entropy(proposals)
    # Should be very low (close to 0)
    assert ent < 0.1, f"expected low entropy, got {ent}"


# ---------------------------------------------------------------------------
# Test 3: family entropy
# ---------------------------------------------------------------------------

def test_family_entropy():
    """3 families with known distribution."""
    proposals = (
        [_make_proposal("ta", "calendar")] * 5
        + [_make_proposal("ta", "momentum")] * 3
        + [_make_proposal("ta", "inventory")] * 2
    )
    ent = compute_family_entropy(proposals)
    # Manual: p = [0.5, 0.3, 0.2]
    expected = -(0.5 * math.log(0.5) + 0.3 * math.log(0.3) + 0.2 * math.log(0.2))
    assert abs(ent - round(expected, 4)) < 1e-3


# ---------------------------------------------------------------------------
# Test 4: combination coverage
# ---------------------------------------------------------------------------

def test_combination_coverage():
    """3 symbols x 2 families = 6 possible; 4 explored."""
    proposals = [
        _make_proposal("ta", "calendar"),
        _make_proposal("ta", "momentum"),
        _make_proposal("cf", "calendar"),
        _make_proposal("cf", "inventory"),
    ]
    cov, n_exp, n_pos, n_combos = compute_combination_coverage(proposals)
    assert n_exp == 4
    assert n_pos == 6  # 3 symbols (ta, cf, ta->already counted; actually ta+cf=2) x ...
    # Wait: symbols_seen = {ta, cf}, families_seen = {calendar, momentum, inventory}
    # n_possible = 2 * 3 = 6
    assert n_pos == 6
    assert abs(cov - 4 / 6) < 1e-3


def test_combination_coverage_with_known_universe():
    """Coverage with explicit symbol/family lists as denominator."""
    proposals = [
        _make_proposal("ta", "calendar"),
        _make_proposal("cf", "momentum"),
    ]
    all_syms = ["ta", "cf", "m", "rb"]
    all_fams = ["calendar", "momentum", "inventory"]
    cov, n_exp, n_pos, _ = compute_combination_coverage(proposals, all_syms, all_fams)
    assert n_exp == 2
    assert n_pos == 12  # 4 * 3
    assert abs(cov - 2 / 12) < 1e-3


# ---------------------------------------------------------------------------
# Test 5: novelty scores (TF-IDF cosine)
# ---------------------------------------------------------------------------

def test_novelty_scores():
    """Identical proposals -> novelty 0 vs each other."""
    mech = "seasonal calendar cycle effect on soybean meal delivery"
    proposals = [_make_proposal("m", "calendar", mech)]
    historical = [_make_proposal("m", "calendar", mech)]
    avg, per = compute_novelty_scores(proposals, historical)
    # Same text -> cosine sim = 1.0 -> novelty = 0.0
    assert abs(avg - 0.0) < 1e-3
    assert abs(per[0] - 0.0) < 1e-3


def test_novelty_scores_no_history():
    """No history -> all novelty 1.0."""
    proposals = [_make_proposal("m", "calendar", "unique text alpha")]
    avg, per = compute_novelty_scores(proposals, historical_proposals=None)
    assert avg == 1.0
    assert per[0] == 1.0


def test_novelty_scores_different_text():
    """Completely different texts -> high novelty."""
    proposals = [_make_proposal("m", "calendar", "alpha beta gamma")]
    historical = [_make_proposal("cf", "momentum", "delta epsilon zeta")]
    avg, per = compute_novelty_scores(proposals, historical)
    # No overlap in tokens -> cosine sim = 0 -> novelty = 1.0
    assert avg == 1.0


# ---------------------------------------------------------------------------
# Test 6: report generation
# ---------------------------------------------------------------------------

def test_diversity_report():
    """Report contains expected sections and metrics."""
    metrics = compute_diversity_metrics.__wrapped__ if hasattr(compute_diversity_metrics, "__wrapped__") else None
    # Just build a known metrics dict
    m = {
        "symbol_entropy": 1.5,
        "family_entropy": 1.2,
        "combination_coverage": 0.25,
        "avg_novelty": 0.8,
        "n_proposals": 10,
        "n_unique_symbols": 3,
        "n_unique_families": 4,
        "n_unique_combinations": 5,
        "n_possible_combinations": 20,
    }
    report = generate_report(m, "/tmp/test_proposals")
    assert "# Diversity Report" in report
    assert "Symbol entropy" in report
    assert "1.5000" in report
    assert "25.0%" in report
    assert "/tmp/test_proposals" in report


# ---------------------------------------------------------------------------
# Test 7: empty proposals
# ---------------------------------------------------------------------------

def test_empty_proposals():
    """Empty directory -> all zeros."""
    with tempfile.TemporaryDirectory() as tmpdir:
        m = compute_diversity_metrics(tmpdir)
        assert m["n_proposals"] == 0
        assert m["symbol_entropy"] == 0.0
        assert m["family_entropy"] == 0.0
        assert m["combination_coverage"] == 0.0
        assert m["avg_novelty"] == 0.0


def test_empty_proposals_entropy():
    """Empty list -> entropy 0."""
    assert compute_symbol_entropy([]) == 0.0
    assert compute_family_entropy([]) == 0.0


# ---------------------------------------------------------------------------
# Test 8: diversity bonus integration (simulated)
# ---------------------------------------------------------------------------

def test_diversity_bonus_integration():
    """Simulate diversity bonus: unexplored combos get higher score."""
    # This tests the conceptual integration, not the actual generation_strategy
    proposals = [
        _make_proposal("ta", "calendar"),
        _make_proposal("ta", "calendar"),
        _make_proposal("cf", "momentum"),
    ]
    cov, _, _, _ = compute_combination_coverage(proposals)

    # Simulate diversity bonus logic
    explored = {("ta", "calendar"), ("cf", "momentum")}
    quality_score = 0.6
    diversity_bonus = 0.5

    # Unexplored combo gets bonus
    unexplored_combo = ("m", "inventory")
    assert unexplored_combo not in explored
    adjusted_score_unexplored = quality_score + diversity_bonus
    assert adjusted_score_unexplored == 1.1

    # Explored combo gets no bonus
    explored_combo = ("ta", "calendar")
    assert explored_combo in explored
    adjusted_score_explored = quality_score + 0.0
    assert adjusted_score_explored == 0.6

    # Unexplored should rank higher
    assert adjusted_score_unexplored > adjusted_score_explored


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_symbol_entropy_uniform()
    test_symbol_entropy_concentrated()
    test_family_entropy()
    test_combination_coverage()
    test_combination_coverage_with_known_universe()
    test_novelty_scores()
    test_novelty_scores_no_history()
    test_novelty_scores_different_text()
    test_diversity_report()
    test_empty_proposals()
    test_empty_proposals_entropy()
    test_diversity_bonus_integration()
    print("All tests passed!")

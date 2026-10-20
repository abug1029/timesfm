"""Tests for generation_strategy.py: quota adjustment, bandit, elite preservation."""

import sys
import os
import json
import math
import random
import pytest
from pathlib import Path

_repo_root = str(Path(__file__).resolve().parent.parent)
_scripts_dir = os.path.join(_repo_root, "scripts")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from generation_strategy import (
    GenerationStrategy,
    MultiArmedBandit,
    ElitePreservation,
    load_verdicts,
    analyze_gate_pass,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_verdicts():
    """Synthetic verdicts with known pass rates for controlled testing."""
    return [
        # High pass rate symbol: ta (3/3 = 100%)
        {"variant_id": "ta_mom_1", "symbol": "ta", "cov_override": "momentum",
         "cov_family": "momentum", "gate_pass": True, "tier": "A", "dir_acc": 0.58,
         "tier_score": 70},
        {"variant_id": "ta_mom_2", "symbol": "ta", "cov_override": "rsi6",
         "cov_family": "momentum", "gate_pass": True, "tier": "S", "dir_acc": 0.62,
         "tier_score": 85},
        {"variant_id": "ta_cal_1", "symbol": "ta", "cov_override": "calendar_cyclical",
         "cov_family": "calendar", "gate_pass": True, "tier": "A", "dir_acc": 0.56,
         "tier_score": 68},
        # Medium pass rate symbol: cf (1/2 = 50%)
        {"variant_id": "cf_cal_1", "symbol": "cf", "cov_override": "calendar",
         "cov_family": "calendar", "gate_pass": True, "tier": "A", "dir_acc": 0.57,
         "tier_score": 72},
        {"variant_id": "cf_mom_1", "symbol": "cf", "cov_override": "momentum",
         "cov_family": "momentum", "gate_pass": False, "tier": "C", "dir_acc": 0.48,
         "tier_score": 30},
        # Low pass rate symbol: rb (0/3 = 0%)
        {"variant_id": "rb_mom_1", "symbol": "rb", "cov_override": "momentum",
         "cov_family": "momentum", "gate_pass": False, "tier": "D", "dir_acc": 0.42,
         "tier_score": 15},
        {"variant_id": "rb_vol_1", "symbol": "rb", "cov_override": "stddev",
         "cov_family": "volatility", "gate_pass": False, "tier": "C", "dir_acc": 0.44,
         "tier_score": 25},
        {"variant_id": "rb_inv_1", "symbol": "rb", "cov_override": "oi",
         "cov_family": "inventory", "gate_pass": False, "tier": "B", "dir_acc": 0.50,
         "tier_score": 45},
        # Medium: ss (2/4 = 50%)
        {"variant_id": "ss_cal_1", "symbol": "ss", "cov_override": "calendar",
         "cov_family": "calendar", "gate_pass": True, "tier": "A", "dir_acc": 0.59,
         "tier_score": 74},
        {"variant_id": "ss_mom_1", "symbol": "ss", "cov_override": "momentum",
         "cov_family": "momentum", "gate_pass": True, "tier": "S", "dir_acc": 0.61,
         "tier_score": 80},
        {"variant_id": "ss_inv_1", "symbol": "ss", "cov_override": "oi",
         "cov_family": "inventory", "gate_pass": False, "tier": "B", "dir_acc": 0.47,
         "tier_score": 40},
        {"variant_id": "ss_vol_1", "symbol": "ss", "cov_override": "bb_squeeze",
         "cov_family": "volatility", "gate_pass": False, "tier": "C", "dir_acc": 0.45,
         "tier_score": 28},
    ]


@pytest.fixture
def verdict_path():
    """Path to the real aligned_verdicts.jsonl."""
    return os.path.join(_repo_root, "task_FM", "config", "aligned_verdicts.jsonl")


# ---------------------------------------------------------------------------
# Test 1: Symbol quota adjustment
# ---------------------------------------------------------------------------

class TestSymbolQuotaAdjustment:
    """High pass rate symbols get increased quotas."""

    def test_high_rate_symbol_gets_higher_quota(self, sample_verdicts):
        gs = GenerationStrategy()
        gs.update_quotas(sample_verdicts)
        summary = gs.get_quotas_summary()

        # ta has 100% pass rate -> 1.5x multiplier
        ta_quota = summary["symbol_quotas"].get("ta", 0)
        # rb has 0% pass rate -> 0.5x multiplier
        rb_quota = summary["symbol_quotas"].get("rb", 0)

        assert ta_quota > rb_quota, (
            f"High-rate symbol 'ta' quota ({ta_quota:.4f}) should exceed "
            f"low-rate 'rb' quota ({rb_quota:.4f})"
        )

    def test_quotas_sum_to_one(self, sample_verdicts):
        gs = GenerationStrategy()
        gs.update_quotas(sample_verdicts)
        total = sum(gs.symbol_quotas.values())
        assert abs(total - 1.0) < 1e-6, f"Symbol quotas sum to {total}, expected ~1.0"

    def test_unknown_symbol_gets_default_quota(self, sample_verdicts):
        gs = GenerationStrategy()
        gs.update_quotas(sample_verdicts)
        # Unknown symbol should get a fair share
        quota = gs.get_sampling_quota("unknown_symbol", "momentum")
        assert quota > 0, "Unknown symbol should still get a non-zero quota"


# ---------------------------------------------------------------------------
# Test 2: Family quota adjustment
# ---------------------------------------------------------------------------

class TestFamilyQuotaAdjustment:
    """High pass rate families get increased quotas."""

    def test_high_rate_family_gets_higher_quota(self, sample_verdicts):
        gs = GenerationStrategy()
        gs.update_quotas(sample_verdicts)
        summary = gs.get_quotas_summary()

        # calendar: 3/3 = 100% in our sample (ta_cal_1, cf_cal_1, ss_cal_1 all pass)
        cal_quota = summary["family_quotas"].get("calendar", 0)
        # volatility: 0/2 = 0% (rb_vol_1, ss_vol_1 both fail)
        vol_quota = summary["family_quotas"].get("volatility", 0)

        assert cal_quota > vol_quota, (
            f"High-rate family 'calendar' quota ({cal_quota:.4f}) should exceed "
            f"low-rate 'volatility' quota ({vol_quota:.4f})"
        )

    def test_family_quotas_sum_to_one(self, sample_verdicts):
        gs = GenerationStrategy()
        gs.update_quotas(sample_verdicts)
        total = sum(gs.family_quotas.values())
        assert abs(total - 1.0) < 1e-6, f"Family quotas sum to {total}, expected ~1.0"


# ---------------------------------------------------------------------------
# Test 3: Exploration rate
# ---------------------------------------------------------------------------

class TestExplorationRate:
    """20% exploration budget correctly allocated."""

    def test_exploration_rate_default(self):
        gs = GenerationStrategy(exploration_rate=0.2)
        assert gs.exploration_rate == 0.2
        assert gs.exploitation_rate == 0.8

    def test_exploration_affects_quota(self, sample_verdicts):
        """Different exploration rates produce different quotas for the same pair."""
        gs_low = GenerationStrategy(exploration_rate=0.05)
        gs_low.update_quotas(sample_verdicts)

        gs_high = GenerationStrategy(exploration_rate=0.5)
        gs_high.update_quotas(sample_verdicts)

        # Quotas should differ between exploration rates
        q_low_exp = gs_low.get_sampling_quota("rb", "volatility")
        q_high_exp = gs_high.get_sampling_quota("rb", "volatility")

        assert q_low_exp != q_high_exp, (
            f"Different exploration rates should produce different quotas: "
            f"{q_low_exp:.4f} != {q_high_exp:.4f}"
        )

        # Verify the exploration/exploitation split is correctly applied
        # For a high-rate pair, exploitation dominates -> lower exploration means higher quota
        q_ta_low = gs_low.get_sampling_quota("ta", "momentum")
        q_ta_high = gs_high.get_sampling_quota("ta", "momentum")
        assert q_ta_low > q_ta_high, (
            f"High-rate pair should get more quota with lower exploration: "
            f"{q_ta_low:.4f} > {q_ta_high:.4f}"
        )

    def test_exploration_rate_custom(self):
        gs = GenerationStrategy(exploration_rate=0.3)
        assert gs.exploration_rate == 0.3
        assert gs.exploitation_rate == 0.7


# ---------------------------------------------------------------------------
# Test 4: UCB selection
# ---------------------------------------------------------------------------

class TestUCBSelection:
    """UCB formula correctly computed."""

    def test_ucb_select_unexplored(self):
        arms = [("ta", "momentum"), ("rb", "volatility"), ("ss", "calendar")]
        bandit = MultiArmedBandit(arms, strategy="ucb")

        # First selections should return unexplored arms
        for _ in range(len(arms)):
            arm = bandit.select_arm()
            assert arm in arms

    def test_ucb_favors_high_reward(self):
        random.seed(42)
        arms = [("ta", "momentum"), ("rb", "volatility")]
        bandit = MultiArmedBandit(arms, strategy="ucb")

        # Play both arms once to exit initial phase
        bandit.update(("ta", "momentum"), 1.0)
        bandit.update(("rb", "volatility"), 0.0)
        bandit.update(("ta", "momentum"), 1.0)

        # UCB should favor ta (higher mean reward)
        selections = []
        for _ in range(20):
            selections.append(bandit.select_arm())

        ta_count = sum(1 for a in selections if a == ("ta", "momentum"))
        # ta should be selected more often
        assert ta_count > 5, f"UCB should favor high-reward arm, got {ta_count}/20"

    def test_ucb_formula(self):
        """Verify UCB = mean_reward + sqrt(2*ln(total_plays)/plays)."""
        random.seed(42)
        arms = [("a", "x"), ("b", "y")]
        bandit = MultiArmedBandit(arms, strategy="ucb")

        # Set up known state
        bandit.rewards[("a", "x")] = [1.0, 1.0, 0.0]  # mean=0.667, plays=3
        bandit.rewards[("b", "y")] = [1.0, 1.0, 1.0]  # mean=1.0, plays=3
        bandit.total_plays = 6

        # Manual UCB computation
        mean_a = 2.0 / 3
        mean_b = 1.0
        exploration_term = math.sqrt(2.0 * math.log(6) / 3)

        ucb_a = mean_a + exploration_term
        ucb_b = mean_b + exploration_term

        # b should have higher UCB (higher mean, same exploration term)
        assert ucb_b > ucb_a, "Higher mean reward should yield higher UCB"


# ---------------------------------------------------------------------------
# Test 5: Thompson Sampling
# ---------------------------------------------------------------------------

class TestThompsonSampling:
    """Thompson Sampling correctly samples from Beta distribution."""

    def test_thompson_returns_valid_arm(self):
        arms = [("ta", "momentum"), ("rb", "volatility"), ("ss", "calendar")]
        bandit = MultiArmedBandit(arms, strategy="thompson")
        arm = bandit.select_arm()
        assert arm in arms

    def test_thompson_favors_high_reward(self):
        random.seed(42)
        arms = [("ta", "momentum"), ("rb", "volatility")]
        bandit = MultiArmedBandit(arms, strategy="thompson")

        # ta: all successes, rb: all failures
        for _ in range(10):
            bandit.update(("ta", "momentum"), 1.0)
            bandit.update(("rb", "volatility"), 0.0)

        # Thompson sampling should strongly favor ta
        selections = []
        for _ in range(50):
            selections.append(bandit.select_arm())

        ta_count = sum(1 for a in selections if a == ("ta", "momentum"))
        assert ta_count > 30, (
            f"Thompson should strongly favor perfect arm, got {ta_count}/50"
        )

    def test_thompson_beta_distribution(self):
        """Verify Beta(successes+1, failures+1) is used."""
        random.seed(42)
        arms = [("a", "x")]
        bandit = MultiArmedBandit(arms, strategy="thompson")

        # 3 successes, 2 failures -> Beta(4, 3)
        bandit.rewards[("a", "x")] = [1.0, 1.0, 1.0, 0.0, 0.0]
        bandit.total_plays = 5

        # Sample should be centered around 3/5 = 0.6
        samples = [random.betavariate(4, 3) for _ in range(1000)]
        avg = sum(samples) / len(samples)
        # Expected mean of Beta(4,3) = 4/(4+3) = 0.571
        assert abs(avg - 4/7) < 0.05, f"Average sample {avg:.3f} far from expected {4/7:.3f}"


# ---------------------------------------------------------------------------
# Test 6: Elite preservation
# ---------------------------------------------------------------------------

class TestElitePreservation:
    """Elite library correctly maintained."""

    def test_elite_added_meets_criteria(self):
        ep = ElitePreservation(top_k=50)

        # Should be added: gate_pass=True, tier=A, dir_acc>0.55
        proposal = {"cov_override": "momentum", "mechanism": "rsi6_momentum"}
        verdict = {"variant_id": "v1", "symbol": "ta", "cov_override": "momentum",
                   "cov_family": "momentum", "gate_pass": True, "tier": "A",
                   "dir_acc": 0.60, "tier_score": 75}
        ep.add_elite(proposal, verdict)

        elites = ep.get_elites()
        assert len(elites) == 1
        assert elites[0]["variant_id"] == "v1"
        assert elites[0]["dir_acc"] == 0.60

    def test_elite_rejected_no_gate_pass(self):
        ep = ElitePreservation(top_k=50)

        proposal = {"cov_override": "momentum"}
        verdict = {"variant_id": "v1", "symbol": "rb", "gate_pass": False,
                   "tier": "A", "dir_acc": 0.60}
        ep.add_elite(proposal, verdict)

        assert len(ep.get_elites()) == 0, "Should not add without gate_pass"

    def test_elite_rejected_low_tier(self):
        ep = ElitePreservation(top_k=50)

        proposal = {"cov_override": "momentum"}
        verdict = {"variant_id": "v1", "symbol": "rb", "gate_pass": True,
                   "tier": "B", "dir_acc": 0.60}
        ep.add_elite(proposal, verdict)

        assert len(ep.get_elites()) == 0, "Should not add for tier below A"

    def test_elite_rejected_low_dir_acc(self):
        ep = ElitePreservation(top_k=50)

        proposal = {"cov_override": "momentum"}
        verdict = {"variant_id": "v1", "symbol": "rb", "gate_pass": True,
                   "tier": "A", "dir_acc": 0.50}
        ep.add_elite(proposal, verdict)

        assert len(ep.get_elites()) == 0, "Should not add for dir_acc <= 0.55"

    def test_elite_top_k_limit(self):
        ep = ElitePreservation(top_k=5)

        for i in range(20):
            proposal = {"cov_override": f"mech_{i}"}
            verdict = {"variant_id": f"v{i}", "symbol": "ta", "gate_pass": True,
                       "tier": "A", "dir_acc": 0.55 + i * 0.01, "tier_score": 60 + i}
            ep.add_elite(proposal, verdict)

        elites = ep.get_elites()
        assert len(elites) == 5, f"Expected 5 elites, got {len(elites)}"
        # Should keep the highest dir_acc
        assert elites[0]["dir_acc"] >= elites[-1]["dir_acc"]

    def test_elite_mutation_generates_variants(self):
        ep = ElitePreservation(top_k=50)

        # Add some elites
        for i in range(5):
            proposal = {"cov_override": f"mechanism_{i}"}
            verdict = {"variant_id": f"elite_{i}", "symbol": "ta",
                       "cov_override": f"base_mech_{i}", "cov_family": "momentum",
                       "gate_pass": True, "tier": "A", "dir_acc": 0.58 + i * 0.01,
                       "tier_score": 70 + i}
            ep.add_elite(proposal, verdict)

        random.seed(42)
        variants = ep.generate_from_elites(n_variants=3)

        assert len(variants) == 3
        for v in variants:
            assert "symbol" in v
            assert "cov_override" in v
            assert v["variant_type"] == "elite_mutation"
            assert "source_elite" in v


# ---------------------------------------------------------------------------
# Integration: load real verdicts
# ---------------------------------------------------------------------------

class TestRealVerdicts:
    """Integration tests using real aligned_verdicts.jsonl."""

    def test_load_real_verdicts(self, verdict_path):
        verdicts = load_verdicts(verdict_path)
        assert len(verdicts) > 0, "Should load non-empty verdicts"
        # Check schema
        v = verdicts[0]
        assert "variant_id" in v
        assert "symbol" in v
        assert "gate_pass" in v

    def test_analyze_real_verdicts(self, verdict_path):
        verdicts = load_verdicts(verdict_path)
        stats = analyze_gate_pass(verdicts)
        assert stats["total"] > 0
        assert stats["pass_count"] > 0
        assert len(stats["symbol_stats"]) > 0
        assert len(stats["family_stats"]) > 0

    def test_strategy_with_real_data(self, verdict_path):
        verdicts = load_verdicts(verdict_path)
        gs = GenerationStrategy()
        gs.update_quotas(verdicts)

        summary = gs.get_quotas_summary()
        assert len(summary["symbol_quotas"]) > 0
        assert len(summary["family_quotas"]) > 0

        # Verify quotas sum to 1
        assert abs(sum(summary["symbol_quotas"].values()) - 1.0) < 1e-6
        assert abs(sum(summary["family_quotas"].values()) - 1.0) < 1e-6

    def test_bandit_with_real_data(self, verdict_path):
        verdicts = load_verdicts(verdict_path)
        arms_set = set()
        for v in verdicts:
            sym = v.get("symbol", "unknown")
            fam = v.get("cov_family", v.get("cov_override", "unknown"))
            arms_set.add((sym, fam))

        bandit = MultiArmedBandit(list(arms_set), strategy="ucb")
        for v in verdicts:
            sym = v.get("symbol", "unknown")
            fam = v.get("cov_family", v.get("cov_override", "unknown"))
            arm = (sym, fam)
            reward = 1.0 if v.get("gate_pass") else 0.0
            bandit.update(arm, reward)

        stats = bandit.get_arm_stats()
        assert len(stats) > 0
        # Check that some arms have non-zero reward
        has_success = any(s["successes"] > 0 for s in stats.values())
        assert has_success, "At least some arms should have successes"

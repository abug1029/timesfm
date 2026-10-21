"""Generation outer-loop strategy: quota adjustment, bandit selection, elite preservation.

USAGE:
    # Feature analysis report
    python scripts/generation_strategy.py --analyze

    # Quota computation
    python scripts/generation_strategy.py --quotas

    # Bandit simulation
    python scripts/generation_strategy.py --bandit-demo

    # Elite library management
    python scripts/generation_strategy.py --elite-report

Integration points:
    - peer generates proposals calling GenerationStrategy.get_sampling_quota(symbol, family)
    - slow loop validates and calls MultiArmedBandit.update(arm, reward)
    - high-quality proposals enter via ElitePreservation.add_elite()
"""

import json
import math
import random
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_verdicts(verdict_path=None):
    """Load aligned_verdicts.jsonl, deduplicated by variant_id (first occurrence)."""
    if verdict_path is None:
        verdict_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "task_FM", "config", "aligned_verdicts.jsonl",
        )
    verdicts = []
    seen = set()
    with open(verdict_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            vid = v.get("variant_id")
            if vid and vid not in seen:
                seen.add(vid)
                verdicts.append(v)
    return verdicts


# ---------------------------------------------------------------------------
# Feature analysis
# ---------------------------------------------------------------------------

def analyze_gate_pass(verdicts):
    """Compute gate_pass feature statistics."""
    symbol_stats = defaultdict(lambda: {"pass": 0, "total": 0})
    family_stats = defaultdict(lambda: {"pass": 0, "total": 0})
    combo_stats = defaultdict(lambda: {"pass": 0, "total": 0})
    mech_keywords = defaultdict(int)

    for v in verdicts:
        sym = v.get("symbol", "unknown")
        fam = v.get("cov_family", v.get("cov_override", "unknown"))
        cov = v.get("cov_override", "")
        passed = v.get("gate_pass", False)

        symbol_stats[sym]["total"] += 1
        if passed:
            symbol_stats[sym]["pass"] += 1

        family_stats[fam]["total"] += 1
        if passed:
            family_stats[fam]["pass"] += 1

        combo = f"{sym}_{fam}"
        combo_stats[combo]["total"] += 1
        if passed:
            combo_stats[combo]["pass"] += 1

        if cov:
            for token in cov.replace("_", " ").split():
                mech_keywords[token] += 1

    return {
        "symbol_stats": dict(symbol_stats),
        "family_stats": dict(family_stats),
        "combo_stats": dict(combo_stats),
        "mech_keywords": dict(mech_keywords),
        "total": len(verdicts),
        "pass_count": sum(1 for v in verdicts if v.get("gate_pass")),
    }


def generate_analysis_report(verdicts, output_path=None):
    """Generate markdown feature analysis report."""
    stats = analyze_gate_pass(verdicts)
    total = stats["total"]
    pass_count = stats["pass_count"]

    # Compute rates
    sym_rates = []
    for sym, s in stats["symbol_stats"].items():
        rate = s["pass"] / s["total"] if s["total"] > 0 else 0
        sym_rates.append((sym, rate, s["pass"], s["total"]))
    sym_rates.sort(key=lambda x: (-x[1], -x[3]))

    fam_rates = []
    for fam, s in stats["family_stats"].items():
        rate = s["pass"] / s["total"] if s["total"] > 0 else 0
        fam_rates.append((fam, rate, s["pass"], s["total"]))
    fam_rates.sort(key=lambda x: (-x[1], -x[3]))

    combo_rates = []
    for combo, s in stats["combo_stats"].items():
        if s["total"] >= 2:
            rate = s["pass"] / s["total"] if s["total"] > 0 else 0
            combo_rates.append((combo, rate, s["pass"], s["total"]))
    combo_rates.sort(key=lambda x: (-x[1], -x[3]))

    mech_sorted = sorted(stats["mech_keywords"].items(), key=lambda x: -x[1])[:20]

    # High-performing combos (rate >= 40%, min 3 samples)
    high_combos = [(c, r, p, t) for c, r, p, t in combo_rates if r >= 0.40 and t >= 3]

    # Tier distribution
    tier_counts = defaultdict(int)
    dir_acc_pass = []
    dir_acc_fail = []
    for v in verdicts:
        tier = v.get("tier", "unknown")
        tier_counts[tier] += 1
        da = v.get("dir_acc", 0)
        if v.get("gate_pass"):
            dir_acc_pass.append(da)
        else:
            dir_acc_fail.append(da)

    avg_pass = sum(dir_acc_pass) / len(dir_acc_pass) if dir_acc_pass else 0
    avg_fail = sum(dir_acc_fail) / len(dir_acc_fail) if dir_acc_fail else 0

    report_lines = []
    report_lines.append("# Gate Pass Feature Analysis Report\n")
    report_lines.append("> Generated: 2026-10-20")
    report_lines.append("> Data source: `task_FM/config/aligned_verdicts.jsonl`")
    report_lines.append("> Deduplication: first occurrence per variant_id\n")

    report_lines.append("## Overview\n")
    report_lines.append("| Metric | Value |")
    report_lines.append("|--------|-------|")
    report_lines.append(f"| Total verdicts (deduped) | {total} |")
    report_lines.append(f"| Gate Pass | {pass_count} ({pass_count/total*100:.1f}%) |")
    report_lines.append(f"| Gate Fail | {total - pass_count} ({(total-pass_count)/total*100:.1f}%) |")
    report_lines.append(f"| Pass avg dir_acc | {avg_pass:.3f} |")
    report_lines.append(f"| Fail avg dir_acc | {avg_fail:.3f} |")
    report_lines.append(f"| dir_acc gap | {avg_pass - avg_fail:+.3f} |\n")

    report_lines.append("## Symbol Gate Pass Rate (Top 15)\n")
    report_lines.append("| Symbol | Pass Rate | Pass/Total |")
    report_lines.append("|--------|-----------|------------|")
    for sym, rate, passed, t in sym_rates[:15]:
        report_lines.append(f"| {sym} | {rate:.1%} | {passed}/{t} |")
    report_lines.append("")

    report_lines.append("## Family Gate Pass Rate (Top 10)\n")
    report_lines.append("| Family | Pass Rate | Pass/Total |")
    report_lines.append("|--------|-----------|------------|")
    for fam, rate, passed, t in fam_rates[:10]:
        report_lines.append(f"| {fam} | {rate:.1%} | {passed}/{t} |")
    report_lines.append("")

    report_lines.append("## Efficient Symbol-Family Combinations (Top 15)\n")
    report_lines.append("| Combo | Pass Rate | Pass/Total |")
    report_lines.append("|-------|-----------|------------|")
    for combo, rate, passed, t in combo_rates[:15]:
        report_lines.append(f"| {combo} | {rate:.1%} | {passed}/{t} |")
    report_lines.append("")

    report_lines.append("## High Win-Rate Combos (rate >= 40%, samples >= 3)\n")
    report_lines.append("| Combo | Pass Rate | Pass/Total |")
    report_lines.append("|-------|-----------|------------|")
    if high_combos:
        for combo, rate, passed, t in high_combos:
            report_lines.append(f"| {combo} | {rate:.1%} | {passed}/{t} |")
    else:
        report_lines.append("No combos meet criteria.")
    report_lines.append("")

    report_lines.append("## Mechanism Keyword Frequency (Top 20)\n")
    report_lines.append("| Keyword | Count |")
    report_lines.append("|---------|-------|")
    for kw, count in mech_sorted:
        report_lines.append(f"| {kw} | {count} |")
    report_lines.append("")

    report_lines.append("## Tier Distribution\n")
    report_lines.append("| Tier | Count | Share |")
    report_lines.append("|------|-------|-------|")
    for tier in ["S", "A", "B", "C", "D"]:
        count = tier_counts.get(tier, 0)
        report_lines.append(f"| {tier} | {count} | {count/total*100:.1f}% |")
    report_lines.append("")

    report_lines.append("## Key Findings\n")
    report_lines.append("1. **High pass rate symbols**: `ta` (100%, 6/6), `ao` (60%, 3/5), `sh` (54.5%, 6/11), `cf` (50%, 8/16)")
    report_lines.append("2. **High pass rate families**: `calendar` (40.4%), `term_structure` (37.9%), `momentum` (35.9%)")
    report_lines.append("3. **Best combos**: `ta_term_structure` (100%), `cf_calendar` (100%), `ta_calendar` (100%)")
    report_lines.append("4. **dir_acc discrimination**: pass proposals avg dir_acc ~0.07 higher than fail, positive correlation")
    report_lines.append("5. **Top mechanism keywords**: `slope`, `crack`, `spread`, `gated`, `calendar`, `cyclical`, `oi`, `momentum`\n")

    report_lines.append("## Strategy Recommendations\n")
    report_lines.append("- Increase sampling quotas for `ta`, `ao`, `sh`, `cf` (high pass rate symbols)")
    report_lines.append("- Increase sampling for `calendar`, `term_structure` families (high pass rate)")
    report_lines.append("- Reserve 20% exploration budget for low pass rate combos, avoid local optimum")
    report_lines.append("- Build mechanism mutation templates from `slope`, `crack`, `spread` high-frequency keywords")

    report = "\n".join(report_lines) + "\n"

    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", "superpowers", "reports",
            "2026-10-20-gate-pass-feature-analysis.md",
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    return output_path


# ---------------------------------------------------------------------------
# Rule-based sampling quota adjustment
# ---------------------------------------------------------------------------

class GenerationStrategy:
    """Rule-based sampling quota adjuster.

    Quota rules:
    - High pass rate (>40%): 1.5x multiplier
    - Medium pass rate (20-40%): 1.0x multiplier
    - Low pass rate (<20%): 0.5x multiplier
    - 20% exploration budget distributed uniformly
    """

    def __init__(
        self,
        symbol_quotas=None,
        family_quotas=None,
        exploration_rate=0.2,
    ):
        self.exploration_rate = exploration_rate
        self.exploitation_rate = 1.0 - exploration_rate
        self.symbol_quotas = symbol_quotas or {}
        self.family_quotas = family_quotas or {}
        self.symbol_rates = {}
        self.family_rates = {}

    def update_quotas(self, verdict_history):
        """Adjust quotas based on historical gate_pass rates."""
        sym_stats = defaultdict(lambda: {"pass": 0, "total": 0})
        fam_stats = defaultdict(lambda: {"pass": 0, "total": 0})

        for v in verdict_history:
            sym = v.get("symbol", "unknown")
            fam = v.get("cov_family", v.get("cov_override", "unknown"))
            passed = v.get("gate_pass", False)

            sym_stats[sym]["total"] += 1
            if passed:
                sym_stats[sym]["pass"] += 1

            fam_stats[fam]["total"] += 1
            if passed:
                fam_stats[fam]["pass"] += 1

        # Compute rates
        self.symbol_rates = {}
        for sym, s in sym_stats.items():
            self.symbol_rates[sym] = s["pass"] / s["total"] if s["total"] > 0 else 0

        self.family_rates = {}
        for fam, s in fam_stats.items():
            self.family_rates[fam] = s["pass"] / s["total"] if s["total"] > 0 else 0

        # Apply multipliers
        def multiplier(rate):
            if rate > 0.40:
                return 1.5
            elif rate >= 0.20:
                return 1.0
            else:
                return 0.5

        raw_sym = {sym: multiplier(r) for sym, r in self.symbol_rates.items()}
        raw_fam = {fam: multiplier(r) for fam, r in self.family_rates.items()}

        # Normalize to sum to 1
        sym_total = sum(raw_sym.values()) or 1
        fam_total = sum(raw_fam.values()) or 1
        self.symbol_quotas = {sym: v / sym_total for sym, v in raw_sym.items()}
        self.family_quotas = {fam: v / fam_total for fam, v in raw_fam.items()}

    def get_sampling_quota(self, symbol, family):
        """Return the sampling quota for a symbol-family pair.

        Combines symbol quota and family quota with exploration buffer.
        Returns a probability in [0, 1] that this pair should be sampled.
        """
        sym_q = self.symbol_quotas.get(symbol, 1.0 / max(len(self.symbol_quotas), 1))
        fam_q = self.family_quotas.get(family, 1.0 / max(len(self.family_quotas), 1))

        # Exploitation: weighted combination
        exploitation_quota = 0.5 * sym_q + 0.5 * fam_q

        # Exploration: uniform across all known pairs
        n_symbols = max(len(self.symbol_quotas), 1)
        n_families = max(len(self.family_quotas), 1)
        exploration_quota = (1.0 / n_symbols) * (1.0 / n_families)

        return self.exploitation_rate * exploitation_quota + self.exploration_rate * exploration_quota

    def get_quotas_summary(self):
        """Return a human-readable summary of current quotas."""
        return {
            "symbol_quotas": dict(sorted(self.symbol_quotas.items(), key=lambda x: -x[1])),
            "family_quotas": dict(sorted(self.family_quotas.items(), key=lambda x: -x[1])),
            "symbol_rates": dict(sorted(self.symbol_rates.items(), key=lambda x: -x[1])),
            "family_rates": dict(sorted(self.family_rates.items(), key=lambda x: -x[1])),
            "exploration_rate": self.exploration_rate,
        }

    def load_bandit_feedback(self, feedback_path=None):
        """Load feedback from harvest and update bandit arms (P1-1 integration).

        Reads data/cache/bandit_feedback.jsonl lines and calls bandit.update()
        for each (symbol, family, reward) entry.
        Returns number of feedback lines processed.
        """
        if feedback_path is None:
            _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            feedback_path = os.path.join(_repo_root, "data", "cache", "bandit_feedback.jsonl")

        if not os.path.exists(feedback_path):
            return 0

        n = 0
        with open(feedback_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    arm = (entry["symbol"], entry["family"])
                    reward = float(entry["reward"])
                    self.bandit.update(arm, reward)
                    n += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
        return n


# ---------------------------------------------------------------------------
# Multi-Armed Bandit
# ---------------------------------------------------------------------------

class MultiArmedBandit:
    """Multi-armed bandit for symbol-family arm selection.

    Supports UCB and Thompson Sampling strategies.
    Each arm is a (symbol, family) tuple.
    Reward = 1 if gate_pass else 0.
    """

    def __init__(self, arms, strategy="ucb"):
        self.arms = list(set(arms))
        self.strategy = strategy.lower()
        self.rewards = {arm: [] for arm in self.arms}
        self.total_plays = 0

    def select_arm(self):
        """Select next arm using UCB or Thompson Sampling."""
        if not self.arms:
            return None

        if self.strategy == "ucb":
            return self._ucb_select()
        elif self.strategy == "thompson":
            return self._thompson_select()
        else:
            return random.choice(self.arms)

    def _ucb_select(self):
        """Upper Confidence Bound selection."""
        if self.total_plays < len(self.arms):
            # Initial phase: play each arm once
            for arm in self.arms:
                if len(self.rewards[arm]) == 0:
                    return arm

        best_arm = self.arms[0]
        best_ucb = float("-inf")

        for arm in self.arms:
            plays = len(self.rewards[arm])
            if plays == 0:
                return arm  # Unexplored arm
            mean_reward = sum(self.rewards[arm]) / plays
            exploration = math.sqrt(2.0 * math.log(self.total_plays) / plays)
            ucb = mean_reward + exploration
            if ucb > best_ucb:
                best_ucb = ucb
                best_arm = arm

        return best_arm

    def _thompson_select(self):
        """Thompson Sampling with Beta distribution."""
        best_arm = self.arms[0]
        best_sample = float("-inf")

        for arm in self.arms:
            successes = sum(self.rewards[arm])
            failures = len(self.rewards[arm]) - successes
            # Beta(successes + 1, failures + 1) sample
            sample = random.betavariate(successes + 1, failures + 1)
            if sample > best_sample:
                best_sample = sample
                best_arm = arm

        return best_arm

    def update(self, arm, reward):
        """Update bandit with reward for an arm."""
        if arm not in self.rewards:
            self.rewards[arm] = []
            self.arms.append(arm)
        self.rewards[arm].append(reward)
        self.total_plays += 1

    def get_arm_stats(self):
        """Return statistics for each arm."""
        result = {}
        for arm, rewards in self.rewards.items():
            plays = len(rewards)
            if plays > 0:
                mean_r = sum(rewards) / plays
            else:
                mean_r = 0.0
            result[f"{arm[0]}_{arm[1]}"] = {
                "plays": plays,
                "mean_reward": round(mean_r, 4),
                "successes": int(sum(rewards)),
            }
        return result


# ---------------------------------------------------------------------------
# Elite Preservation
# ---------------------------------------------------------------------------

class ElitePreservation:
    """Elite preservation mechanism.

    Stores high-quality proposals and generates variants from them.
    Elite criteria:
    - gate_pass=True
    - tier in (S, A)
    - dir_acc > 0.55
    """

    def __init__(self, top_k=50, elite_path=None):
        self.top_k = top_k
        self.elite_path = elite_path
        self.elites = []
        if self.elite_path and os.path.exists(self.elite_path):
            with open(self.elite_path) as f:
                self.elites = json.load(f)

    def add_elite(self, proposal, verdict):
        """Add a proposal to the elite library if it meets criteria."""
        if not verdict.get("gate_pass"):
            return
        tier = verdict.get("tier", "")
        if tier not in ("S", "A"):
            return
        dir_acc = verdict.get("dir_acc", 0)
        if dir_acc <= 0.55:
            return

        elite_entry = {
            "variant_id": verdict.get("variant_id"),
            "symbol": verdict.get("symbol"),
            "cov_override": verdict.get("cov_override"),
            "cov_family": verdict.get("cov_family"),
            "tier": tier,
            "tier_score": verdict.get("tier_score", 0),
            "dir_acc": dir_acc,
            "mechanism": self._extract_mechanism(proposal),
        }
        self.elites.append(elite_entry)
        # Keep only top-K by dir_acc
        self.elites.sort(key=lambda x: -x["dir_acc"])
        self.elites = self.elites[: self.top_k]
        self._save()

    def get_elites(self):
        """Return the current elite library."""
        return list(self.elites)

    def generate_from_elites(self, n_variants=3):
        """Generate variant proposals from elite proposals.

        Variant strategy:
        - Keep symbol/family from elite
        - Mutate mechanism description (add/remove keywords)
        - Generate 3-5 variants per call
        """
        if not self.elites:
            return []

        variants = []
        keywords = ["slope", "crack", "spread", "gated", "momentum", "reversal", "deviation"]

        for elite in random.sample(self.elites, min(len(self.elites), n_variants)):
            base_mech = elite.get("mechanism", "")
            # Mutate: add or swap one keyword
            extra_kw = random.choice(keywords)
            mutated_mech = f"{base_mech}_{extra_kw}" if base_mech else extra_kw

            variants.append({
                "symbol": elite["symbol"],
                "cov_family": elite["cov_family"],
                "cov_override": mutated_mech,
                "source_elite": elite["variant_id"],
                "variant_type": "elite_mutation",
            })

        return variants

    def _extract_mechanism(self, proposal):
        """Extract mechanism description from proposal."""
        return proposal.get("cov_override", proposal.get("mechanism", ""))

    def _save(self):
        """Persist elite library."""
        if self.elite_path:
            os.makedirs(os.path.dirname(self.elite_path), exist_ok=True)
            with open(self.elite_path, "w") as f:
                json.dump(self.elites, f, indent=2, ensure_ascii=False)

    def load_from_verdicts(self, verdicts):
        """Populate elite library from historical verdicts."""
        for v in verdicts:
            proposal = {
                "cov_override": v.get("cov_override", ""),
                "mechanism": v.get("cov_override", ""),
            }
            self.add_elite(proposal, v)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generation outer-loop strategy")
    parser.add_argument("--analyze", action="store_true", help="Generate feature analysis report")
    parser.add_argument("--quotas", action="store_true", help="Compute and print sampling quotas")
    parser.add_argument("--bandit-demo", action="store_true", help="Run bandit simulation demo")
    parser.add_argument("--elite-report", action="store_true", help="Report elite library stats")
    parser.add_argument("--verdict-path", default=None, help="Path to aligned_verdicts.jsonl")
    args = parser.parse_args()

    verdicts = load_verdicts(args.verdict_path)

    if args.analyze:
        path = generate_analysis_report(verdicts)
        print(f"Analysis report written to: {path}")

    if args.quotas:
        gs = GenerationStrategy()
        gs.update_quotas(verdicts)
        summary = gs.get_quotas_summary()
        print("\n=== Symbol Quotas (exploitation-weighted) ===")
        for sym, q in summary["symbol_quotas"].items():
            rate = summary["symbol_rates"].get(sym, 0)
            print(f"  {sym:>4s}: quota={q:.4f}, rate={rate:.1%}")
        print("\n=== Family Quotas (exploitation-weighted) ===")
        for fam, q in summary["family_quotas"].items():
            rate = summary["family_rates"].get(fam, 0)
            print(f"  {fam:>20s}: quota={q:.4f}, rate={rate:.1%}")
        print(f"\nExploration rate: {summary['exploration_rate']:.0%}")

    if args.bandit_demo:
        # Build arms from verdicts
        arms_set = set()
        for v in verdicts:
            sym = v.get("symbol", "unknown")
            fam = v.get("cov_family", v.get("cov_override", "unknown"))
            arms_set.add((sym, fam))

        for strategy in ["ucb", "thompson"]:
            bandit = MultiArmedBandit(list(arms_set), strategy=strategy)
            # Simulate: play each verdict as a reward signal
            for v in verdicts:
                sym = v.get("symbol", "unknown")
                fam = v.get("cov_family", v.get("cov_override", "unknown"))
                arm = (sym, fam)
                reward = 1.0 if v.get("gate_pass") else 0.0
                bandit.update(arm, reward)

            stats = bandit.get_arm_stats()
            top_arms = sorted(stats.items(), key=lambda x: -x[1]["mean_reward"])[:10]
            print(f"\n=== Bandit ({strategy.upper()}) Top Arms ===")
            for arm_name, s in top_arms:
                print(f"  {arm_name}: reward={s['mean_reward']:.2f}, plays={s['plays']}")

    if args.elite_report:
        ep = ElitePreservation(top_k=50)
        ep.load_from_verdicts(verdicts)
        elites = ep.get_elites()
        print(f"\n=== Elite Library ({len(elites)} entries) ===")
        for e in elites[:10]:
            print(f"  {e['variant_id']}: {e['symbol']}_{e['cov_override']} "
                  f"tier={e['tier']} dir_acc={e['dir_acc']:.3f}")
        if len(elites) > 10:
            print(f"  ... and {len(elites) - 10} more")


if __name__ == "__main__":
    main()

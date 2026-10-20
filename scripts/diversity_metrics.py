"""Diversity metrics for proposal exploration.

Computes symbol/family distribution entropy, combination coverage,
and novelty scores to monitor and encourage diverse exploration.

USAGE:
    python scripts/diversity_metrics.py compute --proposals task_FM/experiments
    python scripts/diversity_metrics.py report --proposals task_FM/experiments -o diversity_report.md
"""

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Proposal loading
# ---------------------------------------------------------------------------

def load_proposals(proposals_dir):
    # type: (str) -> List[dict]
    """Load all proposal JSON files from directory tree.

    Handles two patterns:
    - *_proposal.json (legacy)
    - {uuid}_{symbol}_{family}.json (current)
    """
    proposals = []
    root = Path(proposals_dir)
    if not root.exists():
        return proposals

    # Collect all JSON files in shared_findings directories
    for path in sorted(root.rglob("shared_findings/*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
                # Validate it looks like a proposal
                if "id" in data and ("extra" in data or "design_dimensions" in data):
                    proposals.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return proposals


def extract_symbol(p):
    # type: (dict) -> Optional[str]
    return p.get("extra", {}).get("symbol")


def extract_family(p):
    # type: (dict) -> Optional[str]
    fam = p.get("design_dimensions", {}).get("covariate_family")
    return fam if fam and fam != "?" else None


def extract_mechanism(p):
    # type: (dict) -> str
    mech = p.get("extra", {}).get("mechanism", "")
    if not mech:
        mech = p.get("content", "")
    return mech or ""


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------

def compute_symbol_entropy(proposals):
    # type: (List[dict]) -> float
    """Shannon entropy of symbol distribution (nats)."""
    symbols = [extract_symbol(p) for p in proposals if extract_symbol(p)]
    if not symbols:
        return 0.0
    counts = Counter(symbols)
    total = len(symbols)
    entropy = 0.0
    for c in counts.values():
        p_i = c / total
        if p_i > 0:
            entropy -= p_i * math.log(p_i)
    return round(entropy, 4)


def compute_family_entropy(proposals):
    # type: (List[dict]) -> float
    """Shannon entropy of covariate_family distribution (nats)."""
    families = [extract_family(p) for p in proposals if extract_family(p)]
    if not families:
        return 0.0
    counts = Counter(families)
    total = len(families)
    entropy = 0.0
    for c in counts.values():
        p_i = c / total
        if p_i > 0:
            entropy -= p_i * math.log(p_i)
    return round(entropy, 4)


def compute_combination_coverage(proposals, all_symbols=None, all_families=None):
    # type: (List[dict], Optional[List[str]], Optional[List[str]]) -> Tuple[float, int, int, int]
    """Compute (coverage_ratio, n_explored, n_possible, n_unique_combos).

    If all_symbols/all_families not given, infer from proposals.
    """
    combos = set()
    symbols_seen = set()
    families_seen = set()
    for p in proposals:
        s = extract_symbol(p)
        f = extract_family(p)
        if s and f:
            combos.add((s, f))
            symbols_seen.add(s)
            families_seen.add(f)

    syms = all_symbols or sorted(symbols_seen)
    fams = all_families or sorted(families_seen)
    n_possible = len(syms) * len(fams) if syms and fams else 0
    n_explored = len(combos)
    coverage = (n_explored / n_possible) if n_possible > 0 else 0.0
    return round(coverage, 4), n_explored, n_possible, n_explored


def _tokenize(text):
    # type: (str) -> List[str]
    """Simple tokenizer: words (latin + CJK), lowercased."""
    return re.findall(r"[a-zA-Z一-鿿]+", text.lower())


def _cosine_sim(a, b):
    # type: (Dict[str, float], Dict[str, float]) -> float
    """Cosine similarity between two sparse vectors (dicts)."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tf_vector(tokens):
    # type: (List[str]) -> Dict[str, float]
    """Term-frequency vector (normalized)."""
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {k: v / total for k, v in counts.items()}


def compute_novelty_scores(proposals, historical_proposals=None):
    # type: (List[dict], Optional[List[dict]]) -> Tuple[float, List[float]]
    """Compute average novelty = 1 - max_cosine_sim_to_historical.

    Returns (avg_novelty, per_proposal_novelty_list).
    If no historical proposals, novelty is 1.0 for all.
    """
    if not proposals:
        return 0.0, []

    hist = historical_proposals or []
    hist_vectors = [_tf_vector(_tokenize(extract_mechanism(p))) for p in hist]

    novelties = []
    for p in proposals:
        vec = _tf_vector(_tokenize(extract_mechanism(p)))
        if not hist_vectors or not vec:
            novelties.append(1.0)
        else:
            max_sim = max(_cosine_sim(vec, hv) for hv in hist_vectors)
            novelties.append(round(1.0 - max_sim, 4))

    avg_novelty = round(sum(novelties) / len(novelties), 4) if novelties else 0.0
    return avg_novelty, novelties


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def compute_diversity_metrics(proposals_dir, all_symbols=None, all_families=None):
    # type: (str, Optional[List[str]], Optional[List[str]]) -> dict
    """Compute all diversity metrics for a proposals directory."""
    proposals = load_proposals(proposals_dir)
    if not proposals:
        return {
            "symbol_entropy": 0.0,
            "family_entropy": 0.0,
            "combination_coverage": 0.0,
            "avg_novelty": 0.0,
            "n_proposals": 0,
            "n_unique_symbols": 0,
            "n_unique_families": 0,
            "n_unique_combinations": 0,
            "n_possible_combinations": 0,
        }

    sym_ent = compute_symbol_entropy(proposals)
    fam_ent = compute_family_entropy(proposals)
    cov, n_exp, n_pos, n_combos = compute_combination_coverage(
        proposals, all_symbols, all_families
    )
    avg_nov, _ = compute_novelty_scores(proposals)

    symbols = set(extract_symbol(p) for p in proposals if extract_symbol(p))
    families = set(extract_family(p) for p in proposals if extract_family(p))

    return {
        "symbol_entropy": sym_ent,
        "family_entropy": fam_ent,
        "combination_coverage": cov,
        "avg_novelty": avg_nov,
        "n_proposals": len(proposals),
        "n_unique_symbols": len(symbols),
        "n_unique_families": len(families),
        "n_unique_combinations": n_combos,
        "n_possible_combinations": n_pos,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(metrics, proposals_dir):
    # type: (dict, str) -> str
    """Generate markdown diversity report."""
    lines = [
        "# Diversity Report",
        "",
        "**Proposals directory**: `{}`".format(proposals_dir),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        "| Total proposals | {} |".format(metrics["n_proposals"]),
        "| Unique symbols | {} |".format(metrics["n_unique_symbols"]),
        "| Unique families | {} |".format(metrics["n_unique_families"]),
        "| Unique combinations | {} |".format(metrics["n_unique_combinations"]),
        "| Possible combinations | {} |".format(metrics["n_possible_combinations"]),
        "",
        "## Diversity Metrics",
        "",
        "| Metric | Value | Interpretation |",
        "|--------|-------|----------------|",
        "| Symbol entropy | {:.4f} nats | Higher = more uniform |".format(
            metrics["symbol_entropy"]),
        "| Family entropy | {:.4f} nats | Higher = more uniform |".format(
            metrics["family_entropy"]),
        "| Combination coverage | {:.1%} | Fraction of symbol*family explored |".format(
            metrics["combination_coverage"]),
        "| Avg novelty | {:.4f} | Higher = more novel vs history |".format(
            metrics["avg_novelty"]),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Proposal diversity metrics")
    sub = parser.add_subparsers(dest="command")

    p_compute = sub.add_parser("compute", help="Compute metrics (JSON)")
    p_compute.add_argument("--proposals", required=True, help="Proposals directory")
    p_compute.add_argument("--symbols", nargs="*",
                           help="Known symbol list (coverage denominator)")
    p_compute.add_argument("--families", nargs="*",
                           help="Known family list (coverage denominator)")

    p_report = sub.add_parser("report", help="Generate markdown report")
    p_report.add_argument("--proposals", required=True, help="Proposals directory")
    p_report.add_argument("-o", "--output", help="Output file (default: stdout)")
    p_report.add_argument("--symbols", nargs="*", help="Known symbol list")
    p_report.add_argument("--families", nargs="*", help="Known family list")

    args = parser.parse_args()

    if args.command == "compute":
        m = compute_diversity_metrics(args.proposals, args.symbols, args.families)
        print(json.dumps(m, indent=2))
    elif args.command == "report":
        m = compute_diversity_metrics(args.proposals, args.symbols, args.families)
        report = generate_report(m, args.proposals)
        if args.output:
            Path(args.output).write_text(report)
            print("Report written to {}".format(args.output))
        else:
            print(report)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

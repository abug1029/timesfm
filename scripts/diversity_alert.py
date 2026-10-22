"""KL/JS divergence alerts for proposal family distribution.

Wraps diversity_metrics primitives.  Laplace smoothing prevents log(0).
Alert only fires when sample size >= 30 (minimum meaningful distribution).
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Sequence


_MIN_SAMPLE = 30


def _normalise(dist: Sequence[float], epsilon: float) -> list[float]:
    """Laplace-smooth then L1-normalise so every bin is > 0."""
    smoothed = [p + epsilon for p in dist]
    s = sum(smoothed)
    return [v / s for v in smoothed]


def compute_kl_divergence(
    p: Sequence[float],
    q: Sequence[float],
    epsilon: float = 1e-3,
) -> float:
    """KL(p || q) with Laplace smoothing.  Returns nats."""
    if len(p) != len(q) or not p:
        return 0.0
    pn = _normalise(p, epsilon)
    qn = _normalise(q, epsilon)
    return sum(pi * math.log(pi / qi) for pi, qi in zip(pn, qn))


def compute_js_divergence(
    p: Sequence[float],
    q: Sequence[float],
    epsilon: float = 1e-3,
) -> float:
    """JS(p, q) = 0.5*KL(p||m) + 0.5*KL(q||m), m=(p+q)/2.  Returns nats."""
    if len(p) != len(q) or not p:
        return 0.0
    pn = _normalise(p, epsilon)
    qn = _normalise(q, epsilon)
    m = [(a + b) / 2.0 for a, b in zip(pn, qn)]
    # already normalised -> epsilon=0 safe
    return 0.5 * compute_kl_divergence(pn, m, epsilon=0.0) +                0.5 * compute_kl_divergence(qn, m, epsilon=0.0)


def compute_diversity_alert(
    feedback: list[dict],
    threshold: float = 0.3,
    *,
    key: str = "cov_family",
) -> dict:
    """Alert when observed family distribution drifts from uniform.

    Returns dict with triggered bool.  Skips alert when N < 30.
    feedback: list of dicts each containing a key field (default cov_family).
    """
    if len(feedback) < _MIN_SAMPLE:
        return {
            "triggered": False,
            "reason": "sample_size_too_small",
            "n": len(feedback),
            "min_required": _MIN_SAMPLE,
        }

    counts = Counter(item.get(key, "") for item in feedback if item.get(key))
    if not counts:
        return {"triggered": False, "reason": "no_valid_keys", "n": len(feedback)}

    observed = list(counts.values())
    uniform = [sum(observed) / len(observed)] * len(observed)

    kl = compute_kl_divergence(observed, uniform)
    js = compute_js_divergence(observed, uniform)

    return {
        "triggered": kl > threshold,
        "kl_divergence": round(kl, 4),
        "js_divergence": round(js, 4),
        "threshold": threshold,
        "n_bins": len(observed),
        "n_samples": len(feedback),
    }

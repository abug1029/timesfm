"""Covariate family resolver for evaluation."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


# Controlled vocabulary: 6 families
ALLOWED_FAMILIES = {
    "momentum",
    "volatility",
    "inventory",
    "calendar",
    "term_structure",
    "macro_sentiment",
}

# Heuristic keywords for each family (from spec §9.3)
NAME_HINTS = {
    "momentum": ["rsi", "slope", "ha_body", "reversal", "momentum"],
    "volatility": ["atr", "vol", "volatility", "bb", "std", "range"],
    "inventory": ["oi", "ccl", "inventory", "open_interest", "commitment"],
    "calendar": ["calendar", "cyclical", "seasonal", "monthly"],
    "term_structure": ["basis", "term", "structure", "contango", "backwardation"],
    "macro_sentiment": ["macro", "sentiment", "vix", "dxy", "correlation"],
}


def load_covariate_pool(pool_path: Optional[str] = None) -> dict:
    """Load covariate pool from JSON file.

    Args:
        pool_path: Path to covariate_pool.json. If None, uses default location.

    Returns:
        Dict with 'covariates' key containing list of {name, family} dicts.
    """
    if pool_path is None:
        # Default location: config/covariate_pool.json relative to this file
        module_dir = Path(__file__).parent.parent
        pool_path = str(module_dir / "config" / "covariate_pool.json")

    with open(pool_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both dict and list formats
    if isinstance(data, dict):
        if "covariates" in data:
            return data
        elif "pool" in data:
            return {"covariates": data["pool"]}
        else:
            return {"covariates": []}
    elif isinstance(data, list):
        return {"covariates": data}
    else:
        return {"covariates": []}


def resolve_cov_family(verdict: dict, covariate_pool: Optional[dict] = None) -> str:
    """Resolve covariate family for a verdict.

    Three-level fallback:
    1. Exact match: pool contains covariate with name == cov_override
    2. Heuristic: match name hints in cov_override or variant_id
    3. Fallback: "unknown"

    Args:
        verdict: Dict with 'cov_override' and optionally 'variant_id'
        covariate_pool: Pre-loaded pool dict. If None, loads default.

    Returns:
        Family name from ALLOWED_FAMILIES, or "unknown"
    """
    if covariate_pool is None:
        covariate_pool = load_covariate_pool()

    cov_override = verdict.get("cov_override", "")
    variant_id = verdict.get("variant_id", "")

    # Level 1: Exact match in pool
    covariates = covariate_pool.get("covariates", [])
    for cov in covariates:
        if cov.get("name") == cov_override:
            family = cov.get("family", "unknown")
            if family in ALLOWED_FAMILIES:
                return family
            # Family not in controlled vocabulary, continue to heuristic

    # Level 2: Heuristic keyword matching
    search_text = f"{cov_override} {variant_id}".lower()
    for family, keywords in NAME_HINTS.items():
        for keyword in keywords:
            if keyword in search_text:
                return family

    # Level 3: Fallback
    return "unknown"

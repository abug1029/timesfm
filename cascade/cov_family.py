"""Covariate family resolver for evaluation."""
from __future__ import annotations

import json
import os
import re
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

# Word-boundary lookarounds that treat underscore as a separator
# (Python \b treats _ as a word char, which causes false negatives on names like "new_atr_x")
_WB_BEFORE = r"(?<![a-zA-Z0-9])"
_WB_AFTER = r"(?![a-zA-Z0-9])"


def _wb(keyword: str) -> str:
    """Wrap keyword in boundary assertions (underscore-safe)."""
    return f"{_WB_BEFORE}{re.escape(keyword)}{_WB_AFTER}"


# Heuristic keywords for each family (word boundary matching)
# Spec §9.3 name_hints
NAME_HINTS = {
    "momentum": [_wb(k) for k in ["rsi", "slope", "ha_body", "reversal", "momentum", "roc", "roc_x", "ema_cross"]],
    "volatility": [_wb(k) for k in ["atr", "vol", "volatility", "bb", "std", "range"]],
    "inventory": [_wb(k) for k in ["oi", "ccl", "inventory", "open_interest", "commitment"]],
    "calendar": [_wb(k) for k in ["calendar", "cyclical", "seasonal", "monthly", "holiday"]],
    "term_structure": [_wb(k) for k in ["basis", "term", "structure", "contango", "backwardation", "spread", "spread_x"]],
    "macro_sentiment": [_wb(k) for k in ["macro", "sentiment", "vix", "dxy", "correlation"]],
}

# Pre-compile patterns for performance
_COMPILED_HINTS = {
    family: [re.compile(p) for p in patterns]
    for family, patterns in NAME_HINTS.items()
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
       - Supports 'covariates', 'pool', or list format
    2. Heuristic: match name hints in cov_override or variant_id
    3. Fallback: "unknown"

    Args:
        verdict: Dict with 'cov_override' and optionally 'variant_id'
        covariate_pool: Pre-loaded pool dict. If None, loads default.

    Returns:
        Family name from ALLOWED_FAMILIES, or "unknown".
        Note: Caller must filter "unknown" when computing families_hit count.
    """
    if covariate_pool is None:
        covariate_pool = load_covariate_pool()

    cov_override = verdict.get("cov_override", "")
    variant_id = verdict.get("variant_id", "")

    # Level 1: Exact match in pool
    # Support 'covariates', 'pool', or list format (consistent with load_covariate_pool)
    if isinstance(covariate_pool, dict):
        if "covariates" in covariate_pool:
            covariates = covariate_pool["covariates"]
        elif "pool" in covariate_pool:
            covariates = covariate_pool["pool"]
        else:
            covariates = []
    elif isinstance(covariate_pool, list):
        covariates = covariate_pool
    else:
        covariates = []
    for cov in covariates:
        if cov.get("name") == cov_override:
            family = cov.get("family", "unknown")
            if family in ALLOWED_FAMILIES:
                return family
            # Family not in controlled vocabulary, continue to heuristic

    # Level 2: Heuristic keyword matching (boundary-aware, underscore-safe)
    search_text = f"{cov_override} {variant_id}".lower()
    for family, compiled_patterns in _COMPILED_HINTS.items():
        for pattern in compiled_patterns:
            if pattern.search(search_text):
                return family

    # Level 3: Fallback
    return "unknown"

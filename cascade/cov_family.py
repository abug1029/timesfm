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

# PR-C6 (spec §4.5 W5.1): horizon 可知性受控词表。
HORIZON_KNOWN_VALUES = frozenset({
    "known_ahead", "persistence", "self_referential", "unknowable",
})

# known_ahead 必须带的证据字段。取自 `calendar_cyclical` 的**实际**数据契约
# （不是另立一套）：spec W5.1 要求「交易所临时调整不算 known_ahead，除非
# 当时已公告」，对应到字段就是 publication_rule / publication_lag 必须存在
# —— 它们是「何时可知」的判据，缺了就无法审计该假设。
KNOWN_AHEAD_EVIDENCE_FIELDS = (
    "source", "publication_rule", "publication_lag",
    "reconstructable", "verified_by", "verified_at",
)


def validate_horizon_known(pool: dict) -> list:
    """校验每个协变量的 horizon_known 契约，返回问题清单（空 = 通过）。

    spec §4.5 W5.1 要求 known_ahead 必须附证据。此前该约束只活在
    测试与生成脚本里，生产加载路径不校验 —— 新增一个漏填证据的
    known_ahead 会静默通过，把「未来已知」这个最强假设白送给下游填充逻辑。

    **只报告，不改数据**。要连降级一起做，用 `apply_horizon_known_downgrade`
    —— 把「校验」与「变更」分开，调用方才能在不改数据的前提下先看清单。
    """
    problems = []
    covs = pool.get("covariates")
    if not isinstance(covs, dict):
        return ["covariates 不是 dict，无法校验 horizon_known"]

    for name, v in covs.items():
        if not isinstance(v, dict):
            problems.append("%s: 条目不是 dict" % name)
            continue
        hk = v.get("horizon_known")
        if hk not in HORIZON_KNOWN_VALUES:
            problems.append(
                "%s: horizon_known=%r 不在受控词表 %s"
                % (name, hk, sorted(HORIZON_KNOWN_VALUES)))
            continue
        if hk == "known_ahead":
            ev = v.get("known_ahead_evidence")
            if not isinstance(ev, dict):
                problems.append("%s: known_ahead 缺 known_ahead_evidence" % name)
                continue
            missing = [k for k in KNOWN_AHEAD_EVIDENCE_FIELDS if not ev.get(k)]
            if missing:
                problems.append(
                    "%s: known_ahead_evidence 缺字段 %s" % (name, missing))
    return problems


def apply_horizon_known_downgrade(pool: dict) -> list:
    """就地降级不合规的 `known_ahead`，返回降级记录。

    spec §4.5 W5.1 原文：
    > 缺 `known_ahead_evidence` 的协变量**不得**标 `known_ahead`
    > —— **降级为 `unknowable` 并打 WARN**，**不得静默**。

    仅打 WARN 不够：标签仍以 `known_ahead` 流向下游填充逻辑，
    仍然白得「未来已知」这个最强假设 —— 洞没关，只是变可见了。

    降级同时**删除残留证据**：否则陈旧 `known_ahead_evidence` 会零告警
    存活，日后被误当作「证据齐备」而升级回去。

    Returns:
        [(name, 原因)]，空表示无需降级。
    """
    downgraded = []
    covs = pool.get("covariates")
    if not isinstance(covs, dict):
        return downgraded

    for name, v in covs.items():
        if not isinstance(v, dict) or v.get("horizon_known") != "known_ahead":
            continue
        ev = v.get("known_ahead_evidence")
        reason = None
        if not isinstance(ev, dict):
            reason = "缺 known_ahead_evidence"
        else:
            missing = [k for k in KNOWN_AHEAD_EVIDENCE_FIELDS if not ev.get(k)]
            if missing:
                reason = "known_ahead_evidence 缺字段 %s" % missing
        if reason:
            v["horizon_known"] = "unknowable"
            v.pop("known_ahead_evidence", None)
            downgraded.append((name, reason))
    return downgraded


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

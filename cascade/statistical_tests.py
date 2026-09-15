"""Statistical tests for prediction quality evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, Union, Sequence
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo('Asia/Shanghai')


def safe_normalize_cutoff(ts: Union[str, int, float, None]) -> Optional[int]:
    """Normalize cutoff timestamp to Unix seconds (Asia/Shanghai).

    Handles:
    - pd.Timestamp / datetime: naive->localize to Asia/Shanghai, aware->tz_convert
    - str: ISO format, or numeric string (unix seconds/ms, length>=9)
    - int/float: Unix seconds or milliseconds
    - numpy scalars
    - None -> None
    - Invalid -> None

    Spec 9.4: Use pd.Timestamp, naive->localize to Asia/Shanghai, aware->tz_convert.
    """
    if ts is None:
        return None

    # Handle numpy scalars (0-d arrays)
    if hasattr(ts, "ndim") and ts.ndim == 0:
        ts = ts.item()

    # Handle pd.Timestamp / datetime
    if isinstance(ts, (pd.Timestamp, datetime)):
        ts_pd = pd.Timestamp(ts)
        if ts_pd.tzinfo is None:
            # Naive -> localize to Asia/Shanghai
            ts_pd = ts_pd.tz_localize("Asia/Shanghai")
        else:
            # Aware -> convert to Asia/Shanghai
            ts_pd = ts_pd.tz_convert("Asia/Shanghai")
        return int(ts_pd.timestamp())

    # Handle numeric types
    if isinstance(ts, (int, float)):
        if ts > 1e11:  # milliseconds
            return int(ts / 1000)
        return int(ts)

    # Handle string
    if isinstance(ts, str):
        ts_stripped = ts.strip()

        # Check if numeric string: isdigit and length >= 9
        if ts_stripped.isdigit() and len(ts_stripped) >= 9:
            numeric = int(ts_stripped)
            if numeric > 1e11:  # milliseconds
                return numeric // 1000
            return numeric

        # Try parsing as datetime via pd.Timestamp
        try:
            # Handle trailing Z (UTC indicator)
            ts_parse = ts_stripped
            if ts_parse.endswith("Z"):
                ts_parse = ts_parse[:-1] + "+00:00"

            ts_pd = pd.Timestamp(ts_parse)
            if ts_pd.tzinfo is None:
                ts_pd = ts_pd.tz_localize("Asia/Shanghai")
            else:
                ts_pd = ts_pd.tz_convert("Asia/Shanghai")
            return int(ts_pd.timestamp())
        except (ValueError, TypeError):
            return None

    return None



def pair_dir_ok_series(
    variant_points: Sequence,
    baseline_points: Sequence,
) -> tuple[list[int], list[int]]:
    """Pair dir_ok values by normalized cutoff (Inner Join, sorted by time).
    
    Args:
        variant_points: List of (cutoff, dir_ok) tuples or dicts with 'cutoff'/'dir_ok' keys
        baseline_points: Same format as variant_points
    
    Returns:
        (variant_dir_ok_list, baseline_dir_ok_list) - both aligned by common cutoffs, sorted ascending
    """
    def extract(point):
        if isinstance(point, dict):
            cutoff = point.get('cutoff')
            dir_ok = point.get('dir_ok')
            if cutoff is None or dir_ok is None:
                return None, None
            return cutoff, dir_ok
        else:
            if len(point) < 2:
                return None, None
            return point[0], point[1]
    
    # Build {normalized_ts: dir_ok} for both
    variant_map = {}
    for pt in variant_points:
        cutoff, dir_ok = extract(pt)
        if cutoff is None:
            continue
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            variant_map[ts] = int(dir_ok)
    
    baseline_map = {}
    for pt in baseline_points:
        cutoff, dir_ok = extract(pt)
        if cutoff is None:
            continue
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            baseline_map[ts] = int(dir_ok)
    
    # Inner join on common timestamps
    common_ts = sorted(variant_map.keys() & baseline_map.keys())
    
    variant_series = [variant_map[ts] for ts in common_ts]
    baseline_series = [baseline_map[ts] for ts in common_ts]
    
    return variant_series, baseline_series


from scipy.stats import t as student_t


def diebold_mariano_p(
    variant_dir_ok_list: Sequence[float],
    baseline_dir_ok_list: Sequence[float],
    horizon: int = None,
    step: int = None,
) -> float:
    """Diebold-Mariano test for predictive accuracy (one-sided).
    
    H0: variant is NOT better than baseline
    H1: variant IS better than baseline (higher dir_ok)
    
    Returns p-value in [0, 1].
    - p < alpha → reject H0, variant is significantly better
    - p >= alpha → fail to reject H0
    
    Implementation follows Harvey, Leybourne, Newbold (1997) and
    the project spec §4.2.2.
    """
    # Default values from backtest_config
    if horizon is None or step is None:
        from config import backtest_config
        if horizon is None:
            horizon = backtest_config.HORIZON
        if step is None:
            step = backtest_config.STEP
    
    v = np.asarray(variant_dir_ok_list, dtype=float).ravel()
    b = np.asarray(baseline_dir_ok_list, dtype=float).ravel()
    
    # Length check
    if len(v) != len(b) or len(v) < 100:
        return 1.0
    
    T = len(v)
    
    # Spec differential: d = v_ok - b_ok (larger is better)
    d = v - b
    d_bar = np.mean(d)
    
    # Variant worse or no difference → conservative return 1.0
    if d_bar <= 0:
        return 1.0
    
    # Lag order: q = max(1, horizon//step - 1)
    q = max(1, horizon // max(1, step) - 1)
    
    # Newey-West HAC variance estimator (using /T, positive semi-definite)
    gamma = np.zeros(q + 1)
    for j in range(q + 1):
        # γ_j = sum_{t=j+1}^{T} (d_t - d_bar)(d_{t-j} - d_bar) / T
        gamma[j] = np.sum((d[j:] - d_bar) * (d[:-j] - d_bar)) / T if j > 0 else np.sum((d - d_bar) ** 2) / T
    
    # Bartlett kernel weights
    V = gamma[0]
    for j in range(1, q + 1):
        weight = 1.0 - j / (q + 1)
        V += 2.0 * weight * gamma[j]
    
    # Variance degeneration → conservative return 1.0 (spec requirement)
    if V <= 1e-12:
        return 1.0
    
    # DM statistic
    dm_stat = d_bar / np.sqrt(V)
    
    # HLN adjustment factor (Harvey, Leybourne, Newbold 1997)
    h = horizon // max(1, step)
    k_hln = np.sqrt((T + 1 - 2*h + h*(h-1)/T) / T)
    dm_adj = dm_stat * k_hln
    
    # One-sided p-value (right-tail, since d_bar > 0 and larger is better)
    p_value = student_t.sf(dm_adj, df=T - 1)
    
    # Clamp to [0, 1]
    return float(np.clip(p_value, 0.0, 1.0))

def bh_fdr_promote(
    verdicts: Sequence[dict],
    fdr_q: float = 0.10,
    min_batch_size: int = 4,
    bonferroni_alpha: float = 0.025,
) -> dict[str, dict]:
    """Per-symbol BH-FDR correction for variant promotion.

    Args:
        verdicts: List of dicts with keys: variant_id, symbol, p_value, gate_pass
        fdr_q: FDR q-value (default 0.10)
        min_batch_size: Minimum batch size for BH; below uses Bonferroni (default 4)
        bonferroni_alpha: Bonferroni alpha threshold (default 0.025)

    Returns:
        Dict mapping variant_id -> {"fdr_pass": bool}
        - gate_pass=False -> fdr_pass=False (never passes)
        - K < min_batch_size -> Bonferroni correction
        - K >= min_batch_size -> BH-FDR correction
        - Duplicate variant_id: last write wins
    """
    if not verdicts:
        return {}

    # Group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for v in verdicts:
        symbol = v.get("symbol", "unknown")
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(v)

    all_updates: dict[str, dict] = {}

    for symbol, group in by_symbol.items():
        # Deduplicate by variant_id (last write wins)
        seen: dict[str, dict] = {}
        for v in group:
            vid = v.get("variant_id")
            if vid is not None:
                seen[vid] = v
        deduped = list(seen.values())

        K = len(deduped)
        if K == 0:
            continue

        # Sort by (safe_p, variant_id) for deterministic ordering
        def safe_p(v):
            """Return p_value, but 1.0 if gate_pass=False (spec 4.2.3)."""
            if not v.get("gate_pass", False):
                return 1.0  # gate_fail variants sort to end
            p = v.get("p_value")
            return 1.0 if p is None else float(p)

        sorted_group = sorted(deduped, key=lambda v: (safe_p(v), v.get("variant_id", "")))

        # Determine threshold
        if K < min_batch_size:
            # Bonferroni correction
            threshold = bonferroni_alpha
            for v in sorted_group:
                vid = v.get("variant_id")
                gate_pass = v.get("gate_pass", False)
                p = safe_p(v)
                fdr_pass = gate_pass and (p <= threshold)
                all_updates[vid] = {"fdr_pass": fdr_pass}
        else:
            # BH-FDR correction
            # Find largest k such that p_(k) <= k/K * q
            thresholds = [(i + 1) / K * fdr_q for i in range(K)]
            max_pass_idx = -1
            for i, v in enumerate(sorted_group):
                p = safe_p(v)
                if p <= thresholds[i]:
                    max_pass_idx = i

            for i, v in enumerate(sorted_group):
                vid = v.get("variant_id")
                gate_pass = v.get("gate_pass", False)
                fdr_pass = gate_pass and (i <= max_pass_idx)
                all_updates[vid] = {"fdr_pass": fdr_pass}

    return all_updates

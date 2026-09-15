"""Statistical tests for prediction quality evaluation."""
from __future__ import annotations

import numpy as np
from datetime import datetime
from typing import Optional, Union, Sequence
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo('Asia/Shanghai')


def safe_normalize_cutoff(ts: Union[str, int, float, None]) -> Optional[int]:
    """Normalize cutoff timestamp to Unix seconds (Asia/Shanghai).
    
    Handles:
    - str: "2024-06-15 09:00:00", "2024-06-15T09:00:00", Unix timestamp string
    - int/float: Unix seconds or milliseconds
    - numpy scalars
    - tz-aware strings (converts to Asia/Shanghai)
    - None -> None
    - Invalid -> None
    """
    if ts is None:
        return None
    
    # Handle numpy scalars (0-d arrays)
    if hasattr(ts, 'ndim') and ts.ndim == 0:
        ts = ts.item()
    
    # Handle numeric types
    if isinstance(ts, (int, float)):
        # Detect milliseconds vs seconds
        if ts > 1e12:  # milliseconds
            return int(ts / 1000)
        return int(ts)
    
    # Handle string
    if isinstance(ts, str):
        # Try numeric string first
        try:
            numeric = float(ts)
            if numeric > 1e12:
                return int(numeric / 1000)
            return int(numeric)
        except ValueError:
            pass
        
        # Parse datetime string
        try:
            # Handle trailing Z (UTC indicator)
            if ts.endswith('Z'):
                ts_clean = ts[:-1] + '+00:00'
            else:
                ts_clean = ts
            
            dt = datetime.fromisoformat(ts_clean)
            
            if dt.tzinfo is not None:
                # tz-aware: convert to Asia/Shanghai
                dt_shanghai = dt.astimezone(SHANGHAI_TZ)
                return int(dt_shanghai.timestamp())
            else:
                # Naive datetime - assume Asia/Shanghai
                dt = dt.replace(tzinfo=SHANGHAI_TZ)
                return int(dt.timestamp())
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
    variant_losses: Sequence[float],
    baseline_losses: Sequence[float],
    horizon: int = 24,
    step: int = 24,
) -> float:
    """Diebold-Mariano test for predictive accuracy (one-sided).
    
    H0: variant is NOT better than baseline
    H1: variant IS better than baseline
    
    For dir_ok 0/1 values: higher = better (more correct predictions)
    Internally converts to losses: loss = 1 - value
    
    Returns p-value in [0, 1]. 
    - p < alpha → reject H0, variant is significantly better
    - p >= alpha → fail to reject H0
    
    Args:
        variant_losses: Performance series for variant (e.g., dir_ok 0/1, higher=better)
        baseline_losses: Performance series for baseline
        horizon: Forecast horizon (default 24, matches backtest_config.HORIZON)
        step: Walk-forward step (default 24, matches backtest_config.STEP)
    
    Returns:
        float: One-sided p-value
    """
    v_raw = np.asarray(variant_losses, dtype=float).ravel()
    b_raw = np.asarray(baseline_losses, dtype=float).ravel()
    
    # Length check
    if len(v_raw) != len(b_raw) or len(v_raw) < 100:
        return 1.0
    
    T = len(v_raw)
    
    # Convert to losses: higher input values -> lower losses
    # For dir_ok: loss = 1 - dir_ok (1=correct->loss=0, 0=incorrect->loss=1)
    v = 1.0 - v_raw
    b = 1.0 - b_raw
    
    # Loss differential (variant - baseline)
    # If variant is better (higher accuracy, lower loss), d should be negative
    d = v - b
    d_bar = np.mean(d)
    
    # If variant is worse (d_bar > 0), return 1.0 immediately
    if d_bar > 0:
        return 1.0
    
    # If no difference, return 1.0
    if abs(d_bar) < 1e-12:
        return 1.0
    
    # Newey-West HAC variance estimator
    h = max(1, horizon // max(1, step))
    
    # Autocovariances
    gamma = np.zeros(h)
    for j in range(h):
        gamma[j] = np.mean((d[j:] - d_bar) * (d[:-j] - d_bar)) if j > 0 else np.mean((d - d_bar) ** 2)
    
    # Newey-West weights (Bartlett kernel)
    V = gamma[0]
    for j in range(1, h):
        weight = 1.0 - j / h
        V += 2.0 * weight * gamma[j]
    V = V / T
    
    # Special case: if variance is very small but mean difference is clearly negative,
    # return 0.0 (perfect significance)
    if V <= 1e-12:
        if d_bar < -1e-12:
            return 0.0
        return 1.0
    
    # HLN statistic
    dm_adj = d_bar / np.sqrt(V)
    
    # One-sided p-value
    p_value = student_t.sf(-dm_adj, df=T - 1)
    
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

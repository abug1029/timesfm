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

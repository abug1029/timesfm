"""Statistical tests for prediction quality evaluation."""
from __future__ import annotations

import numpy as np
from datetime import datetime
from typing import Optional, Union, Sequence


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
    
    # Handle numpy scalars
    if hasattr(ts, 'item'):
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
            # Remove trailing Z
            ts_clean = ts.replace('Z', '+00:00')
            
            # Try parsing with timezone
            if '+' in ts_clean or ts_clean.count('-') > 2:
                dt = datetime.fromisoformat(ts_clean)
                # Convert to Asia/Shanghai
                from zoneinfo import ZoneInfo
                shanghai_tz = ZoneInfo('Asia/Shanghai')
                dt_shanghai = dt.astimezone(shanghai_tz)
                return int(dt_shanghai.timestamp())
            else:
                # Naive datetime - assume Asia/Shanghai
                dt = datetime.fromisoformat(ts_clean)
                from zoneinfo import ZoneInfo
                shanghai_tz = ZoneInfo('Asia/Shanghai')
                dt = dt.replace(tzinfo=shanghai_tz)
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
            return point.get('cutoff'), point.get('dir_ok')
        else:
            return point[0], point[1]
    
    # Build {normalized_ts: dir_ok} for both
    variant_map = {}
    for pt in variant_points:
        cutoff, dir_ok = extract(pt)
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            variant_map[ts] = int(dir_ok)
    
    baseline_map = {}
    for pt in baseline_points:
        cutoff, dir_ok = extract(pt)
        ts = safe_normalize_cutoff(cutoff)
        if ts is not None:
            baseline_map[ts] = int(dir_ok)
    
    # Inner join on common timestamps
    common_ts = sorted(set(variant_map.keys()) & set(baseline_map.keys()))
    
    variant_series = [variant_map[ts] for ts in common_ts]
    baseline_series = [baseline_map[ts] for ts in common_ts]
    
    return variant_series, baseline_series

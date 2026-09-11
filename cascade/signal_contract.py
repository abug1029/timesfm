"""Live / backtest signal contract — single source for position from forecast.

## Tradable direction (CF-01 A — product law)

**唯一可交易方向** = sign(weighted_1H_pred − base) via ``signal_weight`` /
short_horizon. This is what backtests score and what reports must label as
「交易方向」.

**日线 regime 标签** = daily_slope vs trend_threshold_pct — secondary only,
never overrides trade position. Shown as 「日线状态」 not as the trade call.

Production cascade_predict / monthly / A2 / vol scheme legs MUST call
``position_from_forecast``. Endpoint-only sign(pred[T+24]-base) is legacy.

Copilot currently does NOT call ``position_from_forecast``; the card
direction is daily ``_compute_direction_v2`` (known fork vs CF-01 A).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from config.prediction_scheme import VarietyScheme, signal_weight, trend_direction


def _trade_label(pos: float) -> str:
    if pos > 0:
        return "看多 ↑"
    if pos < 0:
        return "看空 ↓"
    return "中性 →"


def position_from_forecast(
    point_forecast: np.ndarray,
    base_price: float,
    scheme: Optional[VarietyScheme] = None,
    daily_slope: Optional[float] = None,
) -> Dict[str, Any]:
    """Map forecast path → **tradable** position (weighted 1H).

    Args:
        point_forecast: shape (horizon,) price levels
        base_price: T0 close
        scheme: solidified scheme (None → endpoint fallback)
        daily_slope: Stage-1 horizon_slope (fraction/day); only fills
            ``regime_direction`` (副标签), never overrides ``position_sign``

    Returns:
        weighted_pred, delta_pred, position_sign,
        direction (= trade label, 可交易方向),
        regime_direction (日线状态, may be None),
        short_horizon_only, endpoint_delta, used_scheme_weights
    """
    fc = np.asarray(point_forecast, dtype=float).ravel()
    if fc.size == 0:
        raise ValueError("point_forecast empty")
    base = float(base_price)
    endpoint_delta = float(fc[-1] - base)

    if scheme is None:
        delta = endpoint_delta
        weighted = float(fc[-1])
        pos = float(np.sign(delta)) if delta != 0 else 0.0
        trade = _trade_label(pos)
        regime = None
        if daily_slope is not None:
            # no scheme thr — coarse sign only for regime side panel
            ds = float(daily_slope) * 100.0
            regime = "看多 ↑" if ds > 0.1 else ("看空 ↓" if ds < -0.1 else "中性 →")
        return {
            "weighted_pred": weighted,
            "delta_pred": delta,
            "position_sign": pos,
            "direction": trade,  # 可交易方向
            "regime_direction": regime,  # 日线状态
            "short_horizon_only": False,
            "endpoint_delta": endpoint_delta,
            "used_scheme_weights": False,
        }

    w = signal_weight(len(fc), scheme)
    if float(np.sum(w)) <= 0:
        w = np.ones(len(fc), dtype=float)
    weighted = float(np.average(fc, weights=w))
    delta = weighted - base
    pos = float(np.sign(delta)) if delta != 0 else 0.0
    trade = _trade_label(pos)

    regime = None
    if daily_slope is not None:
        # thr only applies to regime label (CF-09 C), not trade position
        regime = trend_direction(float(daily_slope) * 100.0, scheme)

    return {
        "weighted_pred": weighted,
        "delta_pred": float(delta),
        "position_sign": pos,
        "direction": trade,
        "regime_direction": regime,
        "short_horizon_only": bool(scheme.short_horizon_only),
        "endpoint_delta": endpoint_delta,
        "used_scheme_weights": True,
    }

"""
Vol gating 离线重放 — 唯一「按 thr 重算 Neutral 指标」内核。

前提：points_off 已含 vol_prob（来自某次 fullchain/shared-forecast）。
thr 只改 veto 决策，不改 TimesFM 预测 → 无需重跑模型。

scan_vol_thr_smoke / resmoke_vol_thr_offline 必须调用本模块，禁止再拷贝。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from config.backtest_config import SLIPPAGE_TICKS, TICK_SIZES
from cascade.evaluation_metrics import metrics_from_backtest_points
from cascade.neutral_ab_report import classify_row

# 健康 veto 带（报告/启发式用）
HEALTHY_VETO_BAND = (0.10, 0.40)


def valid_points(points_off: Sequence[dict]) -> list[dict]:
    return [
        p for p in points_off
        if "error" not in p and p.get("vol_prob") is not None
    ]


def vol_prob_stats(points_off: Sequence[dict]) -> dict[str, Any]:
    probs = [float(p["vol_prob"]) for p in valid_points(points_off)]
    if not probs:
        return {"n": 0, "min": None, "p50": None, "p80": None, "p90": None, "max": None, "mean": None}
    s = sorted(probs)
    n = len(s)

    def q(alpha: float) -> float:
        return s[min(n - 1, max(0, int(n * alpha)))]

    return {
        "n": n,
        "min": s[0],
        "p50": q(0.50),
        "p80": q(0.80),
        "p90": q(0.90),
        "max": s[-1],
        "mean": sum(s) / n,
    }


def veto_band(veto_rate: float, healthy: tuple[float, float] = HEALTHY_VETO_BAND) -> str:
    lo, hi = healthy
    if veto_rate <= 0.01:
        return "ZERO"
    if veto_rate >= 0.99:
        return "ALL"
    if lo <= veto_rate <= hi:
        return "HEALTHY"
    if veto_rate < lo:
        return "LOW"
    return "HIGH"


def recompute_neutral_at_thr(
    points_off: Sequence[dict],
    thr: float,
    *,
    tick_size: float = 1.0,
    slippage_ticks: int = SLIPPAGE_TICKS,
) -> dict[str, Any]:
    """
    在给定 thr 下重算 Neutral ON 指标。

    Returns:
      {
        metrics, veto_rate, n, n_veto, band,
        # optional compare vs OFF if points_off usable as OFF trades
      }
    """
    ok = valid_points(points_off)
    if not ok:
        empty = metrics_from_backtest_points(
            [], tick_size=tick_size, slippage_ticks=slippage_ticks,
        )
        return {
            "metrics": empty,
            "veto_rate": 0.0,
            "n": 0,
            "n_veto": 0,
            "band": "ZERO",
            "thr": float(thr),
        }

    pts_on: list[dict] = []
    n_veto = 0
    thr_f = float(thr)
    for p in ok:
        vp = float(p["vol_prob"])
        veto = vp >= thr_f
        if veto:
            n_veto += 1
            pts_on.append({
                "delta_pred": 0.0,
                "delta_real": float(p["delta_real"]),
                "base": float(p.get("base", 1.0)),
            })
        else:
            pts_on.append({
                "delta_pred": float(p["delta_pred"]),
                "delta_real": float(p["delta_real"]),
                "base": float(p.get("base", 1.0)),
            })

    metrics_on = metrics_from_backtest_points(
        pts_on, tick_size=tick_size, slippage_ticks=slippage_ticks,
    )
    metrics_off = metrics_from_backtest_points(
        [
            {
                "delta_pred": float(p["delta_pred"]),
                "delta_real": float(p["delta_real"]),
                "base": float(p.get("base", 1.0)),
            }
            for p in ok
        ],
        tick_size=tick_size,
        slippage_ticks=slippage_ticks,
    )
    vr = n_veto / len(ok)
    return {
        "metrics": metrics_on,
        "metrics_off": metrics_off,
        "veto_rate": vr,
        "n": len(ok),
        "n_veto": n_veto,
        "band": veto_band(vr),
        "thr": thr_f,
        "delta_EV": float(metrics_on.get("EV", 0) - metrics_off.get("EV", 0)),
        "delta_MaxDD": float(metrics_on.get("MaxDD", 0) - metrics_off.get("MaxDD", 0)),
        "delta_NetPnL": float(metrics_on.get("NetPnL", 0) - metrics_off.get("NetPnL", 0)),
        "tag": classify_row(
            metrics_off.get("EV", 0),
            metrics_on.get("EV", 0),
            metrics_off.get("MaxDD", 0),
            metrics_on.get("MaxDD", 0),
        ),
    }


def scan_thr_grid(
    points_off: Sequence[dict],
    thrs: Iterable[float],
    *,
    symbol: str = "",
    tick_size: float | None = None,
) -> dict[str, Any]:
    tick = float(tick_size if tick_size is not None else TICK_SIZES.get(symbol.lower(), 1.0))
    by_thr = {}
    for thr in thrs:
        key = f"{float(thr):.2f}"
        by_thr[key] = recompute_neutral_at_thr(points_off, float(thr), tick_size=tick)
    return {
        "symbol": symbol.lower() if symbol else "",
        "vol_stats": vol_prob_stats(points_off),
        "by_thr": by_thr,
        "tick_size": tick,
    }

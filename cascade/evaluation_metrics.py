"""
回测评价指标 — 全项目唯一「秤」

语义约定（禁止分叉）:
  gross_pnl = direction × price_move
  net_pnl   = gross_pnl - tick_size * slippage_ticks  [- commission]
  PF        = sum(net+) / abs(sum(net-))
  EV        = mean(net_pnl)           # 价格点
  EV_ratio  = EV / mean(|price_move|) # 无量纲
  MaxDD     = standard equity DD from equity0=1, r_t=net/base (MaxDD_legacy = old +1 denom)
  DirAcc    = active only (dirs≠0 & rets≠0); DirAcc_legacy = old full-sample rule

滑点:
  config.backtest_config.SLIPPAGE_TICKS = 2 表示双边合计 2 tick
  单笔成本 = tick_size * SLIPPAGE_TICKS

验收（动态 vs 静态）:
  采纳动态 ⇔ PF_dynamic > PF_static AND EV_dynamic > 0
"""

from __future__ import annotations

import numpy as np
from typing import Any, Dict, Optional, Sequence, Union

ArrayLike = Union[np.ndarray, Sequence[float], Sequence[int]]


def calc_net_metrics(
    pred_directions: ArrayLike,
    actual_returns: ArrayLike,
    tick_size: float = 1.0,
    slippage_ticks: int = 2,
    base_prices: Optional[ArrayLike] = None,
    commission_rate: float = 0.0,
) -> Dict[str, float]:
    """
    计算扣除摩擦成本后的净评价指标。

    Args:
        pred_directions: 预测方向 (+1 看多, -1 看空, 0 中性)
        actual_returns: 实际价格变动 (T+H close - T0 close)，非百分比
        tick_size: 最小变动价位
        slippage_ticks: 双边滑点 tick 数（默认 2，与 backtest_config 一致）
        base_prices: 入场基准价（MaxDD / 可选手续费）
        commission_rate: 手续费率（按 base 比例，默认 0）
    """
    dirs = np.asarray(pred_directions, dtype=float)
    rets = np.asarray(actual_returns, dtype=float)

    if dirs.size == 0 or rets.size == 0:
        return {
            "PF": 0.0,
            "EV": 0.0,
            "EV_ratio": 0.0,
            "MaxDD": 0.0,
            "MaxDD_legacy": 0.0,
            "DirAcc": 0.0,
            "DirAcc_legacy": 0.0,
            "NetPnL": 0.0,
            "WinRate": 0.0,
            "n": 0,
            "n_dir": 0,
            "slippage_cost": round(float(tick_size * slippage_ticks), 4),
            "PF_gross": 0.0,
            "EV_gross": 0.0,
        }

    if dirs.shape != rets.shape:
        raise ValueError(
            f"pred_directions shape {dirs.shape} != actual_returns shape {rets.shape}"
        )

    if base_prices is None:
        bases = np.ones(len(rets), dtype=float)
    else:
        bases = np.asarray(base_prices, dtype=float)
        if bases.shape != rets.shape:
            raise ValueError("base_prices length mismatch")

    slip = float(tick_size) * float(slippage_ticks)

    # gross / net
    gross = dirs * rets
    # 中性方向（Neutral Override / 不发单）：无持仓、**无滑点、无手续费**
    # position_sign==0 时 NetPnL 必须严格为 0，否则会「熔断即扣费」毁掉风控裁决
    active = dirs != 0
    net = gross.copy()
    net[~active] = 0.0
    net[active] = gross[active] - slip
    if commission_rate > 0:
        net[active] = net[active] - commission_rate * bases[active]

    # PF
    pos = net[net > 0]
    neg = net[net < 0]
    gross_profit = float(np.sum(pos)) if pos.size else 0.0
    gross_loss = float(np.abs(np.sum(neg))) if neg.size else 0.0
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = 99.99  # 无亏损
    else:
        pf = 0.0

    # gross PF (零摩擦，对照)
    gpos = gross[gross > 0]
    gneg = gross[gross < 0]
    gp = float(np.sum(gpos)) if gpos.size else 0.0
    gl = float(np.abs(np.sum(gneg))) if gneg.size else 0.0
    if gl > 0:
        pf_gross = gp / gl
    elif gp > 0:
        pf_gross = 99.99
    else:
        pf_gross = 0.0

    ev = float(np.mean(net))
    ev_gross = float(np.mean(gross))
    avg_abs = float(np.mean(np.abs(rets)))
    ev_ratio = (ev / avg_abs) if avg_abs > 0 else 0.0

    # MaxDD (compound equity): start at 1.0, compound r_t=net/base
    #   equity = cumprod(1 + r_t); DD = (equity - peak) / peak
    #   自然破产下限: equity ≥ 0 → MaxDD ∈ [-1.0, 0]
    # Legacy: dd = (cum - peak_cum) / (|peak_cum| + 1) without unit notional — MaxDD_legacy
    rel = net / (bases + 1e-8)
    equity = np.empty(len(rel) + 1, dtype=float)
    equity[0] = 1.0
    equity[1:] = np.cumprod(1.0 + rel)  # 2026-08-21 fix: cumprod 替代 cumsum, 防止 MaxDD<-100%
    peak_eq = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_std = np.where(peak_eq > 1e-12, (equity - peak_eq) / peak_eq, 0.0)
    max_dd = float(np.min(dd_std)) if dd_std.size else 0.0
    max_dd = max(max_dd, -1.0)  # 硬下限: MaxDD ≥ -100%

    cum = np.cumsum(rel)  # legacy 仍需
    peak_legacy = np.maximum.accumulate(cum)
    dd_legacy = (cum - peak_legacy) / (np.abs(peak_legacy) + 1.0)
    max_dd_legacy = float(dd_legacy.min()) if dd_legacy.size else 0.0

    # DirAcc: only active non-zero moves — no free wins on rets==0; flats excluded
    active_mask = (dirs != 0) & (rets != 0)
    if np.any(active_mask):
        dir_acc = float(np.mean(np.sign(dirs[active_mask]) == np.sign(rets[active_mask])))
    else:
        dir_acc = 0.0
    # legacy (pre-fix): rets==0 counted correct; dirs==0 counted wrong on moves
    same_legacy = (np.sign(dirs) == np.sign(rets)) | (rets == 0)
    dir_acc_legacy = float(np.mean(same_legacy)) if same_legacy.size else 0.0

    # WinRate: only active trades (dirs != 0)
    if np.any(dirs != 0):
        win_rate = float(np.mean(net[dirs != 0] > 0))
    else:
        win_rate = 0.0

    return {
        "PF": round(float(pf), 3) if pf != 99.99 else 99.99,
        "EV": round(ev, 4),
        "EV_ratio": round(ev_ratio, 4),
        "MaxDD": round(max_dd, 4),
        "MaxDD_legacy": round(max_dd_legacy, 4),
        "DirAcc": round(dir_acc, 4),
        "DirAcc_legacy": round(dir_acc_legacy, 4),
        "NetPnL": round(float(np.sum(net)), 4),
        "WinRate": round(win_rate, 4),
        "n": int(len(net)),
        "n_dir": int(np.sum(active_mask)),
        "slippage_cost": round(slip, 4),
        "PF_gross": round(float(pf_gross), 3) if pf_gross != 99.99 else 99.99,
        "EV_gross": round(ev_gross, 4),
        "avg_win": round(float(np.mean(pos)), 4) if pos.size else 0.0,
        "avg_loss": round(float(np.mean(neg)), 4) if neg.size else 0.0,
    }


def metrics_from_backtest_points(
    points: Sequence[Dict[str, Any]],
    tick_size: float,
    slippage_ticks: int = 2,
) -> Dict[str, float]:
    """
    从 monthly_backtest 风格的 point 列表计算净指标。

    期望每点含: delta_pred, delta_real, base（可选）
    """
    ok = [p for p in points if "error" not in p]
    if not ok:
        return calc_net_metrics([], [], tick_size=tick_size, slippage_ticks=slippage_ticks)

    dirs = np.array([np.sign(p["delta_pred"]) for p in ok], dtype=float)
    rets = np.array([p["delta_real"] for p in ok], dtype=float)
    bases = np.array([p.get("base", 1.0) for p in ok], dtype=float)
    return calc_net_metrics(
        dirs, rets,
        tick_size=tick_size,
        slippage_ticks=slippage_ticks,
        base_prices=bases,
    )


def compare_strategies(
    dynamic_metrics: Dict[str, float],
    static_metrics: Dict[str, float],
) -> Dict[str, Any]:
    """
    严格门禁: PF_dyn > PF_static AND EV_dyn > 0
    持平或略差 → 无效，回退静态。
    """
    delta_pf = dynamic_metrics["PF"] - static_metrics["PF"]
    delta_ev = dynamic_metrics["EV"] - static_metrics["EV"]
    delta_maxdd = dynamic_metrics["MaxDD"] - static_metrics["MaxDD"]

    if delta_pf > 0 and dynamic_metrics["EV"] > 0:
        return {
            "dynamic_better": True,
            "reason": f"PF +{delta_pf:.2f}, EV>0",
            "delta_PF": round(delta_pf, 3),
            "delta_EV": round(delta_ev, 4),
            "delta_MaxDD": round(delta_maxdd, 4),
        }
    if delta_pf > 0:
        return {
            "dynamic_better": False,
            "reason": (
                f"PF +{delta_pf:.2f} but EV={dynamic_metrics['EV']:.4f}"
                f"（EV≤0，回退静态）"
            ),
            "delta_PF": round(delta_pf, 3),
            "delta_EV": round(delta_ev, 4),
            "delta_MaxDD": round(delta_maxdd, 4),
        }
    return {
        "dynamic_better": False,
        "reason": f"PF {delta_pf:+.2f}（动态未优于静态，回退静态）",
        "delta_PF": round(delta_pf, 3),
        "delta_EV": round(delta_ev, 4),
        "delta_MaxDD": round(delta_maxdd, 4),
    }


def print_metrics_comparison(
    symbol: str,
    dynamic_metrics: Dict[str, float],
    static_metrics: Dict[str, float],
    comparison: Dict[str, Any],
) -> None:
    """格式化打印对比结果"""
    print(f"\n{'='*60}")
    print(f"  {symbol.upper()} 回测对比: 动态路由 vs 静态配置")
    print(f"{'='*60}")
    print(f"  {'指标':<15} {'动态':>10} {'静态':>10} {'差值':>10}")
    print(f"  {'-'*45}")
    print(
        f"  {'PF':<15} {dynamic_metrics['PF']:>10.2f} {static_metrics['PF']:>10.2f} "
        f"{comparison['delta_PF']:>+10.2f}"
    )
    print(
        f"  {'EV':<15} {dynamic_metrics['EV']:>10.4f} {static_metrics['EV']:>10.4f} "
        f"{comparison['delta_EV']:>+10.4f}"
    )
    print(
        f"  {'MaxDD':<15} {dynamic_metrics['MaxDD']:>9.2%} {static_metrics['MaxDD']:>9.2%} "
        f"{comparison['delta_MaxDD']:>+9.2%}"
    )
    print(
        f"  {'DirAcc':<15} {dynamic_metrics['DirAcc']:>9.1%} {static_metrics['DirAcc']:>9.1%} "
        f"  (仅参考)"
    )
    print(
        f"  {'WinRate':<15} {dynamic_metrics['WinRate']:>9.1%} "
        f"{static_metrics['WinRate']:>9.1%}"
    )
    print()
    verdict = (
        "[ACCEPT] candidate"
        if comparison["dynamic_better"]
        else "[REJECT] keep baseline"
    )
    print(f"  Verdict: {verdict}")
    print(f"  Reason: {comparison['reason']}")


def calc_vol_scaled_mae(
    pred: ArrayLike,
    actual: ArrayLike,
    atr: ArrayLike,
) -> float:
    """
    波动率缩放 MAE (诊断指标, 不参与决策门禁)。

    Scaled_Error = |Pred - Actual| / ATR
    返回平均缩放误差。<1.0 表示误差在正常日内波动范围内。

    Args:
        pred: 预测值 (价格点)
        actual: 实际值 (价格点)
        atr: 每点 ATR_14 (价格点, 同尺度)
    """
    p = np.asarray(pred, dtype=float)
    a = np.asarray(actual, dtype=float)
    atr_arr = np.asarray(atr, dtype=float)
    if p.size == 0:
        return 0.0
    err = np.abs(p - a)
    # ATR=0 处用 inf (不除零); 不计入有限均值
    with np.errstate(divide="ignore", invalid="ignore"):
        scaled = np.where(atr_arr > 1e-8, err / np.maximum(atr_arr, 1e-8), np.inf)
    finite = scaled[np.isfinite(scaled)]
    return float(np.mean(finite)) if finite.size else float(np.inf)


def calc_margin_maxdd_robust(
    net_pnl_pts: np.ndarray,
    base_prices: np.ndarray,
    contract_multiplier: float,
    horizon: int = 24,
    step: int = 2,
    margin_rate: float = 0.12,
    capital_allocation_ratio: float = 0.30,
    initial_capital: float = 1_000_000.0,
) -> float:
    """
    Margin-based MaxDD with non-overlapping stride sub-sampling.
    stride = horizon // step = 12 independent sub-sequences, average MaxDD.
    """
    stride = max(1, horizon // step)
    sub_dd_list = []

    for offset in range(stride):
        sub_pnl = net_pnl_pts[offset::stride]
        sub_prices = base_prices[offset::stride]

        if len(sub_pnl) < 2:
            continue

        equity = initial_capital
        peak = initial_capital
        max_dd = 0.0

        for t in range(len(sub_pnl)):
            margin_per_lot = sub_prices[t] * contract_multiplier * margin_rate
            lots = max(1, int((equity * capital_allocation_ratio) / margin_per_lot))
            equity += sub_pnl[t] * contract_multiplier * lots

            if equity <= 0:
                max_dd = -1.0
                break
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak)

        sub_dd_list.append(max_dd)

    return float(np.mean(sub_dd_list)) if sub_dd_list else 0.0

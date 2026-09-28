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


def safe_path_corr(
    pred_path: Optional[np.ndarray] | Optional[Sequence[float]],
    real_path: Optional[np.ndarray] | Optional[Sequence[float]],
    eps: float = 1e-8,
) -> Optional[float]:
    if pred_path is None or real_path is None:
        return None
    p = np.asarray(pred_path, dtype=float).ravel()
    r = np.asarray(real_path, dtype=float).ravel()
    if len(p) < 2 or len(r) < 2 or len(p) != len(r):
        return None
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(r))):
        return 0.0
    if np.std(p) < eps or np.std(r) < eps:
        return 0.0
    corr = np.corrcoef(p, r)[0, 1]
    return float(corr) if np.isfinite(corr) else 0.0


def fallback_n_eff(n: int, horizon: int = None, step: int = None) -> int:
    """Bartlett effective sample size estimate.
    
    Defaults: Read from config.backtest_config if not provided.
    WSL production: HORIZON=24, STEP=2 (overlapping windows).
    """
    # 默认值从 backtest_config 读
    if horizon is None or step is None:
        from config import backtest_config
        if horizon is None:
            horizon = backtest_config.HORIZON
        if step is None:
            step = backtest_config.STEP
    
    n = int(n)
    if n <= 0:
        return 0
    h = max(1, int(horizon) // max(1, int(step)))
    factor = 1.0 + 2.0 * sum((1.0 - j / h) ** 2 for j in range(1, h))
    return max(1, int(n / factor))


def calc_prediction_quality(
    pred_endpoints,
    real_endpoints,
    base_prices,
    pred_paths=None,
    real_paths=None,
    roll_flags=None,
) -> dict:
    p_end = np.asarray(pred_endpoints, dtype=float).ravel()
    r_end = np.asarray(real_endpoints, dtype=float).ravel()
    base_raw = np.asarray(base_prices, dtype=float).ravel()
    if not (len(p_end) == len(r_end) == len(base_raw)):
        raise ValueError("pred/real/base length mismatch")
    base = np.maximum(base_raw, 1.0)
    n = len(p_end)
    delta_pred = p_end - base_raw
    delta_real = r_end - base_raw
    eps = 1e-8

    # PR-B4 (spec W6.5): 主口径 = 剔零变动（零变动从分母剔除）
    zero_move = np.abs(delta_real) < eps
    keep_active = ~zero_move

    dir_ok = np.where(
        zero_move,
        False,  # 零变动点 dir_ok=False（但会从分母剔除）
        np.sign(delta_pred) == np.sign(delta_real),
    )

    # 主口径：剔零变动（spec W6.5①）
    n_dir_total = int(n)
    n_dir_active = int(keep_active.sum())
    n_zero_move = int(zero_move.sum())
    dir_acc = float(np.mean(dir_ok[keep_active])) if keep_active.any() else 0.0

    # full 口径：不剔除任何点（独立计算，非别名）
    dir_acc_full = float(np.mean(dir_ok)) if n > 0 else 0.0

    endpoint_mape = float(np.mean(np.abs(p_end - r_end) / base) * 100) if n else 0.0
    endpoint_bias_pct = float(np.mean((delta_pred - delta_real) / base * 100)) if n else 0.0
    abs_delta_real = np.abs(delta_real)
    denom = float(np.sum(abs_delta_real))
    if denom < 1e-8:
        weighted_dir_acc = 0.5
    else:
        weighted_dir_acc = float(np.sum(abs_delta_real * dir_ok) / denom)
    path_corr = mae = mape = decay = None
    if pred_paths is not None and real_paths is not None:
        p_paths = np.asarray(pred_paths, dtype=float)
        r_paths = np.asarray(real_paths, dtype=float)
        # I4 fix: validate path count matches endpoint count
        if p_paths.shape[0] != n:
            raise ValueError(
                f'pred_paths length {p_paths.shape[0]} != endpoint count {n}'
            )
        if r_paths.shape[0] != n:
            raise ValueError(
                f'real_paths length {r_paths.shape[0]} != endpoint count {n}'
            )
        corrs = []
        for i in range(n):
            c = safe_path_corr(p_paths[i], r_paths[i])
            if c is not None:
                corrs.append(c)
        path_corr = float(np.mean(corrs)) if corrs else None
        mae = float(np.mean(np.abs(p_paths - r_paths)))
        mape = float(np.mean(
            np.abs(p_paths - r_paths) / np.maximum(np.abs(r_paths), 1.0)
        ) * 100)
        mid = p_paths.shape[-1] // 2 if p_paths.ndim > 1 else len(p_paths) // 2
        mae_h1 = float(np.mean(np.abs(p_paths[..., :mid] - r_paths[..., :mid])))
        mae_h2 = float(np.mean(np.abs(p_paths[..., mid:] - r_paths[..., mid:])))
        decay = float(mae_h2 / max(mae_h1, 1e-6))
    # D1/D2 分母口径：ex_roll 剔除跨换月点（在主口径基础上）
    if roll_flags is not None and len(roll_flags) == n:
        keep_roll = ~np.asarray(roll_flags, dtype=bool)
        n_roll_excluded = int((~keep_roll).sum())
        # ex_roll 在主口径（剔零变动）基础上再剔跨换月
        keep_both = keep_active & keep_roll
        dir_acc_ex_roll = float(np.mean(dir_ok[keep_both])) if keep_both.any() else 0.0
    else:
        n_roll_excluded = 0
        dir_acc_ex_roll = dir_acc
    n_zero_ratio = (n_zero_move / n_dir_total) if n_dir_total > 0 else 0.0
    n_roll_ratio = (n_roll_excluded / n_dir_total) if n_dir_total > 0 else 0.0

    return {
        "dir_acc": dir_acc,  # 主口径：剔零变动（spec W6.5①）
        "dir_acc_full": dir_acc_full,  # full 口径：不剔除任何点
        "dir_acc_ex_roll": dir_acc_ex_roll,  # 剔零变动 + 剔跨换月
        "n_dir_total": n_dir_total,  # 名义点数（剔除前）
        "n_dir_active": n_dir_active,  # 实际进入 dir_acc 分母的点数
        "n_zero_move": n_zero_move,  # 零变动剔除数
        "n_roll_excluded": n_roll_excluded,  # 跨换月剔除数
        "n_zero_ratio": n_zero_ratio,  # 零变动占比
        "n_roll_ratio": n_roll_ratio,  # 跨换月占比
        "endpoint_mape": endpoint_mape,
        "endpoint_bias_pct": endpoint_bias_pct,
        "path_corr": path_corr,
        "weighted_dir_acc": weighted_dir_acc,
        "mae": mae,
        "mape": mape,
        "decay": decay,
        "n": n,
    }


def measured_n_eff(
    x: np.ndarray,
    h: int = 12,
    q: int = 11,
) -> tuple[Optional[float], str]:
    """实测有效样本量（spec §4.1 W1.2 唯一家）。

    与 DM 检验共用同一估计量（Newey-West Bartlett + HLN），禁止另写一套。

    定义: n_eff = n * sigma0^2 / sigma_LR^2
    其中 sigma0^2 为样本方差，sigma_LR^2 为 Bartlett 核 HAC 长程方差

    Args:
        x: 时间序列
        h: 重叠窗口数参数（默认 12 = HORIZON//STEP）
        q: 最大滞后阶数（默认 11 = h - 1）

    Returns:
        (n_eff, n_eff_status): 有效样本量和状态

    七类边界规则:
        - 常数序列: n_eff = 1, status = "degenerate_constant"
        - 样本不足 (n < 30): n_eff = None, status = "insufficient_n"
        - 长程方差 <= 0: 夹取为 sigma0^2 + WARN, status = "clipped_to_iid"
        - NaN/Inf: 抛出异常, status = "nonfinite"
        - 正常估计: 实测值, status = "ok"
        - 估计失败: n_eff = None, status = "estimation_failed"
    """
    from cascade.statistical_tests import compute_hac_se
    import logging

    x = np.asarray(x, dtype=float).ravel()
    n = len(x)

    # 边界检查：NaN/Inf
    if n == 0 or np.any(np.isnan(x)) or np.any(np.isinf(x)):
        return None, "nonfinite"

    # 边界检查：样本不足
    if n < 30:
        return None, "insufficient_n"

    # 边界检查：常数序列
    if np.std(x) < 1e-10:
        return 1.0, "degenerate_constant"

    # 计算样本方差
    sigma0_sq = np.var(x, ddof=1)

    # 计算 Bartlett 核 HAC 长程方差
    sigma_lr_sq = compute_hac_se(x, q=q)

    # 边界处理：长程方差 <= 0
    if sigma_lr_sq <= 0:
        logging.warning(
            f"Long-run variance <= 0 ({sigma_lr_sq:.6e}), clipping to sample variance"
        )
        sigma_lr_sq = sigma0_sq
        status = "clipped_to_iid"
    else:
        status = "ok"

    # 计算 n_eff
    n_eff = n * sigma0_sq / sigma_lr_sq

    # 数学保证：n_eff <= n
    if n_eff > n:
        n_eff = float(n)

    return float(n_eff), status


def compute_meets_min_info(
    n: int,
    n_eff: Optional[float],
    n_eff_status: str,
    dm_common_count: int,
    min_n: int = 30,
    min_n_eff: int = 50,
    min_pairs: int = 50,
) -> bool:
    """计算是否满足确认检验的最低信息要求（spec §4.1 W1.2）。

    改为一个显式布尔字段表达「是否满足确认检验的最低信息要求」。

    Args:
        n: 样本量
        n_eff: 有效样本量
        n_eff_status: n_eff 状态
        dm_common_count: DM 配对数量
        min_n: 最小样本量（默认 30）
        min_n_eff: 最小有效样本量（默认 50）
        min_pairs: 最小配对数（默认 50）

    Returns:
        bool: 是否满足最低信息要求

    判定条件:
        n >= min_n
        AND n_eff >= min_n_eff
        AND dm_common_count >= min_pairs
        AND n_eff_status in VALID_ESTIMATE

    VALID_ESTIMATE 包括: ok, degenerate_constant, clipped_to_iid, estimation_failed
    不包括: insufficient_n, nonfinite（这些是错误，不是「统计上不可判定」）
    """
    VALID_ESTIMATE = {"ok", "degenerate_constant", "clipped_to_iid", "estimation_failed"}

    return (
        n >= min_n
        and (n_eff is not None and n_eff >= min_n_eff)
        and dm_common_count >= min_pairs
        and n_eff_status in VALID_ESTIMATE
    )

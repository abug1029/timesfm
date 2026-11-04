"""评估网格与基线评估 cutoffs。

从月度回测抽出的评估网格逻辑：
- select_eval_indices: 按收盘时间选出评估下标，右边界 total - horizon - 1
- filter_by_daily_sufficiency: 过滤日线数据不足的评估点
- baseline_eval_cutoffs: 品种基线的评估 cutoff 序列（身份）

不导入 torch。
"""

import pandas as pd

from data.data_store import DataStore


def _bar_dt(dts, idx):
    if hasattr(dts, "iloc"):
        return dts.iloc[idx]
    return dts[idx]


def _close_ts(dt) -> str:
    # 与评估循环同一公式：开盘 dt + 1h，字典序比较，不解析 eval_start_ts。
    return (pd.Timestamp(dt) + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")


def select_eval_indices(dts, *, eval_start_ts=None, max_points=None,
                        context_bars: int, horizon: int, step: int,
                        eval_window_bars: int) -> list:
    """按收盘时间选出评估下标。不碰模型。

    eval_start_ts 为空时与旧公式逐点相同：左边界仍是
    max(context_bars, total - eval_window_bars)。
    有值时左边界改为「收盘时间 >= eval_start_ts 且 idx >= context_bars」的第一根，
    不再用尾部窗口。右边界是 total - horizon - 1（保证最后一个 eval 点有完整 horizon 根 target）。然后才 [:max_points]。
    """
    total = len(dts)
    right = total - horizon - 1
    if eval_start_ts is None:
        left = max(context_bars, total - eval_window_bars)
    else:
        bound = (eval_start_ts if isinstance(eval_start_ts, str)
                 else pd.Timestamp(eval_start_ts).strftime("%Y-%m-%d %H:%M:%S"))
        left = None
        for idx in range(context_bars, right + 1):
            if _close_ts(_bar_dt(dts, idx)) >= bound:
                left = idx
                break
        if left is None:
            return []
    indices = list(range(left, right + 1, step))
    if max_points is not None:
        indices = indices[:max_points]
    return indices


def filter_by_daily_sufficiency(indices, hourly_dt, daily_df, min_daily_required: int) -> list:
    """过滤日线数据不足 min_daily_required 天的评估点。"""
    if daily_df is None or daily_df.empty:
        return list(indices)
    import bisect
    daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
    kept = []
    for idx in indices:
        day = str(_bar_dt(hourly_dt, idx))[:10]
        if bisect.bisect_right(daily_dates, day) >= min_daily_required:
            kept.append(idx)
    return kept


def baseline_eval_cutoffs(symbol: str) -> list:
    """品种的评估 cutoff 序列（基线身份）。

    空序列或读库失败时抛 RuntimeError，不返回 []。
    """
    import config.backtest_config as bc
    with DataStore(symbol) as store:
        hourly = store.get_main_contract_1h(limit=99999)
        daily = store.get_main_continuous(limit=99999)
    if hourly is None or hourly.empty:
        raise RuntimeError(f"{symbol} 小时线为空，不能把空网格当成通过")
    indices = select_eval_indices(
        hourly["dt"],
        context_bars=bc.CONTEXT_BARS,
        horizon=bc.HORIZON,
        step=bc.STEP,
        eval_window_bars=bc.EVAL_WINDOW_BARS,
    )
    need = max(bc.CONTEXT_DAYS - bc.HORIZON_DAYS, 100)
    indices = filter_by_daily_sufficiency(indices, hourly["dt"], daily, need)
    if not indices:
        raise RuntimeError(f"{symbol} 评估网格为空，不能把空文件当成通过")
    return [_close_ts(_bar_dt(hourly["dt"], idx)) for idx in indices]

#!/usr/bin/env python
"""Phase 15 相关性预检: 4 新协变量 vs 现有 19 协变量

目的: 确认新协变量 (NVI/QSTICK/VWAP偏离/StdDev) 与现有协变量的信息冗余度。
判定标准:
  - mean |corr| < 0.5  → 通过
  - 0.5 <= mean |corr| < 0.7  → 警告, 保留但记录
  - mean |corr| >= 0.7  → 放弃 (信息冗余)

用法:
    python scripts/p15_corr_precheck.py [symbol]
    python scripts/p15_corr_precheck.py ss
"""
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from data.data_store import DataStore


# === 新协变量计算 (独立实现, 不依赖 features.py) ===

def calc_nvi(close: np.ndarray, volume: np.ndarray, lookback: int = 20) -> np.ndarray:
    """NVI: 缩量日累积收益 -> 追踪聪明资金"""
    n = len(close)
    nvi = np.full(n, np.nan)
    nvi[0] = 1000.0
    null_streak = 0
    for i in range(1, n):
        if np.isnan(volume[i]) or np.isnan(volume[i - 1]):
            null_streak += 1
            if null_streak > 6:
                nvi[i] = np.nan
            else:
                nvi[i] = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0
            continue
        null_streak = 0
        ret = (close[i] - close[i - 1]) / (close[i - 1] + 1e-8)
        if volume[i] < volume[i - 1]:
            prev = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0
            nvi[i] = prev * (1 + ret)
        else:
            nvi[i] = nvi[i - 1] if not np.isnan(nvi[i - 1]) else 1000.0
    nvi = np.nan_to_num(nvi, nan=0.0)
    s = pd.Series(nvi)
    roll_mean = s.rolling(lookback, min_periods=1).mean()
    roll_std = s.rolling(lookback, min_periods=1).std()
    zscore = ((s - roll_mean) / (roll_std + 1e-8)).values
    return zscore


def calc_qstick(close: np.ndarray, open_: np.ndarray, lookback: int = 14) -> np.ndarray:
    """QSTICK: SMA(Close-Open, N) / rolling_std(QSTICK, 60)"""
    body = close - open_
    qstick = pd.Series(body).rolling(lookback, min_periods=1).mean().values
    std = pd.Series(qstick).rolling(60, min_periods=1).std().values
    return np.where(std > 1e-8, qstick / (std + 1e-8), 0.0)


def calc_vwap_dev(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                  volume: np.ndarray, lookback: int = 24) -> np.ndarray:
    """VWAP偏离: (Close-VWAP)/VWAP"""
    tp = (high + low + close) / 3.0
    tp_vol = pd.Series(tp * volume).rolling(lookback, min_periods=1).sum().values
    vol_sum = pd.Series(volume).rolling(lookback, min_periods=1).sum().values
    vwap = tp_vol / (vol_sum + 1e-8)
    deviation = (close - vwap) / (np.abs(vwap) + 1e-8)
    return np.nan_to_num(deviation, nan=0.0)


def calc_stddev(close: np.ndarray, lookback: int = 20) -> np.ndarray:
    """StdDev: 收盘价标准差 -> 百分比偏离"""
    stddev = pd.Series(close).rolling(lookback, min_periods=1).std().values
    mean60 = pd.Series(stddev).rolling(60, min_periods=1).mean().values
    return np.where(mean60 > 1e-8, stddev / (mean60 + 1e-8) - 1.0, 0.0)


# === 现有协变量计算 (简化版, 用于相关性对比) ===

def calc_existing_covariates(df: pd.DataFrame) -> dict:
    """计算现有 19 类协变量用于相关性对比"""
    from cascade.features import (
        calc_rsi_state, calc_rolling_hurst, calc_hourly_slope,
        calc_pca_momentum, calc_ao_acceleration, calc_bb_squeeze,
        calc_ha_body_direction, calc_reversal_shadow_ratio,
        calc_sar_distance, calc_vor, calc_oi_pct_change,
        _calc_atr,
    )

    close = df["close_price"].values.astype(float)
    result = {}

    # oi
    if "open_interest" in df.columns and df["open_interest"].notna().any():
        oi_pct = calc_oi_pct_change(df["open_interest"])
        result["oi"] = np.nan_to_num(oi_pct.values, nan=0.0)
    else:
        result["oi"] = np.zeros(len(close))

    # rsi_state
    rsi = calc_rsi_state(close, rsi_period=14)
    result["rsi_state"] = np.nan_to_num(rsi.astype(float), nan=0.0)

    # hurst
    hurst = calc_rolling_hurst(close, window=120, step=6)
    result["hurst"] = np.nan_to_num(hurst, nan=0.0)

    # hourly_slope
    h_slope = calc_hourly_slope(close, window=24)
    result["hourly_slope"] = np.nan_to_num(h_slope.values, nan=0.0)

    # pca_momentum
    pca = calc_pca_momentum(close, periods=[5, 9, 14, 21], squash=True)
    result["pca_momentum"] = np.nan_to_num(pca, nan=0.0)

    # ao_accel
    ao = calc_ao_acceleration(df)
    result["ao_accel"] = np.nan_to_num(ao, nan=0.0)

    # bb_squeeze
    bb = calc_bb_squeeze(df)
    result["bb_squeeze"] = np.nan_to_num(bb, nan=0.0)

    # ha_body
    atr = _calc_atr(df, period=14)
    ha = calc_ha_body_direction(df, atr_arr=atr)
    result["ha_body"] = np.nan_to_num(ha, nan=0.0)

    # reversal_shadow
    rs = calc_reversal_shadow_ratio(df, atr_arr=atr, lookback=20)
    result["reversal_shadow"] = np.nan_to_num(rs, nan=0.0)

    # sar_dist
    sd = calc_sar_distance(df, atr_arr=atr)
    result["sar_dist"] = np.nan_to_num(sd, nan=0.0)

    # vor
    if "volume" in df.columns and "open_interest" in df.columns:
        vol = df["volume"].values.astype(float)
        oi = df["open_interest"].values.astype(float)
        vor = calc_vor(vol, oi, zscore_window=min(len(df), 480))
        result["vor"] = np.nan_to_num(vor, nan=0.0)
    else:
        result["vor"] = np.zeros(len(close))

    return result


def precheck(symbol: str = "ss"):
    store = DataStore(symbol)
    df = store.get_main_contract_1h(limit=5000)
    if df is None or len(df) < 500:
        print(f"[ERROR] {symbol}: 1H 数据不足 (n={len(df) if df is not None else 0})")
        return

    c = df["close_price"].values.astype(float)
    o = df["open_price"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    v = df["volume"].values.astype(float)

    new_covs = {
        "nvi": calc_nvi(c, v),
        "qstick": calc_qstick(c, o),
        "vwap_deviation": calc_vwap_dev(c, h, l, v),
        "stddev": calc_stddev(c),
    }

    # 基本统计
    print(f"=== Phase 15 相关性预检: {symbol.upper()} (n={len(df)}) ===\n")
    print(f"--- 新协变量基本统计 ---")
    for name, arr in new_covs.items():
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            print(f"  {name:<18s} ALL NaN")
            continue
        print(f"  {name:<18s} mean={np.mean(valid):+.4f}  std={np.std(valid):.4f}  "
              f"min={np.min(valid):+.4f}  max={np.max(valid):+.4f}")

    # 新协变量互相关
    print(f"\n--- 新协变量互相关矩阵 ---")
    names_new = list(new_covs.keys())
    arrs_new = [new_covs[n] for n in names_new]
    min_len = min(len(a) for a in arrs_new)
    mat_new = np.column_stack([a[:min_len] for a in arrs_new])
    corr_new = np.corrcoef(mat_new, rowvar=False)
    header = f"{'':>18s}" + "  ".join(f"{n:>12s}" for n in names_new)
    print(header)
    for i, n in enumerate(names_new):
        row = f"{n:<18s}" + "  ".join(f"{corr_new[i, j]:>12.4f}" for j in range(len(names_new)))
        print(row)

    # 与现有协变量的相关性
    print(f"\n--- 新协变量 vs 现有协变量 (mean |corr|) ---")
    try:
        existing = calc_existing_covariates(df)
    except Exception as e:
        print(f"  [WARN] 现有协变量计算失败: {e}")
        print(f"  跳过交叉相关性分析, 仅保留新协变量互相关")
        existing = {}

    if existing:
        names_old = sorted(existing.keys())
        print(f"\n{'新协变量':>18s}  {'mean|corr|':>10s}  {'max|corr|':>10s}  {'判定':>8s}  {'最相关现有协变量'}")
        print("-" * 80)

        for new_name, new_arr in new_covs.items():
            corrs = []
            for old_name in names_old:
                old_arr = existing[old_name]
                min_l = min(len(new_arr), len(old_arr))
                valid_mask = ~(np.isnan(new_arr[:min_l]) | np.isnan(old_arr[:min_l]))
                if valid_mask.sum() < 30:
                    continue
                c_val = np.corrcoef(new_arr[:min_l][valid_mask], old_arr[:min_l][valid_mask])[0, 1]
                if not np.isnan(c_val):
                    corrs.append((old_name, c_val))

            if not corrs:
                print(f"{new_name:>18s}  {'N/A':>10s}")
                continue

            abs_corrs = [(n, abs(v)) for n, v in corrs]
            mean_abs = np.mean([ac for _, ac in abs_corrs])
            max_abs = max(ac for _, ac in abs_corrs)
            top_old = sorted(corrs, key=lambda x: abs(x[1]), reverse=True)[:3]
            top_str = ", ".join(f"{n}({v:+.3f})" for n, v in top_old)

            if mean_abs < 0.5:
                verdict = "PASS"
            elif mean_abs < 0.7:
                verdict = "WARN"
            else:
                verdict = "FAIL"

            print(f"{new_name:>18s}  {mean_abs:>10.4f}  {max_abs:>10.4f}  {verdict:>8s}  {top_str}")

    print(f"\n=== 预检完成 ===")


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "ss"
    precheck(sym)

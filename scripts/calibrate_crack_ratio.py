"""
SC→FU/BU crack spread ratio 标定

OLS on returns (避免 I(1) 水平序列 spurious regression)
滚动 2 年窗口 (~500 bars)，取中位数

用法:
    python scripts/calibrate_crack_ratio.py fu
    python scripts/calibrate_crack_ratio.py bu
    python scripts/calibrate_crack_ratio.py fu bu  # 同时标定两个
"""
import sys
import argparse
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from data.data_store import DataStore
from cascade.features import _align_feedstock


def calibrate_ratio(target: str, feedstock: str = "sc",
                    window: int = 500) -> float:
    """
    OLS on returns: target_ret = ratio * feedstock_ret + error
    滚动 window 窗口, 取中位数 ratio

    Args:
        target: 目标品种 (fu/bu)
        feedstock: 原料品种 (默认 sc)
        window: 滚动窗口大小 (bars, 默认 500 ≈ 2 年)

    Returns:
        ratio (中位数)
    """
    # 1. 读数据
    with DataStore(target) as ts:
        df_target = ts.get_main_contract_1h(limit=99999)
    with DataStore(feedstock) as fs:
        df_feedstock = fs.get_main_contract_1h(limit=99999)

    if df_target.empty or df_feedstock.empty:
        raise ValueError(f"{target} or {feedstock} 数据为空")

    print(f"{target.upper()}: {len(df_target)} bars, "
          f"{df_target['dt'].iloc[0]} ~ {df_target['dt'].iloc[-1]}")
    print(f"{feedstock.upper()}: {len(df_feedstock)} bars, "
          f"{df_feedstock['dt'].iloc[0]} ~ {df_feedstock['dt'].iloc[-1]}")

    # 2. 对齐: 复用 _align_feedstock (与 calc_crack_spread 同一逻辑)
    aligned_feedstock = _align_feedstock(df_target, df_feedstock)

    # 3. 取两者都有数据的段 (去掉 feedstock 为 NaN 的前段)
    valid = aligned_feedstock.notna()
    if valid.sum() < window:
        raise ValueError(f"重叠段仅 {valid.sum()} bars < window {window}")

    target_close = df_target.loc[valid, "close_price"].astype(float).values
    feedstock_close = aligned_feedstock[valid].values

    print(f"重叠段: {valid.sum()} bars")

    # 4. Returns (np.diff)
    target_ret = np.diff(target_close)
    feedstock_ret = np.diff(feedstock_close)
    n_ret = len(target_ret)

    # 5. 滚动 OLS (无截距): ratio = sum(x*y) / sum(x*x)
    ratios = []
    for i in range(window, n_ret):
        w_f = feedstock_ret[i - window:i]
        w_t = target_ret[i - window:i]
        denom = np.sum(w_f ** 2)
        if denom < 1e-10:
            continue
        r = np.sum(w_f * w_t) / denom
        ratios.append(r)

    if not ratios:
        raise ValueError("无有效滚动窗口")

    ratios = np.array(ratios)
    median_ratio = float(np.median(ratios))

    # 6. 输出
    print(f"\n{'='*50}")
    print(f"品种: {target.upper()} (feedstock: {feedstock.upper()})")
    print(f"滚动窗口: {window} bars")
    print(f"有效窗口数: {len(ratios)}")
    print(f"Ratio 分布:")
    print(f"  中位数: {median_ratio:.4f}")
    print(f"  均值:   {np.mean(ratios):.4f}")
    print(f"  标准差: {np.std(ratios):.4f}")
    print(f"  P25:    {np.percentile(ratios, 25):.4f}")
    print(f"  P75:    {np.percentile(ratios, 75):.4f}")
    print(f"  Min:    {np.min(ratios):.4f}")
    print(f"  Max:    {np.max(ratios):.4f}")
    print(f"{'='*50}")

    # 合理性检查
    if target == "fu":
        lo, hi = 3.5, 5.5   # OLS: FU_ret = ratio * SC_ret, FU元/吨 per SC元/桶
    elif target == "bu":
        lo, hi = 2.5, 6.0   # BU 价格结构不同于 FU, 区间更宽
    else:
        lo, hi = 1.0, 10.0

    if lo <= median_ratio <= hi:
        print(f"[OK] median {median_ratio:.4f} in [{lo}, {hi}]")
    else:
        print(f"[WARN] median {median_ratio:.4f} outside [{lo}, {hi}], check data")

    return median_ratio


def main():
    parser = argparse.ArgumentParser(description="SC→target crack spread ratio 标定")
    parser.add_argument("targets", nargs="+", help="目标品种 (fu bu)")
    parser.add_argument("--window", type=int, default=500,
                        help="滚动窗口 (bars, 默认 500)")
    args = parser.parse_args()

    results = {}
    for t in args.targets:
        print(f"\n{'#'*60}")
        print(f"# 标定 {t.upper()} ratio")
        print(f"{'#'*60}\n")
        results[t] = calibrate_ratio(t, window=args.window)

    # 汇总
    print(f"\n\n{'='*60}")
    print("汇总 (写入 config/crack_spread_pairs.py):")
    print(f"{'='*60}")
    for t, r in results.items():
        print(f'    "{t}": {{"feedstock": "sc", "ratio": {r:.4f}}},')


if __name__ == "__main__":
    main()

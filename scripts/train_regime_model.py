#!/usr/bin/env python3
"""
训练 1H Regime K-Means 模型 (P1.3.a)

硬约束:
  - 训练样本时间戳 ≤ train_end（默认 2026-03-31），与 P1.4 OOS 物理隔离
  - StandardScaler 仅在训练窗 fit，随 pkl 保存
  - 标签按经济意义映射（非纯 ADX 序）
  - 特征契约 FEATURE_VERSION / EXPECTED_FEATURE_COLUMNS

用法:
    python scripts/train_regime_model.py
    python scripts/train_regime_model.py --varieties ss rb jm i
    python scripts/train_regime_model.py --train-end 2026-03-31
"""

from __future__ import annotations

import sys
import os
import argparse
import shutil
import pickle
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from data.data_store import DataStore
from cascade.regime_features import (
    extract_1h_regime_features,
    FEATURE_VERSION,
    EXPECTED_FEATURE_COLUMNS,
)
from config.prediction_scheme import list_solidified

# 与纲领一致：训练截止 / OOS 起点
DEFAULT_TRAIN_END = "2026-03-31"
DEFAULT_OOS_START = "2026-04-01"
MIN_BARS_PER_SYMBOL = 500
MIN_FEATURE_ROWS = 80
REGIME_LABELS = {
    0: "high_vol_trend",
    1: "low_vol_narrow",
    2: "wide_oscillation",
    3: "transition",
}


def load_1h_raw(symbol: str, limit: int | None = None) -> pd.DataFrame | None:
    """加载 1H OHLCV（默认尽量全量）。"""
    try:
        with DataStore(symbol) as store:
            # limit=None → 全表；否则取最近 N 根
            df = store.get_main_contract_1h(limit=limit if limit is not None else 10**9)
            if df is None or df.empty:
                print(f"  {symbol.upper()}: 无 1H 数据")
                return None
            df = df.copy()
            df["dt"] = pd.to_datetime(df["dt"])
            df = df.sort_values("dt").reset_index(drop=True)
            return df
    except Exception as e:
        print(f"  {symbol.upper()}: 加载失败 ({e})")
        return None


def build_feature_frame(
    symbol: str,
    df_1h: pd.DataFrame,
    train_end: pd.Timestamp,
) -> pd.DataFrame | None:
    """
    提取特征并切断训练窗。

    返回列: feature columns + dt + symbol + close
    仅保留 dt.normalize() <= train_end 的行（特征已 dropna）。
    """
    if len(df_1h) < MIN_BARS_PER_SYMBOL:
        print(f"  {symbol.upper()}: bars={len(df_1h)} < {MIN_BARS_PER_SYMBOL}")
        return None

    features = extract_1h_regime_features(df_1h)
    # 对齐索引
    features = features.copy()
    features["dt"] = df_1h["dt"].values
    features["close"] = df_1h["close_price"].values if "close_price" in df_1h.columns else df_1h["close"].values
    features["symbol"] = symbol

    # 有效特征
    feat_cols = list(EXPECTED_FEATURE_COLUMNS)
    valid = features.dropna(subset=feat_cols).copy()

    # 时间隔离
    valid = valid[valid["dt"] <= train_end]
    if len(valid) < MIN_FEATURE_ROWS:
        print(f"  {symbol.upper()}: 训练窗有效特征 {len(valid)} < {MIN_FEATURE_ROWS}")
        return None

    # 断言：无 OOS 泄漏
    assert valid["dt"].max() <= train_end, (
        f"{symbol}: train max dt {valid['dt'].max()} > train_end {train_end}"
    )

    return valid


def assign_economic_labels(
    features_df: pd.DataFrame,
    raw_labels: np.ndarray,
) -> tuple[dict, pd.DataFrame]:
    """
    将原始 cluster id 映射为经济 regime id。

    Regime 0: highest ADX → high_vol_trend
    Regime 1: lowest vol_cone (among remaining) → low_vol_narrow
    Regime 2: highest vol_cone (among remaining) → wide_oscillation
    Regime 3: remaining → transition
    """
    adx_col = "rolling_adx_40"
    vol_cone_col = "vol_cone_position_40"

    tmp = features_df[EXPECTED_FEATURE_COLUMNS].copy()
    tmp["cluster"] = raw_labels

    stats = tmp.groupby("cluster").agg(
        adx_mean=(adx_col, "mean"),
        vol_cone_mean=(vol_cone_col, "mean"),
        n=(adx_col, "count"),
    )

    # 0: max ADX
    c0 = int(stats["adx_mean"].idxmax())
    remaining = [c for c in stats.index if int(c) != c0]

    # 1: min vol_cone among remaining
    rem_stats = stats.loc[remaining]
    c1 = int(rem_stats["vol_cone_mean"].idxmin())
    remaining = [c for c in remaining if int(c) != c1]

    # 2: max vol_cone among remaining
    rem_stats = stats.loc[remaining]
    c2 = int(rem_stats["vol_cone_mean"].idxmax())
    remaining = [c for c in remaining if int(c) != c2]

    c3 = int(remaining[0])

    cluster_to_regime = {c0: 0, c1: 1, c2: 2, c3: 3}

    print("\n=== 经济意义标签映射 ===")
    for cid, rid in sorted(cluster_to_regime.items(), key=lambda x: x[1]):
        row = stats.loc[cid]
        print(
            f"  cluster {cid} → regime {rid} ({REGIME_LABELS[rid]}): "
            f"ADX={row['adx_mean']:.1f}, vol_cone={row['vol_cone_mean']:.2f}, n={int(row['n'])}"
        )

    return cluster_to_regime, stats


def train_kmeans(
    symbols: list[str],
    n_clusters: int = 4,
    train_end: str = DEFAULT_TRAIN_END,
    oos_start: str = DEFAULT_OOS_START,
    bar_limit: int | None = None,
) -> dict:
    train_end_ts = pd.Timestamp(train_end).normalize() + pd.Timedelta(hours=23, minutes=59)
    oos_start_ts = pd.Timestamp(oos_start)

    if not (train_end_ts < oos_start_ts):
        raise ValueError(f"train_end ({train_end}) 必须早于 oos_start ({oos_start})")

    print(f"\n=== P1.3.a 训练窗隔离 ===")
    print(f"  train_end <= {train_end}")
    print(f"  oos_start  = {oos_start} (本脚本不使用 OOS 数据)")
    print(f"  feature_version = {FEATURE_VERSION}")
    print(f"  n_clusters = {n_clusters}")
    print(f"\n=== 加载 {len(symbols)} 个品种 ===\n")

    frames = []
    used_symbols = []

    for sym in symbols:
        print(f"  处理 {sym.upper()}...")
        df_1h = load_1h_raw(sym, limit=bar_limit)
        if df_1h is None:
            continue
        print(f"    raw bars={len(df_1h)}  range={df_1h['dt'].iloc[0]} → {df_1h['dt'].iloc[-1]}")
        feat = build_feature_frame(sym, df_1h, train_end_ts)
        if feat is None:
            continue
        print(f"    train features={len(feat)}  max_dt={feat['dt'].max()}")
        frames.append(feat)
        used_symbols.append(sym)

    if not frames:
        raise ValueError("无法加载任何品种的训练特征")

    full = pd.concat(frames, ignore_index=True)
    # 最终泄漏断言
    if full["dt"].max() > train_end_ts:
        raise RuntimeError(
            f"FATAL leak: max train dt {full['dt'].max()} > {train_end_ts}"
        )

    X = full[EXPECTED_FEATURE_COLUMNS].values
    print(f"\n全量训练矩阵: {X.shape[0]} × {X.shape[1]}  品种={len(used_symbols)}")

    # Scaler + KMeans
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(
        n_clusters=n_clusters,
        random_state=42,
        n_init=20,
        max_iter=500,
    )
    raw_labels = kmeans.fit_predict(X_scaled)
    print(f"  Inertia: {kmeans.inertia_:.2f}  n_iter={kmeans.n_iter_}")

    cluster_to_regime, cluster_stats = assign_economic_labels(
        full[EXPECTED_FEATURE_COLUMNS], raw_labels
    )

    # 分布
    regime_ids = np.array([cluster_to_regime[int(c)] for c in raw_labels])
    print("\n=== Regime 样本分布 ===")
    for rid in range(n_clusters):
        n = int(np.sum(regime_ids == rid))
        pct = 100.0 * n / len(regime_ids)
        print(f"  {rid} {REGIME_LABELS[rid]:18s}: {n:6d} ({pct:5.1f}%)")

    return {
        "model": kmeans,
        "scaler": scaler,
        "cluster_to_regime": cluster_to_regime,
        "feature_columns": list(EXPECTED_FEATURE_COLUMNS),
        "feature_version": FEATURE_VERSION,
        "train_end": train_end,
        "oos_start": oos_start,
        "trained_symbols": used_symbols,
        "n_samples": int(X.shape[0]),
        "inertia": float(kmeans.inertia_),
        "cluster_stats": cluster_stats,
        "regime_labels": REGIME_LABELS,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }


def save_model(model_data: dict, output_path: str) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        bak = out.with_suffix(out.suffix + ".bak")
        shutil.copy2(out, bak)
        print(f"  旧模型已备份: {bak}")
    with open(out, "wb") as f:
        pickle.dump(model_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  模型已保存: {out}")


def main():
    parser = argparse.ArgumentParser(description="训练 1H Regime K-Means (P1.3.a)")
    parser.add_argument("--varieties", nargs="+", help="品种列表 (默认固化品种)")
    parser.add_argument("--n-clusters", type=int, default=4)
    parser.add_argument("--train-end", type=str, default=DEFAULT_TRAIN_END)
    parser.add_argument("--oos-start", type=str, default=DEFAULT_OOS_START)
    parser.add_argument("--limit", type=int, default=None, help="每品种最多 bar 数 (默认全量)")
    parser.add_argument(
        "--output", type=str, default="models/regime_kmeans_1h.pkl",
    )
    args = parser.parse_args()

    symbols = args.varieties if args.varieties else list_solidified()
    # 训练时排除 stars=0 归档品种可选；默认仍用 list_solidified 全量
    print(f"品种: {', '.join(s.upper() for s in symbols)}")

    model_data = train_kmeans(
        symbols,
        n_clusters=args.n_clusters,
        train_end=args.train_end,
        oos_start=args.oos_start,
        bar_limit=args.limit,
    )
    save_model(model_data, args.output)

    print(f"\n=== 训练完成 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print(f"  n_samples={model_data['n_samples']}")
    print(f"  symbols={len(model_data['trained_symbols'])}")
    print(f"  train_end={model_data['train_end']}")
    print(f"  feature_version={model_data['feature_version']}")
    print(f"  output={args.output}")
    print("  下一步: python scripts/validate_regime_clusters.py")


if __name__ == "__main__":
    main()

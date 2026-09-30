#!/usr/bin/env python3
"""
校验 1H K-Means Cluster 的经济意义 (P1.3.b)

对每个样本（特征 lookback-only，模型预测 regime）计算未来 24H 统计:
  vol_24h, move_24h, abs_move_24h, dir_consistency, skew_24h

门禁（纲领）:
  1. ≥3/4 cluster 叙事一致
  2. high_vol_trend.abs_move >= 1.3 * low_vol_narrow.abs_move
  3. high_vol_trend.dir_consistency > wide_oscillation.dir_consistency
  4. wide_oscillation: |move| / abs_move 偏小（净位移弱）
  5. low_vol_narrow.vol 为最低或次低
  6. 每簇 n >= 总样本 8%

用法:
    python scripts/validate_regime_clusters.py
    python scripts/validate_regime_clusters.py --model models/regime_kmeans_1h.pkl
"""

from __future__ import annotations

import sys
import os
import argparse
import json
import pickle
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd

from data.data_store import DataStore
from cascade.regime_features import (
    extract_1h_regime_features,
    EXPECTED_FEATURE_COLUMNS,
    FEATURE_VERSION,
)
from config.prediction_scheme import list_solidified

HORIZON = 24
MIN_CLUSTER_PCT = 0.08
REGIME_LABELS = {
    0: "high_vol_trend",
    1: "low_vol_narrow",
    2: "wide_oscillation",
    3: "transition",
}


def load_model(path: str) -> dict:
    with open(path, "rb") as f:
        data = pickle.load(f)
    required = ["model", "scaler", "cluster_to_regime", "feature_columns", "train_end"]
    for k in required:
        if k not in data or data[k] is None:
            raise ValueError(f"模型缺少字段: {k}（请用 P1.3.a 脚本重训）")
    return data


def load_1h(symbol: str) -> pd.DataFrame | None:
    try:
        with DataStore(symbol) as store:
            df = store.get_main_contract_1h(limit=10**9)
        if df is None or df.empty:
            return None
        df = df.copy()
        df["dt"] = pd.to_datetime(df["dt"])
        return df.sort_values("dt").reset_index(drop=True)
    except Exception as e:
        print(f"  {symbol.upper()}: load fail ({e})")
        return None


def future_path_metrics(closes: np.ndarray, i: int, horizon: int = HORIZON) -> dict | None:
    """基于 close[i] 与 close[i+1:i+horizon+1] 计算未来路径统计。"""
    if i + horizon >= len(closes):
        return None
    c0 = closes[i]
    if c0 == 0 or np.isnan(c0):
        return None
    path = closes[i + 1: i + horizon + 1]
    # bar returns
    prev = np.concatenate([[c0], path[:-1]])
    rets = (path - prev) / prev
    total_move = (path[-1] - c0) / c0
    abs_move = abs(total_move)
    vol = float(np.std(rets)) if len(rets) else 0.0
    # direction consistency: |sum r| / sum |r|
    sum_abs = float(np.sum(np.abs(rets))) + 1e-12
    dir_consistency = float(abs(np.sum(rets)) / sum_abs)
    skew = float(pd.Series(rets).skew()) if len(rets) >= 3 else 0.0
    if np.isnan(skew):
        skew = 0.0
    return {
        "vol_24h": vol,
        "move_24h": float(total_move),
        "abs_move_24h": float(abs_move),
        "dir_consistency": dir_consistency,
        "skew_24h": skew,
    }


def collect_labeled_samples(
    symbols: list[str],
    model_data: dict,
    step: int = 6,
) -> pd.DataFrame:
    """
    在训练窗内采样：特征 dt <= train_end，用模型打标签，算未来 24H 指标。
    未来收益可用 train_end 之后的价格（评价用，不参与 fit）。
    """
    kmeans = model_data["model"]
    scaler = model_data["scaler"]
    c2r = model_data["cluster_to_regime"]
    feat_cols = model_data["feature_columns"]
    train_end = pd.Timestamp(model_data["train_end"]).normalize() + pd.Timedelta(
        hours=23, minutes=59
    )

    rows = []
    for sym in symbols:
        print(f"  校验采样 {sym.upper()}...")
        df = load_1h(sym)
        if df is None or len(df) < 200:
            continue
        feats = extract_1h_regime_features(df)
        closes = (
            df["close_price"].values.astype(float)
            if "close_price" in df.columns
            else df["close"].values.astype(float)
        )
        dts = pd.to_datetime(df["dt"]).values

        # 逐 bar（降采样 step）
        for i in range(0, len(df) - HORIZON, step):
            if pd.Timestamp(dts[i]) > train_end:
                break  # 训练窗之后的特征截面不纳入 P1.3 主校验集
            row_feat = feats.iloc[i]
            if row_feat[feat_cols].isna().any():
                continue
            x = row_feat[feat_cols].values.astype(float).reshape(1, -1)
            x_s = scaler.transform(x)
            raw = int(kmeans.predict(x_s)[0])
            regime = int(c2r.get(raw, raw))
            fut = future_path_metrics(closes, i)
            if fut is None:
                continue
            rows.append({
                "symbol": sym,
                "dt": pd.Timestamp(dts[i]),
                "regime": regime,
                "label": REGIME_LABELS.get(regime, str(regime)),
                **fut,
            })

    return pd.DataFrame(rows)


def aggregate_by_regime(samples: pd.DataFrame) -> pd.DataFrame:
    if samples.empty:
        return pd.DataFrame()
    g = samples.groupby("regime").agg(
        n=("abs_move_24h", "count"),
        vol_24h=("vol_24h", "mean"),
        move_24h=("move_24h", "mean"),
        abs_move_24h=("abs_move_24h", "mean"),
        dir_consistency=("dir_consistency", "mean"),
        skew_24h=("skew_24h", "mean"),
    )
    g["pct"] = g["n"] / g["n"].sum()
    g["net_to_abs"] = g["move_24h"].abs() / (g["abs_move_24h"] + 1e-12)
    g["label"] = g.index.map(lambda r: REGIME_LABELS.get(int(r), str(r)))
    return g


def evaluate_gates(agg: pd.DataFrame) -> tuple[bool, list[str], list[str]]:
    """返回 (passed, errors, notes)。"""
    errors = []
    notes = []
    if agg.empty or len(agg) < 3:
        return False, ["聚合结果不足 3 个 regime"], notes

    total_n = int(agg["n"].sum())
    need = {
        0: "high_vol_trend",
        1: "low_vol_narrow",
        2: "wide_oscillation",
        3: "transition",
    }

    # 6. 每簇占比
    for rid in need:
        if rid not in agg.index:
            errors.append(f"缺少 regime {rid} ({need[rid]})")
            continue
        if agg.loc[rid, "pct"] < MIN_CLUSTER_PCT:
            errors.append(
                f"regime {rid} ({need[rid]}) 占比 {agg.loc[rid, 'pct']:.1%} < {MIN_CLUSTER_PCT:.0%}"
            )

    if any(r not in agg.index for r in (0, 1, 2)):
        return False, errors, notes

    h = agg.loc[0]
    l = agg.loc[1]
    w = agg.loc[2]

    # 2. abs_move trend vs narrow
    ratio = h["abs_move_24h"] / (l["abs_move_24h"] + 1e-12)
    notes.append(f"abs_move trend/narrow = {ratio:.2f}x")
    if ratio < 1.3:
        errors.append(f"high_vol_trend.abs_move 仅 {ratio:.2f}x low_vol_narrow (需≥1.3)")

    # 3. dir_consistency trend > oscillation
    notes.append(
        f"dir_consistency trend={h['dir_consistency']:.3f} vs osc={w['dir_consistency']:.3f}"
    )
    if h["dir_consistency"] <= w["dir_consistency"]:
        errors.append(
            "high_vol_trend.dir_consistency 未高于 wide_oscillation "
            f"({h['dir_consistency']:.3f} <= {w['dir_consistency']:.3f})"
        )

    # 4. oscillation: net displacement weak vs abs
    notes.append(f"osc |move|/abs_move = {w['net_to_abs']:.3f}")
    if w["net_to_abs"] > 0.55:
        errors.append(
            f"wide_oscillation 净位移过强 net_to_abs={w['net_to_abs']:.3f} (期望偏小)"
        )

    # 5. low_vol vol rank
    vols = agg["vol_24h"].sort_values()
    rank = list(vols.index).index(1) + 1  # 1-based rank ascending
    notes.append(f"low_vol_narrow vol rank = {rank}/{len(agg)} (1=最低)")
    if rank > 2:
        errors.append(f"low_vol_narrow.vol 排名第 {rank}，需最低或次低")

    # 1. 叙事一致性计数（启发式）
    narrative_ok = 0
    checks = {
        0: (h["abs_move_24h"] >= agg["abs_move_24h"].median()) and (h["dir_consistency"] >= agg["dir_consistency"].median()),
        1: (l["vol_24h"] <= agg["vol_24h"].median()),
        2: (w["vol_24h"] >= agg["vol_24h"].median()) and (w["net_to_abs"] <= 0.55 or w["dir_consistency"] <= h["dir_consistency"]),
        3: True,  # transition 宽松
    }
    for rid, ok in checks.items():
        if rid in agg.index and ok:
            narrative_ok += 1
        elif rid in agg.index:
            notes.append(f"narrative weak: regime {rid} {need[rid]}")
    notes.append(f"narrative_ok = {narrative_ok}/4")
    if narrative_ok < 3:
        errors.append(f"叙事一致簇仅 {narrative_ok}/4 (需≥3)")

    return len(errors) == 0, errors, notes


def main():
    parser = argparse.ArgumentParser(description="P1.3.b Cluster 经济意义校验")
    parser.add_argument("--model", default="models/regime_kmeans_1h.pkl")
    parser.add_argument("--varieties", nargs="+", default=None)
    parser.add_argument("--step", type=int, default=6, help="采样步长（bars）")
    parser.add_argument(
        "--report",
        default="reports/phase1/p1_3_cluster_economics.md",
    )
    args = parser.parse_args()

    print(f"加载模型: {args.model}")
    model_data = load_model(args.model)
    print(
        f"  feature_version={model_data.get('feature_version')} "
        f"train_end={model_data.get('train_end')} "
        f"n_samples(train)={model_data.get('n_samples')}"
    )
    if model_data.get("feature_version") != FEATURE_VERSION:
        print(
            f"[WARN] 模型 feature_version={model_data.get('feature_version')} "
            f"!= 当前 {FEATURE_VERSION}"
        )

    symbols = args.varieties if args.varieties else list_solidified()
    # 排除 stars=0 可在外部传参；默认全固化
    print(f"\n=== 采样未来 24H 指标 (step={args.step}) ===\n")
    samples = collect_labeled_samples(symbols, model_data, step=args.step)
    print(f"\n有效样本: {len(samples)}")
    if samples.empty:
        raise SystemExit("无有效样本，校验失败")

    agg = aggregate_by_regime(samples)
    print("\n=== 按 Regime 聚合 ===")
    print(agg.to_string())

    passed, errors, notes = evaluate_gates(agg)
    print("\n=== 门禁 ===")
    for n in notes:
        print(f"  note: {n}")
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    else:
        print("  ALL GATES PASSED")

    # 写报告
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P1.3 Cluster 经济意义校验",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**模型**: `{args.model}`",
        f"**train_end**: {model_data.get('train_end')}",
        f"**feature_version**: {model_data.get('feature_version')}",
        f"**样本数**: {len(samples)} (step={args.step})",
        f"**门禁**: {'✅ PASS' if passed else '❌ FAIL'}",
        "",
        "## 聚合表",
        "",
        "```",
        agg.to_string(),
        "```",
        "",
        "## Notes",
        "",
    ]
    for n in notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    if errors:
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## 决策")
    lines.append("")
    if passed:
        lines.append("簇经济意义通过 → 可进入 **P1.4** OOS 动态 vs 静态回测。")
    else:
        lines.append(
            "簇经济意义**未通过** → **禁止**进入 P1.4；"
            "保持动态路由关闭；需调整特征/聚类数/标签规则后重训。"
        )
    lines.append("")
    # JSON side-car
    side = {
        "passed": passed,
        "n_samples": len(samples),
        "errors": errors,
        "notes": notes,
        "aggregate": agg.reset_index().to_dict(orient="records"),
        "model": {
            "path": args.model,
            "train_end": model_data.get("train_end"),
            "feature_version": model_data.get("feature_version"),
            "n_train_samples": model_data.get("n_samples"),
        },
    }
    json_path = report_path.with_suffix(".json")
    json_path.write_text(json.dumps(side, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {report_path}")
    print(f"JSON:  {json_path}")

    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()

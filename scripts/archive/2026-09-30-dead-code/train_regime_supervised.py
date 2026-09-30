#!/usr/bin/env python3
"""
P1.3.c 伪标签监督 Regime 分类

废弃无监督 K-Means 作为真源：
  Y = 由未来 24H 路径定义的伪标签
  X = 当前 10 维 1H regime 特征（FEATURE_VERSION=1h_v1）

伪标签规则（可调）:
  trend:   abs_move >= q_abs 且 dir_consistency >= dir_thr
  narrow:  abs_move <= q_abs_low 且 vol 偏低（用 abs_move 低分位代理）
  osc:     abs_move >= q_abs 且 dir_consistency < dir_thr
  other:   其余 → 本轮可二分类(trend vs rest) 或四分类

首轮默认:
  - 板块: black_metals (rb/i/jm/ss)
  - 任务: binary trend vs non-trend（AUC 主指标）
  - 训练窗: dt <= train_end；未来 24H 可跨 train_end 仅用于构造 Y
  - 模型: RandomForest + 可选 XGBoost
  - 门禁: AUC >= 0.55 否则触发特征重构

用法:
  python scripts/train_regime_supervised.py --sector black_metals
  python scripts/train_regime_supervised.py --sector black_metals --model both
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
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score,
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from data.data_store import DataStore
from cascade.regime_features import (
    extract_1h_regime_features,
    EXPECTED_FEATURE_COLUMNS,
    EXPECTED_FEATURE_COLUMNS_V2,
    FEATURE_VERSION,
    FEATURE_VERSION_V2,
)
from config.sector_map import get_sector_symbols, SECTOR_NAMES

DEFAULT_TRAIN_END = "2026-03-31"
DEFAULT_OOS_START = "2026-04-01"
HORIZON = 24
AUC_GATE = 0.55


def resolve_feature_set(version: str) -> tuple[str, list[str]]:
    v = version.lower().strip()
    if v in ("1h_v2", "v2", FEATURE_VERSION_V2):
        return FEATURE_VERSION_V2, list(EXPECTED_FEATURE_COLUMNS_V2)
    return FEATURE_VERSION, list(EXPECTED_FEATURE_COLUMNS)


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


def future_path_stats(closes: np.ndarray, i: int, horizon: int = HORIZON) -> dict | None:
    if i + horizon >= len(closes):
        return None
    c0 = float(closes[i])
    if c0 == 0 or np.isnan(c0):
        return None
    path = closes[i + 1: i + horizon + 1].astype(float)
    prev = np.concatenate([[c0], path[:-1]])
    rets = (path - prev) / np.where(prev == 0, np.nan, prev)
    rets = np.nan_to_num(rets, nan=0.0)
    total_move = (path[-1] - c0) / c0
    abs_move = abs(total_move)
    sum_abs = float(np.sum(np.abs(rets))) + 1e-12
    dir_consistency = float(abs(np.sum(rets)) / sum_abs)
    vol = float(np.std(rets))
    return {
        "abs_move": abs_move,
        "dir_consistency": dir_consistency,
        "vol": vol,
        "move": float(total_move),
    }


def build_dataset(
    symbols: list[str],
    train_end: str,
    step: int = 6,
    dir_thr: float = 0.40,
    abs_q_high: float = 0.70,
    abs_q_low: float = 0.30,
    feature_version: str = FEATURE_VERSION,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    构建 (X, Y) 样本。

    Y_binary: 1 = trend 伪标签
    Y_multi:  0 trend / 1 narrow / 2 osc / 3 other
    """
    train_end_ts = pd.Timestamp(train_end).normalize() + pd.Timedelta(hours=23, minutes=59)
    rows = []

    for sym in symbols:
        print(f"  构建 {sym.upper()}...")
        df = load_1h(sym)
        if df is None or len(df) < 300:
            print(f"    skip (数据不足)")
            continue
        if feature_columns is None:
            feature_columns = list(EXPECTED_FEATURE_COLUMNS)
        feats = extract_1h_regime_features(df, version=feature_version)
        closes = (
            df["close_price"].values.astype(float)
            if "close_price" in df.columns
            else df["close"].values.astype(float)
        )
        dts = pd.to_datetime(df["dt"])

        for i in range(0, len(df) - HORIZON, step):
            # X 时间截面必须在训练窗内
            if dts.iloc[i] > train_end_ts:
                break
            fr = feats.iloc[i]
            if fr[feature_columns].isna().any():
                continue
            fut = future_path_stats(closes, i)
            if fut is None:
                continue
            row = {
                "symbol": sym,
                "dt": dts.iloc[i],
                **{c: float(fr[c]) for c in feature_columns},
                **fut,
            }
            rows.append(row)

    data = pd.DataFrame(rows)
    if data.empty:
        raise ValueError("无样本")

    # 在训练集上算分位数阈值（避免用全市场混合外推；本函数仅 IS 样本）
    q_hi = float(data["abs_move"].quantile(abs_q_high))
    q_lo = float(data["abs_move"].quantile(abs_q_low))
    print(f"\n  伪标签阈值: abs_move q{int(abs_q_high*100)}={q_hi:.5f}  "
          f"q{int(abs_q_low*100)}={q_lo:.5f}  dir_thr={dir_thr}")

    def multi_label(r) -> int:
        if r["abs_move"] >= q_hi and r["dir_consistency"] >= dir_thr:
            return 0  # trend
        if r["abs_move"] <= q_lo:
            return 1  # narrow
        if r["abs_move"] >= q_hi and r["dir_consistency"] < dir_thr:
            return 2  # osc
        return 3  # other

    data["y_multi"] = data.apply(multi_label, axis=1)
    data["y_trend"] = (data["y_multi"] == 0).astype(int)

    print("  Y 分布 (multi):")
    for k, name in [(0, "trend"), (1, "narrow"), (2, "osc"), (3, "other")]:
        n = int((data["y_multi"] == k).sum())
        print(f"    {k} {name:8s}: {n:6d} ({100*n/len(data):5.1f}%)")
    print(f"  Y trend positive rate: {data['y_trend'].mean():.1%}  n={len(data)}")

    data.attrs["q_hi"] = q_hi
    data.attrs["q_lo"] = q_lo
    data.attrs["dir_thr"] = dir_thr
    return data


def time_split_auc(
    X: np.ndarray,
    y: np.ndarray,
    model_factory,
    n_splits: int = 4,
) -> dict:
    """时间序列交叉验证 AUC。"""
    # 需要足够正负样本
    if y.sum() < 20 or (len(y) - y.sum()) < 20:
        return {"mean_auc": float("nan"), "fold_aucs": [], "error": "class imbalance / too few"}

    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs = []
    accs = []
    for fold, (tr, te) in enumerate(tscv.split(X)):
        y_tr, y_te = y[tr], y[te]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue
        clf = model_factory()
        clf.fit(X[tr], y_tr)
        if hasattr(clf, "predict_proba"):
            proba = clf.predict_proba(X[te])[:, 1]
        else:
            proba = clf.decision_function(X[te])
        try:
            auc = roc_auc_score(y_te, proba)
        except ValueError:
            continue
        pred = (proba >= 0.5).astype(int)
        acc = accuracy_score(y_te, pred)
        aucs.append(float(auc))
        accs.append(float(acc))
        print(f"    fold{fold+1}: AUC={auc:.4f}  Acc={acc:.4f}  "
              f"n_tr={len(tr)} n_te={len(te)} pos_te={y_te.mean():.1%}")

    if not aucs:
        return {"mean_auc": float("nan"), "fold_aucs": [], "error": "no valid folds"}
    return {
        "mean_auc": float(np.mean(aucs)),
        "std_auc": float(np.std(aucs)),
        "fold_aucs": aucs,
        "mean_acc": float(np.mean(accs)),
    }


def holdout_eval(
    data: pd.DataFrame,
    model_factory,
    feature_columns: list[str],
    holdout_frac: float = 0.25,
) -> dict:
    """按时间切末段 holdout。"""
    data = data.sort_values("dt").reset_index(drop=True)
    cut = int(len(data) * (1 - holdout_frac))
    tr, te = data.iloc[:cut], data.iloc[cut:]
    X_tr = tr[feature_columns].values
    X_te = te[feature_columns].values
    y_tr = tr["y_trend"].values
    y_te = te["y_trend"].values

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    clf = model_factory()
    clf.fit(X_tr_s, y_tr)
    proba = clf.predict_proba(X_te_s)[:, 1]
    pred = (proba >= 0.5).astype(int)

    if len(np.unique(y_te)) < 2:
        auc = float("nan")
    else:
        auc = float(roc_auc_score(y_te, proba))

    # 特征重要性
    imp = None
    if hasattr(clf, "feature_importances_"):
        imp = sorted(
            zip(feature_columns, clf.feature_importances_.tolist()),
            key=lambda x: -x[1],
        )

    return {
        "holdout_auc": auc,
        "holdout_acc": float(accuracy_score(y_te, pred)),
        "n_train": len(tr),
        "n_test": len(te),
        "pos_rate_test": float(y_te.mean()),
        "confusion": confusion_matrix(y_te, pred).tolist(),
        "report": classification_report(y_te, pred, digits=3, zero_division=0),
        "feature_importance": imp,
        "model": clf,
        "scaler": scaler,
    }


def make_rf():
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=50,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def make_xgb():
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            objective="binary:logistic",
            eval_metric="auc",
            random_state=42,
            n_jobs=-1,
        )
    except ImportError:
        # 回退: sklearn GradientBoosting（环境无 xgboost 时）
        from sklearn.ensemble import GradientBoostingClassifier
        print("  [INFO] xgboost 未安装 → 使用 GradientBoostingClassifier")
        return GradientBoostingClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )


def main():
    parser = argparse.ArgumentParser(description="P1.3.c 伪标签监督 Regime")
    parser.add_argument("--sector", default="black_metals")
    parser.add_argument("--train-end", default=DEFAULT_TRAIN_END)
    parser.add_argument("--step", type=int, default=6)
    parser.add_argument("--dir-thr", type=float, default=0.40)
    parser.add_argument("--abs-q-high", type=float, default=0.70)
    parser.add_argument("--abs-q-low", type=float, default=0.30)
    parser.add_argument(
        "--model", choices=["rf", "xgb", "both"], default="both",
    )
    parser.add_argument(
        "--feature-version",
        default=FEATURE_VERSION,
        help="1h_v1 基础特征 / 1h_v2 路径扩展特征",
    )
    parser.add_argument("--auc-gate", type=float, default=AUC_GATE)
    parser.add_argument(
        "--report",
        default=None,
    )
    parser.add_argument(
        "--output",
        default=None,
    )
    args = parser.parse_args()

    feat_ver, feat_cols = resolve_feature_set(args.feature_version)
    if args.report is None:
        tag = "v2" if feat_ver == FEATURE_VERSION_V2 else "v1"
        args.report = f"reports/phase1/p1_3c_supervised_black_{tag}.md"
    if args.output is None:
        tag = "v2" if feat_ver == FEATURE_VERSION_V2 else "v1"
        args.output = f"models/regime_supervised_black_{tag}.pkl"

    symbols = get_sector_symbols(args.sector)
    sector_name = SECTOR_NAMES.get(args.sector, args.sector)
    print(f"=== P1.3.c 伪标签监督 ===")
    print(f"  sector={args.sector} ({sector_name})  symbols={symbols}")
    print(f"  train_end={args.train_end}  feature={feat_ver}  n_feat={len(feat_cols)}")
    print(f"  AUC gate={args.auc_gate}")

    data = build_dataset(
        symbols,
        train_end=args.train_end,
        step=args.step,
        dir_thr=args.dir_thr,
        abs_q_high=args.abs_q_high,
        abs_q_low=args.abs_q_low,
        feature_version=feat_ver,
        feature_columns=feat_cols,
    )

    X_raw = data[feat_cols].values
    y = data["y_trend"].values.astype(int)
    # 对 CV 使用整段标准化（仅用于相对比较；holdout 内重新 fit scaler）
    scaler_cv = StandardScaler()
    X = scaler_cv.fit_transform(X_raw)

    results = {
        "sector": args.sector,
        "symbols": symbols,
        "train_end": args.train_end,
        "feature_version": feat_ver,
        "feature_columns": feat_cols,
        "n_features": len(feat_cols),
        "n_samples": len(data),
        "trend_rate": float(y.mean()),
        "q_hi": data.attrs.get("q_hi"),
        "q_lo": data.attrs.get("q_lo"),
        "dir_thr": data.attrs.get("dir_thr"),
        "models": {},
    }

    model_specs = []
    if args.model in ("rf", "both"):
        model_specs.append(("rf", make_rf))
    if args.model in ("xgb", "both"):
        model_specs.append(("xgb", make_xgb))

    best_name = None
    best_auc = -1.0
    best_bundle = None

    for name, factory in model_specs:
        print(f"\n--- {name.upper()} TimeSeries CV ---")
        try:
            cv = time_split_auc(X, y, factory, n_splits=4)
        except Exception as e:
            print(f"  CV failed: {e}")
            cv = {"mean_auc": float("nan"), "error": str(e)}
        print(f"  CV mean AUC={cv.get('mean_auc')}  std={cv.get('std_auc')}")

        print(f"--- {name.upper()} Time Holdout ---")
        try:
            ho = holdout_eval(data, factory, feature_columns=feat_cols)
            print(f"  Holdout AUC={ho['holdout_auc']:.4f}  Acc={ho['holdout_acc']:.4f}")
            print(f"  pos_rate_test={ho['pos_rate_test']:.1%}")
            if ho.get("feature_importance"):
                print("  Top features:")
                for f, v in ho["feature_importance"][:5]:
                    print(f"    {f}: {v:.4f}")
        except Exception as e:
            print(f"  Holdout failed: {e}")
            ho = {"holdout_auc": float("nan"), "error": str(e)}

        # 主裁决 AUC：优先 holdout，其次 CV
        primary = ho.get("holdout_auc")
        if primary is None or (isinstance(primary, float) and np.isnan(primary)):
            primary = cv.get("mean_auc", float("nan"))

        results["models"][name] = {
            "cv": {k: v for k, v in cv.items() if k != "model"},
            "holdout": {
                k: v for k, v in ho.items()
                if k not in ("model", "scaler")
            },
            "primary_auc": primary,
        }

        if primary == primary and primary > best_auc:  # not nan
            best_auc = float(primary)
            best_name = name
            best_bundle = {
                "model": ho.get("model"),
                "scaler": ho.get("scaler"),
                "model_name": name,
            }

    passed = best_auc >= args.auc_gate
    results["best_model"] = best_name
    results["best_auc"] = best_auc
    results["auc_gate"] = args.auc_gate
    results["passed"] = passed
    results["decision"] = (
        "PASS → 可扩展多板块 / 准备监督版路由设计"
        if passed
        else "FAIL → 跳转 P1.3.d 特征重构（当前 X 对未来 Y 预测力不足）"
    )

    print(f"\n=== 裁决 ===")
    print(f"  best={best_name}  AUC={best_auc:.4f}  gate={args.auc_gate}")
    print(f"  {'PASS' if passed else 'FAIL'}: {results['decision']}")

    # 保存模型（仅 PASS 时写正式路径；FAIL 也写 debug bundle 便于分析）
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "P1.3.c",
        "passed": passed,
        "best_auc": best_auc,
        "best_model_name": best_name,
        "sector": args.sector,
        "symbols": symbols,
        "train_end": args.train_end,
        "feature_version": feat_ver,
        "feature_columns": list(feat_cols),
        "label_rule": {
            "type": "pseudo_future_24h",
            "trend": f"abs_move>=q{int(args.abs_q_high*100)} and dir_consistency>={args.dir_thr}",
            "q_hi": results["q_hi"],
            "q_lo": results["q_lo"],
            "dir_thr": results["dir_thr"],
        },
        "metrics": results,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }
    if best_bundle and best_bundle.get("model") is not None:
        payload["model"] = best_bundle["model"]
        payload["scaler"] = best_bundle["scaler"]

    if not passed:
        out_path = out_path.with_name(out_path.stem + "_fail" + out_path.suffix)
    with open(out_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  model bundle: {out_path}")

    # 报告
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# P1.3.c 伪标签监督分类 — {sector_name}",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**板块**: `{args.sector}` {symbols}",
        f"**train_end**: {args.train_end}",
        f"**feature_version**: {feat_ver} ({len(feat_cols)} dims)",
        f"**样本**: {len(data)}  trend_rate={y.mean():.1%}",
        f"**伪标签**: abs_move≥q{int(args.abs_q_high*100)} ({results['q_hi']:.5f}) "
        f"且 dir_consistency≥{args.dir_thr}",
        f"**AUC 门禁**: {args.auc_gate}",
        f"**结果**: {'✅ PASS' if passed else '❌ FAIL'}  "
        f"best={best_name} AUC={best_auc:.4f}",
        "",
        "## 模型对比",
        "",
    ]
    for name, m in results["models"].items():
        lines.append(f"### {name}")
        lines.append(f"- CV mean AUC: {m['cv'].get('mean_auc')}")
        lines.append(f"- Holdout AUC: {m['holdout'].get('holdout_auc')}")
        lines.append(f"- Holdout Acc: {m['holdout'].get('holdout_acc')}")
        lines.append(f"- Primary AUC: {m['primary_auc']}")
        if m["holdout"].get("feature_importance"):
            lines.append("- Top features:")
            for f, v in m["holdout"]["feature_importance"][:5]:
                lines.append(f"  - {f}: {v:.4f}")
        if m["holdout"].get("report"):
            lines.append("")
            lines.append("```")
            lines.append(m["holdout"]["report"].rstrip())
            lines.append("```")
        lines.append("")

    lines.extend([
        "## 决策",
        "",
        results["decision"],
        "",
        "动态路由默认状态: **仍关闭**（P0）。",
        "P1.4 仍阻塞，直至监督模型在经济意义上通过后续门禁。",
        "",
        f"产物: `{out_path}`",
        f"JSON: `{report_path.with_suffix('.json')}`",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    json_path = report_path.with_suffix(".json")
    # metrics 可 JSON 化
    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"  report: {report_path}")

    # 更新 task_state.json
    ts_path = project_root / "task_state.json"
    if ts_path.exists():
        try:
            state = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["phase"] = "P1.3.c"
    state["status"] = "completed" if passed else "failed_gate"
    state["p1_3c_result"] = {
        "sector": args.sector,
        "best_model": best_name,
        "best_auc": best_auc,
        "auc_gate": args.auc_gate,
        "passed": passed,
        "decision": results["decision"],
        "report": str(report_path).replace("\\", "/"),
    }
    for t in state.get("tasks", []):
        if t.get("id") == "P1.3.c":
            t["status"] = "completed" if passed else "failed"
            t["result_auc"] = best_auc
            t["passed_gate"] = passed
            t["feature_version"] = feat_ver
        if t.get("id") == "P1.3.d":
            if feat_ver == FEATURE_VERSION_V2:
                t["status"] = "completed" if passed else "failed"
                t["result_auc"] = best_auc
                t["note"] = f"1h_v2 path features evaluated; AUC={best_auc:.4f}"
            elif not passed:
                t["status"] = "ready"
                t["note"] = "Triggered by P1.3.c AUC < gate"
    ts_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  task_state: {ts_path}")

    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()

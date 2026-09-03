#!/usr/bin/env python3
"""
P1.3.f 诊断拆解 + 真 OOS

严格约束（用户批复）:
  1. Target A: 仅高波动 abs_move >= q70（q70 冻结于 IS）
  2. Target B: 仅高方向一致性 dir_consistency >= 0.6（提高阈值）
  3. 真 OOS: 2026-04-01 ~ 2026-07-31（禁止用 holdout 冒充）
  4. 黑色系 only；OOS 未过门前禁止扩板块
  5. 动态路由保持关闭；不触发 P1.4

用法:
  python scripts/diagnose_regime_supervised.py --sector black_metals
  python scripts/diagnose_regime_supervised.py --feature-version both
"""

from __future__ import annotations

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
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

HORIZON = 24
DEFAULT_TRAIN_END = "2026-03-31"
DEFAULT_OOS_START = "2026-04-01"
DEFAULT_OOS_END = "2026-07-31"
DIR_THR = 0.60  # 用户要求 0.6
ABS_Q = 0.70
AUC_GATE = 0.55


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
    return {
        "abs_move": float(abs_move),
        "dir_consistency": dir_consistency,
        "move": float(total_move),
        "vol": float(np.std(rets)),
    }


def feature_cols(version: str) -> tuple[str, list[str]]:
    v = version.lower()
    if v in ("1h_v2", "v2"):
        return FEATURE_VERSION_V2, list(EXPECTED_FEATURE_COLUMNS_V2)
    return FEATURE_VERSION, list(EXPECTED_FEATURE_COLUMNS)


def build_full_panel(
    symbols: list[str],
    feature_version: str,
    step: int = 6,
) -> pd.DataFrame:
    """构建含 IS+OOS 的全面板（特征截面时间不截断；Y 用未来 24H）。"""
    ver, cols = feature_cols(feature_version)
    rows = []
    for sym in symbols:
        print(f"  panel {sym.upper()} ({ver})...")
        df = load_1h(sym)
        if df is None or len(df) < 300:
            continue
        feats = extract_1h_regime_features(df, version=ver)
        closes = (
            df["close_price"].values.astype(float)
            if "close_price" in df.columns
            else df["close"].values.astype(float)
        )
        dts = pd.to_datetime(df["dt"])
        for i in range(0, len(df) - HORIZON, step):
            fr = feats.iloc[i]
            if fr[cols].isna().any():
                continue
            fut = future_path_stats(closes, i)
            if fut is None:
                continue
            rows.append({
                "symbol": sym,
                "dt": dts.iloc[i],
                **{c: float(fr[c]) for c in cols},
                **fut,
            })
    data = pd.DataFrame(rows)
    if data.empty:
        raise ValueError("empty panel")
    data = data.sort_values("dt").reset_index(drop=True)
    data.attrs["feature_version"] = ver
    data.attrs["feature_columns"] = cols
    print(f"  panel n={len(data)}  range={data['dt'].min()} → {data['dt'].max()}")
    return data


def assign_labels(
    data: pd.DataFrame,
    train_mask: np.ndarray,
    abs_q: float = ABS_Q,
    dir_thr: float = DIR_THR,
) -> dict:
    """
    阈值仅在 IS 上估计并冻结。
    Target A: abs_move >= q_abs_is
    Target B: dir_consistency >= dir_thr
    Target Combined (参考): A and B  (dir_thr 已 0.6)
    """
    is_abs = data.loc[train_mask, "abs_move"]
    q_abs = float(is_abs.quantile(abs_q))
    y_a = (data["abs_move"] >= q_abs).astype(int).values
    y_b = (data["dir_consistency"] >= dir_thr).astype(int).values
    y_c = ((data["abs_move"] >= q_abs) & (data["dir_consistency"] >= dir_thr)).astype(int).values
    print(f"  frozen abs_move q{int(abs_q*100)}(IS)={q_abs:.5f}")
    print(f"  dir_thr={dir_thr}")
    for name, y in [("A_vol", y_a), ("B_dir", y_b), ("C_trend", y_c)]:
        oos_m = ~train_mask
        if oos_m.any():
            print(
                f"    {name}: overall={y.mean():.1%}  "
                f"IS={y[train_mask].mean():.1%}  OOS={y[oos_m].mean():.1%}"
            )
        else:
            print(f"    {name}: pos={y.mean():.1%}")
    return {
        "q_abs": q_abs,
        "dir_thr": dir_thr,
        "y_a": y_a,
        "y_b": y_b,
        "y_c": y_c,
    }


def safe_auc(y_true, proba) -> float:
    y_true = np.asarray(y_true)
    proba = np.asarray(proba)
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, proba))


def safe_ap(y_true, proba) -> float:
    y_true = np.asarray(y_true)
    proba = np.asarray(proba)
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, proba))


def make_rf():
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=50,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def make_gb():
    return GradientBoostingClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )


def eval_is_cv(X: np.ndarray, y: np.ndarray, n_splits: int = 4) -> dict:
    """IS 内 TimeSeriesSplit 参考（非主裁决）。"""
    if y.sum() < 30 or (len(y) - y.sum()) < 30:
        return {"mean_auc": float("nan"), "fold_aucs": [], "note": "too few positives/negatives"}
    tscv = TimeSeriesSplit(n_splits=n_splits)
    aucs = []
    for tr, te in tscv.split(X):
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        sc = StandardScaler()
        Xtr = sc.fit_transform(X[tr])
        Xte = sc.transform(X[te])
        clf = make_rf()
        clf.fit(Xtr, y[tr])
        proba = clf.predict_proba(Xte)[:, 1]
        aucs.append(safe_auc(y[te], proba))
    return {
        "mean_auc": float(np.nanmean(aucs)) if aucs else float("nan"),
        "std_auc": float(np.nanstd(aucs)) if aucs else float("nan"),
        "fold_aucs": aucs,
    }


def eval_true_oos(
    X_is: np.ndarray,
    y_is: np.ndarray,
    X_oos: np.ndarray,
    y_oos: np.ndarray,
    model_name: str = "rf",
) -> dict:
    """IS 训练 → 真 OOS 测试。"""
    if len(y_is) == 0 or len(y_oos) == 0:
        return {"oos_auc": float("nan"), "error": "empty split"}
    if len(np.unique(y_is)) < 2:
        return {"oos_auc": float("nan"), "error": "IS single class"}
    if len(np.unique(y_oos)) < 2:
        return {
            "oos_auc": float("nan"),
            "error": "OOS single class",
            "oos_pos_rate": float(y_oos.mean()),
            "n_oos": int(len(y_oos)),
        }

    sc = StandardScaler()
    Xtr = sc.fit_transform(X_is)
    Xte = sc.transform(X_oos)
    clf = make_rf() if model_name == "rf" else make_gb()
    clf.fit(Xtr, y_is)
    proba = clf.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    imp = None
    if hasattr(clf, "feature_importances_"):
        imp = clf.feature_importances_.tolist()

    return {
        "oos_auc": safe_auc(y_oos, proba),
        "oos_ap": safe_ap(y_oos, proba),
        "oos_brier": float(brier_score_loss(y_oos, proba)),
        "oos_acc": float((pred == y_oos).mean()),
        "n_is": int(len(y_is)),
        "n_oos": int(len(y_oos)),
        "is_pos_rate": float(y_is.mean()),
        "oos_pos_rate": float(y_oos.mean()),
        "feature_importance": imp,
        "model": model_name,
    }


def walk_forward_oos_like(
    data: pd.DataFrame,
    cols: list[str],
    y: np.ndarray,
    train_end: pd.Timestamp,
    oos_end: pd.Timestamp,
    n_folds: int = 3,
) -> dict:
    """
    在 IS 尾部做前向滚动参考（仍非真 OOS）。
    真 OOS 单独报告。
    """
    is_data = data[data["dt"] <= train_end].reset_index(drop=True)
    y_is = y[data["dt"].values <= train_end]
    if len(is_data) < 500:
        return {"mean_auc": float("nan")}
    # 按时间均分 n_folds 个测试窗
    n = len(is_data)
    fold_size = n // (n_folds + 1)
    aucs = []
    for k in range(1, n_folds + 1):
        cut = fold_size * k
        end = min(cut + fold_size, n)
        if end - cut < 50:
            continue
        tr = np.arange(0, cut)
        te = np.arange(cut, end)
        yt, ye = y_is[tr], y_is[te]
        if len(np.unique(yt)) < 2 or len(np.unique(ye)) < 2:
            continue
        sc = StandardScaler()
        Xtr = sc.fit_transform(is_data.iloc[tr][cols].values)
        Xte = sc.transform(is_data.iloc[te][cols].values)
        clf = make_rf()
        clf.fit(Xtr, yt)
        proba = clf.predict_proba(Xte)[:, 1]
        aucs.append(safe_auc(ye, proba))
    return {
        "mean_auc": float(np.nanmean(aucs)) if aucs else float("nan"),
        "fold_aucs": aucs,
    }


def run_one_version(
    symbols: list[str],
    feature_version: str,
    step: int,
    train_end: str,
    oos_start: str,
    oos_end: str,
) -> dict:
    print(f"\n{'='*60}")
    print(f"Feature set: {feature_version}")
    print(f"{'='*60}")
    data = build_full_panel(symbols, feature_version, step=step)
    cols = data.attrs["feature_columns"]
    ver = data.attrs["feature_version"]

    train_end_ts = pd.Timestamp(train_end) + pd.Timedelta(hours=23, minutes=59)
    oos_start_ts = pd.Timestamp(oos_start)
    oos_end_ts = pd.Timestamp(oos_end) + pd.Timedelta(hours=23, minutes=59)

    is_mask = (data["dt"] <= train_end_ts).values
    oos_mask = ((data["dt"] >= oos_start_ts) & (data["dt"] <= oos_end_ts)).values
    print(f"  IS n={is_mask.sum()}  OOS n={oos_mask.sum()}")
    if oos_mask.sum() < 50:
        print("  [WARN] OOS samples few — check data coverage")

    labels = assign_labels(data, is_mask, abs_q=ABS_Q, dir_thr=DIR_THR)
    X = data[cols].values

    targets = {
        "A_high_vol": labels["y_a"],
        "B_high_dir": labels["y_b"],
        "C_trend_combo": labels["y_c"],
    }

    out = {
        "feature_version": ver,
        "n_features": len(cols),
        "feature_columns": cols,
        "q_abs_is": labels["q_abs"],
        "dir_thr": labels["dir_thr"],
        "n_is": int(is_mask.sum()),
        "n_oos": int(oos_mask.sum()),
        "targets": {},
    }

    for tname, y in targets.items():
        print(f"\n--- Target {tname} ---")
        # IS CV reference
        cv = eval_is_cv(X[is_mask], y[is_mask])
        print(f"  IS TSCV mean AUC={cv.get('mean_auc'):.4f}  folds={cv.get('fold_aucs')}")

        wf = walk_forward_oos_like(data, cols, y, train_end_ts, oos_end_ts)
        print(f"  IS walk-forward mean AUC={wf.get('mean_auc')}")

        # True OOS
        oos_rf = eval_true_oos(X[is_mask], y[is_mask], X[oos_mask], y[oos_mask], "rf")
        print(
            f"  TRUE OOS RF  AUC={oos_rf.get('oos_auc')}  "
            f"AP={oos_rf.get('oos_ap')}  pos_oos={oos_rf.get('oos_pos_rate')}"
        )
        oos_gb = eval_true_oos(X[is_mask], y[is_mask], X[oos_mask], y[oos_mask], "gb")
        print(
            f"  TRUE OOS GB  AUC={oos_gb.get('oos_auc')}  "
            f"AP={oos_gb.get('oos_ap')}"
        )

        # top features from RF on IS→OOS
        top = None
        if oos_rf.get("feature_importance"):
            top = sorted(
                zip(cols, oos_rf["feature_importance"]),
                key=lambda x: -x[1],
            )[:8]
            print("  Top RF features (IS-trained):")
            for f, v in top:
                print(f"    {f}: {v:.4f}")

        primary = oos_rf.get("oos_auc", float("nan"))
        passed = (primary == primary) and primary >= AUC_GATE
        out["targets"][tname] = {
            "is_cv": cv,
            "is_walk_forward": wf,
            "true_oos_rf": {k: v for k, v in oos_rf.items() if k != "feature_importance"},
            "true_oos_gb": {k: v for k, v in oos_gb.items() if k != "feature_importance"},
            "top_features": top,
            "primary_oos_auc": primary,
            "passed_gate_0.55": passed,
        }

    # 核心诊断
    a_auc = out["targets"]["A_high_vol"]["primary_oos_auc"]
    b_auc = out["targets"]["B_high_dir"]["primary_oos_auc"]
    gap = (
        float(a_auc - b_auc)
        if (a_auc == a_auc and b_auc == b_auc)
        else float("nan")
    )
    if a_auc == a_auc and b_auc == b_auc:
        if a_auc >= 0.55 and b_auc < 0.55:
            verdict = "VOL_PREDICTOR_ONLY"
            msg = (
                "Target A(波动) OOS 有信号而 Target B(方向一致性) 无信号 → "
                "本质是波动率预测器，不可用于趋势路由。"
            )
        elif a_auc >= 0.55 and b_auc >= 0.55:
            verdict = "BOTH_SIGNAL"
            msg = "波动与方向一致性均有 OOS 信号 → 可继续研究趋势伪标签。"
        elif a_auc < 0.55 and b_auc < 0.55:
            verdict = "NO_SIGNAL"
            msg = "A/B 双目标 OOS 均 <0.55 → 当前特征集废弃作路由真源。"
        else:
            verdict = "DIR_ONLY_SURPRISE"
            msg = "方向信号强于波动（少见）→ 需人工复核。"
    else:
        verdict = "INCONCLUSIVE"
        msg = "OOS AUC 无效（样本/类别不足）。"

    out["diagnosis"] = {
        "A_minus_B_oos_auc": gap,
        "verdict": verdict,
        "message": msg,
        "auc_gate": AUC_GATE,
        "routing_allowed": verdict == "BOTH_SIGNAL",
        "risk_filter_candidate": verdict in ("VOL_PREDICTOR_ONLY", "BOTH_SIGNAL")
        and (a_auc == a_auc and a_auc >= AUC_GATE),
    }
    print(f"\n  DIAGNOSIS: {verdict}")
    print(f"  {msg}")
    return out


def main():
    parser = argparse.ArgumentParser(description="P1.3.f 诊断拆解 + 真 OOS")
    parser.add_argument("--sector", default="black_metals")
    parser.add_argument(
        "--feature-version",
        default="both",
        choices=["1h_v1", "1h_v2", "both"],
    )
    parser.add_argument("--step", type=int, default=6)
    parser.add_argument("--train-end", default=DEFAULT_TRAIN_END)
    parser.add_argument("--oos-start", default=DEFAULT_OOS_START)
    parser.add_argument("--oos-end", default=DEFAULT_OOS_END)
    parser.add_argument(
        "--report",
        default="reports/phase1/p1_3f_diagnosis_oos.md",
    )
    args = parser.parse_args()

    symbols = get_sector_symbols(args.sector)
    sector_name = SECTOR_NAMES.get(args.sector, args.sector)
    versions = (
        ["1h_v1", "1h_v2"]
        if args.feature_version == "both"
        else [args.feature_version]
    )

    print("=== P1.3.f 诊断拆解 + 真 OOS ===")
    print(f"  sector={args.sector} {symbols}")
    print(f"  IS <= {args.train_end}  OOS {args.oos_start}..{args.oos_end}")
    print(f"  Target A: abs_move>=q70(IS)  Target B: dir_consistency>={DIR_THR}")
    print(f"  AUC gate={AUC_GATE}  (主裁决=TRUE OOS，非 holdout)")
    print("  动态路由: 保持关闭 | 禁止扩板块直至 OOS 站稳")

    all_results = {
        "task": "P1.3.f",
        "sector": args.sector,
        "symbols": symbols,
        "train_end": args.train_end,
        "oos_start": args.oos_start,
        "oos_end": args.oos_end,
        "dir_thr": DIR_THR,
        "abs_q": ABS_Q,
        "auc_gate": AUC_GATE,
        "versions": {},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    for ver in versions:
        all_results["versions"][ver] = run_one_version(
            symbols, ver, args.step,
            args.train_end, args.oos_start, args.oos_end,
        )

    # 全局裁决：以 v2 为主，v1 对照
    primary_ver = "1h_v2" if "1h_v2" in all_results["versions"] else versions[0]
    diag = all_results["versions"][primary_ver]["diagnosis"]
    all_results["primary_version"] = primary_ver
    all_results["final_diagnosis"] = diag

    # 写报告
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P1.3.f 诊断拆解 + 真 OOS",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**板块**: {sector_name} `{args.sector}` {symbols}",
        f"**IS**: ≤ {args.train_end}",
        f"**真 OOS**: {args.oos_start} ~ {args.oos_end}",
        f"**Target A**: abs_move ≥ q70（IS 冻结）",
        f"**Target B**: dir_consistency ≥ {DIR_THR}",
        f"**Target C**: A∧B（参考 trend 组合）",
        f"**主裁决**: TRUE OOS AUC（非 holdout）",
        f"**AUC 门禁**: {AUC_GATE}",
        "",
        "## 最终诊断",
        "",
        f"- **verdict**: `{diag['verdict']}`",
        f"- **message**: {diag['message']}",
        f"- **A−B OOS AUC gap**: {diag.get('A_minus_B_oos_auc')}",
        f"- **routing_allowed**: {diag.get('routing_allowed')}",
        f"- **risk_filter_candidate** (高波规避): {diag.get('risk_filter_candidate')}",
        "",
        "## 分版本结果",
        "",
    ]

    for ver, res in all_results["versions"].items():
        lines.append(f"### {ver}")
        lines.append(f"- n_IS={res['n_is']}  n_OOS={res['n_oos']}  q_abs_IS={res['q_abs_is']:.5f}")
        lines.append("")
        lines.append("| Target | IS CV AUC | TRUE OOS RF | TRUE OOS GB | Gate |")
        lines.append("|--------|----------:|------------:|------------:|:----:|")
        def _fmt(x):
            try:
                x = float(x)
                return f"{x:.4f}" if x == x else "nan"
            except Exception:
                return "nan"

        for tname, t in res["targets"].items():
            cv = t["is_cv"].get("mean_auc")
            oos = t["true_oos_rf"].get("oos_auc")
            oos_gb = t["true_oos_gb"].get("oos_auc")
            gate = "PASS" if t["passed_gate_0.55"] else "FAIL"
            lines.append(
                f"| {tname} | {_fmt(cv)} | {_fmt(oos)} | {_fmt(oos_gb)} | {gate} |"
            )
        lines.append("")
        ta = res["targets"]["A_high_vol"]
        if ta.get("top_features"):
            lines.append("Top features (Target A, RF):")
            for f, v in ta["top_features"][:5]:
                lines.append(f"- {f}: {v:.4f}")
            lines.append("")
        tb = res["targets"]["B_high_dir"]
        if tb.get("top_features"):
            lines.append("Top features (Target B, RF):")
            for f, v in tb["top_features"][:5]:
                lines.append(f"- {f}: {v:.4f}")
            lines.append("")
        lines.append(f"Diagnosis: **{res['diagnosis']['verdict']}** — {res['diagnosis']['message']}")
        lines.append("")

    lines.extend([
        "## 决策约束（强制）",
        "",
        "1. 动态路由默认 **继续关闭**",
        "2. **禁止**扩展能化/农产品，直至黑色系方向目标 OOS 站稳",
        "3. **禁止**启动 P1.4 净 PF 对比",
        "4. 若 verdict=VOL_PREDICTOR_ONLY：路由逻辑应退化为「规避高波震荡」风控过滤器，而非趋势寻找",
        "5. 若 verdict=NO_SIGNAL：废弃当前特征集作任何路由真源，另寻方向性特征",
        "",
        f"JSON: `{report_path.with_suffix('.json')}`",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    json_path = report_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n报告: {report_path}")
    print(f"JSON:  {json_path}")

    # task_state
    ts_path = project_root / "task_state.json"
    if ts_path.exists():
        try:
            state = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["phase"] = "P1.3.f"
    state["status"] = diag["verdict"]
    state["p1_3f_result"] = {
        "verdict": diag["verdict"],
        "message": diag["message"],
        "primary_version": primary_ver,
        "A_oos_auc": all_results["versions"][primary_ver]["targets"]["A_high_vol"]["primary_oos_auc"],
        "B_oos_auc": all_results["versions"][primary_ver]["targets"]["B_high_dir"]["primary_oos_auc"],
        "C_oos_auc": all_results["versions"][primary_ver]["targets"]["C_trend_combo"]["primary_oos_auc"],
        "routing_allowed": diag.get("routing_allowed"),
        "risk_filter_candidate": diag.get("risk_filter_candidate"),
        "report": str(report_path).replace("\\", "/"),
    }
    # update tasks list
    tasks = state.get("tasks", [])
    found = False
    for t in tasks:
        if t.get("id") == "P1.3.f":
            t["status"] = "completed"
            t["verdict"] = diag["verdict"]
            t["result"] = state["p1_3f_result"]
            found = True
    if not found:
        tasks.append({
            "id": "P1.3.f",
            "name": "诊断拆解 + 真 OOS",
            "status": "completed",
            "verdict": diag["verdict"],
            "result": state["p1_3f_result"],
        })
    for t in tasks:
        if t.get("id") == "P1.3.e":
            t["status"] = "blocked"
            t["note"] = "Blocked until black metals direction OOS AUC stable >=0.55"
        if t.get("id") == "P1.4":
            t["status"] = "blocked"
    state["tasks"] = tasks
    state["production"] = {
        "dynamic_routing_default": False,
        "reason": f"P1.3.f verdict={diag['verdict']}; routing locked",
    }
    ts_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"task_state: {ts_path}")

    # exit code: 0 always for completed diagnosis; use 2 if both no signal for automation
    if diag["verdict"] == "NO_SIGNAL":
        raise SystemExit(2)
    if diag["verdict"] == "VOL_PREDICTOR_ONLY":
        raise SystemExit(3)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

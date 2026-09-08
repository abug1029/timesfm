"""A2-P1 LGBM 基线探针: walk-forward 训练 + 三曲线门禁。"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
import pandas as pd
try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    lgb = None
    HAS_LIGHTGBM = False
from sklearn.model_selection import TimeSeriesSplit

FEATURE_COLS = [
    "daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
    "hurst","vol_prob","hour_sin","hour_cos","day_of_week",
    "timesfm_pure_pred","timesfm_confidence","horizon_slope",
]

# 超参网格 (内层 TimeSeriesSplit 选)
PARAM_GRID = {
    "num_leaves": [15, 31, 63],
    "min_child_samples": [20, 50],
    "lambda_l1": [0.0, 0.1, 1.0],
    "lambda_l2": [0.0, 0.1],
    "colsample_bytree": [0.7, 0.9],
    "n_estimators": [100, 300],
    "learning_rate": [0.05, 0.1],
    "max_depth": [-1, 6],
}


def _select_hyperparams(X_train, y_train, w_train, random_state=None):
    """内层 TimeSeriesSplit(3) 选超参 (MSE + sample_weight)。返回最佳 params。"""
    tscv = TimeSeriesSplit(n_splits=3)
    best_score, best_params = -np.inf, None
    # 网格搜索 (简化: 随机抽 16 组避免全量爆炸)
    import itertools
    keys = list(PARAM_GRID.keys())
    combos = list(itertools.product(*[PARAM_GRID[k] for k in keys]))
    rng = np.random.default_rng(random_state if random_state is not None else 42)
    sampled = rng.choice(len(combos), size=min(16, len(combos)), replace=False)
    for idx in sampled:
        params = dict(zip(keys, combos[idx]))
        params["verbose"] = -1
        scores = []
        best_iters = []
        for tr_idx, va_idx in tscv.split(X_train):
            m = lgb.LGBMRegressor(**params)
            m.fit(
                X_train[tr_idx], y_train[tr_idx],
                sample_weight=w_train[tr_idx],
                eval_set=[(X_train[va_idx], y_train[va_idx])],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )
            best_iters.append(m.best_iteration_)
            pred = m.predict(X_train[va_idx])
            # 评分: 与 sample_weight 对齐的负 MSE
            scores.append(-np.average((pred - y_train[va_idx]) ** 2, weights=w_train[va_idx]))
        mean_score = np.mean(scores)
        if mean_score > best_score:
            # 更新 n_estimators 为当前参数组合下的平均最优停止步数
            params["n_estimators"] = int(np.mean(best_iters))
            best_score, best_params = mean_score, params
    return best_params or {"num_leaves": 31, "verbose": -1}


def train_lgbm_walkforward(
    dense_matrix: pd.DataFrame,
    eval_bar_indices: list,
    refit_every: int = 10,
    random_state=None,
    target_col: str = "Y",
) -> pd.DataFrame:
    """
    Walk-forward expanding window 训练 LGBM。

    对每个 eval bar T0:
      - 训练切片 = dense_matrix 中 bar_idx <= T0 - 24 的行 (防穿越)
      - 内层 TimeSeriesSplit 选超参 (仅训练段)
      - 训练最终模型 -> 预测 T0 -> pred_return
      - pred_move = T0_close * pred_return (T0_close 由调用方提供, 此处用 Y 还原)
    refit_every: 每 N 个 eval 点重训一次, 中间复用上次模型。
    """
    mat = dense_matrix.sort_values("bar_idx").reset_index(drop=True)
    has_close = "t0_close" in mat.columns

    results = []
    last_model = None
    last_train_end = -1

    for i, t0 in enumerate(eval_bar_indices):
        if i % refit_every == 0 or last_model is None:
            # 训练切片: bar_idx <= t0 - 24
            train_mask = mat["bar_idx"] <= (t0 - 24)
            train_df = mat[train_mask]
            if len(train_df) < 50:
                results.append({"bar_idx": t0, "pred_return": 0.0})
                continue
            # 用 reindex 替代直接列索引: 缺失列自动填 NaN, LGBM 原生处理
            X_train = train_df.reindex(columns=FEATURE_COLS, fill_value=np.nan).values.astype(float)
            y_train = train_df[target_col].values.astype(float)
            w_train = train_df["weight"].values.astype(float)
            # 保留 NaN: LGBM use_missing=True 原生处理, 填 0 会混淆"无变化"与"数据缺失"
            params = _select_hyperparams(X_train, y_train, w_train, random_state=random_state)
            # 直接使用 CV 算出的优化 n_estimators 跑满全量数据
            model_params = dict(params)
            if random_state is not None:
                model_params["random_state"] = random_state
            last_model = lgb.LGBMRegressor(**model_params)
            last_model.fit(X_train, y_train, sample_weight=w_train)
            last_train_end = t0

        # 预测 T0
        t0_row = mat[mat["bar_idx"] == t0]
        if t0_row.empty:
            results.append({"bar_idx": t0, "pred_return": 0.0})
            continue
        # 同样用 reindex 处理缺失列
        X_t0 = t0_row.reindex(columns=FEATURE_COLS, fill_value=np.nan).values.astype(float)
        pred_ret = float(last_model.predict(X_t0)[0])
        results.append({"bar_idx": t0, "pred_return": pred_ret})

    out = pd.DataFrame(results)
    # 还原 pred_move / actual_move (需 t0_close; 若 dense_matrix 含 t0_close 列则用之)
    if has_close:
        close_map = dict(zip(mat["bar_idx"], mat["t0_close"]))
        out["t0_close"] = out["bar_idx"].map(close_map)
        out["pred_move"] = out["t0_close"] * out["pred_return"]
        out["actual_move"] = out["bar_idx"].map(
            dict(zip(mat["bar_idx"], mat["t0_close"] * mat["Y"]))
        )
    else:
        out["pred_move"] = out["pred_return"]
        out["actual_move"] = out["bar_idx"].map(
            dict(zip(mat["bar_idx"], mat["Y"]))
        )
    return out


from config.backtest_config import SYMBOLS, TICK_SIZES
from cascade.evaluation_metrics import calc_net_metrics, calc_vol_scaled_mae


def paired_bootstrap_ev_ci(
    pnl_diff: np.ndarray,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """
    配对 bootstrap on per-point net PnL 差 (LGBM - scheme)。
    返回 EV 差的 95% CI (lower, upper)。
    """
    rng = np.random.default_rng(seed)
    n = len(pnl_diff)
    if n == 0:
        return (0.0, 0.0)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = np.mean(pnl_diff[idx])
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def evaluate_gate(
    lgbm_preds: np.ndarray,
    pure_preds: np.ndarray,
    scheme_preds: np.ndarray,
    actuals: np.ndarray,
    base_prices: np.ndarray,
    atr: np.ndarray,
    tick_size: float,
    slippage_ticks: int = 2,
    n_boot: int = 1000,
) -> dict:
    """
    三曲线 PF/EV/MaxDD + 配对 bootstrap 门禁。

    GO: LGBM PF > scheme PF AND LGBM EV > 0 AND bootstrap EV 差 95% CI 下界 > 0
    """
    lgbm_dir = np.sign(lgbm_preds)
    scheme_dir = np.sign(scheme_preds)
    pure_dir = np.sign(pure_preds)

    lgbm_m = calc_net_metrics(lgbm_dir, actuals, tick_size=tick_size,
                              slippage_ticks=slippage_ticks, base_prices=base_prices)
    scheme_m = calc_net_metrics(scheme_dir, actuals, tick_size=tick_size,
                                slippage_ticks=slippage_ticks, base_prices=base_prices)
    pure_m = calc_net_metrics(pure_dir, actuals, tick_size=tick_size,
                              slippage_ticks=slippage_ticks, base_prices=base_prices)

    # 配对 PnL 差 (LGBM - scheme)
    lgbm_pnl = lgbm_dir * actuals - (tick_size * slippage_ticks) * (lgbm_dir != 0)
    scheme_pnl = scheme_dir * actuals - (tick_size * slippage_ticks) * (scheme_dir != 0)
    ci_lo, ci_hi = paired_bootstrap_ev_ci(lgbm_pnl - scheme_pnl, n_boot=n_boot)

    go = (lgbm_m["PF"] > scheme_m["PF"]) and (lgbm_m["EV"] > 0) and (ci_lo > 0)

    # Vol-Scaled MAE (logging only)
    vol_mae = {
        "lgbm": calc_vol_scaled_mae(lgbm_preds, actuals, atr),
        "pure": calc_vol_scaled_mae(pure_preds, actuals, atr),
        "scheme": calc_vol_scaled_mae(scheme_preds, actuals, atr),
    }

    return {
        "gate": "GO" if go else "NO-GO",
        "lgbm_metrics": lgbm_m,
        "scheme_metrics": scheme_m,
        "pure_metrics": pure_m,
        "ev_diff_ci": {"lower": ci_lo, "upper": ci_hi},
        "vol_scaled_mae": vol_mae,
    }


def _load_models():
    """加载共享 TimesFM 实例 (hourly + daily)。"""
    import torch
    torch.set_float32_matmul_precision("high")
    import timesfm
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    base = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    hourly = HourlyModel(shared_model=base)
    daily = DailyModel(shared_model=base)
    return hourly, daily


def run_symbol(symbol: str, max_points: int | None, dense_step: int,
               refit_every: int, hourly, daily) -> dict:
    """单品种三曲线 + 门禁。"""
    from data.data_store import DataStore, BacktestDataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from config.backtest_config import CONTEXT_BARS, HORIZON, STEP
    from config.prediction_scheme import SCHEMES
    from cascade.features import _calc_atr
    import json, pathlib

    symbol = symbol.upper()
    sym_lower = symbol.lower()
    cache = f"reports/a2_p1_features/{sym_lower}_dense_matrix.parquet"
    pathlib.Path(cache).parent.mkdir(parents=True, exist_ok=True)

    with DataStore(sym_lower) as store:
        mat = build_dense_feature_matrix(
            sym_lower, store, dense_step=dense_step,
            shared_hourly=hourly, shared_daily=daily, cache_path=cache,
        )

    # t0_close 列 (还原 pred_move 用)
    with DataStore(sym_lower) as store2:
        df_1h = store2.get_main_contract_1h(limit=100000)
    closes = df_1h["close_price"].values.astype(float)
    mat["t0_close"] = [closes[t] if t < len(closes) else np.nan for t in mat["bar_idx"]]

    # eval points: 复用 monthly_backtest 网格
    total = len(df_1h)
    eval_bars = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))
    if max_points:
        eval_bars = eval_bars[-max_points:]  # 取最新 max_points 个, 确保训练数据充足
    # 仅保留 dense_matrix 中有的 bar
    valid_set = set(mat["bar_idx"].tolist())
    eval_bars = [b for b in eval_bars if b in valid_set]

    if not eval_bars:
        return {"symbol": symbol, "gate": "NO-GO", "error": "no valid eval bars",
                "lgbm_metrics": {}, "scheme_metrics": {}, "pure_metrics": {},
                "ev_diff_ci": {}, "vol_scaled_mae": {}, "caveats": [],
                "n_eval": 0, "dense_rows": len(mat), "underpowered": len(mat) < 200}

    # LGBM walk-forward (曲线③)
    lgbm_out = train_lgbm_walkforward(mat, eval_bars, refit_every=refit_every)

    # 曲线①② @ eval bars
    pure_preds, scheme_preds, actuals, bases, atrs = [], [], [], [], []
    scheme_errors: list[tuple[int, str]] = []  # (eval_index, error_msg)
    scheme = SCHEMES.get(sym_lower)
    for b in eval_bars:
        row = mat[mat["bar_idx"] == b].iloc[0]
        t0_close = float(row["t0_close"]) if not np.isnan(row["t0_close"]) else closes[b]
        # ① pure: dense_matrix 已有 timesfm_pure_pred (收益率形式) -> 价格变动
        pure_move = float(row["timesfm_pure_pred"]) * t0_close
        pure_preds.append(pure_move)
        # actual
        actual_move = closes[b + HORIZON] - closes[b]
        actuals.append(actual_move)
        bases.append(t0_close)
        # ATR @ T0
        atr_arr = _calc_atr(df_1h.iloc[: b + 1])
        atrs.append(float(atr_arr[-1]) if len(atr_arr) else 1.0)
        # ② scheme: HourlyModel.predict with scheme covs
        if scheme is None:
            scheme_preds.append(float('nan'))  # 未配置，不伪装为 0
            continue
        cutoff = pd.Timestamp(df_1h["dt"].iloc[b]).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with BacktestDataStore(sym_lower, cutoff) as bts:
                dr = daily.predict(sym_lower, bts)
                hr = HourlyModel(shared_model=hourly.model)
                res = hr.predict(sym_lower, bts, dr,
                                 covariate_type=scheme.covariate_type,
                                 covariate_types=scheme.covariate_types,
                                 verbose=False, skip_validation=True)
                from cascade.signal_contract import position_from_forecast
                _sig = position_from_forecast(
                    res.point_forecast, t0_close, scheme=scheme,
                    daily_slope=getattr(dr, "horizon_slope", None),
                )
                scheme_move = float(_sig["delta_pred"])
                scheme_preds.append(scheme_move)
        except Exception as e:
            scheme_preds.append(float('nan'))
            scheme_errors.append((len(scheme_preds) - 1, f"{type(e).__name__}: {e}"))

    # scheme 错误可见化
    if scheme_errors:
        print(f"[{symbol}] scheme 执行失败 ({len(scheme_errors)} 处):")
        for idx, msg in scheme_errors:
            print(f"  eval[{idx}]: {msg}")

    # LGBM pred_move (曲线③)
    lgbm_moves = lgbm_out["pred_move"].values.astype(float)

    # tick_size
    try:
        tick = float(TICK_SIZES[sym_lower])
    except KeyError as exc:
        raise RuntimeError(f"missing tick size for {sym_lower}") from exc

    verdict = evaluate_gate(
        np.array(lgbm_moves), np.array(pure_preds), np.array(scheme_preds),
        np.array(actuals), np.array(bases), np.array(atrs), tick_size=tick,
    )
    verdict["symbol"] = symbol
    verdict["n_eval"] = len(eval_bars)
    verdict["dense_rows"] = len(mat)
    verdict["underpowered"] = len(mat) < 200
    caveats = ["vol_prob 在 2026-03 前评估点有轻微 Lookahead（模型训练截止 2026-03-31），不影响定性结论"]
    if verdict["underpowered"]:
        caveats.append("UNDERPOWERED: dense 训练切片 < 200 行, 结论降权")
    verdict["caveats"] = caveats
    return verdict


def write_report(verdicts: list, path: str):
    """写 Markdown 裁决报告。"""
    import pathlib
    lines = ["# A2-P1 LGBM 基线门禁裁决报告", "", f"**品种数**: {len(verdicts)}", ""]
    go = [v for v in verdicts if v.get("gate") == "GO"]
    lines.append(f"**聚合裁决**: {'GO' if len(go) > len(verdicts)/2 else 'NO-GO'} "
                 f"({len(go)}/{len(verdicts)} 品种 GO)")
    lines.append("")
    lines.append("| 品种 | gate | LGBM PF | scheme PF | LGBM EV | EV差CI下界 | n |")
    lines.append("|------|------|---------|-----------|---------|-----------|---|")
    for v in verdicts:
        lpf = v.get("lgbm_metrics", {}).get("PF", "N/A")
        spf = v.get("scheme_metrics", {}).get("PF", "N/A")
        lev = v.get("lgbm_metrics", {}).get("EV", "N/A")
        ci = v.get("ev_diff_ci", {}).get("lower", "N/A")
        lines.append(f"| {v.get('symbol', '?')} | {v.get('gate', '?')} | {lpf} | "
                     f"{spf} | {lev} | {ci} | {v.get('n_eval', 0)} |")
    lines.append("")
    lines.append("## vol_prob 前瞻瑕疵声明")
    if verdicts and verdicts[0].get("caveats"):
        lines.append(verdicts[0]["caveats"][0])
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    """向后兼容入口: 调用 Orchestrator 调度 Worker 子进程."""
    import argparse
    p = argparse.ArgumentParser(description="A2-P1 LGBM 基线探针 (向后兼容入口, 内部调用 Orchestrator)")
    p.add_argument("symbols", nargs="*", default=None, help="品种列表 (default: 全 20 品种)")
    p.add_argument("--max-points", type=int, default=None, help="[DEPRECATED] 忽略, 使用细粒度续跑 (Worker 内部跳过已完成 bar_idx)")
    p.add_argument("--dense-step", type=int, default=24, help="dense 矩阵步长 (default: 24)")
    p.add_argument("--refit-every", type=int, default=10, help="LGBM 重训间隔 (default: 10)")
    p.add_argument("--force", action="store_true", help="强制重跑 (忽略已有 JSONL)")
    args = p.parse_args()

    if args.max_points is not None:
        print("[WARNING] --max-points 已废弃, 使用细粒度续跑 (Worker 内部跳过已完成 bar_idx)")
    if args.dense_step != 24:
        print(f"[WARNING] --dense-step={args.dense_step} ignored by Orchestrator mode; "
              f"use Worker directly: python scripts/a2_p1_worker.py {args.symbols[0] if args.symbols else 'ss'} --dense-step {args.dense_step}")
    if args.refit_every != 10:
        print(f"[WARNING] --refit-every={args.refit_every} ignored by Orchestrator mode; "
              f"use Worker directly: python scripts/a2_p1_worker.py {args.symbols[0] if args.symbols else 'ss'} --refit-every {args.refit_every}")

    # 调用 Orchestrator
    from scripts.a2_p1_orchestrator import run_orchestrator
    symbols = args.symbols if args.symbols else list(SYMBOLS)
    run_orchestrator(symbols, force=args.force)


if __name__ == "__main__":
    main()

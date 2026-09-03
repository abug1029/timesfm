"""A2-P2 残差叠加 Worker：LGBM 学习 TimesFM 残差，叠加到基线预测。"""
from __future__ import annotations
import sys
import pathlib
import os
import json
import argparse
import subprocess

import numpy as np
import pandas as pd

FM_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 导入 A2-P1 共享运行时工具
sys.path.insert(0, str(FM_ROOT))
from scripts.a2_p1_runtime import (
    generate_eval_grid,
    exclusive_result_lock,
    append_unique_record,
    stable_symbol_seed,
    RunConfig,
)


def compute_residual_target(dense_matrix: pd.DataFrame) -> pd.DataFrame:
    """计算残差目标 Y_residual = Y - timesfm_pure_pred。

    timesfm_pure_pred 为 NaN 时 Y_residual 也为 NaN，由 LGBM use_missing 原生处理。
    """
    out = dense_matrix.copy()
    out["Y_residual"] = out["Y"] - out["timesfm_pure_pred"]
    return out


def stack_predictions(timesfm_pure_pred: np.ndarray, lgbm_residual_pred: np.ndarray) -> np.ndarray:
    """堆叠预测 = TimesFM 基线 + LGBM 残差校正。"""
    return timesfm_pure_pred + lgbm_residual_pred


def _get_git_version() -> str:
    """获取当前 git commit hash"""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=FM_ROOT)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_completed_bars(jsonl_path: pathlib.Path) -> set:
    """读取已有 JSONL, 提取已完成的 bar_idx 集合"""
    completed = set()
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    completed.add(rec["bar_idx"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return completed


def _generate_eval_grid(symbol: str, total_bars: int) -> list:
    """生成 eval bars 网格 (委托共享函数, 与 monthly_backtest/lgbm_features 一致)"""
    return generate_eval_grid(total_bars)


def _evaluate_one_point(mat, t0, hourly, daily, closes, df_1h, scheme, symbol):
    """
    评估单个 eval point T0。
    返回 dict: {bar_idx, pure_pred_move, scheme_pred_move,
                actual_move, base_price, atr, scheme_ok, scheme_error}
    """
    from config.backtest_config import HORIZON
    from cascade.features import _calc_atr

    base_price = float(closes[t0])
    actual_move = float(closes[t0 + HORIZON] - closes[t0])

    atr_arr = _calc_atr(df_1h.iloc[:t0 + 1])
    atr = float(atr_arr[-1]) if len(atr_arr) else 1.0

    row = mat[mat["bar_idx"] == t0]
    if row.empty:
        pure_pred_move = 0.0
    else:
        pure_return = float(row["timesfm_pure_pred"].iloc[0])
        pure_pred_move = pure_return * base_price

    scheme_pred_move = None
    scheme_ok = None
    scheme_error = None
    if scheme is not None:
        try:
            from data.data_store import BacktestDataStore
            from cascade.daily_model import DailyModel
            from cascade.hourly_model import HourlyModel
            cutoff = pd.Timestamp(df_1h["dt"].iloc[t0]).strftime("%Y-%m-%d %H:%M:%S")
            with BacktestDataStore(symbol, cutoff) as bts:
                dr = daily.predict(symbol, bts)
                hr = HourlyModel(shared_model=hourly.model)
                res = hr.predict(symbol, bts, dr,
                                 covariate_type=scheme.covariate_type,
                                 covariate_types=scheme.covariate_types,
                                 verbose=False, skip_validation=True)
                from cascade.signal_contract import position_from_forecast
                _sig = position_from_forecast(
                    res.point_forecast, base_price, scheme=scheme,
                    daily_slope=getattr(dr, "horizon_slope", None),
                )
                scheme_pred_move = float(_sig["delta_pred"])
                scheme_ok = True
        except Exception as exc:
            scheme_pred_move = None
            scheme_ok = False
            scheme_error = f"{type(exc).__name__}: {exc}"

    return {
        "bar_idx": t0,
        "pure_pred_move": pure_pred_move,
        "scheme_pred_move": scheme_pred_move,
        "scheme_ok": scheme_ok,
        "scheme_error": scheme_error,
        "actual_move": actual_move,
        "base_price": base_price,
        "atr": atr,
    }


def run_worker(symbol: str, dense_step: int, refit_every: int,
               dry_run: bool = False, run_id: str = "a2-p2"):
    """A2-P2 Worker 主函数: 残差训练 + 堆叠预测 + 细粒度断点续跑"""
    from data.data_store import DataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from config.prediction_scheme import SCHEMES

    symbol_upper = symbol.upper()
    symbol_lower = symbol.lower()
    version = _get_git_version()
    seed = stable_symbol_seed(symbol_upper)
    np.random.seed(seed)

    config = RunConfig.for_run(run_id, [symbol_lower], FM_ROOT)
    results_dir = config.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = results_dir / f"{symbol_lower}.jsonl"

    with DataStore(symbol_lower) as store:
        df_1h = store.get_main_contract_1h(limit=100000)
    total_bars = len(df_1h)
    closes = df_1h["close_price"].values.astype(float)
    all_eval_bars = _generate_eval_grid(symbol_lower, total_bars)

    cache_path = f"reports/a2_p1_features/{symbol_lower}_dense_matrix.parquet"
    market_cache_path = f"reports/a2_p1_features/{symbol_lower}_market.parquet"
    tsfm_resume_path = f"reports/a2_p1_features/{symbol_lower}_tsfm.jsonl"
    pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

    completed_bars = _load_completed_bars(jsonl_path)
    pending_bars = [b for b in all_eval_bars if b not in completed_bars]
    print(f"[Worker {symbol_upper}] {len(completed_bars)} done, {len(pending_bars)} pending, {total_bars} total bars", flush=True)

    if dry_run:
        print(f"[Worker {symbol_upper}] DRY RUN: would evaluate {len(pending_bars)} bars", flush=True)
        if pending_bars:
            print(f"  First 5 pending: {pending_bars[:5]}", flush=True)
            print(f"  Last 5 pending: {pending_bars[-5:]}", flush=True)
        return

    if not pending_bars:
        print(f"[Worker {symbol_upper}] all done, exit", flush=True)
        return

    lock_path = results_dir / f"{symbol_lower}.worker.lock"
    try:
        with exclusive_result_lock(lock_path, run_id=run_id):
            _run_worker_core(
                symbol_lower, symbol_upper, version, seed, run_id,
                df_1h, closes, total_bars, all_eval_bars, pending_bars,
                results_dir, jsonl_path, dense_step, refit_every,
            )
    except RuntimeError as exc:
        print(f"[Worker {symbol_upper}] LOCK FAILED: {exc}", flush=True)
        sys.exit(1)


def _run_worker_core(
    symbol_lower: str,
    symbol_upper: str,
    version: str,
    seed: int,
    run_id: str,
    df_1h,
    closes,
    total_bars: int,
    all_eval_bars: list,
    pending_bars: list,
    results_dir: pathlib.Path,
    jsonl_path: pathlib.Path,
    dense_step: int,
    refit_every: int,
):
    """A2-P2 Worker 核心逻辑 (必须在 exclusive_result_lock 持有期间调用)"""
    from data.data_store import DataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward
    from config.prediction_scheme import SCHEMES

    # 加载模型
    print(f"[Worker {symbol_upper}] loading models...", flush=True)
    import torch
    torch.set_float32_matmul_precision("high")
    import timesfm
    base = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    hourly = HourlyModel(shared_model=base)
    daily = DailyModel(shared_model=base)

    # 构建 dense matrix (复用 A2-P1 缓存)
    cache_path = f"reports/a2_p1_features/{symbol_lower}_dense_matrix.parquet"
    market_cache_path = f"reports/a2_p1_features/{symbol_lower}_market.parquet"
    tsfm_resume_path = f"reports/a2_p1_features/{symbol_lower}_tsfm.jsonl"
    print(f"[Worker {symbol_upper}] building dense matrix...", flush=True)
    with DataStore(symbol_lower) as store:
        mat = build_dense_feature_matrix(
            symbol_lower, store, dense_step=dense_step,
            shared_hourly=hourly, shared_daily=daily, cache_path=cache_path,
            market_cache_path=market_cache_path, tsfm_resume_path=tsfm_resume_path,
        )

    mat["t0_close"] = [closes[t] if t < len(closes) else float("nan") for t in mat["bar_idx"]]

    # A2-P2 关键差异: 计算残差目标
    mat = compute_residual_target(mat)

    # LGBM walk-forward 训练 (target_col="Y_residual")
    print(f"[Worker {symbol_upper}] training LGBM on residual target, {len(mat)} dense rows...", flush=True)
    lgbm_out = train_lgbm_walkforward(
        mat, all_eval_bars, refit_every=refit_every,
        random_state=seed, target_col="Y_residual",
    )
    lgbm_preds = dict(zip(lgbm_out["bar_idx"], lgbm_out["pred_return"]))

    # 逐 pending bar 评估 + 堆叠预测
    scheme = SCHEMES.get(symbol_lower)
    print(f"[Worker {symbol_upper}] evaluating {len(pending_bars)} points with stacked predictions...", flush=True)
    for t0 in pending_bars:
        result = _evaluate_one_point(mat, t0, hourly, daily, closes, df_1h, scheme, symbol_lower)

        # pure_pred_move = timesfm_pure_pred * base_price (与 A2-P1 相同)
        pure_pred_move = result["pure_pred_move"]

        # lgbm_residual_pred (LGBM 预测的是残差收益率)
        lgbm_residual_pred = lgbm_preds.get(t0, 0.0)

        # stacked_pred_return = timesfm_pure_pred + lgbm_residual_pred
        row = mat[mat["bar_idx"] == t0]
        if row.empty:
            timesfm_pure_pred = 0.0
        else:
            timesfm_pure_pred = float(row["timesfm_pure_pred"].iloc[0])
        stacked_pred_return = stack_predictions(
            np.array([timesfm_pure_pred]), np.array([lgbm_residual_pred])
        )[0]

        base_price = result["base_price"]
        stacked_pred_move = stacked_pred_return * base_price
        lgbm_residual_pred_move = lgbm_residual_pred * base_price

        # scheme_pred_move (与 A2-P1 相同)
        scheme_pred_move = result["scheme_pred_move"]
        scheme_ok = result["scheme_ok"]
        scheme_error = result["scheme_error"]

        record = {
            "bar_idx": t0,
            "pure_pred_move": pure_pred_move,
            "scheme_pred_move": scheme_pred_move,
            "stacked_pred_move": stacked_pred_move,
            "lgbm_residual_pred_move": lgbm_residual_pred_move,
            "actual_move": result["actual_move"],
            "base_price": base_price,
            "atr": result["atr"],
            "run_id": run_id,
            "symbol": symbol_upper,
            "version": version,
            "seed": seed,
            "scheme_ok": scheme_ok,
            "scheme_error": scheme_error,
        }
        append_unique_record(jsonl_path, record)

    print(f"[Worker {symbol_upper}] completed {len(pending_bars)} points, wrote to {jsonl_path}", flush=True)


def main():
    p = argparse.ArgumentParser(description="A2-P2 Worker: 残差训练 + 堆叠预测")
    p.add_argument("symbol", help="品种代码 (如 ss, rb, i)")
    p.add_argument("--run-id", default="a2-p2",
                   help="运行 ID (default: a2-p2)")
    p.add_argument("--dense-step", type=int, default=24, help="dense 矩阵步长 (default: 24)")
    p.add_argument("--refit-every", type=int, default=10, help="LGBM 重训间隔 (default: 10)")
    p.add_argument("--dry-run", action="store_true", help="干跑模式: 只打印 pending bars, 不执行")
    args = p.parse_args()
    run_worker(args.symbol, args.dense_step, args.refit_every, args.dry_run, args.run_id)


if __name__ == "__main__":
    main()

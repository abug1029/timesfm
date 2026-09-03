"""A2-P1 Worker: 单品种 eval point 级别执行 + 细粒度断点续跑。

Usage:
    python scripts/a2_p1_worker.py ss [--run-id a2-p1.1] [--dense-step 24] [--refit-every 10] [--dry-run]

产出:
    reports/a2_p1.1_results/<symbol>.jsonl — 每行一个 eval point 的完整结果
    reports/a2_p1_features/<symbol>_dense_matrix.parquet — dense 矩阵缓存 (原子写入)
"""
from __future__ import annotations

import sys
import pathlib
import os
import json
import argparse
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from scripts.a2_p1_runtime import generate_eval_grid, exclusive_result_lock, append_unique_record, stable_symbol_seed, RunConfig

FM_ROOT = pathlib.Path(__file__).resolve().parent.parent


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
    返回 dict: {bar_idx, pure_pred_move, scheme_pred_move, lgbm_pred_move,
                actual_move, base_price, atr}
    """
    from config.backtest_config import HORIZON
    from cascade.features import _calc_atr

    # base_price = T0 时刻的 close
    base_price = float(closes[t0])

    # actual_move = closes[T0 + HORIZON] - closes[T0]
    actual_move = float(closes[t0 + HORIZON] - closes[t0])

    # ATR @ T0
    atr_arr = _calc_atr(df_1h.iloc[:t0 + 1])
    atr = float(atr_arr[-1]) if len(atr_arr) else 1.0

    # pure_pred_move: 从 dense matrix 读取 timesfm_pure_pred (收益率) * base_price
    row = mat[mat["bar_idx"] == t0]
    if row.empty:
        pure_pred_move = 0.0
    else:
        pure_return = float(row["timesfm_pure_pred"].iloc[0])
        pure_pred_move = pure_return * base_price

    # scheme_pred_move: HourlyModel.predict with scheme covariates
    scheme_pred_move = None
    scheme_ok = None  # 三种状态: None=未配置, True=成功, False=异常
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

    # lgbm_pred_move: 由调用方填充 (从 train_lgbm_walkforward 结果中)
    lgbm_pred_move = None  # 占位, 由主循环填充

    return {
        "bar_idx": t0,
        "pure_pred_move": pure_pred_move,
        "scheme_pred_move": scheme_pred_move,
        "scheme_ok": scheme_ok,
        "scheme_error": scheme_error,
        "lgbm_pred_move": lgbm_pred_move,
        "actual_move": actual_move,
        "base_price": base_price,
        "atr": atr,
    }


def run_worker(symbol: str, dense_step: int, refit_every: int, dry_run: bool = False, run_id: str = "a2-p1.1"):
    """Worker 主函数: 单品种 eval point 级别执行 + 细粒度续跑"""
    from data.data_store import DataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward
    from config.prediction_scheme import SCHEMES

    symbol_upper = symbol.upper()
    symbol_lower = symbol.lower()
    version = _get_git_version()

    # 固定随机种子 (每品种确定性, SHA256-based, 跨进程可复现)
    seed = stable_symbol_seed(symbol_upper)
    np.random.seed(seed)

    # 从 RunConfig 派生路径 (不再硬编码)
    config = RunConfig.for_run(run_id, [symbol_lower], FM_ROOT)
    results_dir = config.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = results_dir / f"{symbol_lower}.jsonl"

    # Step 1: 加载数据, 确定 eval grid
    with DataStore(symbol_lower) as store:
        df_1h = store.get_main_contract_1h(limit=100000)
    total_bars = len(df_1h)
    closes = df_1h["close_price"].values.astype(float)
    all_eval_bars = _generate_eval_grid(symbol_lower, total_bars)

    # 三级缓存路径 (dense_matrix + market + tsfm 断点续算)
    cache_path = f"reports/a2_p1_features/{symbol_lower}_dense_matrix.parquet"
    market_cache_path = f"reports/a2_p1_features/{symbol_lower}_market.parquet"
    tsfm_resume_path = f"reports/a2_p1_features/{symbol_lower}_tsfm.jsonl"
    pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

    # Step 2: 检查已完成 (细粒度续跑)
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

    # Step 3+: 获取排他锁 (覆盖模型加载 → dense matrix → LGBM → JSONL 写入全生命周期)
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
    """Worker 核心逻辑 (必须在 exclusive_result_lock 持有期间调用)"""
    from data.data_store import DataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward
    from config.prediction_scheme import SCHEMES

    # Step 3: 加载模型 (一次性, 本进程共享)
    print(f"[Worker {symbol_upper}] loading models...", flush=True)
    import torch
    torch.set_float32_matmul_precision("high")
    import timesfm
    base = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    hourly = HourlyModel(shared_model=base)
    daily = DailyModel(shared_model=base)

    # Step 4: 构建 dense matrix (三级缓存 + 断点续算)
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

    # 添加 t0_close 列 (train_lgbm_walkforward 需要)
    mat["t0_close"] = [closes[t] if t < len(closes) else float("nan") for t in mat["bar_idx"]]

    # Step 5: LGBM walk-forward 训练 (传入 ALL eval bars, 确保训练窗口完整)
    print(f"[Worker {symbol_upper}] training LGBM on {len(mat)} dense rows, {len(all_eval_bars)} eval bars...", flush=True)
    lgbm_out = train_lgbm_walkforward(mat, all_eval_bars, refit_every=refit_every, random_state=seed)
    lgbm_preds = dict(zip(lgbm_out["bar_idx"], lgbm_out["pred_return"]))

    # Step 6: 逐 pending bar 评估并幂等追加 JSONL
    scheme = SCHEMES.get(symbol_lower)
    print(f"[Worker {symbol_upper}] evaluating {len(pending_bars)} points...", flush=True)
    for t0 in pending_bars:
        result = _evaluate_one_point(mat, t0, hourly, daily, closes, df_1h, scheme, symbol_lower)
        # 填充 lgbm_pred_move
        pred_return = lgbm_preds.get(t0, 0.0)
        result["lgbm_pred_move"] = pred_return * result["base_price"]
        # 添加元数据
        result["version"] = version
        result["seed"] = seed
        result["symbol"] = symbol_upper
        result["run_id"] = run_id
        # 幂等追加 (重复 bar_idx 且字段一致则跳过, 冲突则抛错)
        append_unique_record(jsonl_path, result)

    print(f"[Worker {symbol_upper}] completed {len(pending_bars)} points, wrote to {jsonl_path}", flush=True)


def main():
    p = argparse.ArgumentParser(description="A2-P1 Worker: 单品种 eval point 级别执行")
    p.add_argument("symbol", help="品种代码 (如 ss, rb, i)")
    p.add_argument("--run-id", default="a2-p1.1", choices=["a2-p1", "a2-p1.1"],
                   help="运行 ID (default: a2-p1.1)")
    p.add_argument("--dense-step", type=int, default=24, help="dense 矩阵步长 (default: 24)")
    p.add_argument("--refit-every", type=int, default=10, help="LGBM 重训间隔 (default: 10)")
    p.add_argument("--dry-run", action="store_true", help="干跑模式: 只打印 pending bars, 不执行")
    args = p.parse_args()
    run_worker(args.symbol, args.dense_step, args.refit_every, args.dry_run, args.run_id)


if __name__ == "__main__":
    main()

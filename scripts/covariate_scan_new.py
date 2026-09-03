"""
新协变量优化扫描 v3 (断点续传版)

每完成一个配置即保存到 checkpoint JSON，进程中断后可从断点恢复。

用法:
    python scripts/covariate_scan_new.py ur sr sp     # 新扫描
    python scripts/covariate_scan_new.py ur sr sp --resume  # 从断点恢复
    python scripts/covariate_scan_new.py ur sr sp --reset   # 清除 checkpoint 重新开始
"""

import sys
import os
import json
import time
import bisect
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PYTHONIOENCODING'] = 'utf-8'

import numpy as np
import pandas as pd
import torch

from config.backtest_config import (
    SYMBOLS as BT_SYMBOLS, SYMBOL_NAMES, CONTEXT_BARS, CONTEXT_DAYS,
    HORIZON, HORIZON_DAYS, STEP, MIN_EVAL_POINTS,
)
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from config.prediction_scheme import get_scheme
from data.data_store import BacktestDataStore


NEW_COVARIATES = ["ao_accel", "bb_squeeze", "ha_body", "reversal_shadow", "sar_dist"]
CHECKPOINT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "checkpoints")


def log(msg, end=None):
    if end is not None:
        print(msg, end=end, flush=True)
    else:
        print(msg, flush=True)


def checkpoint_path(symbols):
    """生成 checkpoint 文件路径"""
    key = '_'.join(sorted(symbols))
    return os.path.join(CHECKPOINT_DIR, f"covariate_scan_{key}.json")


def load_checkpoint(path):
    """加载 checkpoint，返回 (completed_symbols_dict, partial_current_symbol_dict_or_None)"""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("completed", {}), data.get("current")
    except Exception:
        return {}, None


def save_checkpoint(path, completed, current=None):
    """保存 checkpoint"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M'),
            "completed": completed,
            "current": current,
        }, f, indent=2, ensure_ascii=False)


def run_backtest(symbol, cov_type, cov_combo, daily_model, hourly_model, verbose=False):
    """单品种单配置 walk-forward 回测"""
    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()

    if all_1h.empty or len(all_1h) < CONTEXT_BARS + HORIZON + STEP:
        return None, "1H data insufficient"

    total = len(all_1h)
    eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))

    if not daily_df.empty:
        daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
        min_daily_req = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
        eval_indices = [
            idx for idx in eval_indices
            if bisect.bisect_right(daily_dates, str(all_1h["dt"].iloc[idx])[:10]) >= min_daily_req
        ]

    if len(eval_indices) < MIN_EVAL_POINTS:
        return None, f"too few eval points ({len(eval_indices)})"

    n_ok = 0
    n_fail = 0
    correct = 0
    errors = []
    last_error = None

    for i, idx in enumerate(eval_indices):
        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        dt = bar_ts.strftime("%Y-%m-%d")
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx+1:idx+1+HORIZON].values.astype(np.float64)

        if i > 0 and i % 10 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            daily_result = daily_model.predict(
                symbol, bt_store,
                context_days=CONTEXT_DAYS, horizon_days=HORIZON_DAYS
            )

            if cov_combo:
                hourly_result = hourly_model.predict(
                    symbol, bt_store, daily_result,
                    horizon=HORIZON, visualize=False,
                    covariate_types=cov_combo,
                    verbose=False, skip_validation=True
                )
            else:
                hourly_result = hourly_model.predict(
                    symbol, bt_store, daily_result,
                    horizon=HORIZON, visualize=False,
                    covariate_type=cov_type,
                    verbose=False, skip_validation=True
                )

            pred = hourly_result.point_forecast
            delta_pred = pred[-1] - base
            delta_real = real[-1] - base

            if delta_real != 0:
                n_ok += 1
                if np.sign(delta_pred) == np.sign(delta_real):
                    correct += 1
                safe_real = np.where(real == 0, 1e-8, np.abs(real))
                mape_val = float(np.mean(np.abs(pred - real) / safe_real) * 100)
                errors.append(mape_val)

        except Exception as e:
            n_fail += 1
            last_error = str(e)
            if verbose:
                log(f"    [ERR] {dt}: {e}")

    if n_ok < MIN_EVAL_POINTS:
        return None, f"too few successes ({n_ok}), last_err={last_error}"

    return {
        "dir_acc": round(correct / n_ok, 4),
        "mape": round(float(np.mean(errors)), 2),
        "n_points": n_ok,
        "n_fail": n_fail,
    }, None


def make_configs(baseline_cov, baseline_combo):
    """生成所有配置列表: (label, cov_type, cov_combo, step_label)"""
    configs = []
    bl = '+'.join(baseline_combo) if baseline_combo else baseline_cov

    # 基线
    configs.append((bl, baseline_cov, baseline_combo, "baseline"))

    # 5 个单协变量
    for cov in NEW_COVARIATES:
        configs.append((cov, cov, None, cov))

    # 5 个组合
    base_list = baseline_combo if baseline_combo else [baseline_cov]
    for cov in NEW_COVARIATES:
        combo = base_list + [cov]
        label = '+'.join(combo)
        configs.append((label, None, combo, f"combo_{cov}"))

    return configs


def scan_symbol(symbol, daily_model, hourly_model, baseline_cov, baseline_combo,
                ckpt_path, completed, checkpoint_current):
    """带断点续传的品种扫描"""
    baseline_label = '+'.join(baseline_combo) if baseline_combo else baseline_cov
    log(f"\n{'='*60}")
    log(f"  {symbol.upper()} ({SYMBOL_NAMES.get(symbol, '?')})")
    log(f"  baseline: {baseline_label}")
    log(f"{'='*60}")

    # 检查是否有该品种的部分进度
    result = checkpoint_current if (checkpoint_current and checkpoint_current.get("symbol") == symbol) else {}
    if "symbol" not in result:
        result = {"symbol": symbol, "baseline_label": baseline_label, "configs": {}}

    configs = make_configs(baseline_cov, baseline_combo)
    total = len(configs)

    for step_i, (label, cov_type, cov_combo, step_key) in enumerate(configs):
        # 跳过已完成的
        if step_key in result.get("configs", {}):
            r = result["configs"][step_key]
            log(f"  [{step_i+1}/{total}] {label}... [checkpoint] DA={r.get('dir_acc', 0):.1%}")
            continue

        log(f"  [{step_i+1}/{total}] {label}...", end="")
        t0 = time.time()
        r, err = run_backtest(symbol, cov_type, cov_combo, daily_model, hourly_model, verbose=True)
        dt = time.time() - t0

        if r:
            # 计算 delta
            baseline_r = result.get("configs", {}).get("baseline")
            baseline_da = baseline_r["dir_acc"] if baseline_r else 0
            delta = r["dir_acc"] - baseline_da
            tag = "[+]" if delta > 0.02 else ("[~]" if delta > 0 else "[-]")
            result.setdefault("configs", {})[step_key] = r
            log(f" OK ({dt:.0f}s) DA={r['dir_acc']:.1%} MAPE={r['mape']:.2f}% {tag} {delta:+.1%}")
        else:
            result.setdefault("configs", {})[step_key] = {"error": err}
            log(f" SKIP ({dt:.0f}s): {err}")

        # 每步保存 checkpoint
        save_checkpoint(ckpt_path, completed, result)

    return result


def print_summary(all_results):
    """打印汇总"""
    log(f"\n{'='*70}")
    log(f"  SUMMARY | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"{'='*70}")
    log(f"{'SYM':<5} {'BASELINE':>22} {'BASE_DA':>8} {'BEST':>30} {'BEST_DA':>8} {'DELTA':>8}")
    log(f"{'-'*70}")

    upgrades = []
    for r in all_results:
        sym = r["symbol"]
        baseline_label = r["baseline_label"]
        baseline_cfg = r["configs"].get("baseline", {})
        ba = baseline_cfg.get("dir_acc", 0) if baseline_cfg else 0

        best_key, best_da = "baseline", ba
        for k, v in r.get("configs", {}).items():
            if isinstance(v, dict) and "dir_acc" in v and v["dir_acc"] > best_da:
                best_key = k
                best_da = v["dir_acc"]

        best_label = best_key if best_key != "baseline" else baseline_label
        delta = best_da - ba
        tag = " <--" if delta > 0.02 else ""
        log(f"{sym.upper():<5} {baseline_label:>22} {ba:>7.1%} {best_label:>30} {best_da:>7.1%} {delta:>+7.1%}{tag}")
        if delta > 0.02:
            upgrades.append({"symbol": sym, "from": baseline_label, "to": best_label, "delta": delta})

    log(f"\nUpgrades ({len(upgrades)}):")
    for u in upgrades:
        log(f"  {u['symbol'].upper()}: {u['from']} -> {u['to']} (DA +{u['delta']:.1%})")
    if not upgrades:
        log("  No significant improvement found.")
    return upgrades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    parser.add_argument("--resume", action="store_true", help="从 checkpoint 恢复")
    parser.add_argument("--reset", action="store_true", help="清除 checkpoint 重新开始")
    args = parser.parse_args()

    symbols = [s.lower() for s in args.symbols] if args.symbols else BT_SYMBOLS
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    ckpt_path = checkpoint_path(symbols)
    completed = {}
    checkpoint_current = None

    if args.resume:
        completed, checkpoint_current = load_checkpoint(ckpt_path)
        if completed or checkpoint_current:
            log(f"[resume] 从 checkpoint 恢复: {ckpt_path}")
            if completed:
                log(f"  已完成: {', '.join(completed.keys())}")
            if checkpoint_current:
                cfg_count = len(checkpoint_current.get("configs", {}))
                log(f"  当前: {checkpoint_current.get('symbol', '?')} ({cfg_count}/11 configs)")
        else:
            log(f"[resume] 无 checkpoint，开始新扫描")

    if args.reset and os.path.exists(ckpt_path):
        os.remove(ckpt_path)
        log(f"[reset] 已删除 checkpoint: {ckpt_path}")

    log(f"=== covariate scan v3 | {ts} | symbols={','.join(s.upper() for s in symbols)} ===")
    log(f"new covariates: {NEW_COVARIATES}")
    log(f"checkpoint: {ckpt_path}")

    log("loading TimesFM...")
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    log("model loaded")

    all_results = []

    # 添加已完成的品种
    for sym, r in completed.items():
        if sym in symbols:
            all_results.append(r)
            log(f"\n  {sym.upper()}: [从 checkpoint 加载]")

    for symbol in symbols:
        if symbol in completed:
            continue  # 跳过已完成

        scheme = get_scheme(symbol)
        if scheme and scheme.covariate_types and len(scheme.covariate_types) > 1:
            baseline_cov, baseline_combo = None, scheme.covariate_types
        elif scheme:
            baseline_cov, baseline_combo = scheme.covariate_type, None
        else:
            baseline_cov, baseline_combo = "ccl", None

        r = scan_symbol(symbol, daily_model, hourly_model, baseline_cov, baseline_combo,
                        ckpt_path, completed, checkpoint_current)

        # 完成一个品种后移到 completed
        completed[symbol] = r
        save_checkpoint(ckpt_path, completed, None)
        all_results.append(r)

    # 汇总
    upgrades = print_summary(all_results)

    # 保存最终结果
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
    os.makedirs(out_dir, exist_ok=True)
    ts_f = datetime.now().strftime('%Y%m%d_%H%M')
    out_path = os.path.join(out_dir, f"covariate_scan_v3_{ts_f}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"ts": ts, "covariates": NEW_COVARIATES,
                    "upgrades": upgrades, "results": all_results}, f, indent=2, ensure_ascii=False)
    log(f"\nsaved: {out_path}")

    # 清理 checkpoint
    if os.path.exists(ckpt_path):
        os.remove(ckpt_path)
        log(f"checkpoint cleaned: {ckpt_path}")


if __name__ == "__main__":
    main()

"""
月度 1H 级联预测回测

标准化月度流程:
1. 读取 config/backtest_config.py 中的品种列表和参数
2. 对所有品种运行 walk-forward 回测
3. 计算汇总指标，自动分类品种
4. 与上月结果对比 (如有历史记录)
5. 生成标准化报告，保存到 reports/monthly_backtest/
6. 更新 history.json

用法:
    python scripts/monthly_backtest.py              # 全品种
    python scripts/monthly_backtest.py ss rb sr     # 指定品种
    python scripts/monthly_backtest.py --summary     # 仅打印历史对比

波动率熔断器（Vol Gating）对比回测请用:
    python scripts/backtest_vol_gating.py --thr 0.55
    python scripts/cascade_predict.py sr --vol-filter
（默认 OFF；不是趋势路由）
"""

import sys
import os
import json
import pickle
import json as _json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PYTHONIOENCODING'] = 'utf-8'

import numpy as np
import pandas as pd
import torch

from config.backtest_config import (
    SYMBOLS, SYMBOL_NAMES, CONTEXT_BARS, CONTEXT_DAYS,
    HORIZON, HORIZON_DAYS, STEP, MIN_EVAL_POINTS, MIN_1H_BARS,
    THRESHOLDS, CATEGORY_LABELS, BACKTEST_DIR, HISTORY_FILE,
    ensure_dirs, TICK_SIZES, SLIPPAGE_TICKS,
)

# 补充 threshold 别名
THRESHOLDS["min_eval_points"] = MIN_EVAL_POINTS
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from cascade.evaluation_metrics import metrics_from_backtest_points
from cascade.signal_contract import position_from_forecast
from config.prediction_scheme import get_scheme
from data.data_store import BacktestDataStore


# ─────────────────────────────────────────────────────────
# 回测引擎
# ─────────────────────────────────────────────────────────

# Checkpoint JSONL 必须含 summarize / metrics_from_backtest_points 所需字段
_CHECKPOINT_POINT_KEYS = (
    "cutoff", "base", "pred_end", "real_end",
    "delta_pred", "delta_real", "dir_ok", "dir12_ok",
    "mae", "mape", "mae_h1", "mae_h2", "coverage", "pnl", "real_range",
)

_DAILY_CACHE_VER = "v2"  # v2 = dates 为 tz-naive ISO 列表, 不再 pickle DailyResult


def _weight_shards(weights_dir):
    import glob as _glob
    base = weights_dir or os.environ.get("TIMESFM_WEIGHTS_DIR") or os.path.expanduser(
        "~/.cache/huggingface/hub/models--google--timesfm-2.5-200m-pytorch/snapshots")
    snaps = sorted(_glob.glob(os.path.join(base, "*", "*.safetensors")))
    if not snaps:
        snaps = sorted(_glob.glob(os.path.join(base, "*.safetensors")))
    if not snaps:
        raise RuntimeError("daily cache: model weights not found for fingerprint (set TIMESFM_WEIGHTS_DIR)")
    return snaps


def _model_fingerprint(cache_dir, weights_dir=None):
    import hashlib
    os.makedirs(cache_dir, exist_ok=True)
    shards = _weight_shards(weights_dir)
    sig = [[os.path.abspath(p), os.path.getsize(p), int(os.path.getmtime(p))] for p in shards]
    meta = os.path.join(cache_dir, ".model_fp.json")
    if os.path.exists(meta):
        try:
            old = _json.load(open(meta, encoding="utf-8"))
            if old.get("sig") == sig and old.get("fp"):
                return old["fp"]
        except Exception:
            pass
    h = hashlib.sha256()
    for sp in shards:
        with open(sp, "rb") as f:
            h.update(f.read(1 << 24))
    fp = h.hexdigest()[:12]
    with open(meta, "w", encoding="utf-8") as f:
        _json.dump({"fp": fp, "sig": sig}, f)
    return fp


def _daily_cache_path(cache_dir, symbol, cutoff, win, fp):
    import hashlib as _hl
    key = _hl.sha256("|".join([_DAILY_CACHE_VER, symbol, cutoff, win, fp]).encode()).hexdigest()
    return os.path.join(cache_dir, f"daily_{symbol}_{key[:16]}.pkl")


def _result_to_payload(result):
    dates = getattr(result, "historical_dates", None)
    iso = None if dates is None else [str(pd.Timestamp(d))[:10] for d in dates]
    return {
        "symbol": result.symbol,
        "forecast": np.asarray(result.forecast),
        "horizon_slope": float(result.horizon_slope),
        "historical_closes": np.asarray(result.historical_closes),
        "historical_dates": iso,
    }


def _payload_to_result(payload):
    from cascade.daily_model import DailyResult
    dates = payload.get("historical_dates")
    idx = pd.DatetimeIndex(dates) if dates is not None else None
    if idx is not None and idx.tz is not None:
        idx = idx.tz_localize(None)
    return DailyResult(
        symbol=payload["symbol"], forecast=payload["forecast"],
        horizon_slope=payload["horizon_slope"],
        historical_closes=payload["historical_closes"],
        historical_dates=idx,
    )


def _load_daily_cache(cache_dir, symbol, cutoff, win, fp):
    p = _daily_cache_path(cache_dir, symbol, cutoff, win, fp)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            obj = pickle.load(f)
        if isinstance(obj, dict) and "forecast" in obj:
            return _payload_to_result(obj)
        os.remove(p)  # 旧 v1 DailyResult pickle, 丢弃重算
        return None
    except Exception:
        try:
            os.remove(p)
        except OSError:
            pass
        return None


def _save_daily_cache(cache_dir, symbol, cutoff, win, fp, result):
    p = _daily_cache_path(cache_dir, symbol, cutoff, win, fp)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(_result_to_payload(result), f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, p)


def _daily_predict_cached(daily_model, symbol, cutoff, context_days, horizon_days, cache_dir, store):
    if not cache_dir:
        return daily_model.predict(symbol, store, context_days=context_days, horizon_days=horizon_days)
    win = f"{context_days}x{horizon_days}"
    fp = _model_fingerprint(cache_dir)
    hit = _load_daily_cache(cache_dir, symbol, cutoff, win, fp)
    if hit is not None:
        return hit
    result = daily_model.predict(symbol, store, context_days=context_days, horizon_days=horizon_days)
    _save_daily_cache(cache_dir, symbol, cutoff, win, fp, result)
    return result


def run_symbol_backtest(symbol, daily_model, hourly_model,
                        cov_override=None, cov_combo=None, clip_gap=None,
                        cache_interval=10, max_points=None,
                        completed=None, checkpoint_fp=None,
                        resumed_points=None,
                        signal_override=None,
                        fill_strategy="default",
                        daily_cache_dir=None):
    """单品种回测，返回汇总指标和逐点详情

    Args:
        cov_override: 覆盖协变量类型 (单协变量模式)
        cov_combo: 协变量组合列表 (多协变量模式), e.g. ["rsi_state", "oi"]
                   优先级高于 cov_override
        clip_gap: 极值截断比例 (None 表示不截断). 对 delta_real 截断到 ±clip_gap*base,
                  用于 LH 等 gap 频发品种的 EV/PF 稳定性评估. MAE/MAPE/dir_ok 不受影响.
                  dir_ok 始终用 raw delta_real；PF/EV 用 clipped（clip_gap 设计如此）。
        cache_interval: 每 N 评估点 clear GPU cache (默认 10, 与原硬编码一致)
        max_points: 每品种最多跑 N 个评估点 (None=不限), 用于 OOM 排查
        completed: set of (symbol, idx) 已完成点 (--resume 时跳过); None=无 resume
        checkpoint_fp: 已打开的 JSONL 追加文件句柄 (mode="a"); None=不写 checkpoint
        resumed_points: dict (symbol, idx) -> full point dict; resume 时合并进 points
        fill_strategy: Horizon 填充策略, "default" (常数) 或 "decay" (12-bar 半衰期衰减)
        daily_cache_dir: 日线预测 pickle 缓存目录 (None=不缓存)
    """
    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)

    # 检查日线数据可用性 (daily model 需要 CONTEXT_DAYS 天)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()

    if all_1h.empty or len(all_1h) < CONTEXT_BARS + HORIZON:
        return None

    # 日线充足性过滤见下方 min_daily_required + bisect（不再使用未接线的 min_eval_date 日历近似）

    total = len(all_1h)
    contract = all_1h["contract_code"].iloc[-1]
    eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))

    # 减量排查: 截断评估点上限 (不破坏后续过滤逻辑)
    if max_points is not None:
        eval_indices = eval_indices[:max_points]
    sym_lower = symbol.lower()

    # 过滤: 只保留日线数据足够的评估点
    # 模型实际需要 horizon_days(22) 天预测, context 略少于 CONTEXT_DAYS 也可用
    min_daily_required = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
    if not daily_df.empty:
        import bisect
        daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
        eval_indices = [
            idx for idx in eval_indices
            if bisect.bisect_right(daily_dates, str(all_1h["dt"].iloc[idx])[:10]) >= min_daily_required
        ]

    if not eval_indices:
        return None

    # 自动检测协变量模式 (优先级: 显式参数 > scheme.covariate_types > scheme.covariate_type > ccl)
    effective_combo = cov_combo  # --combo 显式指定
    effective_single = cov_override  # --cov-override 显式指定
    if not effective_combo and not effective_single:
        _scheme = get_scheme(symbol)
        if _scheme and _scheme.covariate_types and len(_scheme.covariate_types) > 1:
            effective_combo = _scheme.covariate_types
        elif _scheme:
            effective_single = _scheme.covariate_type
        else:
            effective_single = "ccl"
    _cov_label = '+'.join(effective_combo) if effective_combo else effective_single
    print(f"  [cov={_cov_label}]")

    points = []
    for i, idx in enumerate(eval_indices):
        # resume: 合并已完成点（完整 payload）后再跳过重算
        if completed is not None and (sym_lower, idx) in completed:
            if resumed_points is not None and (sym_lower, idx) in resumed_points:
                pt = dict(resumed_points[(sym_lower, idx)])
                pt.pop("symbol", None)
                pt.pop("idx", None)
                points.append(pt)
            continue
        # bar-exact cutoff (full timestamp) — 禁止仅截日期造成同日 1H lookahead
        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        dt = bar_ts.strftime("%Y-%m-%d")  # 报告/cutoff 展示用日历日
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx+1:idx+1+HORIZON].values.astype(np.float64)

        # Clear GPU cache every cache_interval eval points to prevent memory accumulation
        if i > 0 and i % cache_interval == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        if i < 3 or i % 50 == 0:
            print(f"    [{i+1}/{len(eval_indices)}] {cutoff}...", end="", flush=True)

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            if i < 3:
                import time; _t0 = time.time()
            if effective_combo:
                # 多协变量组合模式
                daily_result = _daily_predict_cached(
                    daily_model, symbol, cutoff, CONTEXT_DAYS, HORIZON_DAYS,
                    daily_cache_dir, bt_store)
                if i < 3:
                    _t1 = time.time()
                    print(f" daily={_t1-_t0:.1f}s", end="", flush=True)
                hourly_result = hourly_model.predict(symbol, bt_store, daily_result,
                                                     horizon=HORIZON, visualize=False,
                                                     covariate_types=effective_combo,
                                                     verbose=False,
                                                     fill_strategy=fill_strategy)
                if i < 3:
                    _t2 = time.time()
                    print(f" hourly={_t2-_t1:.1f}s", end="", flush=True)
            else:
                # 单协变量模式
                daily_result = _daily_predict_cached(
                    daily_model, symbol, cutoff, CONTEXT_DAYS, HORIZON_DAYS,
                    daily_cache_dir, bt_store)
                if i < 3:
                    _t1 = time.time()
                    print(f" daily={_t1-_t0:.1f}s", end="", flush=True)
                hourly_result = hourly_model.predict(symbol, bt_store, daily_result,
                                                     horizon=HORIZON, visualize=False,
                                                     covariate_type=effective_single,
                                                     verbose=False,
                                                     fill_strategy=fill_strategy)
                if i < 3:
                    _t2 = time.time()
                    print(f" hourly={_t2-_t1:.1f}s", end="", flush=True)
            pred = hourly_result.point_forecast
            quant = hourly_result.quantile_forecast
            if i < 3:
                print(f" pred_shape={pred.shape}", end="", flush=True)

            # Live-aligned signal: signal_weight / short_horizon (not endpoint-only)
            _scheme = get_scheme(symbol)
            if signal_override:
                import dataclasses
                _scheme = dataclasses.replace(_scheme, **signal_override)
            _sig = position_from_forecast(
                pred, base, scheme=_scheme,
                daily_slope=getattr(daily_result, "horizon_slope", None),
            )
            delta_pred = float(_sig["delta_pred"])
            position_sign = float(_sig["position_sign"])
            delta_real_raw = real[-1] - base
            # Apply gap clipping for EV/PF stability (LH-style)
            # NOTE: dir_ok uses raw moves; PF/EV use clipped delta_real (by design)
            if clip_gap is not None:
                max_move = clip_gap * base
                delta_real = float(np.clip(delta_real_raw, -max_move, max_move))
            else:
                delta_real = delta_real_raw
            dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real_raw)) if delta_real_raw != 0 else True
            if i < 3:
                print(f" dir_ok", end="", flush=True)
            mae = float(np.mean(np.abs(pred - real)))
            safe_real = np.where(real == 0, 1e-8, np.abs(real))
            mape = float(np.mean(np.abs(pred - real) / safe_real) * 100)
            if i < 3:
                print(f" mae", end="", flush=True)

            # PnL: position_sign * delta_real (scheme-weighted direction)
            pnl = float(position_sign * delta_real) if position_sign != 0 else 0.0

            half = HORIZON // 2
            mae_h1 = float(np.mean(np.abs(pred[:half] - real[:half])))
            mae_h2 = float(np.mean(np.abs(pred[half:] - real[half:])))
            if i < 3:
                print(f" mae_h", end="", flush=True)

            # T+12 direction: if short_horizon_only, align with weighted half-path
            if _sig.get("short_horizon_only"):
                d12_pred = float(np.mean(pred[:half]) - base)
            else:
                d12_pred = pred[half-1] - base
            d12_real = real[half-1] - base
            dir12_ok = bool(np.sign(d12_pred) == np.sign(d12_real)) if d12_real != 0 else True

            cov = 0
            if quant is not None and quant.ndim == 2 and quant.shape[1] >= 10:
                for t in range(HORIZON):
                    if quant[t, 1] <= real[t] <= quant[t, 9]:
                        cov += 1
            if i < 3:
                print(f" cov={cov}", end="", flush=True)

            point = {
                "cutoff": dt, "base": base,
                "pred_end": float(pred[-1]), "real_end": float(real[-1]),
                "delta_pred": float(delta_pred), "delta_real": float(delta_real),
                "dir_ok": dir_ok, "dir12_ok": dir12_ok,
                "mae": mae, "mape": mape,
                "mae_h1": mae_h1, "mae_h2": mae_h2,
                "coverage": cov,
                "pnl": pnl,
                "real_range": float(real.max() - real.min()),
            }
            points.append(point)
            # ── checkpoint: 完整 point 字段 (resume 可重建 summarize) ──
            if checkpoint_fp is not None:
                import json as _json
                rec = {"symbol": sym_lower, "idx": int(idx)}
                for k in _CHECKPOINT_POINT_KEYS:
                    rec[k] = point[k]
                # path MAE% for diagnostics (fixed: mean |pred-real|/base, not real[-1] broadcast)
                rec["mae_pct"] = round(float(np.mean(np.abs(pred - real)) / base * 100), 4) if base else 0.0
                checkpoint_fp.write(_json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                checkpoint_fp.flush()  # flush 立即落盘, kill 时不丢当前已写行
            if i < 3 or i % 50 == 0:
                print(f" done")
        except Exception as e:
            points.append({"cutoff": dt, "error": str(e)})
            if checkpoint_fp is not None:
                import json as _json
                checkpoint_fp.write(_json.dumps({
                    "symbol": sym_lower, "idx": int(idx), "error": str(e), "cutoff": dt,
                }, ensure_ascii=False) + "\n")
                checkpoint_fp.flush()
            if i < 3 or i % 50 == 0:
                print(f" ERROR: {e}")
            elif i % 10 == 0:
                print(f"    [{i+1}/{len(eval_indices)}] {dt} ERROR: {e}", flush=True)

    return {
        "symbol": symbol.upper(),
        "name": SYMBOL_NAMES.get(symbol, symbol),
        "contract": contract,
        "total_bars": total,
        "eval_count": len(eval_indices),
        "points": points,
    }


# ─────────────────────────────────────────────────────────
# 指标汇总
# ─────────────────────────────────────────────────────────

def summarize(data):
    """从逐点数据计算汇总指标。

    净 PF / EV / MaxDD / DirAcc 统一走 cascade.evaluation_metrics（全项目唯一秤）。
    """
    ok = [p for p in data["points"] if "error" not in p]
    if not ok:
        return None

    n = len(ok)
    dir_acc_legacy = np.mean([p["dir_ok"] for p in ok])
    dir12_acc = np.mean([p["dir12_ok"] for p in ok])
    mae = np.mean([p["mae"] for p in ok])
    mape = np.mean([p["mape"] for p in ok])
    mae_h1 = np.mean([p["mae_h1"] for p in ok])
    mae_h2 = np.mean([p["mae_h2"] for p in ok])
    decay = mae_h2 / mae_h1 if mae_h1 > 0 else 1.0
    coverage = np.mean([p["coverage"] / HORIZON for p in ok])
    vol_pct = np.mean([p["real_range"] for p in ok]) / np.mean([p["base"] for p in ok]) * 100

    symbol = data["symbol"].lower()
    tick = TICK_SIZES.get(symbol, 1.0)
    net = metrics_from_backtest_points(
        ok, tick_size=tick, slippage_ticks=SLIPPAGE_TICKS,
    )

    avg_abs_real = float(np.mean([abs(p["delta_real"]) for p in ok]))
    ev_gross = float(net["EV_gross"])
    ev_ratio_gross = (ev_gross / avg_abs_real) if avg_abs_real > 0 else 0.0

    return {
        "symbol": data["symbol"],
        "name": data["name"],
        "contract": data["contract"],
        "bars": data["total_bars"],
        "n": n,
        "mae": round(mae, 1),
        "mape": round(mape, 2),
        # DirAcc: 优先用统一秤；保留逐点 dir_ok 作对照
        "dir_acc": round(float(net["DirAcc"]), 3),
        "dir_acc_points": round(float(dir_acc_legacy), 3),
        "dir12_acc": round(dir12_acc, 3),
        "mae_h1": round(mae_h1, 1),
        "mae_h2": round(mae_h2, 1),
        "decay": round(decay, 2),
        "coverage": round(coverage, 3),
        "vol_pct": round(vol_pct, 2),
        # 净指标（含滑点）— evaluation_metrics 唯一来源
        "ev": round(float(net["EV"]), 2),
        "ev_ratio": round(float(net["EV_ratio"]), 3),
        "profit_factor": float(net["PF"]),
        "max_dd": float(net["MaxDD"]),
        "win_rate": round(float(net["WinRate"]), 3),
        "slippage_cost": float(net["slippage_cost"]),
        # 零摩擦对照
        "ev_gross": round(ev_gross, 2),
        "ev_ratio_gross": round(ev_ratio_gross, 3),
        "pf_gross": float(net["PF_gross"]),
        "avg_win": round(float(net["avg_win"]), 2),
        "avg_loss": round(float(net["avg_loss"]), 2),
    }


# ─────────────────────────────────────────────────────────
# 品种分类
# ─────────────────────────────────────────────────────────

def classify(summary_list):
    """按指标自动分类品种

    分类优先级:
    1. 数据不足 (n < min_eval_points)
    2. 高误差 (MAPE > mape_bad)
    3. 趋势型 (DirAcc≥60% 且 decay≤1.4x)
    4. 短线型 (Dir12 >> DirAcc+10%)
    5. 震荡型 (DirAcc < 45%)
    6. 稳定型 (MAPE < 2% 或 DirAcc ≥ 55%)
    7. 其他 → 震荡型
    """
    th = THRESHOLDS
    cats = {k: [] for k in CATEGORY_LABELS}

    for s in summary_list:
        sym = s["symbol"]
        if s["n"] < th["min_eval_points"]:
            cats["insufficient"].append(sym)
        elif s["mape"] > th["mape_bad"]:
            cats["high_error"].append(sym)
        elif s["dir_acc"] >= th["dir_acc_trend"] and s["decay"] <= th["decay_good"]:
            cats["trend"].append(sym)
        elif s["dir12_acc"] > s["dir_acc"] + 0.10:
            cats["short_range"].append(sym)
        elif s["dir_acc"] < th["dir_acc_oscillation"]:
            cats["oscillation"].append(sym)
        elif s["mape"] <= th["mape_good"] or s["dir_acc"] >= 0.55:
            # 稳定型: 精度好 或 方向准确率较高 (即使 MAPE 偏高或 decay 偏大)
            cats["stable"].append(sym)
        else:
            cats["oscillation"].append(sym)

    return cats


# ─────────────────────────────────────────────────────────
# 历史对比
# ─────────────────────────────────────────────────────────

def load_history():
    """加载历史回测结果"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history):
    """保存历史回测结果"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_history(summary_list, categories):
    """将本月结果写入历史 (增量合并: 同品种覆盖, 新品种追加)"""
    history = load_history()
    month_key = datetime.now().strftime("%Y-%m")

    if month_key in history:
        # 增量合并: 按 symbol 去重, 新结果覆盖旧结果
        existing = {s["symbol"]: s for s in history[month_key].get("summary", [])}
        for s in summary_list:
            existing[s["symbol"]] = s
        merged = list(existing.values())
    else:
        merged = summary_list

    # 重新分类 (基于合并后的完整数据)
    merged_cats = classify(merged)

    history[month_key] = {
        "summary": merged,
        "categories": {k: v for k, v in merged_cats.items() if v},
    }
    save_history(history)
    return history


def compare_with_last_month(current_summary):
    """与上月对比"""
    history = load_history()
    months = sorted(history.keys())
    if len(months) < 2:
        return None

    last_month = months[-1]
    last_data = history[last_month]
    last_summary = {s["symbol"]: s for s in last_data["summary"]}

    diffs = []
    for s in current_summary:
        sym = s["symbol"]
        if sym in last_summary:
            prev = last_summary[sym]
            diffs.append({
                "symbol": sym,
                "name": s["name"],
                "dir_acc_delta": round(s["dir_acc"] - prev["dir_acc"], 3),
                "mape_delta": round(s["mape"] - prev["mape"], 2),
                "decay_delta": round(s["decay"] - prev["decay"], 2),
            })
    return {"last_month": last_month, "diffs": diffs}


# ─────────────────────────────────────────────────────────
# 报告生成
# ─────────────────────────────────────────────────────────

def generate_report(summary_list, categories, comparison):
    """生成标准化月度报告"""
    now = datetime.now()
    lines = [
        f"# 1H 级联预测月度回测报告 — {now.strftime('%Y年%m月')}",
        "",
        f"**回测日期**: {now.strftime('%Y-%m-%d')}",
        f"**模型**: TimesFM 2.5 级联 (日线→1H XReg)",
        f"**参数**: context={CONTEXT_BARS}bars, horizon={HORIZON}bars, step={STEP}bars, daily={CONTEXT_DAYS}d→{HORIZON_DAYS}d",
        "",
        "---",
        "",
        "## 一、汇总排名",
        "",
        "| # | 品种 | 名称 | 评估点 | MAPE | DirAcc | DirAcc12 | 衰减 | EV_ratio | PF | WR | Coverage | 波动% |",
        "|--:|------|------|------:|-----:|:------:|:--------:|:----:|:--------:|:--:|:--:|:--------:|------:|",
    ]

    ranked = sorted(summary_list, key=lambda x: x["dir_acc"], reverse=True)
    for i, s in enumerate(ranked):
        pf_str = f"{s['profit_factor']:.1f}" if s['profit_factor'] < 99.99 else "99.99+"
        wr_str = f"{s['win_rate']:.0%}" if 'win_rate' in s else "-"
        lines.append(
            f"| {i+1} | {s['symbol']} | {s['name']} | {s['n']} | "
            f"{s['mape']:.2f}% | {s['dir_acc']:.0%} | {s['dir12_acc']:.0%} | "
            f"{s['decay']:.2f}x | {s['ev_ratio']:+.3f} | {pf_str} | {wr_str} | "
            f"{s['coverage']:.0%} | {s['vol_pct']:.2f}% |"
        )

    # 分类
    lines.extend(["", "## 二、品种分类", ""])
    for cat_key, label in CATEGORY_LABELS.items():
        syms = categories.get(cat_key, [])
        if syms:
            names = [f"{s}({SYMBOL_NAMES.get(s.lower(), '')})" for s in syms]
            lines.append(f"### {label}")
            lines.append(f"**品种**: {', '.join(names)}")
            lines.append("")

    # 月度对比
    if comparison:
        lines.extend([
            "", "## 三、月度对比 (vs {})".format(comparison["last_month"]), "",
            "| 品种 | 名称 | DirAcc变化 | MAPE变化 | 衰减变化 |",
            "|------|------|:---------:|:--------:|:--------:|",
        ])
        for d in sorted(comparison["diffs"], key=lambda x: x["dir_acc_delta"], reverse=True):
            def arrow(v, fmt=".0%"):
                if v > 0.01: return f"+{v:{fmt}} ↑"
                elif v < -0.01: return f"{v:{fmt}} ↓"
                else: return f"{v:{fmt}} →"
            lines.append(
                f"| {d['symbol']} | {d['name']} | "
                f"{arrow(d['dir_acc_delta'])} | "
                f"{arrow(d['mape_delta'], '.2f')} | "
                f"{arrow(d['decay_delta'], '.2f')} |"
            )

    # 稳定性分析
    lines.extend([
        "", "## 四、稳定性分析", "",
        "### 按方向准确率分层",
        "",
    ])
    tiers = [
        ("优秀 (≥60%)", [s for s in ranked if s["dir_acc"] >= 0.60]),
        ("良好 (50-60%)", [s for s in ranked if 0.50 <= s["dir_acc"] < 0.60]),
        ("及格 (45-50%)", [s for s in ranked if 0.45 <= s["dir_acc"] < 0.50]),
        ("不及格 (<45%)", [s for s in ranked if s["dir_acc"] < 0.45]),
    ]
    for label, group in tiers:
        if group:
            syms = ", ".join([s["symbol"] for s in group])
            avg_dir = np.mean([s["dir_acc"] for s in group])
            avg_mape = np.mean([s["mape"] for s in group])
            lines.append(f"- **{label}**: {syms} — 均 DirAcc={avg_dir:.0%}, 均 MAPE={avg_mape:.2f}%")

    lines.extend([
        "",
        "### 衰减比分布",
        "",
    ])
    decay_tiers = [
        ("低衰减 (<1.3x)", [s for s in ranked if s["decay"] < 1.30]),
        ("中衰减 (1.3-1.5x)", [s for s in ranked if 1.30 <= s["decay"] < 1.50]),
        ("高衰减 (>1.5x)", [s for s in ranked if s["decay"] >= 1.50]),
    ]
    for label, group in decay_tiers:
        if group:
            syms = ", ".join([s["symbol"] for s in group])
            lines.append(f"- **{label}**: {syms}")

    # 操作建议
    lines.extend([
        "", "## 五、操作建议", "",
        "| 等级 | 品种 | 策略 |",
        "|:----:|------|------|",
    ])

    actionable = [s for s in ranked if s["n"] >= THRESHOLDS["min_eval_points"]]
    for s in actionable:
        if s["dir_acc"] >= 0.60:
            lines.append(f"| ⭐⭐⭐ | {s['symbol']} | 直接用级联预测信号 |")
        elif s["dir12_acc"] > s["dir_acc"] + 0.10:
            lines.append(f"| ⭐⭐ | {s['symbol']} | 仅参考 T+1~T+{HORIZON//2} 信号 |")
        elif s["mape"] <= THRESHOLDS["mape_good"] and s["dir_acc"] >= 0.50:
            lines.append(f"| ⭐⭐ | {s['symbol']} | 精度好，配合其他指标使用 |")
        elif s["dir_acc"] >= 0.45:
            lines.append(f"| ⭐ | {s['symbol']} | 方向弱，需改进协变量 |")
        else:
            lines.append(f"| ❌ | {s['symbol']} | 当前模型无效 |")

    lines.extend([
        "",
        "---",
        "",
        f"> 本报告由 `scripts/monthly_backtest.py` 自动生成。",
        f"> 参数配置: `config/backtest_config.py`",
        f"> 历史数据: `reports/monthly_backtest/history.json`",
    ])

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main():
    ensure_dirs()

    # 解析参数
    args = sys.argv[1:]
    if "--summary" in args:
        history = load_history()
        if not history:
            print("无历史记录")
            return
        for month in sorted(history.keys()):
            data = history[month]
            syms = [f"{s['symbol']}:{s['dir_acc']:.0%}" for s in data["summary"]]
            print(f"{month}: {', '.join(syms)}")
        return

    # 协变量覆盖: --cov-override rsi_slope | hourly_slope | oi | ccl
    cov_override = None
    if "--cov-override" in args:
        idx = args.index("--cov-override")
        if idx + 1 < len(args):
            cov_override = args[idx + 1]
            args = args[:idx] + args[idx + 2:]  # 移除已解析的参数

    # 组合协变量: --combo "rsi_state,oi,hurst"
    cov_combo = None
    if "--combo" in args:
        idx = args.index("--combo")
        if idx + 1 < len(args):
            cov_combo = [s.strip() for s in args[idx + 1].split(",")]
            args = args[:idx] + args[idx + 2:]

    # 信号模式覆盖: --full-signal (use_full_signal=True, short_horizon_only=False)
    signal_override = None
    if "--full-signal" in args:
        signal_override = {"use_full_signal": True, "short_horizon_only": False}
        args = [a for a in args if a != "--full-signal"]

    # 极值截断: --clip-gap 0.05 (将 delta_real 截断到 ±5%*base, 用于 LH 等 gap 频发品种)
    clip_gap = None
    if "--clip-gap" in args:
        idx = args.index("--clip-gap")
        if idx + 1 < len(args):
            clip_gap = float(args[idx + 1])
            args = args[:idx] + args[idx + 2:]

    # cache 清理频率 (默认 10, 与现状硬编码一致)
    cache_interval = 10
    if "--cache-interval" in args:
        idx = args.index("--cache-interval")
        if idx + 1 < len(args):
            try:
                cache_interval = int(args[idx + 1])
            except ValueError:
                print("--cache-interval 需整数"); return
            args = args[:idx] + args[idx + 2:]

    # 减量排查: 每品种最多跑 N 评估点 (None=不限)
    max_points = None
    if "--max-points" in args:
        idx = args.index("--max-points")
        if idx + 1 < len(args):
            try:
                max_points = int(args[idx + 1])
            except ValueError:
                print("--max-points 需整数"); return
            args = args[:idx] + args[idx + 2:]

    # 断点续跑: --resume <checkpoint.jsonl>
    resume_path = None
    if "--resume" in args:
        idx = args.index("--resume")
        if idx + 1 < len(args):
            resume_path = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    # Baseline 对照: --with-baseline (回测前输出当前固化方案的 baseline 信息)
    with_baseline = "--with-baseline" in args
    args = [a for a in args if a != "--with-baseline"]

    # Horizon 填充策略: --fill-strategy default | decay
    fill_strategy = "default"
    if "--fill-strategy" in args:
        idx = args.index("--fill-strategy")
        if idx + 1 < len(args):
            fill_strategy = args[idx + 1]
            assert fill_strategy in ("default", "decay"), \
                f"Invalid fill_strategy: {fill_strategy} (expected 'default' or 'decay')"
            args = args[:idx] + args[idx + 2:]

    symbols = [s for s in args if not s.startswith("--")]
    if not symbols:
        symbols = SYMBOLS

    if cov_combo:
        cov_tag = f" [combo={'+'.join(cov_combo)}]"
    elif cov_override:
        cov_tag = f" [cov_override={cov_override}]"
    else:
        cov_tag = ""
    sig_tag = " [full_signal]" if signal_override else ""
    print("=" * 60)
    print(f"  1H 级联预测月度回测 — {datetime.now().strftime('%Y-%m')}")
    print(f"  品种: {len(symbols)} 个{cov_tag}{sig_tag}")
    print(f"  参数: context={CONTEXT_BARS}, horizon={HORIZON}, step={STEP}")
    print("=" * 60)

    # Baseline 对照输出
    if with_baseline:
        from config.prediction_scheme import SCHEMES as _SCHEMES
        print(f"\n{'=' * 60}")
        print("  Baseline 对照 (prediction_scheme.py 固化方案)")
        print(f"{'=' * 60}")
        print(f"{'品种':4s}  {'DirAcc':>6}  {'MAPE':>6}  {'Decay':>6}  {'星星':>4s}  协变量")
        print("-" * 60)
        for sym in symbols:
            sc = _SCHEMES.get(sym.lower())
            if sc:
                print(f"{sym.upper():4s}  {sc.dir_acc:>6.0%}  {sc.mape:>5.2f}%  {sc.decay:>5.2f}x  {sc.stars:>2d}★   {sc.covariate_type}")
            else:
                print(f"{sym.upper():4s}  {'未固化':>6s}")
        print(f"\n  注: PF (Profit Factor) 需完整 walk-forward 回测获得,")
        print(f"  scheme 中的 dir_acc 为方向准确率, 非 PF.")
        print(f"{'=' * 60}")

    # 加载模型
    print("\n[1/4] 加载 TimesFM 2.5 模型...")
    torch.set_float32_matmul_precision("high")
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)

    # ── resume: 读已完成的 (symbol, idx) + 完整 point 载荷 ──
    # 单写入者约定: 同一 checkpoint JSONL 同时只允许一个进程 --resume 追加
    # (A2 用 exclusive_result_lock；monthly 依赖运维单 worker，见 scripts/AGENTS.md)
    completed = set()
    resumed_points = {}
    checkpoint_fp = None
    if resume_path:
        from pathlib import Path
        import json as _json
        cp = Path(resume_path)
        if cp.exists():
            with open(cp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = _json.loads(line)
                        key = (rec["symbol"], int(rec["idx"]))
                        completed.add(key)
                        # 仅合并含经济字段的完整记录（旧版只有 mae/dir_ok 的行无法重建）
                        if "delta_pred" in rec and "delta_real" in rec and "error" not in rec:
                            pt = {k: rec[k] for k in _CHECKPOINT_POINT_KEYS if k in rec}
                            resumed_points[key] = pt
                    except (_json.JSONDecodeError, KeyError, TypeError, ValueError):
                        continue
            n_full = len(resumed_points)
            print(
                f"  [resume] 已加载 {len(completed)} 完成点 "
                f"({n_full} 含完整字段可合并) from {resume_path}"
            )
            if len(completed) and n_full < len(completed):
                print(
                    "  [resume][WARN] 部分 checkpoint 行为旧格式/残缺，"
                    "对应点将不计入 summarize（请全量重跑或删残缺行）"
                )
        # 追加模式; 同次运行复用同一文件继续追加
        checkpoint_fp = open(cp, "a", encoding="utf-8")
    # 无 resume 时不创建 checkpoint 文件 (零回归铁律: 仅 --resume 时写 checkpoint)

    # 逐品种回测
    print("[2/4] 运行回测...")
    all_data = []
    summary_list = []

    # 进度日志文件 (供 Monitor 工具事件驱动监控，避免重复轮询触发 400)
    progress_log = BACKTEST_DIR / "progress.log"
    progress_log.write_text(f"START {datetime.now().isoformat()}\n", encoding="utf-8")

    for i, symbol in enumerate(symbols):
        print(f"  [{i+1}/{len(symbols)}] {symbol.upper()}...", end=" ", flush=True)
        progress_log.write_text(f"[{i+1}/{len(symbols)}] {symbol.upper()} START\n",
                                encoding="utf-8")
        try:
            data = run_symbol_backtest(symbol, daily_model, hourly_model,
                                        cov_override=cov_override, cov_combo=cov_combo,
                                        clip_gap=clip_gap,
                                        cache_interval=cache_interval, max_points=max_points,
                                        completed=completed, checkpoint_fp=checkpoint_fp,
                                        resumed_points=resumed_points,
                                        signal_override=signal_override,
                                        fill_strategy=fill_strategy)
            if data is None:
                print("SKIP (无数据)")
                progress_log.write_text(f"[{i+1}/{len(symbols)}] {symbol.upper()} SKIP\n",
                                        encoding="utf-8")
                continue

            s = summarize(data)
            if s is None:
                print("FAIL")
                progress_log.write_text(f"[{i+1}/{len(symbols)}] {symbol.upper()} FAIL\n",
                                        encoding="utf-8")
                continue

            all_data.append(data)
            summary_list.append(s)
            # EV_ratio= 无量纲；勿写成 EV=（价格点 EV 见 s['ev']）— phase4d 解析对齐
            msg = (f"{s['n']}pts DirAcc={s['dir_acc']:.0%}(ref) MAPE={s['mape']:.2f}% "
                   f"decay={s['decay']:.2f}x EV_ratio={s['ev_ratio']:+.3f} PF={s['profit_factor']:.2f} "
                   f"MaxDD={s.get('max_dd', 0):.2%} "
                   f"WR={s.get('win_rate', 0):.0%}")
            print(msg)
            progress_log.write_text(
                f"[{i+1}/{len(symbols)}] {symbol.upper()} OK {msg}\n",
                encoding="utf-8",
            )

        except Exception as e:
            print(f"ERROR: {e}")
            progress_log.write_text(f"[{i+1}/{len(symbols)}] {symbol.upper()} ERROR {e}\n",
                                    encoding="utf-8")

    progress_log.write_text(f"DONE {datetime.now().isoformat()}\n", encoding="utf-8")

    if not summary_list:
        print("无有效结果")
        if checkpoint_fp is not None:
            checkpoint_fp.close()
        return

    # 分类
    print("[3/4] 分类分析...")
    categories = classify(summary_list)

    # 月度对比
    comparison = compare_with_last_month(summary_list)

    # 更新历史
    # 实验旗标不污染历史表
    if not signal_override:
        update_history(summary_list, categories)

    # 生成报告
    report = generate_report(summary_list, categories, comparison)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = BACKTEST_DIR / f"{timestamp}_monthly_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n[4/4] 报告保存: {report_path}")

    # 控制台汇总
    print("\n" + "=" * 80)
    # CF-23 A: 经济指标优先排序 (PF → EV → MaxDD)，DirAcc 仅展示
    print("  汇总 (按 PF 排序, EV/MaxDD 次之; DirAcc 仅附录)")
    print("=" * 80)
    print(f"{'#':>2} {'品种':>4} {'名称':>4} {'MAPE':>7} {'DirAcc':>7} {'Decay':>6} {'EV_r':>6} {'PF':>5} {'WR':>5}")
    print("-" * 58)
    ranked = sorted(
        summary_list,
        key=lambda x: (x.get("profit_factor", 0), x.get("ev_ratio", 0), -abs(x.get("max_dd", 0))),
        reverse=True,
    )
    for i, s in enumerate(ranked):
        pf_s = f"{s['profit_factor']:.1f}" if s['profit_factor'] < 99.99 else "99.99+"
        print(f"{i+1:>2} {s['symbol']:>4} {s['name']:>4} {s['mape']:>6.2f}% {s['dir_acc']:>6.0%} {s['decay']:>5.2f}x {s['ev_ratio']:>+5.3f} {pf_s:>5} {s.get('win_rate', 0):>4.0%}")

    print("\n分类:")
    for cat_key, label in CATEGORY_LABELS.items():
        syms = categories.get(cat_key, [])
        if syms:
            print(f"  {label}: {', '.join(syms)}")

    if comparison:
        print(f"\nvs {comparison['last_month']}:")
        improved = [d for d in comparison["diffs"] if d["dir_acc_delta"] > 0.05]
        degraded = [d for d in comparison["diffs"] if d["dir_acc_delta"] < -0.05]
        if improved:
            print(f"  改善: {', '.join([d['symbol'] for d in improved])}")
        if degraded:
            print(f"  退化: {', '.join([d['symbol'] for d in degraded])}")

    print("\n完成。")

    if checkpoint_fp is not None:
        checkpoint_fp.close()


if __name__ == "__main__":
    main()

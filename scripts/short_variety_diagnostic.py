"""
G001' Short 品种诊断矩阵 v2 (审核修正版)

修正项 (per 20260817_short_variety_worklog_review.md):
- P0-1: 先写盘再 print (print 失败不丢结果)
- P0-2: 每格 JSONL checkpoint + --resume
- P0-3: 全历史均匀采样 (不再取最左 200 点)
- P0-4: 并排报 PF24 + PF12 (短窗收益对齐)
- P1-1: 品种分层 — 病人 BU/P/CF / 对照 CJ / 已优化 AO
- P1-2: 外科 cov 替换 (只动 ha_body, 保留 combo 其余成员)
- P1-3: C2h 用 cov_combo (1H RSI) 而非 cov_override (日线 RSI)
- P1-5: 自动调用 verdict() 做 v2 分层
- P2-3: JSON 字段对齐 verdict() 需求

矩阵:
  病人 (BU/P/CF): A + B + C2h + C3 = 4 configs x 3 = 12
  对照 (CJ):      A + B                = 2 configs x 1 = 2
  已优化 (AO):    A + B                = 2 configs x 1 = 2
  合计: 16 configs

配置:
  A   (baseline):  short_horizon + current covariates
  B   (full):      use_full_signal + decay, covariates unchanged
  C2h (1H RSI):    short_horizon + surgical swap ha_body -> rsi_state (1H, via cov_combo)
  C3  (rsi+oi):    short_horizon + surgical swap ha_body -> rsi_state+oi (via cov_combo)

用法:
  python scripts/short_variety_diagnostic.py
  python scripts/short_variety_diagnostic.py --varieties bu p --max-points 100
  python scripts/short_variety_diagnostic.py --resume
"""

import sys
import os
import json
import copy
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import pandas as pd

from config.prediction_scheme import SCHEMES, VarietyScheme
from scripts.monthly_backtest import (
    run_symbol_backtest, summarize, _CHECKPOINT_POINT_KEYS,
)
from cascade.evaluation_metrics import metrics_from_backtest_points
from scripts.phase4d_parse_results import verdict as v2_verdict
from config.backtest_config import (
    CONTEXT_BARS, HORIZON, STEP, TICK_SIZES, SLIPPAGE_TICKS,
)
from data.data_store import DataStore, BacktestDataStore

# ─────────────────────────────────────────────────────────
# 品种分层 (P1-1)
# ─────────────────────────────────────────────────────────

PATIENTS = ["bu", "p", "cf"]      # 经济失效, 需要修复
CONTROL = ["cj"]                   # 阳性对照 (PF=1.26, 2★)
OPTIMIZED = ["ao"]                 # 已优化 (hourly_slope+calendar), ha_body 有毒
ALL_VARIETIES = PATIENTS + CONTROL + OPTIMIZED

# ─────────────────────────────────────────────────────────
# 外科 cov 替换表 (P1-2)
# 只动 ha_body, 保留 combo 其余成员
# ─────────────────────────────────────────────────────────

SURGICAL_COV = {
    # variety: {current_combo, C2h_combo (swap ha_body->rsi_state), C3_combo (swap ha_body->rsi_state+oi)}
    "bu": {
        "current_single": "ha_body",
        "current_combo": None,
        "C2h": {"cov_combo": ["rsi_state"]},        # 单因子 1H RSI
        "C3":  {"cov_combo": ["rsi_state", "oi"]},  # JD 配方移植
    },
    "p": {
        "current_single": None,
        "current_combo": ["ha_body", "reversal_shadow"],
        "C2h": {"cov_combo": ["rsi_state", "reversal_shadow"]},
        "C3":  {"cov_combo": ["rsi_state", "oi", "reversal_shadow"]},
    },
    "cf": {
        "current_single": None,
        "current_combo": ["ha_body", "calendar_cyclical"],
        "C2h": {"cov_combo": ["rsi_state", "calendar_cyclical"]},
        "C3":  {"cov_combo": ["rsi_state", "oi", "calendar_cyclical"]},
    },
}

# ─────────────────────────────────────────────────────────
# 配置定义
# ─────────────────────────────────────────────────────────

def get_configs(sym: str) -> dict:
    """返回该品种应跑的配置集合."""
    is_patient = sym in PATIENTS

    configs = {
        "A": {
            "label": "baseline (short + current)",
            "signal_override": None,
            "cov_override": None,
            "cov_combo": None,
        },
        "B": {
            "label": "full_signal + decay",
            "signal_override": {"use_full_signal": True, "short_horizon_only": False},
            "cov_override": None,
            "cov_combo": None,
        },
    }

    if is_patient and sym in SURGICAL_COV:
        sc = SURGICAL_COV[sym]
        configs["C2h"] = {
            "label": "short + 1H rsi_state (surgical)",
            "signal_override": None,
            "cov_override": None,
            "cov_combo": sc["C2h"]["cov_combo"],
        }
        configs["C3"] = {
            "label": "short + rsi_state+oi (surgical)",
            "signal_override": None,
            "cov_override": None,
            "cov_combo": sc["C3"]["cov_combo"],
        }

    return configs


# ─────────────────────────────────────────────────────────
# Scheme patching
# ─────────────────────────────────────────────────────────

def patch_scheme(symbol, signal_override):
    if signal_override is None:
        return None
    original = copy.deepcopy(SCHEMES[symbol])
    for k, v in signal_override.items():
        setattr(SCHEMES[symbol], k, v)
    return original


def restore_scheme(symbol, original):
    if original is not None:
        SCHEMES[symbol] = original


# ─────────────────────────────────────────────────────────
# PF12 计算 (P0-4)
# ─────────────────────────────────────────────────────────

def compute_pf12(points, tick_size, slippage_ticks=2):
    """用 T+12 收益重算 PF/EV/MaxDD.

    points 需含 delta_pred, delta_real_12, base.
    delta_real_12 = real[half-1] - base (T+12 close - base).
    """
    half = HORIZON // 2
    ok = [p for p in points if "error" not in p and "delta_real_12" in p]
    if not ok:
        return {}

    # 构造 PF12 用的 points: delta_real 替换为 delta_real_12
    pts12 = []
    for p in ok:
        p12 = dict(p)
        p12["delta_real"] = p["delta_real_12"]
        # pnl12 = position_sign * delta_real_12
        # position_sign = sign(delta_pred)
        sign = np.sign(p["delta_pred"])
        p12["pnl"] = float(sign * p["delta_real_12"]) if sign != 0 else 0.0
        pts12.append(p12)

    net12 = metrics_from_backtest_points(pts12, tick_size=tick_size,
                                          slippage_ticks=slippage_ticks)
    return {
        "PF12": net12.get("PF", None),
        "EV12_ratio": net12.get("EV_ratio", None),
        "MaxDD12": net12.get("MaxDD", None),
    }


# ─────────────────────────────────────────────────────────
# 诊断回测 (fork of run_symbol_backtest with PF12 + uniform sampling)
# ─────────────────────────────────────────────────────────

def run_diagnostic_backtest(symbol, daily_model, hourly_model,
                            cov_override=None, cov_combo=None,
                            max_points=None, checkpoint_fp=None,
                            completed=None, resumed_points=None):
    """Fork of run_symbol_backtest with:
    - Uniform sampling (P0-3) instead of left-truncation
    - PF12 computation (P0-4): stores delta_real_12 per point
    - Checkpoint support (P0-2)
    """
    from config.backtest_config import (
        CONTEXT_BARS, CONTEXT_DAYS, HORIZON, HORIZON_DAYS, STEP,
    )

    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()

    if all_1h.empty or len(all_1h) < CONTEXT_BARS + HORIZON:
        return None

    total = len(all_1h)
    contract = all_1h["contract_code"].iloc[-1]
    eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))

    # P0-3: 全历史均匀采样 (不再取最左 N 点)
    if max_points is not None and len(eval_indices) > max_points:
        step = len(eval_indices) / max_points
        eval_indices = [eval_indices[int(i * step)] for i in range(max_points)]

    sym_lower = symbol.lower()

    # 日线充足性过滤
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

    # 协变量检测
    effective_combo = cov_combo
    effective_single = cov_override
    if not effective_combo and not effective_single:
        _scheme = SCHEMES.get(sym_lower)
        if _scheme and _scheme.covariate_types and len(_scheme.covariate_types) > 1:
            effective_combo = _scheme.covariate_types
        elif _scheme:
            effective_single = _scheme.covariate_type
        else:
            effective_single = "ccl"
    _cov_label = '+'.join(effective_combo) if effective_combo else effective_single
    print(f"  [cov={_cov_label}] n_eval={len(eval_indices)}")

    half = HORIZON // 2
    points = []
    for i, idx in enumerate(eval_indices):
        if completed is not None and (sym_lower, idx) in completed:
            if resumed_points and (sym_lower, idx) in resumed_points:
                pt = dict(resumed_points[(sym_lower, idx)])
                pt.pop("symbol", None)
                pt.pop("idx", None)
                points.append(pt)
            continue

        bar_ts = pd.Timestamp(all_1h["dt"].iloc[idx])
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        dt = bar_ts.strftime("%Y-%m-%d")
        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx+1:idx+1+HORIZON].values.astype(np.float64)

        if i > 0 and i % 10 == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        if i < 3 or i % 50 == 0:
            print(f"    [{i+1}/{len(eval_indices)}] {cutoff}...", end="", flush=True)

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            if effective_combo:
                daily_result = daily_model.predict(symbol, bt_store,
                    context_days=CONTEXT_DAYS, horizon_days=HORIZON_DAYS)
                hourly_result = hourly_model.predict(symbol, bt_store, daily_result,
                    horizon=HORIZON, visualize=False,
                    covariate_types=effective_combo, verbose=False)
            else:
                daily_result = daily_model.predict(symbol, bt_store,
                    context_days=CONTEXT_DAYS, horizon_days=HORIZON_DAYS)
                hourly_result = hourly_model.predict(symbol, bt_store, daily_result,
                    horizon=HORIZON, visualize=False,
                    covariate_type=effective_single, verbose=False)

            pred = hourly_result.point_forecast
            quant = hourly_result.quantile_forecast

            from config.prediction_scheme import get_scheme
            _scheme = get_scheme(symbol)
            _sig = __import__("cascade.signal_contract", fromlist=["position_from_forecast"]).position_from_forecast(
                pred, base, scheme=_scheme,
                daily_slope=getattr(daily_result, "horizon_slope", None),
            )
            delta_pred = float(_sig["delta_pred"])
            position_sign = float(_sig["position_sign"])

            # T+24 (standard)
            delta_real = float(real[-1] - base)
            # T+12 (P0-4: 短窗收益对齐)
            delta_real_12 = float(real[half - 1] - base)

            pnl = float(position_sign * delta_real) if position_sign != 0 else 0.0
            dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True

            mae = float(np.mean(np.abs(pred - real)))
            safe_real = np.where(real == 0, 1e-8, np.abs(real))
            mape = float(np.mean(np.abs(pred - real) / safe_real) * 100)

            if _sig.get("short_horizon_only"):
                d12_pred = float(np.mean(pred[:half]) - base)
            else:
                d12_pred = pred[half - 1] - base
            d12_real = real[half - 1] - base
            dir12_ok = bool(np.sign(d12_pred) == np.sign(d12_real)) if d12_real != 0 else True

            cov = 0
            if quant is not None and quant.ndim == 2 and quant.shape[1] >= 10:
                for t in range(HORIZON):
                    if quant[t, 1] <= real[t] <= quant[t, 9]:
                        cov += 1

            point = {
                "cutoff": dt, "base": base,
                "pred_end": float(pred[-1]), "real_end": float(real[-1]),
                "delta_pred": delta_pred, "delta_real": delta_real,
                "delta_real_12": delta_real_12,  # P0-4
                "dir_ok": dir_ok, "dir12_ok": dir12_ok,
                "mae": mae, "mape": mape,
                "mae_h1": float(np.mean(np.abs(pred[:half] - real[:half]))),
                "mae_h2": float(np.mean(np.abs(pred[half:] - real[half:]))),
                "coverage": cov, "pnl": pnl,
                "real_range": float(real.max() - real.min()),
            }
            points.append(point)

            # Checkpoint (P0-2)
            if checkpoint_fp is not None:
                rec = {"symbol": sym_lower, "idx": int(idx)}
                for k in _CHECKPOINT_POINT_KEYS:
                    rec[k] = point.get(k, 0)
                rec["delta_real_12"] = delta_real_12
                rec["mae_pct"] = round(float(np.mean(np.abs(pred - real)) / base * 100), 4) if base else 0.0
                checkpoint_fp.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                checkpoint_fp.flush()

            if i < 3 or i % 50 == 0:
                print(f" done")

        except Exception as e:
            points.append({"cutoff": dt, "error": str(e)})
            if checkpoint_fp is not None:
                checkpoint_fp.write(json.dumps({
                    "symbol": sym_lower, "idx": int(idx), "error": str(e), "cutoff": dt,
                }, ensure_ascii=False) + "\n")
                checkpoint_fp.flush()
            if i < 3 or i % 50 == 0:
                print(f" [ERR] {e}")

    return {
        "symbol": symbol.upper(),
        "name": sym_lower,
        "contract": contract,
        "total_bars": total,
        "eval_count": len(eval_indices),
        "points": points,
    }


# ─────────────────────────────────────────────────────────
# 主诊断流程
# ─────────────────────────────────────────────────────────

def run_diagnostic(varieties, max_points, output_dir, resume=False):
    from cascade.daily_model import DailyModel
    from cascade.hourly_model import HourlyModel

    print("=" * 70)
    print("G001' Short Variety Diagnostic Matrix v2")
    print(f"Patients:  {[v.upper() for v in varieties if v in PATIENTS]}")
    print(f"Controls:  {[v.upper() for v in varieties if v in CONTROL]}")
    print(f"Optimized: {[v.upper() for v in varieties if v in OPTIMIZED]}")
    print(f"max_points: {max_points} (uniform sampling)")
    print(f"Output: {output_dir}")
    print("=" * 70)

    print("\n[1/3] Loading models...")
    daily_model = DailyModel()
    hourly_model = HourlyModel()
    print("  Models loaded.\n")

    os.makedirs(output_dir, exist_ok=True)
    results_file = os.path.join(output_dir, "short_diagnostic_results.json")

    # Resume (P0-2)
    results = {}
    if resume and os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"[resume] loaded {len(results)} existing results")

    print("[2/3] Running diagnostic matrix...")

    # 计算总配置数
    all_configs = {}
    for sym in varieties:
        all_configs[sym] = get_configs(sym)
    total_configs = sum(len(v) for v in all_configs.values())
    done = 0

    for sym in varieties:
        scheme = SCHEMES.get(sym)
        if scheme is None:
            print(f"  [WARN] {sym} no scheme, skip")
            continue

        configs = all_configs[sym]

        for cfg_key, cfg in configs.items():
            done += 1
            tag = f"{sym}_{cfg_key}"

            # skip completed (resume)
            if tag in results and "error" not in results[tag]:
                print(f"\n  [{done}/{total_configs}] {tag}: [SKIP] already done")
                continue

            print(f"\n  [{done}/{total_configs}] {tag}: {cfg['label']}")

            # Checkpoint file (P0-2)
            ckpt_path = os.path.join(output_dir, f"{tag}.jsonl")
            completed_set = None
            resumed_pts = None
            if resume and os.path.exists(ckpt_path):
                # Parse existing checkpoint
                completed_set = set()
                resumed_pts = {}
                with open(ckpt_path, "r", encoding="utf-8") as cf:
                    for line in cf:
                        try:
                            rec = json.loads(line.strip())
                            if "error" not in rec:
                                completed_set.add((sym, rec["idx"]))
                                resumed_pts[(sym, rec["idx"])] = rec
                        except Exception:
                            pass
                print(f"  [resume] {len(completed_set)} points from checkpoint")

            original = patch_scheme(sym, cfg["signal_override"])

            try:
                ckpt_fp = None
                try:
                    ckpt_fp = open(ckpt_path, "a", encoding="utf-8")

                    data = run_diagnostic_backtest(
                        sym, daily_model, hourly_model,
                        cov_override=cfg["cov_override"],
                        cov_combo=cfg["cov_combo"],
                        max_points=max_points,
                        checkpoint_fp=ckpt_fp,
                        completed=completed_set,
                        resumed_points=resumed_pts,
                    )
                finally:
                    if ckpt_fp:
                        ckpt_fp.close()

                if data is None:
                    r = {"symbol": sym, "config": cfg_key, "error": "no_data"}
                    results[tag] = r
                    # DUMP FIRST (P0-1)
                    with open(results_file, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
                    print(f"    [SKIP] data insufficient")
                    continue

                summary = summarize(data)
                if summary is None:
                    r = {"symbol": sym, "config": cfg_key, "error": "no_points"}
                    results[tag] = r
                    with open(results_file, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
                    print(f"    [SKIP] no valid eval points")
                    continue

                # PF12 (P0-4)
                tick = TICK_SIZES.get(sym, 1.0)
                pf12 = compute_pf12(data["points"], tick_size=tick,
                                     slippage_ticks=SLIPPAGE_TICKS)

                # v2 verdict vs baseline (P1-5)
                v2_status, v2_tag, v2_reasons = "N/A", "", []
                baseline_tag = f"{sym}_A"
                if cfg_key != "A" and baseline_tag in results and "error" not in results[baseline_tag]:
                    bl = results[baseline_tag]
                    cand = {
                        "ev": summary["ev_ratio"],
                        "pf": summary["profit_factor"],
                        "maxdd": summary["max_dd"],
                        "mape": summary["mape"],
                        "diracc": summary["dir_acc"],
                        "n": summary["n"],
                    }
                    base = {
                        "ev": bl.get("EV_ratio", bl.get("EV_r", 0)),
                        "pf": bl.get("PF", 0),
                        "maxdd": bl.get("MaxDD", 0),
                        "mape": bl.get("mape", 0),
                        "diracc": bl.get("dir_acc", 0),
                        "n": bl.get("n", 0),
                    }
                    v2_status, v2_tag, v2_reasons = v2_verdict(base, cand)

                # Build result record (P2-3: aligned fields)
                r = {
                    "symbol": sym,
                    "config": cfg_key,
                    "label": cfg["label"],
                    "n": summary["n"],
                    "dir_acc": summary["dir_acc"],
                    "dir12_acc": summary.get("dir12_acc", None),
                    "mape": summary["mape"],
                    "PF": summary["profit_factor"],
                    "PF12": pf12.get("PF12", None),
                    "EV_ratio": summary["ev_ratio"],
                    "EV_ratio_gross": summary["ev_ratio_gross"],
                    "MaxDD": summary["max_dd"],
                    "MaxDD12": pf12.get("MaxDD12", None),
                    "WR": summary["win_rate"],
                    "decay": summary.get("decay", None),
                    "date_start": data["points"][0].get("cutoff", "") if data["points"] else "",
                    "date_end": data["points"][-1].get("cutoff", "") if data["points"] else "",
                    "v2_status": v2_status,
                    "v2_tag": v2_tag,
                    "v2_reasons": v2_reasons,
                }
                results[tag] = r

                # DUMP FIRST (P0-1)
                with open(results_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2, default=str)

                # Print AFTER dump
                v2_str = f" v2={v2_status}" if v2_status != "N/A" else ""
                pf12_str = f" PF12={r['PF12']:.3f}" if r.get("PF12") is not None else ""
                print(f"    [OK] n={r['n']} DirAcc={r['dir_acc']:.3f} "
                      f"PF={r['PF']:.3f}{pf12_str} "
                      f"EV={r['EV_ratio']:+.4f} MaxDD={r['MaxDD']:.3f}{v2_str}")

            except Exception as e:
                print(f"    [ERR] {e}")
                results[tag] = {"symbol": sym, "config": cfg_key, "error": str(e)}
                # DUMP FIRST even on error
                with open(results_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2, default=str)

            finally:
                restore_scheme(sym, original)

    # ── Summary ──
    print("\n" + "=" * 70)
    print("[3/3] Summary")

    header = f"{'sym':>4} | {'cfg':>4} | {'n':>4} | {'DA':>5} | {'PF':>6} | {'PF12':>6} | {'EV':>7} | {'MaxDD':>7} | {'v2':>10}"
    print(header)
    print("-" * len(header))

    for sym in varieties:
        bl_pf = results.get(f"{sym}_A", {}).get("PF")
        for cfg_key in all_configs.get(sym, {}):
            tag = f"{sym}_{cfg_key}"
            r = results.get(tag)
            if r is None or "error" in r:
                print(f"{sym:>4} | {cfg_key:>4} | {'ERR':>4} | {'':>5} | {'':>6} | {'':>6} | {'':>7} | {'':>7} | {'':>10}")
                continue
            pf12_s = f"{r['PF12']:.3f}" if r.get("PF12") is not None else "N/A"
            delta = ""
            if cfg_key != "A" and bl_pf and r.get("PF"):
                d = r["PF"] - bl_pf
                delta = f"({d:+.3f})"
            print(f"{sym:>4} | {cfg_key:>4} | {r['n']:>4} | {r['dir_acc']:>5.3f} | "
                  f"{r['PF']:>5.3f}{delta} | {pf12_s:>6} | {r.get('EV_ratio',0):>+7.4f} | "
                  f"{r['MaxDD']:>7.3f} | {r.get('v2_status',''):>10}")

    # Save report
    report_file = os.path.join(output_dir, "short_diagnostic_report.md")
    _write_report(results, varieties, all_configs, max_points, report_file)

    print(f"\n[OK] results saved:")
    print(f"  JSON: {results_file}")
    print(f"  report: {report_file}")

    return results


def _write_report(results, varieties, all_configs, max_points, report_file):
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# G001' Short Variety Diagnostic Matrix v2\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Patients**: {', '.join(v.upper() for v in PATIENTS if v in varieties)}\n")
        f.write(f"**Controls**: {', '.join(v.upper() for v in CONTROL if v in varieties)}\n")
        f.write(f"**Optimized**: {', '.join(v.upper() for v in OPTIMIZED if v in varieties)}\n")
        f.write(f"**max_points**: {max_points} (uniform sampling)\n\n")
        f.write("## Configs\n\n")
        f.write("- **A**: baseline (short + current covariates)\n")
        f.write("- **B**: full_signal + decay (tests H1: signal truncation)\n")
        f.write("- **C2h**: surgical ha_body -> rsi_state via cov_combo (tests H2': 1H mean reversion)\n")
        f.write("- **C3**: surgical ha_body -> rsi_state+oi via cov_combo (tests JD formula transplant)\n\n")
        f.write("## Results\n\n")
        f.write("| sym | cfg | n | DirAcc | PF | PF12 | EV | MaxDD | v2 | dates |\n")
        f.write("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|\n")
        for sym in varieties:
            for cfg_key in all_configs.get(sym, {}):
                tag = f"{sym}_{cfg_key}"
                r = results.get(tag)
                if r is None or "error" in r:
                    continue
                pf12_s = f"{r['PF12']:.3f}" if r.get("PF12") is not None else "N/A"
                dates = f"{r.get('date_start','')}~{r.get('date_end','')}"
                f.write(f"| {sym.upper()} | {cfg_key} | {r['n']} | "
                        f"{r['dir_acc']:.3f} | {r['PF']:.3f} | {pf12_s} | "
                        f"{r.get('EV_ratio',0):+.4f} | {r['MaxDD']:.3f} | "
                        f"{r.get('v2_status','')} | {dates} |\n")

        f.write("\n## Hypothesis Testing\n\n")
        f.write("_To be filled after all configs complete._\n")


def main():
    parser = argparse.ArgumentParser(description="Short variety diagnostic v2")
    parser.add_argument("--varieties", nargs="+", default=ALL_VARIETIES)
    parser.add_argument("--max-points", type=int, default=200)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--resume", action="store_true", default=False)
    args = parser.parse_args()

    if args.output_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        args.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "reports", "research", f"short_diagnostic_v2_{ts}"
        )

    run_diagnostic(args.varieties, args.max_points, args.output_dir,
                   resume=args.resume)


if __name__ == "__main__":
    main()

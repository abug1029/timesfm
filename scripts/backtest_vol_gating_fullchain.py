#!/usr/bin/env python3
"""
TimesFM 全链路 Vol Gating 对比回测（重型）

共享 raw forecast 的 OFF vs Neutral Override 配对回测。
评分 / 门禁 / 报告 → cascade.neutral_ab_report（唯一真相源）。

用法:
  python scripts/backtest_vol_gating_fullchain.py --universe l1
  python scripts/backtest_vol_gating_fullchain.py --symbols sr fu --thr 0.55
  python scripts/backtest_vol_gating_fullchain.py --step 48
"""

from __future__ import annotations

import sys
import os
import json
import argparse
import traceback
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd
import torch

from config.backtest_config import (
    CONTEXT_BARS, CONTEXT_DAYS, HORIZON, HORIZON_DAYS, STEP,
    TICK_SIZES, SLIPPAGE_TICKS, BACKTEST_DIR, ensure_dirs,
)
from config.prediction_scheme import get_scheme
from data.data_store import DataStore
from cascade.daily_model import DailyModel
from cascade.hourly_model import HourlyModel
from cascade.evaluation_metrics import metrics_from_backtest_points
from cascade.vol_risk_filter import (
    DEFAULT_MODEL_PATH,
    DEFAULT_PROB_THRESHOLD,
    ThrPolicy,
    VolRiskFilter,
    apply_neutral_override,
)
from cascade.hourly_model import HourlyResult
from cascade.neutral_ab_report import (
    atomic_write_json,
    load_checkpoint_dir,
    save_symbol_checkpoint,
    score_and_write,
)
from data.data_store import BacktestDataStore

DEFAULT_SYMBOLS = ["sr", "fu", "i", "m"]
OOS_START = "2026-04-01"
OOS_END = "2026-07-31"
REPORT_DIR = Path("reports/phase1")


def resolve_cov(symbol: str):
    scheme = get_scheme(symbol)
    if scheme and scheme.covariate_types and len(scheme.covariate_types) > 1:
        return None, scheme.covariate_types, "+".join(scheme.covariate_types)
    if scheme:
        return scheme.covariate_type, None, scheme.covariate_type
    return "ccl", None, "ccl"


def predict_one(symbol, bt_store, daily_model, hourly_model, cov_type, cov_types):
    """静态 scheme 单次预测（shared-forecast 路径）。"""
    daily_result = daily_model.predict(
        symbol, bt_store, context_days=CONTEXT_DAYS, horizon_days=HORIZON_DAYS,
    )
    if cov_types and len(cov_types) > 1:
        hourly_result = hourly_model.predict(
            symbol, bt_store, daily_result,
            horizon=HORIZON, visualize=False,
            covariate_types=cov_types,
            verbose=False, skip_validation=True,
        )
    else:
        hourly_result = hourly_model.predict(
            symbol, bt_store, daily_result,
            horizon=HORIZON, visualize=False,
            covariate_type=cov_type or "ccl",
            verbose=False, skip_validation=True,
        )
    return daily_result, hourly_result


def _point_from_pred(dt, base, real, pred, quant, vol_prob, veto, scheme=None) -> dict:
    """从预测数组构造评估点；Neutral 时 delta_pred=0 → 无滑点（calc_net_metrics）。

    scheme 提供时使用 live signal_weight 加权方向（与 monthly / cascade 一致）。
    """
    from cascade.signal_contract import position_from_forecast
    _sig = position_from_forecast(pred, base, scheme=scheme)
    delta_pred = float(_sig["delta_pred"])
    delta_real = float(real[-1] - base)
    # 浮点压平：强制中性
    if veto and abs(delta_pred) < 1e-9:
        delta_pred = 0.0
    if veto:
        delta_pred = 0.0  # Neutral override always flats economic position
    dir_ok = bool(np.sign(delta_pred) == np.sign(delta_real)) if delta_real != 0 else True
    half = HORIZON // 2
    d12_pred = float(pred[half - 1] - base)
    d12_real = float(real[half - 1] - base)
    if veto:
        d12_pred = 0.0
    dir12_ok = bool(np.sign(d12_pred) == np.sign(d12_real)) if d12_real != 0 else True
    mae = float(np.mean(np.abs(pred - real)))
    safe_real = np.where(real == 0, 1e-8, np.abs(real))
    mape = float(np.mean(np.abs(pred - real) / safe_real) * 100)
    mae_h1 = float(np.mean(np.abs(pred[:half] - real[:half])))
    mae_h2 = float(np.mean(np.abs(pred[half:] - real[half:])))
    position_sign = float(np.sign(delta_pred))
    # 摩擦豁免：空仓不扣滑点（与 calc_net_metrics 一致）
    pnl = float(position_sign * delta_real) if position_sign != 0 else 0.0
    cov = 0
    if quant is not None and quant.ndim == 2 and quant.shape[1] >= 10:
        for t in range(HORIZON):
            if quant[t, 1] <= real[t] <= quant[t, 9]:
                cov += 1
    return {
        "cutoff": dt,
        "base": base,
        "pred_end": float(pred[-1]),
        "real_end": float(real[-1]),
        "delta_pred": delta_pred,
        "delta_real": delta_real,
        "dir_ok": dir_ok,
        "dir12_ok": dir12_ok,
        "mae": mae,
        "mape": mape,
        "mae_h1": mae_h1,
        "mae_h2": mae_h2,
        "coverage": cov,
        "pnl": pnl,
        "real_range": float(real.max() - real.min()),
        "vol_prob": vol_prob,
        "veto": veto,
    }


def _spike_stats(ok: list, track_switch: bool) -> dict:
    if len(ok) < 2:
        return {}
    ends = np.array([p["pred_end"] for p in ok], dtype=float)
    bases = np.array([p["base"] for p in ok], dtype=float)
    d_end = np.diff(ends)
    d_end_pct = d_end / (bases[1:] + 1e-8)
    spike_mask = np.abs(d_end_pct) >= 0.02
    vetos = np.array([bool(p.get("veto")) for p in ok], dtype=bool)
    switch = np.diff(vetos.astype(int)) != 0 if track_switch else np.zeros(len(d_end), dtype=bool)
    if len(switch) < len(spike_mask):
        switch = np.pad(switch, (0, len(spike_mask) - len(switch)))
    return {
        "n_pairs": int(len(d_end)),
        "mean_abs_d_end_pct": float(np.mean(np.abs(d_end_pct))),
        "p95_abs_d_end_pct": float(np.percentile(np.abs(d_end_pct), 95)),
        "max_abs_d_end_pct": float(np.max(np.abs(d_end_pct))),
        "n_spikes_ge_2pct": int(np.sum(spike_mask)),
        "n_spikes_on_veto_switch": int(np.sum(spike_mask & switch[: len(spike_mask)])),
    }


def _pack_result(symbol, mode, cov_label, n_eval, points_all) -> dict | None:
    ok = [p for p in points_all if "error" not in p]
    if not ok:
        return None
    tick = TICK_SIZES.get(symbol.lower(), 1.0)
    # 摩擦校验：中性点不得产生净亏损（滑点）
    net = metrics_from_backtest_points(ok, tick_size=tick, slippage_ticks=SLIPPAGE_TICKS)
    veto_flags = [bool(p.get("veto")) for p in ok]
    return {
        "symbol": symbol,
        "mode": mode,
        "cov_label": cov_label,
        "n_eval": n_eval,
        "n_ok": len(ok),
        "n_err": len(points_all) - len(ok),
        "veto_rate": float(np.mean(veto_flags)) if veto_flags else 0.0,
        "metrics": net,
        "spike_stats": _spike_stats(ok, track_switch=(mode != "off")),
        "points": ok,
    }


def run_symbol_shared_forecast(
    symbol: str,
    daily_model,
    hourly_model,
    vol_filter: VolRiskFilter,
    thr: float,
    oos_start: str,
    oos_end: str,
    step: int,
    checkpoint: dict | None = None,
    default_cov: str = "ha_body",
    ckpt_flush=None,
) -> dict | None:
    """
    共享 raw forecast 的成对回测（OFF + Neutral）。

    每个 cutoff 只跑一次 TimesFM(static scheme)：
      metrics_off ← raw
      metrics_on  ← flatten(raw) if veto else raw
    算力约减半；控制变量完美对齐。
    """
    store = DataStore(symbol)
    all_1h = store.get_main_contract_1h(limit=99999)
    daily_df = store.get_main_continuous(limit=99999)
    store.close()

    if all_1h.empty or len(all_1h) < CONTEXT_BARS + HORIZON:
        print(f"    SKIP {symbol}: 1H insufficient")
        return None

    all_1h = all_1h.copy()
    all_1h["dt"] = pd.to_datetime(all_1h["dt"])
    total = len(all_1h)
    oos_start_ts = pd.Timestamp(oos_start)
    oos_end_ts = pd.Timestamp(oos_end) + pd.Timedelta(hours=23, minutes=59)

    eval_indices = list(range(CONTEXT_BARS, total - HORIZON + 1, step))
    if not daily_df.empty:
        import bisect
        daily_dates = sorted(daily_df["dt"].astype(str).str[:10].tolist())
        min_daily_required = max(CONTEXT_DAYS - HORIZON_DAYS, 100)
        eval_indices = [
            idx for idx in eval_indices
            if bisect.bisect_right(daily_dates, str(all_1h["dt"].iloc[idx])[:10])
            >= min_daily_required
        ]
    eval_indices = [
        idx for idx in eval_indices
        if oos_start_ts <= all_1h["dt"].iloc[idx] <= oos_end_ts
    ]
    if not eval_indices:
        print(f"    SKIP {symbol}: no OOS eval points")
        return None

    scheme = get_scheme(symbol)
    if scheme is None:
        cov_type, cov_types, cov_label = default_cov, None, default_cov
    else:
        cov_type, cov_types, cov_label = resolve_cov(symbol)

    print(f"    SHARED-FORECAST cov={cov_label} n_eval={len(eval_indices)}")

    ckpt = checkpoint if checkpoint is not None else {}
    sym_key = symbol.lower()
    done_cutoffs = set(ckpt.get(sym_key, {}).get("done_cutoffs", []))
    points_off = list(ckpt.get(sym_key, {}).get("points_off", []))
    points_on = list(ckpt.get(sym_key, {}).get("points_on", []))
    # 已完成 cutoff 索引
    done_set = {p["cutoff"] for p in points_off if "cutoff" in p}

    for i, idx in enumerate(eval_indices):
        dt_ts = all_1h["dt"].iloc[idx]
        bar_ts = pd.Timestamp(dt_ts)
        dt = bar_ts.strftime("%Y-%m-%d")
        cutoff = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        # resume key: prefer bar_idx when present (T04 will standardize); date kept for display
        eval_key = f"{idx}:{cutoff}"
        if eval_key in done_set or dt in done_set:
            continue

        base = float(all_1h["close_price"].iloc[idx])
        real = all_1h["close_price"].iloc[idx + 1: idx + 1 + HORIZON].values.astype(np.float64)

        vol_prob = float("nan")
        veto = False
        hist = all_1h.iloc[: idx + 1].copy()
        try:
            decision = vol_filter.evaluate(hist)
            vol_prob = float(decision.vol_prob)
            veto = bool(decision.veto)
        except Exception as e:
            if i < 3:
                print(f"      vol eval fail @ {cutoff}: {e}")

        if i < 3 or i % 5 == 0:
            tag = "VETO" if veto else "keep"
            print(
                f"      [{i+1}/{len(eval_indices)}] {cutoff} {tag} p={vol_prob:.2f}",
                flush=True,
            )

        bt_store = BacktestDataStore(symbol, cutoff)
        try:
            # 只跑一次静态 scheme
            _daily, hourly_result = predict_one(
                symbol, bt_store, daily_model, hourly_model,
                cov_type, cov_types,
            )
            pred_raw = np.asarray(hourly_result.point_forecast, dtype=float).copy()
            quant_raw = hourly_result.quantile_forecast

            # OFF = raw; cutoff key = bar-exact eval_key (idx:timestamp) 防同日碰撞
            p_off = _point_from_pred(
                eval_key, base, real, pred_raw, quant_raw, vol_prob, veto=False, scheme=scheme,
            )
            p_off["cutoff_day"] = dt
            p_off["bar_idx"] = int(idx)
            p_off["veto"] = veto  # 记录当时是否会触发，但不 flatten
            p_off["applied_neutral"] = False

            # ON = flatten if veto else raw
            if veto:
                pred_on, quant_on = apply_neutral_override(pred_raw, base, quant_raw)
                p_on = _point_from_pred(
                    eval_key, base, real, pred_on, quant_on, vol_prob, veto=True, scheme=scheme,
                )
                p_on["applied_neutral"] = True
                # 摩擦豁免断言
                assert abs(p_on["delta_pred"]) < 1e-9, "neutral delta_pred must be 0"
                assert p_on["pnl"] == 0.0, "neutral pnl must be 0 (no friction)"
            else:
                p_on = _point_from_pred(
                    eval_key, base, real, pred_raw, quant_raw, vol_prob, veto=False, scheme=scheme,
                )
                p_on["applied_neutral"] = False
            p_on["cutoff_day"] = dt
            p_on["bar_idx"] = int(idx)

            points_off.append(p_off)
            points_on.append(p_on)
            done_set.add(eval_key)

            # checkpoint 每点更新（分品种原子写）
            if checkpoint is not None:
                checkpoint[sym_key] = {
                    "done_cutoffs": sorted(done_set),
                    "points_off": [
                        {k: v for k, v in p.items() if k != "pred_path"}
                        for p in points_off if "error" not in p
                    ],
                    "points_on": [
                        {k: v for k, v in p.items() if k != "pred_path"}
                        for p in points_on if "error" not in p
                    ],
                    "cov_label": cov_label,
                    "n_eval": len(eval_indices),
                }
                if ckpt_flush is not None:
                    ckpt_flush(sym_key, checkpoint[sym_key])
        except Exception as e:
            points_off.append({"cutoff": dt, "error": str(e)})
            points_on.append({"cutoff": dt, "error": str(e)})
            if i < 5:
                print(f"      ERROR {dt}: {e}")
        finally:
            try:
                bt_store.close()
            except Exception:
                pass

        if i > 0 and i % 5 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

    off_r = _pack_result(symbol, "off", cov_label, len(eval_indices), points_off)
    on_r = _pack_result(symbol, "neutral", cov_label, len(eval_indices), points_on)
    if off_r is None or on_r is None:
        return None

    # Domain-shift 警示
    vr = on_r["veto_rate"]
    domain_warn = None
    if vr < 0.02:
        domain_warn = "VETO_NEAR_ZERO — 可能分布漂移（阈值难触发）"
    elif vr > 0.95:
        domain_warn = "VETO_NEAR_ALL — 可能分布漂移（过度熔断）"
    if domain_warn:
        print(f"    [DOMAIN SHIFT WARN] {symbol.upper()}: {domain_warn} veto%={vr:.0%}")

    # 中性摩擦抽样校验
    neut_pts = [p for p in on_r["points"] if p.get("applied_neutral")]
    if neut_pts:
        sample = neut_pts[0]
        tick = TICK_SIZES.get(symbol.lower(), 1.0)
        m = metrics_from_backtest_points(
            [sample], tick_size=tick, slippage_ticks=SLIPPAGE_TICKS
        )
        assert m["NetPnL"] == 0.0 and m["EV"] == 0.0, (
            f"friction leak on neutral: {m}"
        )
        print(f"    [FRICTION OK] neutral sample NetPnL=0 EV=0")

    return {
        "off": off_r,
        "neutral": on_r,
        "domain_warn": domain_warn,
        "veto_rate": vr,
    }


def _load_universe(universe: str, eligibility_path: str) -> list[str]:
    elig_path = Path(eligibility_path)
    if not elig_path.exists():
        raise SystemExit(
            f"缺少准入文件 {elig_path}，请先: python scripts/universe_eligibility.py"
        )
    elig = json.loads(elig_path.read_text(encoding="utf-8"))
    if universe == "l1":
        return list(elig.get("l1_symbols", []))
    if universe == "l2":
        return list(elig.get("l2_symbols", []))
    return list(elig.get("all_eligible", []))


def main():
    parser = argparse.ArgumentParser(description="TimesFM 全链路 Vol Gating OOS 对比")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="显式品种列表（优先于 --universe）")
    parser.add_argument("--universe", choices=["l1", "l2", "all"], default=None,
                        help="从 eligibility JSON 取品种")
    parser.add_argument(
        "--eligibility",
        default="reports/phase1/universe_eligibility.json",
    )
    parser.add_argument(
        "--thr", type=float, default=None,
        help="全局 thr 覆盖；默认 r0=0.55，r1=用 pkl calibrated_thr",
    )
    parser.add_argument("--thr-chem", type=float, default=None,
                        help="能化板块 thr 覆盖")
    parser.add_argument("--thr-agri", type=float, default=None,
                        help="农产品板块 thr 覆盖")
    parser.add_argument("--oos-start", default=OOS_START)
    parser.add_argument("--oos-end", default=OOS_END)
    parser.add_argument("--step", type=int, default=STEP,
                        help=f"评估步长 (默认 {STEP})")
    parser.add_argument("--default-cov", default="ha_body",
                        help="L2 无 scheme 时的默认第二协变量")
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="分品种 checkpoint 目录（默认 <out-dir>/ckpt）",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="legacy 单文件 ckpt.json；若存在且 ckpt 目录为空则自动迁移",
    )
    parser.add_argument(
        "--report",
        default="reports/phase1/full_universe_neutral/summary.md",
    )
    parser.add_argument("--out-dir", default="reports/phase1/full_universe_neutral")
    parser.add_argument(
        "--vol-model-mode",
        choices=["r0", "r1"],
        default="r0",
        help="r0=全局 v2; r1=按板块路由 chem/agri pkl（black 显式用 R0）",
    )
    parser.add_argument(
        "--r0-model",
        default=DEFAULT_MODEL_PATH,
        help="R0 / black 回退显式路径（非 silent）",
    )
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.lower() for s in args.symbols]
    elif args.universe:
        symbols = _load_universe(args.universe, args.eligibility)
    else:
        symbols = list(DEFAULT_SYMBOLS)
    if not symbols:
        raise SystemExit("empty symbol list")

    # thr 默认：r0 固定 0.55；r1 默认读 pkl 校准阈值
    if args.thr is None and args.vol_model_mode == "r0":
        args.thr = DEFAULT_PROB_THRESHOLD

    ensure_dirs()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_sym_dir = out_dir / "by_symbol"
    by_sym_dir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    ckpt_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else out_dir / "ckpt"
    legacy_ckpt = (
        Path(args.checkpoint)
        if args.checkpoint
        else out_dir / "ckpt.json"
    )
    checkpoint = load_checkpoint_dir(ckpt_dir, legacy_file=legacy_ckpt)

    progress_path = out_dir / "progress.log"
    progress_path.write_text(
        f"START {datetime.now().isoformat()} symbols={symbols} "
        f"thr={args.thr} mode=shared_forecast ckpt_dir={ckpt_dir}\n",
        encoding="utf-8",
    )

    def log(msg: str):
        print(msg, flush=True)
        with open(progress_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def ckpt_flush(sym: str, payload: dict):
        save_symbol_checkpoint(ckpt_dir, sym, payload)

    def save_ckpt(sym: str | None = None):
        if sym is not None and sym in checkpoint:
            save_symbol_checkpoint(ckpt_dir, sym, checkpoint[sym])
        elif sym is None:
            for s, payload in checkpoint.items():
                if isinstance(payload, dict):
                    save_symbol_checkpoint(ckpt_dir, s, payload)

    log("=" * 60)
    log("  TimesFM Full-Chain Vol Gating (SHARED FORECAST)")
    log(f"  symbols={symbols} n={len(symbols)} thr={args.thr} "
        f"thr_chem={args.thr_chem} thr_agri={args.thr_agri}")
    log(f"  OOS={args.oos_start}..{args.oos_end} step={args.step}")
    log(f"  vol_model_mode={args.vol_model_mode} r0={args.r0_model}")
    log(f"  ckpt_dir={ckpt_dir} (per-symbol atomic)")
    log("  DOMAIN SHIFT: alert if veto%~0 or ~100 on non-train sectors")
    log("  FRICTION: position_sign=0 → slip=0 (verified per neutral sample)")
    log("  production default remains OFF")
    log("=" * 60)

    log("\n[1/4] Load TimesFM...")
    torch.set_float32_matmul_precision("high")
    daily_model = DailyModel()
    hourly_model = HourlyModel(shared_model=daily_model.model)
    log("  model ready")

    log("\n[2/4] Load VolRiskFilter(s)...")
    thr_policy = ThrPolicy.from_cli(
        thr=args.thr,
        thr_chem=args.thr_chem,
        thr_agri=args.thr_agri,
        allow_calibrated=True,
        load_operational_file=True,  # models/operational_thr.json
    )
    log(
        f"  thr_policy: global={thr_policy.global_cli} "
        f"sector_cli={dict(thr_policy.sector_cli)} "
        f"operational_file={dict(thr_policy.operational_map)}"
    )
    model_cache: dict = {}

    def vol_filter_for(sym: str) -> VolRiskFilter:
        filt = VolRiskFilter.bind_for_symbol(
            sym,
            mode=args.vol_model_mode,
            r0_path=args.r0_model,
            policy=thr_policy,
            cache=model_cache,
        )
        log(
            f"  {sym}: path={filt.model_path} sector={filt.sector} "
            f"thr={filt.threshold:.4f}({filt.threshold_source}) "
            f"cal={filt.calibrated_thr} op={filt.operational_thr}"
        )
        return filt

    # 预绑定：缺 pkl 立刻失败
    for sym in symbols:
        try:
            p = VolRiskFilter.resolve_model_path_for_symbol(
                sym, mode=args.vol_model_mode, r0_path=args.r0_model,
            )
            log(f"  resolve {sym} → {p}")
            vol_filter_for(sym)
        except Exception as e:
            raise SystemExit(f"vol model resolve/bind failed for {sym}: {e}") from e

    results = {"off": {}, "neutral": {}, "domain_warns": {}}

    log("\n[3/4] Shared-forecast paired run...")
    for sym in symbols:
        log(f"\n  === {sym.upper()} ===")
        try:
            vol_filter = vol_filter_for(sym)
            paired = run_symbol_shared_forecast(
                sym, daily_model, hourly_model, vol_filter, args.thr,
                args.oos_start, args.oos_end, args.step,
                checkpoint=checkpoint,
                default_cov=args.default_cov,
                ckpt_flush=ckpt_flush,
            )
            save_ckpt(sym)
            if paired is None:
                log(f"    no result")
                continue
            results["off"][sym] = {
                k: v for k, v in paired["off"].items() if k != "points"
            }
            results["off"][sym]["points"] = paired["off"]["points"]
            results["neutral"][sym] = {
                k: v for k, v in paired["neutral"].items() if k != "points"
            }
            results["neutral"][sym]["points"] = paired["neutral"]["points"]
            if paired.get("domain_warn"):
                results["domain_warns"][sym] = paired["domain_warn"]

            # per-symbol artifact（原子写）
            atomic_write_json(
                by_sym_dir / f"{sym}.json",
                {
                    "off": {k: v for k, v in paired["off"].items() if k != "points"},
                    "neutral": {
                        k: v for k, v in paired["neutral"].items() if k != "points"
                    },
                    "points_off": paired["off"]["points"],
                    "points_on": paired["neutral"]["points"],
                    "domain_warn": paired.get("domain_warn"),
                },
            )

            mo, mn = paired["off"]["metrics"], paired["neutral"]["metrics"]
            log(
                f"    OFF  PF={mo['PF']} EV={mo['EV']} MaxDD={mo['MaxDD']} NetPnL={mo.get('NetPnL')}"
            )
            log(
                f"    NEUT PF={mn['PF']} EV={mn['EV']} MaxDD={mn['MaxDD']} NetPnL={mn.get('NetPnL')} "
                f"veto={paired['veto_rate']:.0%}"
            )
        except Exception as e:
            log(f"    FATAL {sym}: {e}")
            traceback.print_exc()
            save_ckpt(sym)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    log("\n[4/4] Score & report (cascade.neutral_ab_report)...")
    done = [s for s in symbols if s in results["off"] and s in results["neutral"]]
    if not done:
        log("  no completed symbols — abort report")
        raise SystemExit(2)

    report_path = Path(args.report)
    score = score_and_write(
        done,
        results,
        report_path,
        meta={
            "thr": args.thr,
            "oos_start": args.oos_start,
            "oos_end": args.oos_end,
            "step": args.step,
            "progress_path": str(progress_path).replace("\\", "/"),
            "by_symbol_dir": str(by_sym_dir).replace("\\", "/"),
            "source": "fullchain",
            "vol_model_mode": args.vol_model_mode,
            "r0_model": args.r0_model,
            "thr": args.thr,
            "thr_chem": args.thr_chem,
            "thr_agri": args.thr_agri,
            "filters_bound": [
                {
                    "path": f.model_path,
                    "sector": f.sector,
                    "threshold": f.threshold,
                    "threshold_source": f.threshold_source,
                    "calibrated_thr": f.calibrated_thr,
                    "operational_thr": f.operational_thr,
                }
                for f in (
                    VolRiskFilter.bind_for_symbol(
                        s, mode=args.vol_model_mode, r0_path=args.r0_model,
                        policy=thr_policy, cache=model_cache,
                    )
                    for s in done
                )
            ],
        },
    )
    log(f"\nReport: {report_path}")
    log(f"VERDICT: {score.engineering_verdict}")
    log(f"GATE:    {score.production_gate}")
    log(f"R1:      {score.domain['r1_trigger']}")

    ok_exit = score.engineering_verdict in (
        "PASS_FULLCHAIN", "PASS_NEUTRAL_OVERLAY",
    )
    # 生产门禁不抬升 exit code；工程机制 PASS 即 0
    raise SystemExit(0 if ok_exit else 2)


if __name__ == "__main__":
    main()

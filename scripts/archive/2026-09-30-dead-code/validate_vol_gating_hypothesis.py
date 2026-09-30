#!/usr/bin/env python3
"""
Path 2 / 假设验证：高波期是否摧毁均值回归类信号的净 PF

核心假设:
  震荡/均值回归信号（RSI 状态、VOR 方向）在模型预测的「高波期」
  净 PF 显著劣于「低波期」。

方法（轻量，不跑 TimesFM）:
  1. IS (≤ train_end) 训练 Target-A 波动分类器（1h_v2 特征）
  2. 评估窗（默认真 OOS 2026-04~07，约 3 个月）上输出 P(high_vol)
  3. 用 RSI / VOR 构造可交易方向信号 → 持有 24H 收益 → 扣滑点净 PF
  4. 对比 Pred_High_Vol vs Pred_Low_Vol 的 PF / EV / MaxDD

成功标准（任一强成立即推进熔断器）:
  - PF_high < 1.0 且 PF_low >= 1.0，或
  - PF_low - PF_high >= 0.15，或
  - EV_high < 0 且 EV_low > 0

用法:
  python scripts/validate_vol_gating_hypothesis.py
  python scripts/validate_vol_gating_hypothesis.py --symbols sr fu i m
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from data.data_store import DataStore
from cascade.regime_features import (
    extract_1h_regime_features,
    EXPECTED_FEATURE_COLUMNS_V2,
    FEATURE_VERSION_V2,
)
from cascade.evaluation_metrics import calc_net_metrics
from config.backtest_config import TICK_SIZES, SLIPPAGE_TICKS

HORIZON = 24
TRAIN_END = "2026-03-31"
EVAL_START = "2026-04-01"
EVAL_END = "2026-07-31"
ABS_Q = 0.70
VOL_PROB_THR = 0.55  # 划分 high/low 预测集合的概率阈值
STEP = 6

# 均值回归类品种（当前 scheme 或历史主用）
DEFAULT_MR_SYMBOLS = ["sr", "fu", "i", "m"]  # rsi combo / vor


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
        print(f"  {symbol}: load fail {e}")
        return None


def future_abs_move(closes: np.ndarray, i: int) -> float | None:
    if i + HORIZON >= len(closes):
        return None
    c0 = closes[i]
    if c0 == 0:
        return None
    return abs((closes[i + HORIZON] - c0) / c0)


def future_return(closes: np.ndarray, i: int) -> float | None:
    if i + HORIZON >= len(closes):
        return None
    return float(closes[i + HORIZON] - closes[i])  # 价格点变动，配合 tick 滑点


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def vor_momentum(volume: pd.Series, oi: pd.Series, win: int = 20) -> pd.Series:
    vor = volume / oi.replace(0, np.nan)
    return vor.pct_change(win)


def mr_signal_rsi(rsi: float, lo: float = 30.0, hi: float = 70.0) -> int:
    """均值回归: 超卖做多, 超买做空, 否则空仓。"""
    if np.isnan(rsi):
        return 0
    if rsi <= lo:
        return 1
    if rsi >= hi:
        return -1
    return 0


def mr_signal_vor(vor_mom: float) -> int:
    """
    VOR 动量简化: 量仓比急升常伴随拥挤 → 反向（均值回归假设）。
    vor_mom 大 → 做空；vor_mom 小 → 做多。
    """
    if np.isnan(vor_mom):
        return 0
    if vor_mom > 0.15:
        return -1
    if vor_mom < -0.15:
        return 1
    return 0


def build_symbol_rows(symbol: str, step: int = STEP) -> pd.DataFrame | None:
    df = load_1h(symbol)
    if df is None or len(df) < 400:
        return None
    close_col = "close_price" if "close_price" in df.columns else "close"
    vol_col = "volume"
    oi_col = "open_interest"
    closes = df[close_col].values.astype(float)
    rsi = rsi_series(pd.Series(closes)).values
    vor_m = vor_momentum(df[vol_col], df[oi_col]).values

    feats = extract_1h_regime_features(df, version=FEATURE_VERSION_V2)
    cols = list(EXPECTED_FEATURE_COLUMNS_V2)
    rows = []
    for i in range(0, len(df) - HORIZON, step):
        fr = feats.iloc[i]
        if fr[cols].isna().any():
            continue
        am = future_abs_move(closes, i)
        ret = future_return(closes, i)
        if am is None or ret is None:
            continue
        rows.append({
            "symbol": symbol,
            "dt": df["dt"].iloc[i],
            "close": closes[i],
            "abs_move": am,
            "price_move": ret,
            "rsi": float(rsi[i]) if not np.isnan(rsi[i]) else np.nan,
            "vor_mom": float(vor_m[i]) if not np.isnan(vor_m[i]) else np.nan,
            **{c: float(fr[c]) for c in cols},
        })
    return pd.DataFrame(rows)


def train_vol_model(train_df: pd.DataFrame) -> tuple:
    cols = list(EXPECTED_FEATURE_COLUMNS_V2)
    q = float(train_df["abs_move"].quantile(ABS_Q))
    y = (train_df["abs_move"] >= q).astype(int).values
    X = train_df[cols].values
    sc = StandardScaler()
    Xs = sc.fit_transform(X)
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=40,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(Xs, y)
    return clf, sc, q, cols


def metrics_for_subset(dirs, moves, bases, tick) -> dict:
    dirs = np.asarray(dirs)
    if len(dirs) == 0:
        return {
            "n": 0, "n_active": 0, "PF": np.nan, "EV": np.nan,
            "MaxDD": np.nan, "DirAcc": np.nan, "WinRate": np.nan,
        }
    # 仅对有信号的交易计净 PF（空仓不进分母）
    active = dirs != 0
    if active.sum() == 0:
        return {
            "n": int(len(dirs)), "n_active": 0, "PF": np.nan, "EV": np.nan,
            "MaxDD": np.nan, "DirAcc": np.nan, "WinRate": np.nan,
        }
    m = calc_net_metrics(
        dirs[active],
        np.asarray(moves)[active],
        tick_size=tick,
        slippage_ticks=SLIPPAGE_TICKS,
        base_prices=np.asarray(bases)[active],
    )
    m["n"] = int(len(dirs))
    m["n_active"] = int(active.sum())
    return m


def evaluate_hypothesis(
    symbols: list[str],
    vol_thr: float = VOL_PROB_THR,
    train_end: str = TRAIN_END,
    eval_start: str = EVAL_START,
    eval_end: str = EVAL_END,
) -> dict:
    print("=== Path2 假设验证: 高波期 vs 均值回归信号净 PF ===")
    print(f"  symbols={symbols}")
    print(f"  train_end={train_end}  eval={eval_start}..{eval_end}")
    print(f"  vol_prob_thr={vol_thr}  feature={FEATURE_VERSION_V2}")

    panels = []
    for s in symbols:
        print(f"  build {s.upper()}...")
        p = build_symbol_rows(s)
        if p is not None and len(p):
            print(f"    rows={len(p)}")
            panels.append(p)
        else:
            print(f"    skip")
    if not panels:
        raise SystemExit("无数据")

    data = pd.concat(panels, ignore_index=True).sort_values("dt")
    train_end_ts = pd.Timestamp(train_end) + pd.Timedelta(hours=23, minutes=59)
    eval_start_ts = pd.Timestamp(eval_start)
    eval_end_ts = pd.Timestamp(eval_end) + pd.Timedelta(hours=23, minutes=59)

    train = data[data["dt"] <= train_end_ts]
    ev = data[(data["dt"] >= eval_start_ts) & (data["dt"] <= eval_end_ts)]
    print(f"  train n={len(train)}  eval n={len(ev)}")
    if len(train) < 500 or len(ev) < 50:
        raise SystemExit(f"样本不足 train={len(train)} eval={len(ev)}")

    clf, sc, q_abs, cols = train_vol_model(train)
    print(f"  IS abs_move q70={q_abs:.5f}  high_vol_rate_IS={(train['abs_move']>=q_abs).mean():.1%}")

    X_ev = sc.transform(ev[cols].values)
    proba = clf.predict_proba(X_ev)[:, 1]
    ev = ev.copy()
    ev["vol_prob"] = proba
    ev["pred_high"] = proba >= vol_thr

    # 真实标签对照（非决策，仅诊断）
    ev["true_high"] = ev["abs_move"] >= q_abs

    results = {
        "hypothesis": "MR signals destroy net PF in predicted high-vol regime",
        "train_end": train_end,
        "eval_start": eval_start,
        "eval_end": eval_end,
        "vol_prob_thr": vol_thr,
        "q_abs_is": q_abs,
        "n_train": len(train),
        "n_eval": len(ev),
        "pred_high_rate": float(ev["pred_high"].mean()),
        "symbols": {},
        "pooled": {},
        "verdict": None,
        "pass_hypothesis": False,
    }

    # 逐品种 + 汇总
    pooled_buckets = {
        "high": {"dirs_rsi": [], "moves": [], "bases": [], "ticks": []},
        "low": {"dirs_rsi": [], "moves": [], "bases": [], "ticks": []},
        "high_vor": {"dirs": [], "moves": [], "bases": [], "ticks": []},
        "low_vor": {"dirs": [], "moves": [], "bases": [], "ticks": []},
    }

    for sym in symbols:
        sub = ev[ev["symbol"] == sym]
        if len(sub) < 20:
            continue
        tick = TICK_SIZES.get(sym, 1.0)
        dirs_rsi = [mr_signal_rsi(r) for r in sub["rsi"].values]
        dirs_vor = [mr_signal_vor(v) for v in sub["vor_mom"].values]
        moves = sub["price_move"].values
        bases = sub["close"].values
        high = sub["pred_high"].values

        hi_m = metrics_for_subset(
            [d for d, h in zip(dirs_rsi, high) if h],
            [m for m, h in zip(moves, high) if h],
            [b for b, h in zip(bases, high) if h],
            tick,
        )
        lo_m = metrics_for_subset(
            [d for d, h in zip(dirs_rsi, high) if not h],
            [m for m, h in zip(moves, high) if not h],
            [b for b, h in zip(bases, high) if not h],
            tick,
        )
        hi_v = metrics_for_subset(
            [d for d, h in zip(dirs_vor, high) if h],
            [m for m, h in zip(moves, high) if h],
            [b for b, h in zip(bases, high) if h],
            tick,
        )
        lo_v = metrics_for_subset(
            [d for d, h in zip(dirs_vor, high) if not h],
            [m for m, h in zip(moves, high) if not h],
            [b for b, h in zip(bases, high) if not h],
            tick,
        )

        results["symbols"][sym] = {
            "n": len(sub),
            "pred_high_rate": float(high.mean()),
            "rsi_high": hi_m,
            "rsi_low": lo_m,
            "vor_high": hi_v,
            "vor_low": lo_v,
            "rsi_delta_PF": (
                float(lo_m["PF"] - hi_m["PF"])
                if hi_m["n"] and lo_m["n"] and hi_m["PF"] == hi_m["PF"] and lo_m["PF"] == lo_m["PF"]
                else None
            ),
        }
        print(
            f"  {sym.upper()}: RSI  high PF={hi_m['PF']} (n={hi_m['n_active']}/{hi_m['n']})  "
            f"low PF={lo_m['PF']} (n={lo_m['n_active']}/{lo_m['n']})  "
            f"ΔPF={results['symbols'][sym]['rsi_delta_PF']}"
        )

        for d, m, b, h in zip(dirs_rsi, moves, bases, high):
            key = "high" if h else "low"
            pooled_buckets[key]["dirs_rsi"].append(d)
            pooled_buckets[key]["moves"].append(m)
            pooled_buckets[key]["bases"].append(b)
            pooled_buckets[key]["ticks"].append(tick)
        for d, m, b, h in zip(dirs_vor, moves, bases, high):
            key = "high_vor" if h else "low_vor"
            pooled_buckets[key]["dirs"].append(d)
            pooled_buckets[key]["moves"].append(m)
            pooled_buckets[key]["bases"].append(b)
            pooled_buckets[key]["ticks"].append(tick)

    # 汇总：滑点用逐样本 tick 较难；用加权平均 tick
    def pooled_metrics(dirs, moves, bases, ticks):
        if not dirs:
            return {"n": 0}
        # 逐笔：净 pnl 后算 PF（因 tick 不同）
        net = []
        for d, mv, base, tick in zip(dirs, moves, bases, ticks):
            slip = tick * SLIPPAGE_TICKS
            if d == 1:
                net.append(mv - slip)
            elif d == -1:
                net.append(-mv - slip)
            else:
                net.append(0.0)
        net = np.array(net)
        active = np.array(dirs) != 0
        # 仅对有信号统计主指标，同时报告全样本
        if active.sum() == 0:
            return {"n": len(dirs), "n_active": 0, "PF": np.nan, "EV": np.nan}
        net_a = net[active]
        pos = net_a[net_a > 0].sum()
        neg = abs(net_a[net_a < 0].sum())
        pf = float(pos / neg) if neg > 0 else (99.99 if pos > 0 else 0.0)
        # MaxDD: compound equity (2026-08-21 fix: cumprod 替代 cumsum)
        bases_a = np.array(bases)[active]
        rel = net_a / (bases_a + 1e-8)
        equity = np.empty(len(rel) + 1, dtype=float)
        equity[0] = 1.0
        equity[1:] = np.cumprod(1.0 + rel)
        peak_eq = np.maximum.accumulate(equity)
        with np.errstate(divide="ignore", invalid="ignore"):
            dd = np.where(peak_eq > 1e-12, (equity - peak_eq) / peak_eq, 0.0)
        max_dd = max(float(dd.min()), -1.0) if dd.size else 0.0
        return {
            "n": len(dirs),
            "n_active": int(active.sum()),
            "PF": round(pf, 3) if pf != 99.99 else 99.99,
            "EV": round(float(net_a.mean()), 4),
            "MaxDD": round(max_dd, 4),
            "WinRate": round(float((net_a > 0).mean()), 4),
        }

    rsi_high = pooled_metrics(
        pooled_buckets["high"]["dirs_rsi"],
        pooled_buckets["high"]["moves"],
        pooled_buckets["high"]["bases"],
        pooled_buckets["high"]["ticks"],
    )
    rsi_low = pooled_metrics(
        pooled_buckets["low"]["dirs_rsi"],
        pooled_buckets["low"]["moves"],
        pooled_buckets["low"]["bases"],
        pooled_buckets["low"]["ticks"],
    )
    vor_high = pooled_metrics(
        pooled_buckets["high_vor"]["dirs"],
        pooled_buckets["high_vor"]["moves"],
        pooled_buckets["high_vor"]["bases"],
        pooled_buckets["high_vor"]["ticks"],
    )
    vor_low = pooled_metrics(
        pooled_buckets["low_vor"]["dirs"],
        pooled_buckets["low_vor"]["moves"],
        pooled_buckets["low_vor"]["bases"],
        pooled_buckets["low_vor"]["ticks"],
    )

    results["pooled"] = {
        "rsi_pred_high_vol": rsi_high,
        "rsi_pred_low_vol": rsi_low,
        "vor_pred_high_vol": vor_high,
        "vor_pred_low_vol": vor_low,
    }

    print("\n=== POOLED RSI mean-reversion ===")
    print(f"  HIGH vol pred: {rsi_high}")
    print(f"  LOW  vol pred: {rsi_low}")
    print("=== POOLED VOR mean-reversion ===")
    print(f"  HIGH vol pred: {vor_high}")
    print(f"  LOW  vol pred: {vor_low}")

    # 假设判定（以 RSI 主，VOR 辅）
    reasons = []
    ok = False
    pf_h, pf_l = rsi_high.get("PF"), rsi_low.get("PF")
    ev_h, ev_l = rsi_high.get("EV"), rsi_low.get("EV")
    if pf_h == pf_h and pf_l == pf_l:
        if pf_h < 1.0 and pf_l >= 1.0:
            ok = True
            reasons.append(f"RSI: PF_high={pf_h}<1 且 PF_low={pf_l}>=1")
        if (pf_l - pf_h) >= 0.15:
            ok = True
            reasons.append(f"RSI: PF_low - PF_high = {pf_l - pf_h:.3f} >= 0.15")
    if ev_h == ev_h and ev_l == ev_l:
        if ev_h < 0 and ev_l > 0:
            ok = True
            reasons.append(f"RSI: EV_high={ev_h}<0 且 EV_low={ev_l}>0")

    # VOR 辅助
    pf_vh, pf_vl = vor_high.get("PF"), vor_low.get("PF")
    if pf_vh == pf_vh and pf_vl == pf_vl and (pf_vl - pf_vh) >= 0.15:
        ok = True
        reasons.append(f"VOR: PF_low - PF_high = {pf_vl - pf_vh:.3f} >= 0.15")

    if not ok:
        reasons.append("未满足 PF/EV 差值门槛 → 假设不成立或证据不足")

    results["pass_hypothesis"] = ok
    results["reasons"] = reasons
    results["verdict"] = "HYPOTHESIS_SUPPORTED" if ok else "HYPOTHESIS_REJECTED"
    results["next_action"] = (
        "IMPLEMENT_VOL_CIRCUIT_BREAKER"
        if ok
        else "ABORT_PATH2_REPORT_ONLY"
    )

    print(f"\n=== VERDICT: {results['verdict']} ===")
    for r in reasons:
        print(f"  - {r}")
    print(f"  next: {results['next_action']}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Path2 高波熔断假设验证")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_MR_SYMBOLS)
    parser.add_argument("--vol-thr", type=float, default=VOL_PROB_THR)
    parser.add_argument("--train-end", default=TRAIN_END)
    parser.add_argument("--eval-start", default=EVAL_START)
    parser.add_argument("--eval-end", default=EVAL_END)
    parser.add_argument(
        "--report",
        default="reports/phase1/path2_vol_gating_hypothesis.md",
    )
    args = parser.parse_args()

    res = evaluate_hypothesis(
        [s.lower() for s in args.symbols],
        vol_thr=args.vol_thr,
        train_end=args.train_end,
        eval_start=args.eval_start,
        eval_end=args.eval_end,
    )

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    rh = res["pooled"]["rsi_pred_high_vol"]
    rl = res["pooled"]["rsi_pred_low_vol"]
    lines = [
        "# Path 2 假设验证：高波期 vs 均值回归净 PF",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**裁决**: `{res['verdict']}`",
        f"**下一步**: {res['next_action']}",
        f"**评估窗**: {res['eval_start']} ~ {res['eval_end']} (真 OOS 段)",
        f"**训练窗**: ≤ {res['train_end']}",
        f"**Vol_Prob 阈值**: {res['vol_prob_thr']}",
        f"**品种**: {res.get('symbols') and list(res['symbols'].keys())}",
        "",
        "## 假设",
        "",
        "震荡/均值回归信号（RSI 状态反转、VOR 反向）在 **预测高波期** 净 PF 显著劣于低波期。",
        "",
        "## 汇总（RSI 均值回归信号，扣滑点）",
        "",
        "| Bucket | n | n_active | PF | EV | MaxDD | WinRate |",
        "|--------|--:|---------:|---:|---:|------:|--------:|",
        f"| Pred_High_Vol | {rh.get('n')} | {rh.get('n_active')} | {rh.get('PF')} | {rh.get('EV')} | {rh.get('MaxDD')} | {rh.get('WinRate')} |",
        f"| Pred_Low_Vol | {rl.get('n')} | {rl.get('n_active')} | {rl.get('PF')} | {rl.get('EV')} | {rl.get('MaxDD')} | {rl.get('WinRate')} |",
        "",
        "## 汇总（VOR 反向信号）",
        "",
        f"- High: {res['pooled']['vor_pred_high_vol']}",
        f"- Low: {res['pooled']['vor_pred_low_vol']}",
        "",
        "## 分品种 RSI",
        "",
    ]
    for sym, s in res["symbols"].items():
        lines.append(
            f"- **{sym.upper()}**: high PF={s['rsi_high'].get('PF')} "
            f"low PF={s['rsi_low'].get('PF')} ΔPF={s.get('rsi_delta_PF')}"
        )
    lines.extend([
        "",
        "## 判定理由",
        "",
    ])
    for r in res["reasons"]:
        lines.append(f"- {r}")
    lines.extend([
        "",
        "## 说明",
        "",
        "- 本验证使用 **RSI/VOR 可交易代理信号**，非完整 TimesFM+XReg；用于验证「高波期伤害均值回归」经济逻辑。",
        "- 若假设成立，将实施 **Volatility Gating / Vol Circuit Breaker**（默认 OFF）。",
        "- 若假设不成立，**中止 Path2**，不安装生产熔断器。",
        "",
        f"JSON: `{report.with_suffix('.json')}`",
        "",
    ])
    report.write_text("\n".join(lines), encoding="utf-8")
    report.with_suffix(".json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n报告: {report}")

    # task_state
    ts_path = project_root / "task_state.json"
    state = {}
    if ts_path.exists():
        try:
            state = json.loads(ts_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["phase"] = "Path2_hypothesis"
    state["status"] = res["verdict"]
    state["path2_hypothesis"] = {
        "pass": res["pass_hypothesis"],
        "verdict": res["verdict"],
        "next_action": res["next_action"],
        "rsi_high_PF": rh.get("PF"),
        "rsi_low_PF": rl.get("PF"),
        "report": str(report).replace("\\", "/"),
    }
    ts_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    raise SystemExit(0 if res["pass_hypothesis"] else 2)


if __name__ == "__main__":
    main()

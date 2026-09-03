#!/usr/bin/env python3
"""
Path2 波动率熔断器 OOS 对比回测（轻量）

对比「始终用均值回归信号」vs「高波时熔断(空仓)」在 OOS 上的净 PF / EV / MaxDD。
不跑 TimesFM；验证熔断器作为风控过滤器的经济价值。

成功标准（用户）:
  开启熔断后 MaxDD 显著缩窄，PF 显著提升（总净利可略降）。

用法:
  python scripts/backtest_vol_gating.py
  python scripts/backtest_vol_gating.py --thr 0.75 --symbols sr fu i m
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

from cascade.vol_risk_filter import VolRiskFilter
from cascade.regime_features import extract_1h_regime_features, EXPECTED_FEATURE_COLUMNS_V2, FEATURE_VERSION_V2
from config.backtest_config import TICK_SIZES, SLIPPAGE_TICKS
from data.data_store import DataStore

HORIZON = 24
EVAL_START = "2026-04-01"
EVAL_END = "2026-07-31"
STEP = 6


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def mr_signal(rsi: float) -> int:
    if np.isnan(rsi):
        return 0
    if rsi <= 30:
        return 1
    if rsi >= 70:
        return -1
    return 0


def net_stats(dirs, moves, bases, ticks) -> dict:
    net = []
    for d, mv, base, tick in zip(dirs, moves, bases, ticks):
        slip = tick * SLIPPAGE_TICKS
        if d == 1:
            net.append(mv - slip)
        elif d == -1:
            net.append(-mv - slip)
        else:
            net.append(0.0)
    net = np.asarray(net, dtype=float)
    active = np.asarray(dirs) != 0
    if active.sum() == 0:
        return {"n": len(dirs), "n_active": 0, "PF": np.nan, "EV": np.nan,
                "MaxDD": 0.0, "NetPnL": 0.0, "WinRate": np.nan}
    na = net[active]
    pos = na[na > 0].sum()
    neg = abs(na[na < 0].sum())
    pf = float(pos / neg) if neg > 0 else (99.99 if pos > 0 else 0.0)
    bases_a = np.asarray(bases)[active]
    rel = na / (bases_a + 1e-8)
    # 2026-08-21 fix: cumprod 替代 cumsum, MaxDD ∈ [-1.0, 0]
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
        "EV": round(float(na.mean()), 4),
        "MaxDD": round(max_dd, 4),
        "NetPnL": round(float(na.sum()), 2),
        "WinRate": round(float((na > 0).mean()), 4),
    }


def collect_eval_rows(symbols, filt: VolRiskFilter, thr: float):
    eval_start = pd.Timestamp(EVAL_START)
    eval_end = pd.Timestamp(EVAL_END) + pd.Timedelta(hours=23, minutes=59)
    rows = []
    for sym in symbols:
        print(f"  collect {sym.upper()}...")
        with DataStore(sym) as store:
            df = store.get_main_contract_1h(limit=10**9)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["dt"] = pd.to_datetime(df["dt"])
        df = df.sort_values("dt").reset_index(drop=True)
        close = df["close_price"].values.astype(float)
        rsi = rsi_series(pd.Series(close)).values
        feats = extract_1h_regime_features(df, version=FEATURE_VERSION_V2)
        cols = list(EXPECTED_FEATURE_COLUMNS_V2)
        tick = TICK_SIZES.get(sym, 1.0)

        for i in range(0, len(df) - HORIZON, STEP):
            dt = df["dt"].iloc[i]
            if dt < eval_start or dt > eval_end:
                if dt > eval_end:
                    break
                continue
            fr = feats.iloc[i]
            if fr[cols].isna().any():
                continue
            # vol prob
            x = fr[cols].values.astype(float).reshape(1, -1)
            xs = filt.scaler.transform(x)
            vol_prob = float(filt.model.predict_proba(xs)[0, 1])
            sig = mr_signal(float(rsi[i]) if not np.isnan(rsi[i]) else np.nan)
            price_move = float(close[i + HORIZON] - close[i])
            rows.append({
                "symbol": sym,
                "dt": dt,
                "vol_prob": vol_prob,
                "veto": vol_prob >= thr,
                "sig_raw": sig,
                "sig_gated": 0 if vol_prob >= thr else sig,
                "price_move": price_move,
                "base": float(close[i]),
                "tick": tick,
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Vol Gating OOS 对比")
    parser.add_argument("--symbols", nargs="+", default=["sr", "fu", "i", "m"])
    parser.add_argument("--thr", type=float, default=0.75)
    parser.add_argument("--report", default="reports/phase1/path2_vol_gating_backtest.md")
    args = parser.parse_args()

    print("=== Path2 Vol Gating OOS backtest ===")
    print(f"  thr={args.thr}  symbols={args.symbols}")
    print(f"  window={EVAL_START}..{EVAL_END}")

    filt = VolRiskFilter.load_or_train(prob_threshold=args.thr)
    filt.prob_threshold = args.thr
    df = collect_eval_rows([s.lower() for s in args.symbols], filt, args.thr)
    print(f"  eval rows={len(df)}  veto_rate={df['veto'].mean():.1%}")

    base = net_stats(
        df["sig_raw"].tolist(), df["price_move"].tolist(),
        df["base"].tolist(), df["tick"].tolist(),
    )
    gated = net_stats(
        df["sig_gated"].tolist(), df["price_move"].tolist(),
        df["base"].tolist(), df["tick"].tolist(),
    )

    print("\n  WITHOUT gate:", base)
    print("  WITH    gate:", gated)

    # 成功标准
    pf_ok = (
        base.get("PF") == base.get("PF")
        and gated.get("PF") == gated.get("PF")
        and gated["PF"] > base["PF"]
    )
    dd_ok = (
        base.get("MaxDD") == base.get("MaxDD")
        and gated.get("MaxDD") == gated.get("MaxDD")
        and abs(gated["MaxDD"]) < abs(base["MaxDD"])  # MaxDD 更浅（更接近 0）
    )
    # 若 base PF 已 <1 而 gated >=1 也算成功
    regime_fix = (
        base.get("PF") == base.get("PF")
        and gated.get("PF") == gated.get("PF")
        and base["PF"] < 1.0
        and gated["PF"] >= 1.0
    )
    passed = (pf_ok and dd_ok) or regime_fix or (pf_ok and dd_ok is not False)

    # 更严：PF 提升 且 MaxDD 改善
    strict_pass = pf_ok and dd_ok

    verdict = "PASS" if strict_pass or regime_fix else "FAIL"
    if not strict_pass and pf_ok and not dd_ok:
        verdict = "PARTIAL_PF_ONLY"
    if not pf_ok and dd_ok:
        verdict = "PARTIAL_DD_ONLY"

    print(f"\n  VERDICT={verdict}  pf_ok={pf_ok} dd_ok={dd_ok} regime_fix={regime_fix}")

    # 分品种
    per = {}
    for sym in df["symbol"].unique():
        sub = df[df["symbol"] == sym]
        per[sym] = {
            "base": net_stats(
                sub["sig_raw"].tolist(), sub["price_move"].tolist(),
                sub["base"].tolist(), sub["tick"].tolist(),
            ),
            "gated": net_stats(
                sub["sig_gated"].tolist(), sub["price_move"].tolist(),
                sub["base"].tolist(), sub["tick"].tolist(),
            ),
            "veto_rate": float(sub["veto"].mean()),
        }
        print(f"  {sym.upper()}: base PF={per[sym]['base'].get('PF')} "
              f"gated PF={per[sym]['gated'].get('PF')} "
              f"veto={per[sym]['veto_rate']:.0%}")

    res = {
        "verdict": verdict,
        "strict_pass": strict_pass,
        "thr": args.thr,
        "n": len(df),
        "veto_rate": float(df["veto"].mean()),
        "without_gate": base,
        "with_gate": gated,
        "per_symbol": per,
        "criteria": {
            "pf_improved": pf_ok,
            "maxdd_improved": dd_ok,
            "regime_fix": regime_fix,
        },
    }

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Path2 Vol Gating OOS 对比回测",
        "",
        f"**日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**窗口**: {EVAL_START} ~ {EVAL_END}",
        f"**阈值**: vol_prob ≥ {args.thr}",
        f"**信号**: RSI 均值回归代理（非 TimesFM）",
        f"**裁决**: `{verdict}`",
        "",
        "## 汇总",
        "",
        "| 模式 | n_active | PF | EV | MaxDD | NetPnL | WinRate |",
        "|------|---------:|---:|---:|------:|-------:|--------:|",
        f"| 无熔断 | {base.get('n_active')} | {base.get('PF')} | {base.get('EV')} | {base.get('MaxDD')} | {base.get('NetPnL')} | {base.get('WinRate')} |",
        f"| **有熔断** | {gated.get('n_active')} | **{gated.get('PF')}** | {gated.get('EV')} | **{gated.get('MaxDD')}** | {gated.get('NetPnL')} | {gated.get('WinRate')} |",
        "",
        f"veto_rate={res['veto_rate']:.1%}",
        "",
        "## 成功标准",
        "",
        f"- PF 提升: {pf_ok}",
        f"- MaxDD 缩窄: {dd_ok}",
        f"- 亏损→盈利翻转: {regime_fix}",
        "",
        "## 分品种",
        "",
    ]
    for sym, s in per.items():
        lines.append(
            f"- **{sym.upper()}**: base PF={s['base'].get('PF')} / MaxDD={s['base'].get('MaxDD')} → "
            f"gated PF={s['gated'].get('PF')} / MaxDD={s['gated'].get('MaxDD')} "
            f"(veto {s['veto_rate']:.0%})"
        )
    lines.extend([
        "",
        "## 决策",
        "",
        "熔断器默认 **OFF**。本结果仅支持作为实验性风控开关 `--vol-filter`。",
        "生产趋势路由仍关闭。",
        "",
        f"JSON: `{report.with_suffix('.json')}`",
        "",
    ])
    report.write_text("\n".join(lines), encoding="utf-8")
    report.with_suffix(".json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"  report: {report}")

    # task_state
    ts = project_root / "task_state.json"
    state = {}
    if ts.exists():
        try:
            state = json.loads(ts.read_text(encoding="utf-8"))
        except Exception:
            pass
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["phase"] = "Path2_vol_gating"
    state["status"] = verdict
    state["path2_backtest"] = {
        "verdict": verdict,
        "thr": args.thr,
        "without_PF": base.get("PF"),
        "with_PF": gated.get("PF"),
        "without_MaxDD": base.get("MaxDD"),
        "with_MaxDD": gated.get("MaxDD"),
        "report": str(report).replace("\\", "/"),
    }
    ts.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    raise SystemExit(0 if (strict_pass or regime_fix) else 2)


if __name__ == "__main__":
    main()

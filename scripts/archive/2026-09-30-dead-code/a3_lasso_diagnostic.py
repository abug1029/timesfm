"""
A3-Lasso 诊断: 弱信号品种协变量通道稀疏线性信号检测 (无 TimesFM)

目的 (2026-08-30, SNR 报告方向 4 廉价前置诊断):
  检验"协变量 -> 未来24bar价格变动"是否存在 Lasso 可捕捉的稀疏线性信号。
  零信号 (OOS IC~0, PF<1) 则生产级 XReg-Lasso 改造直接 DOA, 节省全量 walk-forward。
  诊断只能做方向参考 (200pt 教训), 最终裁决仍需生产管线全量。

设计:
  - 特征 7 维: daily_slope, hourly_slope, ha_body, rsi_state, hour_sin, hour_cos, dow
  - 目标 y = close[t+24] - close[t] (与生产 walk-forward 同口径)
  - 训练窗 480 bars; 评估点每 24 bars 一个; Lasso(1.0) vs Ridge(0.1) vs sign(slope)
  - 摩擦: SLIPPAGE_TICKS=2 双边, tick_size 按 backtest_config
"""
import sys
import pathlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from data.data_store import DataStore
from config.backtest_config import TICK_SIZES, SLIPPAGE_TICKS
from cascade.features import calc_hourly_slope, calc_rsi_state, calc_ha_body_direction

SYMBOLS = ["jm", "ma", "ur", "fg", "cf", "ao"]
TRAIN_WINDOW = 480
HORIZON = 24
EVAL_STEP = 24
MAX_EVALS = 400


def build_features(df_1h, daily_closes):
    """7 维特征矩阵 + 24bar 目标 (全序列向量化, 索引对齐 df_1h 行)"""
    closes = df_1h["close_price"].values.astype(float)
    n = len(closes)
    feats = {}

    # daily_slope: 日线 22bar 斜率 (最后值 ffill 到 1H)
    ds = np.zeros(n)
    if daily_closes is not None and len(daily_closes) > 23:
        d = pd.Series(daily_closes)
        dsl = np.zeros(len(d))
        for i in range(23, len(d)):
            w = d.iloc[i-23:i+1].values
            if w[0] > 0:
                x = np.arange(24, dtype=float)
                dsl[i] = np.polyfit(x, w, 1)[0] / w[0]
        ds[:] = dsl[-1] if len(dsl) else 0.0
    feats["daily_slope"] = ds

    # hourly_slope
    hs = calc_hourly_slope(closes, window=24)
    feats["hourly_slope"] = hs.values if hasattr(hs, "values") else np.asarray(hs)

    # ha_body / rsi_state
    feats["ha_body"] = calc_ha_body_direction(df_1h)
    feats["rsi_state"] = calc_rsi_state(closes)

    # 时间特征
    dts = pd.to_datetime(df_1h["dt"])
    feats["hour_sin"] = np.sin(2 * np.pi * dts.dt.hour.values / 24)
    feats["hour_cos"] = np.cos(2 * np.pi * dts.dt.hour.values / 24)
    feats["dow"] = dts.dt.dayofweek.values.astype(float)

    X = np.column_stack([np.nan_to_num(feats[k].astype(float)) for k in
                         ["daily_slope", "hourly_slope", "ha_body", "rsi_state",
                          "hour_sin", "hour_cos", "dow"]])
    # y: 24bar 变动, 末尾 horizon 个无法计算
    y = np.full(n, np.nan)
    y[:-HORIZON] = closes[HORIZON:] - closes[:-HORIZON]
    return X, y


def run_variety(symbol):
    """单品种 walk-forward 诊断"""
    from sklearn.linear_model import Lasso, Ridge
    with DataStore(symbol) as store:
        df_1h = store.get_main_contract_1h(limit=12000)
        daily = store.get_main_continuous(limit=600)
    if df_1h is None or len(df_1h) < TRAIN_WINDOW + HORIZON + 100:
        n1 = 0 if df_1h is None else len(df_1h)
        return {"symbol": symbol, "status": "insufficient_data", "n_1h": n1}
    dc = daily["close_price"].values.astype(float) if daily is not None and len(daily) > 0 else None

    X, y = build_features(df_1h, dc)
    n = len(y)
    tick = TICK_SIZES.get(symbol, 1.0)
    slip = tick * SLIPPAGE_TICKS

    evals = []
    t = n - HORIZON - 1
    while t - TRAIN_WINDOW >= 0 and len(evals) < MAX_EVALS:
        evals.append(t)
        t -= EVAL_STEP
    evals.reverse()

    preds = {"lasso": [], "ridge": [], "slope": []}
    actuals = []
    for t in evals:
        Xtr, ytr = X[t-TRAIN_WINDOW:t-HORIZON], y[t-TRAIN_WINDOW:t-HORIZON]
        mask = ~np.isnan(ytr)
        Xtr, ytr = Xtr[mask], ytr[mask]
        mu, sd = Xtr.mean(0), Xtr.std(0)
        sd[sd < 1e-10] = 1.0
        Xs = (Xtr - mu) / sd
        ys_sd = max(ytr.std(), 1e-8)
        for name in ("lasso", "ridge"):
            if name == "lasso":
                mdl = Lasso(alpha=1.0 * ys_sd, max_iter=2000)
            else:
                mdl = Ridge(alpha=0.1)
            mdl.fit(Xs, ytr / ys_sd)
            xs = (X[t] - mu) / sd
            p = mdl.predict(xs.reshape(1, -1))[0] * ys_sd
            preds[name].append(p)
        preds["slope"].append(X[t, 0])
        actuals.append(y[t])

    return {
        "symbol": symbol, "status": "ok",
        "n_evals": len(evals),
        "tick": tick, "slip": slip,
        "preds": preds, "actuals": actuals,
    }


def score(preds, actuals, slip):
    """PF/EV/IC: 与 evaluation_metrics 同口径 (净 PF, EV_ratio 换 IC)"""
    p = np.array(preds, dtype=float)
    a = np.array(actuals, dtype=float)
    net = np.sign(p) * a - slip
    pos = net[net > 0]
    neg = net[net < 0]
    gp = float(pos.sum()) if pos.size else 0.0
    gl = float(abs(neg.sum())) if neg.size else 0.0
    pf = gp / gl if gl > 0 else (99.99 if gp > 0 else 0.0)
    ev = float(net.mean()) if len(net) else 0.0
    if p.std() > 1e-10 and a.std() > 1e-10:
        ic = float(np.corrcoef(p, a)[0, 1])
    else:
        ic = 0.0
    return pf, ev, ic


def main():
    rows = []
    for sym in SYMBOLS:
        r = run_variety(sym)
        if r.get("status") != "ok":
            rows.append({k: r.get(k) for k in ("symbol", "status", "n_1h")})
            print(f"[SKIP] {sym}: {r.get('status')}")
            continue
        row = {"symbol": sym.upper(), "n": r["n_evals"]}
        for name in ("lasso", "ridge", "slope"):
            pf, ev, ic = score(r["preds"][name], r["actuals"], r["slip"])
            row[f"{name}_pf"] = round(pf, 3)
            row[f"{name}_ev"] = round(ev, 3)
            row[f"{name}_ic"] = round(ic, 4)
        rows.append(row)
        print(f"[{sym.upper()}] n={r['n_evals']} | "
              f"Lasso PF={row['lasso_pf']} EV={row['lasso_ev']} IC={row['lasso_ic']} | "
              f"Ridge PF={row['ridge_pf']} EV={row['ridge_ev']} IC={row['ridge_ic']} | "
              f"slope PF={row['slope_pf']}")
    import json
    out = pathlib.Path("reports/research/20260830_a3_lasso_diagnostic.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print()
    print(f"saved: {out}")


if __name__ == "__main__":
    main()

"""A2-P1 LGBM 特征工程: 12 维宽特征池 (9 市场 + 3 TimesFM)。"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from .features import (
    calc_hourly_slope, calc_pca_momentum, calc_rsi_state,
    calc_oi_pct_change, calc_rolling_hurst, _calc_atr,
)
from .regime_features import extract_1h_regime_features, FEATURE_VERSION_V2
from config.backtest_config import STEP, CONTEXT_BARS, HORIZON as _BT_HORIZON

# VolRiskFilter: 模块级占位 (测试 monkeypatch 用), 运行时延迟绑定
try:
    from .vol_risk_filter import VolRiskFilter  # noqa: F401
except Exception:
    VolRiskFilter = None  # type: ignore


def _daily_slope_at(df_daily: pd.DataFrame, t_dt: pd.Timestamp, lookback: int = 5) -> float:
    """t 时刻的日线滚动斜率 (归一化 %/天)。仅用 t 之前日线, 无穿越。"""
    if df_daily.empty:
        return 0.0
    dt_col = "dt" if "dt" in df_daily.columns else "date"
    # 将 dt 列转为 Timestamp 以兼容字符串和 datetime 输入
    daily_dates = pd.to_datetime(df_daily[dt_col], errors="coerce")
    daily = df_daily[daily_dates <= t_dt].copy()
    if len(daily) < lookback + 1:
        return 0.0
    closes = daily["close_price"].values.astype(float)
    window = closes[-(lookback + 1):]
    if window[0] == 0 or np.any(np.isnan(window)):
        return 0.0
    x = np.arange(len(window), dtype=float)
    slope = np.polyfit(x, window, 1)[0] / window[0]
    return float(slope)


def extract_market_features_at_bar(
    df_1h: pd.DataFrame,
    df_daily: pd.DataFrame,
    t_idx: int,
    symbol: str,
    vol_filter=None,
    precomputed: dict | None = None,
) -> Dict[str, float]:
    """
    在 1H bar t_idx 处抽取 9 维市场特征 (无 TimesFM 依赖)。
    所有计算仅用 df_1h[:t_idx+1] 与 df_daily[<=t_dt], 防穿越。

    precomputed: 可选。含预计算的全序列安全特征 (hurst/hourly_slope/rsi_state/
                 oi_pct_change 为 np.ndarray 全序列, daily_slope 为 {t_idx: val} 字典)。
                 提供时按索引/key O(1) 取值; 未提供时回退切片计算 (向后兼容)。
                 pca_momentum/vol_prob 始终切片 (pca 全局 fitting 防穿越 / vol 涉及模型)。
    """
    closes = df_1h["close_price"].values.astype(float)[: t_idx + 1]
    t_dt = pd.Timestamp(df_1h["dt"].iloc[t_idx])
    pc = precomputed or {}

    # 1. daily_slope (安全: 纯滚动; 字典 key=t_idx 查找防越界)
    if "daily_slope" in pc:
        daily_slope = float(pc["daily_slope"][t_idx])
    else:
        daily_slope = _daily_slope_at(df_daily, t_dt)

    # 2. hourly_slope (安全: window=24 滚动; np.ndarray 位置索引)
    if "hourly_slope" in pc:
        hourly_slope = float(pc["hourly_slope"][t_idx])
    else:
        hourly_slope = float(calc_hourly_slope(closes, window=24).iloc[-1])

    # 3. pca_momentum (危险: StandardScaler+PCA 全局 fitting, 必须切片 closes, 不进 precomputed)
    pca_momentum = float(calc_pca_momentum(closes, periods=[5, 9, 14, 21], squash=True)[-1])

    # 4. rsi_state (安全: 固定阈值离散化; np.ndarray 位置索引)
    if "rsi_state" in pc:
        rsi_state = float(pc["rsi_state"][t_idx])
    else:
        rsi_state = float(calc_rsi_state(closes, rsi_period=14)[-1])

    # 5. oi_pct_change (安全: diff/shift 固定 clip; np.ndarray 位置索引)
    if "oi_pct_change" in pc:
        oi_val = float(pc["oi_pct_change"][t_idx])
    elif "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
        oi_pct = calc_oi_pct_change(df_1h["open_interest"].iloc[: t_idx + 1])
        oi_val = float(oi_pct.iloc[-1])
    else:
        oi_val = 0.0

    # 6. hurst (安全: 纯滚动窗口 DFA; 瓶颈特征, 必须预计算; np.ndarray 位置索引)
    if "hurst" in pc:
        hurst = float(pc["hurst"][t_idx])
    else:
        hurst = float(calc_rolling_hurst(closes, window=120, step=6)[-1])

    # 7. vol_prob (VolRiskFilter; 无则 NaN)
    # 7. vol_prob (regime 特征纯滚动可预计算; scaler/model 预训练纯推理, 不穿越)
    if vol_filter is not None:
        try:
            if "regime_feats" in pc:
                row = pc["regime_feats"].iloc[t_idx]
                feat_cols = vol_filter.feature_columns
                if not row[feat_cols].isna().any():
                    x = row[feat_cols].values.astype(float).reshape(1, -1)
                    xs = vol_filter.scaler.transform(x)
                    vol_prob = float(vol_filter.model.predict_proba(xs)[0, 1])
                else:
                    vol_prob = float("nan")
            else:
                decision = vol_filter.evaluate(df_1h.iloc[: t_idx + 1])
                vol_prob = float(decision.vol_prob)
        except Exception:
            vol_prob = float("nan")
    else:
        vol_prob = float("nan")

    return {
        "daily_slope": daily_slope,
        "hourly_slope": hourly_slope,
        "pca_momentum": pca_momentum,
        "rsi_state": rsi_state,
        "oi_pct_change": oi_val,
        "hurst": hurst,
        "vol_prob": vol_prob,
        "hour_sin": np.sin(2 * np.pi * int(t_dt.hour) / 24),
        "hour_cos": np.cos(2 * np.pi * int(t_dt.hour) / 24),
        "day_of_week": int(t_dt.dayofweek),
    }


def compute_timesfm_features_batch(
    symbol: str,
    store,
    df_1h: pd.DataFrame,
    bar_indices: list,
    shared_hourly,
    shared_daily,
    batch_size: int = 128,
    resume_path: str | None = None,
) -> pd.DataFrame:
    """
    批量计算 3 维 TimesFM 特征 (特征 #10/#11/#12)。

    #10 timesfm_pure_pred: HourlyModel._fallback_predict 的 T+24 点预测 / T0_close
    #11 timesfm_confidence: (P90 - P10) / T0_close
    #12 horizon_slope: DailyModel.predict 的 horizon_slope

    shared_hourly/shared_daily 为已加载的共享模型实例。
    bar_indices: 1H bar 索引列表 (需满足 t >= 479 且 t+24 < len(df_1h))。

    resume_path: 可选。若提供, 启动时读取该 JSONL 中已完成的 bar (bar_idx),
                 只计算未完成的 bars; 每个 bar 完成后立即追加一行并 flush，
                 崩溃/重启最多损失当前 bar, 无需全量重算。调用方必须保证单写入者。
    """
    import json
    closes_all = df_1h["close_price"].values.astype(float)
    CONTEXT = CONTEXT_BARS
    HORIZON = _BT_HORIZON

    # ① 读已完成的 bars (断点续算)
    done = {}
    if resume_path and os.path.exists(resume_path):
        with open(resume_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    done[int(rec["bar_idx"])] = rec
                except (json.JSONDecodeError, KeyError, ValueError):
                    # 跳过不可解析的行 (硬 kill 可能留下残缺尾行, 不阻断续跑)
                    continue

    # ② 只计算未完成的 bars
    pending = [t for t in bar_indices if t not in done]

    # ③ 对每个 pending bar 计算 3 维特征, 完成后立即原子追加
    records = []
    for t in pending:
        ctx = closes_all[max(0, t - CONTEXT + 1) : t + 1]
        rec = {"bar_idx": t}
        if len(ctx) < 48:
            rec["timesfm_pure_pred"] = None
            rec["timesfm_confidence"] = None
        else:
            t0_close = float(ctx[-1])
            try:
                point, quant = shared_hourly._fallback_predict(ctx, horizon=HORIZON)
                pred_t24 = float(point[-1])
                # quant shape (HORIZON, 10); P10=col[1], P90=col[9] (与 hourly_model.summary 一致)
                if quant.ndim == 2 and quant.shape[0] >= HORIZON:
                    p10 = float(quant[-1, 1])
                    p90 = float(quant[-1, 9])
                else:
                    p10 = p90 = pred_t24
                rec["timesfm_pure_pred"] = (pred_t24 / t0_close - 1) if t0_close != 0 else None
                rec["timesfm_confidence"] = (p90 - p10) / t0_close if t0_close != 0 else None
            except Exception:
                rec["timesfm_pure_pred"] = None
                rec["timesfm_confidence"] = None

        # horizon_slope: DailyModel 日线预测 (bar-exact cutoff)
        t_dt = pd.Timestamp(df_1h["dt"].iloc[t])
        cutoff = t_dt.strftime("%Y-%m-%d %H:%M:%S")
        try:
            if hasattr(store, "cutoff_date"):
                from data.data_store import BacktestDataStore
                with BacktestDataStore(symbol, cutoff) as s:
                    daily_result = shared_daily.predict(symbol, s)
            else:
                daily_result = shared_daily.predict(symbol, store)
            rec["horizon_slope"] = float(daily_result.horizon_slope)
        except Exception:
            rec["horizon_slope"] = None

        records.append(rec)
        # ④ 每完成一个 bar 立即追加 + flush；调用方必须保证单写入者
        if resume_path:
            with open(resume_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f.flush()

    # ⑤ 合并已完成 + 新计算的 (O(N) 字典映射, 防 IndexError + 防呆兜底)
    all_recs = {}
    records_dict = {r["bar_idx"]: r for r in records}  # 提前转为字典
    for t in bar_indices:
        if t in done:
            all_recs[t] = done[t]
        elif t in records_dict:
            all_recs[t] = records_dict[t]
        else:
            # 防呆兜底: 既不在 done 也不在 records 中 (异常情况)
            all_recs[t] = {"timesfm_pure_pred": np.nan, "timesfm_confidence": np.nan, "horizon_slope": np.nan}
    # 用 None → np.nan
    for t in all_recs:
        for k in ["timesfm_pure_pred", "timesfm_confidence", "horizon_slope"]:
            all_recs[t][k] = np.nan if all_recs[t][k] is None else all_recs[t][k]

    df = pd.DataFrame.from_dict(all_recs, orient="index")
    df = df.reindex(bar_indices)
    return df[["timesfm_pure_pred", "timesfm_confidence", "horizon_slope"]]


FEATURE_COLUMNS = [
    "daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
    "hurst","vol_prob","hour_sin","hour_cos","day_of_week",
    "timesfm_pure_pred","timesfm_confidence","horizon_slope",
]


def build_dense_feature_matrix(
    symbol: str,
    store,
    dense_step: int = 24,
    shared_hourly=None,
    shared_daily=None,
    vol_filter=None,
    cache_path: str | None = None,
    market_cache_path: str | None = None,
    tsfm_resume_path: str | None = None,
) -> pd.DataFrame:
    """
    构建全历史 dense 特征矩阵 (13 维 + Y + weight)。

    step=dense_step 采样 (默认 24, 非重叠目标)。
    每行: bar t 处的 13 维特征 + Y=(close[t+24]-close[t])/close[t] + weight=sqrt(|Y|)*100。
    所有特征仅用 t 之前数据 (防穿越); Y 是标签 (未来, 仅训练用)。

    三级缓存 (优先级 dense_matrix > market + tsfm):
    - cache_path: 完整 dense matrix 缓存。若提供且存在, 直接读取 (parquet) 并短路返回。
    - market_cache_path: 10 维市场特征缓存。若提供且存在, 直接读取 (parquet);
      否则逐 bar 计算后原子写入 (临时文件 + os.replace)。
    - tsfm_resume_path: 3 维 TimesFM 特征断点续算文件 (jsonl), 传给
      compute_timesfm_features_batch, 崩溃/重启只重算未完成的 bars。
    """
    import pathlib
    if cache_path and pathlib.Path(cache_path).exists():
        return pd.read_parquet(cache_path)

    df_1h = store.get_main_contract_1h(limit=100000)
    df_daily = store.get_main_continuous(limit=100000) if hasattr(store, "get_main_continuous") else pd.DataFrame()
    closes = df_1h["close_price"].values.astype(float)
    HORIZON = _BT_HORIZON
    CONTEXT = CONTEXT_BARS  # 别名, 保持函数内语义不变

    # 有效 bar: t >= CONTEXT (1H context 充足) 且 t+HORIZON < len (Y 可算)
    # 使用共享 eval grid, 确保与 Worker/Orchestrator 边界一致
    from scripts.a2_p1_runtime import generate_eval_grid
    valid = generate_eval_grid(len(closes))
    # dense_step 采样 (默认 24, 与 STEP 一致)
    if dense_step != STEP:
        valid = [t for t in valid if (t - CONTEXT) % dense_step == 0]
    if not valid:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["Y", "weight", "bar_idx", "cutoff"])

    # vol_filter (若未传入, 用模块级 VolRiskFilter 绑定)
    if vol_filter is None and VolRiskFilter is not None:
        try:
            vol_filter = VolRiskFilter.bind_for_symbol(symbol, mode="r0")
        except Exception:
            vol_filter = None  # vol_prob 将全 NaN

    # ① 9 维市场特征: 有缓存则读, 无则算后原子写
    if market_cache_path and pathlib.Path(market_cache_path).exists():
        market_df = pd.read_parquet(market_cache_path)
        if "bar_idx" not in market_df.index.names:
            market_df = market_df.set_index("bar_idx")
    else:
        # 预计算安全特征全序列 (O(N), hurst 瓶颈一次性算完; pca_momentum/vol_prob 不预计算防穿越)
        closes_full = df_1h["close_price"].values.astype(float)
        precomputed = {
            "hurst": calc_rolling_hurst(closes_full, window=120, step=6),       # np.ndarray 全序列, [t_idx] 安全
            "hourly_slope": calc_hourly_slope(closes_full, window=24).values,   # pd.Series->np.ndarray 位置索引
            "rsi_state": calc_rsi_state(closes_full, rsi_period=14),            # np.ndarray
        }
        if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
            precomputed["oi_pct_change"] = calc_oi_pct_change(df_1h["open_interest"]).values
        # daily_slope: 按 valid 字典映射 (key=t_idx), 防 IndexError (valid 长度 396 vs t_idx 480 越界)
        precomputed["daily_slope"] = {
            t: _daily_slope_at(df_daily, pd.Timestamp(df_1h["dt"].iloc[t])) for t in valid
        }
        # regime 特征全序列 (vol_prob 用, 纯滚动安全; scaler/model 预训练纯推理不穿越)
        if vol_filter is not None:
            try:
                precomputed["regime_feats"] = extract_1h_regime_features(df_1h, version=FEATURE_VERSION_V2)
            except Exception:
                pass

        market_rows = []
        for t in valid:
            feats = extract_market_features_at_bar(df_1h, df_daily, t, symbol, vol_filter, precomputed=precomputed)
            feats["bar_idx"] = t
            feats["cutoff"] = str(pd.Timestamp(df_1h["dt"].iloc[t]).strftime("%Y-%m-%d %H:%M"))
            market_rows.append(feats)
        market_df = pd.DataFrame(market_rows).set_index("bar_idx")
        if market_cache_path:
            pathlib.Path(market_cache_path).parent.mkdir(parents=True, exist_ok=True)
            tmp_path = str(market_cache_path) + ".tmp"
            market_df.to_parquet(tmp_path)
            os.replace(tmp_path, str(market_cache_path))

    # ② 3 维 TimesFM 特征 (传 resume_path 支持断点续算)
    if shared_hourly is not None and shared_daily is not None:
        tsfm_df = compute_timesfm_features_batch(
            symbol, store, df_1h, valid, shared_hourly, shared_daily,
            resume_path=tsfm_resume_path,
        )
        tsfm_df = tsfm_df.set_index(tsfm_df.index)
    else:
        tsfm_df = pd.DataFrame(
            {c: [np.nan] * len(valid) for c in ["timesfm_pure_pred", "timesfm_confidence", "horizon_slope"]},
            index=valid,
        )

    mat = market_df.join(tsfm_df, how="left")

    # Y + weight
    mat["Y"] = [(closes[t + HORIZON] - closes[t]) / closes[t] if closes[t] != 0 else np.nan
                for t in valid]
    mat["weight"] = np.sqrt(np.abs(mat["Y"])) * 100.0
    mat = mat.reset_index(names=["bar_idx"])
    if "bar_idx" not in mat.columns:
        mat["bar_idx"] = valid

    if cache_path:
        pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        tmp_path = str(cache_path) + ".tmp"
        mat.to_parquet(tmp_path)
        os.replace(tmp_path, str(cache_path))
    return mat

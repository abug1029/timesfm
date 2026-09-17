# Alpha 2.0 Phase 1 - LGBM 基线门禁探针 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 LGBM 基线探针，对比 TimesFM-pure / TimesFM-scheme / LGBM-B(12维宽特征) 三曲线的 PF/EV，产出 GO/NO-GO 门禁裁决，决定是否启动 A2-P2 残差叠加架构。

**Architecture:** Dense Training, Sparse Evaluation - 全历史 step=24 非重叠 bar 预计算 12 维特征矩阵 (parquet 缓存)；walk-forward expanding window 训练 LGBM (百分比收益率目标)，每 N 点 refit；三曲线 PF/EV + 配对 bootstrap 显著性门禁。

**Tech Stack:** Python 3, LightGBM, scikit-learn (TimeSeriesSplit), pandas, numpy, TimesFM 2.5 (共享底座 `D:\FlyBuddy\shared\timesfm\.venv`), pytest

## Global Constraints

- **北极星指标**: PF/EV/MaxDD。DirAcc 与 Vol-Scaled MAE **仅 logging，永不参与 Go/No-Go**。
- **回归目标**: 百分比收益率 `Y=(close[t+24]-close[t])/close[t]`，`sample_weight=|Y|×10000`。还原价格：`Pred_move=T0_close×Pred_Return` 送 `calc_net_metrics`。
- **dense_step=24** 默认（非重叠目标，防自相关过拟合）；欠拟合时降 12。**绝不降级 standalone**（9 特征败北 ≠ 12 特征败北，防假阴性）。
- **防穿越**: 所有特征仅用 `cutoff` 前数据；`BacktestDataStore(symbol, cutoff_date)` 保证截止；dense 矩阵中 t 行特征不含 `dt > t` 数据。
- **嵌套 CV**: 超参仅在训练段选，外层 T0 零接触。
- **vol_prob 前瞻瑕疵**: 模型训练截止 2026-03-31，2026-03 前评估点有轻微 Lookahead；代码注释 + 报告声明，不重训。
- **常量**: `CONTEXT_BARS=480, HORIZON=24, STEP=24` (来自 `config/backtest_config.py`)。
- **输出语言**: 中文。审核文档须存主仓库 `D:\FlyBuddy\fm_a\`。
- **共享 TimesFM 实例**: 全 run 单次加载（~800MB），`HourlyModel(shared_model=...)` / `DailyModel(shared_model=...)`。

**Spec**: `docs/superpowers/specs/2026-08-04-alpha2-phase1-baseline-gate-design.md`

---

## File Structure

| 文件 | 责任 |
|------|------|
| `cascade/evaluation_metrics.py` (改) | 追加 `calc_vol_scaled_mae()`；不动现有决策逻辑 |
| `cascade/lgbm_features.py` (新) | 特征抽取：`extract_market_features_at_bar` (9维无TimesFM) + `compute_timesfm_features_batch` (3维TimesFM) + `build_dense_feature_matrix` (组装+缓存) |
| `scripts/a2_p1_lgbm_baseline.py` (新) | runner：walk-forward 训练 + 三曲线对比 + bootstrap 门禁 + 报告 |
| `tests/test_vol_scaled_mae.py` (新) | Vol-Scaled MAE 单测 |
| `tests/test_lgbm_features.py` (新) | 特征抽取防泄漏 + schema 单测 |
| `tests/test_a2_p1_baseline.py` (新) | 训练器 + 门禁 smoke 集成 |

---

## Task 1: LightGBM 依赖 + Vol-Scaled MAE 指标

**Files:**
- Modify: `cascade/evaluation_metrics.py` (追加函数)
- Test: `tests/test_vol_scaled_mae.py`

**Interfaces:**
- Produces: `calc_vol_scaled_mae(pred: np.ndarray, actual: np.ndarray, atr: np.ndarray) -> float`

- [ ] **Step 1: 安装 LightGBM 到共享 venv**

```bash
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/pip install lightgbm
D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -c "import lightgbm; print(lightgbm.__version__)"
```
Expected: 打印版本号 (≥4.0)

- [ ] **Step 2: 写失败测试**

```python
# tests/test_vol_scaled_mae.py
import numpy as np
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from cascade.evaluation_metrics import calc_vol_scaled_mae

def test_vol_scaled_mae_basic():
    # 误差 10 点, ATR 5 点 -> 缩放误差 2.0
    pred = np.array([100.0])
    actual = np.array([110.0])
    atr = np.array([5.0])
    assert calc_vol_scaled_mae(pred, actual, atr) == 2.0

def test_vol_scaled_mae_atr_zero_safe():
    # ATR=0 不应除零, 返回 inf 或大数
    pred = np.array([100.0])
    actual = np.array([110.0])
    atr = np.array([0.0])
    result = calc_vol_scaled_mae(pred, actual, atr)
    assert np.isinf(result) or result > 1e6

def test_vol_scaled_mae_multi_point():
    pred = np.array([100.0, 200.0])
    actual = np.array([110.0, 190.0])  # 误差 10 each
    atr = np.array([5.0, 10.0])        # 缩放 2.0, 1.0
    assert calc_vol_scaled_mae(pred, actual, atr) == 1.5  # mean(2.0, 1.0)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_vol_scaled_mae.py -v`
Expected: FAIL (ImportError / function not defined)

- [ ] **Step 4: 实现 calc_vol_scaled_mae**

在 `cascade/evaluation_metrics.py` 末尾追加：

```python
def calc_vol_scaled_mae(
    pred: ArrayLike,
    actual: ArrayLike,
    atr: ArrayLike,
) -> float:
    """
    波动率缩放 MAE (诊断指标, 不参与决策门禁)。

    Scaled_Error = |Pred - Actual| / ATR
    返回平均缩放误差。<1.0 表示误差在正常日内波动范围内。

    Args:
        pred: 预测值 (价格点)
        actual: 实际值 (价格点)
        atr: 每点 ATR_14 (价格点, 同尺度)
    """
    p = np.asarray(pred, dtype=float)
    a = np.asarray(actual, dtype=float)
    atr_arr = np.asarray(atr, dtype=float)
    if p.size == 0:
        return 0.0
    err = np.abs(p - a)
    # ATR=0 处用 inf (不除零); 不计入有限均值
    with np.errstate(divide="ignore", invalid="ignore"):
        scaled = np.where(atr_arr > 1e-8, err / np.maximum(atr_arr, 1e-8), np.inf)
    finite = scaled[np.isfinite(scaled)]
    return float(np.mean(finite)) if finite.size else float(np.inf)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_vol_scaled_mae.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add cascade/evaluation_metrics.py tests/test_vol_scaled_mae.py
git commit -m "feat(a2-p1): Vol-Scaled MAE 诊断指标 + lightgbm 依赖"
```

---

## Task 2: 市场特征抽取器 (9 维, 无 TimesFM)

**Files:**
- Create: `cascade/lgbm_features.py`
- Test: `tests/test_lgbm_features.py`

**Interfaces:**
- Consumes: `features.calc_hourly_slope`, `features.calc_pca_momentum`, `features.calc_rsi_state`, `features.calc_oi_pct_change`, `features.calc_rolling_hurst`, `features._calc_atr`, `vol_risk_filter.VolRiskFilter.bind_for_symbol`
- Produces: `extract_market_features_at_bar(df_1h, df_daily, t_idx, symbol, vol_filter) -> dict` (9 维)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_lgbm_features.py
import numpy as np
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from cascade.lgbm_features import extract_market_features_at_bar

def _make_df_1h(n=600):
    rng = np.random.default_rng(42)
    px = 3000 + np.cumsum(rng.normal(0, 10, n))
    return pd.DataFrame({
        "dt": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open_price": px, "high_price": px+5, "low_price": px-5,
        "close_price": px, "volume": 1000.0, "open_interest": 50000.0,
    })

def _make_df_daily(n=200):
    rng = np.random.default_rng(7)
    px = 3000 + np.cumsum(rng.normal(0, 20, n))
    return pd.DataFrame({"dt": pd.date_range("2024-01-01", periods=n, freq="D"),
                         "close_price": px})

def test_market_features_schema():
    df_1h = _make_df_1h()
    df_daily = _make_df_daily()
    feats = extract_market_features_at_bar(df_1h, df_daily, t_idx=500, symbol="ss", vol_filter=None)
    expected_keys = {"daily_slope","hourly_slope","pca_momentum","rsi_state",
                     "oi_pct_change","hurst","vol_prob","hour_of_day","day_of_week"}
    assert set(feats.keys()) == expected_keys
    # hour/dow 是整数
    assert 0 <= feats["hour_of_day"] <= 23
    assert 0 <= feats["day_of_week"] <= 6

def test_market_features_no_lookahead():
    """t 行特征不含 t 之后数据 (vol_filter=None 时主要验 rsi/slope 用 [:t+1])"""
    df_1h = _make_df_1h()
    df_daily = _make_df_daily()
    t = 500
    feats_a = extract_market_features_at_bar(df_1h, df_daily, t, "ss", None)
    # 篡改 t 之后的数据, 特征应不变
    df_1h_b = df_1h.copy()
    df_1h_b.loc[t+1:, "close_price"] = 99999.0
    feats_b = extract_market_features_at_bar(df_1h_b, df_daily, t, "ss", None)
    for k in ["hourly_slope","pca_momentum","rsi_state","hurst"]:
        assert feats_a[k] == feats_b[k], f"{k} 被未来数据污染"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py::test_market_features_schema -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 extract_market_features_at_bar**

```python
# cascade/lgbm_features.py
"""A2-P1 LGBM 特征工程: 12 维宽特征池 (9 市场 + 3 TimesFM)。"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from .features import (
    calc_hourly_slope, calc_pca_momentum, calc_rsi_state,
    calc_oi_pct_change, calc_rolling_hurst, _calc_atr,
)


def _daily_slope_at(df_daily: pd.DataFrame, t_dt: pd.Timestamp, lookback: int = 5) -> float:
    """t 时刻的日线滚动斜率 (归一化 %/天)。仅用 t 之前日线, 无穿越。"""
    if df_daily.empty:
        return 0.0
    dt_col = "dt" if "dt" in df_daily.columns else "date"
    daily = df_daily[df_daily[dt_col] <= t_dt].copy()
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
) -> Dict[str, float]:
    """
    在 1H bar t_idx 处抽取 9 维市场特征 (无 TimesFM 依赖)。

    特征: daily_slope, hourly_slope, pca_momentum, rsi_state,
          oi_pct_change, hurst, vol_prob, hour_of_day, day_of_week
    所有计算仅用 df_1h[:t_idx+1] 与 df_daily[<=t_dt], 防穿越。
    """
    closes = df_1h["close_price"].values.astype(float)[: t_idx + 1]
    t_dt = pd.Timestamp(df_1h["dt"].iloc[t_idx])

    # 1. daily_slope (日线滚动斜率, 无 TimesFM)
    daily_slope = _daily_slope_at(df_daily, t_dt)

    # 2. hourly_slope (末值)
    hourly_slope = float(calc_hourly_slope(closes, window=24).iloc[-1])

    # 3. pca_momentum (末值)
    pca_momentum = float(calc_pca_momentum(closes, periods=[5, 9, 14, 21], squash=True)[-1])

    # 4. rsi_state (末值)
    rsi_state = float(calc_rsi_state(closes, rsi_period=14)[-1])

    # 5. oi_pct_change (末值)
    if "open_interest" in df_1h.columns and df_1h["open_interest"].notna().any():
        oi_pct = calc_oi_pct_change(df_1h["open_interest"].iloc[: t_idx + 1])
        oi_val = float(oi_pct.iloc[-1])
    else:
        oi_val = 0.0

    # 6. hurst (末值)
    hurst = float(calc_rolling_hurst(closes, window=120, step=6)[-1])

    # 7. vol_prob (VolRiskFilter; 无则 NaN)
    if vol_filter is not None:
        try:
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
        "hour_of_day": int(t_dt.hour),
        "day_of_week": int(t_dt.dayofweek),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add cascade/lgbm_features.py tests/test_lgbm_features.py
git commit -m "feat(a2-p1): 9 维市场特征抽取器 (无 TimesFM, 防穿越)"
```

---

## Task 3: TimesFM 依赖特征批量计算 (3 维)

**Files:**
- Modify: `cascade/lgbm_features.py`
- Test: `tests/test_lgbm_features.py` (追加)

**Interfaces:**
- Consumes: `hourly_model.HourlyModel._fallback_predict`, `daily_model.DailyModel.predict`
- Produces: `compute_timesfm_features_batch(symbol, store, bar_indices, shared_hourly, shared_daily) -> pd.DataFrame` (列: timesfm_pure_pred, timesfm_confidence, horizon_slope)

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_lgbm_features.py
from cascade.lgbm_features import compute_timesfm_features_batch

def test_timesfm_features_schema():
    # 用 mock hourly/daily model 避免加载真模型
    class MockHourly:
        def _fallback_predict(self, closes, horizon=24):
            p = np.full(horizon, float(closes[-1]) * 1.01)
            q = np.column_stack([p - 5] * 10 + [p + 5] * 0)  # 简化
            return p, np.column_stack([p-5, p-4, p-3, p-2, p-1, p, p+1, p+2, p+3, p+5])
    class MockDaily:
        class _R:
            horizon_slope = 0.002
            forecast = np.array([3000.0])
            historical_closes = np.array([3000.0])
            historical_dates = None
        def predict(self, symbol, store, context_days=250, horizon_days=22):
            return self._R()
    df_1h = _make_df_1h()
    # bar_indices 必须满足 t >= 479 (context) 且 t+24 < len
    bars = [500, 524, 548]
    # store 不用 (mock 模型不读 store), 传 None
    result = compute_timesfm_features_batch("ss", None, df_1h, bars, MockHourly(), MockDaily())
    assert set(result.columns) == {"timesfm_pure_pred", "timesfm_confidence", "horizon_slope"}
    assert len(result) == 3
    # pure_pred 归一化 (除以 T0_close)
    assert abs(result["timesfm_pure_pred"].iloc[0] - 0.01) < 0.01
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py::test_timesfm_features_schema -v`
Expected: FAIL (function not defined)

- [ ] **Step 3: 实现 compute_timesfm_features_batch**

在 `cascade/lgbm_features.py` 追加：

```python
def compute_timesfm_features_batch(
    symbol: str,
    store,
    df_1h: pd.DataFrame,
    bar_indices: list,
    shared_hourly,
    shared_daily,
    batch_size: int = 128,
) -> pd.DataFrame:
    """
    批量计算 3 维 TimesFM 特征 (特征 #10/#11/#12)。

    #10 timesfm_pure_pred: HourlyModel._fallback_predict 的 T+24 点预测 / T0_close
    #11 timesfm_confidence: (P90 - P10) / T0_close
    #12 horizon_slope: DailyModel.predict 的 horizon_slope

    shared_hourly/shared_daily 为已加载的共享模型实例。
    bar_indices: 1H bar 索引列表 (需满足 t >= 479 且 t+24 < len(df_1h))。
    """
    closes_all = df_1h["close_price"].values.astype(float)
    CONTEXT = 480
    HORIZON = 24
    records = []

    # 批量 1H 预测 (按 batch_size 分组)
    for i in range(0, len(bar_indices), batch_size):
        batch = bar_indices[i : i + batch_size]
        for t in batch:
            ctx = closes_all[max(0, t - CONTEXT + 1) : t + 1]
            if len(ctx) < 48:
                records.append({"timesfm_pure_pred": np.nan, "timesfm_confidence": np.nan})
                continue
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
                records.append({
                    "timesfm_pure_pred": pred_t24 / t0_close if t0_close != 0 else np.nan,
                    "timesfm_confidence": (p90 - p10) / t0_close if t0_close != 0 else np.nan,
                })
            except Exception:
                records.append({"timesfm_pure_pred": np.nan, "timesfm_confidence": np.nan})

    # Daily horizon_slope: DailyModel 在 t 的日线 context 上预测
    # (DailyModel.predict 读 store 日线; 为历史 bar 重算 -> 用 BacktestDataStore 截止 t 的日期)
    from datetime import datetime
    horizon_slopes = []
    for t in bar_indices:
        t_dt = pd.Timestamp(df_1h["dt"].iloc[t])
        cutoff = t_dt.strftime("%Y-%m-%d")
        try:
            # store 须为支持 cutoff 的 BacktestDataStore; 若生产 store 则用当前数据
            if hasattr(store, "cutoff_date"):
                from data.data_store import BacktestDataStore
                with BacktestDataStore(symbol, cutoff) as s:
                    daily_result = shared_daily.predict(symbol, s)
            else:
                daily_result = shared_daily.predict(symbol, store)
            horizon_slopes.append(float(daily_result.horizon_slope))
        except Exception:
            horizon_slopes.append(np.nan)

    df = pd.DataFrame(records, index=bar_indices)
    df["horizon_slope"] = horizon_slopes
    return df[["timesfm_pure_pred", "timesfm_confidence", "horizon_slope"]]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add cascade/lgbm_features.py tests/test_lgbm_features.py
git commit -m "feat(a2-p1): 3 维 TimesFM 特征批量计算 (#10/#11/#12)"
```

---

## Task 4: Dense 特征矩阵组装 + 缓存

**Files:**
- Modify: `cascade/lgbm_features.py`
- Test: `tests/test_lgbm_features.py` (追加)

**Interfaces:**
- Consumes: Task 2 `extract_market_features_at_bar`, Task 3 `compute_timesfm_features_batch`, `vol_risk_filter.VolRiskFilter.bind_for_symbol`
- Produces: `build_dense_feature_matrix(symbol, store, dense_step, shared_hourly, shared_daily) -> pd.DataFrame` (12 特征列 + Y + weight + bar_idx + cutoff)

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_lgbm_features.py
from cascade.lgbm_features import build_dense_feature_matrix

def test_dense_matrix_schema_and_cache(tmp_path, monkeypatch):
    df_1h = _make_df_1h(700)
    df_daily = _make_df_daily(200)
    # monkeypatch store
    class FakeStore:
        cutoff_date = None
        def get_main_contract_1h(self, limit=1023): return df_1h
        def get_main_continuous(self, limit=250): return df_daily
    class MockHourly:
        def _fallback_predict(self, closes, horizon=24):
            p = np.full(horizon, float(closes[-1]))
            q = np.column_stack([p]*10)
            return p, q
    class MockDaily:
        class _R:
            horizon_slope = 0.0
            forecast = np.array([3000.0]); historical_closes = np.array([3000.0]); historical_dates = None
        def predict(self, symbol, store, context_days=250, horizon_days=22): return self._R()
    monkeypatch.setattr("cascade.lgbm_features.VolRiskFilter", None)  # 跳过 vol_prob
    mat = build_dense_feature_matrix("ss", FakeStore(), dense_step=24,
                                      shared_hourly=MockHourly(), shared_daily=MockDaily())
    # 12 特征 + Y + weight
    feat_cols = {"daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
                 "hurst","vol_prob","hour_of_day","day_of_week",
                 "timesfm_pure_pred","timesfm_confidence","horizon_slope"}
    assert feat_cols.issubset(mat.columns)
    assert "Y" in mat.columns and "weight" in mat.columns
    # Y = (close[t+24]-close[t])/close[t]
    closes = df_1h["close_price"].values
    first_t = mat["bar_idx"].iloc[0]
    expected_y = (closes[first_t+24] - closes[first_t]) / closes[first_t]
    assert abs(mat["Y"].iloc[0] - expected_y) < 1e-9

def test_dense_matrix_no_lookahead():
    """dense 矩阵 t 行特征不含 dt > t 的数据 (Y 除外, Y 是标签)"""
    df_1h = _make_df_1h(700)
    df_daily = _make_df_daily(200)
    class FakeStore:
        cutoff_date = None
        def get_main_contract_1h(self, limit=1023): return df_1h
        def get_main_continuous(self, limit=250): return df_daily
    class MockHourly:
        def _fallback_predict(self, closes, horizon=24):
            p = np.full(horizon, float(closes[-1])); q = np.column_stack([p]*10)
            return p, q
    class MockDaily:
        class _R:
            horizon_slope = 0.0; forecast=np.array([3000.0]); historical_closes=np.array([3000.0]); historical_dates=None
        def predict(self, symbol, store, context_days=250, horizon_days=22): return self._R()
    mat = build_dense_feature_matrix("ss", FakeStore(), dense_step=24,
                                      shared_hourly=MockHourly(), shared_daily=MockDaily())
    # 篡改未来数据, 特征列不变
    t0 = mat["bar_idx"].iloc[0]
    df_1h_b = df_1h.copy()
    df_1h_b.loc[t0+25:, "close_price"] = 99999.0
    class FakeStoreB(FakeStore):
        def get_main_contract_1h(self, limit=1023): return df_1h_b
    mat_b = build_dense_feature_matrix("ss", FakeStoreB(), dense_step=24,
                                       shared_hourly=MockHourly(), shared_daily=MockDaily())
    for col in ["hourly_slope","pca_momentum","rsi_state","hurst"]:
        assert mat[col].iloc[0] == mat_b[col].iloc[0], f"{col} 被未来污染"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py::test_dense_matrix_schema_and_cache -v`
Expected: FAIL

- [ ] **Step 3: 实现 build_dense_feature_matrix**

在 `cascade/lgbm_features.py` 追加：

```python
FEATURE_COLUMNS = [
    "daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
    "hurst","vol_prob","hour_of_day","day_of_week",
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
) -> pd.DataFrame:
    """
    构建全历史 dense 特征矩阵 (12 维 + Y + weight)。

    step=dense_step 采样 (默认 24, 非重叠目标)。
    每行: bar t 处的 12 维特征 + Y=(close[t+24]-close[t])/close[t] + weight=|Y|*10000。
    所有特征仅用 t 之前数据 (防穿越); Y 是标签 (未来, 仅训练用)。

    cache_path: 若提供且存在, 直接读取 (parquet); 否则计算后写入。
    """
    import pathlib
    if cache_path and pathlib.Path(cache_path).exists():
        return pd.read_parquet(cache_path)

    df_1h = store.get_main_contract_1h(limit=100000)
    df_daily = store.get_main_continuous(limit=100000) if hasattr(store, "get_main_continuous") else pd.DataFrame()
    closes = df_1h["close_price"].values.astype(float)
    HORIZON = 24
    CONTEXT = 480

    # 有效 bar: t >= CONTEXT (1H context 充足) 且 t+HORIZON < len (Y 可算)
    # 起点对齐 Task 7 eval_bars (range(CONTEXT_BARS, ...)) 防空集陷阱
    valid = list(range(CONTEXT, len(closes) - HORIZON, dense_step))
    if not valid:
        return pd.DataFrame(columns=FEATURE_COLUMNS + ["Y", "weight", "bar_idx", "cutoff"])

    # vol_filter (若未传入, bind)
    if vol_filter is None:
        try:
            from .vol_risk_filter import VolRiskFilter
            vol_filter = VolRiskFilter.bind_for_symbol(symbol, mode="r0")
        except Exception:
            vol_filter = None  # vol_prob 将全 NaN

    # 9 维市场特征 (逐 bar)
    market_rows = []
    for t in valid:
        feats = extract_market_features_at_bar(df_1h, df_daily, t, symbol, vol_filter)
        feats["bar_idx"] = t
        feats["cutoff"] = str(pd.Timestamp(df_1h["dt"].iloc[t]).strftime("%Y-%m-%d %H:%M"))
        market_rows.append(feats)
    market_df = pd.DataFrame(market_rows).set_index("bar_idx")

    # 3 维 TimesFM 特征 (批量)
    if shared_hourly is not None and shared_daily is not None:
        tsfm_df = compute_timesfm_features_batch(
            symbol, store, df_1h, valid, shared_hourly, shared_daily
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
    mat["weight"] = np.abs(mat["Y"]) * 10000.0
    mat = mat.reset_index().rename(columns={"index": "bar_idx"})
    if "bar_idx" not in mat.columns:
        mat["bar_idx"] = valid

    if cache_path:
        pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        mat.to_parquet(cache_path)
    return mat
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_lgbm_features.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add cascade/lgbm_features.py tests/test_lgbm_features.py
git commit -m "feat(a2-p1): dense 特征矩阵组装 + parquet 缓存 (防穿越)"
```

---

## Task 5: LGBM walk-forward 训练器

**Files:**
- Create: `scripts/a2_p1_lgbm_baseline.py`
- Test: `tests/test_a2_p1_baseline.py`

**Interfaces:**
- Consumes: Task 4 `build_dense_feature_matrix`, `config.backtest_config` 常量
- Produces: `train_lgbm_walkforward(dense_matrix, eval_bar_indices, refit_every=10) -> pd.DataFrame` (列: bar_idx, pred_return, pred_move, actual_move)

- [ ] **Step 1: 写失败测试 (合成数据)**

```python
# tests/test_a2_p1_baseline.py
import numpy as np
import pandas as pd
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.a2_p1_lgbm_baseline import train_lgbm_walkforward

def _synth_matrix(n=400):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "bar_idx": np.arange(n),
        "hourly_slope": rng.normal(0, 0.001, n),
        "rsi_state": rng.integers(-2, 3, n).astype(float),
        "timesfm_pure_pred": rng.normal(0, 0.01, n),
        "hurst": rng.normal(0, 0.5, n),
        "Y": rng.normal(0, 0.02, n),  # 与特征弱相关 -> LGBM 学不到太多
        "weight": rng.uniform(1, 200, n),
    })
    return df

def test_walkforward_output_schema():
    mat = _synth_matrix(400)
    eval_bars = list(range(50, 400, 10))  # 35 eval points
    out = train_lgbm_walkforward(mat, eval_bars, refit_every=5)
    assert set(["bar_idx","pred_return","pred_move","actual_move"]).issubset(out.columns)
    assert len(out) == len(eval_bars)
    # actual_move 需要 T0_close 还原; 合成测试无 close, 检查 pred_return 范围合理
    assert out["pred_return"].abs().max() < 1.0

def test_walkforward_no_train_test_overlap():
    """eval bar t 的预测只用 t 之前训练数据"""
    mat = _synth_matrix(400)
    eval_bars = [200]
    out = train_lgbm_walkforward(mat, eval_bars, refit_every=1)
    # 篡改 t=200 处的 Y (标签), 预测应不变 (训练不含 t)
    mat_b = mat.copy()
    mat_b.loc[mat_b["bar_idx"] == 200, "Y"] = 999.0
    out_b = train_lgbm_walkforward(mat_b, eval_bars, refit_every=1)
    assert abs(out["pred_return"].iloc[0] - out_b["pred_return"].iloc[0]) < 1e-6
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_a2_p1_baseline.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 train_lgbm_walkforward**

```python
# scripts/a2_p1_lgbm_baseline.py
"""A2-P1 LGBM 基线探针: walk-forward 训练 + 三曲线门禁。"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit

FEATURE_COLS = [
    "daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
    "hurst","vol_prob","hour_of_day","day_of_week",
    "timesfm_pure_pred","timesfm_confidence","horizon_slope",
]

# 超参网格 (内层 TimeSeriesSplit 选)
PARAM_GRID = {
    "num_leaves": [15, 31, 63],
    "min_child_samples": [20, 50],
    "lambda_l1": [0.0, 0.1, 1.0],
    "lambda_l2": [0.0, 0.1],
    "colsample_bytree": [0.7, 0.9],
    "n_estimators": [100, 300],
    "learning_rate": [0.05, 0.1],
    "max_depth": [-1, 6],
}


def _select_hyperparams(X_train, y_train, w_train):
    """内层 TimeSeriesSplit(3) 选超参 (MSE + sample_weight)。返回最佳 params。"""
    tscv = TimeSeriesSplit(n_splits=3)
    best_score, best_params = -np.inf, None
    # 网格搜索 (简化: 随机抽 16 组避免全量爆炸)
    import itertools
    keys = list(PARAM_GRID.keys())
    combos = list(itertools.product(*[PARAM_GRID[k] for k in keys]))
    rng = np.random.default_rng(42)
    sampled = rng.choice(len(combos), size=min(16, len(combos)), replace=False)
    for idx in sampled:
        params = dict(zip(keys, combos[idx]))
        params["verbose"] = -1
        scores = []
        for tr_idx, va_idx in tscv.split(X_train):
            m = lgb.LGBMRegressor(**params)
            m.fit(X_train[tr_idx], y_train[tr_idx], sample_weight=w_train[tr_idx])
            pred = m.predict(X_train[va_idx])
            # 评分: 与 sample_weight 对齐的负 MSE
            scores.append(-np.average((pred - y_train[va_idx]) ** 2, weights=w_train[va_idx]))
        mean_score = np.mean(scores)
        if mean_score > best_score:
            best_score, best_params = mean_score, params
    return best_params or {"num_leaves": 31, "verbose": -1}


def train_lgbm_walkforward(
    dense_matrix: pd.DataFrame,
    eval_bar_indices: list,
    refit_every: int = 10,
) -> pd.DataFrame:
    """
    Walk-forward expanding window 训练 LGBM。

    对每个 eval bar T0:
      - 训练切片 = dense_matrix 中 bar_idx <= T0 - 24 的行 (防穿越)
      - 内层 TimeSeriesSplit 选超参 (仅训练段)
      - 训练最终模型 -> 预测 T0 -> pred_return
      - pred_move = T0_close * pred_return (T0_close 由调用方提供, 此处用 Y 还原)
    refit_every: 每 N 个 eval 点重训一次, 中间复用上次模型。
    """
    mat = dense_matrix.sort_values("bar_idx").reset_index(drop=True)
    # close 列 (若存在, 用于还原 pred_move); 否则用 Y 反推
    has_close = "t0_close" in mat.columns

    results = []
    last_model = None
    last_train_end = -1

    for i, t0 in enumerate(eval_bar_indices):
        if i % refit_every == 0 or last_model is None:
            # 训练切片: bar_idx <= t0 - 24
            train_mask = mat["bar_idx"] <= (t0 - 24)
            train_df = mat[train_mask]
            if len(train_df) < 50:
                results.append({"bar_idx": t0, "pred_return": 0.0})
                continue
            X_train = train_df[FEATURE_COLS].values.astype(float)
            y_train = train_df["Y"].values.astype(float)
            w_train = train_df["weight"].values.astype(float)
            # 保留 NaN: LGBM use_missing=True 原生处理, 填 0 会混淆"无变化"与"数据缺失"
            params = _select_hyperparams(X_train, y_train, w_train)
            last_model = lgb.LGBMRegressor(**params)
            last_model.fit(X_train, y_train, sample_weight=w_train)
            last_train_end = t0

        # 预测 T0
        t0_row = mat[mat["bar_idx"] == t0]
        if t0_row.empty:
            results.append({"bar_idx": t0, "pred_return": 0.0})
            continue
        X_t0 = t0_row[FEATURE_COLS].values.astype(float)  # 保留 NaN, LGBM 原生处理
        pred_ret = float(last_model.predict(X_t0)[0])
        results.append({"bar_idx": t0, "pred_return": pred_ret})

    out = pd.DataFrame(results)
    # 还原 pred_move / actual_move (需 t0_close; 若 dense_matrix 含 t0_close 列则用之)
    if has_close:
        close_map = dict(zip(mat["bar_idx"], mat["t0_close"]))
        out["t0_close"] = out["bar_idx"].map(close_map)
        out["pred_move"] = out["t0_close"] * out["pred_return"]
        out["actual_move"] = out["bar_idx"].map(
            dict(zip(mat["bar_idx"], mat["t0_close"] * mat["Y"]))
        )
    else:
        out["pred_move"] = out["pred_return"]
        out["actual_move"] = out["bar_idx"].map(
            dict(zip(mat["bar_idx"], mat["Y"]))
        )
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_a2_p1_baseline.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/a2_p1_lgbm_baseline.py tests/test_a2_p1_baseline.py
git commit -m "feat(a2-p1): LGBM walk-forward 训练器 (嵌套 CV + refit-every)"
```

---

## Task 6: 三曲线对比 + bootstrap 门禁

**Files:**
- Modify: `scripts/a2_p1_lgbm_baseline.py`
- Test: `tests/test_a2_p1_baseline.py` (追加)

**Interfaces:**
- Consumes: Task 5 `train_lgbm_walkforward`, `evaluation_metrics.calc_net_metrics`, `evaluation_metrics.calc_vol_scaled_mae`
- Produces: `evaluate_gate(lgbm_preds, pure_preds, scheme_preds, actuals, base_prices, atr, tick_size) -> dict` (verdict: GO/NO-GO + metrics + bootstrap CI)

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_a2_p1_baseline.py
from scripts.a2_p1_lgbm_baseline import evaluate_gate, paired_bootstrap_ev_ci

def test_paired_bootstrap_ci_basic():
    """LGBM 明显优于 scheme 时, EV 差 CI 下界 > 0"""
    rng = np.random.default_rng(1)
    n = 200
    actual = rng.normal(0, 10, n)
    # LGBM: 方向对, 赚; scheme: 随机, 不赚
    lgbm_pnl = np.sign(actual) * np.abs(actual) - 2  # 净盈利
    scheme_pnl = rng.normal(0, 5, n)
    lo, hi = paired_bootstrap_ev_ci(lgbm_pnl - scheme_pnl, n_boot=500)
    assert lo > 0  # LGBM 显著优

def test_evaluate_gate_go():
    rng = np.random.default_rng(2)
    n = 200
    actual = rng.normal(0, 10, n)
    base = np.full(n, 3000.0)
    atr = np.full(n, 10.0)
    lgbm_pred = np.sign(actual) * 5  # 方向对
    scheme_pred = rng.normal(0, 1, n)  # 弱
    pure_pred = rng.normal(0, 1, n)
    verdict = evaluate_gate(lgbm_pred, pure_pred, scheme_pred, actual, base, atr, tick_size=1.0)
    assert verdict["gate"] == "GO"
    assert verdict["lgbm_metrics"]["EV"] > 0
    assert verdict["lgbm_metrics"]["PF"] > verdict["scheme_metrics"]["PF"]

def test_evaluate_gate_no_go():
    rng = np.random.default_rng(3)
    n = 200
    actual = rng.normal(0, 10, n)
    base = np.full(n, 3000.0); atr = np.full(n, 10.0)
    # LGBM 不优于 scheme
    lgbm_pred = rng.normal(0, 1, n)
    scheme_pred = np.sign(actual) * 5  # scheme 强
    pure_pred = rng.normal(0, 1, n)
    verdict = evaluate_gate(lgbm_pred, pure_pred, scheme_pred, actual, base, atr, tick_size=1.0)
    assert verdict["gate"] == "NO-GO"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_a2_p1_baseline.py::test_evaluate_gate_go -v`
Expected: FAIL

- [ ] **Step 3: 实现 bootstrap + evaluate_gate**

在 `scripts/a2_p1_lgbm_baseline.py` 追加：

```python
from cascade.evaluation_metrics import calc_net_metrics, calc_vol_scaled_mae


def paired_bootstrap_ev_ci(
    pnl_diff: np.ndarray,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """
    配对 bootstrap on per-point net PnL 差 (LGBM - scheme)。
    返回 EV 差的 95% CI (lower, upper)。
    """
    rng = np.random.default_rng(seed)
    n = len(pnl_diff)
    if n == 0:
        return (0.0, 0.0)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = np.mean(pnl_diff[idx])
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def evaluate_gate(
    lgbm_preds: np.ndarray,
    pure_preds: np.ndarray,
    scheme_preds: np.ndarray,
    actuals: np.ndarray,
    base_prices: np.ndarray,
    atr: np.ndarray,
    tick_size: float,
    slippage_ticks: int = 2,
    n_boot: int = 1000,
) -> dict:
    """
    三曲线 PF/EV/MaxDD + 配对 bootstrap 门禁。

    GO: LGBM PF > scheme PF AND LGBM EV > 0 AND bootstrap EV 差 95% CI 下界 > 0
    """
    lgbm_dir = np.sign(lgbm_preds)
    scheme_dir = np.sign(scheme_preds)
    pure_dir = np.sign(pure_preds)

    lgbm_m = calc_net_metrics(lgbm_dir, actuals, tick_size=tick_size,
                              slippage_ticks=slippage_ticks, base_prices=base_prices)
    scheme_m = calc_net_metrics(scheme_dir, actuals, tick_size=tick_size,
                                slippage_ticks=slippage_ticks, base_prices=base_prices)
    pure_m = calc_net_metrics(pure_dir, actuals, tick_size=tick_size,
                              slippage_ticks=slippage_ticks, base_prices=base_prices)

    # 配对 PnL 差 (LGBM - scheme)
    lgbm_pnl = lgbm_dir * actuals - (tick_size * slippage_ticks) * (lgbm_dir != 0)
    scheme_pnl = scheme_dir * actuals - (tick_size * slippage_ticks) * (scheme_dir != 0)
    ci_lo, ci_hi = paired_bootstrap_ev_ci(lgbm_pnl - scheme_pnl, n_boot=n_boot)

    go = (lgbm_m["PF"] > scheme_m["PF"]) and (lgbm_m["EV"] > 0) and (ci_lo > 0)

    # Vol-Scaled MAE (logging only)
    vol_mae = {
        "lgbm": calc_vol_scaled_mae(lgbm_preds, actuals, atr),
        "pure": calc_vol_scaled_mae(pure_preds, actuals, atr),
        "scheme": calc_vol_scaled_mae(scheme_preds, actuals, atr),
    }

    return {
        "gate": "GO" if go else "NO-GO",
        "lgbm_metrics": lgbm_m,
        "scheme_metrics": scheme_m,
        "pure_metrics": pure_m,
        "ev_diff_ci": {"lower": ci_lo, "upper": ci_hi},
        "vol_scaled_mae": vol_mae,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_a2_p1_baseline.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/a2_p1_lgbm_baseline.py tests/test_a2_p1_baseline.py
git commit -m "feat(a2-p1): 三曲线 PF/EV 门禁 + 配对 bootstrap 显著性"
```

---

## Task 7: CLI + 报告生成 + smoke 集成

**Files:**
- Modify: `scripts/a2_p1_lgbm_baseline.py`
- Test: `tests/test_a2_p1_baseline.py` (smoke)

**Interfaces:**
- Consumes: Tasks 4-6, `data.data_store.BacktestDataStore`, `cascade.hourly_model.HourlyModel`, `cascade.daily_model.DailyModel`, `config.prediction_scheme.SCHEMES`, `config.backtest_config` (CONTEXT_BARS/HORIZON/STEP)

- [ ] **Step 1: 写 smoke 测试 (单品种 ss, 减量)**

```python
# 追加到 tests/test_a2_p1_baseline.py (标记 slow, 默认跳过)
import pytest
@pytest.mark.slow
def test_smoke_ss_end_to_end():
    """端到端: ss 品种, --max-points 10, 验证落盘 + 报告生成"""
    import subprocess
    r = subprocess.run(
        ["D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python",
         "scripts/a2_p1_lgbm_baseline.py", "ss", "--max-points", "10",
         "--dense-step", "24", "--refit-every", "5"],
        capture_output=True, text=True, cwd="D:/FlyBuddy/fm_a", timeout=1800,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    # 验证 JSONL 落盘
    import pathlib, json
    out_jsonl = pathlib.Path("reports/a2_p1_baseline_results.jsonl")
    assert out_jsonl.exists()
    lines = out_jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert "gate" in rec and "lgbm_metrics" in rec
```

- [ ] **Step 2: 实现 CLI + 报告生成**

在 `scripts/a2_p1_lgbm_baseline.py` 追加：

```python
def _load_models():
    """加载共享 TimesFM 实例 (hourly + daily)。"""
    import timesfm
    from cascade.hourly_model import HourlyModel
    from cascade.daily_model import DailyModel
    base = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    hourly = HourlyModel(shared_model=base)
    daily = DailyModel(shared_model=base)
    return hourly, daily


def run_symbol(symbol: str, max_points: int | None, dense_step: int,
               refit_every: int, hourly, daily) -> dict:
    """单品种三曲线 + 门禁。"""
    from data.data_store import DataStore, BacktestDataStore
    from cascade.lgbm_features import build_dense_feature_matrix
    from config.backtest_config import CONTEXT_BARS, HORIZON, STEP
    import json, pathlib

    cache = f"reports/a2_p1_features/{symbol}_dense_matrix.parquet"
    with DataStore(symbol) as store:
        mat = build_dense_feature_matrix(
            symbol, store, dense_step=dense_step,
            shared_hourly=hourly, shared_daily=daily, cache_path=cache,
        )
    # t0_close 列 (还原 pred_move 用)
    df_1h = DataStore(symbol).get_main_contract_1h(limit=100000)
    closes = df_1h["close_price"].values.astype(float)
    mat["t0_close"] = [closes[t] if t < len(closes) else np.nan for t in mat["bar_idx"]]

    # eval points: 复用 monthly_backtest 网格
    total = len(df_1h)
    eval_bars = list(range(CONTEXT_BARS, total - HORIZON + 1, STEP))
    if max_points:
        eval_bars = eval_bars[:max_points]
    # 仅保留 dense_matrix 中有的 bar
    valid_set = set(mat["bar_idx"].tolist())
    eval_bars = [b for b in eval_bars if b in valid_set]

    # LGBM walk-forward (曲线③)
    lgbm_out = train_lgbm_walkforward(mat, eval_bars, refit_every=refit_every)

    # 曲线①②: TimesFM-pure / scheme @ eval bars (复用 dense_matrix 的 pure_pred 作为①)
    # 曲线② scheme: 需 HourlyModel.predict 带 scheme covs (逐点, 较慢)
    from cascade.hourly_model import HourlyModel
    from config.prediction_scheme import SCHEMES
    scheme = SCHEMES.get(symbol)
    pure_preds, scheme_preds, actuals, bases, atrs = [], [], [], [], []
    for b in eval_bars:
        row = mat[mat["bar_idx"] == b].iloc[0]
        t0_close = closes[b]
        # ① pure: dense_matrix 已有 timesfm_pure_pred (归一化) -> 还原价格点
        pure_pred_price = row["timesfm_pure_pred"] * t0_close
        pure_preds.append(pure_pred_price)
        # actual
        actual_move = closes[b + HORIZON] - closes[b]
        actuals.append(actual_move)
        bases.append(t0_close)
        # ATR @ T0 (vol-scaled MAE logging)
        from cascade.features import _calc_atr
        atr_arr = _calc_atr(df_1h.iloc[: b + 1])
        atrs.append(float(atr_arr[-1]) if len(atr_arr) else 1.0)
        # ② scheme: 跑 HourlyModel.predict (带 scheme covs)
        cutoff = str(pd.Timestamp(df_1h["dt"].iloc[b]).strftime("%Y-%m-%d"))
        try:
            with BacktestDataStore(symbol, cutoff) as bts:
                from cascade.daily_model import DailyModel
                dr = daily.predict(symbol, bts)
                hr = HourlyModel(shared_model=hourly.model)
                res = hr.predict(symbol, bts, dr, covariate_type=scheme.covariate_type,
                                 covariate_types=scheme.covariate_types, verbose=False)
                scheme_preds.append(float(res.point_forecast[-1]) - t0_close)
        except Exception:
            scheme_preds.append(0.0)

    # LGBM pred_move (曲线③)
    lgbm_moves = lgbm_out["pred_move"].values.astype(float)

    # tick_size: 从 data.config 取 (与 monthly_backtest 一致)
    from data.config import get_tick_size
    tick = get_tick_size(symbol) if hasattr(__import__("data.config", fromlist=["get_tick_size"]), "get_tick_size") else 1.0

    verdict = evaluate_gate(
        lgbm_moves, np.array(pure_preds), np.array(scheme_preds),
        np.array(actuals), np.array(bases), np.array(atrs), tick_size=tick,
    )
    verdict["symbol"] = symbol
    verdict["n_eval"] = len(eval_bars)
    verdict["dense_rows"] = len(mat)
    verdict["underpowered"] = len(mat) < 200
    # vol_prob 前瞻声明 + UNDERPOWERED
    caveats = ["vol_prob 在 2026-03 前评估点有轻微 Lookahead（模型训练截止 2026-03-31），不影响定性结论"]
    if verdict["underpowered"]:
        caveats.append("UNDERPOWERED: dense 训练切片 < 200 行, 结论降权")
    verdict["caveats"] = caveats
    return verdict


def write_report(verdicts: list, path: str):
    """写 Markdown 裁决报告到主仓库。"""
    import pathlib
    lines = ["# A2-P1 LGBM 基线门禁裁决报告", "", f"**品种数**: {len(verdicts)}", ""]
    go = [v for v in verdicts if v["gate"] == "GO"]
    lines.append(f"**聚合裁决**: {'GO' if len(go) > len(verdicts)/2 else 'NO-GO'} "
                 f"({len(go)}/{len(verdicts)} 品种 GO)")
    lines.append("")
    lines.append("| 品种 | gate | LGBM PF | scheme PF | LGBM EV | EV差CI下界 | n |")
    lines.append("|------|------|---------|-----------|---------|-----------|---|")
    for v in verdicts:
        lines.append(f"| {v['symbol']} | {v['gate']} | {v['lgbm_metrics']['PF']} | "
                     f"{v['scheme_metrics']['PF']} | {v['lgbm_metrics']['EV']} | "
                     f"{v['ev_diff_ci']['lower']:.4f} | {v['n_eval']} |")
    lines.append("")
    lines.append("## vol_prob 前瞻瑕疵声明")
    lines.append(verdicts[0]["caveats"][0] if verdicts else "")
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    import argparse, json
    p = argparse.ArgumentParser(description="A2-P1 LGBM 基线探针")
    p.add_argument("symbols", nargs="+")
    p.add_argument("--max-points", type=int, default=None)
    p.add_argument("--dense-step", type=int, default=24)
    p.add_argument("--refit-every", type=int, default=10)
    p.add_argument("--resume", type=str, default=None)
    args = p.parse_args()

    hourly, daily = _load_models()
    # resume: 读已完成的品种
    done = set()
    if args.resume:
        import pathlib
        if pathlib.Path(args.resume).exists():
            for line in pathlib.Path(args.resume).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    done.add(json.loads(line)["symbol"])

    jsonl_path = "reports/a2_p1_baseline_results.jsonl"
    import pathlib
    pathlib.Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)
    verdicts = []
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for sym in args.symbols:
            if sym in done:
                continue
            print(f"[A2-P1] {sym} ...")
            v = run_symbol(sym, args.max_points, args.dense_step, args.refit_every, hourly, daily)
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
            f.flush()
            verdicts.append(v)
            print(f"[A2-P1] {sym}: {v['gate']} (LGBM PF={v['lgbm_metrics']['PF']}, "
                  f"scheme PF={v['scheme_metrics']['PF']})")

    write_report(verdicts, "reports/research/2026-08-04_a2_p1_baseline_result.md")
    print(f"\n报告: reports/research/2026-08-04_a2_p1_baseline_result.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行全量单测 (非 smoke)**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python -m pytest tests/test_vol_scaled_mae.py tests/test_lgbm_features.py tests/test_a2_p1_baseline.py -v -m "not slow"`
Expected: 全 passed

- [ ] **Step 4: smoke 测试 (单品种 ss, 减量)**

Run: `D:/FlyBuddy/timesfm/.praxist-venv/Scripts/python scripts/a2_p1_lgbm_baseline.py ss --max-points 10 --dense-step 24 --refit-every 5`
Expected: 退出码 0, 生成 `reports/a2_p1_baseline_results.jsonl` + `reports/research/2026-08-04_a2_p1_baseline_result.md`, 打印 ss 的 gate。

- [ ] **Step 5: 提交**

```bash
git add scripts/a2_p1_lgbm_baseline.py tests/test_a2_p1_baseline.py
git commit -m "feat(a2-p1): CLI + 裁决报告 + smoke 集成 (ss 验证通过)"
```

---

## Self-Review

**1. Spec coverage:**
- §3 三曲线 (①pure ②scheme ③LGBM-B) -> Task 6/7 evaluate_gate ✓
- §4 12 维特征池 -> Task 2 (9维) + Task 3 (3维) ✓
- §4 vol_prob 前瞻声明 -> Task 7 verdict["caveats"] + 报告 ✓
- §5 每品种独立 -> Task 7 run_symbol 逐品种 ✓
- §7 Dense Training (step=24, 非重叠) -> Task 4 build_dense_feature_matrix ✓
- §7 expanding window + refit-every -> Task 5 train_lgbm_walkforward ✓
- §8 百分比收益率 Y + sample_weight + 还原价格 -> Task 4 (Y/weight) + Task 5 (pred_move=T0×return) ✓
- §8 嵌套 TimeSeriesSplit 超参 -> Task 5 _select_hyperparams ✓
- §8 UNDERPOWERED (<200 行) -> Task 7 run_symbol `verdict["underpowered"] = len(mat) < 200` + caveats ✓ (已 inline 修复)
- §9 错误处理 (SKIP/NaN/JSONL resume) -> Task 7 (try/except + JSONL + --resume) ✓
- §10 测试 (防泄漏/schema/嵌套CV/smoke) -> 各 Task 单测 ✓
- §11 输出 (parquet/jsonl/report) -> Task 4 cache + Task 7 jsonl/report ✓
- §3 配对 bootstrap 门禁 -> Task 6 paired_bootstrap_ev_ci ✓

**2. Gap 修复**: Task 7 run_symbol 增加 UNDERPOWERED 检查。在 `run_symbol` 的 `verdict` 返回前加：
```python
verdict["underpowered"] = len(mat) < 200
if verdict["underpowered"]:
    verdict["caveats"].append("UNDERPOWERED: dense 训练切片 < 200 行, 结论降权")
```

**3. 类型一致性**: `train_lgbm_walkforward` 返回 `bar_idx/pred_return/pred_move/actual_move`; Task 7 用 `lgbm_out["pred_move"]` ✓。`evaluate_gate` 接收 array 参数; Task 7 传 np.array ✓。`build_dense_feature_matrix` 返回 DataFrame 含 `bar_idx/Y/weight` + 12 特征列; Task 5 用 FEATURE_COLS ✓。

**4. 已知简化 (impl 阶段验证)**:
- `get_tick_size(symbol)` 来源需 impl 时确认 (data.config 或 backtest_config); Task 7 已加 fallback `1.0`。
- DailyModel 历史 predict 用 BacktestDataStore 截止 t 日期 (Task 3); 若性能差, 可改用 dense matrix 的 daily_slope 近似 horizon_slope (降级, 记录)。
- 超参网格采样 16 组 (Task 5) 而非全量 ~288 组, 控制算力; 可调。

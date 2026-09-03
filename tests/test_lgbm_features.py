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
    # 2026-08-30 同步: hour_of_day 已改为 hour_sin/hour_cos 周期编码 (与 calendar_cyclical 同哲学)
    expected_keys = {"daily_slope","hourly_slope","pca_momentum","rsi_state",
                     "oi_pct_change","hurst","vol_prob","hour_sin","hour_cos","day_of_week"}
    assert set(feats.keys()) == expected_keys
    # sin/cos 有界 [-1,1], dow 是整数
    assert -1.0 <= feats["hour_sin"] <= 1.0
    assert -1.0 <= feats["hour_cos"] <= 1.0
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

from cascade.lgbm_features import compute_timesfm_features_batch

def test_timesfm_features_schema():
    # 用 mock hourly/daily model 避免加载真模型
    class MockHourly:
        def _fallback_predict(self, closes, horizon=24):
            p = np.full(horizon, float(closes[-1]) * 1.01)
            q = np.column_stack([p-5, p-4, p-3, p-2, p-1, p, p+1, p+2, p+3, p+5])
            return p, q
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

from cascade.lgbm_features import build_dense_feature_matrix

def test_dense_matrix_schema_and_cache(tmp_path, monkeypatch):
    df_1h = _make_df_1h(700)
    df_daily = _make_df_daily(200)
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
    cache = str(tmp_path / "dense.parquet")
    mat = build_dense_feature_matrix("ss", FakeStore(), dense_step=24,
                                      shared_hourly=MockHourly(), shared_daily=MockDaily(),
                                      cache_path=cache)
    # 12 特征 + Y + weight (2026-08-30 同步: hour_of_day -> hour_sin/hour_cos 周期编码)
    feat_cols = {"daily_slope","hourly_slope","pca_momentum","rsi_state","oi_pct_change",
                 "hurst","vol_prob","hour_sin","hour_cos","day_of_week",
                 "timesfm_pure_pred","timesfm_confidence","horizon_slope"}
    assert feat_cols.issubset(mat.columns)
    assert "Y" in mat.columns and "weight" in mat.columns
    # Y = (close[t+24]-close[t])/close[t]
    closes = df_1h["close_price"].values
    first_t = mat["bar_idx"].iloc[0]
    expected_y = (closes[first_t+24] - closes[first_t]) / closes[first_t]
    assert abs(mat["Y"].iloc[0] - expected_y) < 1e-9
    # 缓存文件已生成
    import pathlib
    assert pathlib.Path(cache).exists()

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
    # 篡改未来数据, 特征不变
    t0 = mat["bar_idx"].iloc[0]
    df_1h_b = df_1h.copy()
    df_1h_b.loc[t0+25:, "close_price"] = 99999.0
    class FakeStoreB(FakeStore):
        def get_main_contract_1h(self, limit=1023): return df_1h_b
    mat_b = build_dense_feature_matrix("ss", FakeStoreB(), dense_step=24,
                                       shared_hourly=MockHourly(), shared_daily=MockDaily())
    for col in ["hourly_slope","pca_momentum","rsi_state","hurst"]:
        assert mat[col].iloc[0] == mat_b[col].iloc[0], f"{col} 被未来污染"

import os, pickle, sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from monthly_backtest import (
    _daily_cache_path, _model_fingerprint, _daily_predict_cached,
    _load_daily_cache, _save_daily_cache,
)

def _fake_weights(tmp_path, name="model.safetensors", blob=b"W" * 64):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / name
    p.write_bytes(blob)
    return str(tmp_path)

def test_cache_key_contains_symbol_cutoff_window(tmp_path):
    fp = _model_fingerprint(str(tmp_path / "c"), weights_dir=_fake_weights(tmp_path / "w"))
    p1 = _daily_cache_path(str(tmp_path / "c"), "m", "2021-01-05 14:00:00", "250x22", fp)
    p2 = _daily_cache_path(str(tmp_path / "c"), "m", "2021-01-06 09:00:00", "250x22", fp)
    assert p1 != p2 and "m" in os.path.basename(p1)

def test_fingerprint_stable_then_invalidates_on_mtime(tmp_path, monkeypatch):
    wdir = tmp_path / "w"
    cache = str(tmp_path / "c")
    monkeypatch.setenv("TIMESFM_WEIGHTS_DIR", _fake_weights(wdir))
    fp1 = _model_fingerprint(cache)
    fp2 = _model_fingerprint(cache)
    assert fp1 == fp2 and len(fp1) == 12
    # 改 shard 内容+mtime → 必须换 fp (禁止 .model_fp 永缓存)
    shard = wdir / "model.safetensors"
    shard.write_bytes(b"V" * 64)
    os.utime(shard, (os.path.getmtime(shard) + 10, os.path.getmtime(shard) + 10))
    fp3 = _model_fingerprint(cache)
    assert fp3 != fp1

def test_roundtrip_dates_tz_naive(tmp_path):
    from cascade.daily_model import DailyResult
    r = DailyResult(
        symbol="m", forecast=np.arange(22.0),
        horizon_slope=-0.01, historical_closes=np.arange(250.0),
        historical_dates=pd.DatetimeIndex(["2020-12-01", "2020-12-02"]),
    )
    _save_daily_cache(str(tmp_path), "m", "2021-01-05 14:00:00", "250x22", "abc123", r)
    got = _load_daily_cache(str(tmp_path), "m", "2021-01-05 14:00:00", "250x22", "abc123")
    assert np.array_equal(got.forecast, r.forecast)
    assert np.array_equal(got.historical_closes, r.historical_closes)
    assert list(pd.DatetimeIndex(got.historical_dates).strftime("%Y-%m-%d")) == ["2020-12-01", "2020-12-02"]
    assert getattr(got.historical_dates, "tz", None) is None

@pytest.mark.slow
def test_ab_bitexact(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cascade.daily_model import DailyModel
    from data.data_store import BacktestDataStore
    from monthly_backtest import _daily_predict_cached
    d = DailyModel()
    calls = {"n": 0}
    real_predict = d.predict
    def wrapped(*a, **k):
        calls["n"] += 1
        return real_predict(*a, **k)
    monkeypatch.setattr(d, "predict", wrapped)
    cache = str(tmp_path)
    cutoffs = ["2021-01-05 14:00:00", "2021-01-11 09:00:00", "2021-01-14 13:00:00"]
    for c in cutoffs:
        store = BacktestDataStore("m", c)
        try:
            r_live = real_predict("m", store, context_days=250, horizon_days=22)
            n_before = calls["n"]
            r_miss = _daily_predict_cached(d, "m", c, 250, 22, cache, store)
            r_hit = _daily_predict_cached(d, "m", c, 250, 22, cache, store)
            assert calls["n"] == n_before + 1  # HIT 不得再 predict
            for r in (r_miss, r_hit):
                assert np.array_equal(r.forecast, r_live.forecast), f"forecast mismatch {c}"
                assert np.array_equal(r.historical_closes, r_live.historical_closes)
                assert abs(r.horizon_slope - r_live.horizon_slope) < 1e-12
                live_d = pd.DatetimeIndex(r_live.historical_dates).strftime("%Y-%m-%d")
                hit_d = pd.DatetimeIndex(r.historical_dates).strftime("%Y-%m-%d")
                assert list(hit_d) == list(live_d)
        finally:
            if hasattr(store, "close"):
                store.close()

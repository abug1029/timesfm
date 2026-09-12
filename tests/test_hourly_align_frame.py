"""C9: ALIGN 1H 帧与协变量矩阵同一根序列 (不加载 TimesFM)."""
import numpy as np
import pandas as pd
import pytest

from cascade.data_validator import ValidationResult
from cascade.daily_model import DailyResult
from cascade.features import (
    build_combo_covariate_matrix,
    build_covariate_matrix,
    calc_calendar_cyclical,
    calc_hourly_slope,
)
from cascade.hourly_model import HourlyModel

HORIZON = 24


def _frame(n, close0, last_dt, contract):
    dts = pd.date_range(end=pd.Timestamp(last_dt), periods=n, freq="h")
    close = close0 + np.arange(n, dtype=float) * 0.5
    return pd.DataFrame({
        "dt": dts,
        "open_price": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close_price": close,
        "volume": np.full(n, 1000.0),
        "open_interest": 50_000 + np.arange(n, dtype=float),
        "contract_code": contract,
        "ccl_value": np.full(n, 1000.0),
    })


def _main_df():
    return _frame(48, 100.0, "2026-01-02 14:00:00", "SS_MAIN")


def _align_df():
    return _frame(96, 200.0, "2026-01-10 14:00:00", "ss2609")


class FakeStore:
    def __init__(self, main_df, align_df):
        self.main_df = main_df
        self.align_df = align_df
        self.main_calls = 0
        self.klines_calls = 0

    def get_main_contract_1h(self, limit=480):
        self.main_calls += 1
        return self.main_df.tail(int(limit)).reset_index(drop=True)

    def get_klines_1h(self, contract_code=None, limit=480):
        self.klines_calls += 1
        return self.align_df.tail(int(limit)).reset_index(drop=True)


def _daily_inputs():
    hist = np.linspace(180.0, 210.0, 40)
    pred = np.linspace(210.0, 220.0, 22)
    dates = pd.date_range("2025-11-24", periods=40, freq="D")
    return hist, pred, dates


def _ctx_len(mat, horizon=HORIZON):
    return len(mat["daily_slope"]) - horizon


def _assert_follows_align(mat, align_df, main_df):
    ctx = _ctx_len(mat)
    assert ctx == len(align_df)
    assert ctx != len(main_df)
    last_ctx = ctx - 1
    expected_slope = calc_hourly_slope(align_df["close_price"].values)
    main_slope = calc_hourly_slope(main_df["close_price"].values)
    assert mat["hourly_slope"][last_ctx] == pytest.approx(float(expected_slope.iloc[-1]))
    assert mat["hourly_slope"][last_ctx] != pytest.approx(float(main_slope.iloc[-1]))
    expected_cal = calc_calendar_cyclical(align_df, HORIZON)
    main_cal = calc_calendar_cyclical(main_df, HORIZON)
    assert mat["calendar_doy_sin"][last_ctx] == pytest.approx(float(expected_cal[len(align_df) - 1, 0]))
    assert mat["calendar_doy_sin"][last_ctx] != pytest.approx(float(main_cal[len(main_df) - 1, 0]))
    assert align_df["close_price"].iloc[-1] == pytest.approx(200.0 + 95 * 0.5)
    assert main_df["close_price"].iloc[-1] == pytest.approx(100.0 + 47 * 0.5)
    assert pd.Timestamp(align_df["dt"].iloc[-1]) == pd.Timestamp("2026-01-10 14:00:00")
    assert pd.Timestamp(main_df["dt"].iloc[-1]) == pd.Timestamp("2026-01-02 14:00:00")


def test_single_passed_df_1h_follows_align_not_main():
    main_df, align_df = _main_df(), _align_df()
    store = FakeStore(main_df, align_df)
    hist, pred, dates = _daily_inputs()

    mat_default = build_covariate_matrix(
        "ss", store, hist, pred, dates, horizon=HORIZON,
        covariate_type="hourly_slope",
    )
    assert _ctx_len(mat_default) == len(main_df)
    assert store.main_calls >= 1

    store.main_calls = 0
    mat = build_covariate_matrix(
        "ss", store, hist, pred, dates, horizon=HORIZON,
        covariate_type="hourly_slope",
        df_1h=align_df,
    )
    cal = build_covariate_matrix(
        "ss", store, hist, pred, dates, horizon=HORIZON,
        covariate_type="calendar_cyclical",
        df_1h=align_df,
    )
    assert store.main_calls == 0
    mat["calendar_doy_sin"] = cal["calendar_doy_sin"]
    _assert_follows_align(mat, align_df, main_df)


def test_combo_passed_df_1h_follows_align_not_main():
    main_df, align_df = _main_df(), _align_df()
    store = FakeStore(main_df, align_df)
    hist, pred, dates = _daily_inputs()

    mat_default = build_combo_covariate_matrix(
        "ss", store, hist, pred, dates, horizon=HORIZON,
        covariate_types=["hourly_slope", "calendar_cyclical"],
    )
    assert _ctx_len(mat_default) == len(main_df)
    assert store.main_calls >= 1

    store.main_calls = 0
    mat = build_combo_covariate_matrix(
        "ss", store, hist, pred, dates, horizon=HORIZON,
        covariate_types=["hourly_slope", "calendar_cyclical"],
        df_1h=align_df,
    )
    assert store.main_calls == 0
    _assert_follows_align(mat, align_df, main_df)


def _daily_result():
    hist, pred, dates = _daily_inputs()
    return DailyResult(
        symbol="ss",
        forecast=pred,
        horizon_slope=0.001,
        historical_closes=hist,
        historical_dates=dates,
    )


def _align_vr():
    return ValidationResult(
        ok=True,
        contract_1h="ss2605",
        contract_daily="ss2609",
    )


class _FakeTimesFM:
    def compile(self, config):
        pass

    def forecast_with_covariates(self, **kwargs):
        h = 24
        return [np.ones(h)], [np.ones((h, 10))]


def test_hourly_predict_passes_align_df_1h_to_single_build(monkeypatch):
    main_df, align_df = _main_df(), _align_df()
    store = FakeStore(main_df, align_df)
    captured = {}

    def fake_build(**kwargs):
        captured["df_1h"] = kwargs.get("df_1h")
        n = len(kwargs["df_1h"]) if kwargs.get("df_1h") is not None else 48
        h = kwargs.get("horizon", HORIZON)
        arr = np.zeros(n + h, dtype=float)
        return {"daily_slope": arr, "hourly_slope": arr.copy()}

    monkeypatch.setattr("cascade.data_validator.validate_prediction_data", lambda *a, **k: _align_vr())
    monkeypatch.setattr("cascade.hourly_model.build_covariate_matrix", fake_build)

    model = HourlyModel.__new__(HourlyModel)
    model.model = _FakeTimesFM()
    model.predict(
        "ss", store, _daily_result(),
        visualize=False, verbose=False, skip_validation=True,
        covariate_type="hourly_slope",
    )
    passed = captured.get("df_1h")
    assert passed is not None
    assert len(passed) == len(align_df)
    assert passed["close_price"].iloc[-1] == pytest.approx(align_df["close_price"].iloc[-1])
    assert passed["close_price"].iloc[-1] != pytest.approx(main_df["close_price"].iloc[-1])
    assert pd.Timestamp(passed["dt"].iloc[-1]) == pd.Timestamp(align_df["dt"].iloc[-1])


def test_hourly_predict_passes_align_df_1h_to_combo_build(monkeypatch):
    main_df, align_df = _main_df(), _align_df()
    store = FakeStore(main_df, align_df)
    captured = {}

    def fake_combo(**kwargs):
        captured["df_1h"] = kwargs.get("df_1h")
        n = len(kwargs["df_1h"]) if kwargs.get("df_1h") is not None else 48
        h = kwargs.get("horizon", HORIZON)
        arr = np.zeros(n + h, dtype=float)
        return {"daily_slope": arr, "hourly_slope": arr.copy(), "oi_pct_change": arr.copy()}

    monkeypatch.setattr("cascade.data_validator.validate_prediction_data", lambda *a, **k: _align_vr())
    monkeypatch.setattr("cascade.hourly_model.build_combo_covariate_matrix", fake_combo)

    model = HourlyModel.__new__(HourlyModel)
    model.model = _FakeTimesFM()
    model.predict(
        "ss", store, _daily_result(),
        visualize=False, verbose=False, skip_validation=True,
        covariate_types=["hourly_slope", "oi"],
    )
    passed = captured.get("df_1h")
    assert passed is not None
    assert len(passed) == len(align_df)
    assert passed["close_price"].iloc[-1] == pytest.approx(align_df["close_price"].iloc[-1])
    assert passed["close_price"].iloc[-1] != pytest.approx(main_df["close_price"].iloc[-1])

import timesfm
from cascade.daily_model import (
    FP_FIELDS,
    FM_COMPILED_FP_ATTR,
    DailyModel,
    forecast_config_fp,
    ensure_compiled,
)


class FakeModel:
    def __init__(self):
        self.n = 0
        self.last = None

    def compile(self, config, **kwargs):
        self.n += 1
        self.last = config

    def forecast(self, horizon, inputs):
        import numpy as np
        h = horizon
        point = [np.linspace(100.0, 101.0, h)]
        quant = [np.tile(point[0][:, None], (1, 10))]
        return point, quant


def test_fp_none_on_missing_fields():
    assert forecast_config_fp(object()) is None


def test_fp_stable_for_same_config():
    a = DailyModel._DAILY_CONFIG
    b = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=256,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    )
    assert forecast_config_fp(a) == forecast_config_fp(b)
    assert len(forecast_config_fp(a)) == len(FP_FIELDS)


def test_ensure_compiled_skips_same_fp():
    m = FakeModel()
    cfg = DailyModel._DAILY_CONFIG
    ensure_compiled(m, cfg)
    ensure_compiled(m, cfg)
    assert m.n == 1
    assert getattr(m, FM_COMPILED_FP_ATTR) == forecast_config_fp(cfg)


def test_ensure_compiled_runs_when_config_changes():
    m = FakeModel()
    ensure_compiled(m, DailyModel._DAILY_CONFIG)
    other = timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=128,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
        return_backcast=True,
    )
    ensure_compiled(m, other)
    assert m.n == 2
    assert m.last is other


def test_ensure_compiled_does_not_write_fp_if_compile_raises():
    class Boom(FakeModel):
        def compile(self, config, **kwargs):
            self.n += 1
            raise RuntimeError("compile failed")

    m = Boom()
    try:
        ensure_compiled(m, DailyModel._DAILY_CONFIG)
        raise AssertionError("should raise")
    except RuntimeError:
        pass
    assert m.n == 1
    assert not hasattr(m, FM_COMPILED_FP_ATTR) or getattr(m, FM_COMPILED_FP_ATTR, None) is None

import numpy as np
import pandas as pd
from cascade.hourly_model import HourlyModel


class _Store:
    cutoff_date = "2020-02-28"
    def get_main_continuous(self, limit=250):
        n = max(limit, 40)
        dates = pd.bdate_range("2020-01-02", periods=n)
        return pd.DataFrame({
            "dt": dates,
            "close_price": np.linspace(3000.0, 3100.0, n),
        })


def test_daily_predict_skips_second_compile():
    m = FakeModel()
    model = DailyModel(shared_model=m)
    assert m.n == 1
    store = _Store()
    r1 = model.predict("m", store, context_days=40, horizon_days=22)
    r2 = model.predict("m", store, context_days=40, horizon_days=22)
    assert m.n == 1
    assert np.array_equal(r1.forecast, r2.forecast)


def test_shared_model_daily_then_hourly_must_recompile():
    m = FakeModel()
    DailyModel(shared_model=m)
    n_after_daily = m.n
    HourlyModel(shared_model=m)
    assert m.n == n_after_daily + 1
    ensure_compiled(m, HourlyModel._XREG_CONFIG)
    assert m.n == n_after_daily + 1
    ensure_compiled(m, DailyModel._DAILY_CONFIG)
    assert m.n == n_after_daily + 2

import pytest
from data.data_store import BacktestDataStore


@pytest.mark.slow
def test_skip_vs_force_compile_bitexact_real_model():
    cutoffs = [
        "2021-01-05 14:00:00",
        "2021-01-11 09:00:00",
        "2021-01-14 13:00:00",
    ]
    probe = BacktestDataStore("m", cutoffs[0])
    try:
        df = probe.get_main_continuous(limit=30)
        if df is None or getattr(df, "empty", True):
            pytest.skip("no m daily data")
        df1h = probe.get_main_contract_1h(limit=30)
        if df1h is None or getattr(df1h, "empty", True):
            pytest.skip("no m 1h data")
    finally:
        probe.close()

    daily = DailyModel()
    hourly = HourlyModel(shared_model=daily.model)
    for cutoff in cutoffs:
        with BacktestDataStore("m", cutoff) as store:
            # warmup compiles DAILY if last cutoff left XREG; r_skip then hits skip
            daily.predict("m", store, context_days=250, horizon_days=22)
            r_skip = daily.predict("m", store, context_days=250, horizon_days=22)
            daily.model.compile(DailyModel._DAILY_CONFIG)
            setattr(daily.model, FM_COMPILED_FP_ATTR, None)
            r_force = daily.predict("m", store, context_days=250, horizon_days=22)
            assert np.array_equal(r_skip.forecast, r_force.forecast), cutoff

            # warmup compiles XREG after daily; h_skip then hits skip
            hourly.predict(
                "m", store, r_skip, horizon=24, visualize=False,
                covariate_type="ccl", verbose=False,
            )
            h_skip = hourly.predict(
                "m", store, r_skip, horizon=24, visualize=False,
                covariate_type="ccl", verbose=False,
            )
            hourly.model.compile(HourlyModel._XREG_CONFIG)
            setattr(hourly.model, FM_COMPILED_FP_ATTR, None)
            h_force = hourly.predict(
                "m", store, r_force, horizon=24, visualize=False,
                covariate_type="ccl", verbose=False,
            )
            assert np.array_equal(h_skip.point_forecast, h_force.point_forecast), cutoff

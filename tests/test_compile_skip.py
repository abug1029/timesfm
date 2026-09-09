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
"""C12: combo rsi_state must match single-path daily RSI mapped onto 1H.

Single-path build_covariate_matrix uses daily RSI forward-filled onto 1H
bars, then horizon decay from the last context state. Combo previously
computed RSI on 1H closes under the same name. This locks both paths to
the daily mapping. Does not load TimesFM.
"""
import numpy as np
import pandas as pd
import pytest

from cascade.features import (
    build_combo_covariate_matrix,
    build_covariate_matrix,
    calc_rsi_state,
)

HORIZON = 24
LIMIT = 480
RSI_TYPES = ("rsi_state", "rsi6", "rsi12", "rsi24")


class FakeStore:
    def __init__(self, df_1h):
        self.df_1h = df_1h

    def get_main_contract_1h(self, limit=480):
        return self.df_1h.tail(int(limit)).reset_index(drop=True)


def _inputs():
    """1H oscillates (hourly RSI ~0); daily hist is a strong uptrend."""
    n_1h = LIMIT
    dts = pd.date_range(end=pd.Timestamp("2026-03-01 14:00:00"), periods=n_1h, freq="h")
    close_1h = 3000.0 + 20.0 * np.sin(np.arange(n_1h, dtype=float) / 3.0)
    df_1h = pd.DataFrame({
        "dt": dts,
        "open": close_1h,
        "high": close_1h + 1.0,
        "low": close_1h - 1.0,
        "close": close_1h,
        "close_price": close_1h,
        "volume": np.full(n_1h, 1000.0),
        "open_interest": 80_000 + np.arange(n_1h, dtype=float),
    })

    n_daily = 40
    daily_dates = pd.date_range(end=pd.Timestamp("2026-03-01"), periods=n_daily, freq="D")
    hist = 2000.0 + np.linspace(0.0, 2000.0, n_daily)
    pred = hist[-1] + np.array([40.0, 80.0])
    store = FakeStore(df_1h)
    return store, hist, pred, daily_dates, df_1h


@pytest.mark.parametrize("cov", RSI_TYPES)
def test_combo_rsi_state_matches_single_path(cov):
    store, hist, pred, daily_dates, df_1h = _inputs()

    single = build_covariate_matrix(
        "m", store, hist, pred, daily_dates,
        horizon=HORIZON, limit=LIMIT, covariate_type=cov,
    )
    combo = build_combo_covariate_matrix(
        "m", store, hist, pred, daily_dates,
        horizon=HORIZON, limit=LIMIT, covariate_types=[cov],
    )

    assert cov in single
    assert cov in combo
    assert len(combo[cov]) == len(single[cov])
    assert len(combo[cov]) == len(combo["daily_slope"])
    np.testing.assert_allclose(combo[cov], single[cov])

    hourly = calc_rsi_state(
        df_1h["close_price"].values.astype(float),
        rsi_period={"rsi_state": 14, "rsi6": 6, "rsi12": 12, "rsi24": 24}[cov],
    ).astype(float)
    ctx_len = len(df_1h)
    assert not np.allclose(single[cov][:ctx_len], hourly), (
        "fixture vacuous: daily-mapped rsi_state already equals 1H RSI; "
        "cannot detect the C12 mix-up"
    )

"""DailyModel.predict 读框: 实盘走 get_safe_daily, 回测仍走 get_main_continuous."""
from datetime import date, datetime

import pandas as pd

from cascade.daily_model import read_daily_frame


def _frame_with_today():
    return pd.DataFrame({
        "dt": ["2026-09-08", "2026-09-09", "2026-09-10"],
        "close_price": [100.0, 101.0, 102.0],
    })


class _LiveStore:
    def __init__(self, df):
        self._df = df

    def get_main_continuous(self, limit=None):
        if limit is None:
            return self._df.copy()
        return self._df.tail(int(limit)).reset_index(drop=True)


class _BacktestStore(_LiveStore):
    cutoff_date = "2026-09-10 10:30:00"


def test_live_store_trims_unclosed_today_before_15():
    """活 DataStore、10:30、库尾含今日日线 → 读框不含今日。"""
    store = _LiveStore(_frame_with_today())
    result = read_daily_frame(
        "ss", store, context_days=10, now_dt=datetime(2026, 9, 10, 10, 30),
    )
    assert not result.empty
    last = pd.to_datetime(result["dt"].iloc[-1]).date()
    assert last == date(2026, 9, 9)
    days = set(pd.to_datetime(result["dt"]).dt.date)
    assert date(2026, 9, 10) not in days


def test_backtest_store_still_uses_get_main_continuous():
    """有 cutoff_date 的 store 不走 get_safe_daily。"""
    store = _BacktestStore(_frame_with_today())
    result = read_daily_frame(
        "ss", store, context_days=10, now_dt=datetime(2026, 9, 10, 10, 30),
    )
    days = set(pd.to_datetime(result["dt"]).dt.date)
    assert date(2026, 9, 10) in days
    assert pd.to_datetime(result["dt"].iloc[-1]).date() == date(2026, 9, 10)

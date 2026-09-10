from datetime import date, datetime
from unittest.mock import MagicMock
import pandas as pd
import pytest

from data.data_store import get_safe_daily


def _make_mock_store(dates):
    """构造 Mock store, 返回指定日期的日线 DataFrame"""
    df = pd.DataFrame({'dt': dates, 'close': [100.0] * len(dates)})
    mock = MagicMock()
    mock.get_main_continuous.return_value = df
    return mock


def test_intraday_daily_auto_trim():
    """盘中(10:30)读到今日日线 -> 自动剔除, 不报错"""
    mock_store = _make_mock_store(['2026-09-09', '2026-09-10'])
    result = get_safe_daily('ss', now_dt=datetime(2026, 9, 10, 10, 30), store=mock_store)
    assert len(result) == 1
    assert pd.to_datetime(result['dt'].iloc[-1]).date() == date(2026, 9, 9)


def test_night_session_daily_kept():
    """夜盘(21:30)读到今日日线 -> 保留(已收盘)"""
    mock_store = _make_mock_store(['2026-09-09', '2026-09-10'])
    result = get_safe_daily('ss', now_dt=datetime(2026, 9, 10, 21, 30), store=mock_store)
    assert len(result) == 2
    assert pd.to_datetime(result['dt'].iloc[-1]).date() == date(2026, 9, 10)


def test_night_session_cross_day_future_trimmed():
    """★★★ 核心: 夜盘跨日归属下一交易日 -> 未来日线必须剔除"""
    mock_store = _make_mock_store(['2026-09-10', '2026-09-14'])
    result = get_safe_daily('ss', now_dt=datetime(2026, 9, 11, 21, 30), store=mock_store)
    assert len(result) == 1
    assert pd.to_datetime(result['dt'].iloc[-1]).date() == date(2026, 9, 10)


def test_night_session_cross_day_with_today_label():
    """夜盘跨日 + 当日已收盘同时存在 -> 未来行剔除, 当日保留"""
    mock_store = _make_mock_store(['2026-09-10', '2026-09-11', '2026-09-14'])
    result = get_safe_daily('ss', now_dt=datetime(2026, 9, 11, 21, 30), store=mock_store)
    # 09-10 < 今天 -> 保留; 09-11 == 今天 且 hour=21 >= 15 -> 保留; 09-14 > 今天 -> 剔除
    assert len(result) == 2


def test_next_day_old_daily_kept():
    """次日早盘读到昨日日线 -> 保留"""
    mock_store = _make_mock_store(['2026-09-09', '2026-09-10'])
    result = get_safe_daily('ss', now_dt=datetime(2026, 9, 11, 9, 30), store=mock_store)
    assert len(result) == 2
    assert pd.to_datetime(result['dt'].iloc[-1]).date() == date(2026, 9, 10)


def test_empty_db_no_crash():
    """数据库为空 -> 返回空 DataFrame, 不崩溃"""
    mock_store = MagicMock()
    mock_store.get_main_continuous.return_value = pd.DataFrame()
    result = get_safe_daily('nonexistent', store=mock_store)
    assert result.empty

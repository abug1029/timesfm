"""
中国商品期货「交易日」语义（周末 + 法定节假日感知）。

根因:
  - 夜盘 21:00 起，交易所交易日标签常为**下一交易日**（周五夜 → 下周一）。
  - 日线幽灵 bar 既不是简单 calendar today，也不能用固定 today+3 一刀切：
      * 周五夜：必须允许下周一标签（盘中未完成）
      * 周六日：应只保留上周五及更早（丢弃未完成的周一 partial）
  - 2026-08-30: 工作日推进委托 data/holidays.py，感知法定节假日与调休工作日。
    未知年份 (2027+) 自动回退纯周末跳过（原行为），guard 删除逻辑不变。

本模块只回答:
  max_allowed_daily_label(now) → 库内允许的最大日线/1H 日期标签（含当日未完成会话）
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, time
from typing import Optional

from data.holidays import (
    is_holiday as _is_holiday,
    is_workday as _is_workday,
)


def _as_dt(now: Optional[datetime] = None) -> datetime:
    return now if now is not None else datetime.now()


def next_weekday(d: date) -> date:
    """下一个工作日（跳过周六日与法定节假日；调休上班的周末视为工作日）。"""
    x = d + timedelta(days=1)
    while not _is_workday(x):
        x += timedelta(days=1)
    return x


def prev_weekday(d: date) -> date:
    """不晚于 d 的最近工作日（同上）。"""
    x = d
    while not _is_workday(x):
        x -= timedelta(days=1)
    return x


def previous_weekday_before(d: date) -> date:
    """严格早于 d 的最近工作日。"""
    return prev_weekday(d - timedelta(days=1))


def is_night_session(now: datetime) -> bool:
    """
    是否处于商品期货夜盘时段（简化并集 21:00–02:30）。
    周末无夜盘；周一 00:00–02:30 无（周日无夜盘）。
    """
    if now.weekday() >= 5:
        return False
    t = now.time()
    if time(21, 0) <= t:
        return True
    if t < time(2, 30):
        # 周一凌晨不属于上周五夜盘的延续（已在周末断开）
        if now.weekday() == 0:
            return False
        return True
    return False


def open_trading_day_label(now: Optional[datetime] = None) -> Optional[date]:
    """
    若当前有进行中的会话，返回该会话对应的交易日标签；否则 None。

    - 日盘 ~08:50–15:30: 标签 = 当日
    - 夜盘 21:00+: 标签 = 下一交易日（周五 → 下周一）
    - 夜盘 00:00–02:30: 标签 = 当日（跨日段）
    """
    now = _as_dt(now)
    if now.weekday() >= 5:
        return None

    t = now.time()

    if time(8, 50) <= t <= time(15, 30):
        return now.date()

    if is_night_session(now):
        if t < time(2, 30):
            return now.date()
        return next_weekday(now.date())

    return None


def last_closed_trading_day(now: Optional[datetime] = None) -> date:
    """最近已完全收盘的交易日标签。"""
    now = _as_dt(now)
    open_td = open_trading_day_label(now)
    if open_td is not None:
        return previous_weekday_before(open_td)

    d, t = now.date(), now.time()
    if now.weekday() >= 5:
        return prev_weekday(d)
    if t > time(15, 30):
        return d
    # 开盘前 / 下午收盘后、夜盘前
    return previous_weekday_before(d)


def _prev_weekend_only(d: date) -> date:
    """纯周末口径的最近工作日 (不含节假日表, 用于上限保底)。"""
    x = d
    while x.weekday() >= 5:
        x -= timedelta(days=1)
    return x


def max_allowed_daily_label(now: Optional[datetime] = None) -> date:
    """
    库内允许的最大日线/1H 日期标签（含进行中交易日）。

    - 会话进行中 → open trading day（允许未完成 bar）
    - 否则 → last closed trading day（拒绝未来/未开盘标签）
    - 节假日保护 (2026-08-30): 周末时段取「节假日口径」与「纯周末口径」的 max，
      保证上限**永不低于现状** —— 即使节假日表漏掉调休工作日，
      cap 也不低于纯周末口径，不可能因表错误回退到更早而误删有效 bar。
    """
    now = _as_dt(now)
    open_td = open_trading_day_label(now)
    if open_td is not None:
        return open_td
    label = last_closed_trading_day(now)
    if now.weekday() >= 5:
        label = max(label, _prev_weekend_only(now.date()))
    return label

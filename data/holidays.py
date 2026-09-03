"""
中国法定节假日表 (静态, 官方口径)

数据来源 (国务院办公厅通知, 经 chinese-calendar 项目核对):
- 2025: 国办发明电〔2024〕21号
- 2026: 国务院通知 https://www.gov.cn/zhengce/content/202511/content_7047090.htm
- 2027+: 未发布, is_known(year)=False, 所有函数回退为纯周末逻辑 (现状行为)

安全设计 (错误方向):
  - 节假日表只用于「放宽」时效性检查和「修正」交易日标签:
    * 表中多标 (把工作日标成节假日) → 时效性更宽容, 不会拒绝新鲜数据
    * 表中漏标 (把节假日标成工作日) → 回退现状行为 (星期矩阵), 不产生新故障
  - trading_calendar 的 max_allowed_daily_label 取「周末口径」与「节假日口径」的
    max, 保证上限永不低于现状 → 幽灵K线 guard 不可能因表错误删除有效 bar

维护: 每年 11-12 月国务院发布次年安排后, 在 HOLIDAYS / ADJ_WORKDAYS 补一行。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Set, Tuple

# ── 法定节假日 (商品期货休市日, 含调休连休) ──
HOLIDAYS: Dict[int, Set[Tuple[int, int]]] = {
    2025: {
        # 元旦
        (1, 1),
        # 春节 1/28-2/4
        *[(1, 28), (1, 29), (1, 30), (1, 31), (2, 1), (2, 2), (2, 3), (2, 4)],
        # 清明 4/4-4/6
        *[(4, 4), (4, 5), (4, 6)],
        # 劳动节 5/1-5/5
        *[(5, 1), (5, 2), (5, 3), (5, 4), (5, 5)],
        # 端午 5/31-6/2
        *[(5, 31), (6, 1), (6, 2)],
        # 国庆+中秋 10/1-10/8
        *[(10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8)],
    },
    2026: {
        # 元旦 1/1-1/3
        *[(1, 1), (1, 2), (1, 3)],
        # 春节 2/15-2/23 (9天)
        *[(2, 15), (2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 21), (2, 22), (2, 23)],
        # 清明 4/4-4/6
        *[(4, 4), (4, 5), (4, 6)],
        # 劳动节 5/1-5/5
        *[(5, 1), (5, 2), (5, 3), (5, 4), (5, 5)],
        # 端午 6/19-6/21
        *[(6, 19), (6, 20), (6, 21)],
        # 中秋 9/25-9/27
        *[(9, 25), (9, 26), (9, 27)],
        # 国庆 10/1-10/7
        *[(10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7)],
    },
}

# ── 调休工作日 (周末上班, 视为交易日) ──
ADJ_WORKDAYS: Dict[int, Set[Tuple[int, int]]] = {
    2025: {
        (1, 26),   # 春节调休 (周日)
        (2, 8),    # 春节调休 (周六)
        (4, 27),   # 劳动节调休 (周日)
        (9, 28),   # 国庆调休 (周日)
        (10, 11),  # 国庆调休 (周六)
    },
    2026: {
        (1, 4),    # 元旦调休 (周日)
        (2, 14),   # 春节调休 (周六)
        (2, 28),   # 春节调休 (周六)
        (5, 9),    # 劳动节调休 (周六)
        (9, 20),   # 国庆调休 (周日)
        (10, 10),  # 国庆调休 (周六)
    },
}


def is_known(year: int) -> bool:
    """该年份是否有权威节假日表。无表年份所有函数回退纯周末逻辑。"""
    return year in HOLIDAYS


def is_holiday(d: date) -> bool:
    """法定休市日 (仅已知年份; 未知年份返回 False = 回退现状)。"""
    return d.year in HOLIDAYS and (d.month, d.day) in HOLIDAYS[d.year]


def is_workday(d: date) -> bool:
    """交易日近似 = 工作日: 非周末, 或调休上班的周末; 且非法定节假日。"""
    if is_holiday(d):
        return False
    if d.weekday() >= 5:
        return d.year in ADJ_WORKDAYS and (d.month, d.day) in ADJ_WORKDAYS[d.year]
    return True


# ── 交易日推进 (已知年份感知节假日; 未知年份回退纯周末跳过) ──

def next_trading_day(d: date) -> date:
    """严格晚于 d 的下一交易日。未知年份等价于旧 next_weekday。"""
    x = d + timedelta(days=1)
    # 未知年份: is_workday 对周末返回 False (无 ADJ_WORKDAYS) → 纯周末跳过, 与旧逻辑一致
    while not is_workday(x):
        x += timedelta(days=1)
    return x


def prev_trading_day(d: date) -> date:
    """不晚于 d 的最近交易日。未知年份等价于旧 prev_weekday。"""
    x = d
    while not is_workday(x):
        x -= timedelta(days=1)
    return x


def previous_trading_day_before(d: date) -> date:
    """严格早于 d 的最近交易日。"""
    return prev_trading_day(d - timedelta(days=1))


def count_holidays_between(date_from: date, date_to: date) -> int:
    """(date_from, date_to] 区间内的法定节假日数 (未知年份返回 0 = 不放宽)。"""
    n = 0
    d = date_from + timedelta(days=1)
    while d <= date_to:
        if is_holiday(d):
            n += 1
        d += timedelta(days=1)
    return n

"""
data/holidays.py 单元测试: 表完整性 + API 行为 + 安全回退
"""
import unittest
from datetime import date

from data.holidays import (
    HOLIDAYS, ADJ_WORKDAYS, is_known, is_holiday, is_workday,
    next_trading_day, prev_trading_day, previous_trading_day_before,
    count_holidays_between,
)


class TestTableIntegrity(unittest.TestCase):
    """表完整性: 已知年份非空, 结构正确"""

    def test_2025_2026_tables_present(self):
        self.assertIn(2025, HOLIDAYS)
        self.assertIn(2026, HOLIDAYS)
        self.assertGreaterEqual(len(HOLIDAYS[2025]), 25)
        self.assertGreaterEqual(len(HOLIDAYS[2026]), 27)
        self.assertGreaterEqual(len(ADJ_WORKDAYS[2025]), 5)
        self.assertGreaterEqual(len(ADJ_WORKDAYS[2026]), 5)

    def test_no_overlap_holiday_and_adj_workday(self):
        for year in HOLIDAYS:
            overlap = HOLIDAYS[year] & ADJ_WORKDAYS.get(year, set())
            self.assertEqual(overlap, set())


class TestUnknownYearFallback(unittest.TestCase):
    """未知年份 (2027+): 全部回退纯周末逻辑"""

    def test_is_known_false(self):
        self.assertFalse(is_known(2027))

    def test_is_holiday_always_false(self):
        self.assertFalse(is_holiday(date(2027, 1, 1)))

    def test_workday_weekend_rules_only(self):
        # 2027-01-02 周六 -> 非工作日; 2027-01-04 周一 -> 工作日
        self.assertFalse(is_workday(date(2027, 1, 2)))
        self.assertTrue(is_workday(date(2027, 1, 4)))

    def test_next_prev_fallback_equal_weekday_skip(self):
        # 未知年份, next/prev 等价于纯周末跳过
        self.assertEqual(next_trading_day(date(2027, 1, 1)), date(2027, 1, 4))  # Fri->Mon
        self.assertEqual(prev_trading_day(date(2027, 1, 2)), date(2027, 1, 1))  # Sat->Fri


class TestHolidayAPI2026(unittest.TestCase):
    """2026 年 API 行为"""

    def test_holidays(self):
        self.assertTrue(is_holiday(date(2026, 2, 17)))   # 春节
        self.assertTrue(is_holiday(date(2026, 10, 1)))   # 国庆
        self.assertFalse(is_holiday(date(2026, 3, 5)))   # 普通工作日

    def test_adj_workday(self):
        # 2026-02-14 周六春节调休上班 -> 工作日
        self.assertTrue(is_workday(date(2026, 2, 14)))
        # 2026-02-21 周六 (春节假期内) -> 非工作日
        self.assertFalse(is_workday(date(2026, 2, 21)))

    def test_spring_festival_night_session_label(self):
        # 节前周五 2/13 夜盘 -> 下一交易日应为 2/14 (调休周六) 而非跳到节后
        self.assertEqual(next_trading_day(date(2026, 2, 13)), date(2026, 2, 14))
        # 节后: 2/23 (假) -> 2/24 (周二, 节后首日)
        self.assertEqual(next_trading_day(date(2026, 2, 23)), date(2026, 2, 24))

    def test_national_day_stretch(self):
        self.assertEqual(next_trading_day(date(2026, 9, 30)), date(2026, 10, 8))
        self.assertEqual(prev_trading_day(date(2026, 10, 7)), date(2026, 9, 30))

    def test_count_holidays_between(self):
        # 国庆 (9/30, 10/8] 内 7 天节假日
        self.assertEqual(count_holidays_between(date(2026, 9, 30), date(2026, 10, 8)), 7)
        # 未知年份返回 0
        self.assertEqual(count_holidays_between(date(2027, 9, 30), date(2027, 10, 8)), 0)


if __name__ == "__main__":
    unittest.main()

"""
测试日历系统

验证 DOC-WORLD-007
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from world.calendar import (
    Season,
    Month,
    MONTHS,
    FESTIVALS,
    DAYS_PER_MONTH,
    MONTHS_PER_YEAR,
    DAYS_PER_YEAR,
    game_minutes_to_date,
    format_game_date,
    get_festival_on_date,
)


class TestCalendar:
    """日历系统测试"""

    def test_month_count(self):
        """测试月份数量"""
        assert len(MONTHS) == 12
        assert MONTHS_PER_YEAR == 12

    def test_days_per_month(self):
        """测试每月天数"""
        assert DAYS_PER_MONTH == 30
        for month_info in MONTHS.values():
            assert month_info.days == 30

    def test_days_per_year(self):
        """测试全年天数"""
        assert DAYS_PER_YEAR == 360

    def test_month_numbers(self):
        """测试月份编号连续"""
        month_numbers = [info.month_number for info in MONTHS.values()]
        assert sorted(month_numbers) == list(range(1, 13))

    def test_seasons_distribution(self):
        """测试季节分布（每季度 3 个月）"""
        seasons_count = {}
        for month_info in MONTHS.values():
            season = month_info.season
            seasons_count[season] = seasons_count.get(season, 0) + 1

        assert seasons_count[Season.SPRING] == 3
        assert seasons_count[Season.SUMMER] == 3
        assert seasons_count[Season.AUTUMN] == 3
        assert seasons_count[Season.WINTER] == 3


class TestGameDateConversion:
    """游戏日期转换测试"""

    def test_game_minutes_to_date_start(self):
        """测试世界开始时间（0 分钟）"""
        year, month, day, hour, minute = game_minutes_to_date(0)
        assert year == 0
        assert month == 1
        assert day == 1
        assert hour == 0
        assert minute == 0

    def test_game_minutes_to_date_one_day(self):
        """测试一天后（1440 分钟）"""
        year, month, day, hour, minute = game_minutes_to_date(1440)
        assert year == 0
        assert month == 1
        assert day == 2
        assert hour == 0
        assert minute == 0

    def test_game_minutes_to_date_one_month(self):
        """测试一个月后（30 天 = 43200 分钟）"""
        year, month, day, hour, minute = game_minutes_to_date(43200)
        assert year == 0
        assert month == 2
        assert day == 1
        assert hour == 0
        assert minute == 0

    def test_game_minutes_to_date_one_year(self):
        """测试一年后（360 天 = 518400 分钟）"""
        year, month, day, hour, minute = game_minutes_to_date(518400)
        assert year == 1
        assert month == 1
        assert day == 1
        assert hour == 0
        assert minute == 0

    def test_format_game_date(self):
        """测试游戏日期格式化"""
        # 第 0 年 1 月 1 日 00:00
        assert "第0年1月1日 00:00" in format_game_date(0)

        # 第 0 年 1 月 2 日 12:30
        assert "第0年1月2日 12:30" in format_game_date(1440 + 750)


class TestFestivals:
    """节日系统测试"""

    def test_festival_count(self):
        """测试节日数量"""
        assert len(FESTIVALS) >= 3

    def test_festival_info(self):
        """测试节日信息完整性"""
        for festival in FESTIVALS:
            assert len(festival.festival_id) > 0
            assert len(festival.display_name_zh) > 0
            assert len(festival.display_name_en) > 0
            assert festival.month in MONTHS
            assert 1 <= festival.day <= 30
            assert len(festival.description) > 0
            assert len(festival.activities) > 0

    def test_get_festival_on_date(self):
        """测试获取指定日期的节日"""
        # 春醒节：初绽月 1 日
        festival = get_festival_on_date(Month.FIRST_BLOOM, 1)
        assert festival is not None
        assert festival.festival_id == "spring_awakening"

        # 无节日的日期
        no_festival = get_festival_on_date(Month.FIRST_BLOOM, 15)
        assert no_festival is None

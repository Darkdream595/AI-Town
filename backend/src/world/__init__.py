"""
World 世界设定模块

提供世界常量、种族、职业、日历等定义
"""

from .constants import (
    RegionId,
    RegionInfo,
    REGIONS,
    Race,
    RaceInfo,
    RACES,
    Profession,
    ProfessionInfo,
    PROFESSIONS,
    COPPER_PER_SILVER,
    copper_to_silver_display,
)

from .calendar import (
    Season,
    Month,
    MonthInfo,
    MONTHS,
    Festival,
    FESTIVALS,
    DAYS_PER_MONTH,
    MONTHS_PER_YEAR,
    DAYS_PER_YEAR,
    game_minutes_to_date,
    format_game_date,
    get_festival_on_date,
)

from .content_boundaries import (
    ContentSeverity,
    is_content_appropriate,
    validate_content_boundaries,
)

__all__ = [
    # 区域
    "RegionId",
    "RegionInfo",
    "REGIONS",
    # 种族
    "Race",
    "RaceInfo",
    "RACES",
    # 职业
    "Profession",
    "ProfessionInfo",
    "PROFESSIONS",
    # 货币
    "COPPER_PER_SILVER",
    "copper_to_silver_display",
    # 日历
    "Season",
    "Month",
    "MonthInfo",
    "MONTHS",
    "Festival",
    "FESTIVALS",
    "DAYS_PER_MONTH",
    "MONTHS_PER_YEAR",
    "DAYS_PER_YEAR",
    "game_minutes_to_date",
    "format_game_date",
    "get_festival_on_date",
    # 内容边界
    "ContentSeverity",
    "is_content_appropriate",
    "validate_content_boundaries",
]

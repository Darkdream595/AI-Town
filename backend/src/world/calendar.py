"""
日历和时间系统

符合 DOC-WORLD-007 规范：
- 游戏日历
- 季节系统
- 节日定义
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


# ==================== 日历系统 ====================

class Season(str, Enum):
    """季节"""
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


class Month(str, Enum):
    """月份（12个月）"""
    FIRST_BLOOM = "first_bloom"          # 初绽月（春）
    RAIN_SONG = "rain_song"              # 雨歌月（春）
    GREEN_GROWTH = "green_growth"        # 翠长月（春）
    SUN_PEAK = "sun_peak"                # 烈日月（夏）
    HARVEST_GOLD = "harvest_gold"        # 金收月（夏）
    AMBER_LIGHT = "amber_light"          # 琥光月（夏）
    LEAF_FALL = "leaf_fall"              # 落叶月（秋）
    MIST_VEIL = "mist_veil"              # 雾纱月（秋）
    FROST_EDGE = "frost_edge"            # 霜锋月（秋）
    SNOW_SILENCE = "snow_silence"        # 雪寂月（冬）
    ICE_MIRROR = "ice_mirror"            # 冰镜月（冬）
    STAR_COLD = "star_cold"              # 星寒月（冬）


@dataclass(frozen=True)
class MonthInfo:
    """月份信息"""
    month: Month
    display_name_zh: str
    display_name_en: str
    season: Season
    month_number: int  # 1-12
    days: int  # 每月天数


# 游戏日历：每月 30 天，全年 360 天
MONTHS = {
    Month.FIRST_BLOOM: MonthInfo(
        month=Month.FIRST_BLOOM,
        display_name_zh="初绽月",
        display_name_en="First Bloom",
        season=Season.SPRING,
        month_number=1,
        days=30
    ),
    Month.RAIN_SONG: MonthInfo(
        month=Month.RAIN_SONG,
        display_name_zh="雨歌月",
        display_name_en="Rain Song",
        season=Season.SPRING,
        month_number=2,
        days=30
    ),
    Month.GREEN_GROWTH: MonthInfo(
        month=Month.GREEN_GROWTH,
        display_name_zh="翠长月",
        display_name_en="Green Growth",
        season=Season.SPRING,
        month_number=3,
        days=30
    ),
    Month.SUN_PEAK: MonthInfo(
        month=Month.SUN_PEAK,
        display_name_zh="烈日月",
        display_name_en="Sun Peak",
        season=Season.SUMMER,
        month_number=4,
        days=30
    ),
    Month.HARVEST_GOLD: MonthInfo(
        month=Month.HARVEST_GOLD,
        display_name_zh="金收月",
        display_name_en="Harvest Gold",
        season=Season.SUMMER,
        month_number=5,
        days=30
    ),
    Month.AMBER_LIGHT: MonthInfo(
        month=Month.AMBER_LIGHT,
        display_name_zh="琥光月",
        display_name_en="Amber Light",
        season=Season.SUMMER,
        month_number=6,
        days=30
    ),
    Month.LEAF_FALL: MonthInfo(
        month=Month.LEAF_FALL,
        display_name_zh="落叶月",
        display_name_en="Leaf Fall",
        season=Season.AUTUMN,
        month_number=7,
        days=30
    ),
    Month.MIST_VEIL: MonthInfo(
        month=Month.MIST_VEIL,
        display_name_zh="雾纱月",
        display_name_en="Mist Veil",
        season=Season.AUTUMN,
        month_number=8,
        days=30
    ),
    Month.FROST_EDGE: MonthInfo(
        month=Month.FROST_EDGE,
        display_name_zh="霜锋月",
        display_name_en="Frost Edge",
        season=Season.AUTUMN,
        month_number=9,
        days=30
    ),
    Month.SNOW_SILENCE: MonthInfo(
        month=Month.SNOW_SILENCE,
        display_name_zh="雪寂月",
        display_name_en="Snow Silence",
        season=Season.WINTER,
        month_number=10,
        days=30
    ),
    Month.ICE_MIRROR: MonthInfo(
        month=Month.ICE_MIRROR,
        display_name_zh="冰镜月",
        display_name_en="Ice Mirror",
        season=Season.WINTER,
        month_number=11,
        days=30
    ),
    Month.STAR_COLD: MonthInfo(
        month=Month.STAR_COLD,
        display_name_zh="星寒月",
        display_name_en="Star Cold",
        season=Season.WINTER,
        month_number=12,
        days=30
    ),
}

# 日历常量
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 360 天


def game_minutes_to_date(game_minutes: int) -> tuple[int, int, int, int, int]:
    """
    游戏分钟转换为游戏日期

    Args:
        game_minutes: 从世界创建起算的游戏分钟数

    Returns:
        tuple: (年, 月, 日, 时, 分)
    """
    total_days = game_minutes // (60 * 24)
    remaining_minutes = game_minutes % (60 * 24)

    year = total_days // DAYS_PER_YEAR
    day_of_year = total_days % DAYS_PER_YEAR
    month = day_of_year // DAYS_PER_MONTH + 1  # 1-12
    day = day_of_year % DAYS_PER_MONTH + 1     # 1-30

    hour = remaining_minutes // 60
    minute = remaining_minutes % 60

    return (year, month, day, hour, minute)


def format_game_date(game_minutes: int) -> str:
    """
    格式化游戏日期为可读字符串

    Args:
        game_minutes: 游戏分钟数

    Returns:
        str: 格式化的日期字符串
    """
    year, month, day, hour, minute = game_minutes_to_date(game_minutes)
    return f"第{year}年{month}月{day}日 {hour:02d}:{minute:02d}"


# ==================== 节日定义 ====================

@dataclass(frozen=True)
class Festival:
    """节日定义"""
    festival_id: str
    display_name_zh: str
    display_name_en: str
    month: Month
    day: int  # 1-30
    description: str
    activities: List[str]


FESTIVALS = [
    Festival(
        festival_id="spring_awakening",
        display_name_zh="春醒节",
        display_name_en="Spring Awakening",
        month=Month.FIRST_BLOOM,
        day=1,
        description="庆祝春天到来和万物复苏",
        activities=["种植仪式", "花冠编织", "集市贸易"]
    ),
    Festival(
        festival_id="harvest_celebration",
        display_name_zh="丰收庆典",
        display_name_en="Harvest Celebration",
        month=Month.HARVEST_GOLD,
        day=15,
        description="庆祝丰收，感谢自然的馈赠",
        activities=["收割仪式", "盛宴", "感恩祈祷"]
    ),
    Festival(
        festival_id="winter_solstice",
        display_name_zh="冬至祭",
        display_name_en="Winter Solstice",
        month=Month.SNOW_SILENCE,
        day=1,
        description="迎接最长的黑夜，祈求光明回归",
        activities=["篝火晚会", "故事分享", "守夜"]
    ),
]


def get_festival_on_date(month: Month, day: int) -> Optional[Festival]:
    """
    获取指定日期的节日

    Args:
        month: 月份
        day: 日期（1-30）

    Returns:
        Optional[Festival]: 节日信息，如果当天无节日则返回 None
    """
    for festival in FESTIVALS:
        if festival.month == month and festival.day == day:
            return festival
    return None

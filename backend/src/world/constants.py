"""
世界常量定义

符合 DOC-WORLD-001 到 DOC-WORLD-012 规范：
- 三个区域：王冠溪镇、暮语森林、银烬矿洞
- 种族、文化、职业定义
- 日历和节日系统
"""

from enum import Enum
from dataclasses import dataclass
from typing import List


# ==================== 区域定义 ====================

class RegionId(str, Enum):
    """区域标识符"""
    CROWN_CREEK_TOWN = "crown_creek_town"
    TWILIGHT_WHISPER_FOREST = "twilight_whisper_forest"
    SILVER_ASH_MINE = "silver_ash_mine"


@dataclass(frozen=True)
class RegionInfo:
    """区域信息"""
    region_id: RegionId
    display_name_zh: str
    display_name_en: str
    description: str
    is_outdoor: bool
    is_safe: bool


# 三个主要区域
REGIONS = {
    RegionId.CROWN_CREEK_TOWN: RegionInfo(
        region_id=RegionId.CROWN_CREEK_TOWN,
        display_name_zh="王冠溪镇",
        display_name_en="Crown Creek Town",
        description="小镇中心，居民主要居住和活动区域",
        is_outdoor=True,
        is_safe=True
    ),
    RegionId.TWILIGHT_WHISPER_FOREST: RegionInfo(
        region_id=RegionId.TWILIGHT_WHISPER_FOREST,
        display_name_zh="暮语森林",
        display_name_en="Twilight Whisper Forest",
        description="神秘森林，蕴含魔法力量和野生生物",
        is_outdoor=True,
        is_safe=False
    ),
    RegionId.SILVER_ASH_MINE: RegionInfo(
        region_id=RegionId.SILVER_ASH_MINE,
        display_name_zh="银烬矿洞",
        display_name_en="Silver Ash Mine",
        description="地下矿洞，可开采珍贵矿物，但有危险生物",
        is_outdoor=False,
        is_safe=False
    ),
}


# ==================== 种族定义 ====================

class Race(str, Enum):
    """种族枚举"""
    HUMAN = "human"
    ELF = "elf"
    DWARF = "dwarf"
    HALFLING = "halfling"


@dataclass(frozen=True)
class RaceInfo:
    """种族信息"""
    race: Race
    display_name_zh: str
    display_name_en: str
    description: str
    typical_professions: List[str]
    base_language: str


RACES = {
    Race.HUMAN: RaceInfo(
        race=Race.HUMAN,
        display_name_zh="人类",
        display_name_en="Human",
        description="适应力强，平衡发展的种族",
        typical_professions=["农夫", "商人", "工匠", "骑士"],
        base_language="crown_common"
    ),
    Race.ELF: RaceInfo(
        race=Race.ELF,
        display_name_zh="精灵",
        display_name_en="Elf",
        description="与自然和魔法亲近的长寿种族",
        typical_professions=["魔法师", "弓箭手", "药剂师", "吟游诗人"],
        base_language="crown_common"
    ),
    Race.DWARF: RaceInfo(
        race=Race.DWARF,
        display_name_zh="矮人",
        display_name_en="Dwarf",
        description="擅长工艺和战斗的坚韧种族",
        typical_professions=["铁匠", "矿工", "战士", "工程师"],
        base_language="crown_common"
    ),
    Race.HALFLING: RaceInfo(
        race=Race.HALFLING,
        display_name_zh="半身人",
        display_name_en="Halfling",
        description="小巧灵活，擅长社交和贸易",
        typical_professions=["厨师", "商人", "盗贼", "旅店老板"],
        base_language="crown_common"
    ),
}


# ==================== 职业定义 ====================

class Profession(str, Enum):
    """职业枚举"""
    FARMER = "farmer"
    MERCHANT = "merchant"
    BLACKSMITH = "blacksmith"
    MINER = "miner"
    MAGE = "mage"
    PRIEST = "priest"
    GUARD = "guard"
    INNKEEPER = "innkeeper"
    ALCHEMIST = "alchemist"
    HUNTER = "hunter"


@dataclass(frozen=True)
class ProfessionInfo:
    """职业信息"""
    profession: Profession
    display_name_zh: str
    display_name_en: str
    description: str
    workplace_types: List[str]
    base_income_per_day_copper: int  # 铜羽/天


PROFESSIONS = {
    Profession.FARMER: ProfessionInfo(
        profession=Profession.FARMER,
        display_name_zh="农夫",
        display_name_en="Farmer",
        description="耕种土地，生产食物",
        workplace_types=["farm", "field"],
        base_income_per_day_copper=50
    ),
    Profession.MERCHANT: ProfessionInfo(
        profession=Profession.MERCHANT,
        display_name_zh="商人",
        display_name_en="Merchant",
        description="买卖商品，促进贸易",
        workplace_types=["shop", "market"],
        base_income_per_day_copper=100
    ),
    Profession.BLACKSMITH: ProfessionInfo(
        profession=Profession.BLACKSMITH,
        display_name_zh="铁匠",
        display_name_en="Blacksmith",
        description="锻造武器和工具",
        workplace_types=["smithy"],
        base_income_per_day_copper=80
    ),
    Profession.MINER: ProfessionInfo(
        profession=Profession.MINER,
        display_name_zh="矿工",
        display_name_en="Miner",
        description="在矿洞中开采矿石",
        workplace_types=["mine"],
        base_income_per_day_copper=70
    ),
    Profession.MAGE: ProfessionInfo(
        profession=Profession.MAGE,
        display_name_zh="魔法师",
        display_name_en="Mage",
        description="研究和施展魔法",
        workplace_types=["tower", "academy"],
        base_income_per_day_copper=120
    ),
    Profession.PRIEST: ProfessionInfo(
        profession=Profession.PRIEST,
        display_name_zh="牧师",
        display_name_en="Priest",
        description="侍奉神明，治疗伤病",
        workplace_types=["temple", "shrine"],
        base_income_per_day_copper=60
    ),
    Profession.GUARD: ProfessionInfo(
        profession=Profession.GUARD,
        display_name_zh="守卫",
        display_name_en="Guard",
        description="维护小镇治安",
        workplace_types=["guardhouse", "town_square"],
        base_income_per_day_copper=90
    ),
    Profession.INNKEEPER: ProfessionInfo(
        profession=Profession.INNKEEPER,
        display_name_zh="旅店老板",
        display_name_en="Innkeeper",
        description="经营旅店，招待客人",
        workplace_types=["inn", "tavern"],
        base_income_per_day_copper=85
    ),
    Profession.ALCHEMIST: ProfessionInfo(
        profession=Profession.ALCHEMIST,
        display_name_zh="炼金术士",
        display_name_en="Alchemist",
        description="调制药剂和魔法物品",
        workplace_types=["alchemy_shop"],
        base_income_per_day_copper=110
    ),
    Profession.HUNTER: ProfessionInfo(
        profession=Profession.HUNTER,
        display_name_zh="猎人",
        display_name_en="Hunter",
        description="狩猎野生动物，采集资源",
        workplace_types=["forest", "wilderness"],
        base_income_per_day_copper=65
    ),
}


# ==================== 货币单位 ====================

# RULE-FOUNDATION-043: 货币单位
COPPER_PER_SILVER = 100  # 1 银冠 = 100 铜羽


def copper_to_silver_display(copper: int) -> str:
    """
    铜羽转换为显示格式

    Args:
        copper: 铜羽数量

    Returns:
        str: 显示格式（如 "1银冠50铜羽"）
    """
    silver = copper // COPPER_PER_SILVER
    remaining_copper = copper % COPPER_PER_SILVER

    if silver > 0 and remaining_copper > 0:
        return f"{silver}银冠{remaining_copper}铜羽"
    elif silver > 0:
        return f"{silver}银冠"
    else:
        return f"{copper}铜羽"

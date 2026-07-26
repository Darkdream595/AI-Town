"""
测试世界常量

验证 DOC-WORLD-001 到 DOC-WORLD-006
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from world.constants import (
    RegionId,
    REGIONS,
    Race,
    RACES,
    Profession,
    PROFESSIONS,
    COPPER_PER_SILVER,
    copper_to_silver_display,
)


class TestRegions:
    """区域定义测试"""

    def test_region_count(self):
        """测试区域数量"""
        assert len(REGIONS) == 3

    def test_region_ids(self):
        """测试区域 ID"""
        assert RegionId.CROWN_CREEK_TOWN in REGIONS
        assert RegionId.TWILIGHT_WHISPER_FOREST in REGIONS
        assert RegionId.SILVER_ASH_MINE in REGIONS

    def test_region_info(self):
        """测试区域信息完整性"""
        for region_id, region_info in REGIONS.items():
            assert region_info.region_id == region_id
            assert len(region_info.display_name_zh) > 0
            assert len(region_info.display_name_en) > 0
            assert len(region_info.description) > 0
            assert isinstance(region_info.is_outdoor, bool)
            assert isinstance(region_info.is_safe, bool)

    def test_safe_regions(self):
        """测试安全区域"""
        town = REGIONS[RegionId.CROWN_CREEK_TOWN]
        assert town.is_safe is True

        forest = REGIONS[RegionId.TWILIGHT_WHISPER_FOREST]
        assert forest.is_safe is False

        mine = REGIONS[RegionId.SILVER_ASH_MINE]
        assert mine.is_safe is False


class TestRaces:
    """种族定义测试"""

    def test_race_count(self):
        """测试种族数量"""
        assert len(RACES) == 4

    def test_race_ids(self):
        """测试种族 ID"""
        assert Race.HUMAN in RACES
        assert Race.ELF in RACES
        assert Race.DWARF in RACES
        assert Race.HALFLING in RACES

    def test_race_info(self):
        """测试种族信息完整性"""
        for race, race_info in RACES.items():
            assert race_info.race == race
            assert len(race_info.display_name_zh) > 0
            assert len(race_info.display_name_en) > 0
            assert len(race_info.description) > 0
            assert len(race_info.typical_professions) > 0
            assert race_info.base_language == "crown_common"


class TestProfessions:
    """职业定义测试"""

    def test_profession_count(self):
        """测试职业数量"""
        assert len(PROFESSIONS) >= 10

    def test_profession_info(self):
        """测试职业信息完整性"""
        for profession, prof_info in PROFESSIONS.items():
            assert prof_info.profession == profession
            assert len(prof_info.display_name_zh) > 0
            assert len(prof_info.display_name_en) > 0
            assert len(prof_info.description) > 0
            assert len(prof_info.workplace_types) > 0
            assert prof_info.base_income_per_day_copper > 0

    def test_profession_income_range(self):
        """测试职业收入范围合理"""
        for prof_info in PROFESSIONS.values():
            # 每日收入应该在 50-200 铜羽之间
            assert 50 <= prof_info.base_income_per_day_copper <= 200


class TestCurrency:
    """货币系统测试"""

    def test_currency_conversion(self):
        """测试货币换算"""
        assert COPPER_PER_SILVER == 100

    def test_copper_to_silver_display(self):
        """测试货币显示格式"""
        assert copper_to_silver_display(0) == "0铜羽"
        assert copper_to_silver_display(50) == "50铜羽"
        assert copper_to_silver_display(100) == "1银冠"
        assert copper_to_silver_display(150) == "1银冠50铜羽"
        assert copper_to_silver_display(250) == "2银冠50铜羽"
        assert copper_to_silver_display(1000) == "10银冠"

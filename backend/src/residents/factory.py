"""
居民工厂 - 创建初始居民

基于现有 resident_model，为10个角色创建初始居民数据
"""

from typing import Dict
from ..foundation import generate_ulid, WorldCoordinate
from ..world import Race, Profession
from .resident_model import (
    Resident,
    Gender,
    Age,
    Appearance,
    Personality,
    Values,
    SkillType,
    Skill,
)


class ResidentFactory:
    """居民工厂类"""

    @staticmethod
    def create_human_farmer() -> Resident:
        """创建人类农夫"""
        resident = Resident(
            name="托马斯",
            race=Race.HUMAN,
            gender=Gender.MALE,
            age=Age(years=35, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="human_farmer",
                skin_tone="tan",
                hair_color="brown",
                eye_color="brown",
                height_cm=175,
                build="sturdy"
            ),
            personality=Personality(
                openness=45,
                conscientiousness=75,
                extraversion=55,
                agreeableness=70,
                neuroticism=35
            ),
            values=Values(
                tradition=70,
                community=80,
                wealth=45,
                power=30,
                knowledge=40
            ),
            profession=Profession.FARMER,
            current_position=WorldCoordinate(x_wu=200, y_wu=300),
            money_copper=150,
        )

        # 设置技能
        resident.skills[SkillType.FARMING] = Skill(
            skill_type=SkillType.FARMING,
            level=5,
            experience=200
        )

        return resident

    @staticmethod
    def create_elf_mage() -> Resident:
        """创建精灵法师"""
        resident = Resident(
            name="艾莉娅",
            race=Race.ELF,
            gender=Gender.FEMALE,
            age=Age(years=120, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="elf_mage",
                skin_tone="fair",
                hair_color="silver",
                eye_color="blue",
                height_cm=165,
                build="slim"
            ),
            personality=Personality(
                openness=85,
                conscientiousness=65,
                extraversion=45,
                agreeableness=60,
                neuroticism=50
            ),
            values=Values(
                tradition=60,
                community=50,
                wealth=40,
                power=55,
                knowledge=90
            ),
            profession=Profession.MAGE,
            current_position=WorldCoordinate(x_wu=350, y_wu=300),
            money_copper=200,
        )

        resident.skills[SkillType.MAGIC] = Skill(
            skill_type=SkillType.MAGIC,
            level=7,
            experience=450
        )

        return resident

    @staticmethod
    def create_dwarf_blacksmith() -> Resident:
        """创建矮人铁匠"""
        resident = Resident(
            name="格罗恩",
            race=Race.DWARF,
            gender=Gender.MALE,
            age=Age(years=80, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="dwarf_blacksmith",
                skin_tone="tan",
                hair_color="red",
                eye_color="brown",
                height_cm=140,
                build="sturdy"
            ),
            personality=Personality(
                openness=40,
                conscientiousness=90,
                extraversion=50,
                agreeableness=55,
                neuroticism=30
            ),
            values=Values(
                tradition=85,
                community=65,
                wealth=60,
                power=45,
                knowledge=55
            ),
            profession=Profession.BLACKSMITH,
            current_position=WorldCoordinate(x_wu=500, y_wu=300),
            money_copper=250,
        )

        resident.skills[SkillType.BLACKSMITHING] = Skill(
            skill_type=SkillType.BLACKSMITHING,
            level=8,
            experience=600
        )

        return resident

    @staticmethod
    def create_halfling_merchant() -> Resident:
        """创建半身人商人"""
        resident = Resident(
            name="菲利普",
            race=Race.HALFLING,
            gender=Gender.MALE,
            age=Age(years=45, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="halfling_merchant",
                skin_tone="fair",
                hair_color="blonde",
                eye_color="green",
                height_cm=105,
                build="average"
            ),
            personality=Personality(
                openness=70,
                conscientiousness=60,
                extraversion=80,
                agreeableness=65,
                neuroticism=40
            ),
            values=Values(
                tradition=50,
                community=60,
                wealth=85,
                power=50,
                knowledge=60
            ),
            profession=Profession.MERCHANT,
            current_position=WorldCoordinate(x_wu=650, y_wu=300),
            money_copper=500,
        )

        resident.skills[SkillType.TRADING] = Skill(
            skill_type=SkillType.TRADING,
            level=6,
            experience=300
        )
        resident.skills[SkillType.SOCIAL] = Skill(
            skill_type=SkillType.SOCIAL,
            level=5,
            experience=200
        )

        return resident

    @staticmethod
    def create_human_guard() -> Resident:
        """创建人类守卫"""
        resident = Resident(
            name="艾登",
            race=Race.HUMAN,
            gender=Gender.MALE,
            age=Age(years=30, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="human_guard",
                skin_tone="tan",
                hair_color="black",
                eye_color="brown",
                height_cm=180,
                build="athletic"
            ),
            personality=Personality(
                openness=50,
                conscientiousness=80,
                extraversion=60,
                agreeableness=60,
                neuroticism=35
            ),
            values=Values(
                tradition=70,
                community=75,
                wealth=50,
                power=65,
                knowledge=45
            ),
            profession=Profession.GUARD,
            current_position=WorldCoordinate(x_wu=200, y_wu=450),
            money_copper=120,
        )

        resident.skills[SkillType.COMBAT] = Skill(
            skill_type=SkillType.COMBAT,
            level=6,
            experience=350
        )

        return resident

    @staticmethod
    def create_human_priest() -> Resident:
        """创建人类牧师"""
        resident = Resident(
            name="索菲亚",
            race=Race.HUMAN,
            gender=Gender.FEMALE,
            age=Age(years=40, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="human_priest",
                skin_tone="fair",
                hair_color="brown",
                eye_color="blue",
                height_cm=168,
                build="slim"
            ),
            personality=Personality(
                openness=60,
                conscientiousness=75,
                extraversion=55,
                agreeableness=85,
                neuroticism=40
            ),
            values=Values(
                tradition=80,
                community=90,
                wealth=30,
                power=40,
                knowledge=70
            ),
            profession=Profession.PRIEST,
            current_position=WorldCoordinate(x_wu=350, y_wu=450),
            money_copper=100,
        )

        resident.skills[SkillType.MAGIC] = Skill(
            skill_type=SkillType.MAGIC,
            level=5,
            experience=250
        )
        resident.skills[SkillType.SOCIAL] = Skill(
            skill_type=SkillType.SOCIAL,
            level=6,
            experience=300
        )

        return resident

    @staticmethod
    def create_human_innkeeper() -> Resident:
        """创建人类旅店老板"""
        resident = Resident(
            name="威廉",
            race=Race.HUMAN,
            gender=Gender.MALE,
            age=Age(years=50, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="human_innkeeper",
                skin_tone="fair",
                hair_color="grey",
                eye_color="brown",
                height_cm=172,
                build="sturdy"
            ),
            personality=Personality(
                openness=55,
                conscientiousness=70,
                extraversion=75,
                agreeableness=80,
                neuroticism=35
            ),
            values=Values(
                tradition=65,
                community=80,
                wealth=65,
                power=40,
                knowledge=50
            ),
            profession=Profession.INNKEEPER,
            current_position=WorldCoordinate(x_wu=500, y_wu=450),
            money_copper=300,
        )

        resident.skills[SkillType.COOKING] = Skill(
            skill_type=SkillType.COOKING,
            level=6,
            experience=320
        )
        resident.skills[SkillType.SOCIAL] = Skill(
            skill_type=SkillType.SOCIAL,
            level=7,
            experience=400
        )

        return resident

    @staticmethod
    def create_elf_alchemist() -> Resident:
        """创建精灵炼金术士"""
        resident = Resident(
            name="瑟兰迪尔",
            race=Race.ELF,
            gender=Gender.FEMALE,
            age=Age(years=150, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="elf_alchemist",
                skin_tone="fair",
                hair_color="blonde",
                eye_color="green",
                height_cm=170,
                build="slim"
            ),
            personality=Personality(
                openness=90,
                conscientiousness=70,
                extraversion=40,
                agreeableness=55,
                neuroticism=45
            ),
            values=Values(
                tradition=50,
                community=55,
                wealth=50,
                power=45,
                knowledge=95
            ),
            profession=Profession.ALCHEMIST,
            current_position=WorldCoordinate(x_wu=650, y_wu=450),
            money_copper=180,
        )

        resident.skills[SkillType.ALCHEMY] = Skill(
            skill_type=SkillType.ALCHEMY,
            level=7,
            experience=450
        )
        resident.skills[SkillType.CRAFTING] = Skill(
            skill_type=SkillType.CRAFTING,
            level=5,
            experience=200
        )

        return resident

    @staticmethod
    def create_human_hunter() -> Resident:
        """创建人类猎人"""
        resident = Resident(
            name="奥斯卡",
            race=Race.HUMAN,
            gender=Gender.MALE,
            age=Age(years=28, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="human_hunter",
                skin_tone="tan",
                hair_color="brown",
                eye_color="green",
                height_cm=178,
                build="athletic"
            ),
            personality=Personality(
                openness=65,
                conscientiousness=60,
                extraversion=50,
                agreeableness=55,
                neuroticism=40
            ),
            values=Values(
                tradition=60,
                community=50,
                wealth=55,
                power=50,
                knowledge=55
            ),
            profession=Profession.HUNTER,
            current_position=WorldCoordinate(x_wu=200, y_wu=600),
            money_copper=130,
        )

        resident.skills[SkillType.COMBAT] = Skill(
            skill_type=SkillType.COMBAT,
            level=5,
            experience=250
        )
        resident.skills[SkillType.CRAFTING] = Skill(
            skill_type=SkillType.CRAFTING,
            level=4,
            experience=150
        )

        return resident

    @staticmethod
    def create_dwarf_miner() -> Resident:
        """创建矮人矿工"""
        resident = Resident(
            name="巴林",
            race=Race.DWARF,
            gender=Gender.MALE,
            age=Age(years=70, life_stage="adult", birth_game_time=0),
            appearance=Appearance(
                sprite_id="dwarf_miner",
                skin_tone="tan",
                hair_color="black",
                eye_color="brown",
                height_cm=135,
                build="sturdy"
            ),
            personality=Personality(
                openness=45,
                conscientiousness=85,
                extraversion=55,
                agreeableness=60,
                neuroticism=35
            ),
            values=Values(
                tradition=80,
                community=70,
                wealth=70,
                power=45,
                knowledge=50
            ),
            profession=Profession.MINER,
            current_position=WorldCoordinate(x_wu=350, y_wu=600),
            money_copper=140,
        )

        resident.skills[SkillType.MINING] = Skill(
            skill_type=SkillType.MINING,
            level=7,
            experience=500
        )

        return resident

    @staticmethod
    def create_all_initial_residents() -> Dict[str, Resident]:
        """创建所有初始居民"""
        residents = {
            "human_farmer": ResidentFactory.create_human_farmer(),
            "elf_mage": ResidentFactory.create_elf_mage(),
            "dwarf_blacksmith": ResidentFactory.create_dwarf_blacksmith(),
            "halfling_merchant": ResidentFactory.create_halfling_merchant(),
            "human_guard": ResidentFactory.create_human_guard(),
            "human_priest": ResidentFactory.create_human_priest(),
            "human_innkeeper": ResidentFactory.create_human_innkeeper(),
            "elf_alchemist": ResidentFactory.create_elf_alchemist(),
            "human_hunter": ResidentFactory.create_human_hunter(),
            "dwarf_miner": ResidentFactory.create_dwarf_miner(),
        }
        return residents

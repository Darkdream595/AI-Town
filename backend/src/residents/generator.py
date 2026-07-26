"""
Resident 生成器

用于生成具有合理属性和多样性的居民
"""

import random
from typing import Optional
from residents import Resident, Gender, Age, Appearance, Personality, Values, SkillType
from world import Race, Profession, RACES, PROFESSIONS
from foundation import WorldCoordinate


# 姓名库（中文姓名）
FIRST_NAMES_MALE = [
    "明轩", "子涵", "宇轩", "浩然", "俊杰", "天佑", "文昊", "泽宇", "煜祺", "智渊"
]

FIRST_NAMES_FEMALE = [
    "雨婷", "可馨", "梦琪", "雅静", "诗涵", "欣怡", "若雪", "紫萱", "芷若", "语嫣"
]

FAMILY_NAMES = [
    "李", "王", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "高"
]


# 外观特征
SKIN_TONES = ["fair", "tan", "olive", "dark", "pale"]
HAIR_COLORS = ["black", "brown", "blonde", "red", "gray", "white", "silver"]
EYE_COLORS = ["brown", "blue", "green", "hazel", "gray", "amber"]
BUILDS = ["slim", "average", "sturdy", "athletic", "stocky"]


class ResidentGenerator:
    """居民生成器"""

    def __init__(self, seed: Optional[int] = None):
        """
        初始化生成器

        Args:
            seed: 随机种子（用于可复现生成）
        """
        if seed is not None:
            random.seed(seed)

    def generate(
        self,
        race: Optional[Race] = None,
        profession: Optional[Profession] = None,
        gender: Optional[Gender] = None,
        age_years: Optional[int] = None,
    ) -> Resident:
        """
        生成一个居民

        Args:
            race: 指定种族（None = 随机）
            profession: 指定职业（None = 随机）
            gender: 指定性别（None = 随机）
            age_years: 指定年龄（None = 随机）

        Returns:
            Resident: 生成的居民
        """
        # 种族
        if race is None:
            race = random.choice(list(Race))

        # 性别
        if gender is None:
            gender = random.choice([Gender.MALE, Gender.FEMALE])

        # 年龄
        if age_years is None:
            age_years = random.randint(18, 60)

        life_stage = self._get_life_stage(age_years)

        # 姓名
        name = self._generate_name(gender, race)

        # 外观
        appearance = self._generate_appearance(race, age_years, profession)

        # 个性（Big Five，带随机性）
        personality = Personality(
            openness=self._random_trait(),
            conscientiousness=self._random_trait(),
            extraversion=self._random_trait(),
            agreeableness=self._random_trait(),
            neuroticism=self._random_trait(),
        )

        # 价值观
        values = Values(
            tradition=self._random_trait(),
            community=self._random_trait(),
            wealth=self._random_trait(),
            power=self._random_trait(),
            knowledge=self._random_trait(),
        )

        # 职业
        if profession is None:
            # 根据种族选择典型职业
            race_info = RACES[race]
            typical_profs = [p for p in Profession if PROFESSIONS[p].display_name_zh in race_info.typical_professions]
            if typical_profs:
                profession = random.choice(typical_profs)
            else:
                profession = random.choice(list(Profession))

        # 初始金钱（根据职业）
        prof_info = PROFESSIONS[profession]
        money_copper = random.randint(
            prof_info.base_income_per_day_copper * 5,
            prof_info.base_income_per_day_copper * 20
        )

        # 创建居民
        resident = Resident(
            name=name,
            race=race,
            gender=gender,
            age=Age(years=age_years, life_stage=life_stage, birth_game_time=0),
            appearance=appearance,
            personality=personality,
            values=values,
            profession=profession,
            money_copper=money_copper,
            current_scene_id="region.crown_creek_town",
        )

        # 根据职业初始化技能
        self._initialize_skills(resident, profession)

        return resident

    def generate_batch(
        self,
        count: int,
        race_distribution: Optional[dict] = None,
    ) -> list[Resident]:
        """
        批量生成居民

        Args:
            count: 生成数量
            race_distribution: 种族分布（如 {Race.HUMAN: 0.5, Race.ELF: 0.3, ...}）

        Returns:
            list[Resident]: 生成的居民列表
        """
        if race_distribution is None:
            # 默认分布：50% 人类，其他均分
            race_distribution = {
                Race.HUMAN: 0.5,
                Race.ELF: 0.2,
                Race.DWARF: 0.2,
                Race.HALFLING: 0.1,
            }

        residents = []
        for _ in range(count):
            # 按分布选择种族
            race = self._weighted_random_choice(race_distribution)
            residents.append(self.generate(race=race))

        return residents

    def _generate_name(self, gender: Gender, race: Race) -> str:
        """生成姓名"""
        family_name = random.choice(FAMILY_NAMES)

        if gender == Gender.MALE:
            first_name = random.choice(FIRST_NAMES_MALE)
        else:
            first_name = random.choice(FIRST_NAMES_FEMALE)

        return f"{family_name}{first_name}"

    def _generate_appearance(self, race: Race, age: int, profession: Optional[Profession]) -> Appearance:
        """生成外观"""
        # Sprite ID 根据种族和职业
        if profession:
            sprite_base = f"{race.value}_{profession.value}"
        else:
            sprite_base = f"{race.value}_default"

        # 根据种族选择典型特征
        if race == Race.ELF:
            skin_tone = random.choice(["fair", "pale", "olive"])
            hair_color = random.choice(["blonde", "silver", "brown"])
            height_cm = random.randint(165, 185)
        elif race == Race.DWARF:
            skin_tone = random.choice(["tan", "olive", "fair"])
            hair_color = random.choice(["brown", "black", "red", "gray"])
            height_cm = random.randint(125, 145)
        elif race == Race.HALFLING:
            skin_tone = random.choice(["fair", "tan"])
            hair_color = random.choice(["brown", "black", "blonde"])
            height_cm = random.randint(95, 115)
        else:  # HUMAN
            skin_tone = random.choice(SKIN_TONES)
            hair_color = random.choice(HAIR_COLORS)
            height_cm = random.randint(155, 185)

        # 年龄影响发色
        if age > 50:
            hair_color = random.choice(["gray", "white", hair_color])

        return Appearance(
            sprite_id=sprite_base,
            skin_tone=skin_tone,
            hair_color=hair_color,
            eye_color=random.choice(EYE_COLORS),
            height_cm=height_cm,
            build=random.choice(BUILDS),
        )

    def _initialize_skills(self, resident: Resident, profession: Profession):
        """根据职业初始化技能"""
        skill_mapping = {
            Profession.FARMER: SkillType.FARMING,
            Profession.MINER: SkillType.MINING,
            Profession.BLACKSMITH: SkillType.BLACKSMITHING,
            Profession.ALCHEMIST: SkillType.ALCHEMY,
            Profession.MAGE: SkillType.MAGIC,
            Profession.GUARD: SkillType.COMBAT,
            Profession.MERCHANT: SkillType.TRADING,
            Profession.INNKEEPER: SkillType.COOKING,
        }

        primary_skill = skill_mapping.get(profession)
        if primary_skill:
            skill = resident.get_skill(primary_skill)
            skill.level = random.randint(3, 7)  # 初始 3-7 级
            skill.experience = random.randint(0, 100)

        # 所有居民都有一些社交技能
        social_skill = resident.get_skill(SkillType.SOCIAL)
        social_skill.level = random.randint(1, 3)

    def _get_life_stage(self, age: int) -> str:
        """根据年龄获取生命阶段"""
        if age < 18:
            return "youth"
        elif age < 60:
            return "adult"
        else:
            return "elder"

    def _random_trait(self) -> int:
        """生成随机特质值（偏向中性，正态分布）"""
        # 使用三角分布，中心在 50
        value = random.triangular(0, 100, 50)
        return int(value)

    def _weighted_random_choice(self, distribution: dict):
        """加权随机选择"""
        choices = list(distribution.keys())
        weights = list(distribution.values())
        return random.choices(choices, weights=weights, k=1)[0]

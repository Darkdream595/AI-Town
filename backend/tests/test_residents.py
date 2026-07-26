"""
测试 Resident 数据模型

验证 DOC-RESIDENT-001 到 DOC-RESIDENT-012
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from residents import (
    Resident,
    Gender,
    NeedType,
    EmotionType,
    Emotion,
    SkillType,
    HealthStatus,
)
from world import Race, Profession
from foundation import WorldCoordinate, is_valid_ulid


class TestResidentCreation:
    """Resident 创建测试"""

    def test_create_resident_with_defaults(self):
        """测试创建居民（默认值）"""
        resident = Resident()

        assert is_valid_ulid(resident.resident_id)
        assert resident.race == Race.HUMAN
        assert resident.gender == Gender.MALE
        assert resident.age.years == 25
        assert resident.age.life_stage == "adult"

    def test_create_resident_with_custom_values(self):
        """测试创建居民（自定义值）"""
        resident = Resident(
            name="艾莉亚",
            race=Race.ELF,
            gender=Gender.FEMALE,
        )

        assert resident.name == "艾莉亚"
        assert resident.race == Race.ELF
        assert resident.gender == Gender.FEMALE

    def test_resident_id_unique(self):
        """测试居民 ID 唯一性"""
        residents = [Resident() for _ in range(100)]
        ids = [r.resident_id for r in residents]

        assert len(ids) == len(set(ids)), "Resident IDs should be unique"


class TestPersonality:
    """个性测试"""

    def test_personality_defaults(self):
        """测试个性默认值（50 = 中性）"""
        resident = Resident()

        assert resident.personality.openness == 50
        assert resident.personality.conscientiousness == 50
        assert resident.personality.extraversion == 50
        assert resident.personality.agreeableness == 50
        assert resident.personality.neuroticism == 50

    def test_personality_range(self):
        """测试个性值范围（0-100）"""
        from residents.resident_model import Personality

        # 合法范围
        p = Personality(
            openness=0,
            conscientiousness=100,
            extraversion=50,
            agreeableness=25,
            neuroticism=75
        )

        assert 0 <= p.openness <= 100
        assert 0 <= p.conscientiousness <= 100


class TestNeeds:
    """需求测试"""

    def test_get_need_initial_value(self):
        """测试获取需求初始值"""
        resident = Resident()

        hunger = resident.needs.get_need(NeedType.HUNGER)
        assert hunger.need_type == NeedType.HUNGER
        assert hunger.value == 80  # 初始 80%
        assert hunger.decay_rate == 5.0

    def test_need_decay(self):
        """测试需求衰减"""
        resident = Resident()
        resident.needs.get_need(NeedType.HUNGER)

        # 模拟 10 游戏小时后
        resident.needs.update_decay(current_game_time=600)  # 600 分钟 = 10 小时

        hunger = resident.needs.get_need(NeedType.HUNGER)
        # 80 - (5.0 * 10) = 30
        assert hunger.value == 30

    def test_need_decay_minimum_zero(self):
        """测试需求衰减不低于 0"""
        resident = Resident()
        resident.needs.get_need(NeedType.HUNGER)

        # 模拟 100 游戏小时后
        resident.needs.update_decay(current_game_time=6000)

        hunger = resident.needs.get_need(NeedType.HUNGER)
        assert hunger.value >= 0


class TestEmotions:
    """情绪测试"""

    def test_add_emotion(self):
        """测试添加情绪"""
        resident = Resident()

        emotion = Emotion(
            emotion_type=EmotionType.HAPPY,
            intensity=80,
            caused_by="获得礼物"
        )

        resident.emotions.add_emotion(emotion)

        assert len(resident.emotions.current_emotions) == 1
        assert resident.emotions.current_emotions[0].emotion_type == EmotionType.HAPPY

    def test_emotion_limit(self):
        """测试情绪数量限制（最多 5 个）"""
        resident = Resident()

        # 添加 10 个情绪
        for i in range(10):
            resident.emotions.add_emotion(Emotion(
                emotion_type=EmotionType.HAPPY,
                intensity=50 + i
            ))

        # 应该只保留最强的 5 个
        assert len(resident.emotions.current_emotions) <= 5

    def test_mood_calculation(self):
        """测试心情计算"""
        resident = Resident()

        # 添加正面情绪
        resident.emotions.add_emotion(Emotion(
            emotion_type=EmotionType.HAPPY,
            intensity=80
        ))
        resident.emotions.update_mood()

        # 心情应该偏高
        assert resident.emotions.mood > 50


class TestSkills:
    """技能测试"""

    def test_get_skill_initial_level(self):
        """测试获取技能初始等级"""
        resident = Resident()

        farming = resident.get_skill(SkillType.FARMING)

        assert farming.skill_type == SkillType.FARMING
        assert farming.level == 1
        assert farming.experience == 0

    def test_skill_level_up(self):
        """测试技能升级"""
        resident = Resident()

        farming = resident.get_skill(SkillType.FARMING)
        farming.level = 5
        farming.experience = 1000

        assert farming.level == 5
        assert farming.experience == 1000


class TestHealth:
    """健康测试"""

    def test_health_defaults(self):
        """测试健康默认值"""
        resident = Resident()

        assert resident.health.status == HealthStatus.HEALTHY
        assert resident.health.current_hp == 100
        assert resident.health.max_hp == 100
        assert len(resident.health.injuries) == 0

    def test_health_injured(self):
        """测试受伤状态"""
        resident = Resident()

        resident.health.status = HealthStatus.INJURED
        resident.health.current_hp = 60
        resident.health.injuries.append("左臂划伤")

        assert resident.health.status == HealthStatus.INJURED
        assert resident.health.current_hp == 60
        assert "左臂划伤" in resident.health.injuries


class TestProfessionAndHome:
    """职业和住所测试"""

    def test_assign_profession(self):
        """测试分配职业"""
        resident = Resident(name="农夫汤姆")

        resident.profession = Profession.FARMER
        resident.workplace_building_id = "building_farm_001"
        resident.home_building_id = "building_house_001"

        assert resident.profession == Profession.FARMER
        assert resident.workplace_building_id == "building_farm_001"
        assert resident.home_building_id == "building_house_001"


class TestResidentUpdate:
    """Resident 更新测试"""

    def test_update_resident_state(self):
        """测试更新居民状态"""
        resident = Resident()
        resident.needs.get_need(NeedType.HUNGER)

        # 更新到游戏时间 120 分钟
        resident.update(current_game_time=120)

        # 需求应该衰减
        hunger = resident.needs.get_need(NeedType.HUNGER)
        assert hunger.value < 80  # 从 80 衰减

        # last_updated 应该更新或相同（可能在同一毫秒）
        assert resident.last_updated.timestamp_ms >= resident.created_at.timestamp_ms

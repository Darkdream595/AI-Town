"""
Resident 数据模型

符合 DOC-RESIDENT-001 到 DOC-RESIDENT-012 规范：
- Resident 身份、种族、外观
- 个性和价值观
- Needs（需求）和 Emotions（情绪）
- 技能和能力
- 职业和住所绑定
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime

from ..foundation import generate_ulid, WorldCoordinate, RealTime
from ..world import Race, Profession


# ==================== 性别和年龄 ====================

class Gender(str, Enum):
    """性别"""
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"


@dataclass
class Age:
    """年龄信息"""
    years: int  # 实际年龄（年）
    life_stage: str  # 生命阶段：youth, adult, elder
    birth_game_time: int  # 出生时的游戏时间（游戏分钟）


# ==================== 外观 ====================

@dataclass
class Appearance:
    """外观特征"""
    sprite_id: str  # Sprite Atlas ID（如 "human_farmer"）
    skin_tone: str  # 肤色（如 "fair", "tan", "dark"）
    hair_color: str  # 发色
    eye_color: str  # 瞳色
    height_cm: int  # 身高（厘米）
    build: str  # 体型（如 "slim", "average", "sturdy"）


# ==================== 个性与价值观 ====================

@dataclass
class Personality:
    """
    个性特质（Big Five 模型）

    每个维度 0-100，50 为中性
    """
    openness: int          # 开放性（0=保守，100=开放）
    conscientiousness: int # 尽责性（0=随意，100=谨慎）
    extraversion: int      # 外向性（0=内向，100=外向）
    agreeableness: int     # 宜人性（0=竞争，100=合作）
    neuroticism: int       # 神经质（0=稳定，100=敏感）


@dataclass
class Values:
    """
    价值观倾向

    每个维度 0-100
    """
    tradition: int   # 传统 vs 变革
    community: int   # 集体 vs 个人
    wealth: int      # 物质 vs 精神
    power: int       # 权力 vs 平等
    knowledge: int   # 知识 vs 实践


# ==================== Needs（需求）====================

class NeedType(str, Enum):
    """需求类型"""
    HUNGER = "hunger"          # 饥饿
    THIRST = "thirst"          # 口渴
    ENERGY = "energy"          # 精力
    HYGIENE = "hygiene"        # 卫生
    SOCIAL = "social"          # 社交
    COMFORT = "comfort"        # 舒适
    SAFETY = "safety"          # 安全
    ENTERTAINMENT = "entertainment"  # 娱乐


@dataclass
class Need:
    """单个需求"""
    need_type: NeedType
    value: int  # 0-100，0=极度匮乏，100=完全满足
    decay_rate: float  # 衰减速率（每游戏小时）
    last_updated: int  # 上次更新时的游戏时间


@dataclass
class NeedsState:
    """需求状态集合"""
    needs: Dict[NeedType, Need] = field(default_factory=dict)

    def get_need(self, need_type: NeedType) -> Need:
        """获取指定需求"""
        if need_type not in self.needs:
            # 初始化默认需求
            self.needs[need_type] = Need(
                need_type=need_type,
                value=80,  # 初始 80%
                decay_rate=self._get_default_decay_rate(need_type),
                last_updated=0
            )
        return self.needs[need_type]

    def _get_default_decay_rate(self, need_type: NeedType) -> float:
        """获取默认衰减速率"""
        decay_rates = {
            NeedType.HUNGER: 5.0,       # 每小时 -5
            NeedType.THIRST: 8.0,       # 每小时 -8
            NeedType.ENERGY: 4.0,       # 每小时 -4
            NeedType.HYGIENE: 2.0,      # 每小时 -2
            NeedType.SOCIAL: 3.0,       # 每小时 -3
            NeedType.COMFORT: 2.5,      # 每小时 -2.5
            NeedType.SAFETY: 1.0,       # 每小时 -1
            NeedType.ENTERTAINMENT: 3.5,  # 每小时 -3.5
        }
        return decay_rates.get(need_type, 2.0)

    def update_decay(self, current_game_time: int):
        """更新所有需求的衰减"""
        for need in self.needs.values():
            elapsed_hours = (current_game_time - need.last_updated) / 60
            decay = need.decay_rate * elapsed_hours
            need.value = max(0, need.value - int(decay))
            need.last_updated = current_game_time


# ==================== Emotions（情绪）====================

class EmotionType(str, Enum):
    """情绪类型"""
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    EXCITED = "excited"
    CALM = "calm"
    ANXIOUS = "anxious"
    CONTENT = "content"


@dataclass
class Emotion:
    """单个情绪"""
    emotion_type: EmotionType
    intensity: int  # 0-100
    caused_by: Optional[str] = None  # 触发事件描述
    expires_at: Optional[int] = None  # 过期时的游戏时间


@dataclass
class EmotionState:
    """情绪状态"""
    current_emotions: List[Emotion] = field(default_factory=list)
    mood: int = 50  # 整体心情（0-100）

    def add_emotion(self, emotion: Emotion):
        """添加情绪"""
        self.current_emotions.append(emotion)
        # 限制情绪数量（保留最强的 5 个）
        if len(self.current_emotions) > 5:
            self.current_emotions.sort(key=lambda e: e.intensity, reverse=True)
            self.current_emotions = self.current_emotions[:5]

    def update_mood(self):
        """更新整体心情"""
        if not self.current_emotions:
            return

        # 根据当前情绪计算心情
        positive_emotions = [EmotionType.HAPPY, EmotionType.EXCITED, EmotionType.CONTENT, EmotionType.CALM]
        positive_sum = sum(e.intensity for e in self.current_emotions if e.emotion_type in positive_emotions)
        negative_sum = sum(e.intensity for e in self.current_emotions if e.emotion_type not in positive_emotions)

        # 加权平均
        total_intensity = positive_sum + negative_sum
        if total_intensity > 0:
            self.mood = int((positive_sum / total_intensity) * 100)


# ==================== 技能 ====================

class SkillType(str, Enum):
    """技能类型"""
    FARMING = "farming"
    MINING = "mining"
    BLACKSMITHING = "blacksmithing"
    ALCHEMY = "alchemy"
    MAGIC = "magic"
    COMBAT = "combat"
    TRADING = "trading"
    COOKING = "cooking"
    CRAFTING = "crafting"
    SOCIAL = "social"


@dataclass
class Skill:
    """技能"""
    skill_type: SkillType
    level: int = 1  # 1-10
    experience: int = 0  # 经验值


# ==================== 健康状态 ====================

class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"
    INJURED = "injured"
    ILL = "ill"
    UNCONSCIOUS = "unconscious"
    RECOVERING = "recovering"


@dataclass
class HealthState:
    """健康状态"""
    status: HealthStatus = HealthStatus.HEALTHY
    current_hp: int = 100
    max_hp: int = 100
    injuries: List[str] = field(default_factory=list)  # 伤势描述
    illnesses: List[str] = field(default_factory=list)  # 疾病描述
    recovery_progress: int = 0  # 恢复进度（0-100）


# ==================== Resident 主类 ====================

@dataclass
class Resident:
    """
    居民数据模型

    符合 DOC-RESIDENT-001 规范
    """
    # 唯一标识
    resident_id: str = field(default_factory=generate_ulid)

    # 基本信息
    name: str = ""
    race: Race = Race.HUMAN
    gender: Gender = Gender.MALE
    age: Age = field(default_factory=lambda: Age(years=25, life_stage="adult", birth_game_time=0))

    # 外观
    appearance: Appearance = field(default_factory=lambda: Appearance(
        sprite_id="human_farmer",
        skin_tone="fair",
        hair_color="brown",
        eye_color="brown",
        height_cm=170,
        build="average"
    ))

    # 个性与价值观
    personality: Personality = field(default_factory=lambda: Personality(
        openness=50,
        conscientiousness=50,
        extraversion=50,
        agreeableness=50,
        neuroticism=50
    ))
    values: Values = field(default_factory=lambda: Values(
        tradition=50,
        community=50,
        wealth=50,
        power=50,
        knowledge=50
    ))

    # 职业和住所
    profession: Optional[Profession] = None
    workplace_building_id: Optional[str] = None
    home_building_id: Optional[str] = None

    # 位置
    current_position: Optional[WorldCoordinate] = None
    current_scene_id: str = "region.crown_creek_town"

    # 需求和情绪
    needs: NeedsState = field(default_factory=NeedsState)
    emotions: EmotionState = field(default_factory=EmotionState)

    # 健康
    health: HealthState = field(default_factory=HealthState)

    # 技能
    skills: Dict[SkillType, Skill] = field(default_factory=dict)

    # 物品栏
    inventory_item_ids: List[str] = field(default_factory=list)
    money_copper: int = 100  # 初始 100 铜羽

    # 元数据
    created_at: RealTime = field(default_factory=RealTime.now)
    last_updated: RealTime = field(default_factory=RealTime.now)

    def get_skill(self, skill_type: SkillType) -> Skill:
        """获取技能"""
        if skill_type not in self.skills:
            self.skills[skill_type] = Skill(skill_type=skill_type)
        return self.skills[skill_type]

    def update(self, current_game_time: int):
        """更新居民状态（需求衰减、情绪过期）"""
        self.needs.update_decay(current_game_time)
        self.emotions.update_mood()
        self.last_updated = RealTime.now()

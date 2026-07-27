"""
居民系统数据模型

符合 DOC-RESIDENT-001 到 DOC-RESIDENT-009 规范
使用 Pydantic V2 进行数据验证
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime

from .schemas import (
    RESIDENT_AGGREGATE_SCHEMA_VERSION,
    IDENTITY_SCHEMA_VERSION,
    PERSONALITY_SCHEMA_VERSION,
    NEEDS_SCHEMA_VERSION,
    CAPABILITY_SCHEMA_VERSION,
    ASSIGNMENT_SCHEMA_VERSION,
    HEALTH_SCHEMA_VERSION,
    LIFECYCLE_SCHEMA_VERSION,
    ROUTINE_SCHEMA_VERSION,
)


# ============================================================================
# Identity - 身份系统 (DOC-RESIDENT-002)
# ============================================================================

class LanguageProficiency(BaseModel):
    """语言熟练度"""
    language_id: str = Field(..., description="语言ID，如 language.crown_common")
    level: int = Field(..., ge=0, le=100, description="熟练度 0-100")


class Appearance(BaseModel):
    """外观配置"""
    profile_id: str = Field(..., description="外观配置ID")
    sprite_asset_id: str = Field(..., description="Sprite 资源ID，如 sprite.resident.apothecary")
    portrait_asset_id: str = Field(..., description="肖像资源ID")
    combat_sprite_asset_id: str = Field(..., description="战斗 Sprite 资源ID")
    palette_variant_id: str = Field(..., description="调色板变体ID")
    presentation_tags: List[str] = Field(default_factory=list, description="展示标签，如 hair.braided")


class ResidentIdentity(BaseModel):
    """
    居民身份

    符合 DOC-RESIDENT-002 规范
    """
    identity_schema_version: int = Field(default=IDENTITY_SCHEMA_VERSION, description="身份 Schema 版本")
    display_name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    self_name: str = Field(..., min_length=1, max_length=100, description="自称名字")
    pronoun_id: str = Field(..., description="代词ID，如 pronoun.she, pronoun.he, pronoun.they")
    ancestry_id: str = Field(..., description="种族ID，如 ancestry.human, ancestry.elf")
    culture_ids: List[str] = Field(default_factory=list, description="文化ID列表")
    language_proficiencies: List[LanguageProficiency] = Field(default_factory=list, description="语言熟练度")
    appearance: Appearance = Field(..., description="外观配置")


# ============================================================================
# Personality - 个性系统 (DOC-RESIDENT-003)
# ============================================================================

class PersonalityDimensions(BaseModel):
    """个性六维度"""
    sociability: int = Field(..., ge=0, le=100, description="社交性")
    diligence: int = Field(..., ge=0, le=100, description="勤奋度")
    curiosity: int = Field(..., ge=0, le=100, description="好奇心")
    empathy: int = Field(..., ge=0, le=100, description="共情力")
    caution: int = Field(..., ge=0, le=100, description="谨慎性")
    assertiveness: int = Field(..., ge=0, le=100, description="主张性")


class ValueWeight(BaseModel):
    """价值观权重"""
    value_id: str = Field(..., description="价值观ID，如 value.community")
    weight_q1000: int = Field(..., ge=0, le=1000, description="权重 0-1000")


class PreferenceWeight(BaseModel):
    """偏好权重"""
    preference_id: str = Field(..., description="偏好ID，如 preference.activity.herbalism")
    weight_q1000: int = Field(..., ge=0, le=1000, description="权重 0-1000")


class ResidentPersonality(BaseModel):
    """
    居民个性

    符合 DOC-RESIDENT-003 规范
    """
    schema_version: int = Field(default=PERSONALITY_SCHEMA_VERSION, description="个性 Schema 版本")
    dimensions: PersonalityDimensions = Field(..., description="个性六维度")
    values: List[ValueWeight] = Field(default_factory=list, description="价值观列表")
    preferences: List[PreferenceWeight] = Field(default_factory=list, description="偏好列表")
    fears: List[str] = Field(default_factory=list, description="恐惧列表")
    profile_revision: int = Field(default=0, description="个性配置修订版本")


# ============================================================================
# Needs & Emotions - 需求与情绪 (DOC-RESIDENT-004)
# ============================================================================

class NeedValue(BaseModel):
    """单个需求值"""
    value_q1000: int = Field(..., ge=0, le=1000, description="需求值 0-1000，0=完全满足，1000=极度匮乏")
    last_updated_game_time: int = Field(..., ge=0, description="最后更新的游戏时间（分钟）")


class Emotion(BaseModel):
    """情绪状态"""
    primary: str = Field(..., description="主要情绪，如 calm, happy, angry, fearful")
    intensity_q1000: int = Field(..., ge=0, le=1000, description="情绪强度 0-1000")
    cause_event_ids: List[str] = Field(default_factory=list, description="导致情绪的事件ID列表")
    updated_at_game_time: int = Field(..., ge=0, description="情绪更新时间")
    decay_rate_q1000_per_game_hour: int = Field(..., ge=0, le=1000, description="每游戏小时衰减速率")


class ResidentNeedsState(BaseModel):
    """
    居民需求状态

    符合 DOC-RESIDENT-004 规范
    """
    needs_schema_version: int = Field(default=NEEDS_SCHEMA_VERSION, description="需求 Schema 版本")
    values: Dict[str, NeedValue] = Field(
        default_factory=dict,
        description="需求值字典：hunger, fatigue, safety, social, comfort"
    )
    emotion: Emotion = Field(..., description="当前情绪状态")


# ============================================================================
# Capability - 技能能力 (DOC-RESIDENT-005)
# ============================================================================

class SkillRating(BaseModel):
    """技能评级"""
    rating: int = Field(..., ge=0, le=100, description="技能等级 0-100")
    xp: int = Field(default=0, ge=0, description="经验值")
    last_practiced_game_time: int = Field(..., ge=0, description="最后练习时间")


class ResidentCapabilityState(BaseModel):
    """
    居民技能能力状态

    符合 DOC-RESIDENT-005 规范
    """
    capability_schema_version: int = Field(default=CAPABILITY_SCHEMA_VERSION, description="能力 Schema 版本")
    skills: Dict[str, SkillRating] = Field(default_factory=dict, description="技能字典")
    ability_ids: List[str] = Field(default_factory=list, description="已解锁能力ID列表")
    capability_revision: int = Field(default=0, description="能力修订版本")


# ============================================================================
# Assignment - 职业与住所 (DOC-RESIDENT-006)
# ============================================================================

class ProfessionAssignment(BaseModel):
    """职业分配"""
    assignment_id: str = Field(..., description="分配ID（ULID）")
    profession_id: str = Field(..., description="职业ID，如 profession.apothecary")
    workplace_id: str = Field(..., description="工作场所ID")
    state: str = Field(..., description="状态：active, suspended, terminated")
    effective_from_game_time: int = Field(..., ge=0, description="生效开始时间")
    effective_until_game_time: Optional[int] = Field(None, description="生效结束时间，None表示无限期")


class ResidenceAssignment(BaseModel):
    """住所分配"""
    assignment_id: str = Field(..., description="分配ID（ULID）")
    building_id: str = Field(..., description="建筑ID")
    interior_scene_id: str = Field(..., description="室内场景ID")
    bed_node_id: str = Field(..., description="床位节点ID")
    state: str = Field(..., description="状态：active, temporary, evicted")


class ResidentAssignmentState(BaseModel):
    """
    居民职业与住所分配

    符合 DOC-RESIDENT-006 规范
    """
    assignment_schema_version: int = Field(default=ASSIGNMENT_SCHEMA_VERSION, description="分配 Schema 版本")
    profession: Optional[ProfessionAssignment] = Field(None, description="职业分配")
    residence: Optional[ResidenceAssignment] = Field(None, description="住所分配")


# ============================================================================
# Health - 健康状态 (DOC-RESIDENT-007)
# ============================================================================

class Injury(BaseModel):
    """伤势"""
    injury_id: str = Field(..., description="伤势ID")
    severity: str = Field(..., description="严重程度：minor, moderate, severe")
    body_part: str = Field(..., description="受伤部位")
    inflicted_at_game_time: int = Field(..., ge=0, description="受伤时间")
    healed_at_game_time: Optional[int] = Field(None, description="治愈时间")


class Illness(BaseModel):
    """疾病"""
    illness_id: str = Field(..., description="疾病ID")
    severity: str = Field(..., description="严重程度：mild, moderate, severe")
    onset_at_game_time: int = Field(..., ge=0, description="发病时间")
    cured_at_game_time: Optional[int] = Field(None, description="治愈时间")


class HealthRestriction(BaseModel):
    """健康限制"""
    restriction_type: str = Field(..., description="限制类型：movement, combat, work")
    reason: str = Field(..., description="限制原因")
    until_game_time: Optional[int] = Field(None, description="限制结束时间")


class ResidentHealthState(BaseModel):
    """
    居民健康状态

    符合 DOC-RESIDENT-007 规范
    """
    health_schema_version: int = Field(default=HEALTH_SCHEMA_VERSION, description="健康 Schema 版本")
    condition: str = Field(..., description="健康状况：healthy, injured, ill, critical, downed")
    hp_current: int = Field(..., ge=0, description="当前生命值")
    hp_max: int = Field(..., gt=0, description="最大生命值")
    injuries: List[Injury] = Field(default_factory=list, description="伤势列表")
    illnesses: List[Illness] = Field(default_factory=list, description="疾病列表")
    restrictions: List[HealthRestriction] = Field(default_factory=list, description="行动限制列表")
    health_revision: int = Field(default=0, description="健康修订版本")


# ============================================================================
# Lifecycle - 生命周期 (DOC-RESIDENT-008)
# ============================================================================

class DefeatRecord(BaseModel):
    """失败/倒下记录（非永久死亡）"""
    defeat_id: str = Field(..., description="失败事件ID")
    defeated_at_game_time: int = Field(..., ge=0, description="倒下时间")
    cause: str = Field(..., description="倒下原因")
    recovery_at_game_time: Optional[int] = Field(None, description="恢复时间")


class ResidentLifecycle(BaseModel):
    """
    居民生命周期

    符合 DOC-RESIDENT-008 规范
    """
    lifecycle_schema_version: int = Field(default=LIFECYCLE_SCHEMA_VERSION, description="生命周期 Schema 版本")
    age_stage: str = Field(..., description="年龄阶段：child, teen, adult, elder")
    age_stage_since_game_time: int = Field(..., ge=0, description="进入当前年龄阶段的时间")
    lifecycle_state: str = Field(..., description="生命周期状态：active, downed, inactive")
    defeat: Optional[DefeatRecord] = Field(None, description="失败记录")


# ============================================================================
# Routine - 日常作息 (DOC-RESIDENT-009)
# ============================================================================

class RoutineWindow(BaseModel):
    """作息窗口"""
    window_id: str = Field(..., description="窗口ID")
    day_type: str = Field(..., description="日期类型：workday, restday, festival")
    start_minute_of_day: int = Field(..., ge=0, lt=1440, description="开始时间（一天中的分钟数 0-1439）")
    end_minute_of_day: int = Field(..., ge=0, lt=1440, description="结束时间")
    candidate_activity_tags: List[str] = Field(default_factory=list, description="候选活动标签")
    preferred_destination_ids: List[str] = Field(default_factory=list, description="首选目的地ID")
    flexibility_game_minutes: int = Field(..., ge=0, description="灵活性（游戏分钟）")
    interruptibility: str = Field(..., description="可中断性：low, normal, high")


class ResidentRoutineState(BaseModel):
    """
    居民日常作息状态

    符合 DOC-RESIDENT-009 规范
    """
    routine_schema_version: int = Field(default=ROUTINE_SCHEMA_VERSION, description="作息 Schema 版本")
    schedule_profile_id: str = Field(..., description="作息配置ID")
    windows: List[RoutineWindow] = Field(default_factory=list, description="作息窗口列表")
    active_long_action_id: Optional[str] = Field(None, description="当前长时间行动ID")
    routine_revision: int = Field(default=0, description="作息修订版本")


# ============================================================================
# Resident Aggregate - 居民聚合根 (DOC-RESIDENT-001)
# ============================================================================

class ResidentAggregate(BaseModel):
    """
    居民聚合根

    符合 DOC-RESIDENT-001 规范
    这是唯一的权威存储和序列化 Schema
    """
    aggregate_schema_version: int = Field(
        default=RESIDENT_AGGREGATE_SCHEMA_VERSION,
        description="聚合根 Schema 版本"
    )
    resident_id: str = Field(..., description="居民实例ID（ULID）")
    resident_key: str = Field(..., description="居民稳定 Catalog ID")
    world_id: str = Field(..., description="世界ID（ULID）")
    resident_revision: int = Field(..., ge=0, description="居民修订版本（World Revision）")

    # 子系统状态（内嵌完整对象，不允许ID引用）
    identity: ResidentIdentity = Field(..., description="身份信息")
    personality: ResidentPersonality = Field(..., description="个性信息")
    needs_state: ResidentNeedsState = Field(..., description="需求状态")
    capability_state: ResidentCapabilityState = Field(..., description="能力状态")
    assignment_state: ResidentAssignmentState = Field(..., description="职业住所分配")
    health_state: ResidentHealthState = Field(..., description="健康状态")
    lifecycle: ResidentLifecycle = Field(..., description="生命周期")
    routine_state: ResidentRoutineState = Field(..., description="日常作息")

    # 外部引用（只存储ID）
    inventory_id: str = Field(..., description="物品栏ID（外部引用）")

    # 时间戳
    created_at_game_time: int = Field(..., ge=0, description="创建时间（游戏时间分钟）")
    updated_at_game_time: int = Field(..., ge=0, description="最后更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "aggregate_schema_version": 1,
                "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
                "resident_key": "resident.farmer.thomas",
                "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
                "resident_revision": 0,
                "inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
                "created_at_game_time": 0,
                "updated_at_game_time": 0,
            }
        }


# ============================================================================
# Resident Summary Projection - 只读摘要 (DOC-RESIDENT-001)
# ============================================================================

class ResidentSummaryProjection(BaseModel):
    """
    居民摘要投影（只读）

    用于列表展示、UI等场景
    不能用于持久化存储
    """
    resident_id: str
    resident_key: str
    display_name: str
    ancestry_id: str
    profession_id: Optional[str] = None
    lifecycle_state: str
    condition: str
    hp_current: int
    hp_max: int
    primary_emotion: str

    # 需求简要（仅显示关键指标）
    hunger_q1000: int
    fatigue_q1000: int
    social_q1000: int

    @classmethod
    def from_aggregate(cls, aggregate: ResidentAggregate) -> "ResidentSummaryProjection":
        """从聚合根创建摘要"""
        return cls(
            resident_id=aggregate.resident_id,
            resident_key=aggregate.resident_key,
            display_name=aggregate.identity.display_name,
            ancestry_id=aggregate.identity.ancestry_id,
            profession_id=aggregate.assignment_state.profession.profession_id
                if aggregate.assignment_state.profession else None,
            lifecycle_state=aggregate.lifecycle.lifecycle_state,
            condition=aggregate.health_state.condition,
            hp_current=aggregate.health_state.hp_current,
            hp_max=aggregate.health_state.hp_max,
            primary_emotion=aggregate.needs_state.emotion.primary,
            hunger_q1000=aggregate.needs_state.values.get("hunger", NeedValue(value_q1000=0, last_updated_game_time=0)).value_q1000,
            fatigue_q1000=aggregate.needs_state.values.get("fatigue", NeedValue(value_q1000=0, last_updated_game_time=0)).value_q1000,
            social_q1000=aggregate.needs_state.values.get("social", NeedValue(value_q1000=0, last_updated_game_time=0)).value_q1000,
        )

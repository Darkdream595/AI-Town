"""
魔法域共享常量（DOC-MAGIC-001..012 的数值与封闭枚举真源）

平衡包络常量集中在 `magic.balance.v1`（RULE-MAGIC-066）：运行时不可热改，
调整走文档版本变更，历史结算不受追溯。
"""

from enum import Enum

# -- REQ-MAGIC-005：Mana 模型 --
MANA_MAX_BASE = 60
MANA_MAX_CAP = 160  # 60 + SchoolSkill 上限 100

# -- RULE-MAGIC-010/011：周期恢复 --
MANA_REGEN_INTERVAL_MINUTES = 10
MANA_BASE_REGEN = 3
TIDE_Q1000_MIN = 500
TIDE_Q1000_MAX = 1500
TIDE_Q1000_DEFAULT = 1000
REGEN_INCREMENT_MAX = 9  # floor(3 × 1500/1000 × 2) 的包络上限（REQ-MAGIC-023）
REGEN_BATCH_CAP = 64  # 单 occurrence 处理施法者上限，超出顺延

# -- RULE-MAGIC-012：枯竭阈值（Catalog 常量） --
EXHAUSTION_ENTER_THRESHOLD = 10
EXHAUSTION_EXIT_THRESHOLD = 30

# -- RULE-MAGIC-017：法术数值范围 --
MANA_COST_MIN = 5
MANA_COST_MAX = 60
COOLDOWN_MAX_GAME_MINUTES = 1440

# -- REQ-MAGIC-020：充能 --
CHARGES_MAX_MIN = 1
CHARGES_MAX_MAX = 20

# -- RULE-MAGIC-055：回充 --
RECHARGE_MANA_PER_CHARGE = 15
RECHARGE_MIN_SCHOOL_RATING = 30

# -- RULE-MAGIC-056：被动饰物 --
TRINKET_TIDE_BONUS_CAP_Q1000 = 100

# -- RULE-MAGIC-040 / REQ-MAGIC-023：行为平衡 --
DAILY_INSTANT_CAST_BUDGET = 8
HEAL_DAILY_CAP_BPS = 5000  # 单目标每游戏日治疗累计不超过 hp_max 的 50%

# -- RULE-MAGIC-051：持续效果实例 --
EFFECT_MAX_DURATION_GAME_MINUTES = 1440
ANCHOR_MAX_DURATION_GAME_MINUTES = 10080
SCENE_EFFECT_INSTANCE_CAP = 32
ANCHOR_SCENE_CAP = 2

# -- RULE-MAGIC-031：学习难度 --
STUDY_WORK_UNITS_MIN = 4
STUDY_WORK_UNITS_PER_10_MANA = 2

# -- DOC-MAGIC-006 §9 / DOC-MAGIC-007 §9 --
KNOWLEDGE_ENTRIES_CAP = 64
CANDIDATES_CAP = 16


class ActivityKind(str, Enum):
    """RULE-MAGIC-010 的活动倍率：休息 2、常规 1、Encounter 内 0"""

    RESTING = "resting"
    NORMAL = "normal"
    ENCOUNTER = "encounter"


ACTIVITY_MULT = {
    ActivityKind.RESTING: 2,
    ActivityKind.NORMAL: 1,
    ActivityKind.ENCOUNTER: 0,
}


class CastKind(str, Enum):
    INSTANT = "instant"
    RITUAL = "ritual"


class TargetMode(str, Enum):
    """RULE-MAGIC-015 的封闭目标枚举"""

    SELF = "self"
    SINGLE_ENTITY = "single_entity"
    MULTI_ENTITY = "multi_entity"
    GROUND_POINT = "ground_point"
    AREA_AROUND_CASTER = "area_around_caster"
    NONE = "none"


class LegalOverride(str, Enum):
    INHERIT = "inherit"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"


class Legality(str, Enum):
    """REQ-MAGIC-010 的判定输出"""

    PERMITTED = "permitted"
    RESTRICTED_AUTHORIZED = "restricted_authorized"
    REJECTED = "rejected"


class VerdictClassification(str, Enum):
    """RULE-MAGIC-027 的四分类"""

    VALID = "VALID"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    TRANSIENT_OWNER_UNAVAILABLE = "TRANSIENT_OWNER_UNAVAILABLE"


class KnowledgeState(str, Enum):
    """RULE-MAGIC-029：unknown → studying → learned，无降级"""

    STUDYING = "studying"
    LEARNED = "learned"


class SourceKind(str, Enum):
    TEACHER = "teacher"
    SPELLBOOK = "spellbook"
    PRACTICE = "practice"
    INITIALIZATION = "initialization"


class DeclaredPurpose(str, Enum):
    UTILITY = "utility"
    HEALING = "healing"
    DEFENSE = "defense"
    COMBAT = "combat"
    RITUAL = "ritual"


class EffectInstanceState(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DISPELLED = "dispelled"


class MagicItemKind(str, Enum):
    CHARGED_SPELL_ITEM = "charged_spell_item"
    SPELLBOOK = "spellbook"
    PASSIVE_TRINKET = "passive_trinket"


class ChargeState(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"  # RULE-MAGIC-057：tombstone 同步，不可复活


#: 允许进入 cosmology 注册条的机制挂钩（DES-MAGIC-001，恰好两项）
ALLOWED_MECHANICAL_HOOKS = frozenset({"starweave_tide_modifier", "ley_anchor_presence"})

#: 被动饰物允许的注册修正键（RULE-MAGIC-056）
ALLOWED_TRINKET_MODIFIERS = frozenset({"starweave_tide_modifier", "detect_radius_bonus"})

#: DES-MAGIC-005 的 reason_code 封闭集
CAST_REASON_CODES = frozenset(
    {
        "MAGIC_SPELL_UNKNOWN",
        "MAGIC_SPELL_NOT_LEARNED",
        "MAGIC_CASTER_EXHAUSTED",
        "MAGIC_MANA_INSUFFICIENT",
        "MAGIC_TARGET_INVALID",
        "MAGIC_RANGE_EXCEEDED",
        "MAGIC_PREREQUISITE_MISSING",
        "MAGIC_CONSENT_MISSING",
        "MAGIC_LEGALITY_PROHIBITED",
        "MAGIC_ENCOUNTER_RULE_CONFLICT",
        "stale_revision",
    }
)

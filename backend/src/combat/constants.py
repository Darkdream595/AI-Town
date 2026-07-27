"""
战斗域共享常量（DOC-COMBAT-001..012 的数值与封闭枚举真源）
"""

from enum import Enum

# -- RULE-COMBAT-003：小队与站位 --
PARTY_MAX_MEMBERS = 4
FORMATION_SLOTS = ("front_left", "front_right", "rear_left", "rear_right")

# -- RULE-COMBAT-012：Round Cap --
ROUND_CAP = 200

# -- DOC-COMBAT-003 §9：候选上限（与 DOC-AI-011 一致） --
OPTION_CANDIDATE_CAP = 32

# -- DOC-COMBAT-004 §9：单 Turn Roll 上限 --
ROLL_CAP_PER_TURN = 32

# -- DOC-COMBAT-005 §9：单 Combatant 活跃状态实例上限 --
STATUS_INSTANCE_CAP = 16

# -- DOC-COMBAT-007：决策与上下文 --
DECISION_DEADLINE_MS = 8000
RECENT_TURNS_CAP = 6
MODEL_ID = "deepseek-v4-flash"
COMBAT_PROMPT_ID = "resident-combat-turn/v1"

# -- RULE-COMBAT-058：装备耐久损耗（注册表数值） --
WEAR_WEAPON_PER_USE_Q1000 = 5
WEAR_ARMOR_PER_HIT_Q1000 = 3
WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000 = 500
DURABILITY_FULL_Q1000 = 1000

# -- DOC-COMBAT-010 §9：Loot draw 上限 --
LOOT_DRAW_CAP = 64

# -- RULE-COMBAT-019：属性上下界 --
ATTRIBUTE_MIN = 1
ATTRIBUTE_MAX = 200

# -- power_q1000 注册范围（DOC-COMBAT-004 §3） --
POWER_Q1000_MIN = 100
POWER_Q1000_MAX = 5000

FORMULA_VERSION_V1 = "combat_formula.v1"

# -- 基础 attack 行动（注册常量，非硬编码于解析路径） --
BASIC_ATTACK_FORMULA_REF = "combat_formula.v1.physical_single"
BASIC_ATTACK_POWER_Q1000 = 1000
FLEE_FORMULA_REF = "combat_formula.v1.flee_attempt"
REVIVE_FORMULA_REF = "combat_formula.v1.revive"

# -- RULE-COMBAT-036：Injury Threshold Table（终态 HP 比例 -> injury.*） --
INJURY_NONE_MIN_Q1000 = 750
INJURY_BRUISES_MIN_Q1000 = 500
INJURY_DEEP_WOUNDS_MIN_Q1000 = 250
INJURY_BRUISES = "injury.bruises"
INJURY_DEEP_WOUNDS = "injury.deep_wounds"
INJURY_SEVERE_TRAUMA = "injury.severe_trauma"


class TriggerSource(str, Enum):
    """RULE-COMBAT-001：五种合法触发源"""

    AMBUSH_EVENT = "ambush_event"
    AGGRO_CONTACT = "aggro_contact"
    DEFENSE_RESPONSE = "defense_response"
    ARENA_DUEL = "arena_duel"
    SCRIPTED_QUEST = "scripted_quest"


class EncounterState(str, Enum):
    FORMING = "forming"
    ACTIVE = "active"
    RESOLVING = "resolving"
    ENDED = "ended"


class Phase(str, Enum):
    """RULE-COMBAT-007：TurnTime 只以 (round, turn, phase) 表达"""

    ROUND_START = "round_start"
    ACTOR_TURN = "actor_turn"
    ROUND_END = "round_end"


class TurnStatus(str, Enum):
    """RULE-COMBAT-010：封闭状态机"""

    PENDING = "pending"
    AWAITING_DECISION = "awaiting_decision"
    DECISION_RECEIVED = "decision_received"
    RESOLVED = "resolved"
    SKIPPED = "skipped"


class SkipReason(str, Enum):
    """RULE-COMBAT-010：skip 仅允许四种原因"""

    DEFEATED_DOWN = "defeated_down"
    FLED = "fled"
    SURRENDERED = "surrendered"
    CONTROL_STATUS = "control_status"


class Side(str, Enum):
    """首版仅两方，不支持三方混战"""

    PARTY = "party"
    ADVERSARY = "adversary"


class CombatantKind(str, Enum):
    RESIDENT = "resident"
    PLAYER_RESIDENT = "player_resident"
    CREATURE = "creature"
    SUMMON = "summon"


class CombatantState(str, Enum):
    ACTIVE = "active"
    DOWN = "down"
    FLED = "fled"
    SURRENDERED = "surrendered"


class ActionKind(str, Enum):
    """RULE-COMBAT-014：12 种封闭行动"""

    ATTACK = "attack"
    SKILL = "skill"
    CAST_SPELL = "cast_spell"
    USE_ITEM = "use_item"
    DEFEND = "defend"
    SWITCH_POSITION = "switch_position"
    ASSIST = "assist"
    OBSERVE = "observe"
    TALK = "talk"
    FLEE = "flee"
    SURRENDER = "surrender"
    PASS = "pass"


class StatusCategory(str, Enum):
    BUFF = "buff"
    DEBUFF = "debuff"
    DAMAGE_OVER_TIME = "damage_over_time"
    HEAL_OVER_TIME = "heal_over_time"
    CONTROL = "control"


class StackingPolicy(str, Enum):
    """RULE-COMBAT-028：同一 definition 只允许一种策略"""

    REFRESH_DURATION = "refresh_duration"
    STACK_INTENSITY = "stack_intensity"
    INDEPENDENT_INSTANCES = "independent_instances"
    REJECT_DUPLICATE = "reject_duplicate"


class EndCondition(str, Enum):
    """RULE-COMBAT-049：封闭终结条件"""

    SIDE_ELIMINATED = "side_eliminated"
    SURRENDER_ACCEPTED = "surrender_accepted"
    NEGOTIATED_END = "negotiated_end"
    FLEE_COMPLETE = "flee_complete"
    ROUND_CAP_FORCED = "round_cap_forced"


class DefeatOutcome(str, Enum):
    """Resident 四种非永久 + Creature 终态（RULE-COMBAT-051/053）"""

    UNCONSCIOUS = "unconscious"
    SEVERELY_INJURED = "severely_injured"
    RETREATED = "retreated"
    CAPTIVE = "captive"
    DIED = "died"
    DISSIPATED = "dissipated"
    FLED = "fled"


RESIDENT_OUTCOMES = frozenset(
    {
        DefeatOutcome.UNCONSCIOUS,
        DefeatOutcome.SEVERELY_INJURED,
        DefeatOutcome.RETREATED,
        DefeatOutcome.CAPTIVE,
    }
)
CREATURE_OUTCOMES = frozenset({DefeatOutcome.DIED, DefeatOutcome.DISSIPATED, DefeatOutcome.FLED})


class HpBucket(str, Enum):
    """DOC-COMBAT-007：敌情知识边界的封闭桶"""

    UNHARMED = "unharmed"
    SCRATCHED = "scratched"
    WOUNDED = "wounded"
    CRITICAL = "critical"
    DOWN = "down"


def hp_bucket_of(hp_current: int, hp_max: int) -> HpBucket:
    if hp_current <= 0:
        return HpBucket.DOWN
    if hp_max <= 0:
        return HpBucket.DOWN
    if hp_current >= hp_max:
        return HpBucket.UNHARMED
    ratio_q1000 = hp_current * 1000 // hp_max
    if ratio_q1000 < 250:
        return HpBucket.CRITICAL
    if ratio_q1000 < 500:
        return HpBucket.WOUNDED
    return HpBucket.SCRATCHED


class FallbackReason(str, Enum):
    """RULE-COMBAT-041：fallback 触发条件封闭集"""

    MODEL_TIMEOUT = "model_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_AFTER_REPAIR = "invalid_after_repair"
    CANCELLED = "cancelled"


#: 战斗域 reason code 汇总（测试断言用）
COMBAT_REASON_CODES = frozenset(
    {
        "COMBAT_TRIGGER_SOURCE_INVALID",
        "COMBAT_ACTOR_LOCKED",
        "COMBAT_PARTY_OVERFLOW",
        "COMBAT_PARTICIPANT_NOT_ACTIVE",
        "COMBAT_DUEL_PERMIT_MISSING",
        "COMBAT_TURN_STALE",
        "COMBAT_TURN_NOT_OWNER",
        "COMBAT_TURN_PHASE_INVALID",
        "COMBAT_OPTION_ILLEGAL",
        "COMBAT_OPTION_TARGET_INVALID",
        "COMBAT_OPTION_COST_UNPAYABLE",
        "COMBAT_NEGOTIATION_TERM_UNKNOWN",
        "COMBAT_FORMULA_INVALID",
        "COMBAT_STATUS_DEFINITION_INVALID",
        "COMBAT_RESOLUTION_MISMATCH",
        "COMBAT_SETTLEMENT_DUPLICATE",
        "COMBAT_SETTLEMENT_REVISION_STALE",
        "COMBAT_OUTCOME_MAPPING_INVALID",
        "COMBAT_CAPTIVITY_INVALID",
        "COMBAT_LOOT_TABLE_INVALID",
        "COMBAT_RESOLVE_STATE_INVALID",
        "COMBAT_RESOLVE_REVISION_STALE",
        "RESIDENT_PERMANENT_DEATH_FORBIDDEN",
    }
)

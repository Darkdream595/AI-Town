"""
战斗健康域（docs/12-combat-health，DOC-COMBAT-001..012）

确定性回合制战斗：Encounter 创建与锁、initiative 回合机、封闭行动集合、
整数公式、状态效果、非永久败北映射、战利品与耐久、AI 决策降级、
结果事务原子性与恢复。
"""

from .constants import (
    BASIC_ATTACK_FORMULA_REF,
    BASIC_ATTACK_POWER_Q1000,
    COMBAT_REASON_CODES,
    CREATURE_OUTCOMES,
    DECISION_DEADLINE_MS,
    FLEE_FORMULA_REF,
    FORMATION_SLOTS,
    INJURY_BRUISES,
    INJURY_DEEP_WOUNDS,
    INJURY_SEVERE_TRAUMA,
    LOOT_DRAW_CAP,
    MODEL_ID,
    COMBAT_PROMPT_ID,
    OPTION_CANDIDATE_CAP,
    PARTY_MAX_MEMBERS,
    RECENT_TURNS_CAP,
    RESIDENT_OUTCOMES,
    REVIVE_FORMULA_REF,
    ROLL_CAP_PER_TURN,
    ROUND_CAP,
    STATUS_INSTANCE_CAP,
    WEAR_ARMOR_PER_HIT_Q1000,
    WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000,
    WEAR_WEAPON_PER_USE_Q1000,
    ActionKind,
    CombatantKind,
    CombatantState,
    DefeatOutcome,
    EncounterState,
    EndCondition,
    FallbackReason,
    HpBucket,
    Phase,
    Side,
    SkipReason,
    StatusCategory,
    StackingPolicy,
    TriggerSource,
    TurnStatus,
    hp_bucket_of,
)
from .decisions import (
    CombatDecisionOutcome,
    CombatDecisionService,
    CombatModelProvider,
    DecisionError,
    ModelTimeoutError,
    ProviderUnavailableError,
    ReplayRecord,
    RequestCancelledError,
    build_decision_context,
    context_hash_of,
    tactical_fallback,
)
from .endings import (
    CombatantFinal,
    EndingError,
    evaluate_end_conditions,
    map_defeat_outcomes,
)
from .engine import (
    ADJACENT_SLOTS,
    CombatEngine,
    CombatEngineError,
    Encounter,
    LegalCombatOption,
    LegalTargetSet,
    NegotiationDecision,
)
from .formulas import (
    FORMULA_REGISTRY,
    FormulaError,
    FormulaOutcome,
    TargetOutcome,
    crit_permille,
    defend_reduced,
    flee_permille,
    healing_amount,
    hit_permille,
    magical_damage,
    physical_damage,
    resolve_formula,
)
from .loot import (
    CURRENCY_ITEM_DEFINITION_ID,
    CombatEconPort,
    LootDrop,
    LootEntry,
    LootError,
    LootOutcome,
    LootTableRegistry,
    NegotiationYield,
    WearLedger,
    WearSettlement,
    roll_loot,
)
from .rng import CombatRngHub, DeterministicRandomStream, RandomStreamError, RollRecord
from .sheets import (
    ATTRIBUTE_NAMES,
    CombatantSheet,
    CreatureTemplate,
    SheetError,
    Stats,
    clamp_attribute,
    derive_combatant_sheet,
)
from .status import (
    StatusDefinition,
    StatusError,
    StatusInstance,
    StatusRegistry,
    StatusStore,
    build_default_statuses,
)
from .ui import build_encounter_view, get_command_outcome

__all__ = [name for name in dir() if not name.startswith("_")]

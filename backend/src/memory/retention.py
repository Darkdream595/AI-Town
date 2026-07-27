"""
重要度、衰减、遗忘与再激活

符合 DOC-MEMORY-005：
- v1 整日 retention factor table
- strength_q1000 = floor(base * factor / 1000)
- RULE-MEMORY-034：只使用 GameTime 整日差；Pause/关闭/现实离线不产生 decay
- RULE-MEMORY-036：单事件绝对 delta≤100，clamp 0..1000
- RULE-MEMORY-040：tombstone 不可恢复
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

RETENTION_VERSION = "memory-retention/v1"

GAME_MINUTES_PER_DAY = 1440

#: 冷移阈值（DOC-MEMORY-005 §3）
COLD_THRESHOLD_Q1000 = 250

#: Reactivation trigger 阈值
REACTIVATION_THRESHOLD_Q1000 = 700

#: 单次 reactivation 上限
MAX_REACTIVATIONS_PER_TRIGGER = 4


class RetentionClass(str, Enum):
    ROUTINE = "routine"
    NORMAL = "normal"
    SIGNIFICANT = "significant"
    CORE = "core"
    PINNED = "pinned"


#: v1 整日 retention factor table（DES-MEMORY-005）
#: (max_elapsed_days, {retention_class: factor_q1000})
RETENTION_FACTOR_TABLE: tuple[tuple[int, dict[RetentionClass, int]], ...] = (
    (0, {RetentionClass.ROUTINE: 1000, RetentionClass.NORMAL: 1000, RetentionClass.SIGNIFICANT: 1000, RetentionClass.CORE: 1000, RetentionClass.PINNED: 1000}),
    (3, {RetentionClass.ROUTINE: 750, RetentionClass.NORMAL: 900, RetentionClass.SIGNIFICANT: 970, RetentionClass.CORE: 1000, RetentionClass.PINNED: 1000}),
    (7, {RetentionClass.ROUTINE: 500, RetentionClass.NORMAL: 750, RetentionClass.SIGNIFICANT: 920, RetentionClass.CORE: 1000, RetentionClass.PINNED: 1000}),
    (30, {RetentionClass.ROUTINE: 250, RetentionClass.NORMAL: 500, RetentionClass.SIGNIFICANT: 820, RetentionClass.CORE: 980, RetentionClass.PINNED: 1000}),
    (90, {RetentionClass.ROUTINE: 100, RetentionClass.NORMAL: 250, RetentionClass.SIGNIFICANT: 700, RetentionClass.CORE: 950, RetentionClass.PINNED: 1000}),
)
RETENTION_FACTOR_91_PLUS: dict[RetentionClass, int] = {
    RetentionClass.ROUTINE: 50,
    RetentionClass.NORMAL: 100,
    RetentionClass.SIGNIFICANT: 600,
    RetentionClass.CORE: 900,
    RetentionClass.PINNED: 1000,
}


def retention_factor_q1000(retention_class: RetentionClass, elapsed_game_days: int) -> int:
    """整日 retention factor 查表"""
    for max_days, row in RETENTION_FACTOR_TABLE:
        if elapsed_game_days <= max_days:
            return row[retention_class]
    return RETENTION_FACTOR_91_PLUS[retention_class]


def compute_strength_q1000(base_importance_q1000: int, factor_q1000: int) -> int:
    """strength = floor(base * factor / 1000)（RULE-MEMORY-037：派生值，不写回）"""
    return (base_importance_q1000 * factor_q1000) // 1000


def apply_importance_delta(current_importance_q1000: int, delta: int) -> int:
    """importance 变化：单事件绝对 delta≤100，clamp 0..1000（RULE-MEMORY-036）"""
    clamped_delta = max(-100, min(100, delta))
    return max(0, min(1000, current_importance_q1000 + clamped_delta))


@dataclass(frozen=True)
class RetentionDecision:
    """retention 评估结果"""

    memory_id: str
    elapsed_game_days: int
    factor_q1000: int
    strength_q1000: int
    should_move_to_cold: bool
    skip_reason: Optional[str]


def evaluate_retention(
    memory_id: str,
    retention_class: RetentionClass,
    base_importance_q1000: int,
    last_strength_anchor_game_time: int,
    current_game_time: int,
    is_active: bool,
    legal_hold: bool = False,
) -> RetentionDecision:
    """
    retention 评估

    - pinned/core 不自动 cold（RULE-MEMORY-035）
    - legal_hold 跳过
    - strength<250 且非 protected 时可进入 cold
    """
    if current_game_time < last_strength_anchor_game_time:
        raise ValueError("MEMORY_RETENTION_TIME_INVALID: GameTime 倒退")

    elapsed_days = (current_game_time - last_strength_anchor_game_time) // GAME_MINUTES_PER_DAY
    factor = retention_factor_q1000(retention_class, elapsed_days)
    strength = compute_strength_q1000(base_importance_q1000, factor)

    if legal_hold:
        return RetentionDecision(memory_id, elapsed_days, factor, strength, False, "legal_hold")
    if retention_class in (RetentionClass.CORE, RetentionClass.PINNED):
        return RetentionDecision(memory_id, elapsed_days, factor, strength, False, "protected_class")
    if not is_active:
        return RetentionDecision(memory_id, elapsed_days, factor, strength, False, "not_active")

    return RetentionDecision(
        memory_id=memory_id,
        elapsed_game_days=elapsed_days,
        factor_q1000=factor,
        strength_q1000=strength,
        should_move_to_cold=strength < COLD_THRESHOLD_Q1000,
        skip_reason=None,
    )


@dataclass(frozen=True)
class TombstoneAudit:
    """tombstone 审计（DOC-MEMORY-005 §4）"""

    reason: str  # invalid_source/duplicate_record/authorized_admin_correction/migration_redaction
    source_event_id: str
    payload_hash: str
    tombstoned_at_revision: int


ALLOWED_TOMBSTONE_REASONS: frozenset[str] = frozenset(
    {"invalid_source", "duplicate_record", "authorized_admin_correction", "migration_redaction"}
)


class TombstoneStateError(Exception):
    """tombstone 不可恢复为 active（RULE-MEMORY-040）"""


class MemoryStateMachine:
    """
    记忆状态机（DOC-MEMORY-005 §6）

    active -> cold
    cold -> reactivated
    reactivated -> active/cold
    active/cold/reactivated -> tombstoned
    tombstoned -> terminal
    """

    EDGES: dict[str, frozenset[str]] = {
        "active": frozenset({"cold", "tombstoned"}),
        "cold": frozenset({"reactivated", "tombstoned"}),
        "reactivated": frozenset({"active", "cold", "tombstoned"}),
        "tombstoned": frozenset(),
    }

    @classmethod
    def can_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.EDGES.get(from_state, frozenset())

    @classmethod
    def transition(cls, from_state: str, to_state: str) -> str:
        if not cls.can_transition(from_state, to_state):
            raise TombstoneStateError(f"非法记忆状态迁移: {from_state} -> {to_state}")
        return to_state

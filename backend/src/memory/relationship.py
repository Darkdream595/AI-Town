"""
五维有向关系模型

符合 DOC-MEMORY-006：
- 五维 affection/trust/fear/respect/intimacy，各 -100..100（RULE-MEMORY-042）
- 每维限幅 20、五维合计限幅 40（RULE-MEMORY-047）
- 缩放与余量按 trust,affection,fear,respect,intimacy 顺序循环分配
- 同一 (edge_id, source_event_id, rule_version) 最多应用一次（RULE-MEMORY-046）
"""

from __future__ import annotations

from dataclasses import dataclass, field

RELATIONSHIP_DELTA_VERSION = "relationship-delta/v1"

#: 五维（schema 顺序）
DIMENSIONS: tuple[str, ...] = ("affection", "trust", "fear", "respect", "intimacy")

#: 余量循环分配顺序（DES-MEMORY-006 §4）
DISTRIBUTION_ORDER: tuple[str, ...] = ("trust", "affection", "fear", "respect", "intimacy")

DIMENSION_MIN = -100
DIMENSION_MAX = 100
BASE_DELTA_LIMIT = 20
TOTAL_DELTA_LIMIT = 40


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _truncate_toward_zero(numerator: int, denominator: int) -> int:
    """整数除法向零取整（不用浮点，RULE-MEMORY-045）"""
    quotient = abs(numerator) // denominator
    return quotient if numerator >= 0 else -quotient


@dataclass(frozen=True)
class RelationshipVector:
    """五维关系向量"""

    affection: int = 0
    trust: int = 0
    fear: int = 0
    respect: int = 0
    intimacy: int = 0

    def __post_init__(self) -> None:
        for dimension in DIMENSIONS:
            value = getattr(self, dimension)
            if not DIMENSION_MIN <= value <= DIMENSION_MAX:
                raise ValueError(f"维度 {dimension} 越界: {value}")

    def as_dict(self) -> dict[str, int]:
        return {dimension: getattr(self, dimension) for dimension in DIMENSIONS}

    def with_value(self, dimension: str, value: int) -> "RelationshipVector":
        return RelationshipVector(**{**self.as_dict(), dimension: value})


@dataclass(frozen=True)
class RelationshipDeltaSet:
    """单事件五维 delta（base_delta 各 -20..20）"""

    base_deltas: dict[str, int]
    interpretation_q1000: int  # -1000..1000

    def __post_init__(self) -> None:
        if not -1000 <= self.interpretation_q1000 <= 1000:
            raise ValueError(f"interpretation 越界: {self.interpretation_q1000}")
        for dimension, base in self.base_deltas.items():
            if dimension not in DIMENSIONS:
                raise ValueError(f"未知维度: {dimension}")
            if not -BASE_DELTA_LIMIT <= base <= BASE_DELTA_LIMIT:
                raise ValueError(f"base_delta 越界: {dimension}={base}")


@dataclass(frozen=True)
class EvidenceEntry:
    """证据条目：source event、dimension、base/interpretation/applied、rule version"""

    source_event_id: str
    dimension: str
    base_delta: int
    interpretation_q1000: int
    applied_delta: int
    rule_version: str


def compute_applied_deltas(
    current: RelationshipVector,
    delta_set: RelationshipDeltaSet,
) -> tuple[RelationshipVector, dict[str, int]]:
    """
    应用 delta（DES-MEMORY-006 §4）

    返回 (next_vector, applied_deltas)。
    五维 applied delta 绝对值之和永不超过 40。
    """
    pre_applied: dict[str, int] = {}
    for dimension in DIMENSIONS:
        base = delta_set.base_deltas.get(dimension, 0)
        interpreted = _truncate_toward_zero(base * delta_set.interpretation_q1000, 1000)
        limited = _clamp(interpreted, -BASE_DELTA_LIMIT, BASE_DELTA_LIMIT)
        current_value = getattr(current, dimension)
        pre_next = _clamp(current_value + limited, DIMENSION_MIN, DIMENSION_MAX)
        pre_applied[dimension] = pre_next - current_value

    sum_abs = sum(abs(value) for value in pre_applied.values())
    if sum_abs <= TOTAL_DELTA_LIMIT:
        applied = dict(pre_applied)
    else:
        # 每维先按比例向零取整
        applied = {
            dimension: _truncate_toward_zero(value * TOTAL_DELTA_LIMIT, sum_abs)
            for dimension, value in pre_applied.items()
        }
        # 未分配的绝对单位按 DISTRIBUTION_ORDER 循环分配
        remaining = TOTAL_DELTA_LIMIT - sum(abs(value) for value in applied.values())
        while remaining > 0:
            progressed = False
            for dimension in DISTRIBUTION_ORDER:
                if remaining <= 0:
                    break
                target = pre_applied[dimension]
                if abs(applied[dimension]) < abs(target):
                    sign = 1 if target > 0 else -1
                    applied[dimension] += sign
                    remaining -= 1
                    progressed = True
            if not progressed:
                break

    next_vector = RelationshipVector(
        **{
            dimension: getattr(current, dimension) + applied[dimension]
            for dimension in DIMENSIONS
        }
    )
    return next_vector, applied


@dataclass
class RelationshipEdge:
    """有向关系边（A→B 与 B→A 独立，RULE-MEMORY-043）"""

    edge_id: str
    world_id: str
    source_resident_id: str
    target_resident_id: str
    vector: RelationshipVector = field(default_factory=RelationshipVector)
    edge_revision: int = 1
    last_source_event_id: str | None = None
    state: str = "active"  # active | archived
    _applied_event_keys: set[str] = field(default_factory=set)


class DuplicateEffectError(Exception):
    """MEMORY_RELATIONSHIP_DUPLICATE_EFFECT"""


def apply_relationship_event(
    edge: RelationshipEdge,
    source_event_id: str,
    delta_set: RelationshipDeltaSet,
    expected_edge_revision: int | None = None,
) -> tuple[RelationshipVector, list[EvidenceEntry]]:
    """
    应用事件 delta（幂等：同 (edge_id, source_event_id, rule_version) 最多一次）

    返回 (新向量, evidence entries)。
    """
    event_key = f"{edge.edge_id}:{source_event_id}:{RELATIONSHIP_DELTA_VERSION}"
    if event_key in edge._applied_event_keys:
        raise DuplicateEffectError(f"事件 {source_event_id} 已应用于 edge {edge.edge_id}")

    if expected_edge_revision is not None and expected_edge_revision != edge.edge_revision:
        raise ValueError(
            f"MEMORY_RELATIONSHIP_STALE: expected={expected_edge_revision} actual={edge.edge_revision}"
        )

    next_vector, applied = compute_applied_deltas(edge.vector, delta_set)
    evidence = [
        EvidenceEntry(
            source_event_id=source_event_id,
            dimension=dimension,
            base_delta=delta_set.base_deltas.get(dimension, 0),
            interpretation_q1000=delta_set.interpretation_q1000,
            applied_delta=applied[dimension],
            rule_version=RELATIONSHIP_DELTA_VERSION,
        )
        for dimension in DIMENSIONS
        if applied[dimension] != 0
    ]

    edge.vector = next_vector
    edge.edge_revision += 1
    edge.last_source_event_id = source_event_id
    edge._applied_event_keys.add(event_key)
    return next_vector, evidence

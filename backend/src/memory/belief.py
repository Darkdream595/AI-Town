"""
信念与客观事实分离 + Reconciliation

符合 DOC-MEMORY-010：
- knowledge_state 封闭为 unknown/believed/disbelieved/contradicted
- RULE-MEMORY-081：没有 belief 时为 unknown，不从客观状态反推
- RULE-MEMORY-083：同一 predicate/subject 可有多个互相矛盾 belief
- Reconciliation v1 公式；每个 evidence event 只应用一次
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class KnowledgeState(str, Enum):
    UNKNOWN = "unknown"
    BELIEVED = "believed"
    DISBELIEVED = "disbelieved"
    CONTRADICTED = "contradicted"


class EvidenceKind(str, Enum):
    DIRECT_OBSERVATION_SUPPORTING = "direct_observation_supporting"
    DIRECT_OBSERVATION_CONTRADICTING = "direct_observation_contradicting"
    TESTIMONY_SUPPORTING = "testimony_supporting"
    TESTIMONY_CONTRADICTING = "testimony_contradicting"


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def reconciliation_delta(evidence_kind: EvidenceKind, source_confidence_q1000: int = 0) -> int:
    """
    Reconciliation v1（DES-MEMORY-010）

    direct observation supporting: +200
    direct observation contradicting: -300
    authorized testimony supporting: +floor(source/10), max +100
    authorized testimony contradicting: -floor(source/10), max -100
    """
    if evidence_kind == EvidenceKind.DIRECT_OBSERVATION_SUPPORTING:
        return 200
    if evidence_kind == EvidenceKind.DIRECT_OBSERVATION_CONTRADICTING:
        return -300
    testimony_delta = min(100, source_confidence_q1000 // 10)
    if evidence_kind == EvidenceKind.TESTIMONY_SUPPORTING:
        return testimony_delta
    return -testimony_delta


@dataclass
class SemanticBeliefState:
    """单条 SemanticBelief 的调和状态"""

    belief_id: str
    claim_key: str  # predicate_id + subject_ref
    confidence_q1000: int
    state: KnowledgeState = KnowledgeState.BELIEVED
    contradiction_ids: list[str] = field(default_factory=list)
    _applied_evidence_ids: set[str] = field(default_factory=set)


class DuplicateEvidenceError(Exception):
    """同一 evidence event 重复应用"""


def reconcile_belief(
    belief: SemanticBeliefState,
    source_event_id: str,
    evidence_kind: EvidenceKind,
    source_confidence_q1000: int = 0,
) -> int:
    """
    调和 belief（RULE-MEMORY-084：按 source event 幂等）

    返回新 confidence。达到 0 不删除 belief；标为 disbelieved 并保留 provenance。
    """
    if source_event_id in belief._applied_evidence_ids:
        raise DuplicateEvidenceError(f"evidence {source_event_id} 已应用")

    delta = reconciliation_delta(evidence_kind, source_confidence_q1000)
    belief.confidence_q1000 = clamp(belief.confidence_q1000 + delta, 0, 1000)
    belief._applied_evidence_ids.add(source_event_id)

    if belief.confidence_q1000 == 0:
        belief.state = KnowledgeState.DISBELIEVED
    elif evidence_kind in (
        EvidenceKind.DIRECT_OBSERVATION_CONTRADICTING,
        EvidenceKind.TESTIMONY_CONTRADICTING,
    ) and belief.contradiction_ids:
        belief.state = KnowledgeState.CONTRADICTED
    elif belief.confidence_q1000 > 0:
        belief.state = KnowledgeState.BELIEVED
    return belief.confidence_q1000


def query_knowledge_state(beliefs: list[SemanticBeliefState], claim_key: str) -> KnowledgeState:
    """
    actor 对 claim 的知识状态（RULE-MEMORY-081/083）

    没有 belief 时为 unknown；多条矛盾 belief 为 contradicted。
    """
    matching = [belief for belief in beliefs if belief.claim_key == claim_key]
    if not matching:
        return KnowledgeState.UNKNOWN
    has_contradiction = any(belief.contradiction_ids for belief in matching) or len(matching) > 1
    if has_contradiction:
        return KnowledgeState.CONTRADICTED
    return matching[0].state

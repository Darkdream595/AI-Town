"""
记忆巩固、摘要与冷热分层

符合 DOC-MEMORY-004：
- v1 可合并条件（同 world/owner/policy/kind、低重要度、≥3 条、≤7 日窗、tag Jaccard≥700、无 protected）
- RULE-MEMORY-028：摘要 AccessPolicy 必须与全部来源相同
- RULE-MEMORY-029：Commitment、importance≥600、pinned、shared_secret、legal-hold 永不自动巩固
- RULE-MEMORY-031：同一 lineage hash 最多生成一个 summary
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

CONSOLIDATION_VERSION = "memory-consolidation/v1"

MIN_SOURCE_RECORDS = 3
MAX_SOURCE_RECORDS = 64
MAX_WINDOW_GAME_MINUTES = 7 * 1440
CONSOLIDATION_IMPORTANCE_LIMIT = 600
CONSOLIDATION_JACCARD_THRESHOLD = 700

#: 受保护 semantic tags（DOC-MEMORY-004 §4.6）
PROTECTED_TAGS: frozenset[str] = frozenset(
    {
        "consequence.trauma",
        "consequence.life_saving",
        "consequence.major_betrayal",
        "pinned",
    }
)


class ConsolidationState(str, Enum):
    """batch 状态机"""

    PLANNED = "planned"
    SUMMARIZING = "summarizing"
    COMMITTING = "committing"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


CONSOLIDATION_EDGES: dict[ConsolidationState, frozenset[ConsolidationState]] = {
    ConsolidationState.PLANNED: frozenset({ConsolidationState.SUMMARIZING, ConsolidationState.FAILED}),
    ConsolidationState.SUMMARIZING: frozenset({ConsolidationState.COMMITTING, ConsolidationState.FAILED}),
    ConsolidationState.COMMITTING: frozenset({ConsolidationState.COMPLETED, ConsolidationState.RECOVERY_REQUIRED}),
    ConsolidationState.RECOVERY_REQUIRED: frozenset({ConsolidationState.COMPLETED, ConsolidationState.FAILED}),
    ConsolidationState.COMPLETED: frozenset(),
    ConsolidationState.FAILED: frozenset(),
}


@dataclass(frozen=True)
class ConsolidationSourceMetadata:
    """参与巩固判定的 source metadata"""

    memory_id: str
    world_id: str
    memory_owner_id: str
    access_policy_id: str
    memory_kind: str
    importance_q1000: int
    state: str
    created_at_game_time: int
    semantic_tags: frozenset[str]
    record_hash: str
    legal_hold: bool = False
    is_shared_secret: bool = False
    has_accepted_commitment: bool = False


def check_consolidation_eligibility(
    sources: list[ConsolidationSourceMetadata],
) -> tuple[bool, Optional[str]]:
    """
    v1 可合并条件（DES-MEMORY-004 §4）；返回 (eligible, reject_reason)
    """
    if not MIN_SOURCE_RECORDS <= len(sources) <= MAX_SOURCE_RECORDS:
        return False, f"source 数量 {len(sources)} 不在 [{MIN_SOURCE_RECORDS},{MAX_SOURCE_RECORDS}]"

    first = sources[0]
    for source in sources:
        if (
            source.world_id != first.world_id
            or source.memory_owner_id != first.memory_owner_id
            or source.access_policy_id != first.access_policy_id
            or source.memory_kind != first.memory_kind
        ):
            return False, "MEMORY_POLICY_MISMATCH: world/owner/policy/kind 必须一致"
        if source.memory_kind not in ("episodic_memory", "social_impression"):
            return False, f"kind {source.memory_kind} 不可巩固"
        if source.importance_q1000 >= CONSOLIDATION_IMPORTANCE_LIMIT:
            return False, f"importance≥{CONSOLIDATION_IMPORTANCE_LIMIT} 永不自动巩固"
        if source.state != "active":
            return False, "仅 active 记录可巩固"
        if source.legal_hold or source.is_shared_secret or source.has_accepted_commitment:
            return False, "legal hold/shared_secret/accepted commitment 受保护"
        if source.semantic_tags & PROTECTED_TAGS:
            return False, "含受保护 tag（trauma/救命/背叛/pinned）"

    start = min(source.created_at_game_time for source in sources)
    end = max(source.created_at_game_time for source in sources)
    if end - start > MAX_WINDOW_GAME_MINUTES:
        return False, "GameTime 窗口超过 7 日"

    return True, None


def compute_lineage_hash(
    source_memory_ids: list[str], source_record_hashes: list[str], algorithm_version: str = CONSOLIDATION_VERSION
) -> str:
    """Lineage Hash：source ID + source record hash + algorithm version 的 canonical SHA-256"""
    canonical = json_canonical(source_memory_ids, source_record_hashes, algorithm_version)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def json_canonical(ids: list[str], hashes: list[str], version: str) -> str:
    pairs = sorted(zip(ids, hashes))
    return version + "\n" + "\n".join(f"{memory_id}:{record_hash}" for memory_id, record_hash in pairs)


@dataclass
class ConsolidationLedger:
    """lineage hash 幂等台账（RULE-MEMORY-031）"""

    _summaries: dict[str, str] = field(default_factory=dict)  # lineage_hash -> summary_memory_id

    def register_summary(self, lineage_hash: str, summary_memory_id: str) -> str:
        """同一 lineage hash 最多生成一个 summary；重放返回原 summary ID"""
        existing = self._summaries.get(lineage_hash)
        if existing is not None:
            return existing
        self._summaries[lineage_hash] = summary_memory_id
        return summary_memory_id

    def replay(self, lineage_hash: str) -> Optional[str]:
        return self._summaries.get(lineage_hash)

"""
记忆写入资格、幂等与生命周期

符合 DOC-MEMORY-002：
- RULE-MEMORY-009/010：来源资格（Proposal/模型文本/未提交内容永不具备写入资格）
- RULE-MEMORY-011：direct observation 必须有感知证据
- RULE-MEMORY-012/013：write key 幂等与冲突
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

WRITE_RULE_VERSION = "memory-write/v1"

#: 具备写入资格的 source_kind（RULE-MEMORY-009）
ELIGIBLE_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "domain_event",
        "direct_observation",
        "testimony",
        "inference",
        "self_commitment",
        "routine_training",
    }
)


class Eligibility(str, Enum):
    """写入资格判定"""

    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class WriteLifecycle(str, Enum):
    """写入生命周期：proposed -> eligible -> committed | rejected；proposed -> deferred -> eligible"""

    PROPOSED = "proposed"
    ELIGIBLE = "eligible"
    COMMITTED = "committed"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class MemoryWriteCandidate:
    """MemoryWriteCandidateV1（DES-MEMORY-002）"""

    candidate_id: str
    world_id: str
    memory_owner_id: str
    memory_kind: str
    source_kind: str
    source_event_ids: tuple[str, ...]
    source_memory_ids: tuple[str, ...]
    observed_revision: int
    observed_game_time: int
    observation_evidence: Optional[dict[str, Any]]
    write_rule_version: str = WRITE_RULE_VERSION


@dataclass(frozen=True)
class EligibilityResult:
    """资格判定结果"""

    eligibility: Eligibility
    reason_code: Optional[str]
    write_key: str


def compute_write_key(candidate: MemoryWriteCandidate) -> str:
    """
    Write Key canonical tuple（DES-MEMORY-002）：UTF-8 编码后 lowercase SHA-256

    world_id \n owner \n kind \n source_kind \n sort(event_ids) \n sort(memory_ids) \n rule_version
    """
    canonical = (
        candidate.world_id
        + "\n"
        + candidate.memory_owner_id
        + "\n"
        + candidate.memory_kind
        + "\n"
        + candidate.source_kind
        + "\n"
        + ",".join(sorted(candidate.source_event_ids))
        + "\n"
        + ",".join(sorted(candidate.source_memory_ids))
        + "\n"
        + candidate.write_rule_version
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_candidate_hash(candidate: MemoryWriteCandidate) -> str:
    """canonical candidate hash（RULE-MEMORY-013 冲突检测用）"""
    canonical = "|".join(
        [
            candidate.candidate_id,
            candidate.world_id,
            candidate.memory_owner_id,
            candidate.memory_kind,
            candidate.source_kind,
            ",".join(sorted(candidate.source_event_ids)),
            ",".join(sorted(candidate.source_memory_ids)),
            str(candidate.observed_revision),
            candidate.write_rule_version,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_write_eligibility(
    candidate: MemoryWriteCandidate,
    committed_event_ids: frozenset[str],
    access_policy_resolvable: bool = True,
) -> EligibilityResult:
    """
    写入资格判定

    - committed_event_ids：已提交 DomainEvent 集合（来源必须是已提交事件）
    - access_policy_resolvable：AccessPolicy 可唯一计算（RULE-MEMORY-016）
    """
    write_key = compute_write_key(candidate)

    if candidate.write_rule_version != WRITE_RULE_VERSION:
        return EligibilityResult(Eligibility.REJECTED, "MEMORY_WRITE_RULE_VERSION_UNKNOWN", write_key)

    if candidate.source_kind not in ELIGIBLE_SOURCE_KINDS:
        return EligibilityResult(Eligibility.REJECTED, "MEMORY_SOURCE_NOT_COMMITTED", write_key)

    if not candidate.source_event_ids and not candidate.source_memory_ids:
        return EligibilityResult(Eligibility.REJECTED, "MEMORY_PROVENANCE_MISSING", write_key)

    # 来源事件必须已提交
    for event_id in candidate.source_event_ids:
        if event_id not in committed_event_ids:
            return EligibilityResult(Eligibility.REJECTED, "MEMORY_SOURCE_NOT_COMMITTED", write_key)

    # direct observation 必须有感知证据（RULE-MEMORY-011）
    if candidate.source_kind == "direct_observation":
        evidence = candidate.observation_evidence
        if evidence is None:
            return EligibilityResult(Eligibility.REJECTED, "MEMORY_OBSERVATION_UNPROVEN", write_key)
        if not evidence.get("sense_modes") or evidence.get("observer_id") != candidate.memory_owner_id:
            return EligibilityResult(Eligibility.REJECTED, "MEMORY_OBSERVATION_UNPROVEN", write_key)

    # AccessPolicy 无法唯一计算时 deferred，禁止先 public 写入后补权限（RULE-MEMORY-016）
    if not access_policy_resolvable:
        return EligibilityResult(Eligibility.DEFERRED, "MEMORY_ACCESS_POLICY_UNRESOLVED", write_key)

    return EligibilityResult(Eligibility.ELIGIBLE, None, write_key)


class WriteKeyConflictError(Exception):
    """MEMORY_WRITE_CONFLICT（RULE-MEMORY-013）"""


@dataclass
class CommittedWrite:
    """幂等写入结果"""

    write_key: str
    candidate_hash: str
    memory_id: str
    event_id: str


@dataclass
class WriteKeyStore:
    """(world_id, write_key) 幂等存储；重放返回原结果（RULE-MEMORY-012）"""

    _store: dict[tuple[str, str], CommittedWrite] = field(default_factory=dict)

    def commit(
        self,
        world_id: str,
        write_key: str,
        candidate_hash: str,
        memory_id: str,
        event_id: str,
    ) -> CommittedWrite:
        key = (world_id, write_key)
        existing = self._store.get(key)
        if existing is not None:
            if existing.candidate_hash != candidate_hash:
                raise WriteKeyConflictError(f"write key {write_key} 幂等冲突")
            return existing
        record = CommittedWrite(
            write_key=write_key,
            candidate_hash=candidate_hash,
            memory_id=memory_id,
            event_id=event_id,
        )
        self._store[key] = record
        return record

    def replay(self, world_id: str, write_key: str) -> Optional[CommittedWrite]:
        """重放查询；返回原 memory ID 和 event ID 或 None"""
        return self._store.get((world_id, write_key))

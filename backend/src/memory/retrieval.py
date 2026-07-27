"""
相关记忆检索、评分与输出预算

符合 DOC-MEMORY-003：
- 七分量整数公式，总权重恰为 1000（RULE-MEMORY-020）
- Recency / Commitment urgency 查表
- 同分 tie-break：importance desc / created_at_game_time desc / memory_id asc
- commitment 保留槽 + record_limit + UTF-8 byte limit（RULE-MEMORY-021/022）
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

RETRIEVAL_SCORE_VERSION = "memory-retrieval-score/v1"

#: 七分量权重（DES-MEMORY-003），总和恰为 1000
WEIGHT_SEMANTIC = 300
WEIGHT_GOAL = 180
WEIGHT_PARTICIPANT = 120
WEIGHT_EMOTION = 80
WEIGHT_IMPORTANCE = 120
WEIGHT_COMMITMENT = 120
WEIGHT_RECENCY = 80

#: Recency table：整游戏日 -> q1000
RECENCY_TABLE: tuple[tuple[int, int], ...] = (
    (0, 1000),
    (1, 900),
    (3, 750),
    (7, 550),
    (30, 300),
    (90, 150),
)
RECENCY_FLOOR = 50

#: Commitment urgency table（仅 status=accepted 应用）
COMMITMENT_OVERDUE_OR_WITHIN_24MIN = 1000
COMMITMENT_WITHIN_1_DAY = 800
COMMITMENT_WITHIN_3_DAYS = 500
COMMITMENT_FARTHER = 250
COMMITMENT_NO_DEADLINE = 300

GAME_MINUTES_PER_DAY = 1440


def recency_q1000(elapsed_game_days: int) -> int:
    """recency 查表"""
    for max_days, value in RECENCY_TABLE:
        if elapsed_game_days <= max_days:
            return value
    return RECENCY_FLOOR


def commitment_urgency_q1000(
    status: str, deadline_game_time: Optional[int], current_game_time: int
) -> int:
    """commitment urgency 查表；非 accepted 一律 0"""
    if status != "accepted":
        return 0
    if deadline_game_time is None:
        return COMMITMENT_NO_DEADLINE
    remaining = deadline_game_time - current_game_time
    if remaining <= 24:
        return COMMITMENT_OVERDUE_OR_WITHIN_24MIN
    if remaining <= GAME_MINUTES_PER_DAY:
        return COMMITMENT_WITHIN_1_DAY
    if remaining <= 3 * GAME_MINUTES_PER_DAY:
        return COMMITMENT_WITHIN_3_DAYS
    return COMMITMENT_FARTHER


def weighted_jaccard_q1000(
    query_tags: frozenset[str], record_tags: frozenset[str], tag_weights: Optional[dict[str, int]] = None
) -> int:
    """versioned tag weight 的加权 Jaccard；空并集为 0（纯整数）"""
    if not query_tags and not record_tags:
        return 0
    weights = tag_weights or {}

    def weight(tag: str) -> int:
        return weights.get(tag, 1000)

    intersection_weight = sum(weight(tag) for tag in query_tags & record_tags)
    union_weight = sum(weight(tag) for tag in query_tags | record_tags)
    if union_weight == 0:
        return 0
    return (intersection_weight * 1000) // union_weight


def participant_match_q1000(
    query_participant_ids: frozenset[str], record_participant_ids: frozenset[str]
) -> int:
    """交集数/查询 participant 数，查询为空则 0"""
    if not query_participant_ids:
        return 0
    matched = len(query_participant_ids & record_participant_ids)
    return (matched * 1000) // len(query_participant_ids)


def emotion_match_q1000(
    query_emotion_id: Optional[str], record_emotion_id: Optional[str], compatible_groups: Optional[dict[str, frozenset[str]]] = None
) -> int:
    """相同 emotion=1000，兼容组=500，否则 0；查询无 emotion 则为 0"""
    if query_emotion_id is None or record_emotion_id is None:
        return 0
    if query_emotion_id == record_emotion_id:
        return 1000
    groups = compatible_groups or {}
    group = groups.get(query_emotion_id, frozenset())
    if record_emotion_id in group:
        return 500
    return 0


@dataclass(frozen=True)
class ComponentScores:
    """七分量（全为 0..1000 整数）"""

    semantic_match_q1000: int
    goal_match_q1000: int
    participant_match_q1000: int
    emotion_match_q1000: int
    importance_q1000: int
    commitment_urgency_q1000: int
    recency_q1000: int


def compute_score_q1000(components: ComponentScores) -> int:
    """总分整数公式（RULE-MEMORY-020）：floor(sum(component*weight)/1000)"""
    return (
        components.semantic_match_q1000 * WEIGHT_SEMANTIC
        + components.goal_match_q1000 * WEIGHT_GOAL
        + components.participant_match_q1000 * WEIGHT_PARTICIPANT
        + components.emotion_match_q1000 * WEIGHT_EMOTION
        + components.importance_q1000 * WEIGHT_IMPORTANCE
        + components.commitment_urgency_q1000 * WEIGHT_COMMITMENT
        + components.recency_q1000 * WEIGHT_RECENCY
    ) // 1000


@dataclass(frozen=True)
class RetrievalLimits:
    """输出预算（DES-MEMORY-003 limits）"""

    candidate_limit: int = 128
    record_limit: int = 16
    commitment_limit: int = 4
    utf8_byte_limit: int = 12288


@dataclass
class RetrievalCandidate:
    """metadata candidate（ACL allow 后）"""

    memory_id: str
    memory_kind: str
    semantic_tags: frozenset[str]
    participant_ids: frozenset[str]
    emotion_id: Optional[str]
    importance_q1000: int
    created_at_game_time: int
    last_reactivated_game_time: Optional[int]
    commitment_status: Optional[str] = None
    commitment_deadline: Optional[int] = None
    access_decision_id: str = ""
    source_revision: int = 0
    authorized_payload: Optional[dict[str, Any]] = None


@dataclass
class RetrievedRecord:
    """输出记录（DES-MEMORY-003 §4）"""

    memory_id: str
    kind: str
    authorized_payload: Optional[dict[str, Any]]
    score_q1000: int
    component_scores: ComponentScores
    source_revision: int
    access_decision_id: str


@dataclass
class AuthorizedMemoryContext:
    """AuthorizedMemoryContextV1"""

    records: list[RetrievedRecord]
    observed_revision: int
    index_revision: int
    query_hash: str
    result_hash: str
    truncated: bool


def build_component_scores(
    candidate: RetrievalCandidate,
    goal_tags: frozenset[str],
    concept_tags: frozenset[str],
    participant_ids: frozenset[str],
    emotion_id: Optional[str],
    current_game_time: int,
    tag_weights: Optional[dict[str, int]] = None,
    compatible_groups: Optional[dict[str, frozenset[str]]] = None,
) -> ComponentScores:
    """为单条 candidate 计算七分量"""
    anchor = max(
        candidate.created_at_game_time,
        candidate.last_reactivated_game_time or 0,
    )
    elapsed_days = max(0, (current_game_time - anchor) // GAME_MINUTES_PER_DAY)
    return ComponentScores(
        semantic_match_q1000=weighted_jaccard_q1000(concept_tags, candidate.semantic_tags, tag_weights),
        goal_match_q1000=weighted_jaccard_q1000(goal_tags, candidate.semantic_tags, tag_weights),
        participant_match_q1000=participant_match_q1000(participant_ids, candidate.participant_ids),
        emotion_match_q1000=emotion_match_q1000(emotion_id, candidate.emotion_id, compatible_groups),
        importance_q1000=candidate.importance_q1000,
        commitment_urgency_q1000=commitment_urgency_q1000(
            candidate.commitment_status or "",
            candidate.commitment_deadline,
            current_game_time,
        ),
        recency_q1000=recency_q1000(elapsed_days),
    )


def retrieve_authorized_memories(
    candidates: list[RetrievalCandidate],
    goal_tags: frozenset[str],
    concept_tags: frozenset[str],
    participant_ids: frozenset[str],
    emotion_id: Optional[str],
    current_game_time: int,
    observed_revision: int,
    index_revision: int,
    limits: Optional[RetrievalLimits] = None,
    tag_weights: Optional[dict[str, int]] = None,
    compatible_groups: Optional[dict[str, frozenset[str]]] = None,
) -> AuthorizedMemoryContext:
    """
    检索链（RULE-MEMORY-017..024）

    输入 candidates 必须已经过 ACL allow 且不含 tombstoned/cold。
    """
    resolved_limits = limits or RetrievalLimits()
    scored: list[tuple[RetrievalCandidate, ComponentScores, int]] = []
    for candidate in candidates[: resolved_limits.candidate_limit]:
        components = build_component_scores(
            candidate,
            goal_tags,
            concept_tags,
            participant_ids,
            emotion_id,
            current_game_time,
            tag_weights,
            compatible_groups,
        )
        scored.append((candidate, components, compute_score_q1000(components)))

    # 稳定排序：score desc / importance desc / created desc / memory_id asc（RULE-MEMORY-020）
    scored.sort(
        key=lambda entry: (
            -entry[2],
            -entry[0].importance_q1000,
            -entry[0].created_at_game_time,
            entry[0].memory_id,
        )
    )

    # 先保留 commitment 槽（RULE-MEMORY-021）：相关 accepted Commitment
    commitment_entries = [
        entry
        for entry in scored
        if entry[0].memory_kind == "commitment" and entry[0].commitment_status == "accepted"
    ][: resolved_limits.commitment_limit]
    commitment_ids = {entry[0].memory_id for entry in commitment_entries}

    remaining_entries = [entry for entry in scored if entry[0].memory_id not in commitment_ids]
    selected = commitment_entries + remaining_entries[: max(0, resolved_limits.record_limit - len(commitment_entries))]

    # 逐条 canonical UTF-8 byte limit（RULE-MEMORY-022）
    records: list[RetrievedRecord] = []
    used_bytes = 0
    truncated = False
    for candidate, components, score in selected:
        record = RetrievedRecord(
            memory_id=candidate.memory_id,
            kind=candidate.memory_kind,
            authorized_payload=candidate.authorized_payload,
            score_q1000=score,
            component_scores=components,
            source_revision=candidate.source_revision,
            access_decision_id=candidate.access_decision_id,
        )
        record_bytes = len(
            json.dumps(
                {
                    "memory_id": record.memory_id,
                    "kind": record.kind,
                    "score_q1000": record.score_q1000,
                    "authorized_payload": record.authorized_payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        )
        if used_bytes + record_bytes > resolved_limits.utf8_byte_limit:
            truncated = True
            continue
        used_bytes += record_bytes
        records.append(record)

    if len(records) < len(scored) and not truncated:
        truncated = len(selected) < len(scored)

    query_hash = hashlib.sha256(
        json.dumps(
            {
                "goal_tags": sorted(goal_tags),
                "concept_tags": sorted(concept_tags),
                "participant_ids": sorted(participant_ids),
                "emotion_id": emotion_id,
                "observed_revision": observed_revision,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    result_hash = hashlib.sha256(
        json.dumps(
            [record.memory_id for record in records] + [query_hash],
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return AuthorizedMemoryContext(
        records=records,
        observed_revision=observed_revision,
        index_revision=index_revision,
        query_hash="sha256:" + query_hash[:16],
        result_hash="sha256:" + result_hash[:16],
        truncated=truncated,
    )

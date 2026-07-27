"""
居民主观可见上下文与隐私边界

符合 DOC-AI-002：DecisionContextV1、Secret ACL、Visibility Proof、预算裁剪。
- RULE-AI-007：上下文只允许 actor 自身状态、当前感知、其 Memory/Belief、承诺、公开事实或有效 Grant
- RULE-AI-008：客观事实与 Belief/Memory 分开标记
- RULE-AI-009：每项非公开数据必须有可验证 Visibility Proof
- RULE-AI-011：裁剪不得删除安全约束、当前目标、关键 Need、承诺 deadline 或 unknown_or_redacted
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .constants import PlanKind, SecretLabel

#: 上下文容量上限（DOC-AI-002 §9）
MAX_CONTEXT_BYTES = 48 * 1024
MAX_PERCEIVED_ENTITIES = 32
MAX_MEMORIES = 24
MAX_BELIEFS = 24
MAX_COMMITMENTS = 16

#: 各计划层 token 预算（DOC-AI-008 §4）
PLAN_INPUT_TOKEN_BUDGET: dict[PlanKind, int] = {
    PlanKind.IMMEDIATE_ACTION: 3000,
    PlanKind.HOURLY_INTENT: 4500,
    PlanKind.DAILY_PLAN: 7000,
    PlanKind.COMBAT_TURN: 2500,
}

#: 保守字符估计（DOC-AI-008 §8：tokenizer 不可用时 +20% 预留）
CHARS_PER_TOKEN_ESTIMATE = 3


class SourceKind(str, Enum):
    """Visibility Proof 的 source 类别"""

    SELF_STATE = "self_state"
    PERCEPTION = "perception"
    MEMORY = "memory"
    BELIEF = "belief"
    COMMITMENT = "commitment"
    PUBLIC_FACT = "public_fact"
    DISCLOSURE_GRANT = "disclosure_grant"


@dataclass(frozen=True)
class VisibilityProof:
    """可见性证明（DOC-AI-002 §4 固定字段）"""

    subject_ref: str
    owner_domain: str
    source_kind: SourceKind
    source_id: str
    access_reason: str
    source_revision: int
    secret_label: SecretLabel
    expires_at_game_time: Optional[int]

    def is_valid_at(self, game_time: int) -> bool:
        """grant 过期即排除（RULE-AI-009）"""
        return self.expires_at_game_time is None or game_time < self.expires_at_game_time


@dataclass(frozen=True)
class ContextItem:
    """一条可进入上下文的数据（fact/belief/memory 分开标记）"""

    item_id: str
    knowledge_layer: str  # "fact" | "belief" | "memory" | "commitment"
    payload: dict[str, Any]
    proof: VisibilityProof
    #: 裁剪保护：安全/目标/关键 Need/deadline 项不可被裁掉（RULE-AI-011）
    trim_protected: bool = False


@dataclass(frozen=True)
class DisclosureGrant:
    """已提交的披露授权"""

    grant_id: str
    scope: str
    secret_label: SecretLabel
    participant_ids: frozenset[str]
    expires_at_game_time: Optional[int]

    def allows(self, actor_id: str, label: SecretLabel, game_time: int) -> bool:
        """shared_secret 只对明确参与者披露（RULE-AI-010）"""
        if self.expires_at_game_time is not None and game_time >= self.expires_at_game_time:
            return False
        if label == SecretLabel.SHARED_SECRET:
            return actor_id in self.participant_ids
        return self.secret_label == label


@dataclass
class DecisionContextV1:
    """DOC-AI-002 §4 schema.ai.decision_context.v1"""

    schema_version: int
    resident_id: str
    observed_revision: int
    observed_game_time: int
    self_projection: dict[str, Any]
    position: dict[str, Any]
    perceived_entities: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    commitments: list[dict[str, Any]] = field(default_factory=list)
    available_action_ids: list[str] = field(default_factory=list)
    unknown_or_redacted: list[str] = field(default_factory=list)
    visibility_proofs: list[VisibilityProof] = field(default_factory=list)
    context_hash: str = ""

    def canonical_json(self) -> str:
        """canonical JSON：键排序、数组按 stable ID 排序（DOC-AI-002 §4）"""
        payload = {
            "schema_version": self.schema_version,
            "resident_id": self.resident_id,
            "observed_revision": self.observed_revision,
            "observed_game_time": self.observed_game_time,
            "self": self.self_projection,
            "position": self.position,
            "perceived_entities": _sort_by_stable_id(self.perceived_entities),
            "beliefs": _sort_by_stable_id(self.beliefs),
            "memories": _sort_by_stable_id(self.memories),
            "commitments": _sort_by_stable_id(self.commitments),
            "available_action_ids": sorted(self.available_action_ids),
            "unknown_or_redacted": sorted(self.unknown_or_redacted),
            "visibility_proofs": [
                {
                    "subject_ref": p.subject_ref,
                    "owner_domain": p.owner_domain,
                    "source_kind": p.source_kind.value,
                    "source_id": p.source_id,
                    "access_reason": p.access_reason,
                    "source_revision": p.source_revision,
                    "secret_label": p.secret_label.value,
                    "expires_at_game_time": p.expires_at_game_time,
                }
                for p in sorted(self.visibility_proofs, key=lambda x: x.subject_ref)
            ],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        """同一输入与 policy 得到 byte-equivalent hash（DOC-AI-002 §10）"""
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]


def _sort_by_stable_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """数组元素按 stable ID 排序；无 ID 的按 canonical JSON 排序保证确定性"""

    def sort_key(item: dict[str, Any]) -> str:
        for key in ("entity_id", "memory_id", "belief_id", "commitment_id", "subject_ref"):
            if key in item:
                return str(item[key])
        return json.dumps(item, ensure_ascii=False, sort_keys=True)

    return sorted(items, key=sort_key)


def filter_subjective_context(
    actor_id: str,
    items: list[ContextItem],
    grants: list[DisclosureGrant],
    game_time: int,
) -> tuple[list[ContextItem], list[str]]:
    """
    按 Secret Label 与 Grant 过滤（RULE-AI-007/009/010）

    返回 (可披露项, unknown_or_redacted 提示列表)。
    ACL owner 不可用（无 proof/grant）时默认拒绝非公开数据（DOC-AI-002 §8）。
    """
    visible: list[ContextItem] = []
    redacted: list[str] = []
    for item in items:
        label = item.proof.secret_label
        if label == SecretLabel.PUBLIC:
            visible.append(item)
            continue
        if label == SecretLabel.PERSONAL and item.proof.source_kind in (
            SourceKind.SELF_STATE,
            SourceKind.MEMORY,
            SourceKind.BELIEF,
            SourceKind.COMMITMENT,
        ):
            # personal 数据默认仅本人；self/memory/belief/commitment 天然是本人的
            visible.append(item)
            continue
        granted = any(grant.allows(actor_id, label, game_time) for grant in grants)
        if granted and item.proof.is_valid_at(game_time):
            visible.append(item)
        else:
            redacted.append(item.item_id)
    return visible, redacted


def budget_context(
    visible_items: list[ContextItem],
    plan_kind: PlanKind,
) -> tuple[list[ContextItem], list[ContextItem]]:
    """
    确定性预算裁剪（RULE-AI-011 / TEST-AI-007）

    顺序：safety → goal → commitment → recent/relevant。
    trim_protected 项（安全约束、当前目标、关键 Need、deadline）永不裁剪。
    返回 (保留项, 被裁项)。
    """
    budget_chars = PLAN_INPUT_TOKEN_BUDGET[plan_kind] * CHARS_PER_TOKEN_ESTIMATE

    protected = [item for item in visible_items if item.trim_protected]
    trimmable = [item for item in visible_items if not item.trim_protected]

    # 确定性排序：知识层优先级 -> item_id（稳定决胜）
    layer_priority = {"fact": 0, "commitment": 1, "belief": 2, "memory": 3}
    trimmable.sort(key=lambda item: (layer_priority.get(item.knowledge_layer, 9), item.item_id))

    kept = list(protected)
    used_chars = sum(
        len(json.dumps(item.payload, ensure_ascii=False, sort_keys=True)) for item in kept
    )
    dropped: list[ContextItem] = []
    for item in trimmable:
        item_chars = len(json.dumps(item.payload, ensure_ascii=False, sort_keys=True))
        if used_chars + item_chars <= budget_chars:
            kept.append(item)
            used_chars += item_chars
        else:
            dropped.append(item)
    return kept, dropped

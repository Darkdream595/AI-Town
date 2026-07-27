"""
秘密、隐私、AccessPolicy 与 Prompt 前过滤

符合 DOC-MEMORY-009：
- 六级 access level 封闭 enum，未知 fail closed（RULE-MEMORY-068）
- personal 仅 owner；shared_secret 仅精确 participant set 且 owner 必须在内（RULE-MEMORY-072）
- relationship 阈值与 allow list 必须同时满足（RULE-MEMORY-073）
- Mayor 不是 privacy override（RULE-MEMORY-075）
- boundary scan 失败整份 context rejected（RULE-MEMORY-077）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AccessLevel(str, Enum):
    PUBLIC = "public"
    COMMUNITY = "community"
    FACTION = "faction"
    RELATIONSHIP = "relationship"
    PERSONAL = "personal"
    SHARED_SECRET = "shared_secret"


class AccessPurpose(str, Enum):
    RESIDENT_DECISION_CONTEXT = "resident_decision_context"
    PLAYER_JOURNAL = "player_journal"
    DIALOGUE_CONTEXT = "dialogue_context"
    AUTHORIZED_UI = "authorized_ui"
    RUMOR_TRANSFER = "rumor_transfer"
    ADMIN_FORENSIC = "admin_forensic"


@dataclass(frozen=True)
class RelationshipRule:
    """relationship 阈值（require_all 恒为 true）"""

    minimum_trust: int
    minimum_intimacy: int


@dataclass(frozen=True)
class AccessPolicy:
    """AccessPolicyV1（DES-MEMORY-009）"""

    access_policy_id: str
    world_id: str
    owner_principal_id: str
    access_level: AccessLevel
    policy_version: int
    community_id: Optional[str] = None
    faction_id: Optional[str] = None
    relationship_rule: Optional[RelationshipRule] = None
    participant_ids: frozenset[str] = frozenset()
    explicit_allow_principal_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        # conditional 约束（schema allOf）
        if self.access_level == AccessLevel.COMMUNITY and not self.community_id:
            raise ValueError("community level 必须有 community_id")
        if self.access_level == AccessLevel.FACTION and not self.faction_id:
            raise ValueError("faction level 必须有 faction_id")
        if self.access_level == AccessLevel.RELATIONSHIP and self.relationship_rule is None:
            raise ValueError("relationship level 必须有 relationship_rule")
        if self.access_level == AccessLevel.SHARED_SECRET:
            if len(self.participant_ids) < 2:
                raise ValueError("shared_secret participant_ids 至少 2")
            # owner 必须在 participant set 中（RULE-MEMORY-072）
            if self.owner_principal_id not in self.participant_ids:
                raise ValueError("shared_secret owner 必须在 participant set 中")
        else:
            if self.participant_ids:
                raise ValueError("非 shared_secret 不得有 participant_ids")


class AccessDecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class AccessDecision:
    """AccessDecisionV1（DES-MEMORY-009）"""

    access_decision_id: str
    world_id: str
    principal_id: str
    memory_id: str
    policy_id: str
    policy_version: int
    observed_revision: int
    purpose: AccessPurpose
    decision: AccessDecisionKind
    reason_code: str


@dataclass(frozen=True)
class AccessSnapshot:
    """同一 observed Revision 的 membership/relationship 快照（RULE-MEMORY-070）"""

    observed_revision: int
    community_members: frozenset[str]  # 属于 policy community 的 principal
    faction_members: frozenset[str]
    # (viewer_principal, owner_principal) -> (trust, intimacy)
    relationship_values: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)


def authorize_memory_access(
    principal_id: str,
    memory_id: str,
    access_decision_id: str,
    policy: AccessPolicy,
    purpose: AccessPurpose,
    snapshot: AccessSnapshot,
    observed_revision: int,
) -> AccessDecision:
    """
    六级访问判定；任何失败 fail closed（RULE-MEMORY-068/072/073/075）

    Mayor 身份不在此函数签名中：治理身份不产生隐式授权。
    """
    if snapshot.observed_revision != observed_revision:
        return _deny(access_decision_id, policy, principal_id, memory_id, purpose, observed_revision, "snapshot_stale")

    level = policy.access_level
    allowed = False
    reason = "no_rule_matched"

    if principal_id == policy.owner_principal_id:
        allowed, reason = True, "owner_access"
    elif level == AccessLevel.PUBLIC:
        allowed, reason = True, "public_access"
    elif level == AccessLevel.COMMUNITY:
        if principal_id in snapshot.community_members:
            allowed, reason = True, "community_member"
    elif level == AccessLevel.FACTION:
        if principal_id in snapshot.faction_members:
            allowed, reason = True, "faction_member"
    elif level == AccessLevel.RELATIONSHIP:
        # 阈值与 explicit allow list 必须同时满足（RULE-MEMORY-073）
        if principal_id in policy.explicit_allow_principal_ids and policy.relationship_rule:
            trust, intimacy = snapshot.relationship_values.get(
                (principal_id, policy.owner_principal_id), (-100, -100)
            )
            if (
                trust >= policy.relationship_rule.minimum_trust
                and intimacy >= policy.relationship_rule.minimum_intimacy
            ):
                allowed, reason = True, "relationship_threshold_met"
            else:
                reason = "relationship_threshold_unmet"
        else:
            reason = "not_in_allow_list"
    elif level == AccessLevel.PERSONAL:
        reason = "personal_owner_only"
    elif level == AccessLevel.SHARED_SECRET:
        if principal_id in policy.participant_ids:
            allowed, reason = True, "shared_secret_participant"
        else:
            reason = "not_participant"

    decision_kind = AccessDecisionKind.ALLOW if allowed else AccessDecisionKind.DENY
    return AccessDecision(
        access_decision_id=access_decision_id,
        world_id=policy.world_id,
        principal_id=principal_id,
        memory_id=memory_id,
        policy_id=policy.access_policy_id,
        policy_version=policy.policy_version,
        observed_revision=observed_revision,
        purpose=purpose,
        decision=decision_kind,
        reason_code=reason,
    )


def _deny(
    access_decision_id: str,
    policy: AccessPolicy,
    principal_id: str,
    memory_id: str,
    purpose: AccessPurpose,
    observed_revision: int,
    reason_code: str,
) -> AccessDecision:
    return AccessDecision(
        access_decision_id=access_decision_id,
        world_id=policy.world_id,
        principal_id=principal_id,
        memory_id=memory_id,
        policy_id=policy.access_policy_id,
        policy_version=policy.policy_version,
        observed_revision=observed_revision,
        purpose=purpose,
        decision=AccessDecisionKind.DENY,
        reason_code=reason_code,
    )


class SecretBoundaryError(Exception):
    """MEMORY_SECRET_BOUNDARY_FAILED（RULE-MEMORY-077）"""


@dataclass(frozen=True)
class ContextItemEnvelope:
    """待输出的 context 项及其 decision"""

    memory_id: str
    policy_id: str
    policy_version: int
    access_decision: AccessDecision


def scan_authorized_context(items: list[ContextItemEnvelope]) -> None:
    """
    Secret boundary scan（RULE-MEMORY-077）

    发现 decision 缺失、policy version 不匹配、deny item 时整份 context rejected。
    """
    for item in items:
        decision = item.access_decision
        if decision is None:
            raise SecretBoundaryError(f"{item.memory_id}: decision 缺失")
        if decision.decision != AccessDecisionKind.ALLOW:
            raise SecretBoundaryError(f"{item.memory_id}: deny item 不得进入 context")
        if decision.policy_id != item.policy_id or decision.policy_version != item.policy_version:
            raise SecretBoundaryError(f"{item.memory_id}: policy version 不匹配")
        if decision.memory_id != item.memory_id:
            raise SecretBoundaryError(f"{item.memory_id}: decision memory_id 不匹配")

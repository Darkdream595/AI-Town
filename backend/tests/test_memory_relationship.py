"""
测试五维关系与六级访问策略

覆盖 TEST-MEMORY-021/022/023/033/034/035（DOC-MEMORY-006/009 §11）
"""

import pytest

from src.memory import (
    AccessDecisionKind,
    AccessLevel,
    AccessPolicy,
    AccessPurpose,
    AccessSnapshot,
    ContextItemEnvelope,
    DuplicateEffectError,
    RelationshipDeltaSet,
    RelationshipEdge,
    RelationshipRule,
    RelationshipVector,
    SecretBoundaryError,
    apply_relationship_event,
    authorize_memory_access,
    compute_applied_deltas,
    scan_authorized_context,
)

EDGE_ID = "01K1AB2CD3EF4GH5JK6MNP7QRE"
WORLD_ID = "01K1AB2CD3EF4GH5JK6MNP7QR0"
SOURCE_ID = "01K1AB2CD3EF4GH5JK6MNP7QRS"
TARGET_ID = "01K1AB2CD3EF4GH5JK6MNP7QRT"
EVENT_ID = "01K1AB2CD3EF4GH5JK6MNP7QRV"
POLICY_ID = "01K1AB2CD3EF4GH5JK6MNP7QRW"
DECISION_ID = "01K1AB2CD3EF4GH5JK6MNP7QRX"


class TestVectorSchema:
    """TEST-MEMORY-021：五维 strict 与 range"""

    def test_dimension_bounds(self):
        with pytest.raises(ValueError):
            RelationshipVector(affection=101)
        with pytest.raises(ValueError):
            RelationshipVector(trust=-101)
        vector = RelationshipVector(affection=-100, trust=100)
        assert vector.affection == -100


class TestDeltaOracle:
    """TEST-MEMORY-022：delta/舍入/缩放/clamp oracle"""

    def test_basic_delta(self):
        current = RelationshipVector()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 10}, interpretation_q1000=1000)
        next_vector, applied = compute_applied_deltas(current, delta_set)
        assert next_vector.trust == 10
        assert applied["trust"] == 10

    def test_interpretation_scaling(self):
        current = RelationshipVector()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 10}, interpretation_q1000=500)
        next_vector, _ = compute_applied_deltas(current, delta_set)
        assert next_vector.trust == 5

    def test_negative_interpretation_truncate_toward_zero(self):
        current = RelationshipVector()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 7}, interpretation_q1000=-500)
        next_vector, _ = compute_applied_deltas(current, delta_set)
        assert next_vector.trust == -3  # -3.5 → -3（向零取整）

    def test_dimension_clamp_reports_actual(self):
        # current=95、delta=10 → next=100、actual=5（DOC-MEMORY-006 §7）
        current = RelationshipVector(trust=95)
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 10}, interpretation_q1000=1000)
        next_vector, applied = compute_applied_deltas(current, delta_set)
        assert next_vector.trust == 100
        assert applied["trust"] == 5

    def test_per_dimension_limit_20(self):
        current = RelationshipVector()
        # base_delta 上限 20：超出构造即拒绝
        with pytest.raises(ValueError):
            RelationshipDeltaSet(base_deltas={"trust": 21}, interpretation_q1000=1000)

    def test_total_limit_40_scaling(self):
        current = RelationshipVector()
        delta_set = RelationshipDeltaSet(
            base_deltas={"affection": 20, "trust": 20, "fear": 20, "respect": 20, "intimacy": 20},
            interpretation_q1000=1000,
        )
        next_vector, applied = compute_applied_deltas(current, delta_set)
        total = sum(abs(value) for value in applied.values())
        assert total == 40
        # 五维均匀缩放：每维 8
        assert all(abs(value) == 8 for value in applied.values())

    def test_total_limit_round_robin_distribution(self):
        current = RelationshipVector()
        # 三维 pre_applied = 20, 20, 10（sum 50 > 40）
        # 比例缩放：20*40/50=16, 16, 10*40/50=8 → sum 40
        delta_set = RelationshipDeltaSet(
            base_deltas={"trust": 20, "affection": 20, "fear": 10},
            interpretation_q1000=1000,
        )
        _, applied = compute_applied_deltas(current, delta_set)
        assert sum(abs(v) for v in applied.values()) == 40
        assert applied["trust"] == 16
        assert applied["affection"] == 16
        assert applied["fear"] == 8

    def test_round_robin_remainder_order(self):
        # pre: trust=20, affection=20, fear=20 → sum 60
        # 缩放：20*40/60=13（×3）→ sum 39，余 1 按 trust,affection,fear 顺序补给 trust
        current = RelationshipVector()
        delta_set = RelationshipDeltaSet(
            base_deltas={"trust": 20, "affection": 20, "fear": 20},
            interpretation_q1000=1000,
        )
        _, applied = compute_applied_deltas(current, delta_set)
        assert sum(abs(v) for v in applied.values()) == 40
        assert applied["trust"] == 14
        assert applied["affection"] == 13
        assert applied["fear"] == 13


class TestDirectionAndIdempotency:
    """TEST-MEMORY-023：direction、event eligibility 与幂等"""

    def _edge(self) -> RelationshipEdge:
        return RelationshipEdge(
            edge_id=EDGE_ID,
            world_id=WORLD_ID,
            source_resident_id=SOURCE_ID,
            target_resident_id=TARGET_ID,
        )

    def test_same_event_twice_rejected(self):
        edge = self._edge()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 5}, interpretation_q1000=1000)
        apply_relationship_event(edge, EVENT_ID, delta_set)
        with pytest.raises(DuplicateEffectError):
            apply_relationship_event(edge, EVENT_ID, delta_set)

    def test_edge_revision_increments(self):
        edge = self._edge()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 5}, interpretation_q1000=1000)
        apply_relationship_event(edge, EVENT_ID, delta_set)
        assert edge.edge_revision == 2

    def test_stale_revision_rejected(self):
        edge = self._edge()
        delta_set = RelationshipDeltaSet(base_deltas={"trust": 5}, interpretation_q1000=1000)
        with pytest.raises(ValueError):
            apply_relationship_event(edge, EVENT_ID, delta_set, expected_edge_revision=99)


def _policy(level: AccessLevel, **overrides) -> AccessPolicy:
    defaults = dict(
        access_policy_id=POLICY_ID,
        world_id=WORLD_ID,
        owner_principal_id=SOURCE_ID,
        access_level=level,
        policy_version=3,
    )
    defaults.update(overrides)
    return AccessPolicy(**defaults)


def _snapshot(revision: int = 450, **overrides) -> AccessSnapshot:
    defaults = dict(observed_revision=revision, community_members=frozenset(), faction_members=frozenset())
    defaults.update(overrides)
    return AccessSnapshot(**defaults)


def _authorize(principal: str, policy: AccessPolicy, snapshot: AccessSnapshot, revision: int = 450):
    return authorize_memory_access(
        principal_id=principal,
        memory_id="01K1AB2CD3EF4GH5JK6MNP7QRY",
        access_decision_id=DECISION_ID,
        policy=policy,
        purpose=AccessPurpose.RESIDENT_DECISION_CONTEXT,
        snapshot=snapshot,
        observed_revision=revision,
    )


class TestAccessMatrix:
    """TEST-MEMORY-033/034：六级 access matrix"""

    def test_public_allows_any_resident(self):
        decision = _authorize(TARGET_ID, _policy(AccessLevel.PUBLIC), _snapshot())
        assert decision.decision == AccessDecisionKind.ALLOW

    def test_personal_only_owner(self):
        policy = _policy(AccessLevel.PERSONAL)
        assert _authorize(SOURCE_ID, policy, _snapshot()).decision == AccessDecisionKind.ALLOW
        denied = _authorize(TARGET_ID, policy, _snapshot())
        assert denied.decision == AccessDecisionKind.DENY
        assert denied.reason_code == "personal_owner_only"

    def test_community_members_only(self):
        policy = _policy(AccessLevel.COMMUNITY, community_id="community.crown_creek")
        member_snapshot = _snapshot(community_members=frozenset({TARGET_ID}))
        assert _authorize(TARGET_ID, policy, member_snapshot).decision == AccessDecisionKind.ALLOW
        assert _authorize(TARGET_ID, policy, _snapshot()).decision == AccessDecisionKind.DENY

    def test_faction_members_only(self):
        policy = _policy(AccessLevel.FACTION, faction_id="faction.alchemists")
        member_snapshot = _snapshot(faction_members=frozenset({TARGET_ID}))
        assert _authorize(TARGET_ID, policy, member_snapshot).decision == AccessDecisionKind.ALLOW
        assert _authorize(TARGET_ID, policy, _snapshot()).decision == AccessDecisionKind.DENY

    def test_relationship_requires_allow_list_and_threshold(self):
        rule = RelationshipRule(minimum_trust=50, minimum_intimacy=30)
        # 只有阈值无 allow list → 不授权（RULE-MEMORY-073）
        policy_no_list = _policy(AccessLevel.RELATIONSHIP, relationship_rule=rule)
        snapshot = _snapshot(relationship_values={(TARGET_ID, SOURCE_ID): (80, 80)})
        assert _authorize(TARGET_ID, policy_no_list, snapshot).decision == AccessDecisionKind.DENY
        # allow list + 阈值达标 → 授权
        policy_full = _policy(
            AccessLevel.RELATIONSHIP,
            relationship_rule=rule,
            explicit_allow_principal_ids=frozenset({TARGET_ID}),
        )
        assert _authorize(TARGET_ID, policy_full, snapshot).decision == AccessDecisionKind.ALLOW
        # allow list + 阈值不达标 → 拒绝
        low_snapshot = _snapshot(relationship_values={(TARGET_ID, SOURCE_ID): (10, 80)})
        denied = _authorize(TARGET_ID, policy_full, low_snapshot)
        assert denied.decision == AccessDecisionKind.DENY
        assert denied.reason_code == "relationship_threshold_unmet"

    def test_shared_secret_participants_only(self):
        policy = _policy(
            AccessLevel.SHARED_SECRET,
            participant_ids=frozenset({SOURCE_ID, TARGET_ID}),
        )
        assert _authorize(TARGET_ID, policy, _snapshot()).decision == AccessDecisionKind.ALLOW
        outsider = "01K1AB2CD3EF4GH5JK6MNP7QRZ"
        denied = _authorize(outsider, policy, _snapshot())
        assert denied.decision == AccessDecisionKind.DENY
        assert denied.reason_code == "not_participant"

    def test_shared_secret_owner_must_be_participant(self):
        with pytest.raises(ValueError):
            _policy(AccessLevel.SHARED_SECRET, participant_ids=frozenset({TARGET_ID, "other"}))

    def test_mayor_no_implicit_override(self):
        # Mayor 是治理身份，不是 privacy override：函数签名不含身份，按普通 principal 判定
        policy = _policy(AccessLevel.PERSONAL)
        mayor_id = "01K1AB2CD3EF4GH5JK6MNP7QM0"
        assert _authorize(mayor_id, policy, _snapshot()).decision == AccessDecisionKind.DENY

    def test_stale_snapshot_denied(self):
        decision = _authorize(
            TARGET_ID, _policy(AccessLevel.PUBLIC), _snapshot(revision=449), revision=450
        )
        assert decision.decision == AccessDecisionKind.DENY
        assert decision.reason_code == "snapshot_stale"


class TestBoundaryScan:
    """TEST-MEMORY-035：ACL-before-materialize 与 boundary scan"""

    def _allow_decision(self, memory_id: str = "01K1AB2CD3EF4GH5JK6MNP7QRY"):
        return authorize_memory_access(
            principal_id=SOURCE_ID,
            memory_id=memory_id,
            access_decision_id=DECISION_ID,
            policy=_policy(AccessLevel.PUBLIC),
            purpose=AccessPurpose.RESIDENT_DECISION_CONTEXT,
            snapshot=_snapshot(),
            observed_revision=450,
        )

    def test_valid_context_passes(self):
        items = [
            ContextItemEnvelope(
                memory_id="01K1AB2CD3EF4GH5JK6MNP7QRY",
                policy_id=POLICY_ID,
                policy_version=3,
                access_decision=self._allow_decision(),
            )
        ]
        scan_authorized_context(items)  # 不抛异常

    def test_deny_item_rejects_whole_context(self):
        allow_items = [
            ContextItemEnvelope(
                memory_id="01K1AB2CD3EF4GH5JK6MNP7QRY",
                policy_id=POLICY_ID,
                policy_version=3,
                access_decision=self._allow_decision(),
            )
        ]
        deny_decision = authorize_memory_access(
            principal_id=TARGET_ID,
            memory_id="01K1AB2CD3EF4GH5JK6MNP7QRZ",
            access_decision_id=DECISION_ID,
            policy=_policy(AccessLevel.PERSONAL),
            purpose=AccessPurpose.RESIDENT_DECISION_CONTEXT,
            snapshot=_snapshot(),
            observed_revision=450,
        )
        poisoned = allow_items + [
            ContextItemEnvelope(
                memory_id="01K1AB2CD3EF4GH5JK6MNP7QRZ",
                policy_id=POLICY_ID,
                policy_version=3,
                access_decision=deny_decision,
            )
        ]
        with pytest.raises(SecretBoundaryError):
            scan_authorized_context(poisoned)

    def test_policy_version_mismatch_rejected(self):
        items = [
            ContextItemEnvelope(
                memory_id="01K1AB2CD3EF4GH5JK6MNP7QRY",
                policy_id=POLICY_ID,
                policy_version=99,  # 与 decision 不符
                access_decision=self._allow_decision(),
            )
        ]
        with pytest.raises(SecretBoundaryError):
            scan_authorized_context(items)

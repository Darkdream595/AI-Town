"""
测试谣言传播、信念调和与记忆巩固

覆盖 TEST-MEMORY-029/030/013/014/038/040（DOC-MEMORY-008/004/010 §11）
"""

import pytest

from src.memory import (
    ChainValidationError,
    ConsolidationSourceMetadata,
    DuplicateEvidenceError,
    EvidenceKind,
    KnowledgeState,
    MemoryStateMachine,
    RumorChain,
    SemanticBeliefState,
    TombstoneStateError,
    check_consolidation_eligibility,
    compute_lineage_hash,
    compute_next_confidence_q1000,
    query_knowledge_state,
    reconcile_belief,
    reconciliation_delta,
    select_distortion_operation,
    validate_and_append_hop,
)

ID_A = "01K1AB2CD3EF4GH5JK6MNP7QRA"
ID_B = "01K1AB2CD3EF4GH5JK6MNP7QRB"
ID_C = "01K1AB2CD3EF4GH5JK6MNP7QRC"
ID_D = "01K1AB2CD3EF4GH5JK6MNP7QRD"
EVENT = "01K1AB2CD3EF4GH5JK6MNP7QRV"


class TestRumorChain:
    """TEST-MEMORY-029：chain continuity/loop/max hops"""

    def _chain(self) -> RumorChain:
        return RumorChain(chain_fingerprint="a" * 64, origin_belief_id=ID_A)

    def test_hop_index_continuous(self):
        chain = self._chain()
        hop0 = validate_and_append_hop(chain, ID_A, ID_B, EVENT, "h0", 800)
        hop1 = validate_and_append_hop(chain, ID_B, ID_C, EVENT, "h1", 700)
        assert hop0.hop_index == 0
        assert hop1.hop_index == 1

    def test_discontinuity_rejected(self):
        chain = self._chain()
        validate_and_append_hop(chain, ID_A, ID_B, EVENT, "h0", 800)
        with pytest.raises(ChainValidationError):
            validate_and_append_hop(chain, ID_C, ID_D, EVENT, "h1", 700)

    def test_recipient_already_in_chain_stops(self):
        chain = self._chain()
        validate_and_append_hop(chain, ID_A, ID_B, EVENT, "h0", 800)
        # B 再传回 A：A 已在 chain → 停止
        result = validate_and_append_hop(chain, ID_B, ID_A, EVENT, "h1", 700)
        assert result is None

    def test_max_hops_8(self):
        chain = self._chain()
        speakers = [f"01K1AB2CD3EF4GH5JK6MNP7QN{i}" for i in range(10)]
        for index in range(8):
            result = validate_and_append_hop(
                chain, speakers[index], speakers[index + 1], EVENT, f"h{index}", 800 - index * 10
            )
            assert result is not None
        # 第 9 hop 停止
        assert validate_and_append_hop(chain, speakers[8], speakers[9], EVENT, "h8", 700) is None

    def test_confidence_monotonic_non_increasing(self):
        chain = self._chain()
        validate_and_append_hop(chain, ID_A, ID_B, EVENT, "h0", 700)
        with pytest.raises(ChainValidationError):
            validate_and_append_hop(chain, ID_B, ID_C, EVENT, "h1", 900)


class TestConfidenceFormula:
    """TEST-MEMORY-030：confidence/distortion fixed oracle"""

    def test_full_trust_no_distortion(self):
        # trust=100 → factor=1000 → 无损
        assert compute_next_confidence_q1000(800, 100, 0) == 800

    def test_zero_trust_halves(self):
        # trust=0 → factor=500
        assert compute_next_confidence_q1000(800, 0, 0) == 400

    def test_min_trust_zero_factor(self):
        # trust=-100 → factor=0
        assert compute_next_confidence_q1000(800, -100, 0) == 0

    def test_distortion_penalty(self):
        # trust=100, 2 个失真 → 800 - 160
        assert compute_next_confidence_q1000(800, 100, 2) == 640

    def test_never_exceeds_previous(self):
        assert compute_next_confidence_q1000(500, 100, 0) <= 500

    def test_distortion_selector_deterministic(self):
        eligible = ["omit_qualifier", "generalize_quantity"]
        first = select_distortion_operation("claimhash", ["a", "b"], eligible)
        second = select_distortion_operation("claimhash", ["a", "b"], eligible)
        assert first == second
        assert first in eligible

    def test_distortion_selector_none_when_no_eligible(self):
        assert select_distortion_operation("claimhash", ["a"], []) is None


class TestBeliefReconciliation:
    """TEST-MEMORY-038/040：fact/belief 边界与 reconciliation formula"""

    def test_reconciliation_deltas(self):
        assert reconciliation_delta(EvidenceKind.DIRECT_OBSERVATION_SUPPORTING) == 200
        assert reconciliation_delta(EvidenceKind.DIRECT_OBSERVATION_CONTRADICTING) == -300
        assert reconciliation_delta(EvidenceKind.TESTIMONY_SUPPORTING, 500) == 50
        assert reconciliation_delta(EvidenceKind.TESTIMONY_SUPPORTING, 1000) == 100  # max +100
        assert reconciliation_delta(EvidenceKind.TESTIMONY_CONTRADICTING, 1000) == -100

    def test_reconcile_updates_confidence(self):
        belief = SemanticBeliefState(belief_id=ID_A, claim_key="shop.x.is_open", confidence_q1000=500)
        new_value = reconcile_belief(belief, EVENT, EvidenceKind.DIRECT_OBSERVATION_SUPPORTING)
        assert new_value == 700

    def test_duplicate_evidence_rejected(self):
        belief = SemanticBeliefState(belief_id=ID_A, claim_key="k", confidence_q1000=500)
        reconcile_belief(belief, EVENT, EvidenceKind.DIRECT_OBSERVATION_SUPPORTING)
        with pytest.raises(DuplicateEvidenceError):
            reconcile_belief(belief, EVENT, EvidenceKind.DIRECT_OBSERVATION_SUPPORTING)

    def test_zero_confidence_marks_disbelieved_not_deleted(self):
        belief = SemanticBeliefState(belief_id=ID_A, claim_key="k", confidence_q1000=200)
        reconcile_belief(belief, EVENT, EvidenceKind.DIRECT_OBSERVATION_CONTRADICTING)
        assert belief.confidence_q1000 == 0
        assert belief.state == KnowledgeState.DISBELIEVED

    def test_knowledge_state_unknown_without_belief(self):
        assert query_knowledge_state([], "any.claim") == KnowledgeState.UNKNOWN

    def test_knowledge_state_contradicted_with_multiple(self):
        beliefs = [
            SemanticBeliefState(belief_id=ID_A, claim_key="k", confidence_q1000=800),
            SemanticBeliefState(belief_id=ID_B, claim_key="k", confidence_q1000=300),
        ]
        assert query_knowledge_state(beliefs, "k") == KnowledgeState.CONTRADICTED


class TestMemoryStateMachine:
    """状态机合法/非法边"""

    def test_valid_edges(self):
        assert MemoryStateMachine.transition("active", "cold") == "cold"
        assert MemoryStateMachine.transition("cold", "reactivated") == "reactivated"
        assert MemoryStateMachine.transition("reactivated", "active") == "active"

    def test_tombstone_terminal(self):
        with pytest.raises(TombstoneStateError):
            MemoryStateMachine.transition("tombstoned", "active")

    def test_cold_cannot_go_active_directly(self):
        with pytest.raises(TombstoneStateError):
            MemoryStateMachine.transition("cold", "active")


def _source(memory_id: str, **overrides) -> ConsolidationSourceMetadata:
    defaults = dict(
        world_id="01K1AB2CD3EF4GH5JK6MNP7QR0",
        memory_owner_id="01K1AB2CD3EF4GH5JK6MNP7QRS",
        access_policy_id="01K1AB2CD3EF4GH5JK6MNP7QRW",
        memory_kind="episodic_memory",
        importance_q1000=300,
        state="active",
        created_at_game_time=1000,
        semantic_tags=frozenset({"topic.market.gossip"}),
        record_hash="b" * 64,
    )
    defaults.update(overrides)
    return ConsolidationSourceMetadata(memory_id=memory_id, **defaults)


class TestConsolidationEligibility:
    """TEST-MEMORY-013/014：cluster/window/eligibility 与 protected exclusion"""

    def test_three_sources_eligible(self):
        sources = [_source(ID_A), _source(ID_B), _source(ID_C)]
        eligible, reason = check_consolidation_eligibility(sources)
        assert eligible, reason

    def test_two_sources_rejected(self):
        eligible, _ = check_consolidation_eligibility([_source(ID_A), _source(ID_B)])
        assert not eligible

    def test_high_importance_excluded(self):
        sources = [_source(ID_A), _source(ID_B), _source(ID_C, importance_q1000=600)]
        eligible, reason = check_consolidation_eligibility(sources)
        assert not eligible
        assert "importance" in reason

    def test_policy_mismatch_rejected(self):
        sources = [
            _source(ID_A),
            _source(ID_B),
            _source(ID_C, access_policy_id="01K1AB2CD3EF4GH5JK6MNP7QRX"),
        ]
        eligible, reason = check_consolidation_eligibility(sources)
        assert not eligible
        assert "POLICY_MISMATCH" in reason

    def test_shared_secret_excluded(self):
        sources = [_source(ID_A), _source(ID_B), _source(ID_C, is_shared_secret=True)]
        eligible, _ = check_consolidation_eligibility(sources)
        assert not eligible

    def test_protected_tag_excluded(self):
        sources = [
            _source(ID_A),
            _source(ID_B),
            _source(ID_C, semantic_tags=frozenset({"consequence.trauma"})),
        ]
        eligible, _ = check_consolidation_eligibility(sources)
        assert not eligible

    def test_window_over_7_days_rejected(self):
        sources = [
            _source(ID_A, created_at_game_time=0),
            _source(ID_B, created_at_game_time=100),
            _source(ID_C, created_at_game_time=8 * 1440),
        ]
        eligible, reason = check_consolidation_eligibility(sources)
        assert not eligible
        assert "7" in reason

    def test_lineage_hash_deterministic(self):
        ids = [ID_A, ID_B, ID_C]
        hashes = ["a" * 64, "b" * 64, "c" * 64]
        first = compute_lineage_hash(ids, hashes)
        second = compute_lineage_hash(list(reversed(ids)), list(reversed(hashes)))
        assert first == second  # canonical 排序后与输入顺序无关

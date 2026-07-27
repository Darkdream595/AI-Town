"""
测试检索评分、衰减与再激活

覆盖 TEST-MEMORY-009/010/017/018（DOC-MEMORY-003/005 §11）
"""

import pytest

from src.memory import (
    ComponentScores,
    RetentionClass,
    RetrievalCandidate,
    RetrievalLimits,
    apply_importance_delta,
    commitment_urgency_q1000,
    compute_score_q1000,
    compute_strength_q1000,
    emotion_match_q1000,
    evaluate_retention,
    participant_match_q1000,
    recency_q1000,
    retention_factor_q1000,
    retrieve_authorized_memories,
    weighted_jaccard_q1000,
)

MEMORY_A = "01K1AB2CD3EF4GH5JK6MNP7QRA"
MEMORY_B = "01K1AB2CD3EF4GH5JK6MNP7QRB"
MEMORY_C = "01K1AB2CD3EF4GH5JK6MNP7QRC"


class TestSevenComponentFormula:
    """TEST-MEMORY-009：七分量公式、recency/commitment table"""

    def test_weights_sum_to_1000(self):
        assert 300 + 180 + 120 + 80 + 120 + 120 + 80 == 1000

    def test_total_score_formula(self):
        components = ComponentScores(
            semantic_match_q1000=1000,
            goal_match_q1000=1000,
            participant_match_q1000=1000,
            emotion_match_q1000=1000,
            importance_q1000=1000,
            commitment_urgency_q1000=1000,
            recency_q1000=1000,
        )
        assert compute_score_q1000(components) == 1000

    def test_score_floor_integer(self):
        components = ComponentScores(
            semantic_match_q1000=333,
            goal_match_q1000=0,
            participant_match_q1000=0,
            emotion_match_q1000=0,
            importance_q1000=0,
            commitment_urgency_q1000=0,
            recency_q1000=0,
        )
        assert compute_score_q1000(components) == (333 * 300) // 1000

    def test_recency_table(self):
        assert recency_q1000(0) == 1000
        assert recency_q1000(1) == 900
        assert recency_q1000(2) == 750
        assert recency_q1000(3) == 750
        assert recency_q1000(4) == 550
        assert recency_q1000(7) == 550
        assert recency_q1000(8) == 300
        assert recency_q1000(30) == 300
        assert recency_q1000(31) == 150
        assert recency_q1000(90) == 150
        assert recency_q1000(91) == 50

    def test_commitment_urgency_table(self):
        assert commitment_urgency_q1000("accepted", 100, 100) == 1000  # 逾期
        assert commitment_urgency_q1000("accepted", 110, 100) == 1000  # 24 分钟内
        assert commitment_urgency_q1000("accepted", 500, 100) == 800  # 1 日内
        assert commitment_urgency_q1000("accepted", 2000, 100) == 500  # 3 日内
        assert commitment_urgency_q1000("accepted", 99999, 100) == 250  # 更远
        assert commitment_urgency_q1000("accepted", None, 100) == 300  # 无 deadline
        assert commitment_urgency_q1000("proposed", 100, 100) == 0  # 非 accepted

    def test_weighted_jaccard(self):
        query = frozenset({"tag.a.b", "tag.c.d"})
        record = frozenset({"tag.a.b"})
        assert weighted_jaccard_q1000(query, record) == 500
        assert weighted_jaccard_q1000(frozenset(), frozenset()) == 0

    def test_participant_match(self):
        assert participant_match_q1000(frozenset({"a", "b"}), frozenset({"a"})) == 500
        assert participant_match_q1000(frozenset(), frozenset({"a"})) == 0

    def test_emotion_match(self):
        assert emotion_match_q1000("joy", "joy") == 1000
        assert emotion_match_q1000("joy", "hope", {"joy": frozenset({"hope"})}) == 500
        assert emotion_match_q1000("joy", "anger") == 0
        assert emotion_match_q1000(None, "joy") == 0


def _candidate(memory_id: str, importance: int = 500, created: int = 0, **overrides) -> RetrievalCandidate:
    defaults = dict(
        memory_kind="episodic_memory",
        semantic_tags=frozenset({"topic.market.gossip"}),
        participant_ids=frozenset(),
        emotion_id=None,
        importance_q1000=importance,
        created_at_game_time=created,
        last_reactivated_game_time=None,
    )
    defaults.update(overrides)
    return RetrievalCandidate(memory_id=memory_id, **defaults)


class TestStableSortAndLimits:
    """TEST-MEMORY-010：stable sort、limits 与 byte boundary"""

    def test_tie_break_importance_then_created_then_id(self):
        candidates = [
            _candidate(MEMORY_C, importance=400),
            _candidate(MEMORY_A, importance=900),
            _candidate(MEMORY_B, importance=900, created=100),
        ]
        result = retrieve_authorized_memories(
            candidates,
            goal_tags=frozenset(),
            concept_tags=frozenset({"topic.market.gossip"}),
            participant_ids=frozenset(),
            emotion_id=None,
            current_game_time=0,
            observed_revision=1,
            index_revision=1,
        )
        ids = [record.memory_id for record in result.records]
        # 同分时 importance 高者先；再 created 新者先
        assert ids[0] == MEMORY_B
        assert ids[1] == MEMORY_A

    def test_commitment_reserved_slot(self):
        commitment = _candidate(
            MEMORY_A,
            importance=1,
            memory_kind="commitment",
            commitment_status="accepted",
            commitment_deadline=10,
        )
        normal = _candidate(MEMORY_B, importance=1000)
        result = retrieve_authorized_memories(
            [normal, commitment],
            goal_tags=frozenset(),
            concept_tags=frozenset(),
            participant_ids=frozenset(),
            emotion_id=None,
            current_game_time=0,
            observed_revision=1,
            index_revision=1,
            limits=RetrievalLimits(record_limit=16, commitment_limit=1),
        )
        ids = [record.memory_id for record in result.records]
        assert MEMORY_A in ids  # commitment 保留槽，即使分数低

    def test_byte_limit_truncation(self):
        big_payload = {"data": "x" * 2000}
        candidates = [
            _candidate(f"01K1AB2CD3EF4GH5JK6MNP7QX{i}", authorized_payload=big_payload)
            for i in range(10)
        ]
        result = retrieve_authorized_memories(
            candidates,
            goal_tags=frozenset(),
            concept_tags=frozenset({"topic.market.gossip"}),
            participant_ids=frozenset(),
            emotion_id=None,
            current_game_time=0,
            observed_revision=1,
            index_revision=1,
            limits=RetrievalLimits(record_limit=16, commitment_limit=0, utf8_byte_limit=4096),
        )
        assert result.truncated
        assert 0 < len(result.records) < 10

    def test_deterministic_result_hash(self):
        candidates = [_candidate(MEMORY_A), _candidate(MEMORY_B, created=50)]
        kwargs = dict(
            goal_tags=frozenset(),
            concept_tags=frozenset({"topic.market.gossip"}),
            participant_ids=frozenset(),
            emotion_id=None,
            current_game_time=100,
            observed_revision=1,
            index_revision=1,
        )
        first = retrieve_authorized_memories(list(candidates), **kwargs)
        second = retrieve_authorized_memories(list(reversed(candidates)), **kwargs)
        assert first.result_hash == second.result_hash


class TestRetentionTable:
    """TEST-MEMORY-017：retention table、importance delta 与 protected classes"""

    def test_factor_table_all_endpoints(self):
        assert retention_factor_q1000(RetentionClass.ROUTINE, 0) == 1000
        assert retention_factor_q1000(RetentionClass.ROUTINE, 3) == 750
        assert retention_factor_q1000(RetentionClass.ROUTINE, 7) == 500
        assert retention_factor_q1000(RetentionClass.ROUTINE, 30) == 250
        assert retention_factor_q1000(RetentionClass.ROUTINE, 90) == 100
        assert retention_factor_q1000(RetentionClass.ROUTINE, 91) == 50
        assert retention_factor_q1000(RetentionClass.NORMAL, 3) == 900
        assert retention_factor_q1000(RetentionClass.NORMAL, 91) == 100
        assert retention_factor_q1000(RetentionClass.SIGNIFICANT, 91) == 600
        assert retention_factor_q1000(RetentionClass.CORE, 91) == 900
        assert retention_factor_q1000(RetentionClass.PINNED, 500) == 1000

    def test_strength_floor(self):
        assert compute_strength_q1000(500, 750) == 375
        assert compute_strength_q1000(999, 250) == 249

    def test_importance_delta_clamp(self):
        assert apply_importance_delta(500, 150) == 600  # delta 限幅 100
        assert apply_importance_delta(500, -150) == 400
        assert apply_importance_delta(980, 100) == 1000
        assert apply_importance_delta(20, -100) == 0

    def test_protected_classes_never_cold(self):
        for retention_class in (RetentionClass.CORE, RetentionClass.PINNED):
            decision = evaluate_retention(
                memory_id=MEMORY_A,
                retention_class=retention_class,
                base_importance_q1000=10,
                last_strength_anchor_game_time=0,
                current_game_time=365 * 1440,
                is_active=True,
            )
            assert not decision.should_move_to_cold
            assert decision.skip_reason == "protected_class"

    def test_legal_hold_skipped(self):
        decision = evaluate_retention(
            memory_id=MEMORY_A,
            retention_class=RetentionClass.ROUTINE,
            base_importance_q1000=100,
            last_strength_anchor_game_time=0,
            current_game_time=365 * 1440,
            is_active=True,
            legal_hold=True,
        )
        assert not decision.should_move_to_cold
        assert decision.skip_reason == "legal_hold"

    def test_low_strength_moves_to_cold(self):
        decision = evaluate_retention(
            memory_id=MEMORY_A,
            retention_class=RetentionClass.ROUTINE,
            base_importance_q1000=300,
            last_strength_anchor_game_time=0,
            current_game_time=30 * 1440,  # factor 250 → strength 75 < 250
            is_active=True,
        )
        assert decision.should_move_to_cold

    def test_time_regression_rejected(self):
        with pytest.raises(ValueError):
            evaluate_retention(
                memory_id=MEMORY_A,
                retention_class=RetentionClass.NORMAL,
                base_importance_q1000=500,
                last_strength_anchor_game_time=1000,
                current_game_time=500,
                is_active=True,
            )


class TestGameTimeOnlyDecay:
    """TEST-MEMORY-018：GameTime-only decay 与 offline zero delta"""

    def test_zero_elapsed_zero_decay(self):
        # Pause/离线：current == anchor → elapsed 0 日 → factor 1000 → strength 不衰减
        decision = evaluate_retention(
            memory_id=MEMORY_A,
            retention_class=RetentionClass.ROUTINE,
            base_importance_q1000=500,
            last_strength_anchor_game_time=5000,
            current_game_time=5000,
            is_active=True,
        )
        assert decision.factor_q1000 == 1000
        assert decision.strength_q1000 == 500
        assert not decision.should_move_to_cold

    def test_partial_day_no_decay(self):
        # 不足一整日：elapsed 0 日
        decision = evaluate_retention(
            memory_id=MEMORY_A,
            retention_class=RetentionClass.ROUTINE,
            base_importance_q1000=100,
            last_strength_anchor_game_time=0,
            current_game_time=1439,
            is_active=True,
        )
        assert decision.elapsed_game_days == 0

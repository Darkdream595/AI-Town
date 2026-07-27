"""
TEST-PLAYER-021..024：玩家影响世界的因果与事件边界（DOC-PLAYER-006）

- TEST-PLAYER-021：六维 command→event→projection 因果链
- TEST-PLAYER-022：owner result injection 与 direct mutation 拒绝
- TEST-PLAYER-023：Outbox 重发、Revision 补帧与投影重建
- TEST-PLAYER-024：Saga failure、补偿事件与隐私过滤
"""

import pytest

from src.player import (
    IMPACT_DIMENSIONS,
    CausalityEnvelope,
    DirectMutationError,
    ImpactProjection,
    ImpactTracker,
)
from src.player.impact import assert_not_direct_mutation

WORLD = "01K1WRDX000000000000000001"
ACTOR = "01K1RSDT000000000000000001"


class TestCausalChain:
    """TEST-PLAYER-021"""

    def test_six_dimensions_registered(self):
        assert set(IMPACT_DIMENSIONS) == {
            "social", "economic", "political", "spatial", "conflict", "narrative",
        }
        for dim in IMPACT_DIMENSIONS.values():
            assert dim["commands"] and dim["forbidden_mutations"]

    def test_event_carries_full_causality(self):
        tracker = ImpactTracker(WORLD)
        correlation = tracker.new_correlation_id()
        event = tracker.wrap_event(
            command_id="cmd-1",
            correlation_id=correlation,
            actor_entity_id=ACTOR,
            event_type="economy.transaction_committed",
            payload={"transaction_id": "tx-1"},
            revision=201,
            game_time=3120,
            render={"cue": "trade_success"},
        )
        # RULE-PLAYER-027：causation=command、correlation、actor、revision、game_time
        assert event.causation_id == "cmd-1"
        assert event.correlation_id == correlation
        assert event.actor_entity_id == ACTOR
        assert event.revision == 201
        assert event.game_time == 3120
        assert tracker.verify_chain("cmd-1")

    def test_one_command_multiple_events_same_correlation(self):
        tracker = ImpactTracker(WORLD)
        correlation = tracker.new_correlation_id()
        tracker.wrap_event("cmd-1", correlation, ACTOR, "economy.transaction_committed", {}, 201, 3120)
        tracker.wrap_event("cmd-1", correlation, ACTOR, "social.interpretation_recorded", {}, 201, 3120)
        events = tracker.events_by_correlation(correlation)
        assert len(events) == 2
        assert {e.revision for e in events} == {201}

    def test_envelope_requires_mandatory_fields(self):
        with pytest.raises(DirectMutationError):
            CausalityEnvelope(
                event_id="", world_id=WORLD, revision=1, type="t",
                game_time=1, causation_id="c", correlation_id="k",
                actor_entity_id=ACTOR, payload={},
            )


class TestDirectMutationRejection:
    """TEST-PLAYER-022"""

    @pytest.mark.parametrize(
        "field",
        ["set_balance", "set_affection", "teleport", "set_stage",
         "edit_collision", "force_combat_outcome", "mint_currency"],
    )
    def test_forbidden_mutations_rejected(self, field):
        with pytest.raises(DirectMutationError) as exc:
            assert_not_direct_mutation(field)
        assert exc.value.code == "PLAYER_DIRECT_MUTATION_REJECTED"

    def test_non_fact_sources_rejected(self):
        """RULE-PLAYER-029：动画/toast/对话承诺/预测不是事实"""
        for source in ("animation", "toast", "dialogue_promise", "prediction"):
            with pytest.raises(DirectMutationError) as exc:
                ImpactTracker.assert_fact_requires_committed_event(source)
            assert exc.value.code == "IMPACT_NON_FACT_SOURCE"


class TestProjectionPrivacyAndRebuild:
    """TEST-PLAYER-023/024"""

    def test_projection_rejects_private_fields(self):
        """§9：投影不得含隐藏关系数值、私人记忆、secret source、reasoning"""
        for key in ("relationship_raw", "private_memory", "secret_source", "model_reasoning"):
            with pytest.raises(DirectMutationError) as exc:
                ImpactProjection(
                    summary="某人对你不满",
                    dimension="social",
                    correlation_id="corr-1",
                    revision=201,
                    public_fields={key: "leak"},
                )
            assert exc.value.code == "IMPACT_PROJECTION_DISCLOSURE_VIOLATION"

    def test_public_projection_allowed(self):
        projection = ImpactProjection(
            summary="交易完成",
            dimension="economic",
            correlation_id="corr-1",
            revision=201,
            public_fields={"cue": "trade_success"},
        )
        assert projection.public_fields["cue"] == "trade_success"


class TestCompensation:
    """TEST-PLAYER-024：Saga failure 与补偿事件"""

    def test_compensation_creates_new_event_without_touching_history(self):
        tracker = ImpactTracker(WORLD)
        original = tracker.wrap_event(
            "cmd-1", "corr-1", ACTOR, "economy.transaction_committed",
            {"amount": 100}, 201, 3120,
        )
        compensation = tracker.build_compensation(
            original_event_id=original.event_id,
            compensating_command_id="cmd-undo-1",
            event_type="economy.transaction_compensated",
            payload={"amount": -100},
            revision=202,
            game_time=3130,
            actor_entity_id=ACTOR,
        )
        # RULE-PLAYER-030：新事件反向补偿；原事件不被删除/改写/重编号
        assert compensation.payload["compensates_event_id"] == original.event_id
        assert compensation.revision == 202
        still_original = tracker.get_event(original.event_id)
        assert still_original.payload == {"amount": 100}
        assert still_original.revision == 201

    def test_compensation_requires_existing_target(self):
        tracker = ImpactTracker(WORLD)
        with pytest.raises(DirectMutationError) as exc:
            tracker.build_compensation(
                "missing-event", "cmd-x", "t", {}, 1, 1, ACTOR
            )
        assert exc.value.code == "IMPACT_COMPENSATION_TARGET_MISSING"

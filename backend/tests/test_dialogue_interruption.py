"""
TEST-DIALOGUE-013/014：打断、退出与取消（DOC-DIALOGUE-007）

- TEST-DIALOGUE-013：RULE-DIALOGUE-038/039 优先级全序、严格更高才抢占、在途取消
- TEST-DIALOGUE-014：RULE-DIALOGUE-042/044 恢复窗 30 游戏分钟、超窗映射与重放幂等
"""

import pytest

from src.dialogue import (
    INTERRUPT_PRIORITY,
    EndedReason,
    InterruptCommand,
    InterruptDecision,
    InterruptSource,
    InterruptionArbiter,
)
from src.dialogue.constants import INTERRUPT_TO_ENDED_REASON, RESUME_WINDOW_GAME_MINUTES

CONV = "01K1CVRX000000000000000001"


def _command(source: InterruptSource, command_id: str = "cmd-int", conversation_id: str = CONV) -> InterruptCommand:
    return InterruptCommand(
        command_id=command_id,
        conversation_id=conversation_id,
        interrupt_source=source,
        source_event_id="evt-1",
    )


class TestInterruptPriority:
    """TEST-DIALOGUE-013"""

    def test_priority_total_order(self):
        assert INTERRUPT_PRIORITY[InterruptSource.WORLD_TEARDOWN] == 100
        assert INTERRUPT_PRIORITY[InterruptSource.COMBAT_ENCOUNTER] == 80
        assert INTERRUPT_PRIORITY[InterruptSource.SAFETY_EMERGENCY] == 70
        assert INTERRUPT_PRIORITY[InterruptSource.PARTICIPANT_EXIT] == 50
        assert INTERRUPT_PRIORITY[InterruptSource.CONDITION_LOST] == 50
        assert INTERRUPT_PRIORITY[InterruptSource.HIGHER_PRIORITY_CONVERSATION] == 40
        assert INTERRUPT_PRIORITY[InterruptSource.TIMEOUT] == 20

    @pytest.mark.parametrize("source", list(InterruptSource))
    def test_strictly_higher_priority_grants(self, source):
        arbiter = InterruptionArbiter()
        result = arbiter.adjudicate(
            _command(source), conversation_is_terminal=False,
            current_activity_priority=INTERRUPT_PRIORITY[source] - 1,
            current_game_time=100,
        )
        assert result.decision is InterruptDecision.GRANTED

    @pytest.mark.parametrize("source", list(InterruptSource))
    def test_equal_or_lower_priority_rejected(self, source):
        for current in (INTERRUPT_PRIORITY[source], INTERRUPT_PRIORITY[source] + 10):
            arbiter = InterruptionArbiter()
            result = arbiter.adjudicate(
                _command(source), conversation_is_terminal=False,
                current_activity_priority=current,
                current_game_time=100,
            )
            assert result.decision is InterruptDecision.REJECTED_LOWER_PRIORITY

    def test_terminal_conversation_rejected(self):
        arbiter = InterruptionArbiter()
        result = arbiter.adjudicate(
            _command(InterruptSource.WORLD_TEARDOWN), conversation_is_terminal=True,
            current_activity_priority=0, current_game_time=100,
        )
        assert result.decision is InterruptDecision.REJECTED_TERMINAL_STATE

    def test_immediate_interrupt_cancels_in_flight(self):
        arbiter = InterruptionArbiter()
        result = arbiter.adjudicate(
            _command(InterruptSource.COMBAT_ENCOUNTER), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
            in_flight_model_request_ids=("req-1", "req-2"),
            pending_intent_candidate_ids=("cand-1",),
        )
        assert result.decision is InterruptDecision.GRANTED
        # RULE-DIALOGUE-039/041：在途模型请求取消与候选过期随打断原子提交
        assert result.cancelled_model_request_ids == ("req-1", "req-2")
        assert result.expired_intent_candidate_ids == ("cand-1",)
        assert result.resume_deadline_game_time == 100 + RESUME_WINDOW_GAME_MINUTES

    def test_two_sources_same_tick_keeps_highest(self):
        arbiter = InterruptionArbiter()
        arbiter.adjudicate(
            _command(InterruptSource.PARTICIPANT_EXIT, "cmd-1"), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
        )
        arbiter.adjudicate(
            _command(InterruptSource.COMBAT_ENCOUNTER, "cmd-2"), conversation_is_terminal=False,
            current_activity_priority=50, current_game_time=100,
        )
        # 次高源仅作审计附注：超窗 ended reason 仍按最高源映射
        _, ended = arbiter.check_resume(CONV, 1000, conditions_still_met=True, interrupt_source_cleared=True)
        assert ended is EndedReason.PARTICIPANT_UNAVAILABLE  # combat，而非 participant_left

    def test_existing_higher_source_survives_lower_arrival(self):
        arbiter = InterruptionArbiter()
        arbiter.adjudicate(
            _command(InterruptSource.COMBAT_ENCOUNTER, "cmd-1"), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
        )
        arbiter.adjudicate(
            _command(InterruptSource.PARTICIPANT_EXIT, "cmd-2"), conversation_is_terminal=False,
            current_activity_priority=40, current_game_time=100,
        )
        _, ended = arbiter.check_resume(CONV, 1000, conditions_still_met=True, interrupt_source_cleared=True)
        assert ended is EndedReason.PARTICIPANT_UNAVAILABLE  # combat 记录不被 exit 覆盖


class TestResumeWindow:
    """TEST-DIALOGUE-014"""

    def test_replay_returns_duplicate_with_original_payload(self):
        arbiter = InterruptionArbiter()
        command = _command(InterruptSource.SAFETY_EMERGENCY)
        first = arbiter.adjudicate(
            command, conversation_is_terminal=False, current_activity_priority=0,
            current_game_time=100, in_flight_model_request_ids=("req-1",),
        )
        second = arbiter.adjudicate(
            command, conversation_is_terminal=False, current_activity_priority=0,
            current_game_time=200, in_flight_model_request_ids=("req-other",),
        )
        assert second.decision is InterruptDecision.DUPLICATE
        assert second.resume_deadline_game_time == first.resume_deadline_game_time
        assert second.cancelled_model_request_ids == ("req-1",)

    def test_resume_within_window_requires_conditions_and_clearance(self):
        arbiter = InterruptionArbiter()
        arbiter.adjudicate(
            _command(InterruptSource.CONDITION_LOST), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
        )
        can_resume, ended = arbiter.check_resume(CONV, 130, True, True)
        assert (can_resume, ended) == (True, None)
        # 条件未恢复或打断源未解除 → 留在 interrupted
        assert arbiter.check_resume(CONV, 130, False, True) == (False, None)
        assert arbiter.check_resume(CONV, 130, True, False) == (False, None)

    def test_resume_window_boundary(self):
        arbiter = InterruptionArbiter()
        arbiter.adjudicate(
            _command(InterruptSource.TIMEOUT), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
        )
        assert arbiter.resume_deadline(CONV) == 130
        assert RESUME_WINDOW_GAME_MINUTES == 30
        # 截止时刻本身仍在窗内，超过即超窗
        assert arbiter.check_resume(CONV, 130, True, True)[0] is True
        can_resume, ended = arbiter.check_resume(CONV, 131, True, True)
        assert can_resume is False
        assert ended is EndedReason.TIMEOUT

    @pytest.mark.parametrize(
        "source,expected_reason",
        [
            (InterruptSource.COMBAT_ENCOUNTER, EndedReason.PARTICIPANT_UNAVAILABLE),
            (InterruptSource.SAFETY_EMERGENCY, EndedReason.PARTICIPANT_UNAVAILABLE),
            (InterruptSource.TIMEOUT, EndedReason.TIMEOUT),
            (InterruptSource.PARTICIPANT_EXIT, EndedReason.PARTICIPANT_LEFT),
            (InterruptSource.CONDITION_LOST, EndedReason.PARTICIPANT_LEFT),
            (InterruptSource.HIGHER_PRIORITY_CONVERSATION, EndedReason.SUPERSEDED),
            (InterruptSource.WORLD_TEARDOWN, EndedReason.WORLD_TEARDOWN),
        ],
    )
    def test_expired_window_maps_to_ended_reason(self, source, expected_reason):
        assert INTERRUPT_TO_ENDED_REASON[source] is expected_reason
        arbiter = InterruptionArbiter()
        arbiter.adjudicate(
            _command(source), conversation_is_terminal=False,
            current_activity_priority=0, current_game_time=100,
        )
        can_resume, ended = arbiter.check_resume(CONV, 131, True, True)
        assert can_resume is False
        assert ended is expected_reason

    def test_unknown_conversation_cannot_resume(self):
        arbiter = InterruptionArbiter()
        assert arbiter.check_resume(CONV, 100, True, True) == (False, None)
        assert arbiter.resume_deadline(CONV) is None

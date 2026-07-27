"""
TEST-DIALOGUE-015/016：群体对话与旁听（DOC-DIALOGUE-008）

- TEST-DIALOGUE-015：RULE-DIALOGUE-045..048 上限 4、轮次优先级、拒收无轮响应与降员
- TEST-DIALOGUE-016：RULE-DIALOGUE-049..051 旁听矩阵（127/128/129 × LoS × privacy）与 8 人截断
"""

import pytest

from src.dialogue import (
    BystanderGeometry,
    ConversationPrivacy,
    GrantReason,
    GroupDialogueError,
    TurnScheduler,
    adjudicate_departure,
    check_participant_cap,
    evaluate_overhear,
)
from src.dialogue.constants import MAX_OVERHEAR_CANDIDATES, MAX_PARTICIPANTS, OVERHEAR_RANGE_WU
from src.dialogue.group import assert_bystander_has_no_rights

from ai_helpers import ULID_A, ULID_B, ULID_C, ULID_D

CONV = "01K1CVRX000000000000000001"
# ULID 字典序：ULID_B < ULID_D < ULID_C
RESIDENTS = [ULID_C, ULID_B, ULID_D]


class TestParticipantCapAndDeparture:
    """TEST-DIALOGUE-015（容量与降员部分）"""

    def test_cap_allows_three_rejects_four(self):
        assert MAX_PARTICIPANTS == 4
        check_participant_cap(3)
        with pytest.raises(GroupDialogueError) as excinfo:
            check_participant_cap(4)
        assert excinfo.value.code == "group_full"

    def test_departure_rules(self):
        assert adjudicate_departure(3) == "continue_reduced"
        assert adjudicate_departure(2) == "continue_reduced"
        assert adjudicate_departure(1) == "end_participant_exit"


class TestTurnScheduler:
    """TEST-DIALOGUE-015（轮次部分）"""

    def test_addressed_reply_has_highest_priority(self):
        scheduler = TurnScheduler()
        grant = scheduler.grant_next(CONV, RESIDENTS, 0, last_addressed_id=ULID_C)
        assert grant.granted_to == ULID_C
        assert grant.grant_reason is GrantReason.ADDRESSED_REPLY

    def test_pending_question_beats_longest_idle(self):
        scheduler = TurnScheduler()
        grant = scheduler.grant_next(CONV, RESIDENTS, 0, pending_question_ids=[ULID_D, ULID_B])
        # 并列按 participant_id 字典序（ULID_B < ULID_D）
        assert grant.granted_to == ULID_B
        assert grant.grant_reason is GrantReason.PENDING_QUESTION

    def test_longest_idle_with_lexicographic_tie_break(self):
        scheduler = TurnScheduler()
        first = scheduler.grant_next(CONV, RESIDENTS, 0)
        assert first.granted_to == ULID_B  # 全员未发言 → 字典序最小
        assert first.grant_reason is GrantReason.LONGEST_IDLE

        scheduler.consume(CONV, first.turn_grant_id, ULID_B, 0)
        second = scheduler.grant_next(CONV, RESIDENTS, 1)
        assert second.granted_to == ULID_D  # C、D 均未发言，D 字典序更小

        scheduler.consume(CONV, second.turn_grant_id, ULID_D, 1)
        third = scheduler.grant_next(CONV, RESIDENTS, 2)
        assert third.granted_to == ULID_C  # 唯一未发言者

    def test_least_recently_spoke_wins_after_all_spoke(self):
        scheduler = TurnScheduler()
        for index, speaker in enumerate((ULID_B, ULID_D, ULID_C)):
            grant = scheduler.grant_next(CONV, RESIDENTS, index)
            scheduler.consume(CONV, grant.turn_grant_id, speaker, index)
        grant = scheduler.grant_next(CONV, RESIDENTS, 3)
        assert grant.granted_to == ULID_B  # 最久未发言

    def test_at_most_one_active_grant(self):
        scheduler = TurnScheduler()
        scheduler.grant_next(CONV, RESIDENTS, 0)
        with pytest.raises(GroupDialogueError) as excinfo:
            scheduler.grant_next(CONV, RESIDENTS, 0)
        assert excinfo.value.code == "DIALOGUE_TURN_ALREADY_GRANTED"

    def test_no_resident_no_grant(self):
        scheduler = TurnScheduler()
        with pytest.raises(GroupDialogueError) as excinfo:
            scheduler.grant_next(CONV, [], 0)
        assert excinfo.value.code == "DIALOGUE_NO_RESIDENT_PARTICIPANT"

    def test_response_without_grant_rejected(self):
        scheduler = TurnScheduler()
        with pytest.raises(GroupDialogueError) as excinfo:
            scheduler.consume(CONV, "nonexistent", ULID_B, 0)
        assert excinfo.value.code == "DIALOGUE_TURN_GRANT_INVALID"

        grant = scheduler.grant_next(CONV, RESIDENTS, 0)
        with pytest.raises(GroupDialogueError) as excinfo:
            scheduler.consume(CONV, "wrong-grant-id", ULID_B, 0)
        assert excinfo.value.code == "DIALOGUE_TURN_GRANT_INVALID"

        with pytest.raises(GroupDialogueError) as excinfo:
            scheduler.consume(CONV, grant.turn_grant_id, ULID_C, 0)
        assert excinfo.value.code == "DIALOGUE_TURN_GRANT_HOLDER_MISMATCH"
        # 拒收不消费轮次，持轮者仍可提交
        scheduler.consume(CONV, grant.turn_grant_id, grant.granted_to, 0)
        assert not scheduler.has_active_grant(CONV)

    def test_revoke_tracks_consecutive_skips(self):
        scheduler = TurnScheduler()
        scheduler.grant_next(CONV, RESIDENTS, 0)
        skipped = scheduler.revoke(CONV)
        assert skipped == ULID_B
        assert scheduler.consecutive_skips(CONV, ULID_B) == 1
        scheduler.grant_next(CONV, RESIDENTS, 1, last_addressed_id=ULID_B)
        scheduler.revoke(CONV)
        assert scheduler.consecutive_skips(CONV, ULID_B) == 2

    def test_invalidate_for_end(self):
        scheduler = TurnScheduler()
        scheduler.grant_next(CONV, RESIDENTS, 0)
        scheduler.invalidate_for_end(CONV)
        assert not scheduler.has_active_grant(CONV)


class TestOverhear:
    """TEST-DIALOGUE-016"""

    def _geometry(self, bystander_id, distance, same_scene=True, los=True):
        return BystanderGeometry(
            bystander_id=bystander_id, same_scene=same_scene, distance_wu=distance, line_of_sight=los
        )

    def test_distance_boundary_127_128_129(self):
        candidates = [
            self._geometry(ULID_A, 127.0),
            self._geometry(ULID_B, 128.0),
            self._geometry(ULID_C, 129.0),
        ]
        events = evaluate_overhear(CONV, 0, ConversationPrivacy.PUBLIC, 84, candidates)
        assert OVERHEAR_RANGE_WU == 128.0
        assert {e.bystander_id for e in events} == {ULID_A, ULID_B}

    def test_los_and_scene_required(self):
        candidates = [
            self._geometry(ULID_A, 50.0, los=False),
            self._geometry(ULID_B, 50.0, same_scene=False),
            self._geometry(ULID_C, 50.0),
        ]
        events = evaluate_overhear(CONV, 0, ConversationPrivacy.PUBLIC, 84, candidates)
        assert [e.bystander_id for e in events] == [ULID_C]

    def test_private_conversation_never_overheard(self):
        candidates = [self._geometry(ULID_A, 10.0)]
        events = evaluate_overhear(CONV, 0, ConversationPrivacy.PRIVATE_REQUESTED, 84, candidates)
        assert events == []

    def test_event_payload(self):
        [event] = evaluate_overhear(
            CONV, 7, ConversationPrivacy.PUBLIC, 84, [self._geometry(ULID_A, 64.0)]
        )
        assert event.event_type == "dialogue.utterance_overheard/v1"
        assert event.conversation_id == CONV
        assert event.utterance_index == 7
        assert event.observed_revision == 84
        assert event.distance_wu == 64.0
        assert event.line_of_sight is True

    def test_candidates_truncated_to_eight_nearest(self):
        candidates = [self._geometry(f"01K1BYST{index:016d}XXXXXXXX", float(20 + index * 10)) for index in range(10)]
        events = evaluate_overhear(CONV, 0, ConversationPrivacy.PUBLIC, 84, candidates)
        assert MAX_OVERHEAR_CANDIDATES == 8
        assert len(events) == 8
        distances = [e.distance_wu for e in events]
        assert distances == sorted(distances)
        assert max(distances) == 90.0  # 最远被截断的是 100、110

    def test_bystander_never_in_participant_set(self):
        assert_bystander_has_no_rights(ULID_D, [ULID_A, ULID_B])
        with pytest.raises(GroupDialogueError) as excinfo:
            assert_bystander_has_no_rights(ULID_B, [ULID_A, ULID_B])
        assert excinfo.value.code == "DIALOGUE_BYSTANDER_IN_PARTICIPANT_SET"

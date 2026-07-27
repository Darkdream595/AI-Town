"""
TEST-DIALOGUE-001/002/028：会话状态机、Pause Token 生命周期与 teardown（DOC-DIALOGUE-001）

- TEST-DIALOGUE-001：RULE-DIALOGUE-001 合法迁移全通过、非法迁移 fail closed
- TEST-DIALOGUE-002：RULE-DIALOGUE-005/078 会话 Pause Token 恰一枚、随状态持放
- TEST-DIALOGUE-028：utterance 幂等、privacy 不可变、参与者独占与统一 teardown
"""

import pytest

from src.dialogue import (
    ConversationError,
    ConversationKind,
    ConversationPrivacy,
    ConversationRegistry,
    ConversationState,
    EndedReason,
)
from src.player.pause import PauseTokenLedger

from ai_helpers import ULID_A, ULID_B, ULID_C

WORLD = "01K1WRDX000000000000000001"

#: RULE-DIALOGUE-001 合法迁移表（STARTING 仅作起点，starting→active 原子完成）
_LEGAL = {
    ConversationState.ACTIVE: {
        ConversationState.AWAITING_PLAYER,
        ConversationState.AWAITING_MODEL,
        ConversationState.INTERRUPTED,
        ConversationState.ENDED,
    },
    ConversationState.AWAITING_PLAYER: {
        ConversationState.ACTIVE,
        ConversationState.AWAITING_MODEL,
        ConversationState.INTERRUPTED,
        ConversationState.ENDED,
    },
    ConversationState.AWAITING_MODEL: {
        ConversationState.ACTIVE,
        ConversationState.AWAITING_PLAYER,
        ConversationState.INTERRUPTED,
        ConversationState.ENDED,
    },
    ConversationState.INTERRUPTED: {ConversationState.ACTIVE, ConversationState.ENDED},
    ConversationState.ENDED: set(),
}
_ALL_STATES = set(ConversationState)


def _registry() -> ConversationRegistry:
    return ConversationRegistry(WORLD, PauseTokenLedger(world_id=WORLD))


def _start(registry: ConversationRegistry, **overrides):
    kwargs = {
        "command_id": "cmd-start",
        "initiator_id": ULID_A,
        "participant_ids": [ULID_A, ULID_B],
        "kind": ConversationKind.RESIDENT_TO_RESIDENT,
        "game_time": 100,
    }
    kwargs.update(overrides)
    return registry.start_conversation(**kwargs)


def _drive_to(registry: ConversationRegistry, conversation_id: str, target: ConversationState) -> None:
    """从 ACTIVE 一步驱动到目标状态（供状态机穷举的源状态准备）"""
    if target is ConversationState.ACTIVE:
        return
    registry.transition(conversation_id, target, command_id=f"drive-{target.value}")


class TestStateMachine:
    """TEST-DIALOGUE-001"""

    def test_start_is_atomic_starting_to_active(self):
        registry = _registry()
        conversation = _start(registry)
        assert conversation.state is ConversationState.ACTIVE
        events = registry.events()
        assert len(events) == 1
        assert events[0].from_state is ConversationState.STARTING
        assert events[0].to_state is ConversationState.ACTIVE
        assert events[0].event_type == "dialogue.conversation_state_changed/v1"

    @pytest.mark.parametrize(
        "from_state,to_state",
        [(f, t) for f, targets in _LEGAL.items() for t in targets],
    )
    def test_legal_transitions_commit(self, from_state, to_state):
        registry = _registry()
        conversation = _start(registry)
        _drive_to(registry, conversation.conversation_id, from_state)
        revision_before = registry.revision
        result = registry.transition(
            conversation.conversation_id, to_state, command_id=f"t-{from_state.value}-{to_state.value}"
        )
        assert result.state is to_state
        assert registry.revision == revision_before + 1
        event = registry.events()[-1]
        assert event.from_state is from_state
        assert event.to_state is to_state
        assert event.revision == registry.revision

    @pytest.mark.parametrize(
        "from_state,to_state",
        [(f, t) for f in _LEGAL for t in (_ALL_STATES - _LEGAL[f] - {ConversationState.STARTING})],
    )
    def test_illegal_transitions_fail_closed(self, from_state, to_state):
        registry = _registry()
        conversation = _start(registry)
        _drive_to(registry, conversation.conversation_id, from_state)
        revision_before = registry.revision
        with pytest.raises(ConversationError) as excinfo:
            registry.transition(
                conversation.conversation_id, to_state, command_id=f"bad-{from_state.value}-{to_state.value}"
            )
        assert excinfo.value.code == "DIALOGUE_TRANSITION_REJECTED"
        # fail closed：状态与 Revision 均不变
        assert registry.get(conversation.conversation_id).state is from_state
        assert registry.revision == revision_before

    @pytest.mark.parametrize("from_state", sorted(_LEGAL, key=lambda s: s.value))
    def test_transition_back_to_starting_always_rejected(self, from_state):
        registry = _registry()
        conversation = _start(registry)
        _drive_to(registry, conversation.conversation_id, from_state)
        with pytest.raises(ConversationError) as excinfo:
            registry.transition(
                conversation.conversation_id, ConversationState.STARTING, command_id="back-starting"
            )
        assert excinfo.value.code == "DIALOGUE_TRANSITION_REJECTED"

    def test_transition_replay_is_idempotent(self):
        registry = _registry()
        conversation = _start(registry)
        first = registry.transition(
            conversation.conversation_id, ConversationState.AWAITING_PLAYER, command_id="t-replay"
        )
        revision_after_first = registry.revision
        second = registry.transition(
            conversation.conversation_id, ConversationState.AWAITING_PLAYER, command_id="t-replay"
        )
        assert first is second
        assert registry.revision == revision_after_first
        assert len(registry.events()) == 2  # start + 一次迁移

    def test_end_conversation_idempotent(self):
        registry = _registry()
        conversation = _start(registry)
        registry.end_conversation(conversation.conversation_id, "end-1", EndedReason.COMPLETED, game_time=120)
        events_after_first = len(registry.events())
        again = registry.end_conversation(
            conversation.conversation_id, "end-2", EndedReason.ADMIN, game_time=130
        )
        assert again.ended_reason is EndedReason.COMPLETED  # 首次结果不被覆盖
        assert len(registry.events()) == events_after_first


class TestPauseTokenLifecycle:
    """TEST-DIALOGUE-002"""

    def _player_conversation(self, registry: ConversationRegistry):
        return _start(
            registry,
            kind=ConversationKind.PLAYER_TO_RESIDENT,
            player_participant_id=ULID_A,
        )

    def test_acquire_on_start_with_player(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        conversation = self._player_conversation(registry)
        assert ledger.is_paused()
        tokens = ledger.active_tokens()
        assert len(tokens) == 1
        assert tokens[0].owner == "dialogue"
        assert tokens[0].reason == "dialogue_input"
        assert conversation.pause_token_id == tokens[0].token_id

    def test_resident_only_conversation_holds_no_token(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        conversation = _start(registry)
        assert conversation.pause_token_id is None
        assert not ledger.is_paused()
        registry.transition(conversation.conversation_id, ConversationState.AWAITING_MODEL, command_id="t1")
        registry.transition(conversation.conversation_id, ConversationState.INTERRUPTED, command_id="t2")
        assert not ledger.is_paused()

    def test_exactly_one_token_across_interactive_states(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        conversation = self._player_conversation(registry)
        held_token = conversation.pause_token_id
        registry.transition(conversation.conversation_id, ConversationState.AWAITING_PLAYER, command_id="t1")
        registry.transition(conversation.conversation_id, ConversationState.AWAITING_MODEL, command_id="t2")
        registry.transition(conversation.conversation_id, ConversationState.ACTIVE, command_id="t3")
        # 交互态之间迁移不新增 token，仍恰有一枚且为同一枚
        assert registry.active_token_ids() == [held_token]
        assert len(ledger.active_tokens()) == 1

    def test_interrupted_releases_and_resume_reacquires(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        conversation = self._player_conversation(registry)
        original_token = conversation.pause_token_id

        registry.transition(conversation.conversation_id, ConversationState.INTERRUPTED, command_id="t-int")
        assert conversation.pause_token_id is None
        assert not ledger.is_paused()

        registry.transition(conversation.conversation_id, ConversationState.ACTIVE, command_id="t-resume")
        assert conversation.pause_token_id is not None
        assert conversation.pause_token_id != original_token
        assert ledger.is_paused()

    def test_end_releases_token(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        conversation = self._player_conversation(registry)
        registry.end_conversation(conversation.conversation_id, "end-1", EndedReason.COMPLETED)
        assert conversation.pause_token_id is None
        assert not ledger.is_paused()
        assert registry.active_token_ids() == []


class TestUtterancePrivacyAndTeardown:
    """TEST-DIALOGUE-028"""

    def test_utterance_indices_contiguous_and_append_only(self):
        registry = _registry()
        conversation = _start(registry)
        for expected_index in range(3):
            utterance = registry.commit_utterance(
                conversation.conversation_id,
                command_id=f"u-{expected_index}",
                speaker_id=ULID_A if expected_index % 2 == 0 else ULID_B,
                text=f"第 {expected_index} 句",
                game_time=100 + expected_index,
            )
            assert utterance.utterance_index == expected_index
        history = registry.utterances(conversation.conversation_id)
        assert [u.utterance_index for u in history] == [0, 1, 2]

    def test_utterance_replay_yields_single_entry(self):
        registry = _registry()
        conversation = _start(registry)
        first = registry.commit_utterance(
            conversation.conversation_id, command_id="u-replay", speaker_id=ULID_A, text="你好", game_time=100
        )
        revision_after_first = registry.revision
        second = registry.commit_utterance(
            conversation.conversation_id, command_id="u-replay", speaker_id=ULID_A, text="你好", game_time=100
        )
        assert first is second
        assert len(registry.utterances(conversation.conversation_id)) == 1
        assert registry.revision == revision_after_first

    def test_utterance_rejected_for_non_participant_and_ended(self):
        registry = _registry()
        conversation = _start(registry)
        with pytest.raises(ConversationError) as excinfo:
            registry.commit_utterance(
                conversation.conversation_id, command_id="u-x", speaker_id=ULID_C, text="旁观", game_time=100
            )
        assert excinfo.value.code == "DIALOGUE_SPEAKER_NOT_PARTICIPANT"

        registry.end_conversation(conversation.conversation_id, "end-1", EndedReason.COMPLETED)
        with pytest.raises(ConversationError) as excinfo:
            registry.commit_utterance(
                conversation.conversation_id, command_id="u-y", speaker_id=ULID_A, text="太晚", game_time=101
            )
        assert excinfo.value.code == "DIALOGUE_CONVERSATION_ENDED"

    def test_privacy_fixed_at_creation(self):
        registry = _registry()
        conversation = _start(registry, privacy=ConversationPrivacy.PRIVATE_REQUESTED)
        assert conversation.privacy is ConversationPrivacy.PRIVATE_REQUESTED
        registry.assert_privacy_immutable(
            conversation.conversation_id, ConversationPrivacy.PRIVATE_REQUESTED
        )
        with pytest.raises(ConversationError) as excinfo:
            registry.assert_privacy_immutable(conversation.conversation_id, ConversationPrivacy.PUBLIC)
        assert excinfo.value.code == "DIALOGUE_PRIVACY_IMMUTABLE"

    def test_privacy_defaults_public(self):
        registry = _registry()
        conversation = _start(registry)
        assert conversation.privacy is ConversationPrivacy.PUBLIC

    def test_participant_exclusivity(self):
        registry = _registry()
        first = _start(registry)
        assert registry.participant_of(ULID_B) == first.conversation_id
        with pytest.raises(ConversationError) as excinfo:
            _start(registry, command_id="cmd-start-2", participant_ids=[ULID_B, ULID_C])
        assert excinfo.value.code == "DIALOGUE_PARTICIPANT_BUSY"

        registry.end_conversation(first.conversation_id, "end-1", EndedReason.COMPLETED)
        assert registry.participant_of(ULID_B) is None
        second = _start(registry, command_id="cmd-start-3", participant_ids=[ULID_B, ULID_C])
        assert registry.participant_of(ULID_B) == second.conversation_id

    def test_teardown_world_ends_everything_without_leaks(self):
        ledger = PauseTokenLedger(world_id=WORLD)
        registry = ConversationRegistry(WORLD, ledger)
        player_conversation = _start(
            registry,
            command_id="cmd-start-p",
            kind=ConversationKind.PLAYER_TO_RESIDENT,
            player_participant_id=ULID_A,
        )
        resident_conversation = _start(
            registry,
            command_id="cmd-start-r",
            initiator_id=ULID_C,
            participant_ids=[ULID_C, "01K1AB2CD3EF4GH5JK6MNP7QRZ"],
        )
        registry.transition(
            resident_conversation.conversation_id, ConversationState.INTERRUPTED, command_id="t-int"
        )

        registry.teardown_world(command_id="td", game_time=999)

        for conversation in (player_conversation, resident_conversation):
            assert conversation.state is ConversationState.ENDED
            assert conversation.ended_reason is EndedReason.WORLD_TEARDOWN
        assert not ledger.is_paused()
        assert registry.active_token_ids() == []
        assert registry.participant_of(ULID_A) is None
        assert registry.participant_of(ULID_C) is None

"""
会话生命周期与状态机（DOC-DIALOGUE-001）

- RULE-DIALOGUE-001：starting → active ⇄ awaiting_player/awaiting_model →
  interrupted → active/ended；ended 终态；非法迁移 fail closed
- RULE-DIALOGUE-002：迁移只由服务器提交；Client/模型/动画不构成事实
- RULE-DIALOGUE-003：迁移 + 事件 + 幂等结果同事务；失败 Revision 不增长
- RULE-DIALOGUE-004：同一参与者同时最多一个非 ended 会话
- RULE-DIALOGUE-005/078：会话 Pause Token 生命周期（与 PLAYER 输入框 token 独立）
- RULE-DIALOGUE-006：utterance 序号从 0 连续、只追加；重放至多一条
- RULE-DIALOGUE-079：privacy 创建时固定
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..foundation import generate_ulid
from ..player.pause import PauseTokenError, PauseTokenLedger
from .constants import (
    ConversationKind,
    ConversationPrivacy,
    ConversationState,
    DIALOGUE_PAUSE_OWNER,
    DIALOGUE_PAUSE_REASON,
    EndedReason,
)


class ConversationError(Exception):
    """会话操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-DIALOGUE-001 合法迁移表
_ALLOWED_TRANSITIONS: Dict[ConversationState, Set[ConversationState]] = {
    ConversationState.STARTING: {ConversationState.ACTIVE},
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
    ConversationState.INTERRUPTED: {
        ConversationState.ACTIVE,
        ConversationState.ENDED,
    },
    ConversationState.ENDED: set(),
}

#: RULE-DIALOGUE-005：token 绑定的全部交互态
_TOKEN_HELD_STATES = frozenset(
    {
        ConversationState.ACTIVE,
        ConversationState.AWAITING_PLAYER,
        ConversationState.AWAITING_MODEL,
    }
)


@dataclass(frozen=True)
class Utterance:
    """RULE-DIALOGUE-006：只追加的已提交发言"""

    utterance_index: int
    speaker_id: str
    text: str
    committed_revision: int
    game_time: int
    command_id: str
    speech_act_type: Optional[str] = None
    addressed_entity_id: Optional[str] = None


@dataclass(frozen=True)
class StateChangeEvent:
    """dialogue.conversation_state_changed/v1 的最小载荷"""

    event_id: str
    conversation_id: str
    from_state: ConversationState
    to_state: ConversationState
    revision: int
    interrupt_source: Optional[str] = None
    event_type: str = "dialogue.conversation_state_changed/v1"


@dataclass
class Conversation:
    """DES-DIALOGUE-001 投影的运行时形态"""

    conversation_id: str
    world_id: str
    kind: ConversationKind
    privacy: ConversationPrivacy
    participant_ids: List[str]
    initiator_id: str
    state: ConversationState
    created_revision: int
    created_game_time: int
    last_activity_game_time: int
    pause_token_id: Optional[str] = None
    ended_reason: Optional[EndedReason] = None
    player_participant_id: Optional[str] = None
    schema_version: int = 1

    @property
    def has_player(self) -> bool:
        return self.player_participant_id is not None

    @property
    def is_terminal(self) -> bool:
        return self.state is ConversationState.ENDED


class ConversationRegistry:
    """
    会话聚合注册表：状态机、参与者独占、Pause Token 生命周期与事件发射。

    pause_ledger 复用 player.pause.PauseTokenLedger（TIME 域 ledger 就位后
    应替换为其 canonical 实现，owner 字符串语义不变）。
    """

    def __init__(self, world_id: str, pause_ledger: PauseTokenLedger) -> None:
        self._world_id = world_id
        self._pause_ledger = pause_ledger
        self._conversations: Dict[str, Conversation] = {}
        self._utterances: Dict[str, List[Utterance]] = {}
        self._events: List[StateChangeEvent] = []
        self._revision = 0
        # RULE-DIALOGUE-004：participant_id -> conversation_id（非 ended）
        self._active_by_participant: Dict[str, str] = {}
        # 幂等：(command_id) -> 原结果
        self._command_results: Dict[str, object] = {}
        self._utterance_commands: Dict[Tuple[str, str], int] = {}

    @property
    def revision(self) -> int:
        return self._revision

    def events(self) -> List[StateChangeEvent]:
        return list(self._events)

    # -- 创建 --

    def start_conversation(
        self,
        command_id: str,
        initiator_id: str,
        participant_ids: List[str],
        kind: ConversationKind,
        game_time: int,
        privacy: Optional[ConversationPrivacy] = None,
        player_participant_id: Optional[str] = None,
    ) -> Conversation:
        """
        §6 第 1 步：创建会话（starting → active 原子完成）。

        RULE-DIALOGUE-079：居民发起由 Commit Adapter 传入 privacy；
        玩家发起省略时默认 public。创建后不可变更。
        """
        if command_id in self._command_results:
            return self._command_results[command_id]  # type: ignore[return-value]

        # RULE-DIALOGUE-004：参与者独占检查
        for pid in participant_ids:
            existing = self._active_by_participant.get(pid)
            if existing is not None:
                raise ConversationError(
                    "DIALOGUE_PARTICIPANT_BUSY",
                    f"participant {pid} already in conversation {existing}",
                )

        resolved_privacy = privacy or ConversationPrivacy.PUBLIC
        conversation = Conversation(
            conversation_id=generate_ulid(),
            world_id=self._world_id,
            kind=kind,
            privacy=resolved_privacy,
            participant_ids=list(participant_ids),
            initiator_id=initiator_id,
            state=ConversationState.STARTING,
            created_revision=self._revision,
            created_game_time=game_time,
            last_activity_game_time=game_time,
            player_participant_id=player_participant_id,
        )

        # starting → active：含玩家时同事务 acquire 会话 Pause Token
        self._conversations[conversation.conversation_id] = conversation
        self._utterances[conversation.conversation_id] = []
        self._transition(conversation, ConversationState.ACTIVE, command_id=command_id)

        for pid in participant_ids:
            self._active_by_participant[pid] = conversation.conversation_id

        self._command_results[command_id] = conversation
        return conversation

    # -- 状态迁移 --

    def transition(
        self,
        conversation_id: str,
        to_state: ConversationState,
        command_id: str,
        interrupt_source: Optional[str] = None,
        game_time: int = 0,
    ) -> Conversation:
        """RULE-DIALOGUE-001/003：校验后提交迁移；非法迁移 fail closed"""
        idem_key = f"{command_id}:{conversation_id}:{to_state.value}"
        if idem_key in self._command_results:
            return self._command_results[idem_key]  # type: ignore[return-value]

        conversation = self._require(conversation_id)
        result = self._transition(
            conversation, to_state, command_id=command_id,
            interrupt_source=interrupt_source, game_time=game_time,
        )
        self._command_results[idem_key] = result
        return result

    def _transition(
        self,
        conversation: Conversation,
        to_state: ConversationState,
        command_id: str,
        interrupt_source: Optional[str] = None,
        game_time: int = 0,
    ) -> Conversation:
        from_state = conversation.state
        if to_state not in _ALLOWED_TRANSITIONS.get(from_state, set()):
            # fail closed 并记录 rejected 结果
            raise ConversationError(
                "DIALOGUE_TRANSITION_REJECTED",
                f"{from_state.value} -> {to_state.value} not allowed",
            )

        # Pause Token 生命周期（RULE-DIALOGUE-005）
        if conversation.has_player:
            if to_state in (ConversationState.INTERRUPTED, ConversationState.ENDED):
                self._release_conversation_token(conversation, command_id)
            elif to_state is ConversationState.ACTIVE and from_state in (
                ConversationState.STARTING,
                ConversationState.INTERRUPTED,
            ):
                # starting→active 同事务 acquire；interrupted→active 重新 acquire
                self._acquire_conversation_token(
                    conversation, command_id, self._revision
                )

        conversation.state = to_state
        if game_time:
            conversation.last_activity_game_time = game_time
        self._revision += 1
        self._events.append(
            StateChangeEvent(
                event_id=generate_ulid(),
                conversation_id=conversation.conversation_id,
                from_state=from_state,
                to_state=to_state,
                revision=self._revision,
                interrupt_source=interrupt_source,
            )
        )

        if to_state is ConversationState.ENDED:
            for pid in conversation.participant_ids:
                self._active_by_participant.pop(pid, None)
        return conversation

    def _acquire_conversation_token(
        self, conversation: Conversation, command_id: str, revision: int
    ) -> None:
        """RULE-DIALOGUE-005：恰一枚 blocking token，owner=dialogue"""
        if conversation.pause_token_id is not None:
            raise ConversationError(
                "DIALOGUE_TOKEN_ALREADY_HELD",
                "conversation must not hold two pause tokens",
            )
        try:
            token = self._pause_ledger.acquire(
                command_id=f"{command_id}:{conversation.conversation_id}:pause",
                owner=DIALOGUE_PAUSE_OWNER,
                reason=DIALOGUE_PAUSE_REASON,
                revision=revision,
            )
        except PauseTokenError as exc:
            raise ConversationError(exc.code) from exc
        conversation.pause_token_id = token.token_id

    def _release_conversation_token(
        self, conversation: Conversation, command_id: str
    ) -> None:
        """RULE-DIALOGUE-005/078：以同一 token_id 幂等释放；只释放本域 token"""
        if conversation.pause_token_id is None:
            return
        try:
            self._pause_ledger.release(
                command_id=f"{command_id}:{conversation.conversation_id}:release",
                token_id=conversation.pause_token_id,
                owner=DIALOGUE_PAUSE_OWNER,
            )
        except PauseTokenError as exc:
            raise ConversationError(exc.code) from exc
        conversation.pause_token_id = None

    # -- Utterance --

    def commit_utterance(
        self,
        conversation_id: str,
        command_id: str,
        speaker_id: str,
        text: str,
        game_time: int,
        speech_act_type: Optional[str] = None,
        addressed_entity_id: Optional[str] = None,
    ) -> Utterance:
        """
        RULE-DIALOGUE-006：序号从 0 连续、只追加；
        重放相同 command 最多产生一条 utterance。
        """
        idem_key = (conversation_id, command_id)
        if idem_key in self._utterance_commands:
            index = self._utterance_commands[idem_key]
            return self._utterances[conversation_id][index]

        conversation = self._require(conversation_id)
        if conversation.is_terminal:
            raise ConversationError(
                "DIALOGUE_CONVERSATION_ENDED",
                "cannot commit utterance to ended conversation",
            )
        if speaker_id not in conversation.participant_ids:
            raise ConversationError(
                "DIALOGUE_SPEAKER_NOT_PARTICIPANT",
                f"{speaker_id} not in participant set",
            )

        history = self._utterances[conversation_id]
        utterance = Utterance(
            utterance_index=len(history),
            speaker_id=speaker_id,
            text=text,
            committed_revision=self._revision + 1,
            game_time=game_time,
            command_id=command_id,
            speech_act_type=speech_act_type,
            addressed_entity_id=addressed_entity_id,
        )
        history.append(utterance)
        self._revision += 1
        conversation.last_activity_game_time = game_time
        self._utterance_commands[idem_key] = utterance.utterance_index
        return utterance

    def utterances(self, conversation_id: str) -> List[Utterance]:
        return list(self._utterances.get(conversation_id, []))

    # -- 终结与恢复 --

    def end_conversation(
        self,
        conversation_id: str,
        command_id: str,
        reason: EndedReason,
        game_time: int = 0,
    ) -> Conversation:
        """§6 第 4 步 / §7：正常终结；统一 teardown 释放资源"""
        conversation = self._require(conversation_id)
        if conversation.is_terminal:
            return conversation  # 幂等
        conversation.ended_reason = reason
        self.transition(
            conversation_id, ConversationState.ENDED, command_id, game_time=game_time
        )
        return conversation

    def teardown_world(self, command_id: str, game_time: int) -> None:
        """§7：世界关闭时所有非终态会话以 world_teardown 终结，不留悬挂 token"""
        for conversation in list(self._conversations.values()):
            if not conversation.is_terminal:
                conversation.ended_reason = EndedReason.WORLD_TEARDOWN
                if conversation.state is ConversationState.STARTING:
                    conversation.state = ConversationState.ACTIVE
                self._transition(
                    conversation,
                    ConversationState.ENDED,
                    command_id=f"{command_id}:{conversation.conversation_id}",
                    interrupt_source="world_teardown",
                    game_time=game_time,
                )

    def end_reason(self, conversation_id: str) -> Optional[EndedReason]:
        return self._require(conversation_id).ended_reason

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._conversations.get(conversation_id)

    def _require(self, conversation_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationError(
                "DIALOGUE_CONVERSATION_NOT_FOUND", f"unknown {conversation_id}"
            )
        return conversation

    def assert_privacy_immutable(
        self, conversation_id: str, new_privacy: ConversationPrivacy
    ) -> None:
        """RULE-DIALOGUE-079：privacy 创建后任何命令都无法变更"""
        conversation = self._require(conversation_id)
        if new_privacy is not conversation.privacy:
            raise ConversationError(
                "DIALOGUE_PRIVACY_IMMUTABLE",
                "privacy is fixed at creation; end and recreate to change it",
            )

    def participant_of(self, participant_id: str) -> Optional[str]:
        """RULE-DIALOGUE-004：查询参与者当前所属非终态会话"""
        return self._active_by_participant.get(participant_id)

    def active_token_ids(self) -> List[str]:
        """泄漏检查（§9/§10）：所有会话当前持有的 token"""
        return [
            c.pause_token_id
            for c in self._conversations.values()
            if c.pause_token_id is not None
        ]

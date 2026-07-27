"""
群体对话与旁听（DOC-DIALOGUE-008）

- RULE-DIALOGUE-045：participant set 上限 4
- RULE-DIALOGUE-046：Turn Scheduler 唯一发言授权；至多一位居民持轮、
  至多一个在途模型请求
- RULE-DIALOGUE-047：轮次确定性优先级 addressed > pending question >
  longest idle；玩家不占轮次
- RULE-DIALOGUE-048：降员规则
- RULE-DIALOGUE-049..051：旁听条件、witness 事件、旁听者无权限
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    MAX_OVERHEAR_CANDIDATES,
    MAX_PARTICIPANTS,
    OVERHEAR_RANGE_WU,
    TURN_GRANT_EXPIRES_REAL_MS,
    ConversationPrivacy,
    GrantReason,
)


class GroupDialogueError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class TurnGrant:
    """DES-DIALOGUE-008 轮次授权"""

    turn_grant_id: str
    conversation_id: str
    granted_to: str
    granted_for_utterance_index: int
    grant_reason: GrantReason
    expires_real_ms: int = TURN_GRANT_EXPIRES_REAL_MS


@dataclass(frozen=True)
class OverheardEvent:
    """DES-DIALOGUE-008 dialogue.utterance_overheard/v1"""

    event_type: str
    bystander_id: str
    conversation_id: str
    utterance_index: int
    observed_revision: int
    distance_wu: float
    line_of_sight: bool


class TurnScheduler:
    """
    确定性轮次调度器（RULE-DIALOGUE-046/047）。

    每会话至多一个活跃 grant；玩家不在调度轮次中。
    """

    def __init__(self) -> None:
        # conversation_id -> 活跃 grant
        self._active_grants: Dict[str, TurnGrant] = {}
        # conversation_id -> {participant_id: last_spoke_utterance_index}
        self._last_spoke: Dict[str, Dict[str, int]] = {}
        # conversation_id -> {participant_id: consecutive_skips}
        self._skips: Dict[str, Dict[str, int]] = {}

    def grant_next(
        self,
        conversation_id: str,
        resident_participant_ids: List[str],
        next_utterance_index: int,
        last_addressed_id: Optional[str] = None,
        pending_question_ids: Optional[List[str]] = None,
    ) -> TurnGrant:
        """
        优先级：Addressed Reply 目标 > 被 request/ask 指向且未答复者 >
        最久未发言者；同级并列按 participant_id 字典序（RULE-DIALOGUE-047）。
        """
        if conversation_id in self._active_grants:
            raise GroupDialogueError(
                "DIALOGUE_TURN_ALREADY_GRANTED",
                "at most one active grant per conversation",
            )
        if not resident_participant_ids:
            raise GroupDialogueError(
                "DIALOGUE_NO_RESIDENT_PARTICIPANT", "no resident to grant a turn"
            )

        spoke_map = self._last_spoke.setdefault(conversation_id, {})
        pending = set(pending_question_ids or [])

        chosen: str
        reason: GrantReason
        if last_addressed_id and last_addressed_id in resident_participant_ids:
            chosen, reason = last_addressed_id, GrantReason.ADDRESSED_REPLY
        elif pending & set(resident_participant_ids):
            chosen = sorted(pending & set(resident_participant_ids))[0]
            reason = GrantReason.PENDING_QUESTION
        else:
            # 最久未发言：last_spoke 最小（未发言视为 -1）；并列按 ID 字典序
            chosen = min(
                resident_participant_ids,
                key=lambda pid: (spoke_map.get(pid, -1), pid),
            )
            reason = GrantReason.LONGEST_IDLE

        grant = TurnGrant(
            turn_grant_id=generate_ulid(),
            conversation_id=conversation_id,
            granted_to=chosen,
            granted_for_utterance_index=next_utterance_index,
            grant_reason=reason,
        )
        self._active_grants[conversation_id] = grant
        return grant

    def consume(
        self, conversation_id: str, turn_grant_id: str, speaker_id: str, utterance_index: int
    ) -> None:
        """RULE-DIALOGUE-046：无轮次的响应即使解码成功也拒收"""
        grant = self._active_grants.get(conversation_id)
        if grant is None or grant.turn_grant_id != turn_grant_id:
            raise GroupDialogueError(
                "DIALOGUE_TURN_GRANT_INVALID", "response without a valid turn grant"
            )
        if grant.granted_to != speaker_id:
            raise GroupDialogueError(
                "DIALOGUE_TURN_GRANT_HOLDER_MISMATCH",
                f"grant belongs to {grant.granted_to}, not {speaker_id}",
            )
        del self._active_grants[conversation_id]
        self._last_spoke.setdefault(conversation_id, {})[speaker_id] = utterance_index
        self._skips.setdefault(conversation_id, {})[speaker_id] = 0

    def revoke(
        self, conversation_id: str, reason: str = "expired"
    ) -> Optional[str]:
        """
        §8：turn grant 到期收回；连续两次跳过的居民由调用方触发 fallback 退出。
        返回被跳过的居民 ID。
        """
        grant = self._active_grants.pop(conversation_id, None)
        if grant is None:
            return None
        skips = self._skips.setdefault(conversation_id, {})
        skips[grant.granted_to] = skips.get(grant.granted_to, 0) + 1
        return grant.granted_to

    def consecutive_skips(self, conversation_id: str, participant_id: str) -> int:
        return self._skips.get(conversation_id, {}).get(participant_id, 0)

    def has_active_grant(self, conversation_id: str) -> bool:
        return conversation_id in self._active_grants

    def invalidate_for_end(self, conversation_id: str) -> None:
        """§6 第 4 步：会话结束时未消费的 turn grant 一并作废"""
        self._active_grants.pop(conversation_id, None)


def check_participant_cap(current_count: int) -> None:
    """RULE-DIALOGUE-045：超员拒绝返回 group_full"""
    if current_count >= MAX_PARTICIPANTS:
        raise GroupDialogueError(
            "group_full", f"participant set cap {MAX_PARTICIPANTS} reached"
        )


def adjudicate_departure(remaining_count: int) -> str:
    """
    RULE-DIALOGUE-048：剩余 >= 2 降员继续；仅剩 1 人按 participant_exit 终结。
    """
    if remaining_count >= 2:
        return "continue_reduced"
    return "end_participant_exit"


@dataclass(frozen=True)
class BystanderGeometry:
    """旁听判定的同 Revision 几何证据（RULE-DIALOGUE-049）"""

    bystander_id: str
    same_scene: bool
    distance_wu: float
    line_of_sight: bool


def evaluate_overhear(
    conversation_id: str,
    utterance_index: int,
    privacy: ConversationPrivacy,
    observed_revision: int,
    candidates: List[BystanderGeometry],
) -> List[OverheardEvent]:
    """
    RULE-DIALOGUE-049：四条件任一不满足不产生 witness。

    §8：上限 8 名候选，超出按距离最近截断；几何查询失败由调用方
    fail closed（宁可漏听不可误听），本函数只消费已成立的几何证据。
    """
    if privacy is not ConversationPrivacy.PUBLIC:
        # private_requested：只可旁观到「在交谈」，内容不可旁听
        return []
    eligible = [
        c
        for c in candidates
        if c.same_scene and c.distance_wu <= OVERHEAR_RANGE_WU and c.line_of_sight
    ]
    eligible.sort(key=lambda c: (c.distance_wu, c.bystander_id))
    truncated = eligible[:MAX_OVERHEAR_CANDIDATES]
    return [
        OverheardEvent(
            event_type="dialogue.utterance_overheard/v1",
            bystander_id=c.bystander_id,
            conversation_id=conversation_id,
            utterance_index=utterance_index,
            observed_revision=observed_revision,
            distance_wu=c.distance_wu,
            line_of_sight=c.line_of_sight,
        )
        for c in truncated
    ]


def assert_bystander_has_no_rights(bystander_id: str, participant_ids: List[str]) -> None:
    """RULE-DIALOGUE-051：旁听者不加入 participant set、无发言权"""
    if bystander_id in participant_ids:
        raise GroupDialogueError(
            "DIALOGUE_BYSTANDER_IN_PARTICIPANT_SET",
            "bystanders must not appear in the participant set",
        )

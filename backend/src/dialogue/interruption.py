"""
打断、退出与取消（DOC-DIALOGUE-007）

- RULE-DIALOGUE-038：Interrupt Priority 全序，严格高于才能抢占
- RULE-DIALOGUE-039：combat/safety 立即打断，在途模型请求 cancel
- RULE-DIALOGUE-040：玩家任意时刻 Graceful Exit；居民失败走 fallback 或
  ended(timeout)
- RULE-DIALOGUE-041：进入 interrupted 原子完成挂起/取消/过期/释放
- RULE-DIALOGUE-042：Resume Window 30 游戏分钟（暂停不流逝），超窗映射
  ended reason
- RULE-DIALOGUE-043：higher_priority_conversation 只限更高 TIME priority class
- RULE-DIALOGUE-044：迁移事件携带 interrupt_source；重放幂等
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    INTERRUPT_PRIORITY,
    INTERRUPT_TO_ENDED_REASON,
    RESUME_WINDOW_GAME_MINUTES,
    EndedReason,
    InterruptSource,
)


class InterruptionError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class InterruptDecision(str, Enum):
    """DES-DIALOGUE-007 decision 封闭枚举"""

    GRANTED = "granted"
    REJECTED_LOWER_PRIORITY = "rejected_lower_priority"
    REJECTED_TERMINAL_STATE = "rejected_terminal_state"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class InterruptCommand:
    """DES-DIALOGUE-007：只能由服务器内部 owner 或玩家退出网关构造"""

    command_id: str
    conversation_id: str
    interrupt_source: InterruptSource
    source_event_id: str
    affected_participant_ids: Tuple[str, ...] = ()

    @property
    def priority(self) -> int:
        return INTERRUPT_PRIORITY[self.interrupt_source]


@dataclass(frozen=True)
class InterruptResult:
    decision: InterruptDecision
    conversation_id: str
    resume_deadline_game_time: Optional[int] = None
    cancelled_model_request_ids: Tuple[str, ...] = ()
    expired_intent_candidate_ids: Tuple[str, ...] = ()


@dataclass
class _InterruptRecord:
    source: InterruptSource
    resume_deadline_game_time: int
    extra_sources: List[InterruptSource] = field(default_factory=list)


class InterruptionArbiter:
    """
    打断裁决与 Resume Window 管理（每 conversation 一条记录）。
    """

    def __init__(self) -> None:
        self._records: Dict[str, _InterruptRecord] = {}
        self._processed_commands: Dict[str, InterruptResult] = {}

    def adjudicate(
        self,
        command: InterruptCommand,
        conversation_is_terminal: bool,
        current_activity_priority: int,
        current_game_time: int,
        in_flight_model_request_ids: Tuple[str, ...] = (),
        pending_intent_candidate_ids: Tuple[str, ...] = (),
    ) -> InterruptResult:
        """
        RULE-DIALOGUE-038/041/044：裁决 + 原子挂起清单。

        返回结果包含待取消模型请求与待过期 intent candidate，由调用方执行。
        """
        prior = self._processed_commands.get(command.command_id)
        if prior is not None:
            # RULE-DIALOGUE-044：重放同一打断 command 幂等返回原结果
            return InterruptResult(
                decision=InterruptDecision.DUPLICATE,
                conversation_id=prior.conversation_id,
                resume_deadline_game_time=prior.resume_deadline_game_time,
                cancelled_model_request_ids=prior.cancelled_model_request_ids,
                expired_intent_candidate_ids=prior.expired_intent_candidate_ids,
            )

        if conversation_is_terminal:
            result = InterruptResult(
                decision=InterruptDecision.REJECTED_TERMINAL_STATE,
                conversation_id=command.conversation_id,
            )
            self._processed_commands[command.command_id] = result
            return result

        if command.priority <= current_activity_priority:
            # RULE-DIALOGUE-038：相等或更低排队或被拒
            result = InterruptResult(
                decision=InterruptDecision.REJECTED_LOWER_PRIORITY,
                conversation_id=command.conversation_id,
            )
            self._processed_commands[command.command_id] = result
            return result

        # §7：两个打断源同 Tick 到达——取最高者记录，次高者作审计附注
        existing = self._records.get(command.conversation_id)
        extra_sources: List[InterruptSource] = []
        if existing is not None:
            if INTERRUPT_PRIORITY[existing.source] >= command.priority:
                extra_sources = [command.interrupt_source]
                source = existing.source
            else:
                extra_sources = [existing.source]
                source = command.interrupt_source
        else:
            source = command.interrupt_source

        deadline = current_game_time + RESUME_WINDOW_GAME_MINUTES
        self._records[command.conversation_id] = _InterruptRecord(
            source=source,
            resume_deadline_game_time=deadline,
            extra_sources=extra_sources,
        )
        result = InterruptResult(
            decision=InterruptDecision.GRANTED,
            conversation_id=command.conversation_id,
            resume_deadline_game_time=deadline,
            cancelled_model_request_ids=in_flight_model_request_ids,
            expired_intent_candidate_ids=pending_intent_candidate_ids,
        )
        self._processed_commands[command.command_id] = result
        return result

    def check_resume(
        self,
        conversation_id: str,
        current_game_time: int,
        conditions_still_met: bool,
        interrupt_source_cleared: bool,
    ) -> Tuple[bool, Optional[EndedReason]]:
        """
        RULE-DIALOGUE-042：窗口内且参与条件满足且打断源解除才可恢复。

        返回 (can_resume, ended_reason_if_expired)。
        """
        record = self._records.get(conversation_id)
        if record is None:
            return (False, None)
        if current_game_time > record.resume_deadline_game_time:
            ended = INTERRUPT_TO_ENDED_REASON.get(record.source, EndedReason.TIMEOUT)
            return (False, ended)
        if not conditions_still_met or not interrupt_source_cleared:
            return (False, None)
        return (True, None)

    def clear(self, conversation_id: str) -> None:
        self._records.pop(conversation_id, None)

    def resume_deadline(self, conversation_id: str) -> Optional[int]:
        record = self._records.get(conversation_id)
        return record.resume_deadline_game_time if record else None

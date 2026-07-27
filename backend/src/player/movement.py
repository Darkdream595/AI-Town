"""
玩家移动、预测与权威校准（DOC-PLAYER-002）

- RULE-PLAYER-006：玩家与 AI 走同一组 MAP canonical 原语；PLAYER 不维护
  玩家专用合法性（本模块只做 intent 形状/序号/速率校验与校准状态机，
  空间合法性经由注入的 map_router 调用 MAP 原语）
- RULE-PLAYER-007：Client 方向/坐标/速度/expected_revision 均不可信
- RULE-PLAYER-009：失焦/modal/模式切换/断线/Scene 切换清空按键 latch
- RULE-PLAYER-010：预测误差只由视觉校准消除；失败移动不产生位置 DomainEvent
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .constants import (
    DENY_INPUT_SEQUENCE_CONFLICT,
    MAX_SAMPLE_DURATION_MS,
    MOVE_INTENT_RATE_LIMIT_PER_SECOND,
)


class MovementValidationError(Exception):
    """移动 intent 校验失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class SpeedMode(str, Enum):
    """DES-PLAYER-002：仅 walk / fast_walk"""

    WALK = "walk"
    FAST_WALK = "fast_walk"


#: §5 合法 direction 分量
_VALID_DIRECTION_COMPONENTS = frozenset({-1, 0, 1})

#: §5 合法 intent 字段（拒绝未知字段）
_ALLOWED_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "command_id",
        "expected_revision",
        "input_sequence",
        "sample_duration_ms",
        "direction",
        "speed_mode",
        "client_observed_scene_id",
    }
)


@dataclass(frozen=True)
class MoveIntent:
    """DES-PLAYER-002 Player Move Intent（未信任输入）"""

    command_id: str
    expected_revision: int
    input_sequence: int
    sample_duration_ms: int
    direction_x: int
    direction_y: int
    speed_mode: SpeedMode
    client_observed_scene_id: str
    schema_version: int = 1

    @property
    def is_diagonal(self) -> bool:
        return self.direction_x != 0 and self.direction_y != 0

    def normalized_direction(self) -> Tuple[float, float]:
        """
        §5：对角线先归一化，不能获得更高速度。

        返回单位向量；正交方向长度恒为 1。
        """
        length = math.hypot(self.direction_x, self.direction_y)
        if length == 0:
            return (0.0, 0.0)
        return (self.direction_x / length, self.direction_y / length)

    def payload_key(self) -> Tuple:
        """序号冲突判定的 payload 指纹（§7：同序号不同 payload 为冲突）"""
        return (
            self.expected_revision,
            self.sample_duration_ms,
            self.direction_x,
            self.direction_y,
            self.speed_mode.value,
            self.client_observed_scene_id,
        )


@dataclass(frozen=True)
class CommandReceipt:
    """移动命令回执（§7：同 input_sequence 重复到达只返回原 receipt）"""

    command_id: str
    input_sequence: int
    accepted: bool
    reason_code: Optional[str] = None
    confirmed_revision: Optional[int] = None


class MoveIntentValidator:
    """
    intent 形状校验 + 每玩家序号幂等 + 速率限制。

    空间合法性不在此处：通过 route_movement_intent 注入的 map_router
    组合 MAP canonical 原语（is_standable/sweep_disc/validate_path/...）。
    """

    def __init__(self) -> None:
        # 每 binding：已见 input_sequence -> (payload_key, receipt)
        self._sequences: Dict[str, Dict[int, Tuple[Tuple, CommandReceipt]]] = {}
        self._confirmed_sequence: Dict[str, int] = {}
        # 每 binding：最近一秒内的 intent 时间戳（毫秒）队列
        self._rate_windows: Dict[str, Deque[int]] = {}

    def validate_shape(self, raw: dict) -> MoveIntent:
        """
        §9：拒绝 NaN、Infinity、浮点方向、未知字段和超大序号跳变。
        """
        unknown = set(raw) - _ALLOWED_INTENT_FIELDS
        if unknown:
            raise MovementValidationError(
                "PLAYER_INTENT_UNKNOWN_FIELD", f"unknown fields: {sorted(unknown)}"
            )
        if raw.get("schema_version") != 1:
            raise MovementValidationError("PLAYER_INTENT_SCHEMA_VERSION")

        direction = raw.get("direction")
        if not isinstance(direction, dict):
            raise MovementValidationError("PLAYER_INTENT_DIRECTION_INVALID")
        dx = self._direction_component(direction.get("x"))
        dy = self._direction_component(direction.get("y"))
        if dx == 0 and dy == 0:
            # §5：direction.x/y 不能同时为 0
            raise MovementValidationError("PLAYER_INTENT_DIRECTION_ZERO")

        duration = raw.get("sample_duration_ms")
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise MovementValidationError("PLAYER_INTENT_DURATION_INVALID")
        if not 1 <= duration <= MAX_SAMPLE_DURATION_MS:
            # §7：单 intent 上限 100 ms，额外时间不能兑换位移
            raise MovementValidationError("PLAYER_INTENT_DURATION_OUT_OF_RANGE")

        sequence = raw.get("input_sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise MovementValidationError("PLAYER_INTENT_SEQUENCE_INVALID")

        try:
            speed_mode = SpeedMode(raw.get("speed_mode"))
        except ValueError:
            raise MovementValidationError("PLAYER_INTENT_SPEED_MODE_INVALID")

        expected_revision = raw.get("expected_revision")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise MovementValidationError("PLAYER_INTENT_REVISION_INVALID")

        return MoveIntent(
            command_id=str(raw.get("command_id") or ""),
            expected_revision=expected_revision,
            input_sequence=sequence,
            sample_duration_ms=duration,
            direction_x=dx,
            direction_y=dy,
            speed_mode=speed_mode,
            client_observed_scene_id=str(raw.get("client_observed_scene_id") or ""),
        )

    @staticmethod
    def _direction_component(value: object) -> int:
        # §9：拒绝 NaN/Infinity/浮点方向；bool 是 int 子类需先排除
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MovementValidationError("PLAYER_INTENT_DIRECTION_INVALID")
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value) or not value.is_integer():
                raise MovementValidationError("PLAYER_INTENT_DIRECTION_INVALID")
        component = int(value)
        if component not in _VALID_DIRECTION_COMPONENTS:
            raise MovementValidationError("PLAYER_INTENT_DIRECTION_INVALID")
        return component

    def check_rate_limit(self, binding_id: str, now_ms: int) -> None:
        """§9：每玩家移动 intent 限 25/s，超额合并为最新按键状态"""
        window = self._rate_windows.setdefault(binding_id, deque())
        while window and now_ms - window[0] >= 1000:
            window.popleft()
        if len(window) >= MOVE_INTENT_RATE_LIMIT_PER_SECOND:
            raise MovementValidationError(
                "PLAYER_INTENT_RATE_LIMITED",
                "move intent rate exceeded; client must coalesce to latest state",
            )
        window.append(now_ms)

    def check_sequence(
        self, binding_id: str, intent: MoveIntent
    ) -> Optional[CommandReceipt]:
        """
        §7：同一 input_sequence 重复到达只返回原 receipt（返回非 None 表示重放）；
        低于已确认序号的输入忽略；同序号不同 payload 冲突。
        """
        confirmed = self._confirmed_sequence.get(binding_id, -1)
        if intent.input_sequence <= confirmed:
            return CommandReceipt(
                command_id=intent.command_id,
                input_sequence=intent.input_sequence,
                accepted=False,
                reason_code="PLAYER_INTENT_SEQUENCE_STALE",
            )

        seen = self._sequences.setdefault(binding_id, {})
        prior = seen.get(intent.input_sequence)
        if prior is not None:
            prior_key, prior_receipt = prior
            if prior_key != intent.payload_key():
                raise MovementValidationError(
                    DENY_INPUT_SEQUENCE_CONFLICT,
                    f"input_sequence {intent.input_sequence} with different payload",
                )
            return prior_receipt
        return None

    def record_receipt(self, binding_id: str, intent: MoveIntent, receipt: CommandReceipt) -> None:
        self._sequences.setdefault(binding_id, {})[intent.input_sequence] = (
            intent.payload_key(),
            receipt,
        )

    def confirm_sequence(self, binding_id: str, input_sequence: int) -> None:
        """§6 第 6 步：Client 丢弃 <= confirmed_input_sequence 的预测输入"""
        current = self._confirmed_sequence.get(binding_id, -1)
        self._confirmed_sequence[binding_id] = max(current, input_sequence)


class ReconciliationState(str, Enum):
    """§6.1 权威校准状态机"""

    SYNCED = "synced"
    PREDICTING = "predicting"
    AWAITING_ACK = "awaiting_ack"
    CORRECTING = "correcting"
    INPUT_CLEARED = "input_cleared"
    SNAPSHOT_REQUIRED = "snapshot_required"


class ReconciliationTrigger(str, Enum):
    SEND_INTENT = "send_intent"
    AWAIT_ACK = "await_ack"
    ACK_CONFIRMED = "ack_confirmed"
    CORRECTION_NEEDED = "correction_needed"
    CORRECTION_APPLIED = "correction_applied"
    CLEAR_INPUT = "clear_input"  # blur/modal/mode/disconnect
    REVISION_GAP = "revision_gap"  # 或 scene_mismatch
    SNAPSHOT_INSTALLED = "snapshot_installed"
    RESUME_INPUT = "resume_input"


#: §6.1 转换表
_RECONCILIATION_TRANSITIONS: Dict[ReconciliationState, Dict[ReconciliationTrigger, ReconciliationState]] = {
    ReconciliationState.SYNCED: {
        ReconciliationTrigger.SEND_INTENT: ReconciliationState.PREDICTING,
        ReconciliationTrigger.CLEAR_INPUT: ReconciliationState.INPUT_CLEARED,
        ReconciliationTrigger.REVISION_GAP: ReconciliationState.SNAPSHOT_REQUIRED,
    },
    ReconciliationState.PREDICTING: {
        ReconciliationTrigger.AWAIT_ACK: ReconciliationState.AWAITING_ACK,
        ReconciliationTrigger.CLEAR_INPUT: ReconciliationState.INPUT_CLEARED,
        ReconciliationTrigger.REVISION_GAP: ReconciliationState.SNAPSHOT_REQUIRED,
    },
    ReconciliationState.AWAITING_ACK: {
        ReconciliationTrigger.ACK_CONFIRMED: ReconciliationState.SYNCED,
        ReconciliationTrigger.CORRECTION_NEEDED: ReconciliationState.CORRECTING,
        ReconciliationTrigger.CLEAR_INPUT: ReconciliationState.INPUT_CLEARED,
        ReconciliationTrigger.REVISION_GAP: ReconciliationState.SNAPSHOT_REQUIRED,
    },
    ReconciliationState.CORRECTING: {
        ReconciliationTrigger.CORRECTION_APPLIED: ReconciliationState.SYNCED,
        ReconciliationTrigger.CLEAR_INPUT: ReconciliationState.INPUT_CLEARED,
        ReconciliationTrigger.REVISION_GAP: ReconciliationState.SNAPSHOT_REQUIRED,
    },
    ReconciliationState.INPUT_CLEARED: {
        ReconciliationTrigger.RESUME_INPUT: ReconciliationState.SYNCED,
        ReconciliationTrigger.REVISION_GAP: ReconciliationState.SNAPSHOT_REQUIRED,
    },
    ReconciliationState.SNAPSHOT_REQUIRED: {
        ReconciliationTrigger.SNAPSHOT_INSTALLED: ReconciliationState.SYNCED,
    },
}


class ReconciliationStateMachine:
    """
    权威校准状态机（§6.1）。

    RULE-PLAYER-010：预测误差只能由视觉校准消除，不能反向覆盖后端。
    """

    def __init__(self) -> None:
        self._state = ReconciliationState.SYNCED
        # RULE-PLAYER-009：latch 清空事件审计（不记录每帧 raw key event）
        self._clear_reasons: List[str] = []

    @property
    def state(self) -> ReconciliationState:
        return self._state

    @property
    def clear_reasons(self) -> List[str]:
        return list(self._clear_reasons)

    def transition(
        self, trigger: ReconciliationTrigger, clear_reason: str = ""
    ) -> ReconciliationState:
        options = _RECONCILIATION_TRANSITIONS.get(self._state, {})
        nxt = options.get(trigger)
        if nxt is None:
            raise MovementValidationError(
                "PLAYER_RECONCILIATION_TRANSITION_INVALID",
                f"{self._state.value} + {trigger.value} not allowed",
            )
        if trigger is ReconciliationTrigger.CLEAR_INPUT:
            self._clear_reasons.append(clear_reason)
        self._state = nxt
        return self._state


class InputLatch:
    """
    pressed-state 按键采样（§7：浏览器自动重复按键不累积速度）。

    RULE-PLAYER-009：失焦/modal/模式切换/断线/Scene 切换必须清空 latch。
    """

    def __init__(self) -> None:
        self._pressed: set[str] = set()

    def press(self, code: str) -> None:
        self._pressed.add(code)

    def release(self, code: str) -> None:
        self._pressed.discard(code)

    def clear(self) -> None:
        self._pressed.clear()

    def pressed(self) -> frozenset[str]:
        return frozenset(self._pressed)

    def direction_vector(self) -> Tuple[int, int]:
        """从 pressed-state 合成方向；重复 keydown 不影响结果"""
        dx = int("KeyD" in self._pressed) - int("KeyA" in self._pressed)
        dy = int("KeyS" in self._pressed) - int("KeyW" in self._pressed)
        return (dx, dy)

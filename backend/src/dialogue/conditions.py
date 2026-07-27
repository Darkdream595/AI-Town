"""
距离、视线与参与条件（DOC-DIALOGUE-002）

- RULE-DIALOGUE-007/008：同 Scene、<=96 wu（epsilon 1/16）、LoS，服务器持久化
  量化坐标判定
- RULE-DIALOGUE-009：Availability 只读 RESIDENT/TIME 已提交状态
- RULE-DIALOGUE-010：会话建立时创建 Attention Reservation
- RULE-DIALOGUE-011：维持期 Tick 复算，宽限 10 游戏分钟
- RULE-DIALOGUE-012：中途加入不回溯历史
- RULE-DIALOGUE-076：共通语言 >=60，玩家视为 crown_common 100
- RULE-DIALOGUE-077：Availability + Reservation 授予即隐式同意
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    DISTANCE_EPSILON_WU,
    GRACE_PERIOD_GAME_MINUTES,
    PLAYER_LANGUAGE_ID,
    PLAYER_LANGUAGE_LEVEL,
    SHARED_LANGUAGE_THRESHOLD,
    TALK_RANGE_WU,
)


class ParticipationError(Exception):
    """参与条件校验失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class ReservationState(str, Enum):
    GRANTED = "granted"
    RELEASED = "released"
    PREEMPTED = "preempted"
    EXPIRED = "expired"


@dataclass(frozen=True)
class EntitySnapshot:
    """参与条件校验输入（§5 checks 行）"""

    entity_id: str
    scene_id: str
    x_wu: int  # RULE-FOUNDATION-042 持久化量化坐标
    y_wu: int
    available: bool
    language_proficiencies: Dict[str, int] = field(default_factory=dict)
    is_player: bool = False


@dataclass
class AttentionReservation:
    """RULE-DIALOGUE-010：会话期间居民注意力的排他声明"""

    reservation_id: str
    conversation_id: str
    resident_id: str
    expires_game_time: int
    state: ReservationState = ReservationState.GRANTED


class ParticipationValidator:
    """发起与维持条件校验（服务器侧，最新 Revision）"""

    def __init__(
        self,
        los_query: Optional[Callable[[Tuple[int, int], Tuple[int, int], str], bool]] = None,
    ) -> None:
        # MAP 遮挡查询；失败 fail closed 视为视线不成立（§8）
        self._los_query = los_query or (lambda a, b, scene: True)

    def check_initiation(
        self,
        initiator: EntitySnapshot,
        target: EntitySnapshot,
    ) -> str:
        """
        RULE-DIALOGUE-007..009/076/077：全部条件满足返回选定的会话语言 ID，
        否则抛 ParticipationError（具体 reason code）。
        """
        if initiator.scene_id != target.scene_id:
            raise ParticipationError(
                "DIALOGUE_NOT_SAME_SCENE", "initiator and target in different scenes"
            )
        distance = self.distance_wu(initiator, target)
        if distance > TALK_RANGE_WU + DISTANCE_EPSILON_WU:
            raise ParticipationError(
                "DIALOGUE_OUT_OF_RANGE",
                f"distance {distance:.2f} wu exceeds {TALK_RANGE_WU} wu",
            )
        if not self._safe_los(initiator, target):
            raise ParticipationError("DIALOGUE_NO_LINE_OF_SIGHT")
        if not target.available:
            # RULE-DIALOGUE-009：对话域不自行定义居民状态
            raise ParticipationError(
                "DIALOGUE_TARGET_UNAVAILABLE", "target availability is false"
            )
        return self.select_shared_language(initiator, target)

    @staticmethod
    def distance_wu(a: EntitySnapshot, b: EntitySnapshot) -> float:
        return ((a.x_wu - b.x_wu) ** 2 + (a.y_wu - b.y_wu) ** 2) ** 0.5

    def _safe_los(self, a: EntitySnapshot, b: EntitySnapshot) -> bool:
        try:
            return bool(
                self._los_query((a.x_wu, a.y_wu), (b.x_wu, b.y_wu), a.scene_id)
            )
        except Exception:
            # §8：MAP 遮挡查询失败 fail closed
            return False

    @staticmethod
    def _proficiencies(entity: EntitySnapshot) -> Dict[str, int]:
        if entity.is_player:
            # RULE-DIALOGUE-076：玩家视为具有 language.crown_common level 100
            merged = dict(entity.language_proficiencies)
            merged[PLAYER_LANGUAGE_ID] = PLAYER_LANGUAGE_LEVEL
            return merged
        return dict(entity.language_proficiencies)

    @classmethod
    def shared_language_ids(
        cls, a: EntitySnapshot, b: EntitySnapshot
    ) -> List[str]:
        pa, pb = cls._proficiencies(a), cls._proficiencies(b)
        return [
            lang
            for lang in set(pa) & set(pb)
            if pa[lang] >= SHARED_LANGUAGE_THRESHOLD
            and pb[lang] >= SHARED_LANGUAGE_THRESHOLD
        ]

    @classmethod
    def select_shared_language(
        cls, a: EntitySnapshot, b: EntitySnapshot
    ) -> str:
        """
        RULE-DIALOGUE-076：双方 level 之和最高者；并列按 language_id 字典序。
        """
        candidates = cls.shared_language_ids(a, b)
        if not candidates:
            raise ParticipationError(
                "no_shared_language", "no shared language above threshold"
            )
        pa, pb = cls._proficiencies(a), cls._proficiencies(b)
        return min(
            candidates,
            key=lambda lang: (-(pa[lang] + pb[lang]), lang),
        )


class ReservationLedger:
    """
    Attention Reservation 生命周期（RULE-DIALOGUE-010）。

    泄漏检查：任意结束路径后不得存在 granted 状态的悬挂 Reservation。
    """

    def __init__(self) -> None:
        self._reservations: Dict[str, AttentionReservation] = {}

    def create(
        self,
        conversation_id: str,
        resident_ids: List[str],
        expires_game_time: int,
    ) -> List[AttentionReservation]:
        created = []
        for resident_id in resident_ids:
            reservation = AttentionReservation(
                reservation_id=generate_ulid(),
                conversation_id=conversation_id,
                resident_id=resident_id,
                expires_game_time=expires_game_time,
            )
            self._reservations[reservation.reservation_id] = reservation
            created.append(reservation)
        return created

    def release_for_conversation(self, conversation_id: str) -> None:
        """§6 第 4 步：会话结束统一释放"""
        for reservation in self._reservations.values():
            if (
                reservation.conversation_id == conversation_id
                and reservation.state is ReservationState.GRANTED
            ):
                reservation.state = ReservationState.RELEASED

    def preempt(self, reservation_id: str) -> None:
        reservation = self._reservations.get(reservation_id)
        if reservation and reservation.state is ReservationState.GRANTED:
            reservation.state = ReservationState.PREEMPTED

    def expire_overdue(self, current_game_time: int) -> List[str]:
        """到期未授予/未释放的 Reservation；返回受影响的 conversation_id"""
        affected = []
        for reservation in self._reservations.values():
            if (
                reservation.state is ReservationState.GRANTED
                and current_game_time > reservation.expires_game_time
            ):
                reservation.state = ReservationState.EXPIRED
                affected.append(reservation.conversation_id)
        return affected

    def has_leak(self) -> bool:
        """§10 验收：任意结束路径后无悬挂 granted Reservation"""
        return any(
            r.state is ReservationState.GRANTED for r in self._reservations.values()
        )

    def granted_for(self, conversation_id: str) -> List[AttentionReservation]:
        return [
            r
            for r in self._reservations.values()
            if r.conversation_id == conversation_id
            and r.state is ReservationState.GRANTED
        ]


@dataclass
class GraceTracker:
    """
    RULE-DIALOGUE-011：超距宽限期跟踪。

    超出 Talk Range 进入宽限（10 游戏分钟）；回到范围内立即清除；
    宽限满仍超限由调用方迁移 interrupted → ended(participant_left)。
    """

    grace_period_game_minutes: int = GRACE_PERIOD_GAME_MINUTES
    _out_of_range_since: Dict[str, int] = field(default_factory=dict)

    def on_tick(
        self, conversation_id: str, in_range: bool, current_game_time: int
    ) -> bool:
        """返回 True 表示宽限已满（应终结会话）"""
        if in_range:
            self._out_of_range_since.pop(conversation_id, None)
            return False
        since = self._out_of_range_since.setdefault(conversation_id, current_game_time)
        return current_game_time - since >= self.grace_period_game_minutes

    def in_grace(self, conversation_id: str) -> bool:
        return conversation_id in self._out_of_range_since

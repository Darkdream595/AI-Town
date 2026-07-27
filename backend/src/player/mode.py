"""
居民与镇长模式切换状态机（DOC-PLAYER-003）

- RULE-PLAYER-011：resident_active → entering_mayor → mayor_active →
  leaving_mayor → resident_active；任何 error 回到已确认稳定态
- RULE-PLAYER-012：进入 Mayor 前在最新 Revision 验证 active binding 与 office
- RULE-PLAYER-013：mayor_active 必须持有有效 Mayor Pause Token；离开只释放
  自己持有的 token
- RULE-PLAYER-014：禁止转换表（§7.1）
- §7.2：(world_id, command_id) 幂等 + expected_mode_version
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .constants import (
    DENY_MAYOR_AUTHORITY_REVOKED,
    DENY_MODE_BLOCKED_COMBAT,
    DENY_MODE_BLOCKED_RESIDENT_STATE,
    DENY_MODE_BLOCKED_SYSTEM,
)
from .pause import PauseToken, PauseTokenError, PauseTokenLedger


class ModeSwitchError(Exception):
    """模式切换失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class PlayerMode(str, Enum):
    """DES-PLAYER-003：仅允许五个状态"""

    RESIDENT_ACTIVE = "resident_active"
    ENTERING_MAYOR = "entering_mayor"
    MAYOR_ACTIVE = "mayor_active"
    LEAVING_MAYOR = "leaving_mayor"


#: §4 RULE-PLAYER-011：稳定态（error 必须回到这些状态）
STABLE_MODES = frozenset({PlayerMode.RESIDENT_ACTIVE, PlayerMode.MAYOR_ACTIVE})

#: §6 状态机转换表（含 mermaid 图的全部边）
_ALLOWED_TRANSITIONS: Dict[PlayerMode, Set[PlayerMode]] = {
    PlayerMode.RESIDENT_ACTIVE: {PlayerMode.ENTERING_MAYOR},
    PlayerMode.ENTERING_MAYOR: {PlayerMode.MAYOR_ACTIVE, PlayerMode.RESIDENT_ACTIVE},
    PlayerMode.MAYOR_ACTIVE: {PlayerMode.LEAVING_MAYOR},
    PlayerMode.LEAVING_MAYOR: {PlayerMode.RESIDENT_ACTIVE, PlayerMode.MAYOR_ACTIVE},
}

#: DES-PLAYER-003：pause_token_id 只在三个 mayor 相关状态存在
_TOKEN_REQUIRED_MODES = frozenset(
    {PlayerMode.ENTERING_MAYOR, PlayerMode.MAYOR_ACTIVE, PlayerMode.LEAVING_MAYOR}
)

MAYOR_PAUSE_OWNER = "player"
MAYOR_PAUSE_REASON = "mayor_management"


class ProhibitedCondition(str, Enum):
    """§7.1 禁止转换表的可检测条件"""

    ENCOUNTER_ACTIVE = "encounter_active"
    INCAPACITATED_OR_CAPTURED = "incapacitated_or_captured"
    RECOVERY_OR_SHUTDOWN_BARRIER = "recovery_or_shutdown_barrier"
    MAYOR_AUTHORITY_REVOKED = "mayor_authority_revoked"
    ADMIN_CONFIRMATION_ACTIVE = "admin_confirmation_active"
    DIALOGUE_INPUT_MODAL = "dialogue_input_modal"
    SAVE_SWITCHING = "save_switching"


#: §7.1：各条件对应的进入拒绝码
_ENTER_DENY_CODES: Dict[ProhibitedCondition, str] = {
    ProhibitedCondition.ENCOUNTER_ACTIVE: DENY_MODE_BLOCKED_COMBAT,
    ProhibitedCondition.INCAPACITATED_OR_CAPTURED: DENY_MODE_BLOCKED_RESIDENT_STATE,
    ProhibitedCondition.RECOVERY_OR_SHUTDOWN_BARRIER: DENY_MODE_BLOCKED_SYSTEM,
    ProhibitedCondition.SAVE_SWITCHING: DENY_MODE_BLOCKED_SYSTEM,
    ProhibitedCondition.MAYOR_AUTHORITY_REVOKED: DENY_MAYOR_AUTHORITY_REVOKED,
    ProhibitedCondition.ADMIN_CONFIRMATION_ACTIVE: DENY_MODE_BLOCKED_SYSTEM,
    ProhibitedCondition.DIALOGUE_INPUT_MODAL: DENY_MODE_BLOCKED_SYSTEM,
}


@dataclass(frozen=True)
class ModeAggregate:
    """DES-PLAYER-003：每 binding 的模式与转换版本"""

    binding_id: str
    mode: PlayerMode
    mode_version: int
    mayor_authority_version: int
    pause_token_id: Optional[str]
    entered_by_command_id: Optional[str]
    entered_revision: Optional[int]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ModeSwitchError("MODE_SCHEMA_VERSION_UNSUPPORTED")
        if self.mode_version < 0:
            raise ModeSwitchError("MODE_VERSION_INVALID")
        # DES-PLAYER-003：pause_token_id 只在 entering/mayor/leaving 存在
        if self.mode in _TOKEN_REQUIRED_MODES:
            if not self.pause_token_id:
                raise ModeSwitchError(
                    "MODE_TOKEN_REQUIRED",
                    f"{self.mode.value} requires a pause token",
                )
        elif self.pause_token_id is not None:
            raise ModeSwitchError(
                "MODE_TOKEN_UNEXPECTED",
                f"{self.mode.value} must not hold a pause token",
            )


@dataclass(frozen=True)
class ModeSwitchResult:
    aggregate: ModeAggregate
    replayed: bool
    pause_token: Optional[PauseToken] = None


class ModeSwitchStateMachine:
    """
    每 binding 一个状态机；与 PauseTokenLedger 组合（RULE-PLAYER-013）。

    authority_probe 注入：在最新 Revision 验证 active binding 与 Mayor
    office/role（RULE-PLAYER-012），返回 (has_office, authority_version)。
    """

    def __init__(
        self,
        binding_id: str,
        pause_ledger: PauseTokenLedger,
        authority_probe,
        initial_revision: int = 0,
    ) -> None:
        self._pause_ledger = pause_ledger
        self._authority_probe = authority_probe
        self._revision = initial_revision
        self._aggregate = ModeAggregate(
            binding_id=binding_id,
            mode=PlayerMode.RESIDENT_ACTIVE,
            mode_version=0,
            mayor_authority_version=0,
            pause_token_id=None,
            entered_by_command_id=None,
            entered_revision=None,
        )
        # §7.2：(world_id, command_id) -> (payload_hash, result)
        self._idempotency: Dict[str, Tuple[str, ModeSwitchResult]] = {}

    @property
    def aggregate(self) -> ModeAggregate:
        return self._aggregate

    @property
    def mode(self) -> PlayerMode:
        return self._aggregate.mode

    def request_mode_switch(
        self,
        command_id: str,
        target_mode: PlayerMode,
        expected_revision: int,
        expected_mode_version: int,
        prohibited: Set[ProhibitedCondition] = frozenset(),
        current_game_revision: Optional[int] = None,
    ) -> ModeSwitchResult:
        """
        §5 接口：模式转换。

        双击 Tab 不能越过中间态（§7.2）：每次调用只沿转换表走一步；
        相同命令重放返回原状态，不同 payload 冲突。
        """
        revision = (
            current_game_revision if current_game_revision is not None else self._revision
        )
        payload_hash = hashlib.sha256(
            json.dumps(
                {
                    "target_mode": target_mode.value,
                    "expected_revision": expected_revision,
                    "expected_mode_version": expected_mode_version,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        cached = self._idempotency.get(command_id)
        if cached is not None:
            cached_hash, cached_result = cached
            if cached_hash != payload_hash:
                raise ModeSwitchError(
                    "PLAYER_MODE_COMMAND_CONFLICT",
                    "same command_id with different payload",
                )
            return ModeSwitchResult(
                aggregate=cached_result.aggregate,
                replayed=True,
                pause_token=cached_result.pause_token,
            )

        if expected_mode_version != self._aggregate.mode_version:
            raise ModeSwitchError(
                "PLAYER_MODE_VERSION_STALE",
                f"expected mode_version {expected_mode_version}, "
                f"current {self._aggregate.mode_version}",
            )

        result = self._advance(
            command_id=command_id,
            target_mode=target_mode,
            prohibited=prohibited,
            revision=revision,
        )
        self._idempotency[command_id] = (payload_hash, result)
        return result

    def _advance(
        self,
        command_id: str,
        target_mode: PlayerMode,
        prohibited: Set[ProhibitedCondition],
        revision: int,
    ) -> ModeSwitchResult:
        current = self._aggregate.mode
        if target_mode not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ModeSwitchError(
                "PLAYER_MODE_TRANSITION_INVALID",
                f"{current.value} -> {target_mode.value} not in state machine",
            )

        if target_mode is PlayerMode.ENTERING_MAYOR:
            return self._enter_mayor(command_id, prohibited, revision)
        if target_mode is PlayerMode.MAYOR_ACTIVE:
            return self._commit_mayor_active(command_id, revision)
        if target_mode is PlayerMode.LEAVING_MAYOR:
            return self._begin_leave_mayor(command_id, prohibited)
        # target_mode is RESIDENT_ACTIVE
        return self._commit_resident_active(command_id, prohibited)

    def _enter_mayor(
        self,
        command_id: str,
        prohibited: Set[ProhibitedCondition],
        revision: int,
    ) -> ModeSwitchResult:
        """进入顺序：验证禁止态/权限 → 获取 TIME token → 提交 mode"""
        for condition in prohibited:
            deny = _ENTER_DENY_CODES.get(condition)
            if deny is not None:
                # §7.1：Encounter/昏迷/Recovery/撤权/Admin confirmation 禁止进入
                raise ModeSwitchError(deny, f"blocked by {condition.value}")

        has_office, authority_version = self._authority_probe(
            self._aggregate.binding_id, revision
        )
        if not has_office:
            # RULE-PLAYER-012：显示 Mayor UI 或 world ownership 不能替代授权
            raise ModeSwitchError(DENY_MAYOR_AUTHORITY_REVOKED)

        try:
            token = self._pause_ledger.acquire(
                command_id=command_id,
                owner=MAYOR_PAUSE_OWNER,
                reason=MAYOR_PAUSE_REASON,
                revision=revision,
            )
        except PauseTokenError as exc:
            raise ModeSwitchError(exc.code) from exc

        aggregate = ModeAggregate(
            binding_id=self._aggregate.binding_id,
            mode=PlayerMode.ENTERING_MAYOR,
            mode_version=self._aggregate.mode_version + 1,
            mayor_authority_version=authority_version,
            pause_token_id=token.token_id,
            entered_by_command_id=command_id,
            entered_revision=revision,
        )
        self._aggregate = aggregate
        self._revision = revision
        return ModeSwitchResult(aggregate=aggregate, replayed=False, pause_token=token)

    def _commit_mayor_active(
        self, command_id: str, revision: int
    ) -> ModeSwitchResult:
        """pause token committed 且 projection ready 后进入 mayor_active"""
        token_id = self._aggregate.pause_token_id
        if not token_id or not self._pause_ledger.has_token(token_id):
            # RULE-PLAYER-013：mayor_active 必须持有有效 token
            raise ModeSwitchError(
                "MODE_TOKEN_REQUIRED", "mayor_active requires a live pause token"
            )
        aggregate = ModeAggregate(
            binding_id=self._aggregate.binding_id,
            mode=PlayerMode.MAYOR_ACTIVE,
            mode_version=self._aggregate.mode_version + 1,
            mayor_authority_version=self._aggregate.mayor_authority_version,
            pause_token_id=token_id,
            entered_by_command_id=self._aggregate.entered_by_command_id,
            entered_revision=self._aggregate.entered_revision,
        )
        self._aggregate = aggregate
        self._revision = revision
        return ModeSwitchResult(aggregate=aggregate, replayed=False)

    def _begin_leave_mayor(
        self, command_id: str, prohibited: Set[ProhibitedCondition]
    ) -> ModeSwitchResult:
        """
        §7.1：Admin confirmation 进行中禁止离开（防止确认语义漂移）；
        Encounter/昏迷/撤权下若已异常处于 mayor 则允许安全关闭。
        """
        if ProhibitedCondition.ADMIN_CONFIRMATION_ACTIVE in prohibited:
            raise ModeSwitchError(
                DENY_MODE_BLOCKED_SYSTEM,
                "admin confirmation in progress; leaving blocked",
            )
        aggregate = ModeAggregate(
            binding_id=self._aggregate.binding_id,
            mode=PlayerMode.LEAVING_MAYOR,
            mode_version=self._aggregate.mode_version + 1,
            mayor_authority_version=self._aggregate.mayor_authority_version,
            pause_token_id=self._aggregate.pause_token_id,
            entered_by_command_id=self._aggregate.entered_by_command_id,
            entered_revision=self._aggregate.entered_revision,
        )
        self._aggregate = aggregate
        return ModeSwitchResult(aggregate=aggregate, replayed=False)

    def _commit_resident_active(
        self, command_id: str, prohibited: Set[ProhibitedCondition]
    ) -> ModeSwitchResult:
        """
        离开顺序收尾：关闭 projection → 提交 resident mode → 释放自己的 token。

        RULE-PLAYER-013：只释放 owner=player/reason=mayor_management 的 token，
        不解除 Dialogue/Combat/Shutdown token。
        """
        token_id = self._aggregate.pause_token_id
        released: Optional[PauseToken] = None
        if token_id is not None:
            try:
                released = self._pause_ledger.release(
                    command_id=f"{command_id}:release",
                    token_id=token_id,
                    owner=MAYOR_PAUSE_OWNER,
                )
            except PauseTokenError as exc:
                raise ModeSwitchError(exc.code) from exc

        aggregate = ModeAggregate(
            binding_id=self._aggregate.binding_id,
            mode=PlayerMode.RESIDENT_ACTIVE,
            mode_version=self._aggregate.mode_version + 1,
            mayor_authority_version=self._aggregate.mayor_authority_version,
            pause_token_id=None,
            entered_by_command_id=None,
            entered_revision=None,
        )
        self._aggregate = aggregate
        return ModeSwitchResult(aggregate=aggregate, replayed=False, pause_token=released)

    def force_safe_close(self, command_id: str) -> ModeSwitchResult:
        """
        §7.1：Mayor authority revoked 时强制安全关闭。

        从任意 mayor 相关状态确定地回到 resident_active。
        """
        if self._aggregate.mode is PlayerMode.RESIDENT_ACTIVE:
            return ModeSwitchResult(aggregate=self._aggregate, replayed=False)
        token_id = self._aggregate.pause_token_id
        if token_id and self._pause_ledger.has_token(token_id):
            self._pause_ledger.release(
                command_id=f"{command_id}:force_release",
                token_id=token_id,
                owner=MAYOR_PAUSE_OWNER,
            )
        aggregate = ModeAggregate(
            binding_id=self._aggregate.binding_id,
            mode=PlayerMode.RESIDENT_ACTIVE,
            mode_version=self._aggregate.mode_version + 1,
            mayor_authority_version=self._aggregate.mayor_authority_version,
            pause_token_id=None,
            entered_by_command_id=None,
            entered_revision=None,
        )
        self._aggregate = aggregate
        return ModeSwitchResult(aggregate=aggregate, replayed=False)

    @staticmethod
    def adjudicate_crash_recovery(
        mode: PlayerMode,
        token_alive: bool,
        stable_provable: bool,
    ) -> PlayerMode:
        """
        §8 crash 恢复裁定：

        - mayor_active 且 token 有效：恢复 Mayor UI，世界仍暂停
        - resident_active 但孤儿 token：由 Recovery Barrier 审计释放（返回 resident）
        - 中间态：可证明时选择唯一稳定态；无法证明时保持暂停（mayor_active）
        """
        if mode is PlayerMode.MAYOR_ACTIVE and token_alive:
            return PlayerMode.MAYOR_ACTIVE
        if mode is PlayerMode.RESIDENT_ACTIVE:
            return PlayerMode.RESIDENT_ACTIVE
        # 中间态（entering_mayor / leaving_mayor）
        if stable_provable:
            return (
                PlayerMode.MAYOR_ACTIVE if token_alive else PlayerMode.RESIDENT_ACTIVE
            )
        # 无法证明时保持暂停，避免世界在未确认状态下运行
        return PlayerMode.MAYOR_ACTIVE

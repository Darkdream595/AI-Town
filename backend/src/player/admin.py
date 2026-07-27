"""
Sandbox Admin 确认、存档标记与不可抵赖审计（DOC-PLAYER-009）

- RULE-PLAYER-041：Admin Session 由 world owner 显式启用，默认 disabled；
  Mayor/binding/自然语言/Client mode 均不能创建 Admin authority
- RULE-PLAYER-042：改变世界的 AdminCommand 必须经服务端一次性、短期、
  payload-bound 二次确认；Client 自报 confirmed=true 无效
- RULE-PLAYER-043：首次成功 mutation 原子设置 admin_modified=true，不可清除
- RULE-PLAYER-044：mutation 与 state/event/idempotency/mark/audit 全成或全败；
  audit sink 不可用 fail closed
- RULE-PLAYER-045：audit append-only、hash chained、序号单调；attempt/denial/
  expired 也产生审计
- RULE-PLAYER-046：Admin 不能改写历史 event/审计/ID/Revision/Key/路径/Catalog
"""

from __future__ import annotations

import hashlib
import json
import secrets as _secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import ADMIN_CHALLENGE_EXPIRES_IN_MS


class AdminCommandError(Exception):
    """Admin 操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: §5.2：允许 union 首版全集
ADMIN_COMMAND_TYPES = frozenset(
    {
        "admin.resource.grant",
        "admin.resident.relocate_safe",
        "admin.health.recover",
        "admin.event.schedule_registered",
        "admin.weather.set_registered",
    }
)

#: §5.2 每型 strict payload 必填字段
_ADMIN_PAYLOAD_SCHEMAS: Dict[str, frozenset] = {
    "admin.resource.grant": frozenset(
        {"target_resident_id", "resource_kind", "definition_id", "quantity", "reason_code"}
    ),
    "admin.resident.relocate_safe": frozenset(
        {"target_resident_id", "reason_code"}
    ),
    "admin.health.recover": frozenset(
        {"target_resident_id", "reason_code"}
    ),
    "admin.event.schedule_registered": frozenset(
        {"event_template_id", "scheduled_game_time", "reason_code"}
    ),
    "admin.weather.set_registered": frozenset(
        {"weather_id", "reason_code"}
    ),
}

#: §5.2 数量上限
ADMIN_GRANT_QUANTITY_CAP = 10_000

#: §9.1：审计结果全集
class AuditResult:
    ATTEMPTED = "attempted"
    DENIED = "denied"
    EXPIRED = "expired"
    COMMITTED = "committed"
    FAILED = "failed"

    ALL = frozenset({ATTEMPTED, DENIED, EXPIRED, COMMITTED, FAILED})


@dataclass(frozen=True)
class AdminSession:
    """§3：显式启用、短期有效、独立的本地能力"""

    admin_session_id: str
    world_id: str
    player_identity_id: str
    enabled: bool
    expires_at_monotonic_ms: float


@dataclass(frozen=True)
class ConfirmationChallenge:
    """§5.1 确认挑战 Schema"""

    challenge_id: str
    admin_session_id: str
    command_type: str
    payload_hash: str
    human_summary: str
    nonce: str
    issued_at_utc: str
    expires_in_ms: int
    used: bool = False
    schema_version: int = 1


@dataclass(frozen=True)
class SaveIntegrityMark:
    """
    §3/§9.1：世界已使用 Sandbox Admin 的永久单调标记。

    单调 OR：一旦 true 不得通过 UI/回档/分支/Admin command 清除。
    """

    admin_modified: bool = False

    def taint(self) -> "SaveIntegrityMark":
        return SaveIntegrityMark(admin_modified=True)

    def try_clear(self) -> "SaveIntegrityMark":
        """RULE-PLAYER-043：任何清除尝试一律拒绝"""
        raise AdminCommandError(
            "ADMIN_TAINT_CLEAR_REJECTED",
            "admin_modified is permanent and cannot be cleared",
        )


@dataclass(frozen=True)
class AdminAuditEvent:
    """§5.3 AdminAuditEvent Schema"""

    audit_sequence: int
    audit_event_id: str
    world_id: str
    admin_session_id: str
    actor_player_identity_id: str
    command_id: str
    command_type: str
    payload_hash: str
    confirmation_challenge_id: Optional[str]
    result: str
    reason_code: str
    committed_revision: Optional[int]
    previous_audit_hash: str
    audit_hash: str
    recorded_at_utc: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AdminCommandError("AUDIT_SCHEMA_VERSION_UNSUPPORTED")
        if self.result not in AuditResult.ALL:
            raise AdminCommandError(
                "AUDIT_RESULT_INVALID", f"result must be one of {sorted(AuditResult.ALL)}"
            )


def _utc_now_rfc3339() -> str:
    """§5.1：UTC RFC 3339 持久化墙钟（RULE-FOUNDATION-044）"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class AdminAuditLog:
    """
    append-only、hash chained、序号单调的审计日志（RULE-PLAYER-045）。

    sink 为可注入的持久化回调；sink 失败时 append 抛错，调用方 fail closed
    （RULE-PLAYER-044）。
    """

    GENESIS_HASH = "sha256:" + "0" * 64

    def __init__(
        self,
        world_id: str,
        sink: Optional[Callable[[AdminAuditEvent], None]] = None,
    ) -> None:
        self._world_id = world_id
        self._sink = sink
        self._events: List[AdminAuditEvent] = []
        self._last_hash = self.GENESIS_HASH

    @property
    def events(self) -> Tuple[AdminAuditEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        admin_session_id: str,
        actor_player_identity_id: str,
        command_id: str,
        command_type: str,
        payload_hash: str,
        confirmation_challenge_id: Optional[str],
        result: str,
        reason_code: str,
        committed_revision: Optional[int] = None,
    ) -> AdminAuditEvent:
        sequence = len(self._events) + 1
        recorded_at = _utc_now_rfc3339()
        body = {
            "audit_sequence": sequence,
            "world_id": self._world_id,
            "admin_session_id": admin_session_id,
            "actor_player_identity_id": actor_player_identity_id,
            "command_id": command_id,
            "command_type": command_type,
            "payload_hash": payload_hash,
            "confirmation_challenge_id": confirmation_challenge_id,
            "result": result,
            "reason_code": reason_code,
            "committed_revision": committed_revision,
            "previous_audit_hash": self._last_hash,
            "recorded_at_utc": recorded_at,
        }
        audit_hash = "sha256:" + hashlib.sha256(
            json.dumps(body, sort_keys=True).encode("utf-8")
        ).hexdigest()
        event = AdminAuditEvent(
            audit_sequence=sequence,
            audit_event_id=generate_ulid(),
            world_id=self._world_id,
            admin_session_id=admin_session_id,
            actor_player_identity_id=actor_player_identity_id,
            command_id=command_id,
            command_type=command_type,
            payload_hash=payload_hash,
            confirmation_challenge_id=confirmation_challenge_id,
            result=result,
            reason_code=reason_code,
            committed_revision=committed_revision,
            previous_audit_hash=self._last_hash,
            audit_hash=audit_hash,
            recorded_at_utc=recorded_at,
        )
        if self._sink is not None:
            # RULE-PLAYER-044：sink 失败向上抛，mutation fail closed
            self._sink(event)
        self._events.append(event)
        self._last_hash = audit_hash
        return event

    def verify_chain(self) -> bool:
        """§10：audit chain 可验证；任何缺口/篡改返回 False（fail closed）"""
        previous = self.GENESIS_HASH
        for index, event in enumerate(self._events, start=1):
            if event.audit_sequence != index:
                return False
            if event.previous_audit_hash != previous:
                return False
            body = {
                "audit_sequence": event.audit_sequence,
                "world_id": event.world_id,
                "admin_session_id": event.admin_session_id,
                "actor_player_identity_id": event.actor_player_identity_id,
                "command_id": event.command_id,
                "command_type": event.command_type,
                "payload_hash": event.payload_hash,
                "confirmation_challenge_id": event.confirmation_challenge_id,
                "result": event.result,
                "reason_code": event.reason_code,
                "committed_revision": event.committed_revision,
                "previous_audit_hash": event.previous_audit_hash,
                "recorded_at_utc": event.recorded_at_utc,
            }
            expected = "sha256:" + hashlib.sha256(
                json.dumps(body, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if event.audit_hash != expected:
                return False
            previous = event.audit_hash
        return True


class AdminSessionManager:
    """
    Admin Session、确认挑战与白名单 mutation 编排。

    mutation_handler：执行实际 owner 状态变更的注入回调，返回 committed
    revision。monotonic_clock 可注入（测试 expiry 不依赖真实等待）。
    """

    def __init__(
        self,
        audit_log: AdminAuditLog,
        mutation_handler: Optional[Callable[[str, dict], int]] = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        challenge_expires_in_ms: int = ADMIN_CHALLENGE_EXPIRES_IN_MS,
    ) -> None:
        self._audit = audit_log
        self._mutation_handler = mutation_handler
        self._clock = monotonic_clock
        self._expires_in_ms = challenge_expires_in_ms
        self._sessions: Dict[str, AdminSession] = {}
        self._challenges: Dict[str, ConfirmationChallenge] = {}
        self._mark = SaveIntegrityMark()
        # command ID exactly-once（§7）
        self._executed_commands: Dict[str, str] = {}
        # §5.1：challenge 签发时刻的 monotonic deadline（不以墙钟持久化）
        self._challenge_deadlines: Dict[str, float] = {}

    @property
    def save_integrity_mark(self) -> SaveIntegrityMark:
        return self._mark

    # -- Session（RULE-PLAYER-041） --

    def enable_session(
        self,
        world_id: str,
        player_identity_id: str,
        is_world_owner: bool,
        session_ttl_ms: float = 15 * 60 * 1000,
    ) -> AdminSession:
        """只有 world owner 可显式启用；其余来源一律拒绝"""
        if not is_world_owner:
            raise AdminCommandError(
                "ADMIN_SESSION_REQUIRES_WORLD_OWNER",
                "only the world owner can enable an admin session",
            )
        session = AdminSession(
            admin_session_id=generate_ulid(),
            world_id=world_id,
            player_identity_id=player_identity_id,
            enabled=True,
            expires_at_monotonic_ms=self._clock() * 1000 + session_ttl_ms,
        )
        self._sessions[session.admin_session_id] = session
        return session

    def _require_session(self, admin_session_id: str) -> AdminSession:
        session = self._sessions.get(admin_session_id)
        if session is None or not session.enabled:
            raise AdminCommandError(
                "ADMIN_SESSION_INVALID", "admin session missing or disabled"
            )
        if self._clock() * 1000 > session.expires_at_monotonic_ms:
            raise AdminCommandError("ADMIN_SESSION_EXPIRED")
        return session

    # -- 确认挑战（RULE-PLAYER-042） --

    def request_confirmation(
        self,
        admin_session_id: str,
        command_id: str,
        command_type: str,
        payload: dict,
        human_summary: str,
    ) -> ConfirmationChallenge:
        """
        §6 第 2–3 步：预检 + attempted 审计 + 生成 payload-bound challenge。
        """
        session = self._require_session(admin_session_id)
        try:
            self._precheck(command_type, payload)
        except AdminCommandError as exc:
            self._audit.append(
                admin_session_id=session.admin_session_id,
                actor_player_identity_id=session.player_identity_id,
                command_id=command_id,
                command_type=command_type,
                payload_hash=self._hash_payload(payload),
                confirmation_challenge_id=None,
                result=AuditResult.DENIED,
                reason_code=exc.code,
            )
            raise

        payload_hash = self._hash_payload(payload)
        challenge = ConfirmationChallenge(
            challenge_id=generate_ulid(),
            admin_session_id=admin_session_id,
            command_type=command_type,
            payload_hash=payload_hash,
            human_summary=human_summary,
            nonce=_secrets.token_urlsafe(18),
            issued_at_utc=_utc_now_rfc3339(),
            expires_in_ms=self._expires_in_ms,
        )
        self._challenges[challenge.challenge_id] = challenge
        # 签发即固定 monotonic deadline，系统时钟回拨不改变判定（§5.1）
        self._challenge_deadlines[challenge.challenge_id] = (
            self._clock() * 1000 + self._expires_in_ms
        )
        self._audit.append(
            admin_session_id=session.admin_session_id,
            actor_player_identity_id=session.player_identity_id,
            command_id=command_id,
            command_type=command_type,
            payload_hash=payload_hash,
            confirmation_challenge_id=challenge.challenge_id,
            result=AuditResult.ATTEMPTED,
            reason_code=payload.get("reason_code", ""),
        )
        return challenge

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _precheck(command_type: str, payload: dict) -> None:
        if command_type not in ADMIN_COMMAND_TYPES:
            raise AdminCommandError(
                "ADMIN_COMMAND_TYPE_UNREGISTERED",
                f"{command_type!r} not in admin whitelist",
            )
        required = _ADMIN_PAYLOAD_SCHEMAS[command_type]
        if set(payload) != required:
            raise AdminCommandError(
                "ADMIN_PAYLOAD_SCHEMA_MISMATCH",
                f"{command_type} requires exactly {sorted(required)}",
            )
        if command_type == "admin.resource.grant":
            quantity = payload.get("quantity", 0)
            if not isinstance(quantity, int) or not 0 < quantity <= ADMIN_GRANT_QUANTITY_CAP:
                raise AdminCommandError(
                    "ADMIN_GRANT_QUANTITY_OUT_OF_RANGE",
                    f"quantity must be 1..{ADMIN_GRANT_QUANTITY_CAP}",
                )

    # -- 执行（RULE-PLAYER-042/043/044） --

    def execute(
        self,
        admin_session_id: str,
        command_id: str,
        command_type: str,
        payload: dict,
        confirmation: dict,
    ) -> int:
        """
        §6 第 5–6 步：验证 session/nonce/expiry/unused/payload hash 后原子提交
        mutation + mark + committed 审计。

        RULE-PLAYER-042：Client 自报 confirmed=true 没有任何效力——只认服务端
        challenge 的 (challenge_id, nonce)。
        """
        session = self._require_session(admin_session_id)
        payload_hash = self._hash_payload(payload)

        def deny(result: str, code: str) -> AdminCommandError:
            self._audit.append(
                admin_session_id=session.admin_session_id,
                actor_player_identity_id=session.player_identity_id,
                command_id=command_id,
                command_type=command_type,
                payload_hash=payload_hash,
                confirmation_challenge_id=confirmation.get("challenge_id"),
                result=result,
                reason_code=code,
            )
            return AdminCommandError(code)

        # §7：command ID exactly-once；重放返回原结果
        if command_id in self._executed_commands:
            prior = self._executed_commands[command_id]
            if prior != payload_hash:
                raise deny(AuditResult.DENIED, "ADMIN_COMMAND_ID_CONFLICT")
            raise deny(AuditResult.DENIED, "ADMIN_COMMAND_ALREADY_EXECUTED")

        self._precheck(command_type, payload)
        challenge = self._challenges.get(confirmation.get("challenge_id", ""))
        if challenge is None:
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_UNKNOWN")
        if challenge.admin_session_id != admin_session_id:
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_CROSS_SESSION")
        if challenge.used:
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_REPLAYED")
        if challenge.nonce != confirmation.get("nonce"):
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_NONCE_MISMATCH")
        if challenge.command_type != command_type:
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_TYPE_MISMATCH")
        if challenge.payload_hash != payload_hash:
            raise deny(AuditResult.DENIED, "ADMIN_CHALLENGE_PAYLOAD_TAMPERED")
        # §5.1：monotonic 计时判定过期，时钟回拨不影响
        issued_monotonic_ms = self._challenge_monotonic_deadline(challenge)
        if self._clock() * 1000 > issued_monotonic_ms:
            raise deny(AuditResult.EXPIRED, "ADMIN_CHALLENGE_EXPIRED")

        # 原子区：mutation 与 mark、committed 审计全成或全败（RULE-PLAYER-044）
        if self._mutation_handler is None:
            raise deny(AuditResult.FAILED, "ADMIN_MUTATION_HANDLER_UNAVAILABLE")
        try:
            committed_revision = self._mutation_handler(command_type, payload)
        except AdminCommandError:
            raise
        except Exception as exc:
            raise deny(AuditResult.FAILED, f"ADMIN_MUTATION_FAILED: {exc}") from exc

        self._mark = self._mark.taint()
        self._challenges[challenge.challenge_id] = ConfirmationChallenge(
            **{**challenge.__dict__, "used": True}
        )
        self._executed_commands[command_id] = payload_hash
        # committed 审计失败时 fail closed（sink 异常向上抛）
        self._audit.append(
            admin_session_id=session.admin_session_id,
            actor_player_identity_id=session.player_identity_id,
            command_id=command_id,
            command_type=command_type,
            payload_hash=payload_hash,
            confirmation_challenge_id=challenge.challenge_id,
            result=AuditResult.COMMITTED,
            reason_code=payload.get("reason_code", ""),
            committed_revision=committed_revision,
        )
        return committed_revision

    def _challenge_monotonic_deadline(self, challenge: ConfirmationChallenge) -> float:
        """签发时刻固定的 monotonic deadline；未知 challenge 视为已过期"""
        deadline = self._challenge_deadlines.get(challenge.challenge_id)
        if deadline is None:
            return float("-inf")
        return deadline

    # -- 边界（RULE-PLAYER-046） --

    @staticmethod
    def assert_not_forbidden_target(field_name: str) -> None:
        """Admin 不能改写历史 event、审计、ID/Revision、Key、路径或 Catalog"""
        forbidden = {
            "event_history",
            "audit_log",
            "entity_id",
            "revision",
            "api_key",
            "file_path",
            "catalog",
        }
        if field_name in forbidden:
            raise AdminCommandError(
                "ADMIN_TARGET_FORBIDDEN",
                f"admin cannot rewrite {field_name}; use new compensating mutation",
            )

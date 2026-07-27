"""
玩家交互能力与统一验证（DOC-PLAYER-004）

- RULE-PLAYER-016：Client 只能建议 target/action/parameters；actor 由 binding 解析
- RULE-PLAYER-017：PlayerCommand 与 AI ActionProposal 进入同一 Domain validator
- RULE-PLAYER-018：Capability Projection 是 revision-stamped hint，提交点重校验
- RULE-PLAYER-019：交互失败不消耗物品/货币/体力/冷却/Revision
- RULE-PLAYER-020：player.action / mayor.* / admin.* 三种 envelope 禁止互路由
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..ai import ACTION_CATALOG
from .constants import (
    DENY_CAPABILITY_STALE,
    DENY_COMMAND_ID_CONFLICT,
    MAX_COMMAND_PAYLOAD_BYTES,
    MAX_INTERACTION_CANDIDATES,
)


class PlayerCommandError(Exception):
    """PlayerCommand 处理失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: DES-PLAYER-004：envelope 根字段全集（拒绝额外根字段）
_ALLOWED_ENVELOPE_FIELDS = frozenset(
    {"protocol_version", "command_id", "world_id", "expected_revision", "type", "payload"}
)
_ALLOWED_PAYLOAD_FIELDS = frozenset({"action_id", "target_entity_id", "parameters"})

PLAYER_COMMAND_TYPE = "player.action"
MAYOR_COMMAND_PREFIX = "mayor."
ADMIN_COMMAND_PREFIX = "admin."

#: §9：恶意参数模式（prototype key、HTML、脚本 URL、文件路径）
_FORBIDDEN_PARAM_KEYS = frozenset({"__proto__", "prototype", "constructor"})
_HTML_PATTERN = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_SCRIPT_URL_PATTERN = re.compile(r"(?i)\b(javascript|data|vbscript)\s*:")
_FILE_PATH_PATTERN = re.compile(r"(?i)([a-z]:\\|file://|/etc/|/usr/|\.\./)")


@dataclass(frozen=True)
class PlayerCommand:
    """DES-PLAYER-004：已认证 actor、带幂等键与 Revision 的结构化命令"""

    command_id: str
    world_id: str
    expected_revision: int
    action_id: str
    target_entity_id: Optional[str]
    parameters: dict
    actor_resident_id: str  # 由 binding 解析，非 Client 提供
    protocol_version: int = 1
    type: str = PLAYER_COMMAND_TYPE

    def payload_hash(self) -> str:
        canonical = json.dumps(
            {
                "world_id": self.world_id,
                "action_id": self.action_id,
                "target_entity_id": self.target_entity_id,
                "parameters": self.parameters,
                "actor_resident_id": self.actor_resident_id,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DomainValidationResult:
    """Domain validator 的统一结果（RULE-PLAYER-017：Player/AI 共用形状）"""

    legal: bool
    reason_code: Optional[str] = None
    committed_event_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    accepted: bool
    reason_code: Optional[str] = None
    committed_revision: Optional[int] = None


@dataclass(frozen=True)
class InteractionCandidate:
    """
    §3：服务端从距离、视线、Scene、状态和权限派生的候选。

    只含最小公开字段（§9）。
    """

    entity_id: str
    display_name: str
    distance_wu: float
    has_line_of_sight: bool
    state_allows_interaction: bool
    permission_known: bool


@dataclass(frozen=True)
class CandidateSortKey:
    """§6 第 2 步排序键：可交互性优先，其次距离，最后 ID 保证可重复"""

    interactable_rank: int  # 0 = 可交互
    distance_wu: float
    entity_id: str


@dataclass(frozen=True)
class RankedCandidate:
    candidate: InteractionCandidate
    sort_key: CandidateSortKey


def rank_candidates(
    candidates: List[InteractionCandidate],
) -> List[RankedCandidate]:
    """
    §6：按距离、视线、交互半径、Scene、actor 状态和公开权限排序。

    上限 16（§9）；排序键完全确定，同一输入必得同一顺序。
    """
    ranked = [
        RankedCandidate(
            candidate=c,
            sort_key=CandidateSortKey(
                interactable_rank=0
                if (c.has_line_of_sight and c.state_allows_interaction and c.permission_known)
                else 1,
                distance_wu=c.distance_wu,
                entity_id=c.entity_id,
            ),
        )
        for c in candidates
    ]
    ranked.sort(
        key=lambda r: (
            r.sort_key.interactable_rank,
            r.sort_key.distance_wu,
            r.sort_key.entity_id,
        )
    )
    return ranked[:MAX_INTERACTION_CANDIDATES]


#: Domain validator 签名：与 AI ActionProposal 共用同一入口（RULE-PLAYER-017）
DomainValidator = Callable[[str, Optional[str], dict, int], DomainValidationResult]


class PlayerCommandRouter:
    """
    envelope 校验 + actor 解析 + canonical action 路由 + 幂等。

    domain_validators 是与 AI 共用的注册表：每个 action_id 对应一个
    owner validator。PLAYER 不创建新 Action 类型（§2 非目标）。
    """

    def __init__(
        self,
        domain_validators: Optional[Dict[str, DomainValidator]] = None,
    ) -> None:
        self._validators = dict(domain_validators or {})
        # (world_id, command_id) -> (payload_hash, receipt)
        self._idempotency: Dict[Tuple[str, str], Tuple[str, CommandReceipt]] = {}
        # Capability projection 的生成 Revision（RULE-PLAYER-018）
        self._projection_revisions: Dict[str, int] = {}

    def register_validator(self, action_id: str, validator: DomainValidator) -> None:
        if action_id not in ACTION_CATALOG:
            raise PlayerCommandError(
                "PLAYER_ACTION_UNREGISTERED",
                f"action {action_id} not in canonical catalog",
            )
        self._validators[action_id] = validator

    def stamp_capability_projection(self, binding_id: str, revision: int) -> None:
        self._projection_revisions[binding_id] = revision

    def submit_player_command(
        self,
        envelope: dict,
        actor_resident_id: str,
        current_revision: int,
        binding_id: Optional[str] = None,
    ) -> CommandReceipt:
        """
        §6 第 4–6 步：验证 envelope → 解析 actor → 路由 Domain validator。

        RULE-PLAYER-019：失败路径不产生任何提交，receipt 即全部结果。
        """
        command = self.parse_envelope(envelope, actor_resident_id)

        idem_key = (command.world_id, command.command_id)
        cached = self._idempotency.get(idem_key)
        if cached is not None:
            cached_hash, cached_receipt = cached
            if cached_hash != command.payload_hash():
                raise PlayerCommandError(
                    DENY_COMMAND_ID_CONFLICT,
                    "same command id with different payload",
                )
            # §7：重复提交最多一次结算
            return cached_receipt

        # RULE-PLAYER-018：projection 过期不静默执行，要求刷新后重试
        if binding_id is not None:
            projection_revision = self._projection_revisions.get(binding_id)
            if projection_revision is not None and projection_revision < current_revision:
                receipt = CommandReceipt(
                    command_id=command.command_id,
                    accepted=False,
                    reason_code=DENY_CAPABILITY_STALE,
                )
                self._idempotency[idem_key] = (command.payload_hash(), receipt)
                return receipt

        result = self.route_canonical_action(
            actor=command.actor_resident_id,
            action_id=command.action_id,
            target_entity_id=command.target_entity_id,
            parameters=command.parameters,
            revision=current_revision,
        )
        receipt = CommandReceipt(
            command_id=command.command_id,
            accepted=result.legal,
            reason_code=result.reason_code,
            committed_revision=current_revision if result.legal else None,
        )
        self._idempotency[idem_key] = (command.payload_hash(), receipt)
        return receipt

    def parse_envelope(
        self, envelope: dict, actor_resident_id: str
    ) -> PlayerCommand:
        """
        DES-PLAYER-004 + §9：strict envelope 校验。

        RULE-PLAYER-020：player.action envelope 不能构造 Mayor/Admin mutation。
        """
        unknown = set(envelope) - _ALLOWED_ENVELOPE_FIELDS
        if unknown:
            raise PlayerCommandError(
                "PLAYER_ENVELOPE_UNKNOWN_FIELD", f"extra root fields: {sorted(unknown)}"
            )
        if envelope.get("protocol_version") != 1:
            raise PlayerCommandError("PLAYER_ENVELOPE_PROTOCOL_VERSION")

        command_type = envelope.get("type")
        if not isinstance(command_type, str):
            raise PlayerCommandError("PLAYER_ENVELOPE_TYPE_INVALID")
        if command_type.startswith((MAYOR_COMMAND_PREFIX, ADMIN_COMMAND_PREFIX)):
            # RULE-PLAYER-020：禁止从普通交互路由到 Mayor/Admin union
            raise PlayerCommandError(
                "PLAYER_ENVELOPE_UNION_CONFUSION",
                f"{command_type} cannot be routed as player.action",
            )
        if command_type != PLAYER_COMMAND_TYPE:
            raise PlayerCommandError(
                "PLAYER_ENVELOPE_TYPE_INVALID", f"type must be {PLAYER_COMMAND_TYPE}"
            )

        try:
            envelope_size = len(json.dumps(envelope).encode("utf-8"))
        except (TypeError, ValueError):
            raise PlayerCommandError("PLAYER_ENVELOPE_NOT_SERIALIZABLE")
        if envelope_size > MAX_COMMAND_PAYLOAD_BYTES:
            raise PlayerCommandError("PLAYER_ENVELOPE_TOO_LARGE")

        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise PlayerCommandError("PLAYER_ENVELOPE_PAYLOAD_INVALID")
        unknown_payload = set(payload) - _ALLOWED_PAYLOAD_FIELDS
        if unknown_payload:
            raise PlayerCommandError(
                "PLAYER_ENVELOPE_UNKNOWN_FIELD",
                f"extra payload fields: {sorted(unknown_payload)}",
            )

        action_id = payload.get("action_id")
        if not isinstance(action_id, str) or action_id not in ACTION_CATALOG:
            # §9：拒绝未知 action；Catalog 是唯一真源
            raise PlayerCommandError(
                "PLAYER_ACTION_UNREGISTERED", f"unknown action {action_id!r}"
            )

        parameters = payload.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise PlayerCommandError("PLAYER_PARAMETERS_INVALID")
        self._validate_parameters(parameters)

        expected_revision = envelope.get("expected_revision")
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise PlayerCommandError("PLAYER_ENVELOPE_REVISION_INVALID")

        target = payload.get("target_entity_id")
        if target is not None and not isinstance(target, str):
            raise PlayerCommandError("PLAYER_TARGET_INVALID")

        return PlayerCommand(
            command_id=str(envelope.get("command_id") or ""),
            world_id=str(envelope.get("world_id") or ""),
            expected_revision=expected_revision,
            action_id=action_id,
            target_entity_id=target,
            parameters=parameters,
            actor_resident_id=actor_resident_id,
        )

    @classmethod
    def _validate_parameters(cls, parameters: dict) -> None:
        """§9：拒绝 prototype key、HTML、脚本 URL、任意文件路径"""
        for key, value in parameters.items():
            if key in _FORBIDDEN_PARAM_KEYS:
                raise PlayerCommandError(
                    "PLAYER_PARAMETERS_FORBIDDEN_KEY", f"forbidden key {key!r}"
                )
            if isinstance(value, dict):
                cls._validate_parameters(value)
            elif isinstance(value, str):
                cls._validate_parameter_string(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        cls._validate_parameter_string(item)
                    elif isinstance(item, dict):
                        cls._validate_parameters(item)

    @staticmethod
    def _validate_parameter_string(value: str) -> None:
        if _HTML_PATTERN.search(value):
            raise PlayerCommandError("PLAYER_PARAMETERS_HTML_REJECTED")
        if _SCRIPT_URL_PATTERN.search(value):
            raise PlayerCommandError("PLAYER_PARAMETERS_SCRIPT_URL_REJECTED")
        if _FILE_PATH_PATTERN.search(value):
            raise PlayerCommandError("PLAYER_PARAMETERS_FILE_PATH_REJECTED")

    def route_canonical_action(
        self,
        actor: str,
        action_id: str,
        target_entity_id: Optional[str],
        parameters: dict,
        revision: int,
    ) -> DomainValidationResult:
        """
        §5 接口：路由到 owner Domain validator。

        RULE-PLAYER-017：与 AI ActionProposal 同一个 validator 注册表，
        不存在玩家专用放宽版。
        """
        validator = self._validators.get(action_id)
        if validator is None:
            return DomainValidationResult(
                legal=False, reason_code="PLAYER_ACTION_NO_VALIDATOR"
            )
        return validator(actor, target_entity_id, parameters, revision)

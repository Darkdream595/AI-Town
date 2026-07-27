"""
Command Envelope 协议（DOC-BACKEND-005 RULE-BACKEND-025..030）

- 顶层固定六字段，未注册字段即 BACKEND_SCHEMA_INVALID，不忽略、不透传
- type 命中 Command Registry tagged union；payload strict Schema（schema_version 分发）
- Authoritative Field 伪造 → BACKEND_FORBIDDEN + 审计
- Revision 模式由 Registry 静态决定：strict 精确匹配 / relaxed 必须显式 null
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from ..foundation.errors import ApiError
from ..foundation.id_generator import is_valid_ulid
from ..foundation.schema_validate import SchemaValidationError, validate_payload
from ..security.permissions import enforce_role

PROTOCOL_VERSION = 1

COMMAND_ENVELOPE_FIELDS = frozenset({
    "protocol_version", "command_id", "world_id", "expected_revision",
    "type", "payload",
})

#: Authoritative Field：只能由服务器补充；payload 内出现即伪造（RULE-BACKEND-028）
AUTHORITATIVE_FIELDS = frozenset({
    "actor_id", "session_id", "settled_amount", "damage", "path",
    "game_time", "revision", "event_id",
})

REVISION_STRICT = "strict"
REVISION_RELAXED = "relaxed"


@dataclass(frozen=True)
class CommandSpec:
    type: str
    payload_schema: dict
    role: str                      # player / mayor / admin（registry 静态）
    revision_mode: str             # strict / relaxed（registry 静态）
    queue: str = "world_command"


class CommandRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec) -> None:
        if spec.type in self._specs:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "command_type_duplicate"})
        if spec.revision_mode not in (REVISION_STRICT, REVISION_RELAXED):
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "revision_mode_invalid"})
        self._specs[spec.type] = spec

    def get(self, command_type: str) -> CommandSpec:
        spec = self._specs.get(command_type)
        if spec is None:
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "command_type_unregistered"})
        return spec

    def all_types(self) -> Tuple[str, ...]:
        return tuple(sorted(self._specs))


def validate_envelope(registry: CommandRegistry, envelope: object,
                      protocol_version: int = PROTOCOL_VERSION) -> dict:
    """
    命令级验证顺序（DES-BACKEND-005 步骤 1/2/4/5/6；3 幂等键查询在 Orchestrator）：
    1. Envelope 顶层 Schema 与 protocol_version
    2. type 注册表命中（角色权限检查由调用方在步骤 2 位点执行 enforce_role）
    4. payload strict Schema（schema_version 分发）
    5. Authoritative Field 伪造检测
    6. Revision 模式检查
    """
    # 1) 顶层
    if not isinstance(envelope, dict):
        raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "envelope_not_object"})
    unknown = set(envelope.keys()) - COMMAND_ENVELOPE_FIELDS
    if unknown:
        raise ApiError("BACKEND_SCHEMA_INVALID",
                       {"reason_code": f"envelope_unknown_field:{sorted(unknown)[0]}"})
    missing = COMMAND_ENVELOPE_FIELDS - set(envelope.keys())
    if missing:
        raise ApiError("BACKEND_SCHEMA_INVALID",
                       {"reason_code": f"envelope_missing_field:{sorted(missing)[0]}"})
    if envelope["protocol_version"] != protocol_version:
        raise ApiError("BACKEND_PROTOCOL_MISMATCH", {
            "expected": protocol_version, "received": envelope["protocol_version"]})
    if not isinstance(envelope["command_id"], str) or not is_valid_ulid(
            envelope["command_id"]):
        raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "command_id_invalid"})
    if not isinstance(envelope["world_id"], str) or not envelope["world_id"]:
        raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "world_id_invalid"})
    if not isinstance(envelope["type"], str):
        raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "type_invalid"})

    # 2) Registry 命中
    spec = registry.get(envelope["type"])

    # 4) payload strict Schema
    payload = envelope["payload"]
    try:
        validate_payload(payload, spec.payload_schema)
    except SchemaValidationError as exc:
        raise ApiError("BACKEND_SCHEMA_INVALID",
                       {"reason_code": exc.reason_code}) from None

    # 5) Authoritative Field 伪造
    forged = AUTHORITATIVE_FIELDS & set(payload.keys())
    if forged:
        raise ApiError("BACKEND_FORBIDDEN", {
            "reason_code": f"authoritative_field_forged:{sorted(forged)[0]}"})

    # 6) Revision 模式（Registry 静态决定，Client 不可协商）
    expected = envelope["expected_revision"]
    if spec.revision_mode == REVISION_STRICT:
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "expected_revision_required"})
    else:
        if expected is not None:
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "expected_revision_must_be_null"})
    return envelope


def check_strict_revision(spec: CommandSpec, expected_revision: Optional[int],
                          current_revision: int) -> None:
    """World Writer 执行时刻的 Strict 比较（入队不预判）"""
    if spec.revision_mode == REVISION_STRICT and expected_revision != current_revision:
        raise ApiError("BACKEND_STALE_REVISION", {
            "expected": expected_revision, "received": current_revision})


def make_receipt(command_id: str, result: str,
                 committed_revision: Optional[int] = None,
                 event_ids: Optional[list] = None,
                 error: Optional[dict] = None) -> dict:
    """CommandReceipt（DES-BACKEND-005）：result ∈ rejected/committed/failed"""
    return {
        "schema_version": 1,
        "command_id": command_id,
        "result": result,
        "committed_revision": committed_revision,
        "event_ids": list(event_ids) if event_ids else [],
        "error": error,
    }

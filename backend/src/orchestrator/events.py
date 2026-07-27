"""
Domain Event 协议（DOC-BACKEND-006 RULE-BACKEND-031..036）

- Envelope 固定十字段；render 可为 null，其余必填
- causation/correlation 由服务器在提交事务内填充；Client/模型因果声明一律忽略
- coalescible=true 的纯表现 delta 可在 Outbox 合并/丢弃，且不得携带权威语义
- payload/render 不得包含 Secret、他人私有 Belief、API Key、reasoning_content
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation.errors import ApiError
from ..foundation.schema_validate import SchemaValidationError, validate_payload

PROTOCOL_VERSION = 1

EVENT_ENVELOPE_FIELDS = frozenset({
    "protocol_version", "event_id", "world_id", "revision", "type",
    "game_time", "causation_id", "correlation_id", "payload", "render",
})

#: 权威禁词（render 内出现即拒绝；payload 出现 secret/api_key/authorization/
#: reasoning_content 也拒绝——RULE-BACKEND-036）
FORBIDDEN_RENDER_KEYS = frozenset({
    "balance", "amount", "damage", "hp", "permission", "role", "secret",
    "api_key", "authorization", "reasoning_content",
})
FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "secret", "api_key", "authorization", "reasoning_content",
})


@dataclass(frozen=True)
class EventSpec:
    type: str
    payload_schema: dict
    owner_domain: str
    coalescible: bool = False
    #: directed=仅 audience sessions 可见；broadcast=全部可见
    visibility: str = "broadcast"


class EventRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, EventSpec] = {}

    def register(self, spec: EventSpec) -> None:
        if spec.type in self._specs:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": "event_type_duplicate"})
        self._specs[spec.type] = spec

    def get(self, event_type: str) -> EventSpec:
        spec = self._specs.get(event_type)
        if spec is None:
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "event_type_unregistered"})
        return spec

    def all_types(self) -> Tuple[str, ...]:
        return tuple(sorted(self._specs))

    def is_coalescible(self, event_type: str) -> bool:
        return self.get(event_type).coalescible


def _scan_forbidden(value: object, forbidden: frozenset, path: str = "$") -> Optional[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden:
                return f"{path}.{key}"
            hit = _scan_forbidden(item, forbidden, path=f"{path}.{key}")
            if hit:
                return hit
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hit = _scan_forbidden(item, forbidden, path=f"{path}[{index}]")
            if hit:
                return hit
    return None


def build_event(registry: EventRegistry, id_factory: Callable[[], str],
                world_id: str, revision: int, event_type: str,
                game_time: int, causation_id: str, correlation_id: str,
                payload: dict, render: Optional[dict] = None) -> dict:
    """提交事务内组装 Envelope：schema 校验 + 禁词扫描 + 因果填充"""
    spec = registry.get(event_type)
    if spec.coalescible and render is not None:
        # coalescible delta 不得携带 render 权威语义（render 应为 null）
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": "coalescible_with_render"})
    if render is not None:
        hit = _scan_forbidden(render, FORBIDDEN_RENDER_KEYS)
        if hit:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": f"render_authority_leak:{hit}"})
    hit = _scan_forbidden(payload, FORBIDDEN_PAYLOAD_KEYS)
    if hit:
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": f"payload_secret_leak:{hit}"})
    try:
        validate_payload(payload, spec.payload_schema)
    except SchemaValidationError as exc:
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": f"event_payload_invalid:{exc.reason_code}"}) from None
    return {
        "protocol_version": PROTOCOL_VERSION,
        "event_id": id_factory(),
        "world_id": world_id,
        "revision": revision,
        "type": event_type,
        "game_time": game_time,
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "payload": payload,
        "render": render,
    }


def validate_event_envelope(registry: EventRegistry, event: dict) -> None:
    """发布前完整性校验：十字段 + Registry 命中"""
    if not isinstance(event, dict) or set(event.keys()) != EVENT_ENVELOPE_FIELDS:
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": "event_envelope_fields"})
    if event["render"] is not None and not isinstance(event["render"], dict):
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": "event_render_type"})
    registry.get(event["type"])


def visible_to_session(registry: EventRegistry, event: dict,
                       session_id: str, audience: Optional[frozenset] = None) -> bool:
    """Outbox 可见性过滤（RULE-BACKEND-036）：directed 事件仅 audience 内 Session 可见"""
    spec = registry.get(event["type"])
    if spec.visibility == "broadcast":
        return True
    return audience is not None and session_id in audience

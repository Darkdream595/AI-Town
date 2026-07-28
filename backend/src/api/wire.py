"""
Wire 契约登记（DOC-BACKEND-004..007）

- 全部 REST 请求/响应、WS 帧、命令 payload、事件 payload 的 Schema 唯一装配处
- 每个 Schema 携带 Golden Sample，注册即自验（RULE-BACKEND-037）
- 当前全部 v1；新版本与 Upcaster 由 owner 文档驱动追加，禁止就地修改 frozen 版本
"""

from __future__ import annotations

from ..foundation.schema_validate import make_object_schema
from ..orchestrator.commands import CommandRegistry, CommandSpec
from ..orchestrator.events import EventRegistry, EventSpec
from .schemas import SchemaEntry, SchemaRegistry

# ---------------------------------------------------------------------------
# 基础片段
# ---------------------------------------------------------------------------

_SV = {"type": "integer", "minimum": 1}
_ID = {"type": "string", "minLength": 1, "maxLength": 128}
_TEXT = {"type": "string", "maxLength": 2000}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}
_NULLABLE_ID = {"type": ["string", "null"]}
_ULID = {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
_ANY_OBJECT = {"type": "object"}

_GOLDEN_ULID = "01K1AB2CD3EF4GH5JK6MNP7QS0"

# ---------------------------------------------------------------------------
# REST 请求 Schema（DOC-BACKEND-004）
# ---------------------------------------------------------------------------

REST_REQUEST_SCHEMAS = {
    "SessionRequestV1": (
        make_object_schema({"schema_version": _SV}, ("schema_version",)),
        {"schema_version": 1},
    ),
    "ShutdownRequestV1": (
        make_object_schema({
            "schema_version": _SV,
            "shutdown_token": {
                "type": "string", "minLength": 32, "maxLength": 128,
            },
        }, ("schema_version", "shutdown_token")),
        {"schema_version": 1, "shutdown_token": "a" * 32},
    ),
    "WsTicketRequestV1": (
        make_object_schema({"schema_version": _SV, "world_id": _ID},
                           ("schema_version", "world_id")),
        {"schema_version": 1, "world_id": "world-000001"},
    ),
    "WorldCreateV1": (
        make_object_schema({
            "schema_version": _SV,
            "command_id": _ULID,
            "name": {"type": "string", "minLength": 1, "maxLength": 64},
            "seed_hex": {"type": "string", "pattern": "^[0-9a-f]{8,64}$"},
            "template_id": _ID,
        }, ("schema_version", "command_id", "name", "seed_hex")),
        {"schema_version": 1, "command_id": _GOLDEN_ULID,
         "name": "溪口镇", "seed_hex": "0123456789abcdef",
         "template_id": "template.default"},
    ),
    "WorldOpenV1": (
        make_object_schema({"schema_version": _SV, "command_id": _ULID},
                           ("schema_version",)),
        {"schema_version": 1},
    ),
    "WorldCloseV1": (
        make_object_schema({"schema_version": _SV}, ("schema_version",)),
        {"schema_version": 1},
    ),
    "WorldDeleteV1": (
        make_object_schema({"schema_version": _SV, "confirmation_token": _ID},
                           ("schema_version",)),
        {"schema_version": 1, "confirmation_token": "ctok-000001"},
    ),
    "SaveWriteV1": (
        make_object_schema({
            "schema_version": _SV,
            "name": {"type": "string", "minLength": 1, "maxLength": 64},
            "overwrite_save_id": _ID,
            "confirmation_token": _ID,
        }, ("schema_version", "name")),
        {"schema_version": 1, "name": "手动存档"},
    ),
    "SaveLoadV1": (
        make_object_schema({"schema_version": _SV}, ("schema_version",)),
        {"schema_version": 1},
    ),
    "SettingsV1": (
        make_object_schema({
            "schema_version": _SV,
            "language": {"type": "string", "enum": ["zh-CN", "en-US"]},
            "simulation_speed": {"type": "integer", "minimum": 0, "maximum": 4},
            "ui_scale": {"type": "number", "minimum": 0.5, "maximum": 2.0},
        }, ("schema_version",)),
        {"schema_version": 1, "language": "zh-CN",
         "simulation_speed": 1, "ui_scale": 1.0},
    ),
    "SecretPutV1": (
        make_object_schema({
            "schema_version": _SV,
            "api_key": {"type": "string", "minLength": 1, "maxLength": 256},
        }, ("schema_version", "api_key")),
        {"schema_version": 1, "api_key": "sk-test0000000000000000"},
    ),
    "SecretDeleteV1": (
        make_object_schema({"schema_version": _SV, "confirmation_token": _ID},
                           ("schema_version",)),
        {"schema_version": 1, "confirmation_token": "ctok-000001"},
    ),
    "ConfirmationRequestV1": (
        make_object_schema({
            "schema_version": _SV,
            "action": {"type": "string", "minLength": 1, "maxLength": 64},
        }, ("schema_version", "action")),
        {"schema_version": 1, "action": "world.delete"},
    ),
    "DiagnosticsRequestV1": (
        make_object_schema({
            "schema_version": _SV,
            "include_metrics": _BOOL,
            "include_logs": _BOOL,
        }, ("schema_version",)),
        {"schema_version": 1, "include_metrics": True, "include_logs": False},
    ),
}

# ---------------------------------------------------------------------------
# REST 响应 Schema（与 src/api/rest.py 的实际返回保持一致）
# ---------------------------------------------------------------------------

_WORLD_SUMMARY_PROPS = {
    "schema_version": _SV,
    "world_id": _ID,
    "name": {"type": "string"},
    "template_id": _ID,
    "state": {"type": "string", "enum": [
        "created", "opening", "open", "draining", "closed", "deleted"]},
    "current_revision": _INT,
    "created_at": {"type": "string"},
}
_WORLD_SUMMARY_GOLDEN = {
    "schema_version": 1, "world_id": "world-000001", "name": "溪口镇",
    "template_id": "template.default", "state": "created",
    "current_revision": 0, "created_at": "2026-01-01T00:00:00Z",
}

_WORLD_RUNTIME_PROPS = {
    "schema_version": _SV,
    "world_id": _ID,
    "state": {"type": "string"},
    "current_revision": _INT,
    "game_time": {},
    "read_only": _BOOL,
    "overloaded": _BOOL,
}
_WORLD_RUNTIME_GOLDEN = {
    "schema_version": 1, "world_id": "world-000001", "state": "open",
    "current_revision": 42, "game_time": None,
    "read_only": False, "overloaded": False,
}

_SAVE_SLOT_PROPS = {
    "schema_version": _SV,
    "save_id": _ID,
    "world_id": _ID,
    "name": {"type": "string"},
    "kind": {"type": "string", "enum": ["manual", "auto", "checkpoint"]},
    "revision": _INT,
    "written_at": {"type": "string"},
}
_SAVE_SLOT_GOLDEN = {
    "schema_version": 1, "save_id": "save-000001", "world_id": "world-000001",
    "name": "手动存档", "kind": "manual", "revision": 42,
    "written_at": "2026-01-01T00:00:00Z",
}

REST_RESPONSE_SCHEMAS = {
    "HealthStatusV1": (
        make_object_schema({
            "schema_version": _SV,
            "process_state": {"type": "string", "enum": [
                "booting", "recovering", "ready", "draining", "stopped"]},
            "recovery_barrier_active": _BOOL,
            "recovery_error": _NULLABLE_ID,
            "open_world_id": _NULLABLE_ID,
            "current_revision": _INT,
            "uptime_ms": _INT,
            "logging_degraded": _BOOL,
            "package_version": {"type": "string"},
            "build_id": {"type": "string"},
            "package_integrity": {"type": "string"},
        }, ("schema_version", "process_state", "recovery_barrier_active",
            "recovery_error", "open_world_id", "current_revision",
            "uptime_ms", "logging_degraded", "package_version", "build_id",
            "package_integrity")),
        {"schema_version": 1, "process_state": "ready",
         "recovery_barrier_active": False, "recovery_error": None,
         "open_world_id": "world-000001", "current_revision": 42,
         "uptime_ms": 1234, "logging_degraded": False,
         "package_version": "0.1.0", "build_id": "build.test",
         "package_integrity": "verified"},
    ),
    "AppMetaV1": (
        make_object_schema({
            "schema_version": _SV,
            "app_version": {"type": "string"},
            "protocol_version": _SV,
            "build_fingerprint": {"type": "string"},
            "package_version": {"type": "string"},
            "build_id": {"type": "string"},
            "current_revision": _INT,
        }, ("schema_version", "app_version", "protocol_version",
            "build_fingerprint", "package_version", "build_id",
            "current_revision")),
        {"schema_version": 1, "app_version": "0.1.0",
         "protocol_version": 1, "build_fingerprint": "dev",
         "package_version": "0.1.0", "build_id": "build.test",
         "current_revision": 42},
    ),
    "ShutdownStatusV1": (
        make_object_schema({
            "schema_version": _SV,
            "status": {"type": "string", "enum": ["shutting_down"]},
        }, ("schema_version", "status")),
        {"schema_version": 1, "status": "shutting_down"},
    ),
    "SessionInfoV1": (
        make_object_schema({
            "schema_version": _SV,
            "session_id": _ID,
            "role_state": {"type": "string", "enum": [
                "observer", "player", "mayor", "admin"]},
            "world_id": _NULLABLE_ID,
            "idle_remaining_ms": _INT,
            "csrf_rotation_due_ms": _INT,
        }, ("schema_version", "session_id", "role_state", "world_id",
            "idle_remaining_ms", "csrf_rotation_due_ms")),
        {"schema_version": 1, "session_id": "sess-000001",
         "role_state": "observer", "world_id": None,
         "idle_remaining_ms": 3600000, "csrf_rotation_due_ms": 1800000},
    ),
    "WsTicketV1": (
        make_object_schema({
            "schema_version": _SV,
            "ticket": _ID,
            "world_id": _ID,
            "expires_at_utc": {"type": "string"},
            "single_use": _BOOL,
        }, ("schema_version", "ticket", "world_id", "expires_at_utc",
            "single_use")),
        {"schema_version": 1, "ticket": "ticket-000001",
         "world_id": "world-000001",
         "expires_at_utc": "2026-01-01T00:00:00Z", "single_use": True},
    ),
    "WorldListV1": (
        make_object_schema({
            "schema_version": _SV,
            "worlds": {"type": "array", "items": make_object_schema(
                _WORLD_SUMMARY_PROPS, tuple(_WORLD_SUMMARY_PROPS))},
            "total": _INT,
        }, ("schema_version", "worlds", "total")),
        {"schema_version": 1, "worlds": [_WORLD_SUMMARY_GOLDEN], "total": 1},
    ),
    "WorldSummaryV1": (
        make_object_schema(_WORLD_SUMMARY_PROPS, tuple(_WORLD_SUMMARY_PROPS)),
        dict(_WORLD_SUMMARY_GOLDEN),
    ),
    "WorldDetailV1": (
        make_object_schema({
            **_WORLD_SUMMARY_PROPS,
            "seed_hex": {"type": "string"},
            "read_only": _BOOL,
            "overloaded": _BOOL,
        }, tuple(_WORLD_SUMMARY_PROPS) + ("seed_hex", "read_only",
                                          "overloaded")),
        {**_WORLD_SUMMARY_GOLDEN, "seed_hex": "0123456789abcdef",
         "read_only": False, "overloaded": False},
    ),
    "WorldRuntimeStateV1": (
        make_object_schema(_WORLD_RUNTIME_PROPS, tuple(_WORLD_RUNTIME_PROPS)),
        dict(_WORLD_RUNTIME_GOLDEN),
    ),
    "WorldDeleteResultV1": (
        make_object_schema({
            "schema_version": _SV,
            "world_id": _ID,
            "deleted": _BOOL,
        }, ("schema_version", "world_id", "deleted")),
        {"schema_version": 1, "world_id": "world-000001", "deleted": True},
    ),
    "SaveSlotListV1": (
        make_object_schema({
            "schema_version": _SV,
            "saves": {"type": "array", "items": make_object_schema(
                _SAVE_SLOT_PROPS, tuple(_SAVE_SLOT_PROPS))},
        }, ("schema_version", "saves")),
        {"schema_version": 1, "saves": [_SAVE_SLOT_GOLDEN]},
    ),
    "SaveSlotV1": (
        make_object_schema(_SAVE_SLOT_PROPS, tuple(_SAVE_SLOT_PROPS)),
        dict(_SAVE_SLOT_GOLDEN),
    ),
    "SecretStatusV1": (
        make_object_schema({
            "schema_version": _SV,
            "secret_kind": _ID,
            "configured": _BOOL,
            "storage_backend": _NULLABLE_ID,
            "masked_suffix": _NULLABLE_ID,
            "last_verified_at": _NULLABLE_ID,
            "last_verify_result": {"type": "string"},
        }, ("schema_version", "secret_kind", "configured", "storage_backend",
            "masked_suffix", "last_verified_at", "last_verify_result")),
        {"schema_version": 1, "secret_kind": "deepseek_api_key",
         "configured": True, "storage_backend": "memory",
         "masked_suffix": "0000", "last_verified_at": None,
         "last_verify_result": "not_verified"},
    ),
    "ConfirmationTokenV1": (
        make_object_schema({
            "schema_version": _SV,
            "challenge_id": _ID,
            "confirmation_token": _ID,
            "expires_in_ms": _INT,
        }, ("schema_version", "challenge_id", "confirmation_token",
            "expires_in_ms")),
        {"schema_version": 1, "challenge_id": "chal-000001",
         "confirmation_token": "ctok-000001", "expires_in_ms": 60000},
    ),
    "JobResourceV1": (
        make_object_schema({
            "schema_version": _SV,
            "job_id": _ID,
            "kind": _ID,
            "state": {"type": "string", "enum": [
                "queued", "running", "succeeded", "failed"]},
            "result_ref": _NULLABLE_ID,
            "reason_code": _NULLABLE_ID,
        }, ("schema_version", "job_id", "kind", "state", "result_ref",
            "reason_code")),
        {"schema_version": 1, "job_id": "job-000001",
         "kind": "diagnostics_package", "state": "succeeded",
         "result_ref": "diagpkg.local", "reason_code": None},
    ),
    "MetricsSnapshotV1": (
        make_object_schema({"schema_version": _SV}, ("schema_version",),
                           additional=True),
        {"schema_version": 1, "counters": {}, "gauges": {}},
    ),
}

# ---------------------------------------------------------------------------
# WS 帧 Schema（DOC-BACKEND-003 §5 帧 Envelope）
# ---------------------------------------------------------------------------

WS_FRAME_SCHEMAS = {
    "WsFrameEnvelopeV1": (
        make_object_schema({
            "protocol_version": _SV,
            "frame_type": {"type": "string", "enum": [
                "hello_ack", "command_receipt", "event", "error", "heartbeat",
                "snapshot_begin", "snapshot_chunk", "snapshot_end"]},
            "frame_id": _ID,
            "payload": _ANY_OBJECT,
        }, ("protocol_version", "frame_type", "frame_id", "payload")),
        {"protocol_version": 1, "frame_type": "heartbeat",
         "frame_id": "frame-000001",
         "payload": {"schema_version": 1, "heartbeat_id": "hb-000001"}},
    ),
}

# ---------------------------------------------------------------------------
# 命令 payload Schema（DOC-BACKEND-005 §5 基线 Registry 行）
# ---------------------------------------------------------------------------

COMMAND_PAYLOAD_SCHEMAS = {
    "PlayerMoveTargetV1": (
        make_object_schema({
            "schema_version": _SV,
            "target": make_object_schema({
                "scene_id": _ID,
                "x_wu": _NUM,
                "y_wu": _NUM,
            }, ("scene_id", "x_wu", "y_wu")),
        }, ("schema_version", "target")),
        {"schema_version": 1, "target": {
            "scene_id": "region.crown_creek_town", "x_wu": 1040.0,
            "y_wu": 772.5}},
    ),
    "PlayerDialogueSayV1": (
        make_object_schema({
            "schema_version": _SV,
            "text": {"type": "string", "minLength": 1, "maxLength": 200},
            "target_resident_id": _ID,
        }, ("schema_version", "text")),
        {"schema_version": 1, "text": "你好，镇长！"},
    ),
    "MayorTaxProposeV1": (
        make_object_schema({
            "schema_version": _SV,
            "rate_bp": {"type": "integer", "minimum": 0, "maximum": 2000},
            "reason": _TEXT,
        }, ("schema_version", "rate_bp")),
        {"schema_version": 1, "rate_bp": 500, "reason": "修缮码头"},
    ),
    "AdminResourceGrantV1": (
        make_object_schema({
            "schema_version": _SV,
            "resident_id": _ID,
            "resource": _ID,
            "amount": _INT,
        }, ("schema_version", "resident_id", "resource", "amount")),
        {"schema_version": 1, "resident_id": "res-000001",
         "resource": "gold", "amount": 100},
    ),
    "SystemWorldPauseV1": (
        make_object_schema({
            "schema_version": _SV,
            "paused": _BOOL,
        }, ("schema_version", "paused")),
        {"schema_version": 1, "paused": True},
    ),
}

#: (type, payload_schema_name, role, revision_mode)
COMMAND_SPECS = (
    ("player.move.set_target", "PlayerMoveTargetV1", "player", "relaxed"),
    ("player.dialogue.say", "PlayerDialogueSayV1", "player", "relaxed"),
    ("mayor.tax.propose", "MayorTaxProposeV1", "mayor", "strict"),
    ("admin.resource.grant", "AdminResourceGrantV1", "admin", "strict"),
    ("system.world.pause", "SystemWorldPauseV1", "player", "relaxed"),
)

# ---------------------------------------------------------------------------
# 事件 payload Schema（DOC-BACKEND-006 §5 基线 Registry 行）
# ---------------------------------------------------------------------------

EVENT_PAYLOAD_SCHEMAS = {
    "EconomyTransactionCommittedV1": (
        make_object_schema({
            "schema_version": _SV,
            "transaction_id": _ID,
            "from_id": _ID,
            "to_id": _ID,
            "amount": _INT,
            "currency": _ID,
        }, ("schema_version", "transaction_id", "from_id", "to_id", "amount",
            "currency")),
        {"schema_version": 1, "transaction_id": "txn-000001",
         "from_id": "res-000001", "to_id": "res-000002", "amount": 12,
         "currency": "gold"},
    ),
    "ResidentActionCompletedV1": (
        make_object_schema({
            "schema_version": _SV,
            "resident_id": _ID,
            "action_id": _ID,
            "outcome": {"type": "string", "enum": [
                "succeeded", "failed", "cancelled"]},
        }, ("schema_version", "resident_id", "action_id", "outcome")),
        {"schema_version": 1, "resident_id": "res-000001",
         "action_id": "act-000001", "outcome": "succeeded"},
    ),
    "DialogueLineSpokenV1": (
        make_object_schema({
            "schema_version": _SV,
            "speaker_id": _ID,
            "listener_ids": {"type": "array", "items": _ID, "maxItems": 16},
            "text": {"type": "string", "minLength": 1, "maxLength": 500},
        }, ("schema_version", "speaker_id", "listener_ids", "text")),
        {"schema_version": 1, "speaker_id": "res-000001",
         "listener_ids": ["res-000002"], "text": "今晚码头见。"},
    ),
    "RenderPositionDeltaV1": (
        make_object_schema({
            "schema_version": _SV,
            "entity_id": _ID,
            "position": make_object_schema({
                "scene_id": _ID,
                "x_wu": _NUM,
                "y_wu": _NUM,
            }, ("scene_id", "x_wu", "y_wu")),
            "facing_degrees": {"type": "integer", "minimum": 0, "maximum": 359},
        }, ("schema_version", "entity_id", "position", "facing_degrees")),
        {"schema_version": 1, "entity_id": _GOLDEN_ULID, "position": {
            "scene_id": "region.crown_creek_town", "x_wu": 1040.0,
            "y_wu": 772.5}, "facing_degrees": 90},
    ),
    "WorldWeatherChangedV1": (
        make_object_schema({
            "schema_version": _SV,
            "weather": {"type": "string", "enum": [
                "sunny", "cloudy", "rain", "storm", "snow"]},
            "started_at_tick": _INT,
        }, ("schema_version", "weather", "started_at_tick")),
        {"schema_version": 1, "weather": "rain", "started_at_tick": 123456},
    ),
}

#: (type, payload_schema_name, owner_domain, coalescible, visibility)
EVENT_SPECS = (
    ("economy.transaction.committed", "EconomyTransactionCommittedV1",
     "economy", False, "broadcast"),
    ("resident.action.completed", "ResidentActionCompletedV1",
     "residents", False, "broadcast"),
    ("dialogue.line.spoken", "DialogueLineSpokenV1",
     "dialogue", False, "directed"),
    ("render.position.delta", "RenderPositionDeltaV1",
     "backend", True, "broadcast"),
    ("world.weather.changed", "WorldWeatherChangedV1",
     "events", False, "broadcast"),
)


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------

def register_rest_schemas(registry: SchemaRegistry) -> None:
    for name, (schema, golden) in sorted(REST_REQUEST_SCHEMAS.items()):
        registry.register(SchemaEntry(
            name=name, version=1, owner_doc_id="DOC-BACKEND-004",
            status="active", kind="rest_resource",
            schema=schema, golden_sample=golden))
    for name, (schema, golden) in sorted(REST_RESPONSE_SCHEMAS.items()):
        if registry.contains(name, 1):  # 请求/响应共用名（SettingsV1）
            continue
        registry.register(SchemaEntry(
            name=name, version=1, owner_doc_id="DOC-BACKEND-004",
            status="active", kind="rest_resource",
            schema=schema, golden_sample=golden))


def register_ws_frame_schemas(registry: SchemaRegistry) -> None:
    for name, (schema, golden) in sorted(WS_FRAME_SCHEMAS.items()):
        registry.register(SchemaEntry(
            name=name, version=1, owner_doc_id="DOC-BACKEND-003",
            status="active", kind="ws_frame",
            schema=schema, golden_sample=golden))


def register_command_specs(schemas: SchemaRegistry,
                           registry: CommandRegistry) -> None:
    for type_, schema_name, role, revision_mode in COMMAND_SPECS:
        schema, golden = COMMAND_PAYLOAD_SCHEMAS[schema_name]
        if not schemas.contains(schema_name, 1):
            schemas.register(SchemaEntry(
                name=schema_name, version=1, owner_doc_id="DOC-BACKEND-005",
                status="active", kind="command_payload",
                schema=schema, golden_sample=golden))
        registry.register(CommandSpec(
            type=type_, payload_schema=schema, role=role,
            revision_mode=revision_mode))


def register_event_specs(schemas: SchemaRegistry,
                         registry: EventRegistry) -> None:
    for type_, schema_name, owner_domain, coalescible, visibility in EVENT_SPECS:
        schema, golden = EVENT_PAYLOAD_SCHEMAS[schema_name]
        if not schemas.contains(schema_name, 1):
            schemas.register(SchemaEntry(
                name=schema_name, version=1, owner_doc_id="DOC-BACKEND-006",
                status="active", kind="event_payload",
                schema=schema, golden_sample=golden))
        registry.register(EventSpec(
            type=type_, payload_schema=schema, owner_domain=owner_domain,
            coalescible=coalescible, visibility=visibility))


def register_wire_contracts(schemas: SchemaRegistry,
                            commands: CommandRegistry,
                            events: EventRegistry) -> None:
    """进程装配唯一入口（bootstrap 与测试共用）"""
    register_rest_schemas(schemas)
    register_ws_frame_schemas(schemas)
    register_command_specs(schemas, commands)
    register_event_specs(schemas, events)

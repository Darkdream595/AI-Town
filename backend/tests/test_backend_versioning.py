"""TEST-BACKEND-025..027：版本分层、失配矩阵、Upcaster 链与 Registry 完整性"""
from __future__ import annotations

import copy

import pytest

from backend_helpers import ORIGIN, make_assembly, make_client
from src.api.schemas import (
    UPCAST_CHAIN_MAX,
    SchemaEntry,
    SchemaRegistry,
    assert_versioning_policy,
    detect_breaking_changes,
)
from src.foundation.errors import ApiError
from src.foundation.schema_validate import make_object_schema

_SV = {"type": "integer", "minimum": 1}


def _entry(name, version, schema, golden, status="active",
           kind="rest_resource"):
    return SchemaEntry(name=name, version=version,
                       owner_doc_id="DOC-BACKEND-004", status=status,
                       kind=kind, schema=schema, golden_sample=golden)


V1_SCHEMA = make_object_schema(
    {"schema_version": _SV, "name": {"type": "string"}},
    ("schema_version", "name"))
V1_GOLDEN = {"schema_version": 1, "name": "x"}
V2_SCHEMA = make_object_schema(
    {"schema_version": _SV, "name": {"type": "string"},
     "label": {"type": "string"}},
    ("schema_version", "name"))
V2_GOLDEN = {"schema_version": 2, "name": "x", "label": "y"}


# ---------------------------------------------------------------------------
# TEST-BACKEND-025：RULE-BACKEND-037..038 版本分层与兼容白名单 CI diff
# ---------------------------------------------------------------------------

class TestVersionLayers:
    def test_register_self_validates_golden(self):
        registry = SchemaRegistry()
        registry.register(_entry("DemoV", 1, V1_SCHEMA, V1_GOLDEN))
        with pytest.raises(ApiError) as exc_info:
            registry.register(_entry("BadV", 1, V1_SCHEMA,
                                     {"schema_version": 1}))  # 缺 name
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_duplicate_registration_rejected(self):
        registry = SchemaRegistry()
        registry.register(_entry("DemoV", 1, V1_SCHEMA, V1_GOLDEN))
        with pytest.raises(ApiError):
            registry.register(_entry("DemoV", 1, V1_SCHEMA, V1_GOLDEN))

    def test_frozen_entry_fingerprint_recorded(self):
        registry = SchemaRegistry()
        entry = _entry("FrozenV", 1, V1_SCHEMA, V1_GOLDEN, status="frozen")
        registry.register(entry)
        assert entry.frozen_hash
        assert registry.audit_integrity() == []

    def test_frozen_modification_detected(self):
        registry = SchemaRegistry()
        entry = _entry("FrozenV", 1, V1_SCHEMA, V1_GOLDEN, status="frozen")
        registry.register(entry)
        entry.schema = copy.deepcopy(V2_SCHEMA)  # 篡改 frozen
        assert "frozen_modified:FrozenVv1" in registry.audit_integrity()

    def test_compatible_vs_breaking_whitelist(self):
        # Compatible：新增 optional 字段
        assert detect_breaking_changes(V1_SCHEMA, V2_SCHEMA) == []
        # Breaking：删除字段
        assert "field_removed:label" in detect_breaking_changes(
            V2_SCHEMA, V1_SCHEMA)
        # Breaking：optional 变必填（字段在两版中都存在）
        v1_with_label = make_object_schema(
            {"schema_version": _SV, "name": {"type": "string"},
             "label": {"type": "string"}},
            ("schema_version", "name"))
        v2_required = copy.deepcopy(v1_with_label)
        v2_required["required"].append("label")
        assert "optional_to_required:label" in detect_breaking_changes(
            v1_with_label, v2_required)
        # Breaking：新字段直接必填（旧数据无此字段）
        assert "new_field_required:label" in detect_breaking_changes(
            V1_SCHEMA, v2_required)
        # Breaking：字段类型变更
        v2_typed = copy.deepcopy(V2_SCHEMA)
        v2_typed["properties"]["name"] = {"type": "integer"}
        assert "field_type_changed:name" in detect_breaking_changes(
            V1_SCHEMA, v2_typed)
        # Breaking：closed enum 变更
        old_enum = make_object_schema(
            {"schema_version": _SV,
             "kind": {"type": "string", "enum": ["a", "b"]}},
            ("schema_version",))
        new_enum = copy.deepcopy(old_enum)
        new_enum["properties"]["kind"]["enum"] = ["a", "c"]
        assert "closed_enum_changed:kind" in detect_breaking_changes(
            old_enum, new_enum)

    def test_breaking_without_version_bump_blocked(self):
        old = _entry("DemoV", 1, V2_SCHEMA, V2_GOLDEN)
        new = _entry("DemoV", 1, V1_SCHEMA, V1_GOLDEN)
        with pytest.raises(ApiError) as exc_info:
            assert_versioning_policy(old, new)
        assert "breaking_without_bump" in str(exc_info.value.details)


# ---------------------------------------------------------------------------
# TEST-BACKEND-026：RULE-BACKEND-039 失配矩阵与强制刷新收敛
# ---------------------------------------------------------------------------

class TestMismatchMatrix:
    def test_payload_version_higher_than_latest(self):
        assembly = make_assembly()
        client = make_client(assembly)
        response = client.post("/api/v1/session",
                               json={"schema_version": 2}, headers=ORIGIN)
        body = response.json()
        assert body["error"]["code"] == "BACKEND_PROTOCOL_MISMATCH"
        assert body["error"]["details"]["expected"] == 1
        assert body["error"]["details"]["received"] == 2

    def test_ws_protocol_mismatch_closes(self):
        from backend_helpers import (
            FakeTransport,
            create_session,
            promote,
        )
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        ticket = assembly.services.tickets.issue(info["session_id"],
                                                 world.world_id)
        transport = FakeTransport()
        channel = assembly.gateway.connect(transport, info["session_id"],
                                           world.world_id)
        assembly.gateway.handle_hello(channel, {
            "client_protocol_version": 99, "ticket": ticket.ticket,
            "last_acked_revision": 0})
        error = transport.by_type("error")[-1]
        assert error["payload"]["code"] == "BACKEND_PROTOCOL_MISMATCH"
        assert channel.state == "closed"

    def test_lower_version_upcast_then_served(self):
        """低版本 active：按声明版本校验 → upcast 到当前版本进用例"""
        from src.api.pipeline import Pipeline
        from backend_helpers import FakeClock, make_id_factory
        from src.security.rate_limit import RateLimiter
        from src.security.sessions import SessionService
        registry = SchemaRegistry()
        registry.register(_entry("SessionRequestV", 1, V1_SCHEMA, V1_GOLDEN))
        registry.register(_entry("SessionRequestV", 2, V2_SCHEMA, V2_GOLDEN))
        registry.register_upcaster("SessionRequestV", 1, lambda obj: {
            **obj, "schema_version": 2, "label": "upcasted"})
        clock = FakeClock()
        pipeline = Pipeline(8765, SessionService(make_id_factory(), clock),
                            RateLimiter(clock), registry)
        from src.api.catalog import find_route
        from src.api.pipeline import RestRequest
        route = find_route("POST", "/api/v1/session")
        import dataclasses
        route = dataclasses.replace(route, request_schema="SessionRequestV")
        body = pipeline.validate_payload(
            route, {"schema_version": 1, "name": "legacy"})
        assert body["schema_version"] == 2
        assert body["label"] == "upcasted"


# ---------------------------------------------------------------------------
# TEST-BACKEND-027：RULE-BACKEND-040..041 Upcaster 链无损性与 Registry 完整性
# ---------------------------------------------------------------------------

class TestUpcastChain:
    def _registry_with_chain(self):
        registry = SchemaRegistry()
        registry.register(_entry("ChainV", 1, V1_SCHEMA, V1_GOLDEN))
        registry.register(_entry("ChainV", 2, V2_SCHEMA, V2_GOLDEN))
        v3_schema = make_object_schema(
            {"schema_version": _SV, "name": {"type": "string"},
             "label": {"type": "string"}, "priority": {"type": "integer"}},
            ("schema_version", "name", "priority"))
        registry.register(_entry("ChainV", 3, v3_schema,
                                 {"schema_version": 3, "name": "x",
                                  "label": "y", "priority": 1}))
        registry.register_upcaster("ChainV", 1, lambda obj: {
            **obj, "schema_version": 2, "label": "from-v1"})
        registry.register_upcaster("ChainV", 2, lambda obj: {
            **obj, "schema_version": 3, "priority": 0})
        return registry

    def test_chain_upcast_lossless(self):
        registry = self._registry_with_chain()
        upgraded = registry.upcast_chain("ChainV", 1,
                                         {"schema_version": 1, "name": "x"})
        assert upgraded == {"schema_version": 3, "name": "x",
                            "label": "from-v1", "priority": 0}

    def test_chain_broken_link_is_internal_invariant(self):
        registry = SchemaRegistry()
        registry.register(_entry("ChainV", 1, V1_SCHEMA, V1_GOLDEN))
        registry.register(_entry("ChainV", 2, V2_SCHEMA, V2_GOLDEN))
        with pytest.raises(ApiError) as exc_info:
            registry.upcast_chain("ChainV", 1,
                                  {"schema_version": 1, "name": "x"})
        assert "upcast_chain_broken" in str(exc_info.value.details)

    def test_persisted_newer_version_refused(self):
        registry = self._registry_with_chain()
        with pytest.raises(ApiError) as exc_info:
            registry.upcast_chain("ChainV", 9, {"schema_version": 9})
        assert exc_info.value.code == "BACKEND_PROTOCOL_MISMATCH"

    def test_chain_length_capped(self):
        registry = SchemaRegistry()
        schemas = {}
        goldens = {}
        for version in range(1, UPCAST_CHAIN_MAX + 3):
            schema = make_object_schema(
                {"schema_version": _SV, "v": {"type": "integer"}},
                ("schema_version",))
            golden = {"schema_version": version, "v": version}
            registry.register(_entry("LongV", version, schema, golden))
            schemas[version], goldens[version] = schema, golden
        for version in range(1, UPCAST_CHAIN_MAX + 2):
            registry.register_upcaster("LongV", version, lambda obj, v=version: {
                "schema_version": v + 1, "v": v + 1})
        with pytest.raises(ApiError) as exc_info:
            registry.upcast_chain("LongV", 1,
                                  {"schema_version": 1, "v": 1})
        assert "upcast_chain_too_long" in str(exc_info.value.details)

    def test_wire_registry_integrity_clean(self):
        """全量装配的 wire Registry：frozen 未改、golden 自验、无 upcast 缺口"""
        assembly = make_assembly()
        assert assembly.schemas.audit_integrity() == []

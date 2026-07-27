"""TEST-BACKEND-017..020：命令 Envelope、Registry 分发、Revision 矩阵、回执恰好一次"""
from __future__ import annotations

import pytest

from backend_helpers import (
    command_envelope,
    create_session,
    make_assembly,
    make_client,
    make_id_factory,
    make_utc_factory,
    promote,
    ws_connect,
)
from src.api.schemas import SchemaRegistry
from src.api.wire import register_command_specs, register_event_specs
from src.foundation.errors import ApiError
from src.orchestrator.commands import (
    AUTHORITATIVE_FIELDS,
    CommandRegistry,
    check_strict_revision,
    validate_envelope,
)
from src.orchestrator.events import EventRegistry
from src.orchestrator.idempotency import IdempotencyStore
from src.orchestrator.uow import WorldStore, WorldWriter

ULID_A = "01K1AB2CD3EF4GH5JK6MNP7QS0"
ULID_B = "01K1AB2CD3EF4GH5JK6MNP7QS1"


def _commands() -> CommandRegistry:
    schemas = SchemaRegistry()
    registry = CommandRegistry()
    register_command_specs(schemas, registry)
    return registry


def _writer(domain_apply=None):
    schemas = SchemaRegistry()
    commands = CommandRegistry()
    events = EventRegistry()
    register_command_specs(schemas, commands)
    register_event_specs(schemas, events)
    store = WorldStore()
    store.open_world("w1")
    idem = IdempotencyStore(make_utc_factory())
    apply = domain_apply or (lambda _w, _t, _p, _ctx: {
        "state": {}, "events": [], "reservations": []})
    return (WorldWriter(store, idem, commands, events,
                        make_id_factory("tx"), make_utc_factory(), apply),
            store, idem)


# ---------------------------------------------------------------------------
# TEST-BACKEND-017：RULE-BACKEND-025..026 Envelope 严格性与幂等键行为
# ---------------------------------------------------------------------------

class TestEnvelopeStrictness:
    def test_valid_envelope_accepted(self):
        validate_envelope(_commands(), command_envelope(ULID_A, "w1"))

    @pytest.mark.parametrize("mutation", [
        pytest.param(lambda e: e.update({"extra": 1}), id="extra_field"),
        pytest.param(lambda e: e.pop("world_id"), id="missing_field"),
        pytest.param(lambda e: e.update({"protocol_version": 2}),
                     id="protocol_mismatch"),
        pytest.param(lambda e: e.update({"command_id": "not-a-ulid"}),
                     id="command_id_not_ulid"),
    ])
    def test_malformed_envelope_rejected(self, mutation):
        envelope = command_envelope(ULID_A, "w1")
        mutation(envelope)
        with pytest.raises(ApiError) as exc_info:
            validate_envelope(_commands(), envelope)
        assert exc_info.value.code in ("BACKEND_SCHEMA_INVALID",
                                       "BACKEND_PROTOCOL_MISMATCH")

    def test_unknown_command_type_rejected(self):
        with pytest.raises(ApiError) as exc_info:
            validate_envelope(_commands(), command_envelope(
                ULID_A, "w1", command_type="player.nonexistent.action"))
        assert exc_info.value.code == "BACKEND_SCHEMA_INVALID"

    def test_idempotency_key_replay_same_receipt(self):
        writer, _store, _idem = _writer()
        envelope = command_envelope(ULID_A, "w1")
        first = writer.execute(envelope)
        replay = writer.execute(dict(envelope))
        assert first["result"] == "committed"
        assert replay == first  # 恰好一份终局回执

    def test_idempotency_conflict_on_different_payload(self):
        writer, _store, _idem = _writer()
        writer.execute(command_envelope(ULID_A, "w1"))
        with pytest.raises(ApiError) as exc_info:
            writer.execute(command_envelope(
                ULID_A, "w1", payload={"schema_version": 1, "paused": False}))
        assert exc_info.value.code == "BACKEND_IDEMPOTENCY_CONFLICT"

    def test_protocol_rejection_not_recorded(self):
        """协议层拒绝（幂等冲突除外）不消耗幂等记录：可原 command_id 重试"""
        writer, _store, _idem = _writer()
        stale = command_envelope(ULID_A, "w1", command_type="mayor.tax.propose",
                                 expected_revision=5,
                                 payload={"schema_version": 1, "rate_bp": 100})
        rejected = writer.execute(stale)
        assert rejected["result"] == "rejected"
        assert rejected["error"]["code"] == "BACKEND_STALE_REVISION"
        # 修正 expected_revision 后同 command_id 可提交
        fixed = command_envelope(ULID_A, "w1", command_type="mayor.tax.propose",
                                 expected_revision=0,
                                 payload={"schema_version": 1, "rate_bp": 100})
        assert writer.execute(fixed)["result"] == "committed"


# ---------------------------------------------------------------------------
# TEST-BACKEND-018：RULE-BACKEND-027..028 Registry 分发与权威字段伪造拒绝
# ---------------------------------------------------------------------------

class TestRegistryDispatch:
    def test_payload_strict_schema_unknown_field_rejected(self):
        envelope = command_envelope(
            ULID_A, "w1",
            payload={"schema_version": 1, "paused": True, "stealth": 1})
        with pytest.raises(ApiError) as exc_info:
            validate_envelope(_commands(), envelope)
        assert exc_info.value.code == "BACKEND_SCHEMA_INVALID"

    @pytest.mark.parametrize("field", sorted(AUTHORITATIVE_FIELDS))
    def test_authoritative_field_forgery_rejected(self, field):
        """基线 closed schema 下，伪造权威字段在 schema 位点即拒绝"""
        payload = {"schema_version": 1, "paused": True, field: "forged"}
        envelope = command_envelope(ULID_A, "w1", payload=payload)
        with pytest.raises(ApiError) as exc_info:
            validate_envelope(_commands(), envelope)
        assert exc_info.value.code in ("BACKEND_SCHEMA_INVALID",
                                       "BACKEND_FORBIDDEN")

    def test_forgery_check_fires_for_open_owner_schema(self):
        """owner schema 若合法包含权威字段名，伪造检测位点仍拒绝（FORBIDDEN）"""
        from src.orchestrator.commands import CommandSpec
        registry = _commands()
        registry.register(CommandSpec(
            type="player.combat.attack",
            payload_schema={"type": "object", "properties": {
                "schema_version": {"type": "integer", "minimum": 1},
                "damage": {"type": "integer"}},
                "required": ["schema_version"],
                "additionalProperties": False},
            role="player", revision_mode="strict"))
        envelope = command_envelope(
            ULID_A, "w1", command_type="player.combat.attack",
            payload={"schema_version": 1, "damage": 9999})
        with pytest.raises(ApiError) as exc_info:
            validate_envelope(registry, envelope)
        assert exc_info.value.code == "BACKEND_FORBIDDEN"

    def test_registry_covers_baseline_commands(self):
        registry = _commands()
        for command_type in ("player.move.set_target", "player.dialogue.say",
                             "mayor.tax.propose", "admin.resource.grant",
                             "system.world.pause"):
            spec = registry.get(command_type)
            assert spec.payload_schema


# ---------------------------------------------------------------------------
# TEST-BACKEND-019：RULE-BACKEND-029 strict/relaxed Revision 矩阵
# ---------------------------------------------------------------------------

class TestRevisionMatrix:
    @pytest.mark.parametrize("mode,expected,current,ok", [
        ("strict", 3, 3, True),
        ("strict", 3, 4, False),     # 排队期间 Revision 前进 → stale
        ("strict", None, 3, False),  # strict 缺 expected 即失败
        ("relaxed", None, 3, True),  # relaxed 忽略 expected
        ("relaxed", 999, 3, True),
    ])
    def test_check_matrix(self, mode, expected, current, ok):
        spec = _commands().get("mayor.tax.propose" if mode == "strict"
                               else "system.world.pause")
        if ok:
            check_strict_revision(spec, expected, current)
        else:
            with pytest.raises(ApiError) as exc_info:
                check_strict_revision(spec, expected, current)
            assert exc_info.value.code == "BACKEND_STALE_REVISION"

    def test_strict_stale_produces_rejected_receipt_no_side_effect(self):
        writer, store, _idem = _writer()
        envelope = command_envelope(ULID_A, "w1",
                                    command_type="mayor.tax.propose",
                                    expected_revision=9,
                                    payload={"schema_version": 1,
                                             "rate_bp": 100})
        receipt = writer.execute(envelope)
        assert receipt["result"] == "rejected"
        assert receipt["error"]["code"] == "BACKEND_STALE_REVISION"
        assert store.current_revision("w1") == 0  # 无部分效果


# ---------------------------------------------------------------------------
# TEST-BACKEND-020：RULE-BACKEND-030 回执恰好一次与断线取回
# ---------------------------------------------------------------------------

class TestReceiptExactlyOnce:
    def test_receipt_sent_exactly_once_per_command(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "command",
            "payload": command_envelope(ULID_A, world.world_id)})
        receipts = transport.by_type("command_receipt")
        assert len(receipts) == 1
        assert receipts[0]["payload"]["command_id"] == ULID_A

    def test_lookup_receipt_after_disconnect(self):
        """断线后凭 command_id 从幂等存储取回终局回执（RULE-BACKEND-030）"""
        from src.orchestrator.idempotency import canonical_payload_hash
        writer, _store, _idem = _writer()
        envelope = command_envelope(ULID_A, "w1")
        receipt = writer.execute(envelope)
        payload_hash = canonical_payload_hash(envelope["payload"])
        # 模拟断线：不发送回执；重连后直接查询
        fetched = writer.lookup_receipt("w1", ULID_A, payload_hash)
        assert fetched == receipt
        # 未知 command_id → None（Client 需重发）
        assert writer.lookup_receipt("w1", ULID_B, payload_hash) is None

    def test_failed_receipt_also_materialized_and_replayable(self):
        def failing(_w, _t, _p, _ctx):
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"reason_code": "domain_rule"})

        writer, store, _idem = _writer(domain_apply=failing)
        envelope = command_envelope(ULID_A, "w1")
        receipt = writer.execute(envelope)
        assert receipt["result"] == "failed"
        assert receipt["error"]["code"] == "BACKEND_CONFLICT_STATE"
        # failed 回执同样经 UoW 物化：重放返回同一份，revision 前进一次
        assert store.current_revision("w1") == 1
        assert writer.execute(dict(envelope)) == receipt

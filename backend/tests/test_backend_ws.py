"""TEST-BACKEND-009..012：WS Ticket、心跳、catch-up/Snapshot、溢出与协议错误"""
from __future__ import annotations

import pytest

from backend_helpers import (
    FakeTransport,
    append_committed,
    create_session,
    make_assembly,
    make_client,
    make_event,
    make_id_factory,
    promote,
    ws_connect,
)
from src.api.ws import (
    HEARTBEAT_ACK_TIMEOUT_MS,
    HEARTBEAT_INTERVAL_MS,
    MAX_SNAPSHOT_CHUNK_BYTES,
)
from src.foundation.errors import ApiError
from src.orchestrator.outbox import CommittedEventLog, SessionOutbox
from src.security.tickets import TICKET_TTL_MS


def _world_and_channel(assembly, role="player"):
    client = make_client(assembly)
    info, _csrf = create_session(client)
    if role:
        promote(assembly, info["session_id"], role)
    world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                   "template.default")
    return client, info, world


# ---------------------------------------------------------------------------
# TEST-BACKEND-009：RULE-BACKEND-012..013 Ticket 单次性、TTL、supersede
# ---------------------------------------------------------------------------

class TestWsTickets:
    def test_ticket_single_use(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        ticket = assembly.services.tickets.issue(info["session_id"],
                                                 world.world_id)
        assembly.services.tickets.validate_and_consume(
            ticket.ticket, info["session_id"], world.world_id)
        with pytest.raises(ApiError) as exc_info:
            assembly.services.tickets.validate_and_consume(
                ticket.ticket, info["session_id"], world.world_id)
        assert exc_info.value.code == "BACKEND_TICKET_INVALID"

    def test_ticket_ttl_expiry(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        ticket = assembly.services.tickets.issue(info["session_id"],
                                                 world.world_id)
        assembly.test_clock.advance(TICKET_TTL_MS + 1)
        with pytest.raises(ApiError) as exc_info:
            assembly.services.tickets.validate_and_consume(
                ticket.ticket, info["session_id"], world.world_id)
        assert exc_info.value.code == "BACKEND_TICKET_INVALID"

    def test_ticket_cross_session_rejected(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        ticket = assembly.services.tickets.issue(info["session_id"],
                                                 world.world_id)
        with pytest.raises(ApiError) as exc_info:
            assembly.services.tickets.validate_and_consume(
                ticket.ticket, "other-session", world.world_id)
        assert exc_info.value.code == "BACKEND_TICKET_INVALID"

    def test_hello_rejects_bad_ticket_with_close(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        transport = FakeTransport()
        channel = assembly.gateway.connect(transport, info["session_id"],
                                           world.world_id)
        assembly.gateway.handle_hello(channel, {
            "client_protocol_version": 1, "ticket": "forged",
            "last_acked_revision": 0})
        errors = transport.by_type("error")
        assert errors and errors[0]["payload"]["code"] == "BACKEND_TICKET_INVALID"
        assert channel.state == "closed"

    def test_supersede_closes_old_and_hands_over_cursor(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        old_channel, old_transport = ws_connect(assembly, info["session_id"],
                                                world.world_id)
        assert old_channel.state == "live"
        # 旧游标推进后再接手：新连接应继承 outbox 游标
        old_channel.outbox.state.last_acked_revision = 7
        new_channel, new_transport = ws_connect(assembly, info["session_id"],
                                                world.world_id)
        superseded = old_transport.by_type("error")
        assert any(f["payload"]["code"] == "BACKEND_WS_SUPERSEDED"
                   for f in superseded)
        assert old_channel.state == "closed"
        assert new_channel.state == "live"
        assert new_channel.outbox.state.last_acked_revision == 7


# ---------------------------------------------------------------------------
# TEST-BACKEND-010：RULE-BACKEND-014..015 心跳超时与 ack 顺序
# ---------------------------------------------------------------------------

class TestHeartbeat:
    def test_heartbeat_sent_after_interval(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS)
        assembly.gateway.tick_heartbeat()
        heartbeats = transport.by_type("heartbeat")
        assert len(heartbeats) == 1
        heartbeat_id = heartbeats[0]["payload"]["heartbeat_id"]
        assert channel.last_heartbeat_id == heartbeat_id

    def test_ack_resets_miss_state(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS)
        assembly.gateway.tick_heartbeat()
        heartbeat_id = transport.by_type("heartbeat")[0]["payload"]["heartbeat_id"]
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "heartbeat_ack",
            "payload": {"heartbeat_id": heartbeat_id}})
        assert channel.heartbeat_misses == 0
        assert channel.last_heartbeat_id is None

    def test_late_or_forged_ack_ignored(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS)
        assembly.gateway.tick_heartbeat()
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "heartbeat_ack",
            "payload": {"heartbeat_id": "forged"}})
        assert channel.last_heartbeat_id is not None  # 未消费在途心跳

    def test_two_misses_close_channel(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        # 第一次在途心跳超时未 ack → miss 1
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS)
        assembly.gateway.tick_heartbeat()
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS
                                    + HEARTBEAT_ACK_TIMEOUT_MS + 1)
        assembly.gateway.tick_heartbeat()
        assert channel.heartbeat_misses == 1
        assert channel.state == "live"
        # 第二次 → miss 2 → 关闭
        assembly.test_clock.advance(HEARTBEAT_INTERVAL_MS
                                    + HEARTBEAT_ACK_TIMEOUT_MS + 1)
        assembly.gateway.tick_heartbeat()
        assert channel.state == "closed"
        errors = transport.by_type("error")
        assert errors[-1]["payload"]["code"] == "BACKEND_SESSION_INVALID"


# ---------------------------------------------------------------------------
# TEST-BACKEND-011：RULE-BACKEND-016 catch-up 区间完整性与 Snapshot fallback
# ---------------------------------------------------------------------------

class TestCatchUp:
    def test_catch_up_delivers_exact_range_in_order(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        log = assembly.event_logs.setdefault(world.world_id,
                                             CommittedEventLog())
        for revision in range(1, 6):
            log.append_commit([make_event(assembly, world.world_id, revision,
                                          event_id=f"evt-r{revision}")])
        _channel, transport = ws_connect(assembly, info["session_id"],
                                         world.world_id, last_acked_revision=2)
        hello_ack = transport.by_type("hello_ack")[0]
        assert hello_ack["payload"]["resume_mode"] == "catch_up"
        delivered = [f["payload"] for f in transport.by_type("event")]
        assert [e["revision"] for e in delivered] == [3, 4, 5]
        assert [e["event_id"] for e in delivered] == ["evt-r3", "evt-r4",
                                                      "evt-r5"]

    def test_catch_up_skips_coalescible_events(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        log = assembly.event_logs.setdefault(world.world_id,
                                             CommittedEventLog())
        log.append_commit([make_event(assembly, world.world_id, 1)])
        delta = make_event(assembly, world.world_id, 2,
                           event_type="render.position.delta",
                           payload={"schema_version": 1,
                                    "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
                                    "position": {"scene_id": "s", "x_wu": 1.0,
                                                 "y_wu": 2.0},
                                    "facing_degrees": 90})
        log.append_commit([delta])
        log.append_commit([make_event(assembly, world.world_id, 3)])
        _channel, transport = ws_connect(assembly, info["session_id"],
                                         world.world_id, last_acked_revision=0)
        delivered = [f["payload"] for f in transport.by_type("event")]
        assert [e["revision"] for e in delivered] == [1, 3]  # delta 不补发

    def test_pruned_range_falls_back_to_snapshot(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        log = assembly.event_logs.setdefault(world.world_id,
                                             CommittedEventLog(retention=2))
        for revision in range(1, 6):
            log.append_commit([make_event(assembly, world.world_id, revision)])
        _channel, transport = ws_connect(assembly, info["session_id"],
                                         world.world_id, last_acked_revision=1)
        begins = transport.by_type("snapshot_begin")
        chunks = transport.by_type("snapshot_chunk")
        ends = transport.by_type("snapshot_end")
        assert len(begins) == len(chunks) == len(ends) == 1
        import base64
        for chunk in chunks:
            assert len(base64.b64decode(chunk["payload"]["data_b64"])) \
                <= MAX_SNAPSHOT_CHUNK_BYTES

    def test_client_ahead_of_server_falls_back_to_snapshot(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        log = assembly.event_logs.setdefault(world.world_id,
                                             CommittedEventLog())
        log.append_commit([make_event(assembly, world.world_id, 1)])
        _channel, transport = ws_connect(assembly, info["session_id"],
                                         world.world_id, last_acked_revision=99)
        assert transport.by_type("snapshot_begin")


# ---------------------------------------------------------------------------
# TEST-BACKEND-012：RULE-BACKEND-017..018 溢出合并、Lagging resync、协议错误关闭
# ---------------------------------------------------------------------------

class TestOutboxOverflow:
    def test_coalescible_merges_keeping_latest(self):
        assembly = make_assembly()
        outbox = SessionOutbox("s1", "w1", assembly.events, capacity=8)

        def delta(revision, x):
            return make_event(assembly, "w1", revision,
                              event_type="render.position.delta",
                              payload={"schema_version": 1,
                                       "entity_id": "e1",
                                       "position": {"scene_id": "s",
                                                    "x_wu": float(x),
                                                    "y_wu": 0.0},
                                       "facing_degrees": 0},
                              event_id=f"evt-{revision}")

        for revision in range(1, 5):
            outbox.push(delta(revision, revision * 10))
        pending = outbox.pending_frames()
        assert len(pending) == 1  # 同 entity 合并为最新一条
        assert pending[0]["payload"]["position"]["x_wu"] == 40.0

    def test_overflow_marks_lagging_and_requires_resync(self):
        assembly = make_assembly()
        outbox = SessionOutbox("s1", "w1", assembly.events, capacity=3)
        for revision in range(1, 6):  # 不可丢事件超容量
            outbox.push(make_event(assembly, "w1", revision,
                                   event_id=f"evt-{revision}"))
        assert outbox.state.state == "lagging"
        assert outbox.resync_required is True
        # 超容量时缓冲整体作废（走快照重建），只保留溢出后新到的增量
        assert outbox.depth() == 1

    def test_publish_events_triggers_snapshot_on_lagging(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        channel.outbox.capacity = 2  # 缩小缓冲模拟慢消费
        events = [make_event(assembly, world.world_id, revision,
                             event_id=f"evt-{revision}")
                  for revision in range(1, 5)]
        assembly.gateway.publish_events(world.world_id, events)
        assert transport.by_type("snapshot_begin")
        assert channel.state == "live"  # 快照完成即回 live

    def test_protocol_errors_close_channel(self):
        assembly = make_assembly()
        _client, info, world = _world_and_channel(assembly)
        for bad_frame in (
                "not-a-dict",
                {"protocol_version": 99, "frame_type": "ack", "payload": {}},
                {"protocol_version": 1, "frame_type": "bogus", "payload": {}}):
            channel, transport = ws_connect(assembly, info["session_id"],
                                            world.world_id)
            assembly.gateway.handle_frame(channel, bad_frame)
            assert channel.state == "closed", bad_frame
            error = transport.by_type("error")[-1]
            assert error["payload"]["code"] == "BACKEND_PROTOCOL_MISMATCH"

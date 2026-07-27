"""TEST-BACKEND-021..024：事件 Envelope、render 边界、提交后发布、可见性过滤"""
from __future__ import annotations

import pytest

from backend_helpers import (
    append_committed,
    create_session,
    make_assembly,
    make_client,
    make_event,
    make_id_factory,
    promote,
    ws_connect,
)
from src.foundation.errors import ApiError
from src.orchestrator.events import (
    EVENT_ENVELOPE_FIELDS,
    FORBIDDEN_PAYLOAD_KEYS,
    FORBIDDEN_RENDER_KEYS,
    build_event,
    validate_event_envelope,
    visible_to_session,
)


# ---------------------------------------------------------------------------
# TEST-BACKEND-021：RULE-BACKEND-031..032 Envelope 完整性与因果链构造
# ---------------------------------------------------------------------------

class TestEventEnvelope:
    def test_envelope_has_exactly_ten_fields(self):
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1, causation_id="cmd-1",
                           correlation_id="cmd-1")
        assert set(event.keys()) == EVENT_ENVELOPE_FIELDS
        validate_event_envelope(assembly.events, event)

    def test_missing_field_rejected(self):
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1)
        event.pop("causation_id")
        with pytest.raises(ApiError) as exc_info:
            validate_event_envelope(assembly.events, event)
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_causation_chain_construction(self):
        """命令 → 事件 → 事件：causation 指向上一级，correlation 保持链首"""
        assembly = make_assembly()
        first = make_event(assembly, "w1", 1, causation_id="cmd-root",
                           correlation_id="cmd-root", event_id="evt-1")
        second = make_event(assembly, "w1", 2, causation_id=first["event_id"],
                            correlation_id="cmd-root", event_id="evt-2")
        assert first["causation_id"] == "cmd-root"
        assert second["causation_id"] == "evt-1"
        assert second["correlation_id"] == first["correlation_id"] == "cmd-root"

    def test_unregistered_type_rejected(self):
        assembly = make_assembly()
        with pytest.raises(ApiError):
            build_event(assembly.events, make_id_factory(), world_id="w1",
                        revision=1, event_type="bogus.event.type",
                        game_time=0, causation_id="c", correlation_id="c",
                        payload={"schema_version": 1})


# ---------------------------------------------------------------------------
# TEST-BACKEND-022：RULE-BACKEND-033..034 render 边界、全序与 coalescible 合并
# ---------------------------------------------------------------------------

class TestRenderBoundary:
    @pytest.mark.parametrize("key", sorted(FORBIDDEN_RENDER_KEYS))
    def test_render_authority_keys_rejected(self, key):
        assembly = make_assembly()
        with pytest.raises(ApiError) as exc_info:
            make_event(assembly, "w1", 1, render={key: 1, "animation": "x"})
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_render_legit_presentation_keys_accepted(self):
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1,
                           render={"animation": "wave", "sfx": "chime",
                                   "duration_ms": 800})
        assert event["render"]["animation"] == "wave"

    def test_coalescible_event_must_not_carry_render(self):
        assembly = make_assembly()
        with pytest.raises(ApiError) as exc_info:
            make_event(assembly, "w1", 1, event_type="render.position.delta",
                       payload={"schema_version": 1,
                                "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
                                "position": {"scene_id": "s", "x_wu": 1.0,
                                             "y_wu": 2.0},
                                "facing_degrees": 0},
                       render={"animation": "walk"})
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_pending_frames_total_order_by_revision(self):
        from src.orchestrator.outbox import SessionOutbox
        assembly = make_assembly()
        outbox = SessionOutbox("s1", "w1", assembly.events, capacity=16)
        for revision in (3, 1, 2):  # 乱序 push
            outbox.push(make_event(assembly, "w1", revision,
                                   event_id=f"evt-{revision}"))
        assert [e["revision"] for e in outbox.pending_frames()] == [1, 2, 3]


# ---------------------------------------------------------------------------
# TEST-BACKEND-023：RULE-BACKEND-035 提交后发布、event_id 稳定与去重
# ---------------------------------------------------------------------------

class TestPublishAfterCommit:
    def test_events_published_from_committed_log(self):
        """publish_events 只推已提交事件；Outbox 按 revision 全序"""
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        _channel, transport = ws_connect(assembly, info["session_id"],
                                         world.world_id)
        committed = [make_event(assembly, world.world_id, 1,
                                event_id="evt-commit-1")]
        append_committed(assembly, world.world_id, committed)
        assembly.gateway.publish_events(world.world_id, committed)
        delivered = transport.by_type("event")
        assert [f["payload"]["event_id"] for f in delivered] == \
            ["evt-commit-1"]

    def test_event_id_stable_and_dedup_by_client(self):
        """同一事件重发（catch-up 与 live 重合并）时 event_id 一致可去重"""
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1, event_id="evt-stable")
        again = make_event(assembly, "w1", 1, event_id="evt-stable")
        assert event["event_id"] == again["event_id"]
        # 幂等键即 event_id：Client 侧 set 去重语义
        seen = set()
        for candidate in (event, again):
            if candidate["event_id"] not in seen:
                seen.add(candidate["event_id"])
        assert len(seen) == 1

    def test_catch_up_does_not_repush_live_sent(self):
        """live 已发事件在重连 catch-up 中按 last_acked 精确续发，不重不漏"""
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        log = assembly.event_logs.setdefault(
            world.world_id,
            __import__("src.orchestrator.outbox", fromlist=["CommittedEventLog"])
            .CommittedEventLog())
        for revision in (1, 2, 3):
            log.append_commit([make_event(assembly, world.world_id, revision,
                                          event_id=f"evt-{revision}")])
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id, last_acked_revision=1)
        delivered = [f["payload"]["event_id"]
                     for f in transport.by_type("event")]
        assert delivered == ["evt-2", "evt-3"]


# ---------------------------------------------------------------------------
# TEST-BACKEND-024：RULE-BACKEND-036 可见性过滤与 Secret 泄漏注入
# ---------------------------------------------------------------------------

class TestVisibilityFilter:
    def test_broadcast_visible_to_all(self):
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1)
        assert visible_to_session(assembly.events, event, "anyone") is True

    def test_directed_only_visible_to_audience(self):
        assembly = make_assembly()
        event = make_event(assembly, "w1", 1,
                           event_type="dialogue.line.spoken",
                           payload={"schema_version": 1,
                                    "speaker_id": "res-1",
                                    "listener_ids": ["res-2"],
                                    "text": "晚上好"})
        assert visible_to_session(assembly.events, event, "sess-a",
                                  audience=frozenset({"sess-a"})) is True
        assert visible_to_session(assembly.events, event, "sess-b",
                                  audience=frozenset({"sess-a"})) is False
        assert visible_to_session(assembly.events, event, "sess-b",
                                  audience=None) is False

    @pytest.mark.parametrize("key", sorted(FORBIDDEN_PAYLOAD_KEYS))
    def test_secret_leak_in_payload_rejected(self, key):
        assembly = make_assembly()
        payload = {"schema_version": 1, "weather": "rain",
                   "started_at_tick": 1, key: "sk-leak000000"}
        with pytest.raises(ApiError) as exc_info:
            make_event(assembly, "w1", 1, payload=payload)
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_nested_secret_leak_rejected(self):
        assembly = make_assembly()
        payload = {"schema_version": 1, "weather": "rain",
                   "started_at_tick": 1,
                   "nested": {"deep": {"api_key": "sk-leak000000"}}}
        with pytest.raises(ApiError):
            make_event(assembly, "w1", 1, payload=payload)

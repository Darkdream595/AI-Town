"""TEST-BACKEND-001..004：进程模型、队列隔离、启动恢复、Graceful Drain"""
from __future__ import annotations

import pytest

from backend_helpers import (
    BASE_URL,
    FakeClock,
    csrf_headers,
    create_session,
    make_assembly,
    make_client,
    make_id_factory,
    promote,
    ws_connect,
)
from src.bootstrap.config import BackendConfig, resolve_port
from src.bootstrap.drain import DRAIN_STEPS, run_graceful_drain
from src.bootstrap.startup import StartupHooks, run_recovery_sequence
from src.foundation.errors import ApiError
from src.orchestrator.queues import (
    OVERFLOW_DROP_MERGEABLE,
    OVERFLOW_NEVER_DROP,
    OVERFLOW_REJECT_NEW,
    BoundedQueue,
    QueueOverflow,
    QueueSet,
    put_world_command,
)


# ---------------------------------------------------------------------------
# TEST-BACKEND-001：RULE-BACKEND-001..003 bind/worker/同源策略
# ---------------------------------------------------------------------------

class TestBindPolicy:
    def test_non_loopback_bind_refused(self):
        for host in ("0.0.0.0", "192.168.1.10", "example.com", ""):
            with pytest.raises(ApiError) as exc_info:
                BackendConfig(bind_host=host).validate()
            assert exc_info.value.code == "BACKEND_BIND_REFUSED"

    def test_port_range_enforced(self):
        for port in (0, 80, 1023, 65536, -1):
            with pytest.raises(ApiError) as exc_info:
                BackendConfig(bind_port=port).validate()
            assert exc_info.value.code == "BACKEND_BIND_REFUSED"

    def test_port_fallback_within_eight(self):
        busy = {8765, 8766}
        assert resolve_port(BackendConfig(),
                            lambda _h, p: p not in busy) == 8767

    def test_port_exhaustion_refused_not_silent(self):
        with pytest.raises(ApiError) as exc_info:
            resolve_port(BackendConfig(), lambda _h, _p: False)
        assert exc_info.value.code == "BACKEND_BIND_REFUSED"
        assert exc_info.value.details["reason_code"] == "port_exhausted"

    def test_same_origin_no_cors_headers(self):
        client = make_client(make_assembly())
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        for name in response.headers:
            assert not name.lower().startswith("access-control-")
        # preflight 从协议上消除：任何 OPTIONS 一律 403
        preflight = client.options("/api/v1/worlds", headers={
            "origin": BASE_URL,
            "access-control-request-method": "POST"})
        assert preflight.status_code == 403
        assert "access-control-allow-origin" not in preflight.headers

    def test_cross_origin_rejected(self):
        client = make_client(make_assembly())
        response = client.post("/api/v1/session", json={"schema_version": 1},
                               headers={"origin": "http://evil.example:8765"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "BACKEND_ORIGIN_REJECTED"


# ---------------------------------------------------------------------------
# TEST-BACKEND-002：RULE-BACKEND-004..006 队列隔离、容量与满溢回执
# ---------------------------------------------------------------------------

class TestQueueIsolation:
    def test_four_queue_kinds_isolated(self):
        clock = FakeClock()
        queues = QueueSet(clock, capacities={"ai_request": 2})
        for _ in range(2):
            queues.queues["ai_request"].put(object())
        assert queues.queues["ai_request"].depth() == 2
        # AI 队列积压不影响其他队列与世界命令队列
        assert queues.queues["long_action"].depth() == 0
        assert queues.queues["persistence"].depth() == 0
        assert queues.queues["ws_outbox"].depth() == 0
        world_queue = queues.world_command_queue("w1")
        world_queue.put({"cmd": 1})
        assert world_queue.depth() == 1

    def test_world_command_full_rejects_with_queue_full(self):
        clock = FakeClock()
        queue = BoundedQueue("world_command.w1", 2, OVERFLOW_REJECT_NEW, clock)
        put_world_command(queue, {"n": 1})
        put_world_command(queue, {"n": 2})
        with pytest.raises(ApiError) as exc_info:
            put_world_command(queue, {"n": 3})
        assert exc_info.value.code == "BACKEND_QUEUE_FULL"
        assert exc_info.value.spec.retryable is True
        assert exc_info.value.spec.http_status == 503

    def test_mergeable_drop_policy_never_drops_unmergeable(self):
        clock = FakeClock()
        queue = BoundedQueue("ai_request", 2, OVERFLOW_DROP_MERGEABLE, clock)
        queue.put("a", mergeable=True)
        queue.put("b", mergeable=False)
        queue.put("c")  # 丢弃队首可合并项 a，c 入队
        assert queue.peek_items() == ["b", "c"]
        assert queue.dropped_count == 1
        # 无可合并项时满溢抛错——不可丢项绝不静默丢弃
        with pytest.raises(QueueOverflow):
            queue.put("d")
        assert queue.peek_items() == ["b", "c"]

    def test_never_drop_policy_raises_instead_of_dropping(self):
        clock = FakeClock()
        queue = BoundedQueue("ws_outbox", 1, OVERFLOW_NEVER_DROP, clock)
        queue.put({"event": 1})
        with pytest.raises(QueueOverflow):
            queue.put({"event": 2})
        assert queue.dropped_count == 0

    def test_metrics_snapshot_covers_all_queues(self):
        clock = FakeClock()
        queues = QueueSet(clock)
        queues.world_command_queue("w1").put({"cmd": 1})
        snapshot = queues.metrics_snapshot()
        assert set(QueueSet.QUEUE_NAMES) <= set(snapshot)
        assert "world_command.w1" in snapshot
        assert snapshot["world_command.w1"]["depth"] == 1


# ---------------------------------------------------------------------------
# TEST-BACKEND-003：启动恢复顺序与 Recovery Barrier
# ---------------------------------------------------------------------------

class TestStartupRecovery:
    def test_recovery_step_order_and_barrier_lift(self):
        order = []
        hooks = StartupHooks(
            open_persistence=lambda _a: order.append("open_persistence"),
            replay_event_log=lambda _a: (order.append("replay"), 42)[1],
            recovery_audit=lambda _a: order.append("audit"),
            rebuild_projection=lambda _a: order.append("projection"),
            start_workers=lambda _a: order.append("workers"),
        )
        assembly = make_assembly(hooks=hooks, run_recovery=False)
        assert assembly.runtime.state == "booting"
        assert assembly.runtime.recovery_barrier_active is True
        assert run_recovery_sequence(assembly, hooks) is True
        assert order == ["open_persistence", "replay", "audit",
                         "projection", "workers"]
        assert assembly.runtime.state == "ready"
        assert assembly.runtime.recovery_barrier_active is False
        assert assembly.runtime.current_revision == 42

    def test_recovery_failure_holds_barrier(self):
        def boom(_assembly):
            raise RuntimeError("disk gone")

        hooks = StartupHooks(recovery_audit=boom)
        assembly = make_assembly(hooks=hooks, run_recovery=False)
        assert run_recovery_sequence(assembly, hooks) is False
        assert assembly.runtime.recovery_barrier_active is True
        assert assembly.runtime.recovery_error == "recovery_audit_failed"
        assert len(assembly.recovery_failures) == 1

    def test_barrier_blocks_world_writes_but_health_served(self):
        def boom(_assembly):
            raise RuntimeError("db corrupt")

        assembly = make_assembly(
            hooks=StartupHooks(open_persistence=boom), run_recovery=False)
        run_recovery_sequence(assembly,
                              StartupHooks(open_persistence=boom))
        client = make_client(assembly)
        # 健康端点 Barrier 期间仍可用
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["data"]["recovery_barrier_active"] is True
        # 写端点一律 CONFLICT_STATE
        info, csrf = create_session(client)
        promote(assembly, info["session_id"])
        response = client.post("/api/v1/worlds", json={
            "schema_version": 1, "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
            "name": "x", "seed_hex": "0123456789abcdef"},
            headers=csrf_headers(csrf))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BACKEND_CONFLICT_STATE"

    def test_worker_start_failure_holds_barrier(self):
        def boom(_assembly):
            raise RuntimeError("scheduler dead")

        hooks = StartupHooks(start_workers=boom)
        assembly = make_assembly(hooks=hooks, run_recovery=False)
        assert run_recovery_sequence(assembly, hooks) is False
        assert assembly.runtime.recovery_barrier_active is True


# ---------------------------------------------------------------------------
# TEST-BACKEND-004：Graceful Drain 原子性与 BACKEND_SHUTDOWN 回执
# ---------------------------------------------------------------------------

class TestGracefulDrain:
    def test_drain_steps_in_order(self):
        assembly = make_assembly()
        calls = []
        report = run_graceful_drain(
            assembly.runtime, assembly.gateway, assembly.test_clock,
            complete_queued=lambda _t: calls.append("complete"),
            cancel_ai_in_flight=lambda: calls.append("cancel_ai"),
            checkpoint_close=lambda: calls.append("checkpoint"))
        assert report.clean
        assert report.steps_completed == list(DRAIN_STEPS)
        assert calls == ["complete", "cancel_ai", "checkpoint"]
        assert assembly.runtime.state == "stopped"

    def test_draining_rejects_new_ws_command_with_shutdown_receipt(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assert channel.state == "live"
        assembly.runtime.begin_drain()
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "command",
            "payload": {
                "schema_version": 1,
                "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS1",
                "world_id": world.world_id,
                "type": "system.world.pause",
                "expected_revision": None,
                "payload": {"schema_version": 1, "paused": True},
                "client": {"issued_at_ms": 0}}})
        receipts = transport.by_type("command_receipt")
        assert len(receipts) == 1
        receipt = receipts[0]["payload"]
        assert receipt["result"] == "rejected"
        assert receipt["error"]["code"] == "BACKEND_SHUTDOWN"

    def test_draining_rejects_rest_world_write(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, csrf = create_session(client)
        promote(assembly, info["session_id"])
        assembly.runtime.begin_drain()
        response = client.post("/api/v1/worlds", json={
            "schema_version": 1, "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS2",
            "name": "x", "seed_hex": "0123456789abcdef"},
            headers=csrf_headers(csrf))
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BACKEND_SHUTDOWN"

    def test_drain_close_all_channels_with_shutdown(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        report = run_graceful_drain(assembly.runtime, assembly.gateway,
                                    assembly.test_clock)
        assert report.clean
        errors = transport.by_type("error")
        assert any(f["payload"]["code"] == "BACKEND_SHUTDOWN" for f in errors)
        assert channel.state == "closed"

    def test_drain_is_idempotent_no_double_side_effect(self):
        assembly = make_assembly()
        calls = []
        run_graceful_drain(assembly.runtime, assembly.gateway,
                           assembly.test_clock,
                           checkpoint_close=lambda: calls.append("cp"))
        run_graceful_drain(assembly.runtime, assembly.gateway,
                           assembly.test_clock,
                           checkpoint_close=lambda: calls.append("cp"))
        # 第二次 drain 可安全重入（各步骤幂等执行）
        assert calls == ["cp", "cp"]

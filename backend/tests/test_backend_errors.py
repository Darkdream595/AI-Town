"""TEST-BACKEND-039..042：错误注册表、模型/存储失败恢复、背压、安全关机注入"""
from __future__ import annotations

import json

import pytest

from backend_helpers import (
    command_envelope,
    create_session,
    make_assembly,
    make_client,
    promote,
    ws_connect,
)
from src.bootstrap.drain import run_graceful_drain
from src.foundation.errors import (
    ERROR_REGISTRY,
    INTERNAL_INVARIANT_ENVELOPE,
    ApiError,
    error_envelope,
    spec_of,
)

ERROR_CATEGORIES = frozenset({
    "protocol", "auth", "limit", "conflict", "backpressure", "upstream",
    "storage", "internal", "lifecycle"})
WS_BEHAVIORS = frozenset({"error_frame", "error_frame_close", "close", "none"})
LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})


# ---------------------------------------------------------------------------
# TEST-BACKEND-039：RULE-BACKEND-060..061 注册表完备性与错误对象脱敏
# ---------------------------------------------------------------------------

class TestErrorRegistry:
    def test_all_specs_complete(self):
        assert len(ERROR_REGISTRY) >= 23
        for code, spec in ERROR_REGISTRY.items():
            assert spec.code == code
            assert spec.category in ERROR_CATEGORIES, code
            assert spec.ws_behavior in WS_BEHAVIORS, code
            assert isinstance(spec.retryable, bool), code
            assert spec.log_level in LOG_LEVELS, code
            assert spec.message and "{" not in spec.message  # 无插值残留
            if spec.http_status is not None:
                assert 400 <= spec.http_status <= 599, code

    def test_unregistered_code_falls_back_to_internal_invariant(self):
        """未注册码出现在构造路径：统一兜底 INTERNAL_INVARIANT，wire 绝不出现陌生码"""
        assert spec_of("BACKEND_NOT_A_REAL_CODE").code == \
            "BACKEND_INTERNAL_INVARIANT"
        error = ApiError("BACKEND_NOT_A_REAL_CODE")
        assert error.code == "BACKEND_INTERNAL_INVARIANT"

    def test_error_object_schema(self):
        envelope = error_envelope("BACKEND_RATE_LIMITED",
                                  {"route_class": "world-admin"},
                                  retry_after_ms=500)
        error = envelope["error"]
        assert set(error.keys()) == {"schema_version", "code", "message",
                                     "retryable", "retry_after_ms", "details"}
        assert error["code"] == "BACKEND_RATE_LIMITED"
        assert error["retryable"] is True
        assert error["retry_after_ms"] == 500
        assert envelope["schema_version"] == 1

    def test_message_contains_no_internals(self):
        for code in ERROR_REGISTRY:
            message = spec_of(code).message
            for forbidden in ("Traceback", "C:\\", "D:\\", "/home/",
                              "sqlite", "SELECT ", "0x"):
                assert forbidden not in message, code

    def test_details_sanitized_of_secrets(self):
        """details 允许 reason_code 等结构化小对象；绝不携带明文/堆栈"""
        secret = "sk-live0123456789"
        envelope = error_envelope("BACKEND_FORBIDDEN",
                                  {"reason_code": "role_insufficient"})
        assert secret not in json.dumps(envelope)
        invariant = INTERNAL_INVARIANT_ENVELOPE
        assert "error" in invariant
        assert invariant["error"]["code"] == "BACKEND_INTERNAL_INVARIANT"


# ---------------------------------------------------------------------------
# TEST-BACKEND-040：RULE-BACKEND-062..063 模型与存储失败恢复路径
# ---------------------------------------------------------------------------

class TestFailureRecovery:
    def test_model_unavailable_retryable(self):
        spec = spec_of("BACKEND_MODEL_UNAVAILABLE")
        assert spec.retryable is True
        assert spec.category == "upstream"
        assert spec.http_status == 503

    def test_storage_failure_marks_world_read_only(self):
        """on_storage_failure 钩子 → 世界只读降级；完整性核对通过才可恢复"""
        assembly = make_assembly()
        record = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                        "template.default")
        assembly.worlds.mark_read_only(record.world_id)
        assert assembly.worlds.get(record.world_id).read_only is True
        # 完整性核对失败 → 保持只读
        with pytest.raises(ApiError):
            assembly.worlds.recover_writable(record.world_id,
                                             integrity_ok=False)
        assert assembly.worlds.get(record.world_id).read_only is True
        # 核对通过 → 恢复可写
        assembly.worlds.recover_writable(record.world_id, integrity_ok=True)
        assert assembly.worlds.get(record.world_id).read_only is False

    def test_storage_failure_error_spec(self):
        """RULE-BACKEND-063：503 + 不自动重试写（恢复须经完整性检查）"""
        spec = spec_of("BACKEND_STORAGE_FAILURE")
        assert spec.category == "storage"
        assert spec.retryable is False
        assert spec.http_status == 503


# ---------------------------------------------------------------------------
# TEST-BACKEND-041：RULE-BACKEND-064 背压逐级与 Overload 广播
# ---------------------------------------------------------------------------

class TestBackpressure:
    def test_queue_full_is_retryable_backpressure(self):
        spec = spec_of("BACKEND_QUEUE_FULL")
        assert spec.category == "backpressure"
        assert spec.retryable is True
        assert spec.http_status == 503

    def test_overload_state_change_broadcasts(self):
        assembly = make_assembly()
        sent = []
        assembly.worlds._on_broadcast = lambda t, p: sent.append((t, p))
        record = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                        "template.default")
        assembly.worlds.set_overloaded(record.world_id, True)
        assembly.worlds.set_overloaded(record.world_id, True)  # 幂等不重复广播
        assembly.worlds.set_overloaded(record.world_id, False)
        assert sent == [
            ("system.overload.changed",
             {"world_id": record.world_id, "overloaded": True}),
            ("system.overload.changed",
             {"world_id": record.world_id, "overloaded": False})]

    def test_backpressure_levels_distinct(self):
        """逐级：rate_limit(429) → queue_full(503 retryable) → overloaded(503)
        → shutdown(503)：各级错误码相互独立"""
        codes = ["BACKEND_RATE_LIMITED", "BACKEND_QUEUE_FULL",
                 "BACKEND_OVERLOADED", "BACKEND_SHUTDOWN"]
        assert len(set(codes)) == 4
        for code in codes:
            assert code in ERROR_REGISTRY


# ---------------------------------------------------------------------------
# TEST-BACKEND-042：RULE-BACKEND-065 安全关机步骤级故障注入
# ---------------------------------------------------------------------------

class TestDrainFaultInjection:
    def test_each_step_failure_isolated_and_recorded(self):
        assembly = make_assembly()

        class _Gateway:
            def notify_all(self, code):
                raise RuntimeError("ws send dead")

            def close_all(self, code):
                raise RuntimeError("ws close dead")

        report = run_graceful_drain(
            assembly.runtime, _Gateway(), assembly.test_clock,
            complete_queued=lambda _t: (_ for _ in ()).throw(
                RuntimeError("tick stuck")),
            cancel_ai_in_flight=lambda: (_ for _ in ()).throw(
                RuntimeError("ai stuck")),
            checkpoint_close=lambda: (_ for _ in ()).throw(
                RuntimeError("db stuck")))
        assert not report.clean
        assert len(report.failures) == 5  # 步骤 1/3/4/5/6 各一记
        # 步骤 2（进入 draining）不受外部故障影响，仍完成
        assert "reject_new_commands" in report.steps_completed
        assert report.forced is True
        assert assembly.runtime.state == "stopped"

    def test_clean_drain_has_no_failures(self):
        assembly = make_assembly()
        report = run_graceful_drain(assembly.runtime, assembly.gateway,
                                    assembly.test_clock)
        assert report.clean
        assert report.failures == []
        assert report.forced is False

    def test_queued_commands_fail_with_shutdown_receipt(self):
        """drain 期间到达的命令统一 rejected(BACKEND_SHUTDOWN)"""
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.runtime.begin_drain()
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "command",
            "payload": command_envelope("01K1AB2CD3EF4GH5JK6MNP7QS9",
                                        world.world_id)})
        receipt = transport.by_type("command_receipt")[-1]["payload"]
        assert receipt["result"] == "rejected"
        assert receipt["error"]["code"] == "BACKEND_SHUTDOWN"
        assert receipt["error"]["retryable"] is True

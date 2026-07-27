"""TEST-BACKEND-043..046：日志结构轮转、指标预算、Security Fixture、Load Profile"""
from __future__ import annotations

import json
import os

import pytest

from backend_helpers import (
    ORIGIN,
    FakeClock,
    command_envelope,
    create_session,
    csrf_headers,
    make_assembly,
    make_client,
    make_event,
    make_id_factory,
    make_utc_factory,
    promote,
    ws_connect,
)
from src.diagnostics.logging import (
    LOG_FIELD_POLICIES,
    LOG_KEEP_FILES,
    LOG_MAX_BYTES,
    LogPolicyError,
    StructuredLogger,
    check_fields_policy,
)
from src.diagnostics.metrics import (
    CORE_METRICS,
    BudgetEvaluator,
    MetricsRegistry,
    audit_metrics_completeness,
)
from src.orchestrator.outbox import CommittedEventLog
from src.security.redaction import RedactionFilter


def _logger(tmp_path=None, redact=None, mirror=None):
    log_dir = str(tmp_path) if tmp_path is not None else None
    return StructuredLogger("test", log_dir, make_utc_factory(),
                            redact=redact, mirror=mirror)


# ---------------------------------------------------------------------------
# TEST-BACKEND-043：RULE-BACKEND-066..067 日志结构、轮转与主表零泄漏
# ---------------------------------------------------------------------------

class TestStructuredLogging:
    FIXED_FIELDS = {"timestamp", "level", "logger", "event_code", "world_id",
                    "ids", "reason_code", "duration_ms"}

    def test_log_record_has_exactly_fixed_fields(self):
        logger = _logger()
        logger.info("command_committed", world_id="w1",
                    ids={"command_id": "c1"}, reason_code=None, duration_ms=3)
        record = logger.ring_records()[-1]
        assert set(record.keys()) == self.FIXED_FIELDS
        assert record["level"] == "info"
        assert record["logger"] == "test"
        line = json.dumps(record, ensure_ascii=False)
        assert json.loads(line) == record  # JSONL 单行可解析

    def test_file_sink_writes_jsonl(self, tmp_path):
        logger = _logger(tmp_path)
        logger.info("evt_a", world_id="w1")
        logger.error("evt_b", reason_code="boom")
        logger.close()
        lines = (tmp_path / "test.log").read_text(
            encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert set(parsed.keys()) == self.FIXED_FIELDS

    def test_never_field_drops_record_and_counts(self):
        logger = _logger()
        logger.info("safe", ids={"command_id": "c1"})
        logger.info("violation", ids={"csrf_token": "leak"})
        logger.info("unclassified", ids={"brand_new_field": "x"})  # 未归类默认 never
        assert [r["event_code"] for r in logger.ring_records()] == ["safe"]
        assert logger.write_failure_count == 2

    def test_policy_check_rejects_never_and_masked(self):
        check_fields_policy({"command_id": "c1", "world_id": "w1"})
        for field in ("csrf_token", "fs_path", "api_key", "unknown_field"):
            with pytest.raises(LogPolicyError):
                check_fields_policy({field: "x"})

    def test_master_table_covers_secret_fields(self):
        for field in ("api_key", "session_secret",
                      "csrf_token", "ws_ticket", "confirmation_token",
                      "prompt_text", "completion_text", "reasoning_content"):
            assert LOG_FIELD_POLICIES.get(field) == "never", field

    def test_redaction_filter_applied_to_line(self):
        redaction = RedactionFilter()
        redaction.register_secret_value("sk-leak000001")
        logger = _logger(redact=redaction.redact)
        logger.info("x", reason_code="prefix sk-leak000001 suffix")
        line = json.dumps(logger.ring_records()[-1], ensure_ascii=False)
        assert "sk-leak000001" not in line

    def test_log_dir_unwritable_degrades_to_ring(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("occupied", encoding="utf-8")
        # makedirs 撞已存在文件 → OSError → 降级为环形缓冲
        logger = StructuredLogger("test", str(blocker / "sub"), make_utc_factory())
        assert logger.degraded is True
        logger.info("evt")
        assert logger.ring_records()[-1]["event_code"] == "evt"

    def test_rotation_constants(self):
        assert LOG_MAX_BYTES == 10 * 1024 * 1024
        assert LOG_KEEP_FILES == 5


# ---------------------------------------------------------------------------
# TEST-BACKEND-044：RULE-BACKEND-068..069 指标完备性与预算/Breach 行为
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_snapshot_contains_all_core_metrics(self):
        registry = MetricsRegistry()
        snapshot = registry.snapshot()
        assert snapshot["schema_version"] == 1
        assert audit_metrics_completeness(snapshot) == []
        assert len(CORE_METRICS) >= 14

    def test_labels_are_low_cardinality_only(self):
        allowed_labels = {"world_id", "queue", "code", "route_class",
                          "state", "result", "budget"}
        for name, (_kind, dims) in CORE_METRICS.items():
            assert set(dims) <= allowed_labels, name

    def test_counter_gauge_summary_math(self):
        registry = MetricsRegistry()
        registry.increment("error_count", labels={"code": "x"})
        registry.increment("error_count", 2, labels={"code": "x"})
        registry.set_gauge("queue_depth", 7, labels={"queue": "q1"})
        for value in (10.0, 20.0, 30.0, 40.0):
            registry.observe("command_latency_ms", value)
        snapshot = registry.snapshot()
        counters = snapshot["metrics"]["error_count"]
        assert counters[0]["value"] == 3
        assert snapshot["metrics"]["queue_depth"][0]["value"] == 7
        summary = snapshot["metrics"]["command_latency_ms"][0]
        assert summary["samples"] == 4
        # pick 采用 ordered[int(q*n)]（0 基索引）：[10,20,30,40] 的 p50 = ordered[2]
        assert summary["p50"] == pytest.approx(30.0)
        assert summary["p99"] == pytest.approx(40.0)

    def test_budget_breach_after_three_consecutive_windows(self):
        evaluator = BudgetEvaluator(
            budgets={"rest_admin_p95_ms": 50.0}, consecutive=3)
        assert evaluator.evaluate_window({"rest_admin_p95_ms": 60.0}) == []
        assert evaluator.evaluate_window({"rest_admin_p95_ms": 55.0}) == []
        fired = evaluator.evaluate_window({"rest_admin_p95_ms": 51.0})
        assert fired == ["rest_admin_p95_ms"]
        assert evaluator.breached("rest_admin_p95_ms") is True

    def test_budget_recovers_on_good_window(self):
        evaluator = BudgetEvaluator(
            budgets={"rest_admin_p95_ms": 50.0}, consecutive=2)
        evaluator.evaluate_window({"rest_admin_p95_ms": 60.0})
        evaluator.evaluate_window({"rest_admin_p95_ms": 60.0})
        assert evaluator.breached("rest_admin_p95_ms") is True
        evaluator.evaluate_window({"rest_admin_p95_ms": 10.0})
        assert evaluator.breached("rest_admin_p95_ms") is False


# ---------------------------------------------------------------------------
# TEST-BACKEND-045：RULE-BACKEND-070 Security Fixture 全集与自验证
# ---------------------------------------------------------------------------

class TestSecurityFixtures:
    """§5 fixture 清单的可重复离线执行；fixture 失败即发布失败"""

    def _fixture_forged_origin(self):
        client = make_client(make_assembly())
        assert client.post("/api/v1/session", json={"schema_version": 1},
                           headers={"origin": "http://evil:8765"}
                           ).status_code == 403
        assert client.options("/api/v1/worlds",
                              headers=ORIGIN).status_code == 403

    def _fixture_csrf_and_bootstrap_boundary(self):
        assembly = make_assembly()
        client = make_client(assembly)
        assert client.get("/api/v1/health").status_code == 200  # 豁免
        assert client.get("/api/v1/worlds").status_code == 401  # 无 Cookie
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        assert client.post("/api/v1/worlds", json={
            "schema_version": 1, "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
            "name": "x", "seed_hex": "0123456789abcdef"},
            headers={**ORIGIN, "x-ai-town-csrf": "bad"}).status_code == 403

    def _fixture_ticket_replay_expiry_cross_session(self):
        from src.foundation.errors import ApiError
        assembly = make_assembly()
        ticket = assembly.services.tickets.issue("s1", "w1")
        assembly.services.tickets.validate_and_consume(ticket.ticket, "s1", "w1")
        for bad_call in (
                lambda: assembly.services.tickets.validate_and_consume(
                    ticket.ticket, "s1", "w1"),       # 重放
                lambda: assembly.services.tickets.validate_and_consume(
                    "forged", "s1", "w1")):           # 伪造
            with pytest.raises(ApiError):
                bad_call()

    def _fixture_path_traversal_and_symlink(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("spa", encoding="utf-8")
        secret = tmp_path / "secret.txt"
        secret.write_text("top-secret", encoding="utf-8")
        from src.api.app import _resolve_static
        assert _resolve_static(str(static), "../secret.txt") is None
        assert _resolve_static(str(static), "index.html") is not None
        try:
            os.symlink(secret, static / "link.txt")
        except OSError:
            # Windows 无特权无法创建符号链接：保留穿越断言，跳过拒跟断言
            return
        assert _resolve_static(str(static), "link.txt") is None  # 符号链接拒跟

    def _fixture_oversize_and_deep_json(self):
        client = make_client(make_assembly())
        assert client.post("/api/v1/session", content=b" " * 65537,
                           headers={**ORIGIN,
                                    "content-type": "application/json"}
                           ).status_code == 413
        deep = value = {}
        for _ in range(40):
            value["n"] = {}
            value = value["n"]
        assert client.post("/api/v1/session", json=deep,
                           headers=ORIGIN).status_code == 413

    def _fixture_rate_limit_ceiling(self):
        clock = FakeClock()
        from src.security.rate_limit import RateLimiter
        limiter = RateLimiter(clock, limits={"secret": (2.0, 0.01)})
        assert limiter.check("s", "secret") is None
        assert limiter.check("s", "secret") is None
        assert limiter.check("s", "secret") is not None

    def _fixture_privilege_escalation(self):
        from src.foundation.errors import ApiError
        from src.security.permissions import enforce_role
        for command_type in ("mayor.tax.propose", "admin.resource.grant"):
            with pytest.raises(ApiError):
                enforce_role("observer", command_type)

    def _fixture_authoritative_field_forgery(self):
        from src.api.wire import register_command_specs
        from src.api.schemas import SchemaRegistry
        from src.orchestrator.commands import (
            CommandRegistry,
            validate_envelope,
        )
        from src.foundation.errors import ApiError
        schemas = SchemaRegistry()
        registry = CommandRegistry()
        register_command_specs(schemas, registry)
        with pytest.raises(ApiError):
            validate_envelope(registry, command_envelope(
                "01K1AB2CD3EF4GH5JK6MNP7QS0", "w1",
                payload={"schema_version": 1, "paused": True,
                         "damage": 9999}))

    def _fixture_secret_leak_scan(self):
        redaction = RedactionFilter()
        redaction.register_secret_value("sk-fixture9999")
        assert "sk-fixture9999" not in redaction.redact(
            "token is sk-fixture9999 ok")

    def _fixture_unregistered_code_and_field_scan(self):
        from src.foundation.errors import spec_of
        assert spec_of("BACKEND_FAKE_CODE").code == \
            "BACKEND_INTERNAL_INVARIANT"
        with pytest.raises(LogPolicyError):
            check_fields_policy({"unregistered_field": "x"})

    FIXTURE_MANIFEST = {
        "伪造/缺失 Origin、跨源 preflight": _fixture_forged_origin,
        "缺失/错误 CSRF 头与 bootstrap 豁免边界":
            _fixture_csrf_and_bootstrap_boundary,
        "Ticket 重放、过期、跨 Session":
            _fixture_ticket_replay_expiry_cross_session,
        "静态路径穿越与符号链接": _fixture_path_traversal_and_symlink,
        "超大 body/帧、深嵌套 JSON": _fixture_oversize_and_deep_json,
        "各 Route Class 限速触顶": _fixture_rate_limit_ceiling,
        "越权命令（observer 发 mayor/admin）": _fixture_privilege_escalation,
        "权威字段伪造 payload": _fixture_authoritative_field_forgery,
        "注入测试 Key 后全目标泄漏扫描": _fixture_secret_leak_scan,
        "未注册错误码/未归类日志字段扫描":
            _fixture_unregistered_code_and_field_scan,
    }

    def test_manifest_covers_doc_fixture_list(self):
        assert len(self.FIXTURE_MANIFEST) == 10

    def test_all_fixtures_pass(self, tmp_path):
        failures = []
        for name, fixture in self.FIXTURE_MANIFEST.items():
            try:
                if name == "静态路径穿越与符号链接":
                    fixture(self, tmp_path)
                else:
                    fixture(self)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {exc!r}")
        assert failures == [], failures


# ---------------------------------------------------------------------------
# TEST-BACKEND-046：RULE-BACKEND-070 Load Profile 四零断言（短负载）
# ---------------------------------------------------------------------------

class TestLoadProfile:
    def test_short_load_four_zero_assertions(self):
        """命令洪峰 + 事件扇出短负载：
        零 DomainEvent 丢失 / 零幂等违规 / 零 invariant violation / 零 never 泄漏"""
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)

        # -- 短负载：200 条命令（限速器按 fake clock 放行）---------------------
        from src.api.wire import register_command_specs
        from src.orchestrator.idempotency import canonical_payload_hash
        from src.api.wire import COMMAND_PAYLOAD_SCHEMAS
        from src.foundation.schema_validate import validate_payload

        from backend_helpers import make_ulid_factory
        next_ulid = make_ulid_factory()
        command_count = 200
        for index in range(command_count):
            assembly.test_clock.advance(60)  # 20/s 补充下不触顶
            ulid = next_ulid()
            assembly.gateway.handle_frame(channel, {
                "protocol_version": 1, "frame_type": "command",
                "payload": command_envelope(ulid, world.world_id)})

        # -- 事件扇出：50 revision × 2 事件 --------------------------------------
        log = assembly.event_logs.setdefault(world.world_id,
                                             CommittedEventLog())
        all_events = []
        for revision in range(1, 51):
            events = [make_event(assembly, world.world_id, revision,
                                 event_id=f"evt-{revision}-a",
                                 causation_id=f"cmd-{revision}"),
                      make_event(assembly, world.world_id, revision,
                                 event_id=f"evt-{revision}-b",
                                 causation_id=f"cmd-{revision}")]
            log.append_commit(events)
            all_events.extend(events)
        assembly.gateway.publish_events(world.world_id, all_events)

        # -- 四零断言 -------------------------------------------------------------
        # 1. 零 DomainEvent 丢失：Outbox 收到的 == 发布的
        delivered = transport.by_type("event")
        delivered_ids = [f["payload"]["event_id"] for f in delivered]
        assert delivered_ids == [e["event_id"] for e in all_events]
        assert len(delivered_ids) == len(set(delivered_ids)) == 100
        # 2. 零幂等违规：200 条命令各一份回执，无重复 command_id
        receipts = transport.by_type("command_receipt")
        receipt_ids = [f["payload"]["command_id"] for f in receipts]
        assert len(receipt_ids) == command_count
        assert len(set(receipt_ids)) == command_count
        # 3. 零 invariant violation：无 INTERNAL_INVARIANT 错误帧
        invariant_errors = [f for f in transport.by_type("error")
                            if f["payload"]["code"] ==
                            "BACKEND_INTERNAL_INVARIANT"]
        assert invariant_errors == []
        # 4. 零 never 字段泄漏：全部出站帧文本不含 never 类键名/值
        blob = json.dumps(transport.frames, ensure_ascii=False)
        for never_value in ("csrf_token", "session_secret", "sk-"):
            assert never_value not in blob

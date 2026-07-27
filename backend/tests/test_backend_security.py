"""TEST-BACKEND-028..031：Session 生命周期、Origin/CORS/CSRF、角色矩阵、限速尺寸"""
from __future__ import annotations

import json

import pytest

from backend_helpers import (
    BASE_URL,
    ORIGIN,
    FakeClock,
    command_envelope,
    create_session,
    csrf_headers,
    make_assembly,
    make_client,
    make_id_factory,
    promote,
    ws_connect,
)
from src.foundation.errors import ApiError
from src.security.permissions import enforce_rest_role, enforce_role, min_role_for
from src.security.rate_limit import (
    MAX_BODY_BYTES,
    MAX_JSON_DEPTH,
    ROUTE_CLASS_LIMITS,
    RateLimiter,
    json_depth,
)
from src.security.sessions import (
    SESSION_IDLE_TIMEOUT_MS,
    SessionError,
    SessionService,
)

ULID_A = "01K1AB2CD3EF4GH5JK6MNP7QS0"


# ---------------------------------------------------------------------------
# TEST-BACKEND-028：RULE-BACKEND-042 Session 生命周期与重启失效
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    def _service(self, clock, secret=b"test-secret-32bytes-padding!!!"):
        return SessionService(make_id_factory("sess"), clock, secret=secret)

    def test_create_verify_roundtrip(self):
        clock = FakeClock()
        service = self._service(clock)
        session, cookie, csrf = service.create()
        verified = service.verify(cookie)
        assert verified.session_id == session.session_id
        assert verified.role_state == "observer"
        assert csrf

    def test_tampered_signature_rejected(self):
        clock = FakeClock()
        service = self._service(clock)
        session, cookie, _csrf = service.create()
        forged = f"{session.session_id}.{'0' * 64}"
        with pytest.raises(SessionError) as exc_info:
            service.verify(forged)
        assert exc_info.value.code == "BACKEND_SESSION_INVALID"

    def test_idle_timeout_expires_session(self):
        clock = FakeClock()
        service = self._service(clock)
        _session, cookie, _csrf = service.create()
        clock.advance(SESSION_IDLE_TIMEOUT_MS + 1)
        with pytest.raises(SessionError) as exc_info:
            service.verify(cookie)
        assert exc_info.value.code == "BACKEND_SESSION_INVALID"

    def test_activity_refreshes_idle_window(self):
        clock = FakeClock()
        service = self._service(clock)
        _session, cookie, _csrf = service.create()
        clock.advance(SESSION_IDLE_TIMEOUT_MS - 1000)
        service.verify(cookie)  # touch
        clock.advance(2000)
        assert service.verify(cookie).session_id  # 未过期

    def test_restart_invalidates_all_sessions(self):
        """进程重启 = 新 HMAC secret：旧 cookie 全部失效（RULE-BACKEND-042）"""
        clock = FakeClock()
        service = self._service(clock, secret=b"old-secret-32bytes-padding!!!!")
        _session, cookie, _csrf = service.create()
        restarted = self._service(clock, secret=b"new-secret-32bytes-padding!!!!")
        with pytest.raises(SessionError):
            restarted.verify(cookie)

    def test_role_transition_state_machine(self):
        clock = FakeClock()
        service = self._service(clock)
        session, _cookie, _csrf = service.create()
        with pytest.raises(SessionError) as exc_info:
            service.transition_role(session, "mayor")  # observer→mayor 非法
        assert exc_info.value.code == "BACKEND_CONFLICT_STATE"
        service.transition_role(session, "player")
        service.transition_role(session, "mayor")
        service.transition_role(session, "player")
        service.transition_role(session, "observer")
        assert session.role_state == "observer"


# ---------------------------------------------------------------------------
# TEST-BACKEND-029：RULE-BACKEND-043..045 Origin/CORS/CSRF 与 bootstrap 豁免边界
# ---------------------------------------------------------------------------

class TestOriginCsrfLayers:
    def test_bootstrap_exemption_boundary(self):
        """无 Cookie 时仅 anonymous_bootstrap 端点放行（RULE-BACKEND-045）"""
        client = make_client(make_assembly())
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/meta").status_code == 200
        assert client.post("/api/v1/session", json={"schema_version": 1},
                           headers=ORIGIN).status_code == 200
        # 其余全部拒绝
        assert client.get("/api/v1/worlds").status_code == 403
        assert client.get("/api/v1/settings").status_code == 403
        assert client.get("/api/v1/diagnostics/metrics").status_code == 403

    def test_missing_origin_on_write_rejected(self):
        client = make_client(make_assembly())
        response = client.post("/api/v1/session", json={"schema_version": 1})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "BACKEND_ORIGIN_REJECTED"

    def test_get_without_origin_allowed(self):
        client = make_client(make_assembly())
        assert client.get("/api/v1/health").status_code == 200

    def test_wrong_csrf_rejected(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        response = client.post("/api/v1/worlds", json={
            "schema_version": 1, "command_id": ULID_A, "name": "x",
            "seed_hex": "0123456789abcdef"},
            headers={**ORIGIN, "x-ai-town-csrf": "wrong-token"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "BACKEND_CSRF_REJECTED"

    def test_get_with_session_no_csrf_allowed(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)
        promote(assembly, info["session_id"])
        assert client.get("/api/v1/worlds").status_code == 200

    def test_host_header_enforced(self):
        client = make_client(make_assembly())
        response = client.get("/api/v1/health",
                              headers={"host": "evil.example:8765"})
        assert response.status_code == 403

    def test_cookie_attributes(self):
        client = make_client(make_assembly())
        client.post("/api/v1/session", json={"schema_version": 1},
                    headers=ORIGIN)
        set_cookie = client.cookies.jar
        # TestClient 不暴露全部属性，直接核对响应头
        response = client.post("/api/v1/session", json={"schema_version": 1},
                               headers=ORIGIN)
        for header in response.headers.get_list("set-cookie"):
            assert "samesite=strict" in header.lower()
            if "ai_town_session=" in header:
                assert "httponly" in header.lower()


# ---------------------------------------------------------------------------
# TEST-BACKEND-030：RULE-BACKEND-046 角色执行点与 PLAYER 矩阵一致性
# ---------------------------------------------------------------------------

class TestRoleEnforcement:
    @pytest.mark.parametrize("role,command_type,allowed", [
        ("observer", "player.move.set_target", False),
        ("observer", "system.world.pause", False),
        ("player", "player.move.set_target", True),
        ("player", "mayor.tax.propose", False),
        ("player", "admin.resource.grant", False),
        ("player", "system.world.pause", True),
        ("mayor", "mayor.tax.propose", True),
        ("mayor", "player.move.set_target", True),
        ("mayor", "admin.resource.grant", False),
        ("admin", "admin.resource.grant", True),
        ("admin", "mayor.tax.propose", True),
    ])
    def test_command_matrix(self, role, command_type, allowed):
        if allowed:
            enforce_role(role, command_type)
        else:
            with pytest.raises(ApiError) as exc_info:
                enforce_role(role, command_type)
            assert exc_info.value.code == "BACKEND_FORBIDDEN"

    def test_unregistered_prefix_fails_closed_to_admin(self):
        assert min_role_for("unknown.domain.action") == "admin"
        with pytest.raises(ApiError):
            enforce_role("mayor", "unknown.domain.action")

    def test_rest_route_class_matrix(self):
        for route_class in ("world-admin", "save", "settings", "secret",
                            "destructive", "ticket"):
            with pytest.raises(ApiError):
                enforce_rest_role("observer", route_class)
            enforce_rest_role("player", route_class)
        enforce_rest_role("observer", "health")
        enforce_rest_role("observer", "session")

    def test_ws_command_role_checked_against_session(self):
        """WS 命令路径的角色位点：observer 发 player 命令 → 拒绝回执"""
        assembly = make_assembly()
        client = make_client(assembly)
        info, _csrf = create_session(client)  # observer
        world = assembly.worlds.create("cmd-1", "w", "0123456789abcdef",
                                       "template.default")
        channel, transport = ws_connect(assembly, info["session_id"],
                                        world.world_id)
        assembly.gateway.handle_frame(channel, {
            "protocol_version": 1, "frame_type": "command",
            "payload": command_envelope(ULID_A, world.world_id,
                                        command_type="player.move.set_target",
                                        payload={"schema_version": 1,
                                                 "target": {"scene_id": "s",
                                                            "x_wu": 1.0,
                                                            "y_wu": 2.0}})})
        receipt = transport.by_type("command_receipt")[-1]["payload"]
        assert receipt["result"] == "rejected"
        assert receipt["error"]["code"] == "BACKEND_FORBIDDEN"


# ---------------------------------------------------------------------------
# TEST-BACKEND-031：RULE-BACKEND-047..048 速率与尺寸限制边界值
# ---------------------------------------------------------------------------

class TestRateAndSizeLimits:
    def test_bucket_exact_capacity_then_limited(self):
        clock = FakeClock()
        limiter = RateLimiter(clock, limits={"world-admin": (2.0, 1.0)})
        assert limiter.check("s1", "world-admin") is None
        assert limiter.check("s1", "world-admin") is None
        retry = limiter.check("s1", "world-admin")
        assert retry is not None and retry > 0  # 第 3 次超限 → retry_after

    def test_bucket_refills_over_time(self):
        clock = FakeClock()
        limiter = RateLimiter(clock, limits={"world-admin": (1.0, 1.0)})
        assert limiter.check("s1", "world-admin") is None
        assert limiter.check("s1", "world-admin") is not None
        clock.advance(1001)  # 补充 1 token
        assert limiter.check("s1", "world-admin") is None

    def test_unknown_route_class_fails_closed(self):
        clock = FakeClock()
        limiter = RateLimiter(clock)
        # 未登记 route_class → 保守全局限额，不放开
        for _ in range(5):
            assert limiter.check("s1", "no-such-class") is None
        assert limiter.check("s1", "no-such-class") is not None

    def test_rest_rate_limit_envelope(self):
        client = make_client(make_assembly())
        # health 类 120/分：连续 121 次必触顶
        statuses = [client.get("/api/v1/health").status_code
                    for _ in range(121)]
        assert 429 in statuses
        limited = client.get("/api/v1/health")
        if limited.status_code == 429:
            body = limited.json()
            assert body["error"]["code"] == "BACKEND_RATE_LIMITED"
            assert body["error"]["retryable"] is True

    def test_body_size_boundary(self):
        client = make_client(make_assembly())
        padding = MAX_BODY_BYTES - 60
        ok_body = json.dumps({"schema_version": 1, "pad": "x" * padding})
        ok_body = ok_body[:MAX_BODY_BYTES]
        response = client.post("/api/v1/session", content=ok_body,
                               headers={**ORIGIN,
                                        "content-type": "application/json"})
        assert response.status_code in (200, 400)  # 通过尺寸位点
        too_large = client.post("/api/v1/session",
                                content=b" " * (MAX_BODY_BYTES + 1),
                                headers={**ORIGIN,
                                         "content-type": "application/json"})
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "BACKEND_BODY_TOO_LARGE"

    def test_json_depth_boundary(self):
        # json_depth 把叶子计入层级：{"a": 1} → 2
        assert json_depth({"a": 1}) == 2
        nested_ok = value = {}
        for _ in range(MAX_JSON_DEPTH - 2):  # 总深度恰好 32
            value["n"] = {}
            value = value["n"]
        assert json_depth(nested_ok) <= MAX_JSON_DEPTH
        nested_deep = value = {}
        for _ in range(MAX_JSON_DEPTH + 2):
            value["n"] = {}
            value = value["n"]
        assert json_depth(nested_deep) > MAX_JSON_DEPTH
        client = make_client(make_assembly())
        response = client.post("/api/v1/session", json=nested_deep,
                               headers=ORIGIN)
        assert response.status_code == 413

    def test_route_class_limits_table_complete(self):
        for route_class in ("secret", "destructive", "world-admin", "save",
                            "ticket", "diagnostics", "settings", "session",
                            "health", "ws_command", "ws_ack"):
            capacity, refill = ROUTE_CLASS_LIMITS[route_class]
            assert capacity > 0 and refill > 0

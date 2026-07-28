"""TEST-BACKEND-013..016：路由清单、验证顺序、POST 幂等、GET 无副作用"""
from __future__ import annotations

import pytest

from backend_helpers import (
    BASE_URL,
    ORIGIN,
    create_session,
    create_world,
    csrf_headers,
    make_assembly,
    make_client,
    make_ulid_factory,
    promote,
)
from src.api.catalog import (
    AUTH_BOOTSTRAP,
    AUTH_SESSION,
    AUTH_SESSION_CSRF,
    ROUTE_CATALOG,
    audit_catalog,
    find_route,
    path_params,
)


# ---------------------------------------------------------------------------
# TEST-BACKEND-013：RULE-BACKEND-019..020 路由清单、404 边界与无世界写旁路
# ---------------------------------------------------------------------------

class TestRouteCatalog:
    def test_catalog_self_audit_clean(self):
        assert audit_catalog() == []

    def test_catalog_has_23_routes_with_unique_method_path(self):
        assert len(ROUTE_CATALOG) == 23
        keys = [(entry.method, entry.path) for entry in ROUTE_CATALOG]
        assert len(set(keys)) == len(keys)

    def test_every_route_class_known_and_auth_valid(self):
        for entry in ROUTE_CATALOG:
            assert entry.auth in (AUTH_BOOTSTRAP, AUTH_SESSION,
                                  AUTH_SESSION_CSRF)
            assert entry.route_class

    def test_find_route_matches_path_params(self):
        entry = find_route("GET", "/api/v1/worlds/w-123")
        assert entry is not None
        assert path_params(entry.path, "/api/v1/worlds/w-123") == {
            "world_id": "w-123"}
        assert find_route("GET", "/api/v1/worlds/w-123/saves/s-1/load") is None
        assert find_route("POST", "/api/v1/worlds/w-123/saves/s-1/load") \
            is not None

    def test_unknown_api_path_404_envelope(self):
        client = make_client(make_assembly())
        response = client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "BACKEND_NOT_FOUND"
        assert body["error"]["schema_version"] == 1

    def test_no_world_write_bypass(self):
        """所有写方法端点（除 bootstrap 的 session 颁发）都要求 Session+CSRF"""
        for entry in ROUTE_CATALOG:
            if entry.method in ("POST", "PUT", "DELETE"):
                if entry.path in ("/api/v1/session", "/api/v1/shutdown"):
                    assert entry.auth == AUTH_BOOTSTRAP
                else:
                    assert entry.auth == AUTH_SESSION_CSRF, entry.path


# ---------------------------------------------------------------------------
# TEST-BACKEND-014：RULE-BACKEND-021..022 envelope/版本/验证顺序无副作用
# ---------------------------------------------------------------------------

@pytest.fixture()
def ready_client():
    assembly = make_assembly()
    client = make_client(assembly)
    info, csrf = create_session(client)
    promote(assembly, info["session_id"])
    return assembly, client, info, csrf


class TestPipelineOrder:
    def test_origin_checked_before_body_parse(self, ready_client):
        """坏 Origin + 坏 JSON：先报 Origin（证明位点顺序），且无任何副作用"""
        _assembly, client, _info, csrf = ready_client
        response = client.post(
            "/api/v1/worlds", content=b"{not json",
            headers={"origin": "http://evil:8765",
                     "x-ai-town-csrf": csrf,
                     "content-type": "application/json"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "BACKEND_ORIGIN_REJECTED"

    def test_failed_validation_has_no_side_effects(self, ready_client):
        assembly, client, _info, _csrf = ready_client
        before = len(assembly.worlds.list())
        # 缺 CSRF 的有效 body：拒绝且世界未创建
        response = client.post("/api/v1/worlds", json={
            "schema_version": 1,
            "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
            "name": "x", "seed_hex": "0123456789abcdef"}, headers=ORIGIN)
        assert response.status_code == 403
        assert len(assembly.worlds.list()) == before

    def test_envelope_schema_version_gates(self, ready_client):
        _assembly, client, _info, csrf = ready_client
        response = client.post("/api/v1/worlds", json={
            "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
            "name": "x", "seed_hex": "0123456789abcdef"},
            headers=csrf_headers(csrf))
        assert response.json()["error"]["code"] == "BACKEND_SCHEMA_INVALID"
        response = client.post("/api/v1/worlds", json={
            "schema_version": 99,
            "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
            "name": "x", "seed_hex": "0123456789abcdef"},
            headers=csrf_headers(csrf))
        body = response.json()
        assert body["error"]["code"] == "BACKEND_PROTOCOL_MISMATCH"
        assert body["error"]["details"]["expected"] == 1

    def test_success_envelope_shape(self, ready_client):
        _assembly, client, _info, csrf = ready_client
        response = client.post("/api/v1/session", json={"schema_version": 1},
                               headers=ORIGIN)
        body = response.json()
        assert set(body.keys()) == {"schema_version", "data"}
        assert body["schema_version"] == 1

    def test_auth_column_enforced_per_endpoint(self, ready_client):
        """逐端点核对 auth 列：bootstrap 端点无 Cookie 放行，其余拒绝"""
        client = make_client(make_assembly())  # 无 session 的新 client
        # bootstrap：health/meta/session 放行
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/meta").status_code == 200
        assert client.post("/api/v1/session", json={"schema_version": 1},
                           headers=ORIGIN).status_code == 200
        # session 级：无 Cookie → 401
        assert client.get("/api/v1/worlds").status_code == 403
        # session_csrf 级：无 Cookie → 401
        assert client.post("/api/v1/worlds", json={
            "schema_version": 1,
            "command_id": "01K1AB2CD3EF4GH5JK6MNP7QS0", "name": "x",
            "seed_hex": "0123456789abcdef"}, headers=ORIGIN).status_code == 403


# ---------------------------------------------------------------------------
# TEST-BACKEND-015：RULE-BACKEND-023 POST 幂等与 Confirmation Token 生命周期
# ---------------------------------------------------------------------------

class TestPostIdempotency:
    def test_world_create_replay_returns_same_world(self, ready_client):
        assembly, client, _info, csrf = ready_client
        ulid = "01K1AB2CD3EF4GH5JK6MNP7QS0"
        first = create_world(client, csrf, ulid)
        second = create_world(client, csrf, ulid)
        assert first == second
        assert len(assembly.worlds.list()) == 1

    def test_confirmation_token_lifecycle(self, ready_client):
        assembly, client, info, csrf = ready_client
        world_id = create_world(client, csrf, "01K1AB2CD3EF4GH5JK6MNP7QS1")
        # 无 token 删除 → CONFIRMATION_REQUIRED
        response = client.request("DELETE", f"/api/v1/worlds/{world_id}",
                                  json={"schema_version": 1},
                                  headers=csrf_headers(csrf))
        assert response.status_code == 428
        assert response.json()["error"]["code"] == \
            "BACKEND_CONFIRMATION_REQUIRED"
        # 颁发 → 使用成功
        issue = client.post("/api/v1/confirmations", json={
            "schema_version": 1, "action": "world.delete"},
            headers=csrf_headers(csrf))
        token = issue.json()["data"]["confirmation_token"]
        deleted = client.request("DELETE", f"/api/v1/worlds/{world_id}",
                                 json={"schema_version": 1,
                                       "confirmation_token": token},
                                 headers=csrf_headers(csrf))
        assert deleted.status_code == 200
        # 单次性：同 token 再用 → 拒绝
        world_id2 = create_world(client, csrf, "01K1AB2CD3EF4GH5JK6MNP7QS2")
        replay = client.request("DELETE", f"/api/v1/worlds/{world_id2}",
                                json={"schema_version": 1,
                                      "confirmation_token": token},
                                headers=csrf_headers(csrf))
        assert replay.status_code == 428

    def test_confirmation_token_ttl(self, ready_client):
        assembly, client, _info, csrf = ready_client
        issue = client.post("/api/v1/confirmations", json={
            "schema_version": 1, "action": "world.delete"},
            headers=csrf_headers(csrf))
        token = issue.json()["data"]["confirmation_token"]
        assembly.test_clock.advance(60_001)
        world_id = create_world(client, csrf, "01K1AB2CD3EF4GH5JK6MNP7QS3")
        response = client.request("DELETE", f"/api/v1/worlds/{world_id}",
                                  json={"schema_version": 1,
                                        "confirmation_token": token},
                                  headers=csrf_headers(csrf))
        assert response.status_code == 428


# ---------------------------------------------------------------------------
# TEST-BACKEND-016：RULE-BACKEND-024 GET 无副作用与 Job 化长任务
# ---------------------------------------------------------------------------

class TestGetSideEffectFree:
    def test_get_endpoints_do_not_mutate(self, ready_client):
        assembly, client, _info, csrf = ready_client
        world_id = create_world(client, csrf, "01K1AB2CD3EF4GH5JK6MNP7QS4")
        before_worlds = [r.to_summary() for r in assembly.worlds.list()]
        before_settings = assembly.services.settings.get()
        before_revision = assembly.runtime.current_revision
        for _ in range(3):
            assert client.get("/api/v1/worlds").status_code == 200
            assert client.get(f"/api/v1/worlds/{world_id}").status_code == 200
            assert client.get("/api/v1/settings").status_code == 200
            assert client.get(
                f"/api/v1/worlds/{world_id}/saves").status_code == 200
        # diagnostics 类限速最严（2/分），单独一次核对无副作用即可
        assert client.get("/api/v1/diagnostics/metrics").status_code == 200
        assert [r.to_summary() for r in assembly.worlds.list()] == before_worlds
        assert assembly.services.settings.get() == before_settings
        assert assembly.runtime.current_revision == before_revision

    def test_diagnostics_package_is_job(self, ready_client):
        _assembly, client, _info, csrf = ready_client
        response = client.post("/api/v1/diagnostics/package", json={
            "schema_version": 1, "include_metrics": True},
            headers=csrf_headers(csrf))
        assert response.status_code == 202
        job = response.json()["data"]
        assert job["kind"] == "diagnostics_package"
        # 轮询直到终态（内存 builder 同步完成）
        polled = client.get(f"/api/v1/diagnostics/jobs/{job['job_id']}")
        assert polled.status_code == 200
        assert polled.json()["data"]["state"] == "succeeded"
        assert polled.json()["data"]["result_ref"]

    def test_job_poll_unknown_404(self, ready_client):
        _assembly, client, _info, _csrf = ready_client
        response = client.get("/api/v1/diagnostics/jobs/nope")
        assert response.status_code == 404

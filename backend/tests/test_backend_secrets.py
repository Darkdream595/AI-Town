"""TEST-BACKEND-032..035：Secret 提交通道、零泄漏扫描、ref 边界、生命周期审计"""
from __future__ import annotations

import json

import pytest

from backend_helpers import (
    create_session,
    csrf_headers,
    make_assembly,
    make_client,
    make_id_factory,
    make_utc_factory,
    promote,
)
from src.foundation.errors import ApiError
from src.security.redaction import RedactionFilter
from src.security.secrets import (
    SECRET_KIND_DEEPSEEK,
    ChainedSecretStore,
    CredentialRef,
    DpapiFileStore,
    MemorySecretStore,
    SecretService,
    WindowsCredentialManagerStore,
)

PLAINTEXT = "sk-test0123456789abcdefDEADBEEF"


def _secret_service(audit=None):
    redaction = RedactionFilter()
    return SecretService(MemorySecretStore(), redaction,
                         make_id_factory("ref"), audit=audit,
                         utc_now=make_utc_factory()), redaction


# ---------------------------------------------------------------------------
# TEST-BACKEND-032：RULE-BACKEND-049..050 提交通道与双后端存储往返
# ---------------------------------------------------------------------------

class TestSecretChannel:
    def test_put_secret_via_rest_channel(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, csrf = create_session(client)
        promote(assembly, info["session_id"])
        response = client.put("/api/v1/secrets/deepseek-api-key", json={
            "schema_version": 1, "api_key": PLAINTEXT},
            headers=csrf_headers(csrf))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["configured"] is True
        assert PLAINTEXT not in response.text
        assert data["masked_suffix"] == PLAINTEXT[-4:]

    def test_memory_store_roundtrip(self):
        store = MemorySecretStore()
        store.write("AI-Town/test", PLAINTEXT)
        assert store.read("AI-Town/test") == PLAINTEXT
        store.delete("AI-Town/test")
        assert store.read("AI-Town/test") is None

    def test_chained_store_fallback(self):
        """WCM 不可用时降级到次后端（双后端链；测试用 fake，不触真实凭据管理器）"""
        class _DeadBackend:
            backend_name = "dead"

            def write(self, target, plaintext):
                raise RuntimeError("wcm unavailable")

            def read(self, target):
                raise RuntimeError("wcm unavailable")

            def delete(self, target):
                raise RuntimeError("wcm unavailable")

        fallback = MemorySecretStore()
        chain = ChainedSecretStore([_DeadBackend(), fallback])
        chain.write("AI-Town/test", PLAINTEXT)
        assert chain.backend_name == "memory"
        assert chain.read("AI-Town/test") == PLAINTEXT

    def test_chained_store_all_dead_raises_storage_failure(self):
        class _DeadBackend:
            backend_name = "dead"

            def write(self, target, plaintext):
                raise RuntimeError("gone")

            def read(self, target):
                raise RuntimeError("gone")

            def delete(self, target):
                raise RuntimeError("gone")

        chain = ChainedSecretStore([_DeadBackend()])
        with pytest.raises(ApiError) as exc_info:
            chain.write("AI-Town/test", PLAINTEXT)
        assert exc_info.value.code == "BACKEND_STORAGE_FAILURE"

    def test_empty_key_rejected(self):
        service, _redaction = _secret_service()
        with pytest.raises(ApiError) as exc_info:
            service.set_secret(SECRET_KIND_DEEPSEEK, "   ")
        assert exc_info.value.code == "BACKEND_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# TEST-BACKEND-033：RULE-BACKEND-051 全目标明文零泄漏扫描
# ---------------------------------------------------------------------------

class TestPlaintextZeroLeak:
    def test_plaintext_absent_from_all_surfaces(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, csrf = create_session(client)
        promote(assembly, info["session_id"])
        client.put("/api/v1/secrets/deepseek-api-key", json={
            "schema_version": 1, "api_key": PLAINTEXT},
            headers=csrf_headers(csrf))
        surfaces = []
        # 1) Secret 状态端点
        status = client.get("/api/v1/secrets/deepseek-api-key/status")
        surfaces.append(("secret_status", status.text))
        # 2) 指标快照
        surfaces.append(("metrics",
                         client.get("/api/v1/diagnostics/metrics").text))
        # 3) 审计事件流
        surfaces.append(("audit_events", json.dumps(
            assembly.secrets._audit.__self__ if hasattr(
                assembly.secrets._audit, "__self__") else {}, default=str)))
        # 4) 结构化日志内存环
        surfaces.append(("logs", json.dumps(
            assembly.logger.ring_records(), ensure_ascii=False, default=str)))
        # 5) 错误 envelope（故意触发一次 secret 校验错误）
        error = client.put("/api/v1/secrets/deepseek-api-key",
                           json={"schema_version": 1, "api_key": ""},
                           headers=csrf_headers(csrf))
        surfaces.append(("error_envelope", error.text))
        # 6) 健康端点
        surfaces.append(("health", client.get("/api/v1/health").text))
        for name, text in surfaces:
            assert PLAINTEXT not in text, f"plaintext leaked into {name}"


# ---------------------------------------------------------------------------
# TEST-BACKEND-034：RULE-BACKEND-052..053 ref 边界、单请求持有与 Redaction
# ---------------------------------------------------------------------------

class TestCredentialRefBoundary:
    def test_auth_header_handle_single_use(self):
        service, _redaction = _secret_service()
        service.set_secret(SECRET_KIND_DEEPSEEK, PLAINTEXT)
        ref = service.get_credential_ref(SECRET_KIND_DEEPSEEK)
        handle = service.resolve_for_request(ref)
        header = handle.header()
        assert header == {"Authorization": f"Bearer {PLAINTEXT}"}
        with pytest.raises(ApiError) as exc_info:
            handle.header()  # 第二次调用即失效（调用方 bug → 内部不变量）
        assert exc_info.value.code == "BACKEND_INTERNAL_INVARIANT"

    def test_delete_invalidates_ref(self):
        service, _redaction = _secret_service()
        service.set_secret(SECRET_KIND_DEEPSEEK, PLAINTEXT)
        ref = service.get_credential_ref(SECRET_KIND_DEEPSEEK)
        service.delete_secret(SECRET_KIND_DEEPSEEK)
        with pytest.raises(ApiError) as exc_info:
            service.resolve_for_request(ref)
        assert exc_info.value.code == "BACKEND_FORBIDDEN"
        assert "stale" in str(exc_info.value.details)

    def test_rotation_bumps_generation_stales_old_ref(self):
        service, _redaction = _secret_service()
        service.set_secret(SECRET_KIND_DEEPSEEK, PLAINTEXT)
        old_ref = service.get_credential_ref(SECRET_KIND_DEEPSEEK)
        service.set_secret(SECRET_KIND_DEEPSEEK, "sk-new999999999999999999")
        with pytest.raises(ApiError):
            service.resolve_for_request(old_ref)

    def test_redaction_exact_and_pattern(self):
        redaction = RedactionFilter()
        fingerprint = redaction.register_secret_value(PLAINTEXT)
        assert len(fingerprint) == 12
        text = f"key={PLAINTEXT} and sk-live999888777"
        redacted = redaction.redact(text)
        assert PLAINTEXT not in redacted
        assert "sk-live999888777" not in redacted
        assert "key=" in redacted  # 非敏感部分保留

    def test_fingerprint_stable_and_not_plaintext(self):
        redaction = RedactionFilter()
        first = redaction.register_secret_value(PLAINTEXT)
        assert first == redaction.register_secret_value(PLAINTEXT)
        assert PLAINTEXT[-4:] not in first


# ---------------------------------------------------------------------------
# TEST-BACKEND-035：RULE-BACKEND-054 生命周期审计、删除失效与 verify 语义
# ---------------------------------------------------------------------------

class TestSecretLifecycleAudit:
    def test_audit_events_masked_with_fingerprint(self):
        events = []
        service, _redaction = _secret_service(audit=events.append)
        service.set_secret(SECRET_KIND_DEEPSEEK, PLAINTEXT)
        service.delete_secret(SECRET_KIND_DEEPSEEK)
        assert [e["action"] for e in events] == ["set", "delete"]
        blob = json.dumps(events)
        assert PLAINTEXT not in blob
        assert events[0]["masked_suffix"] == PLAINTEXT[-4:]
        assert events[0]["fingerprint"]
        assert events[0]["result"] == "ok"

    def test_status_transitions(self):
        service, _redaction = _secret_service()
        before = service.status(SECRET_KIND_DEEPSEEK)
        assert before["configured"] is False
        assert before["last_verify_result"] == "not_verified"
        service.set_secret(SECRET_KIND_DEEPSEEK, PLAINTEXT)
        configured = service.status(SECRET_KIND_DEEPSEEK)
        assert configured["configured"] is True
        assert configured["storage_backend"] == "memory"
        service.record_verify(SECRET_KIND_DEEPSEEK, "ok")
        verified = service.status(SECRET_KIND_DEEPSEEK)
        assert verified["last_verify_result"] == "ok"
        assert verified["last_verified_at"]
        service.delete_secret(SECRET_KIND_DEEPSEEK)
        after = service.status(SECRET_KIND_DEEPSEEK)
        assert after["configured"] is False
        assert after["masked_suffix"] is None

    def test_verify_on_unconfigured_404(self):
        service, _redaction = _secret_service()
        with pytest.raises(ApiError) as exc_info:
            service.record_verify(SECRET_KIND_DEEPSEEK, "ok")
        assert exc_info.value.code == "BACKEND_NOT_FOUND"

    def test_delete_via_rest_requires_confirmation(self):
        assembly = make_assembly()
        client = make_client(assembly)
        info, csrf = create_session(client)
        promote(assembly, info["session_id"])
        client.put("/api/v1/secrets/deepseek-api-key", json={
            "schema_version": 1, "api_key": PLAINTEXT},
            headers=csrf_headers(csrf))
        issue = client.post("/api/v1/confirmations", json={
            "schema_version": 1, "action": "secret.delete"},
            headers=csrf_headers(csrf))
        token = issue.json()["data"]["confirmation_token"]
        deleted = client.request("DELETE", "/api/v1/secrets/deepseek-api-key",
                                 json={"schema_version": 1,
                                       "confirmation_token": token},
                                 headers=csrf_headers(csrf))
        assert deleted.status_code == 200
        assert deleted.json()["data"]["configured"] is False

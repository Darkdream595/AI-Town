"""DOC-RELEASE-008：备用停止入口与安全关闭契约。"""
from __future__ import annotations

from backend_helpers import BASE_URL, make_assembly, make_client


def _post_shutdown(client, token: str):
    return client.post(
        "/api/v1/shutdown",
        json={"schema_version": 1, "shutdown_token": token},
        headers={"origin": BASE_URL},
    )


def test_shutdown_with_matching_token_begins_drain_once():
    assembly = make_assembly()
    calls: list[str] = []
    assembly.services.shutdown_token = "a" * 32
    assembly.services.shutdown_request = lambda: calls.append("requested")
    client = make_client(assembly)

    first = _post_shutdown(client, "a" * 32)
    second = _post_shutdown(client, "a" * 32)

    assert first.status_code == 202
    assert first.json()["data"]["status"] == "shutting_down"
    assert second.status_code == 202
    assert second.json()["data"]["status"] == "shutting_down"
    assert calls == ["requested"]
    assert assembly.runtime.state == "draining"


def test_shutdown_rejects_wrong_or_unconfigured_token():
    assembly = make_assembly()
    assembly.services.shutdown_token = "a" * 32
    client = make_client(assembly)

    wrong = _post_shutdown(client, "b" * 32)
    assembly.services.shutdown_token = None
    unconfigured = _post_shutdown(client, "a" * 32)

    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "BACKEND_FORBIDDEN"
    assert unconfigured.status_code == 403


def test_shutdown_schema_requires_version_and_token():
    client = make_client(make_assembly())

    missing_version = client.post(
        "/api/v1/shutdown",
        json={"shutdown_token": "a" * 32},
        headers={"origin": BASE_URL},
    )
    missing_token = client.post(
        "/api/v1/shutdown",
        json={"schema_version": 1},
        headers={"origin": BASE_URL},
    )

    assert missing_version.status_code == 400
    assert missing_token.status_code == 400

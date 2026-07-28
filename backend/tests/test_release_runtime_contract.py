"""Launcher 与 backend 的 release runtime 契约。"""
from __future__ import annotations

from src.orchestrator.runtime import ProcessRuntime


def test_health_exposes_release_identity_and_integrity():
    runtime = ProcessRuntime(
        lambda: 1_000,
        package_version="0.1.0",
        build_id="build.test",
        package_integrity="verified",
    )

    health = runtime.health()

    assert health["package_version"] == "0.1.0"
    assert health["build_id"] == "build.test"
    assert health["package_integrity"] == "verified"

"""生成工具不得在仓库中保存 DashScope 凭据。"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTH_HELPER = PROJECT_ROOT / "tools" / "dashscope_auth.py"
GENERATION_SCRIPTS = (
    PROJECT_ROOT / "tools" / "batch_generate_simplified.py",
    PROJECT_ROOT / "tools" / "batch_generate_sprites.py",
    PROJECT_ROOT / "tools" / "batch_generate_sprites_parallel.py",
    PROJECT_ROOT / "tools" / "batch_generate_sprites_sdk.py",
    PROJECT_ROOT / "tools" / "test_generate_one.py",
)


def _load_auth_helper():
    spec = importlib.util.spec_from_file_location("dashscope_auth", AUTH_HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dashscope_key_is_required_from_environment(monkeypatch):
    auth = _load_auth_helper()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        auth.require_dashscope_api_key()


def test_dashscope_key_from_environment_is_preserved(monkeypatch):
    auth = _load_auth_helper()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")

    assert auth.require_dashscope_api_key() == "test-only-key"


def test_generation_scripts_contain_no_sk_prefixed_secret_literals():
    for script in GENERATION_SCRIPTS:
        source = script.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        secret_literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("sk-")
            and len(node.value) > 16
        ]

        if secret_literals:
            pytest.fail(f"{script} contains an embedded sk- credential")
        assert "require_dashscope_api_key" in source

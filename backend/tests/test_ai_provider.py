"""
测试 DeepSeek 模型策略与 Thinking 路由

覆盖 TEST-AI-025/026/027/028（DOC-AI-007 §11）
"""

import json

import pytest

from src.ai import (
    FakeModelProvider,
    ModelRequestV1,
    PlanKind,
    ProviderFailureKind,
    classify_provider_error,
    default_deepseek_profile,
    parse_provider_response,
    route_thinking_policy,
)

from ai_helpers import ULID_A, make_valid_proposal


def _request(prompt_id: str = "resident-action/v1", thinking: bool = False, effort=None) -> ModelRequestV1:
    return ModelRequestV1(
        request_id=ULID_A,
        profile_id="provider.deepseek.v4_flash.v1",
        model="deepseek-v4-flash",
        prompt_id=prompt_id,
        messages=({"role": "user", "content": "test"},),
        json_output_enabled=True,
        thinking_enabled=thinking,
        reasoning_effort=effort,
        max_output_tokens=700,
        deadline_monotonic_ms=9999999,
        idempotency_key="idem-1",
    )


class TestThinkingRouting:
    """TEST-AI-025：routing matrix 与显式 toggle"""

    def test_immediate_action_thinking_off(self):
        policy = route_thinking_policy(PlanKind.IMMEDIATE_ACTION)
        assert policy.thinking_enabled is False
        assert policy.reasoning_effort is None
        assert policy.prompt_id == "resident-action/v1"

    def test_hourly_intent_thinking_off(self):
        policy = route_thinking_policy(PlanKind.HOURLY_INTENT)
        assert policy.thinking_enabled is False
        assert policy.reasoning_effort is None

    def test_daily_plan_thinking_on_high(self):
        policy = route_thinking_policy(PlanKind.DAILY_PLAN)
        assert policy.thinking_enabled is True
        assert policy.reasoning_effort == "high"

    def test_combat_turn_thinking_off(self):
        policy = route_thinking_policy(PlanKind.COMBAT_TURN)
        assert policy.thinking_enabled is False
        assert policy.prompt_id == "resident-combat-turn/v1"


class TestJsonOutputAndValidation:
    """TEST-AI-026：JSON Output + strict local validation"""

    def test_fake_provider_returns_registered_artifact(self):
        provider = FakeModelProvider()
        request = _request()
        artifact = make_valid_proposal("wait")
        provider.register_response(request, artifact)
        response = provider.generate_json(request)
        assert response.finish_status == "completed"
        assert json.loads(response.artifact_bytes.decode("utf-8"))["action"] == "wait"

    def test_fake_provider_deterministic_by_hash(self):
        provider = FakeModelProvider()
        request = _request()
        provider.register_response(request, make_valid_proposal("wait"))
        response1 = provider.generate_json(request)
        response2 = provider.generate_json(request)
        assert response1.artifact_bytes == response2.artifact_bytes

    def test_unregistered_request_empty_response(self):
        provider = FakeModelProvider()
        response = provider.generate_json(_request())
        assert response.failure_kind == ProviderFailureKind.EMPTY_RESPONSE


class TestReasoningContentDisposal:
    """TEST-AI-027：reasoning_content/key sink negative audit"""

    def test_reasoning_content_dropped(self):
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(make_valid_proposal("wait")),
                            "reasoning_content": "CHAIN_OF_THOUGHT_SHOULD_BE_DROPPED",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        ).encode("utf-8")
        response = parse_provider_response(body, "req-1")
        assert response.finish_status == "completed"
        # Normalized Response 不含 reasoning 字段
        assert not hasattr(response, "reasoning_content")
        assert b"CHAIN_OF_THOUGHT" not in (response.artifact_bytes or b"")

    def test_profile_requires_https(self):
        from src.ai.provider import ProviderProfile

        with pytest.raises(ValueError):
            ProviderProfile(
                profile_id="p.insecure",
                provider_kind="deepseek_compatible",
                base_url="http://api.deepseek.com",
                model="deepseek-v4-flash",
                credential_ref="ref",
                connect_timeout_real_ms=5000,
                request_timeout_real_ms=30000,
                max_response_bytes=16384,
                profile_version=1,
            )

    def test_default_profile(self):
        profile = default_deepseek_profile()
        assert profile.base_url.startswith("https://")
        assert profile.model == "deepseek-v4-flash"


class TestFailureClassification:
    """TEST-AI-028：provider failure classification"""

    def test_injected_failures(self):
        provider = FakeModelProvider()
        request = _request()
        provider.register_failure(request, ProviderFailureKind.RATE_LIMITED)
        response = provider.generate_json(request)
        assert response.failure_kind == ProviderFailureKind.RATE_LIMITED
        assert response.finish_status == "failed"

    def test_cancellation(self):
        provider = FakeModelProvider()
        request = _request()
        provider.register_response(request, make_valid_proposal("wait"))
        response = provider.generate_json(request, cancellation_requested=True)
        assert response.failure_kind == ProviderFailureKind.CANCELLED

    def test_parse_empty_body(self):
        response = parse_provider_response(b"", "req-2")
        assert response.failure_kind == ProviderFailureKind.EMPTY_RESPONSE

    def test_parse_oversized_body(self):
        response = parse_provider_response(b" " * 16385, "req-3")
        assert response.failure_kind == ProviderFailureKind.RESPONSE_TOO_LARGE

    def test_parse_invalid_json(self):
        response = parse_provider_response(b"not json", "req-4")
        assert response.failure_kind == ProviderFailureKind.INVALID_JSON

    def test_classify_httpx_errors(self):
        import httpx

        request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
        assert (
            classify_provider_error(httpx.ConnectTimeout("timeout", request=request))
            == ProviderFailureKind.CONNECT_TIMEOUT
        )
        assert (
            classify_provider_error(httpx.ReadTimeout("timeout", request=request))
            == ProviderFailureKind.REQUEST_TIMEOUT
        )
        response_429 = httpx.Response(429, request=request)
        assert (
            classify_provider_error(
                httpx.HTTPStatusError("rate", request=request, response=response_429)
            )
            == ProviderFailureKind.RATE_LIMITED
        )
        response_500 = httpx.Response(500, request=request)
        assert (
            classify_provider_error(
                httpx.HTTPStatusError("server", request=request, response=response_500)
            )
            == ProviderFailureKind.PROVIDER_UNAVAILABLE
        )

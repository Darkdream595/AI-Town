"""
DeepSeek 模型策略与 Thinking 路由

符合 DOC-AI-007：
- RULE-AI-037：所有请求显式设置 Thinking；即时/Hourly/combat 为 off，Daily/复杂规划为 on+high
- RULE-AI-040：reasoning_content 不进入 Normalized Response/日志/Event/Memory
- RULE-AI-042：HTTP success 不是 Proposal success；分类见 ProviderFailureKind
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .constants import PlanKind, ProviderFailureKind

#: 模型响应上限（DOC-AI-004 §9）
MAX_RESPONSE_BYTES = 16 * 1024

#: 每世界普通 in-flight（DOC-AI-009 §9）
MAX_IN_FLIGHT_PER_WORLD = 2


@dataclass(frozen=True)
class ProviderProfile:
    """Provider Profile（DES-AI-007）"""

    profile_id: str
    provider_kind: str
    base_url: str
    model: str
    credential_ref: str
    connect_timeout_real_ms: int
    request_timeout_real_ms: int
    max_response_bytes: int
    profile_version: int

    def __post_init__(self) -> None:
        # 只允许 https endpoint，开发 FakeProvider 除外（DOC-AI-007 §9）
        if self.provider_kind != "fake" and not self.base_url.startswith("https://"):
            raise ValueError(f"endpoint 必须 https: {self.base_url}")


def default_deepseek_profile() -> ProviderProfile:
    """已批准总体设计的默认 profile（DES-AI-007）"""
    return ProviderProfile(
        profile_id="provider.deepseek.v4_flash.v1",
        provider_kind="deepseek_compatible",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        credential_ref="windows_secret.deepseek_api_key",
        connect_timeout_real_ms=5000,
        request_timeout_real_ms=30000,
        max_response_bytes=MAX_RESPONSE_BYTES,
        profile_version=1,
    )


@dataclass(frozen=True)
class ThinkingPolicy:
    """Thinking 路由（DOC-AI-007 §4 表）"""

    thinking_enabled: bool
    reasoning_effort: Optional[str]  # "high" | None
    prompt_id: str


def route_thinking_policy(plan_kind: PlanKind) -> ThinkingPolicy:
    """五类 request 的 Thinking/reasoning_effort 路由矩阵（TEST-AI-025）"""
    if plan_kind == PlanKind.DAILY_PLAN:
        return ThinkingPolicy(thinking_enabled=True, reasoning_effort="high", prompt_id="resident-daily-plan/v1")
    if plan_kind == PlanKind.HOURLY_INTENT:
        return ThinkingPolicy(thinking_enabled=False, reasoning_effort=None, prompt_id="resident-hourly-intent/v1")
    if plan_kind == PlanKind.IMMEDIATE_ACTION:
        return ThinkingPolicy(thinking_enabled=False, reasoning_effort=None, prompt_id="resident-action/v1")
    if plan_kind == PlanKind.COMBAT_TURN:
        return ThinkingPolicy(thinking_enabled=False, reasoning_effort=None, prompt_id="resident-combat-turn/v1")
    raise ValueError(f"未知 plan_kind: {plan_kind}")


@dataclass(frozen=True)
class ModelRequestV1:
    """ModelRequestV1（DOC-AI-007 §4 必含字段）"""

    request_id: str
    profile_id: str
    model: str
    prompt_id: str
    messages: tuple[dict[str, str], ...]
    json_output_enabled: bool
    thinking_enabled: bool
    reasoning_effort: Optional[str]
    max_output_tokens: int
    deadline_monotonic_ms: int
    idempotency_key: str


@dataclass(frozen=True)
class NormalizedModelResponse:
    """
    Normalized Response（DOC-AI-007 §3）

    只含 artifact bytes、usage、finish/status 与 provider request ID。
    绝不含 reasoning_content（RULE-AI-040）。
    """

    artifact_bytes: Optional[bytes]
    input_tokens: int
    output_tokens: int
    finish_status: str  # "completed" | "failed" | "cancelled"
    provider_request_id: str
    failure_kind: Optional[ProviderFailureKind] = None


class ModelProvider(Protocol):
    """Provider Port（DOC-AI-007 §4）"""

    def generate_json(
        self, request: ModelRequestV1, cancellation_requested: bool = False
    ) -> NormalizedModelResponse:
        ...

    def probe_profile(self, profile_id: str) -> bool:
        ...


@dataclass
class InjectedFailure:
    """FakeProvider 注入的失败（RULE-AI-067）"""

    failure_kind: ProviderFailureKind


class FakeModelProvider:
    """
    按 input hash 返回固定响应的 FakeModelProvider（RULE-AI-067）

    可注入 timeout、empty、invalid JSON、forbidden、rate limit 和 late result。
    """

    def __init__(self) -> None:
        self._responses: dict[str, bytes] = {}
        self._failures: dict[str, InjectedFailure] = {}
        self.received_requests: list[ModelRequestV1] = []

    @staticmethod
    def request_fingerprint(request: ModelRequestV1) -> str:
        canonical = json.dumps(
            {
                "prompt_id": request.prompt_id,
                "messages": list(request.messages),
                "thinking_enabled": request.thinking_enabled,
                "reasoning_effort": request.reasoning_effort,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def register_response(self, request: ModelRequestV1, artifact: dict[str, Any]) -> str:
        """为请求指纹注册固定 JSON 响应"""
        fingerprint = self.request_fingerprint(request)
        self._responses[fingerprint] = json.dumps(artifact, ensure_ascii=False).encode("utf-8")
        return fingerprint

    def register_response_bytes(self, request: ModelRequestV1, raw: bytes) -> str:
        fingerprint = self.request_fingerprint(request)
        self._responses[fingerprint] = raw
        return fingerprint

    def register_failure(self, request: ModelRequestV1, failure_kind: ProviderFailureKind) -> None:
        fingerprint = self.request_fingerprint(request)
        self._failures[fingerprint] = InjectedFailure(failure_kind=failure_kind)

    def generate_json(
        self, request: ModelRequestV1, cancellation_requested: bool = False
    ) -> NormalizedModelResponse:
        self.received_requests.append(request)
        fingerprint = self.request_fingerprint(request)

        if cancellation_requested:
            return NormalizedModelResponse(
                artifact_bytes=None,
                input_tokens=0,
                output_tokens=0,
                finish_status="cancelled",
                provider_request_id=f"fake-{fingerprint[:12]}",
                failure_kind=ProviderFailureKind.CANCELLED,
            )

        injected = self._failures.get(fingerprint)
        if injected is not None:
            return NormalizedModelResponse(
                artifact_bytes=None,
                input_tokens=0,
                output_tokens=0,
                finish_status="failed",
                provider_request_id=f"fake-{fingerprint[:12]}",
                failure_kind=injected.failure_kind,
            )

        raw = self._responses.get(fingerprint)
        if raw is None:
            return NormalizedModelResponse(
                artifact_bytes=None,
                input_tokens=0,
                output_tokens=0,
                finish_status="failed",
                provider_request_id=f"fake-{fingerprint[:12]}",
                failure_kind=ProviderFailureKind.EMPTY_RESPONSE,
            )
        return NormalizedModelResponse(
            artifact_bytes=raw,
            input_tokens=0,
            output_tokens=0,
            finish_status="completed",
            provider_request_id=f"fake-{fingerprint[:12]}",
        )

    def probe_profile(self, profile_id: str) -> bool:
        return True


def parse_provider_response(
    raw_body: bytes, provider_request_id: str, max_response_bytes: int = MAX_RESPONSE_BYTES
) -> NormalizedModelResponse:
    """
    DeepSeek 兼容响应解析（RULE-AI-040/042）

    - 读取后立即丢弃 reasoning_content，不进入 Normalized Response
    - 大小/空响应/非法 JSON 分类
    """
    if len(raw_body) == 0:
        return NormalizedModelResponse(
            artifact_bytes=None,
            input_tokens=0,
            output_tokens=0,
            finish_status="failed",
            provider_request_id=provider_request_id,
            failure_kind=ProviderFailureKind.EMPTY_RESPONSE,
        )
    if len(raw_body) > max_response_bytes:
        return NormalizedModelResponse(
            artifact_bytes=None,
            input_tokens=0,
            output_tokens=0,
            finish_status="failed",
            provider_request_id=provider_request_id,
            failure_kind=ProviderFailureKind.RESPONSE_TOO_LARGE,
        )
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return NormalizedModelResponse(
            artifact_bytes=None,
            input_tokens=0,
            output_tokens=0,
            finish_status="failed",
            provider_request_id=provider_request_id,
            failure_kind=ProviderFailureKind.INVALID_JSON,
        )

    try:
        message = payload["choices"][0]["message"]
        # reasoning_content 在此读取并立即丢弃，绝不向下游传递
        _ = message.get("reasoning_content")
        content = message.get("content")
        usage = payload.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
    except (KeyError, IndexError, TypeError, ValueError):
        return NormalizedModelResponse(
            artifact_bytes=None,
            input_tokens=0,
            output_tokens=0,
            finish_status="failed",
            provider_request_id=provider_request_id,
            failure_kind=ProviderFailureKind.INVALID_JSON,
        )

    if not content:
        return NormalizedModelResponse(
            artifact_bytes=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_status="failed",
            provider_request_id=provider_request_id,
            failure_kind=ProviderFailureKind.EMPTY_RESPONSE,
        )

    return NormalizedModelResponse(
        artifact_bytes=content.encode("utf-8"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_status="completed",
        provider_request_id=provider_request_id,
    )


def classify_provider_error(exception: Exception) -> ProviderFailureKind:
    """异常 -> 失败分类（TEST-AI-028）"""
    import httpx

    if isinstance(exception, httpx.ConnectTimeout):
        return ProviderFailureKind.CONNECT_TIMEOUT
    if isinstance(exception, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return ProviderFailureKind.REQUEST_TIMEOUT
    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code
        if status == 429:
            return ProviderFailureKind.RATE_LIMITED
        if status in (400, 422):
            return ProviderFailureKind.CONTENT_REFUSED
        if status in (401, 403):
            return ProviderFailureKind.CONFIG_INVALID
        return ProviderFailureKind.PROVIDER_UNAVAILABLE
    if isinstance(exception, (httpx.ConnectError, httpx.NetworkError)):
        return ProviderFailureKind.PROVIDER_UNAVAILABLE
    return ProviderFailureKind.PROVIDER_UNAVAILABLE

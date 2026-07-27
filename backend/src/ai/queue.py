"""
AI 请求并发、优先级与生命周期

符合 DOC-AI-009：
- RULE-AI-049：普通 provider 请求每世界 max_in_flight=2，pending 默认上限 64
- RULE-AI-050：priority_class, deadline, accepted_sequence, resident_id, request_id 唯一全序
- RULE-AI-052：deadline 使用 monotonic RealTime，Pause 不延长网络 timeout
- RULE-AI-053：仅 connect/provider unavailable/rate limit 可重试；max attempts=2；退避 250/1000ms + jitter
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constants import RETRYABLE_FAILURES, ProviderFailureKind

MAX_IN_FLIGHT = 2
MAX_PENDING = 64
DEFAULT_MAX_ATTEMPTS = 2
#: 退避序列（real ms），索引为 attempt-1
RETRY_BACKOFF_MS: tuple[int, ...] = (250, 1000)


class RequestState(str, Enum):
    """请求状态机（DES-AI-009）"""

    CREATED = "created"
    QUEUED = "queued"
    LEASED = "leased"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RETRY_WAIT = "retry_wait"
    TERMINAL_FAILED = "terminal_failed"


@dataclass
class AIRequest:
    """Request record（DES-AI-009）"""

    request_id: str
    logical_request_id: str
    resident_id: str
    job_id: str
    priority_class: int  # 0..5，TIME 提供
    accepted_sequence: int
    observed_revision: int
    context_hash: str
    deadline_monotonic_ms: int
    attempt: int = 1
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    state: RequestState = RequestState.CREATED
    deadline_game_time: Optional[int] = None

    def ordering_key(self) -> tuple:
        """
        全序（RULE-AI-050）：
        priority_class, deadline_game_time|null-as-infinity, accepted_sequence, resident_id, request_id
        """
        deadline_key = self.deadline_game_time if self.deadline_game_time is not None else float("inf")
        return (
            self.priority_class,
            deadline_key,
            self.accepted_sequence,
            self.resident_id,
            self.request_id,
        )


class QueueFullError(Exception):
    """pending 超上限（DOC-AI-009 §8）"""


class RequestQueue:
    """
    AI Request Queue

    - in-flight ≤ 2（不能为追赶高倍速扩大）
    - pending ≤ 64
    - lease 按全序
    """

    def __init__(self, max_in_flight: int = MAX_IN_FLIGHT, max_pending: int = MAX_PENDING):
        self._max_in_flight = max_in_flight
        self._max_pending = max_pending
        self._requests: dict[str, AIRequest] = {}
        self._sequence_counter = 0

    def next_sequence(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def enqueue(self, request: AIRequest) -> None:
        """入队；queue full 时 priority 5 先拒绝（DOC-AI-009 §8）"""
        pending = [
            r for r in self._requests.values() if r.state in (RequestState.QUEUED, RequestState.RETRY_WAIT)
        ]
        if len(pending) >= self._max_pending:
            raise QueueFullError(f"pending 超上限 {self._max_pending}，priority {request.priority_class} 拒绝")
        request.state = RequestState.QUEUED
        self._requests[request.request_id] = request

    def lease_next(self, now_monotonic_ms: int) -> Optional[AIRequest]:
        """按全序 lease 下一个；in-flight 满则返回 None"""
        in_flight_count = sum(
            1 for r in self._requests.values() if r.state in (RequestState.LEASED, RequestState.IN_FLIGHT)
        )
        if in_flight_count >= self._max_in_flight:
            return None

        candidates = [
            r
            for r in self._requests.values()
            if r.state in (RequestState.QUEUED, RequestState.RETRY_WAIT)
            and r.deadline_monotonic_ms > now_monotonic_ms
        ]
        if not candidates:
            return None
        selected = min(candidates, key=lambda r: r.ordering_key())
        selected.state = RequestState.LEASED
        return selected

    def mark_in_flight(self, request_id: str) -> None:
        self._requests[request_id].state = RequestState.IN_FLIGHT

    def mark_succeeded(self, request_id: str) -> None:
        self._requests[request_id].state = RequestState.SUCCEEDED

    def mark_terminal_failed(self, request_id: str) -> None:
        self._requests[request_id].state = RequestState.TERMINAL_FAILED

    def cancel(self, request_id: str) -> None:
        """cooperative cancel；迟到 response 标记 discarded 由调用方处理（RULE-AI-051）"""
        request = self._requests.get(request_id)
        if request is not None and request.state in (
            RequestState.QUEUED,
            RequestState.LEASED,
            RequestState.IN_FLIGHT,
            RequestState.RETRY_WAIT,
        ):
            request.state = RequestState.CANCELLED

    def expire_overdue(self, now_monotonic_ms: int) -> list[str]:
        """deadline 过期处理；返回过期 request_id"""
        expired_ids: list[str] = []
        for request in self._requests.values():
            if request.state in (RequestState.QUEUED, RequestState.RETRY_WAIT, RequestState.LEASED) and (
                request.deadline_monotonic_ms <= now_monotonic_ms
            ):
                request.state = RequestState.EXPIRED
                expired_ids.append(request.request_id)
        return expired_ids

    def handle_failure(
        self, request_id: str, failure_kind: ProviderFailureKind, now_monotonic_ms: int
    ) -> tuple[RequestState, Optional[int]]:
        """
        失败处理（RULE-AI-053）

        返回 (新状态, retry_delay_ms|None)。
        仅 RETRYABLE_FAILURES 可重试；退避 250/1000ms + deterministic jitter 0..100ms。
        """
        request = self._requests[request_id]
        if failure_kind not in RETRYABLE_FAILURES or request.attempt >= request.max_attempts:
            request.state = RequestState.TERMINAL_FAILED
            return request.state, None

        backoff = RETRY_BACKOFF_MS[min(request.attempt - 1, len(RETRY_BACKOFF_MS) - 1)]
        jitter = compute_request_jitter_ms(request.request_id, request.attempt)
        delay = backoff + jitter
        if now_monotonic_ms + delay >= request.deadline_monotonic_ms:
            # deadline 不足不再重试
            request.state = RequestState.TERMINAL_FAILED
            return request.state, None

        request.attempt += 1
        request.state = RequestState.RETRY_WAIT
        return request.state, delay

    def counts(self) -> dict[str, int]:
        """metrics：queue depth 等（不含内容，DOC-AI-009 §9）"""
        result: dict[str, int] = {}
        for request in self._requests.values():
            result[request.state.value] = result.get(request.state.value, 0) + 1
        return result


def compute_request_jitter_ms(request_id: str, attempt: int) -> int:
    """deterministic request-hash jitter 0..100ms（RULE-AI-053）"""
    digest = hashlib.sha256(f"{request_id}:{attempt}".encode("utf-8")).digest()
    return digest[0] % 101

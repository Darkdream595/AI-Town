"""
测试 AI 请求并发、优先级与生命周期

覆盖 TEST-AI-033/034/035/036（DOC-AI-009 §11）
"""

import pytest

from src.ai import (
    AIRequest,
    ProviderFailureKind,
    QueueFullError,
    RequestQueue,
    RequestState,
    compute_request_jitter_ms,
)

from ai_helpers import ULID_A, ULID_B, ULID_C


def _request(
    request_id: str,
    priority_class: int = 4,
    accepted_sequence: int = 1,
    deadline_ms: int = 100000,
    deadline_game_time=None,
    resident_id: str = ULID_A,
) -> AIRequest:
    return AIRequest(
        request_id=request_id,
        logical_request_id=request_id,
        resident_id=resident_id,
        job_id=request_id,
        priority_class=priority_class,
        accepted_sequence=accepted_sequence,
        observed_revision=84,
        context_hash="sha256:abc",
        deadline_monotonic_ms=deadline_ms,
        deadline_game_time=deadline_game_time,
    )


class TestConcurrencyBounds:
    """TEST-AI-033：concurrency=2/pending=64"""

    def test_max_in_flight_two(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        queue.enqueue(_request(ULID_B, accepted_sequence=2))
        queue.enqueue(_request(ULID_C, accepted_sequence=3))
        first = queue.lease_next(now_monotonic_ms=0)
        queue.mark_in_flight(first.request_id)
        second = queue.lease_next(now_monotonic_ms=0)
        queue.mark_in_flight(second.request_id)
        # in-flight 已满，第三个无法 lease
        assert queue.lease_next(now_monotonic_ms=0) is None

    def test_pending_limit_64(self):
        queue = RequestQueue()
        for index in range(64):
            queue.enqueue(
                _request(f"{index:026d}".replace("0", "A", 1), accepted_sequence=index)
            )
        with pytest.raises(QueueFullError):
            queue.enqueue(_request(ULID_A, accepted_sequence=999))

    def test_overload_backpressure_not_expansion(self):
        # 4× overload 触发 backpressure 而非扩大并发
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        queue.enqueue(_request(ULID_B, accepted_sequence=2))
        queue.enqueue(_request(ULID_C, accepted_sequence=3))
        queue.lease_next(now_monotonic_ms=0)
        queue.lease_next(now_monotonic_ms=0)
        assert queue._max_in_flight == 2
        assert queue.lease_next(now_monotonic_ms=0) is None


class TestOrderingStability:
    """TEST-AI-034：stable priority/deadline ordering"""

    def test_priority_class_first(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, priority_class=4, accepted_sequence=1))
        queue.enqueue(_request(ULID_B, priority_class=1, accepted_sequence=2))
        leased = queue.lease_next(now_monotonic_ms=0)
        assert leased.request_id == ULID_B

    def test_deadline_game_time_second(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, priority_class=4, accepted_sequence=1, deadline_game_time=3000))
        queue.enqueue(_request(ULID_B, priority_class=4, accepted_sequence=2, deadline_game_time=2000))
        leased = queue.lease_next(now_monotonic_ms=0)
        assert leased.request_id == ULID_B

    def test_null_deadline_as_infinity(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, priority_class=4, accepted_sequence=1, deadline_game_time=None))
        queue.enqueue(_request(ULID_B, priority_class=4, accepted_sequence=2, deadline_game_time=9999))
        leased = queue.lease_next(now_monotonic_ms=0)
        assert leased.request_id == ULID_B

    def test_sequence_tiebreak(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, priority_class=4, accepted_sequence=2))
        queue.enqueue(_request(ULID_B, priority_class=4, accepted_sequence=1))
        leased = queue.lease_next(now_monotonic_ms=0)
        assert leased.request_id == ULID_B

    def test_ordering_deterministic_across_insertion_orders(self):
        def lease_order(sequences):
            queue = RequestQueue()
            for seq, rid in sequences:
                queue.enqueue(_request(rid, accepted_sequence=seq))
            order = []
            while True:
                leased = queue.lease_next(now_monotonic_ms=0)
                if leased is None:
                    break
                order.append(leased.request_id)
                queue.mark_succeeded(leased.request_id)
            return order

        forward = lease_order([(1, ULID_A), (2, ULID_B), (3, ULID_C)])
        reverse = lease_order([(3, ULID_C), (2, ULID_B), (1, ULID_A)])
        assert forward == reverse


class TestCancelLatePause:
    """TEST-AI-035：cancel/late/pause lifecycle"""

    def test_cancel_queued_request(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        queue.cancel(ULID_A)
        assert queue.lease_next(now_monotonic_ms=0) is None

    def test_expire_overdue(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1, deadline_ms=500))
        expired = queue.expire_overdue(now_monotonic_ms=600)
        assert expired == [ULID_A]
        assert queue.lease_next(now_monotonic_ms=600) is None

    def test_in_flight_not_expired_by_queue(self):
        # 已发出的网络请求由 adapter 处理取消，queue 不直接置 expired
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1, deadline_ms=500))
        leased = queue.lease_next(now_monotonic_ms=0)
        queue.mark_in_flight(leased.request_id)
        expired = queue.expire_overdue(now_monotonic_ms=600)
        assert expired == []


class TestRetryPolicy:
    """TEST-AI-036：retry classes/backoff/exhaustion"""

    def test_retryable_failure_requeues(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        queue.mark_in_flight(ULID_A)
        state, delay = queue.handle_failure(
            ULID_A, ProviderFailureKind.RATE_LIMITED, now_monotonic_ms=0
        )
        assert state == RequestState.RETRY_WAIT
        assert 250 <= delay <= 350  # backoff 250 + jitter 0..100

    def test_non_retryable_failure_terminal(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        state, delay = queue.handle_failure(
            ULID_A, ProviderFailureKind.INVALID_JSON, now_monotonic_ms=0
        )
        assert state == RequestState.TERMINAL_FAILED
        assert delay is None

    def test_max_attempts_exhaustion(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1))
        state, _ = queue.handle_failure(ULID_A, ProviderFailureKind.CONNECT_TIMEOUT, 0)
        assert state == RequestState.RETRY_WAIT
        # 第二次失败达到 max_attempts=2
        state, delay = queue.handle_failure(ULID_A, ProviderFailureKind.CONNECT_TIMEOUT, 0)
        assert state == RequestState.TERMINAL_FAILED
        assert delay is None

    def test_deadline_too_short_no_retry(self):
        queue = RequestQueue()
        queue.enqueue(_request(ULID_A, accepted_sequence=1, deadline_ms=100))
        state, delay = queue.handle_failure(
            ULID_A, ProviderFailureKind.RATE_LIMITED, now_monotonic_ms=0
        )
        assert state == RequestState.TERMINAL_FAILED
        assert delay is None

    def test_jitter_deterministic(self):
        assert compute_request_jitter_ms(ULID_A, 1) == compute_request_jitter_ms(ULID_A, 1)
        assert 0 <= compute_request_jitter_ms(ULID_A, 1) <= 100

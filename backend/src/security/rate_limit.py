"""
速率与尺寸限制（DOC-BACKEND-008 RULE-BACKEND-047/048）

- token bucket 按 (session_id, route_class) 计；超限返回 retry_after_ms
- 限制器内部故障 fail closed 到保守全局限额，不放开为无限
- 尺寸限制为常量：REST body ≤ 65536、WS 帧 ≤ 32768、JSON 深度 ≤ 32、出站块 ≤ 262144
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

MAX_BODY_BYTES = 65536
MAX_WS_FRAME_BYTES = 32768
MAX_JSON_DEPTH = 32
MAX_SNAPSHOT_CHUNK_BYTES = 262144

#: route_class → (容量, 每秒补充)；REST 类按分钟换算
ROUTE_CLASS_LIMITS: Dict[str, Tuple[float, float]] = {
    "secret": (5.0, 5.0 / 60.0),
    "destructive": (5.0, 5.0 / 60.0),
    "world-admin": (30.0, 30.0 / 60.0),
    "save": (12.0, 12.0 / 60.0),
    "ticket": (10.0, 10.0 / 60.0),
    "diagnostics": (2.0, 2.0 / 60.0),
    "settings": (30.0, 30.0 / 60.0),
    "session": (10.0, 10.0 / 60.0),
    "health": (120.0, 120.0 / 60.0),
    "ws_command": (40.0, 20.0),       # 20/s burst 40
    "ws_ack": (10.0, 10.0),           # ack/heartbeat_ack 10/s
}

#: fail closed 保守全局限额
_FALLBACK_LIMIT = (5.0, 5.0 / 60.0)


class RateLimiter:
    def __init__(self, monotonic_ms: Callable[[], int],
                 limits: Optional[Dict[str, Tuple[float, float]]] = None) -> None:
        self._clock = monotonic_ms
        self._limits = dict(limits or ROUTE_CLASS_LIMITS)
        self._buckets: Dict[Tuple[str, str], list] = {}

    def _bucket(self, session_id: str, route_class: str) -> list:
        key = (session_id, route_class)
        bucket = self._buckets.get(key)
        if bucket is None:
            capacity, refill = self._limits.get(route_class, _FALLBACK_LIMIT)
            bucket = [capacity, self._clock()]
            self._buckets[key] = bucket
        return bucket

    def check(self, session_id: str, route_class: str) -> Optional[int]:
        """允许返回 None；拒绝返回 retry_after_ms（≥1）"""
        try:
            capacity, refill = self._limits.get(route_class, _FALLBACK_LIMIT)
            bucket = self._bucket(session_id, route_class)
            now = self._clock()
            elapsed_s = max(0, now - bucket[1]) / 1000.0
            bucket[0] = min(capacity, bucket[0] + elapsed_s * refill)
            bucket[1] = now
            if bucket[0] >= 1.0:
                bucket[0] -= 1.0
                return None
            deficit = 1.0 - bucket[0]
            return max(1, int(deficit / refill * 1000.0) + 1)
        except Exception:
            # fail closed：按保守限额再试一次；仍异常则拒绝 1000ms
            try:
                bucket = self._bucket(session_id, "__fallback__")
                if bucket[0] >= 1.0:
                    bucket[0] -= 1.0
                    return None
            except Exception:
                pass
            return 1000

    def reset(self, session_id: str) -> None:
        for key in [key for key in self._buckets if key[0] == session_id]:
            del self._buckets[key]


def json_depth(value: object, _depth: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return _depth + 1
        return max(json_depth(item, _depth + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return _depth + 1
        return max(json_depth(item, _depth + 1) for item in value)
    return _depth + 1

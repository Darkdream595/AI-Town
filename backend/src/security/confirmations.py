"""
破坏性操作 Confirmation Token（DOC-BACKEND-004 RULE-BACKEND-023）

- 服务端颁发一次性确认凭据；绑定 (session_id, action)，TTL 有限
- 缺失/过期/重放/跨 action 一律 BACKEND_CONFIRMATION_REQUIRED
- 日志只记 challenge_id，Token 值本身 never-log
"""

from __future__ import annotations

import secrets as _secrets
from dataclasses import dataclass
from typing import Callable, Dict, Optional

CONFIRMATION_TTL_MS = 60_000


@dataclass
class ConfirmationChallenge:
    challenge_id: str
    session_id: str
    action: str
    token: str
    issued_at_ms: int
    used: bool = False


class ConfirmationService:
    def __init__(self, id_factory: Callable[[], str],
                 monotonic_ms: Callable[[], int],
                 ttl_ms: int = CONFIRMATION_TTL_MS) -> None:
        self._id_factory = id_factory
        self._clock = monotonic_ms
        self._ttl_ms = ttl_ms
        self._challenges: Dict[str, ConfirmationChallenge] = {}

    def issue(self, session_id: str, action: str) -> ConfirmationChallenge:
        challenge = ConfirmationChallenge(
            challenge_id=self._id_factory(),
            session_id=session_id,
            action=action,
            token=_secrets.token_urlsafe(32),
            issued_at_ms=self._clock(),
        )
        self._challenges[challenge.challenge_id] = challenge
        return challenge

    def consume(self, session_id: str, action: str, token: Optional[str]) -> None:
        """校验并消耗；任何失败抛 code=BACKEND_CONFIRMATION_REQUIRED"""
        from ..foundation.errors import ApiError  # 延迟导入避免环

        if not token:
            raise ApiError("BACKEND_CONFIRMATION_REQUIRED",
                           {"action": action, "reason_code": "token_missing"})
        match: Optional[ConfirmationChallenge] = None
        for challenge in self._challenges.values():
            if challenge.token == token:
                match = challenge
                break
        if match is None:
            raise ApiError("BACKEND_CONFIRMATION_REQUIRED",
                           {"action": action, "reason_code": "token_unknown"})
        if match.used:
            raise ApiError("BACKEND_CONFIRMATION_REQUIRED",
                           {"action": action, "reason_code": "token_replayed"})
        if self._clock() - match.issued_at_ms > self._ttl_ms:
            raise ApiError("BACKEND_CONFIRMATION_REQUIRED",
                           {"action": action, "reason_code": "token_expired"})
        if match.session_id != session_id or match.action != action:
            raise ApiError("BACKEND_CONFIRMATION_REQUIRED",
                           {"action": action, "reason_code": "token_scope_mismatch"})
        match.used = True

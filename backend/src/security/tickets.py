"""
WebSocket Ticket（DOC-BACKEND-003 RULE-BACKEND-012）

- 256-bit CSPRNG 值；绑定 (session_id, world_id)；TTL 30000 real ms（monotonic）
- 单次使用：mark_used 后重放一律拒绝；日志只记 SHA-256 前 12 hex 指纹
"""

from __future__ import annotations

import hashlib
import secrets as _secrets
from dataclasses import dataclass
from typing import Callable, Dict, Optional

TICKET_TTL_MS = 30_000


def ticket_fingerprint(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()[:12]


@dataclass
class WsTicket:
    ticket: str
    session_id: str
    world_id: str
    issued_at_ms: int
    used: bool = False

    @property
    def fingerprint(self) -> str:
        return ticket_fingerprint(self.ticket)


class WsTicketService:
    def __init__(self, monotonic_ms: Callable[[], int],
                 ttl_ms: int = TICKET_TTL_MS) -> None:
        self._clock = monotonic_ms
        self._ttl_ms = ttl_ms
        self._tickets: Dict[str, WsTicket] = {}

    def issue(self, session_id: str, world_id: str) -> WsTicket:
        ticket = WsTicket(
            ticket=_secrets.token_urlsafe(32),  # 256-bit
            session_id=session_id,
            world_id=world_id,
            issued_at_ms=self._clock(),
        )
        self._tickets[ticket.ticket] = ticket
        return ticket

    def validate_and_consume(self, ticket_value: Optional[str],
                             session_id: str, world_id: str) -> WsTicket:
        """握手检查：有效性 → 绑定 → 单次；失败抛 code=BACKEND_TICKET_INVALID"""
        from ..foundation.errors import ApiError

        ticket = self._tickets.get(ticket_value or "")
        if ticket is None:
            raise ApiError("BACKEND_TICKET_INVALID", {"reason_code": "ticket_unknown"})
        if ticket.used:
            raise ApiError("BACKEND_TICKET_INVALID", {"reason_code": "ticket_replayed"})
        if self._clock() - ticket.issued_at_ms > self._ttl_ms:
            raise ApiError("BACKEND_TICKET_INVALID", {"reason_code": "ticket_expired"})
        if ticket.session_id != session_id or ticket.world_id != world_id:
            raise ApiError("BACKEND_TICKET_INVALID",
                           {"reason_code": "ticket_scope_mismatch"})
        ticket.used = True
        return ticket

    def drop_world(self, world_id: str) -> None:
        for key in [k for k, t in self._tickets.items() if t.world_id == world_id]:
            del self._tickets[key]

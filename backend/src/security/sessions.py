"""
本地 Session 服务（DOC-BACKEND-008）

- RULE-BACKEND-042：ai_town_session Cookie，HttpOnly + SameSite=Strict + Path=/；
  值为进程内 256-bit Secret 签名的不透明令牌；Secret 仅存内存，重启全部失效
- 空闲 60 real 分钟过期（monotonic RealTime 计量）
- CSRF 双提交：Session 建立时同时颁发非 HttpOnly 的 ai_town_csrf Cookie
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

SESSION_COOKIE_NAME = "ai_town_session"
CSRF_COOKIE_NAME = "ai_town_csrf"
CSRF_HEADER_NAME = "x-ai-town-csrf"
SESSION_IDLE_TIMEOUT_MS = 60 * 60 * 1000  # 60 real 分钟
CSRF_ROTATION_MS = 30 * 60 * 1000

ROLE_STATES = frozenset({"observer", "player", "mayor", "admin"})

#: Role State 合法迁移（迁移条件由 PLAYER 域拥有，本表只做状态机约束）
ROLE_TRANSITIONS = frozenset({
    ("observer", "player"),
    ("player", "mayor"),
    ("mayor", "player"),
    ("player", "admin"),
    ("admin", "player"),
    ("player", "observer"),
})


class SessionError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class Session:
    session_id: str
    role_state: str = "observer"
    world_id: Optional[str] = None
    created_at_ms: int = 0
    last_seen_ms: int = 0
    csrf_issued_at_ms: int = 0
    csrf_token: str = ""

    def to_info(self, clock_ms: Callable[[], int]) -> dict:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "role_state": self.role_state,
            "world_id": self.world_id,
            "idle_remaining_ms": max(
                0, SESSION_IDLE_TIMEOUT_MS - (clock_ms() - self.last_seen_ms)),
            "csrf_rotation_due_ms": max(
                0, CSRF_ROTATION_MS - (clock_ms() - self.csrf_issued_at_ms)),
        }


class SessionService:
    """进程内 Session 签发/验签；重启即全失效（Secret 每次构造重新生成）"""

    def __init__(self, id_factory: Callable[[], str],
                 monotonic_ms: Callable[[], int],
                 secret: Optional[bytes] = None) -> None:
        self._id_factory = id_factory
        self._clock = monotonic_ms
        self._secret = secret if secret is not None else _secrets.token_bytes(32)
        self._sessions: Dict[str, Session] = {}

    # -- 签发 ----------------------------------------------------------------

    def _sign(self, session_id: str) -> str:
        return hmac.new(self._secret, session_id.encode("ascii"),
                        hashlib.sha256).hexdigest()

    def create(self, world_id: Optional[str] = None) -> tuple:
        """返回 (session, cookie_value, csrf_token)；Role 初始 observer"""
        session = Session(
            session_id=self._id_factory(),
            world_id=world_id,
            created_at_ms=self._clock(),
            last_seen_ms=self._clock(),
            csrf_issued_at_ms=self._clock(),
            csrf_token=_secrets.token_urlsafe(32),
        )
        self._sessions[session.session_id] = session
        cookie_value = f"{session.session_id}.{self._sign(session.session_id)}"
        return session, cookie_value, session.csrf_token

    # -- 验签 ----------------------------------------------------------------

    def verify(self, cookie_value: Optional[str], touch: bool = True) -> Session:
        if not cookie_value or "." not in cookie_value:
            raise SessionError("BACKEND_SESSION_INVALID", "missing cookie")
        session_id, signature = cookie_value.rsplit(".", 1)
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("BACKEND_SESSION_INVALID", "unknown session")
        expected = self._sign(session_id)
        if not hmac.compare_digest(signature, expected):
            raise SessionError("BACKEND_SESSION_INVALID", "bad signature")
        now = self._clock()
        if now - session.last_seen_ms > SESSION_IDLE_TIMEOUT_MS:
            raise SessionError("BACKEND_SESSION_INVALID", "idle expired")
        if touch:
            session.last_seen_ms = now
        return session

    def verify_csrf(self, session: Session, header_value: Optional[str]) -> None:
        if not header_value or not hmac.compare_digest(header_value,
                                                       session.csrf_token):
            raise SessionError("BACKEND_CSRF_REJECTED", "csrf mismatch")

    # -- Role State -----------------------------------------------------------

    def transition_role(self, session: Session, target: str) -> Session:
        if target not in ROLE_STATES:
            raise SessionError("BACKEND_SCHEMA_INVALID", f"role {target}")
        if (session.role_state, target) not in ROLE_TRANSITIONS:
            raise SessionError("BACKEND_CONFLICT_STATE",
                               f"{session.role_state} → {target}")
        session.role_state = target
        return session

    def bind_world(self, session: Session, world_id: Optional[str]) -> None:
        session.world_id = world_id

    def drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError("BACKEND_SESSION_INVALID", "unknown session")
        return session

    def active_count(self) -> int:
        return len(self._sessions)

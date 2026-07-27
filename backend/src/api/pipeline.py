"""
REST 统一验证管线（DOC-BACKEND-004 RULE-BACKEND-022 / DOC-BACKEND-008 §5 位点表）

验证顺序（任一步失败立即返回对应错误码，且不执行任何后续副作用）：
transport → Origin/Host → 速率限制 → body 大小与 JSON 解析 →
Session/CSRF（按 auth 列）→ 权限 → schema_version 支持性 → payload Schema → 用例前置条件

- RULE-BACKEND-043：Host 必须 loopback:{port}；非 GET 必须 Origin 命中 Allowlist
- RULE-BACKEND-044：CORS 全拒绝（无 Access-Control-Allow-*；OPTIONS 一律 403）
- RULE-BACKEND-045：CSRF 双提交；anonymous_bootstrap 只豁免 Session 验签与 CSRF 两位点
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation.errors import ApiError
from ..security import sessions as session_mod
from ..security.permissions import enforce_rest_role
from ..security.rate_limit import MAX_BODY_BYTES, MAX_JSON_DEPTH, RateLimiter, json_depth
from ..security.sessions import Session, SessionError, SessionService
from .catalog import AUTH_BOOTSTRAP, AUTH_SESSION, AUTH_SESSION_CSRF, RouteEntry
from .schemas import SchemaRegistry

LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


@dataclass
class RestRequest:
    method: str
    path: str
    headers: Dict[str, str]
    body: bytes
    client: str = "127.0.0.1"

    def header(self, name: str) -> Optional[str]:
        return self.headers.get(name.lower())


@dataclass
class RestContext:
    request: RestRequest
    route: RouteEntry
    session: Optional[Session] = None
    body_json: Optional[dict] = None
    side_effect_free: bool = True  # 验证期探针：通过全部位点前不得产生副作用


class Pipeline:
    """验证位点执行器（框架无关；FastAPI adapter 只做 transport 翻译）"""

    def __init__(self, bind_port: int,
                 session_service: SessionService,
                 rate_limiter: RateLimiter,
                 schemas: SchemaRegistry,
                 audit_hook: Optional[Callable[[dict], None]] = None) -> None:
        self._port = bind_port
        self._sessions = session_service
        self._rate = rate_limiter
        self._schemas = schemas
        self._audit = audit_hook or (lambda _entry: None)

    # -- 位点 1/2：Origin/Host ------------------------------------------------

    def check_origin_host(self, request: RestRequest) -> None:
        host = request.header("host") or ""
        host_name, _, host_port = host.rpartition(":")
        if host_name not in LOOPBACK_HOSTS or host_port != str(self._port):
            self._audit({"checkpoint": "host", "result": "rejected",
                         "origin_allowed": False, "port": host_port})
            raise ApiError("BACKEND_ORIGIN_REJECTED",
                           {"reason_code": "host_not_loopback"})
        if request.method != "GET":
            origin = request.header("origin")
            if not origin:
                self._audit({"checkpoint": "origin", "result": "rejected",
                             "origin_allowed": False})
                raise ApiError("BACKEND_ORIGIN_REJECTED",
                               {"reason_code": "origin_missing"})
            origin_host = origin.replace("http://", "").replace("https://", "")
            origin_name, _, origin_port = origin_host.rpartition(":")
            if origin_name not in LOOPBACK_HOSTS or origin_port != str(self._port):
                self._audit({"checkpoint": "origin", "result": "rejected",
                             "origin_allowed": False})
                raise ApiError("BACKEND_ORIGIN_REJECTED",
                               {"reason_code": "origin_not_allowed"})

    def check_cors_preflight(self, request: RestRequest) -> None:
        """OPTIONS preflight 一律 403；响应绝不携带 Access-Control-Allow-*"""
        if request.method == "OPTIONS":
            self._audit({"checkpoint": "cors_preflight", "result": "rejected"})
            raise ApiError("BACKEND_ORIGIN_REJECTED", {"reason_code": "cors_preflight"})

    # -- 位点 3：速率限制 --------------------------------------------------------

    def check_rate(self, session_key: str, route: RouteEntry) -> None:
        retry_after = self._rate.check(session_key, route.route_class)
        if retry_after is not None:
            raise ApiError("BACKEND_RATE_LIMITED",
                           {"route_class": route.route_class},
                           retry_after_ms=retry_after)

    # -- 位点 4：body 大小与 JSON ------------------------------------------------

    def parse_body(self, request: RestRequest) -> Optional[dict]:
        if not request.body:
            return None
        if len(request.body) > MAX_BODY_BYTES:
            raise ApiError("BACKEND_BODY_TOO_LARGE",
                           {"reason_code": "rest_body_too_large"})
        try:
            parsed = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "json_parse_failed"}) from None
        if json_depth(parsed) > MAX_JSON_DEPTH:
            raise ApiError("BACKEND_BODY_TOO_LARGE",
                           {"reason_code": "json_depth_exceeded"})
        return parsed

    # -- 位点 5：Session/CSRF -----------------------------------------------------

    def check_session(self, request: RestRequest, route: RouteEntry) -> Optional[Session]:
        if route.auth == AUTH_BOOTSTRAP:
            return None
        try:
            session = self._sessions.verify(request.header("x-session"))
        except SessionError as exc:
            raise ApiError(exc.code) from None
        if route.auth == AUTH_SESSION_CSRF:
            try:
                self._sessions.verify_csrf(
                    session, request.header(session_mod.CSRF_HEADER_NAME))
            except SessionError as exc:
                self._audit({"checkpoint": "csrf", "result": "rejected",
                             "session_id": session.session_id})
                raise ApiError(exc.code) from None
        return session

    # -- 位点 6/7/8：权限 / schema_version / payload ----------------------------

    def check_permission(self, session: Optional[Session], route: RouteEntry) -> None:
        role = session.role_state if session else "observer"
        enforce_rest_role(role, route.route_class)

    def validate_payload(self, route: RouteEntry, body: Optional[dict]) -> Optional[dict]:
        """schema_version 支持性 → payload Schema；低版本 active → 校验后 upcast"""
        if route.request_schema is None:
            return None
        if body is None:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "body_missing"})
        version = body.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ApiError("BACKEND_SCHEMA_INVALID",
                           {"reason_code": "schema_version_invalid"})
        latest = self._schemas.latest_version(route.request_schema)
        if version > latest:
            raise ApiError("BACKEND_PROTOCOL_MISMATCH",
                           {"expected": latest, "received": version})
        # 按请求声明版本校验，再 upcast 到当前版本进入用例
        self._schemas.validate_wire(route.request_schema, version, body)
        if version < latest:
            body = self._schemas.upcast_chain(route.request_schema, version, body)
        return body

    # -- 全序执行 -----------------------------------------------------------------

    def run(self, request: RestRequest, route: RouteEntry,
            session_key_hint: Optional[str] = None) -> RestContext:
        """按 RULE-BACKEND-022 顺序执行全部位点；任一步失败无副作用"""
        self.check_cors_preflight(request)          # 1 transport 即拦截 preflight
        self.check_origin_host(request)             # 2 Origin/Host
        session_key = session_key_hint or request.header("x-session") or request.client
        self.check_rate(session_key, route)         # 3 速率限制
        body_json = self.parse_body(request)        # 4 body/JSON
        session = self.check_session(request, route)  # 5 Session/CSRF（按 auth 列）
        self.check_permission(session, route)       # 6 权限
        body = self.validate_payload(route, body_json)  # 7/8 schema_version + Schema
        return RestContext(request=request, route=route, session=session,
                           body_json=body)

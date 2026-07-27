"""
FastAPI 适配层（DOC-BACKEND-001 §5 ASGI 分层 / DOC-BACKEND-004 §5）

- 只做 transport 翻译：验证位点全部在 api.pipeline（框架无关）
- 同源静态托管：白名单扩展名、拒绝路径穿越与目录列举；/api/、/ws/ 下未注册
  路径一律 404，不做 SPA 回退；其余路径回退 index.html
- CORS 全拒绝：不加任何 Access-Control-Allow-* 头；安全响应头基线全量携带
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from ..foundation.errors import (
    INTERNAL_INVARIANT_ENVELOPE,
    ApiError,
    error_envelope,
    spec_of,
)
from .catalog import find_route
from .pipeline import Pipeline, RestRequest
from .rest import RestServices, dispatch
from .ws import WsGateway

STATIC_EXTENSIONS = frozenset({
    ".html", ".js", ".css", ".json", ".png", ".jpg", ".jpeg", ".webp",
    ".svg", ".ico", ".woff", ".woff2", ".ttf", ".map", ".txt",
})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


@dataclass
class AppContext:
    pipeline: Pipeline
    services: RestServices
    gateway: WsGateway
    static_dir: Optional[str]
    bind_port: int


def _resolve_static(static_dir: str, url_path: str) -> Optional[str]:
    """路径穿越/符号链接防护：解析后必须仍在 static_dir 内，且扩展名白名单"""
    if ".." in url_path or url_path.startswith("/"):
        return None
    candidate = os.path.realpath(os.path.join(static_dir, url_path))
    root = os.path.realpath(static_dir)
    if not candidate.startswith(root + os.sep):
        return None
    if os.path.islink(candidate) or os.path.isdir(candidate):
        return None
    extension = os.path.splitext(candidate)[1].lower()
    if extension not in STATIC_EXTENSIONS:
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="AI Town Backend", version="0.1.0",
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        status = exc.spec.http_status or 500
        return JSONResponse(status_code=status, content=exc.to_envelope(),
                            headers=SECURITY_HEADERS)

    @app.exception_handler(Exception)
    async def unknown_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=INTERNAL_INVARIANT_ENVELOPE,
                            headers=SECURITY_HEADERS)

    async def handle_api(request: Request) -> Response:
        body = await request.body()
        rest_request = RestRequest(
            method=request.method,
            path=request.url.path,
            headers={
                "host": request.headers.get("host", ""),
                "origin": request.headers.get("origin"),
                "x-ai-town-csrf": request.headers.get("x-ai-town-csrf"),
                "x-session": request.cookies.get("ai_town_session"),
            },
            body=body,
            client=request.client.host if request.client else "127.0.0.1",
        )
        route = find_route(request.method, request.url.path)
        try:
            # preflight 拒绝先于路由匹配：任何 OPTIONS 一律 403，绝不 404 误导
            ctx.pipeline.check_cors_preflight(rest_request)
            if route is None:
                raise ApiError("BACKEND_NOT_FOUND", {"path": request.url.path})
            context = ctx.pipeline.run(rest_request, route)
            response = dispatch(context, ctx.services)
        except ApiError as exc:
            status = exc.spec.http_status or 500
            return JSONResponse(status_code=status, content=exc.to_envelope(),
                                headers=SECURITY_HEADERS)
        headers = dict(SECURITY_HEADERS)
        if request.method == "GET":
            headers["Cache-Control"] = "no-store"
        json_response = JSONResponse(status_code=response.status,
                                     content=response.envelope(), headers=headers)
        for name, value, http_only in response.cookies:
            json_response.set_cookie(
                name, value, httponly=http_only, samesite="strict", path="/")
        return json_response

    # -- 已登记 API 路由（catch-all 在 /api/ 与 /ws/ 下严格 404） -------------------
    for methods in (["GET"], ["POST"], ["PUT"], ["DELETE"], ["OPTIONS"]):
        app.add_api_route("/api/{full_path:path}", handle_api, methods=methods)

    # -- WebSocket ---------------------------------------------------------------
    @app.websocket("/ws/v1")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        session_cookie = websocket.cookies.get("ai_town_session")
        world_id = websocket.query_params.get("world_id", "")
        try:
            session = ctx.services.sessions.verify(session_cookie)
        except Exception:
            await websocket.close(code=4401)
            return

        class _Transport:
            async def send(self, frame: dict) -> None:
                await websocket.send_text(
                    json.dumps(frame, ensure_ascii=False, separators=(",", ":")))

            async def close(self, code: str) -> None:
                await websocket.close(code=4409)

        await websocket.accept()

        import asyncio

        class _SyncTransport:
            def send(self, frame: dict) -> None:
                asyncio.get_event_loop().create_task(transport.send(frame))

            def close(self, code: str) -> None:
                asyncio.get_event_loop().create_task(transport.close(code))

        transport = _Transport()
        channel = ctx.gateway.connect(_SyncTransport(), session.session_id, world_id)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    frame = json.loads(raw)
                except ValueError:
                    frame = None
                ctx.gateway.handle_frame(channel, frame)
        except WebSocketDisconnect:
            pass

    # -- 静态托管与 SPA 回退 --------------------------------------------------------
    @app.get("/{full_path:path}")
    async def static_or_spa(full_path: str) -> Response:
        if ".." in full_path:
            return JSONResponse(status_code=404,
                                content=error_envelope("BACKEND_NOT_FOUND",
                                                       {"path": full_path}),
                                headers=SECURITY_HEADERS)
        if full_path.startswith(("api/", "api", "ws/", "ws")):
            return JSONResponse(status_code=404,
                                content=error_envelope("BACKEND_NOT_FOUND",
                                                       {"path": full_path}),
                                headers=SECURITY_HEADERS)
        if ctx.static_dir and os.path.isdir(ctx.static_dir):
            candidate = _resolve_static(ctx.static_dir, full_path) if full_path else None
            if candidate is None and full_path:
                # 带扩展名的缺失资源 → 404；无扩展名路径 → SPA 前端路由回退
                if os.path.splitext(full_path)[1]:
                    return JSONResponse(status_code=404,
                                        content=error_envelope("BACKEND_NOT_FOUND",
                                                               {"path": full_path}),
                                        headers=SECURITY_HEADERS)
            target = candidate or _resolve_static(ctx.static_dir, "index.html")
            if target is not None:
                extension = os.path.splitext(target)[1].lower()
                with open(target, "rb") as handle:
                    content = handle.read()
                return Response(content=content,
                                media_type=CONTENT_TYPES.get(extension,
                                                             "application/octet-stream"),
                                headers=SECURITY_HEADERS)
        return JSONResponse(
            status_code=503,
            content=error_envelope("BACKEND_STORAGE_FAILURE",
                                   {"reason_code": "static_bundle_missing"}),
            headers=SECURITY_HEADERS)

    return app

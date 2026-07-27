"""
REST 用例层（DOC-BACKEND-004 §5 端点目录）

- 响应一律 Response Envelope：{schema_version, data}；GET 带 Cache-Control: no-store
- 破坏性操作必须携带服务端颁发的一次性 Confirmation Token
- REST 只承载管理与查询：不提供任何世界写旁路（游戏命令只走 WS command 帧）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation.errors import ApiError
from ..foundation.id_generator import is_valid_ulid
from ..orchestrator.jobs import JobRegistry
from ..orchestrator.runtime import ProcessRuntime
from ..orchestrator.worlds import WorldRegistry
from ..security.confirmations import ConfirmationService
from ..security.secrets import SECRET_KIND_DEEPSEEK, SecretService
from ..security.sessions import SessionService
from ..security.tickets import WsTicketService, ticket_fingerprint
from .catalog import DESTRUCTIVE_ACTIONS, RouteEntry, path_params
from .pipeline import RestContext

APP_VERSION = "0.1.0"
BUILD_FINGERPRINT = "dev-local"


@dataclass
class RestResponse:
    status: int
    data: dict
    cookies: List[Tuple[str, str, bool]] = field(default_factory=list)  # (name, value, httponly)

    def envelope(self) -> dict:
        return {"schema_version": 1, "data": self.data}


class SettingsService:
    """非敏感设置（内存 port；持久化由 persistence 阶段实现）"""

    DEFAULTS = {"language": "zh-CN", "simulation_speed": 1, "ui_scale": 1.0}

    def __init__(self) -> None:
        self._values = dict(self.DEFAULTS)

    def get(self) -> dict:
        return {"schema_version": 1, **self._values}

    def put(self, values: dict) -> dict:
        for key in values:
            if key == "schema_version":
                continue
            if key not in self.DEFAULTS:
                raise ApiError("BACKEND_SCHEMA_INVALID",
                               {"reason_code": f"settings_key_unknown:{key}"})
        self._values.update({k: v for k, v in values.items() if k != "schema_version"})
        return self.get()


class SaveSlotService:
    """存档槽（内存 port；DOC-RELEASE-004 的 SQLite/分支语义由 persistence 阶段实现）"""

    def __init__(self, id_factory: Callable[[], str],
                 utc_now: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self._utc_now = utc_now
        self._slots: Dict[str, Dict[str, dict]] = {}  # world_id → save_id → slot

    def list(self, world_id: str) -> List[dict]:
        return sorted(self._slots.get(world_id, {}).values(),
                      key=lambda slot: slot["save_id"])

    def write(self, world_id: str, name: str, revision: int,
              overwrite_save_id: Optional[str] = None) -> dict:
        slots = self._slots.setdefault(world_id, {})
        if overwrite_save_id is not None:
            slot = slots.get(overwrite_save_id)
            if slot is None:
                raise ApiError("BACKEND_NOT_FOUND", {"save_id": overwrite_save_id})
            slot.update({"name": name, "revision": revision,
                         "written_at": self._utc_now()})
            return slot
        save_id = self._id_factory()
        slot = {
            "schema_version": 1,
            "save_id": save_id,
            "world_id": world_id,
            "name": name,
            "kind": "manual",
            "revision": revision,
            "written_at": self._utc_now(),
        }
        slots[save_id] = slot
        return slot

    def get(self, world_id: str, save_id: str) -> dict:
        slot = self._slots.get(world_id, {}).get(save_id)
        if slot is None:
            raise ApiError("BACKEND_NOT_FOUND", {"save_id": save_id})
        return slot


@dataclass
class RestServices:
    sessions: SessionService
    tickets: WsTicketService
    confirmations: ConfirmationService
    secrets: SecretService
    worlds: WorldRegistry
    saves: SaveSlotService
    settings: SettingsService
    jobs: JobRegistry
    runtime: ProcessRuntime
    utc_now: Callable[[], str]
    monotonic_ms: Callable[[], int]
    metrics_snapshot: Callable[[], dict]
    diagnostics_builder: Optional[Callable[[dict], str]] = None  # → result_ref


def _require_world_write(services: RestServices) -> None:
    """Recovery Barrier 期间 world-admin 写端点一律 CONFLICT_STATE；
    Drain 期间一律 BACKEND_SHUTDOWN（RULE-BACKEND-065 步骤 2）"""
    if services.runtime.state == "draining":
        raise ApiError("BACKEND_SHUTDOWN", {"reason_code": "draining"})
    if services.runtime.recovery_barrier_active:
        raise ApiError("BACKEND_CONFLICT_STATE",
                       {"reason_code": "recovery_barrier_active"})


def _consume_confirmation(ctx: RestContext, services: RestServices,
                          action: str) -> None:
    token = (ctx.body_json or {}).get("confirmation_token")
    services.confirmations.consume(ctx.session.session_id, action, token)


def dispatch(ctx: RestContext, services: RestServices) -> RestResponse:
    """用例分发：此处之前不得产生任何副作用（RULE-BACKEND-022）"""
    route = ctx.route
    path = route.path
    params = path_params(path, ctx.request.path)
    method = route.method
    body = ctx.body_json or {}

    # -- health / meta ----------------------------------------------------------
    if path == "/api/v1/health":
        return RestResponse(200, services.runtime.health())
    if path == "/api/v1/meta":
        return RestResponse(200, {
            "schema_version": 1,
            "app_version": APP_VERSION,
            "protocol_version": 1,
            "build_fingerprint": BUILD_FINGERPRINT,
        })

    # -- session ---------------------------------------------------------------
    if path == "/api/v1/session":
        session, cookie, csrf = services.sessions.create()
        return RestResponse(200, session.to_info(services.monotonic_ms), cookies=[
            ("ai_town_session", cookie, True),
            ("ai_town_csrf", csrf, False),
        ])

    # -- ws tickets -------------------------------------------------------------
    if path == "/api/v1/ws-tickets":
        world_id = body.get("world_id")
        if not world_id:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "world_id_required"})
        services.worlds.get(world_id)  # 404 if unknown
        ticket = services.tickets.issue(ctx.session.session_id, world_id)
        return RestResponse(200, {
            "schema_version": 1,
            "ticket": ticket.ticket,
            "world_id": world_id,
            "expires_at_utc": services.utc_now(),
            "single_use": True,
        })

    # -- worlds -----------------------------------------------------------------
    if path == "/api/v1/worlds" and method == "GET":
        worlds = services.worlds.list()
        return RestResponse(200, {
            "schema_version": 1,
            "worlds": [record.to_summary() for record in worlds[:100]],
            "total": len(worlds),
        })
    if path == "/api/v1/worlds" and method == "POST":
        _require_world_write(services)
        command_id = body.get("command_id")
        if not command_id or not is_valid_ulid(command_id):
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "command_id_invalid"})
        record = services.worlds.create(
            command_id, body.get("name", "新世界"),
            body.get("seed_hex", ""), body.get("template_id", "template.default"))
        return RestResponse(200, record.to_summary())
    if path == "/api/v1/worlds/{world_id}" and method == "GET":
        record = services.worlds.get(params["world_id"])
        detail = record.to_summary()
        detail.update({"seed_hex": record.seed_hex, "read_only": record.read_only,
                       "overloaded": record.overloaded})
        return RestResponse(200, detail)
    if path == "/api/v1/worlds/{world_id}/open":
        _require_world_write(services)
        record = services.worlds.open(params["world_id"])
        services.runtime.open_world_id = record.world_id
        services.runtime.current_revision = record.current_revision
        return RestResponse(200, record.to_runtime_state())
    if path == "/api/v1/worlds/{world_id}/close":
        services.worlds.begin_drain(params["world_id"])
        record = services.worlds.finish_drain(params["world_id"])
        services.runtime.open_world_id = None
        return RestResponse(200, record.to_runtime_state())
    if path == "/api/v1/worlds/{world_id}" and method == "DELETE":
        _require_world_write(services)
        _consume_confirmation(ctx, services, "world.delete")
        record = services.worlds.delete(params["world_id"])
        return RestResponse(200, {"schema_version": 1,
                                  "world_id": record.world_id, "deleted": True})

    # -- saves ------------------------------------------------------------------
    if path == "/api/v1/worlds/{world_id}/saves" and method == "GET":
        services.worlds.get(params["world_id"])
        return RestResponse(200, {"schema_version": 1,
                                  "saves": services.saves.list(params["world_id"])})
    if path == "/api/v1/worlds/{world_id}/saves" and method == "POST":
        record = services.worlds.get(params["world_id"])
        overwrite_id = body.get("overwrite_save_id")
        if overwrite_id is not None:
            _consume_confirmation(ctx, services, "save.overwrite")
        slot = services.saves.write(params["world_id"], body.get("name", "手动存档"),
                                    record.current_revision,
                                    overwrite_save_id=overwrite_id)
        return RestResponse(200, slot)
    if path == "/api/v1/worlds/{world_id}/saves/{save_id}/load":
        _require_world_write(services)
        services.saves.get(params["world_id"], params["save_id"])
        record = services.worlds.open(params["world_id"])
        return RestResponse(200, record.to_runtime_state())

    # -- settings ---------------------------------------------------------------
    if path == "/api/v1/settings" and method == "GET":
        return RestResponse(200, services.settings.get())
    if path == "/api/v1/settings" and method == "PUT":
        return RestResponse(200, services.settings.put(body))

    # -- secrets ----------------------------------------------------------------
    if path == "/api/v1/secrets/deepseek-api-key" and method == "PUT":
        status = services.secrets.set_secret(SECRET_KIND_DEEPSEEK,
                                             body.get("api_key", ""))
        return RestResponse(200, status)
    if path == "/api/v1/secrets/deepseek-api-key/status":
        return RestResponse(200, services.secrets.status(SECRET_KIND_DEEPSEEK))
    if path == "/api/v1/secrets/deepseek-api-key" and method == "DELETE":
        _consume_confirmation(ctx, services, "secret.delete")
        return RestResponse(200, services.secrets.delete_secret(SECRET_KIND_DEEPSEEK))

    # -- confirmations -----------------------------------------------------------
    if path == "/api/v1/confirmations":
        action = body.get("action")
        if not action:
            raise ApiError("BACKEND_SCHEMA_INVALID", {"reason_code": "action_required"})
        challenge = services.confirmations.issue(ctx.session.session_id, action)
        return RestResponse(200, {
            "schema_version": 1,
            "challenge_id": challenge.challenge_id,
            "confirmation_token": challenge.token,
            "expires_in_ms": 60_000,
        })

    # -- diagnostics -------------------------------------------------------------
    if path == "/api/v1/diagnostics/package":
        job = services.jobs.create("diagnostics_package")
        services.jobs.start(job.job_id)
        try:
            builder = services.diagnostics_builder or (lambda _req: "diagpkg.local")
            result_ref = builder(body)
            services.jobs.succeed(job.job_id, result_ref)
        except Exception:
            services.jobs.fail(job.job_id, "package_build_failed")
        return RestResponse(202, services.jobs.get(job.job_id).to_resource())
    if path == "/api/v1/diagnostics/jobs/{job_id}":
        return RestResponse(200, services.jobs.get(params["job_id"]).to_resource())
    if path == "/api/v1/diagnostics/metrics":
        return RestResponse(200, services.metrics_snapshot())

    raise ApiError("BACKEND_NOT_FOUND", {"path": path})

"""
进程装配与启动恢复序列（DES-BACKEND-001；DOC-BACKEND-001 §5/§6）

启动顺序：
  config load（含 Secret Provider 装配）
  → persistence open + migration + integrity（DOC-RELEASE-001..003，可注入）
  → snapshot read + event log replay（可注入）
  → core invariant recovery audit（可注入）
  → revision projection rebuild（可注入）
  → lift Recovery Barrier
  → ASGI bind 127.0.0.1:port
  → scheduler / AI workers / outbox senders 启动（可注入）

任一恢复步骤失败：进程保持 Recovery Barrier（hold_barrier），
只暴露健康与诊断端点，写端点 BACKEND_CONFLICT_STATE——不退出、不半恢复。
"""

from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..api.app import AppContext
from ..api.pipeline import Pipeline
from ..api.rest import RestServices, SaveSlotService, SettingsService
from ..api.schemas import SchemaRegistry
from ..api.wire import register_wire_contracts
from ..api.ws import WsGateway
from ..diagnostics.logging import StructuredLogger
from ..diagnostics.metrics import MetricsRegistry
from ..foundation.errors import ApiError
from ..orchestrator.commands import CommandRegistry
from ..orchestrator.events import EventRegistry
from ..orchestrator.jobs import JobRegistry
from ..orchestrator.outbox import CommittedEventLog
from ..orchestrator.queues import BoundedQueue
from ..orchestrator.runtime import ProcessRuntime
from ..orchestrator.worlds import WorldRegistry
from ..security.confirmations import ConfirmationService
from ..security.rate_limit import RateLimiter
from ..security.redaction import RedactionFilter
from ..security.secrets import (
    ChainedSecretStore,
    MemorySecretStore,
    SecretService,
    SecretStoreBackend,
)
from ..security.sessions import SessionService
from ..security.tickets import WsTicketService
from .config import BackendConfig


def _system_monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def _system_utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _uuid_id() -> str:
    return uuid.uuid4().hex


@dataclass
class StartupHooks:
    """恢复序列可注入步骤；默认全部为无副作用 no-op（内存运行）。

    persistence 阶段（DOC-RELEASE-001..003）以真实实现替换：
    open_persistence / replay_event_log / recovery_audit / rebuild_projection。
    """
    secret_backends: Optional[List[SecretStoreBackend]] = None
    open_persistence: Optional[Callable[["AssembledRuntime"], None]] = None
    replay_event_log: Optional[Callable[["AssembledRuntime"], int]] = None
    recovery_audit: Optional[Callable[["AssembledRuntime"], None]] = None
    rebuild_projection: Optional[Callable[["AssembledRuntime"], None]] = None
    start_workers: Optional[Callable[["AssembledRuntime"], None]] = None


@dataclass
class AssembledRuntime:
    """装配产物：AppContext 之外暴露测试/运维需要的内部句柄"""
    config: BackendConfig
    app_context: AppContext
    runtime: ProcessRuntime
    sessions: SessionService
    schemas: SchemaRegistry
    commands: CommandRegistry
    events: EventRegistry
    worlds: WorldRegistry
    jobs: JobRegistry
    secrets: SecretService
    metrics: MetricsRegistry
    logger: StructuredLogger
    event_logs: Dict[str, CommittedEventLog] = field(default_factory=dict)
    recovery_failures: List[str] = field(default_factory=list)

    @property
    def services(self) -> RestServices:
        return self.app_context.services

    @property
    def gateway(self) -> WsGateway:
        return self.app_context.gateway


def assemble(config: BackendConfig,
             hooks: Optional[StartupHooks] = None,
             monotonic_ms: Callable[[], int] = _system_monotonic_ms,
             utc_now: Callable[[], str] = _system_utc_now,
             id_factory: Callable[[], str] = _uuid_id,
             ) -> AssembledRuntime:
    """进程部件装配（DES-BACKEND-001 config load 步）"""
    config.validate()
    hooks = hooks or StartupHooks()

    schemas = SchemaRegistry()
    commands = CommandRegistry()
    events = EventRegistry()
    register_wire_contracts(schemas, commands, events)
    gaps = schemas.audit_integrity()
    if gaps:
        raise ApiError("BACKEND_INTERNAL_INVARIANT",
                       {"reason_code": f"schema_registry_gaps:{gaps[0]}"})

    redaction = RedactionFilter()
    logger = StructuredLogger("backend", None, utc_now,
                              redact=redaction.redact)  # 默认内存环；文件由启动器装配
    metrics = MetricsRegistry()

    backends = hooks.secret_backends
    store = ChainedSecretStore(backends) if backends else MemorySecretStore()
    secrets = SecretService(store, redaction, id_factory, utc_now=utc_now)

    sessions = SessionService(id_factory, monotonic_ms)
    rate = RateLimiter(monotonic_ms)
    tickets = WsTicketService(monotonic_ms)
    confirmations = ConfirmationService(id_factory, monotonic_ms)
    worlds = WorldRegistry(id_factory, utc_now)
    jobs = JobRegistry(id_factory)
    runtime = ProcessRuntime(monotonic_ms)

    pipeline = Pipeline(config.bind_port, sessions, rate, schemas,
                        audit_hook=lambda entry: logger.log(
                            "info", "pipeline_audit", ids=entry))

    services = RestServices(
        sessions=sessions, tickets=tickets, confirmations=confirmations,
        secrets=secrets, worlds=worlds, saves=SaveSlotService(id_factory, utc_now),
        settings=SettingsService(), jobs=jobs, runtime=runtime,
        utc_now=utc_now, monotonic_ms=monotonic_ms,
        metrics_snapshot=lambda: metrics.snapshot(),
    )

    event_logs: Dict[str, CommittedEventLog] = {}
    queues: Dict[str, BoundedQueue] = {}

    def queue_for(world_id: str) -> BoundedQueue:
        queue = queues.get(world_id)
        if queue is None:
            queue = BoundedQueue(f"world_command:{world_id}",
                                 config.world_command_queue_capacity,
                                 "reject", monotonic_ms)
            queues[world_id] = queue
        return queue

    gateway = WsGateway(
        sessions=sessions, tickets=tickets, commands=commands, events=events,
        rate_limiter=rate, id_factory=id_factory, monotonic_ms=monotonic_ms,
        event_log_provider=lambda world_id: event_logs.setdefault(
            world_id, CommittedEventLog()),
        command_executor=lambda envelope, revision: {
            "schema_version": 1, "command_id": envelope.get("command_id"),
            "result": "committed", "reason_code": None, "event_ids": [],
            "revision": revision},
        queue_provider=queue_for,
        snapshot_provider=lambda world_id: {"schema_version": 1,
                                            "revision": 0, "state": {}},
        outbox_capacity=config.ws_outbox_capacity,
        accepting_commands=lambda: runtime.state != "draining",
    )

    app_context = AppContext(pipeline=pipeline, services=services,
                             gateway=gateway, static_dir=config.static_dir,
                             bind_port=config.bind_port)
    return AssembledRuntime(
        config=config, app_context=app_context, runtime=runtime,
        sessions=sessions, schemas=schemas, commands=commands, events=events,
        worlds=worlds, jobs=jobs, secrets=secrets, metrics=metrics,
        logger=logger, event_logs=event_logs)


# ---------------------------------------------------------------------------
# 恢复序列（lift/hold Recovery Barrier）
# ---------------------------------------------------------------------------

RECOVERY_STEPS = (
    "open_persistence",
    "replay_event_log",
    "recovery_audit",
    "rebuild_projection",
)


def run_recovery_sequence(assembled: AssembledRuntime,
                          hooks: Optional[StartupHooks] = None) -> bool:
    """按 DES-BACKEND-001 顺序执行恢复；全部成功 → lift Barrier。

    任一步失败：hold_barrier（进程保持恢复屏障，只暴露健康/诊断），
    返回 False。不产生半事务——每步要么完整成功要么整体标记失败。
    """
    hooks = hooks or StartupHooks()
    runtime = assembled.runtime
    runtime.enter_recovering()

    for step_name in RECOVERY_STEPS:
        step = getattr(hooks, step_name, None)
        if step is None:
            continue
        try:
            result = step(assembled)
            if step_name == "replay_event_log" and isinstance(result, int):
                runtime.current_revision = result
        except Exception as exc:  # noqa: BLE001 — 恢复失败一律 hold，不区分类型
            reason = getattr(exc, "code", None) or f"{step_name}_failed"
            runtime.hold_barrier(str(reason))
            assembled.recovery_failures.append(f"{step_name}:{exc!r}")
            return False

    runtime.lift_barrier()
    workers = hooks.start_workers
    if workers is not None:
        try:
            workers(assembled)
        except Exception as exc:  # noqa: BLE001
            runtime.hold_barrier(f"start_workers_failed")
            assembled.recovery_failures.append(f"start_workers:{exc!r}")
            return False
    return True

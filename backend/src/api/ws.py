"""
WebSocket 生命周期与实时同步（DOC-BACKEND-003 RULE-BACKEND-012..018）

- 握手检查顺序固定：Origin/Host（transport 层）→ Ticket 有效性 → Session 状态
- 同 Session 同 world 最多一条 live 连接；新连接 hello 后旧连接 BACKEND_WS_SUPERSEDED
- 心跳：服务器每 20000ms 发 heartbeat，Client 5000ms 内回 ack；连续 2 次未回关闭
- 事件按 Revision 严格递增推送；ack 释放已确认缓冲；重连 catch-up / Snapshot fallback
- 未知 frame_type / 非法 JSON / 版本不匹配 → error(BACKEND_PROTOCOL_MISMATCH) + close

传输无关：transport 只需 send(frame) / close(code)；FastAPI 绑定在 app.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

from ..foundation.errors import ApiError
from ..orchestrator.commands import CommandRegistry, validate_envelope
from ..orchestrator.events import EventRegistry
from ..orchestrator.outbox import (
    CATCH_UP_MAX_EVENTS,
    CommittedEventLog,
    SessionOutbox,
    SnapshotRequired,
)
from ..orchestrator.queues import BoundedQueue, put_world_command
from ..security.permissions import enforce_role
from ..security.rate_limit import RateLimiter
from ..security.sessions import SessionService
from ..security.tickets import WsTicketService

PROTOCOL_VERSION = 1
HEARTBEAT_INTERVAL_MS = 20_000
HEARTBEAT_ACK_TIMEOUT_MS = 5_000
HEARTBEAT_MAX_MISSES = 2
MAX_SNAPSHOT_CHUNK_BYTES = 262144

FRAME_TYPES = frozenset({
    "hello", "hello_ack", "heartbeat", "heartbeat_ack", "command",
    "command_receipt", "event", "snapshot_begin", "snapshot_chunk",
    "snapshot_end", "ack", "error",
})

CHANNEL_STATES = frozenset(
    {"authenticating", "catching_up", "snapshotting", "live", "lagging", "closed"})


class WsTransport(Protocol):
    def send(self, frame: dict) -> None: ...
    def close(self, code: str) -> None: ...


@dataclass
class Channel:
    channel_id: str
    session_id: str
    world_id: str
    transport: WsTransport
    outbox: SessionOutbox
    state: str = "authenticating"
    last_heartbeat_sent_ms: int = -1
    last_heartbeat_id: Optional[str] = None
    heartbeat_misses: int = 0
    last_client_activity_ms: int = 0


class WsGateway:
    def __init__(self,
                 sessions: SessionService,
                 tickets: WsTicketService,
                 commands: CommandRegistry,
                 events: EventRegistry,
                 rate_limiter: RateLimiter,
                 id_factory: Callable[[], str],
                 monotonic_ms: Callable[[], int],
                 event_log_provider: Callable[[str], CommittedEventLog],
                 command_executor: Callable[[dict, int], dict],
                 queue_provider: Callable[[str], BoundedQueue],
                 snapshot_provider: Callable[[str], dict],
                 outbox_capacity: int = 512,
                 on_close: Optional[Callable[[Channel, str], None]] = None,
                 accepting_commands: Optional[Callable[[], bool]] = None) -> None:
        self._sessions = sessions
        self._tickets = tickets
        self._commands = commands
        self._events = events
        self._rate = rate_limiter
        self._id_factory = id_factory
        self._clock = monotonic_ms
        self._event_log = event_log_provider
        self._execute = command_executor
        self._queue = queue_provider
        self._snapshot = snapshot_provider
        self._outbox_capacity = outbox_capacity
        self._on_close = on_close or (lambda _c, _r: None)
        self._accepting = accepting_commands or (lambda: True)
        self._channels: Dict[str, Channel] = {}
        self._live_index: Dict[tuple, str] = {}  # (session_id, world_id) → channel_id

    # -- 帧构造 ----------------------------------------------------------------

    def _frame(self, frame_type: str, payload: dict) -> dict:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "frame_type": frame_type,
            "frame_id": self._id_factory(),
            "payload": payload,
        }

    def _send_error(self, channel: Channel, code: str,
                    details: Optional[dict] = None, close: bool = False) -> None:
        error = ApiError(code, details)
        channel.transport.send(self._frame("error", error.to_error_object()))
        if close:
            self._close(channel, code)

    def _close(self, channel: Channel, code: str) -> None:
        if channel.state == "closed":
            return
        channel.state = "closed"
        self._channels.pop(channel.channel_id, None)
        if self._live_index.get((channel.session_id, channel.world_id)) == channel.channel_id:
            del self._live_index[(channel.session_id, channel.world_id)]
        channel.transport.close(code)
        self._on_close(channel, code)

    # -- 握手 ----------------------------------------------------------------

    def connect(self, transport: WsTransport, session_id: str, world_id: str) -> Channel:
        outbox = SessionOutbox(session_id, world_id, self._events,
                               capacity=self._outbox_capacity)
        channel = Channel(
            channel_id=self._id_factory(),
            session_id=session_id, world_id=world_id,
            transport=transport, outbox=outbox,
            last_client_activity_ms=self._clock(),
        )
        self._channels[channel.channel_id] = channel
        return channel

    def handle_hello(self, channel: Channel, payload: dict) -> None:
        try:
            if payload.get("client_protocol_version") != PROTOCOL_VERSION:
                raise ApiError("BACKEND_PROTOCOL_MISMATCH", {
                    "expected": PROTOCOL_VERSION,
                    "received": payload.get("client_protocol_version")})
            # Ticket 有效性 → 绑定 → 单次
            self._tickets.validate_and_consume(
                payload.get("ticket"), channel.session_id, channel.world_id)
            last_acked = payload.get("last_acked_revision", 0)
            if not isinstance(last_acked, int) or last_acked < 0:
                raise ApiError("BACKEND_SCHEMA_INVALID",
                               {"reason_code": "last_acked_invalid"})
            current = self._event_log(channel.world_id).current_revision()
            if last_acked > current:
                # 声称进度超过服务器：视为损坏/跨世界错连 → Snapshot 重建
                raise SnapshotRequired("client_ahead_of_server")
        except SnapshotRequired:
            self._enter_snapshot(channel)
            return
        except ApiError as exc:
            close = exc.spec.ws_behavior in ("error_frame_close", "close")
            self._send_error(channel, exc.code, exc.details,
                             close=True if exc.code in (
                                 "BACKEND_PROTOCOL_MISMATCH",
                                 "BACKEND_TICKET_INVALID") else close)
            return

        # supersede：同 Session 同 world 已有 live 连接 → 旧连接关闭 + 游标移交
        old_id = self._live_index.get((channel.session_id, channel.world_id))
        if old_id is not None and old_id != channel.channel_id:
            old = self._channels.get(old_id)
            if old is not None:
                old.outbox.handover_to(channel.outbox)
                self._send_error(old, "BACKEND_WS_SUPERSEDED", close=True)
        self._live_index[(channel.session_id, channel.world_id)] = channel.channel_id

        # resume 判定
        if last_acked == current:
            resume_mode = "live"
            channel.state = "live"
        else:
            try:
                channel.state = "catching_up"
                channel.outbox.catch_up(self._event_log(channel.world_id), last_acked)
                resume_mode = "catch_up"
                channel.state = "live"
            except SnapshotRequired:
                self._enter_snapshot(channel)
                return
        channel.transport.send(self._frame("hello_ack", {
            "schema_version": 1,
            "world_id": channel.world_id,
            "current_revision": current,
            "resume_mode": resume_mode,
        }))
        if resume_mode == "catch_up":
            self._flush(channel)

    def _enter_snapshot(self, channel: Channel) -> None:
        """Snapshot fallback：分块发送锚定 Revision 的权威投影"""
        channel.state = "snapshotting"
        self._live_index[(channel.session_id, channel.world_id)] = channel.channel_id
        snapshot = self._snapshot(channel.world_id)
        revision = snapshot.get("revision", 0)
        import json as _json
        blob = _json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        channel.transport.send(self._frame("snapshot_begin", {
            "schema_version": 1, "world_id": channel.world_id,
            "revision": revision,
            "total_bytes": len(blob),
        }))
        for offset in range(0, len(blob), MAX_SNAPSHOT_CHUNK_BYTES):
            chunk = blob[offset: offset + MAX_SNAPSHOT_CHUNK_BYTES]
            channel.transport.send(self._frame("snapshot_chunk", {
                "schema_version": 1,
                "offset": offset,
                "data_b64": __import__("base64").b64encode(chunk).decode("ascii"),
            }))
        channel.transport.send(self._frame("snapshot_end", {
            "schema_version": 1, "revision": revision}))
        channel.outbox.state.last_acked_revision = revision
        channel.outbox.state.sent_revision = revision
        channel.outbox.state.max_pushed_revision = revision
        channel.outbox.resync_required = False
        channel.state = "live"

    # -- 帧分发 ----------------------------------------------------------------

    def handle_frame(self, channel: Channel, raw: object) -> None:
        if channel.state == "closed":
            return
        channel.last_client_activity_ms = self._clock()
        if not isinstance(raw, dict):
            self._send_error(channel, "BACKEND_PROTOCOL_MISMATCH",
                             {"reason_code": "frame_not_json"}, close=True)
            return
        if raw.get("protocol_version") != PROTOCOL_VERSION:
            self._send_error(channel, "BACKEND_PROTOCOL_MISMATCH", {
                "expected": PROTOCOL_VERSION,
                "received": raw.get("protocol_version")}, close=True)
            return
        frame_type = raw.get("frame_type")
        if frame_type not in FRAME_TYPES:
            self._send_error(channel, "BACKEND_PROTOCOL_MISMATCH",
                             {"reason_code": "frame_type_unknown"}, close=True)
            return
        payload = raw.get("payload") or {}
        if frame_type == "hello":
            self.handle_hello(channel, payload)
        elif frame_type == "heartbeat_ack":
            self._handle_heartbeat_ack(channel, payload)
        elif frame_type == "ack":
            self._handle_ack(channel, payload)
        elif frame_type == "command":
            self._handle_command(channel, payload)

    # -- 心跳 ----------------------------------------------------------------

    def tick_heartbeat(self) -> None:
        """周期驱动（Outbound Sender）：到点发心跳；连续 miss 超限关闭"""
        now = self._clock()
        for channel in list(self._channels.values()):
            if channel.state != "live":
                continue
            if channel.last_heartbeat_id is not None:
                # 有心跳在途：超时未 ack 记 miss，超限关闭
                if now - channel.last_heartbeat_sent_ms > (
                        HEARTBEAT_INTERVAL_MS + HEARTBEAT_ACK_TIMEOUT_MS):
                    channel.heartbeat_misses += 1
                    if channel.heartbeat_misses >= HEARTBEAT_MAX_MISSES:
                        self._send_error(channel, "BACKEND_SESSION_INVALID",
                                         {"reason_code": "heartbeat_timeout"},
                                         close=True)
                        continue
                    channel.last_heartbeat_id = None
            if channel.last_heartbeat_id is None and (
                    channel.last_heartbeat_sent_ms < 0
                    or now - channel.last_heartbeat_sent_ms >= HEARTBEAT_INTERVAL_MS):
                heartbeat_id = self._id_factory()
                channel.last_heartbeat_id = heartbeat_id
                channel.last_heartbeat_sent_ms = now
                channel.transport.send(self._frame("heartbeat", {
                    "schema_version": 1, "heartbeat_id": heartbeat_id}))

    def _handle_heartbeat_ack(self, channel: Channel, payload: dict) -> None:
        if payload.get("heartbeat_id") != channel.last_heartbeat_id:
            return  # 迟到/伪造 ack：不重置 miss，也不报错（幂等丢弃）
        channel.heartbeat_misses = 0
        channel.last_heartbeat_id = None

    # -- ack -----------------------------------------------------------------

    def _handle_ack(self, channel: Channel, payload: dict) -> None:
        last_acked = payload.get("last_acked_revision", 0)
        if isinstance(last_acked, int) and last_acked >= 0:
            channel.outbox.ack(last_acked)

    # -- command --------------------------------------------------------------

    def _handle_command(self, channel: Channel, envelope: dict) -> None:
        try:
            if not self._accepting():
                raise ApiError("BACKEND_SHUTDOWN",
                               {"reason_code": "draining"})
            retry = self._rate.check(channel.session_id, "ws_command")
            if retry is not None:
                raise ApiError("BACKEND_RATE_LIMITED", retry_after_ms=retry)
            session = self._sessions.get(channel.session_id)
            validate_envelope(self._commands, envelope)
            enforce_role(session.role_state, envelope["type"])
            if envelope["world_id"] != channel.world_id:
                raise ApiError("BACKEND_FORBIDDEN",
                               {"reason_code": "world_mismatch"})
            put_world_command(self._queue(channel.world_id), envelope)
            receipt = self._execute(envelope, 0)
        except ApiError as exc:
            if "command_id" in (envelope or {}):
                from ..orchestrator.commands import make_receipt
                receipt = make_receipt(envelope["command_id"], "rejected",
                                       error=exc.to_error_object())
            else:
                self._send_error(channel, exc.code, exc.details)
                return
        channel.transport.send(self._frame("command_receipt", receipt))

    # -- 事件发布（已提交事件 → Outbox → 帧） -------------------------------------

    def publish_events(self, world_id: str, events: List[dict]) -> None:
        """只从已提交事务的 Outbox 读出后发布（RULE-BACKEND-035）"""
        for channel in list(self._channels.values()):
            if channel.world_id != world_id or channel.state != "live":
                continue
            for event in events:
                channel.outbox.push(event)
            if channel.outbox.resync_required:
                self._enter_snapshot(channel)
            else:
                self._flush(channel)

    def _flush(self, channel: Channel) -> None:
        for event in channel.outbox.pending_frames():
            channel.transport.send(self._frame("event", event))
        channel.outbox.mark_sent()

    # -- 关闭 ----------------------------------------------------------------

    def notify_all(self, code: str = "BACKEND_SHUTDOWN") -> None:
        """Drain 预告帧（RULE-BACKEND-065 步骤 1）：只通知不关闭"""
        for channel in list(self._channels.values()):
            if channel.state != "closed":
                self._send_error(channel, code, close=False)

    def close_all(self, code: str = "BACKEND_SHUTDOWN") -> None:
        for channel in list(self._channels.values()):
            self._send_error(channel, code, close=True)

    def channel_count(self) -> int:
        return len(self._channels)

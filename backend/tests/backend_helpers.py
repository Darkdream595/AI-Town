"""后端测试共享夹具（Phase 15 TEST-BACKEND-001..046）

- 假 monotonic 时钟 / 确定性 id / 合法 ULID 工厂
- make_assembly：经 bootstrap.assemble 全装配 + 恢复序列完成（ready 态）
- make_client：同源 TestClient（Host 头满足 pipeline 位点 2）
- session/csrf/role 快捷助手；FakeTransport 收集 WS 出站帧

注意：所有测试绝不触碰真实 Windows 凭据管理器/DPAPI——Secret 一律 Memory 后端。
"""
from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starlette.testclient import TestClient

from src.api.app import create_app
from src.bootstrap.config import BackendConfig
from src.bootstrap.startup import (
    AssembledRuntime,
    StartupHooks,
    assemble,
    run_recovery_sequence,
)
from src.orchestrator.outbox import CommittedEventLog

PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"
ORIGIN = {"origin": BASE_URL}

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class FakeClock:
    def __init__(self, start_ms: int = 1_000_000) -> None:
        self.now_ms = start_ms

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> int:
        self.now_ms += ms
        return self.now_ms


def make_id_factory(prefix: str = "id"):
    counter = itertools.count(1)
    return lambda: f"{prefix}-{next(counter):06d}"


def make_ulid_factory():
    """合法 ULID（26 字符 Crockford Base32），确定性递增"""
    counter = itertools.count(1)

    def next_ulid() -> str:
        value = next(counter)
        chars = []
        for _ in range(26):
            chars.append(_ULID_ALPHABET[value % 32])
            value //= 32
        return "".join(reversed(chars))

    return next_ulid


def make_utc_factory(start: str = "2026-01-01T00:00:00Z"):
    return lambda: start


def make_assembly(
        hooks: StartupHooks | None = None,
        static_dir: str | None = None,
        run_recovery: bool = True,
        config: BackendConfig | None = None,
        ) -> AssembledRuntime:
    """全装配；默认完成恢复序列（ready）。时钟/id 全部确定性。"""
    clock = FakeClock()
    assembly = assemble(
        config or BackendConfig(static_dir=static_dir),
        hooks=hooks,
        monotonic_ms=clock,
        utc_now=make_utc_factory(),
        id_factory=make_id_factory())
    assembly.test_clock = clock  # type: ignore[attr-defined]
    if run_recovery:
        assert run_recovery_sequence(assembly, hooks), assembly.recovery_failures
    return assembly


def make_client(assembly: AssembledRuntime) -> TestClient:
    return TestClient(create_app(assembly.app_context), base_url=BASE_URL)


def create_session(client: TestClient) -> tuple:
    """POST /api/v1/session → (session_info, csrf_token)"""
    response = client.post("/api/v1/session", json={"schema_version": 1},
                           headers=ORIGIN)
    assert response.status_code == 200, response.text
    info = response.json()["data"]
    csrf = client.cookies.get("ai_town_csrf")
    assert csrf
    return info, csrf


def csrf_headers(csrf: str) -> dict:
    return {**ORIGIN, "x-ai-town-csrf": csrf}


def promote(assembly: AssembledRuntime, session_id: str, role: str = "player"):
    session = assembly.sessions.get(session_id)
    # observer→player→mayor→… 逐步走合法迁移链
    chain = {"player": ["player"], "mayor": ["player", "mayor"],
             "admin": ["player", "admin"]}[role]
    for step in chain:
        assembly.sessions.transition_role(session, step)
    return session


def create_world(client: TestClient, csrf: str, ulid: str,
                 name: str = "溪口镇", seed: str = "0123456789abcdef") -> str:
    response = client.post("/api/v1/worlds", json={
        "schema_version": 1, "command_id": ulid, "name": name,
        "seed_hex": seed}, headers=csrf_headers(csrf))
    assert response.status_code == 200, response.text
    return response.json()["data"]["world_id"]


# ---------------------------------------------------------------------------
# WS 助手
# ---------------------------------------------------------------------------

class FakeTransport:
    """收集出站帧；closed_code 记录关闭码"""

    def __init__(self) -> None:
        self.frames: list = []
        self.closed_code: str | None = None

    def send(self, frame: dict) -> None:
        self.frames.append(frame)

    def close(self, code: str) -> None:
        self.closed_code = code

    def by_type(self, frame_type: str) -> list:
        return [f for f in self.frames if f.get("frame_type") == frame_type]

    @property
    def last(self) -> dict | None:
        return self.frames[-1] if self.frames else None


def ws_connect(assembly: AssembledRuntime, session_id: str, world_id: str,
               last_acked_revision: int = 0):
    """connect + ticket + hello → (channel, transport)；默认进入 live"""
    ticket = assembly.services.tickets.issue(session_id, world_id)
    transport = FakeTransport()
    channel = assembly.gateway.connect(transport, session_id, world_id)
    assembly.gateway.handle_hello(channel, {
        "client_protocol_version": 1,
        "ticket": ticket.ticket,
        "last_acked_revision": last_acked_revision,
    })
    return channel, transport


def append_committed(assembly: AssembledRuntime, world_id: str,
                     events: list) -> None:
    log = assembly.event_logs.setdefault(world_id, CommittedEventLog())
    log.append_commit(events)


def make_event(assembly: AssembledRuntime, world_id: str, revision: int,
               event_type: str = "world.weather.changed",
               payload: dict | None = None, event_id: str | None = None,
               causation_id: str = "cmd-test",
               correlation_id: str = "cmd-test",
               render: dict | None = None,
               game_time: int = 0) -> dict:
    from src.orchestrator.events import build_event
    return build_event(
        assembly.events,
        make_id_factory("evt") if event_id is None else (lambda: event_id),
        world_id=world_id, revision=revision, event_type=event_type,
        game_time=game_time, causation_id=causation_id,
        correlation_id=correlation_id,
        payload=payload or {"schema_version": 1, "weather": "rain",
                            "started_at_tick": 1},
        render=render)


def command_envelope(ulid: str, world_id: str,
                     command_type: str = "system.world.pause",
                     expected_revision: int | None = None,
                     payload: dict | None = None) -> dict:
    """Command Envelope：恰好六字段（DES-BACKEND-005），多一少一即拒绝"""
    return {
        "protocol_version": 1,
        "command_id": ulid,
        "world_id": world_id,
        "type": command_type,
        "expected_revision": expected_revision,
        "payload": payload or {"schema_version": 1, "paused": True},
    }


def frame_bytes(frame: dict) -> int:
    return len(json.dumps(frame, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))

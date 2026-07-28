"""RELEASE 测试共享夹具（tests 目录无 __init__，直接 import）"""
from __future__ import annotations

import itertools
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.persistence import database, paths, schema, worlds  # noqa: E402

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_COUNTER = itertools.count(1)
_UTC_BASE = None


def _next_ulid() -> str:
    value = next(_ULID_COUNTER)
    chars = []
    for _ in range(26):
        chars.append(_ULID_ALPHABET[value % 32])
        value //= 32
    return "".join(reversed(chars))


def make_ulid_factory():
    """合法 ULID 工厂；全局共享计数保证跨工厂唯一（event_id 唯一约束）"""
    return _next_ulid


_UTC_COUNTER = itertools.count(0)


def make_utc_factory(start: str = "2026-07-28T10:00:00.000Z",
                     step_seconds: int = 61):
    """确定性递增 UTC（RFC 3339 毫秒 Z）；全局共享计数保证时序先后稳定"""
    import datetime as dt
    base = dt.datetime.strptime(start, "%Y-%m-%dT%H:%M:%S.%fZ")

    def utc_now() -> str:
        moment = base + dt.timedelta(seconds=step_seconds * next(_UTC_COUNTER))
        return moment.strftime("%Y-%m-%dT%H:%M:%S.") + \
            "%03dZ" % (moment.microsecond // 1000)

    return utc_now


def make_command_ids():
    counter = itertools.count(1)
    return lambda: "cmd-%06d" % next(counter)


@pytest.fixture()
def layout(tmp_path):
    ly = paths.UserDataLayout(tmp_path / "AI-Town 数据")
    ly.ensure_root_layout()
    return ly


@pytest.fixture()
def app_conn(layout):
    conn = database.open_write_connection(layout.app_db_path)
    schema.create_app_database(conn)
    yield conn
    database.close_write_connection(layout.app_db_path, conn)


@pytest.fixture()
def registry(layout, app_conn):
    return worlds.WorldRegistry(
        layout, app_conn, utc_now=make_utc_factory(),
        new_ulid=make_ulid_factory(), seed_fn=lambda: "cd" * 16)


@pytest.fixture()
def created_world(registry):
    return registry.create_world(command_id="cmd-create-1",
                                 display_name="测试世界 一")


@pytest.fixture()
def world_conn(layout, created_world):
    world_id = created_world["world_id"]
    conn = database.open_write_connection(layout.world_db_path(world_id))
    yield conn
    database.close_write_connection(layout.world_db_path(world_id), conn)


_TICK_ULIDS = _next_ulid


def append_tick(conn, world_id, *, revision=None, game_time=1,
                event_type="test.tick", payload=None, ulid=None,
                utc="2026-07-28T10:00:00.000Z"):
    """追加一条合法 tick 事件并同步 world_meta（同事务）"""
    from src.persistence import event_log
    revision = revision or event_log.tip_revision(conn) + 1
    event_log.append_event(conn, {
        "revision": revision, "event_id": ulid or _TICK_ULIDS(),
        "world_id": world_id, "event_type": event_type,
        "event_schema_version": 1, "game_time": game_time,
        "causation_id": None, "correlation_id": None,
        "payload_json": json.dumps(payload or {}, sort_keys=True),
        "render_json": None, "created_at": utc})
    conn.execute(
        "UPDATE world_meta SET revision=?, game_time=? WHERE id=1",
        (revision, game_time))
    conn.commit()
    return revision


def force_rmtree(path):
    for p in Path(path).rglob("*"):
        if p.is_file():
            try:
                import os
                os.chmod(p, 0o666)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)

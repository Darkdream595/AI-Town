"""
数据库 Schema（DOC-RELEASE-001 §5.2/5.3、DOC-RELEASE-003 §5.1/5.2、DOC-RELEASE-004 §5.1）

- DES-RELEASE-001：app.sqlite3 核心表
- DES-RELEASE-003：schema_migrations 版本记录表（两库同构）
- DES-RELEASE-005：event_log 追加式物理 Schema + 拒写 trigger
- DES-RELEASE-006：snapshot_meta
- DES-RELEASE-008：save_records

首版 schema_version：app=1，world=1；min_supported=1。
"""

from __future__ import annotations

import sqlite3

APP_SCHEMA_CURRENT = 1
APP_SCHEMA_MIN_SUPPORTED = 1
WORLD_SCHEMA_CURRENT = 1
WORLD_SCHEMA_MIN_SUPPORTED = 1

# ---------------------------------------------------------------------------
# app.sqlite3
# ---------------------------------------------------------------------------

APP_DDL = """
CREATE TABLE IF NOT EXISTS world_registry (
  world_id        TEXT PRIMARY KEY,
  display_name    TEXT NOT NULL,
  seed_hex        TEXT NOT NULL,
  schema_version  INTEGER NOT NULL,
  created_at      TEXT NOT NULL,
  last_opened_at  TEXT,
  deleted_at      TEXT,
  origin_world_id TEXT
);
CREATE TABLE IF NOT EXISTS app_settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS release_stamp (
  package_version TEXT NOT NULL,
  build_id        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  to_version    INTEGER PRIMARY KEY,
  step_id       TEXT NOT NULL,
  applied_at    TEXT NOT NULL,
  duration_ms   INTEGER NOT NULL,
  backup_file   TEXT NOT NULL,
  backup_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
  command_id   TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  result_json  TEXT NOT NULL,
  created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id   TEXT PRIMARY KEY,
  at         TEXT NOT NULL,
  action     TEXT NOT NULL,
  world_id   TEXT,
  detail_json TEXT
);
"""

# ---------------------------------------------------------------------------
# world.sqlite3
# ---------------------------------------------------------------------------

WORLD_DDL = """
CREATE TABLE IF NOT EXISTS world_meta (
  id                     INTEGER PRIMARY KEY CHECK (id = 1),
  world_id               TEXT NOT NULL,
  timeline_id            TEXT NOT NULL,
  parent_timeline_id     TEXT,
  branch_source_revision INTEGER,
  revision               INTEGER NOT NULL,
  game_time              INTEGER NOT NULL,
  schema_version         INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_log (
  revision       INTEGER PRIMARY KEY,
  event_id       TEXT NOT NULL UNIQUE,
  world_id       TEXT NOT NULL,
  event_type     TEXT NOT NULL,
  event_schema_version INTEGER NOT NULL,
  game_time      INTEGER NOT NULL,
  causation_id   TEXT,
  correlation_id TEXT,
  payload_json   TEXT NOT NULL,
  render_json    TEXT,
  created_at     TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS event_log_no_update BEFORE UPDATE ON event_log
BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS event_log_no_delete BEFORE DELETE ON event_log
BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END;
CREATE TABLE IF NOT EXISTS snapshot_meta (
  snapshot_id     TEXT PRIMARY KEY,
  anchor_revision INTEGER NOT NULL UNIQUE,
  file_name       TEXT NOT NULL,
  file_sha256     TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  trigger         TEXT NOT NULL
    CHECK (trigger IN ('clean_shutdown','revision_interval','manual_save','auto_save'))
);
CREATE TABLE IF NOT EXISTS save_records (
  save_id         TEXT PRIMARY KEY,
  kind            TEXT NOT NULL CHECK (kind IN ('auto','manual')),
  slot            TEXT CHECK (slot IN ('slot_1','slot_2','slot_3')),
  timeline_id     TEXT NOT NULL,
  anchor_revision INTEGER NOT NULL,
  snapshot_id     TEXT NOT NULL REFERENCES snapshot_meta(snapshot_id),
  game_time       INTEGER NOT NULL,
  display_label   TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  trashed_at      TEXT
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
  command_id   TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  result_json  TEXT NOT NULL,
  created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  to_version    INTEGER PRIMARY KEY,
  step_id       TEXT NOT NULL,
  applied_at    TEXT NOT NULL,
  duration_ms   INTEGER NOT NULL,
  backup_file   TEXT NOT NULL,
  backup_sha256 TEXT NOT NULL
);
"""


def create_app_database(conn: sqlite3.Connection) -> None:
    """首启按当前 schema 创建 app.sqlite3（DOC-RELEASE-001 §6）"""
    conn.executescript(APP_DDL)
    conn.execute(
        "INSERT OR IGNORE INTO app_meta(key, value) VALUES ('schema_version', ?)",
        (str(APP_SCHEMA_CURRENT),))
    conn.commit()


def create_world_database(conn: sqlite3.Connection, world_id: str,
                          timeline_id: str) -> None:
    """创建世界库并写入初始 world_meta（revision 从 0 起，事件从 1 起）"""
    conn.executescript(WORLD_DDL)
    conn.execute(
        "INSERT OR IGNORE INTO world_meta"
        "(id, world_id, timeline_id, parent_timeline_id,"
        " branch_source_revision, revision, game_time, schema_version)"
        " VALUES (1, ?, ?, NULL, NULL, 0, 0, ?)",
        (world_id, timeline_id, WORLD_SCHEMA_CURRENT))
    conn.commit()


def app_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key='schema_version'").fetchone()
    if row is None:
        raise _corrupt("app_meta.schema_version 缺失")
    return int(row[0])


def set_app_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "UPDATE app_meta SET value=? WHERE key='schema_version'", (str(version),))


def world_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT schema_version FROM world_meta WHERE id=1").fetchone()
    if row is None:
        raise _corrupt("world_meta 缺失")
    return int(row[0])


def set_world_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("UPDATE world_meta SET schema_version=? WHERE id=1", (version,))


def read_world_meta(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM world_meta WHERE id=1").fetchone()
    if row is None:
        raise _corrupt("world_meta 缺失")
    return dict(row)


def _corrupt(message: str) -> Exception:
    from .constants import ReleaseError
    return ReleaseError("RELEASE_DB_CORRUPT_METADATA", {"detail": message})


# ---------------------------------------------------------------------------
# Snapshot 状态表与投影注册表（DOC-RELEASE-003 §5.2：构建期生成，缺表即校验失败）
# ---------------------------------------------------------------------------

#: 规范化状态表清单（各 owner Schema 注册表在此登记；world_meta 为 RELEASE 自有）
STATE_TABLE_REGISTRY: list[str] = ["world_meta"]

#: domain 投影导出器：name -> callable(conn) -> JSON 可序列化对象
PROJECTION_EXPORTERS: dict[str, object] = {}

#: 投影恢复器：name -> callable(conn, data) -> None（replay/branch 重建用）
PROJECTION_RESTORERS: dict[str, object] = {}


def register_state_table(name: str) -> None:
    if name not in STATE_TABLE_REGISTRY:
        STATE_TABLE_REGISTRY.append(name)


def register_projection(name: str, exporter, restorer) -> None:
    PROJECTION_EXPORTERS[name] = exporter
    PROJECTION_RESTORERS[name] = restorer

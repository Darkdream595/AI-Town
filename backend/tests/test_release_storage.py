"""TEST-RELEASE-001..004：SQLite 数据模型与存储布局（DOC-RELEASE-001）"""
from __future__ import annotations

import os
import sqlite3

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_ulid_factory)

from src.persistence import database, paths, schema
from src.persistence.constants import ReleaseError


class TestLayoutAndPragmas:  # TEST-RELEASE-001：RULE-RELEASE-001..004
    def test_layout_matches_spec(self, layout):
        assert layout.app_db_path.name == "app.sqlite3"
        for name in ("worlds", "trash", "secrets", "runtime", "logs",
                     "diagnostics"):
            assert (layout.root / name).is_dir()

    def test_unicode_and_space_paths(self, tmp_path):
        unicode_root = tmp_path / "游戏 测试（新）" / "AI-Town"
        ly = paths.UserDataLayout(unicode_root)
        ly.ensure_root_layout()
        world_id = make_ulid_factory()()
        world_dir = ly.ensure_world_layout(world_id)
        assert world_dir.is_dir()
        db = database.open_write_connection(ly.world_db_path(world_id))
        schema.create_world_database(db, world_id, make_ulid_factory()())
        database.close_write_connection(ly.world_db_path(world_id), db)

    def test_pragmas_applied_and_verified(self, app_conn):
        actual = database.verify_pragmas(app_conn)
        assert actual["journal_mode"] == "wal"
        assert actual["foreign_keys"] == 1
        assert actual["busy_timeout"] == 5000
        assert actual["synchronous"] == 1

    def test_single_writer_per_database(self, layout, app_conn):
        with pytest.raises(ReleaseError) as exc:
            database.open_write_connection(layout.app_db_path)
        assert exc.value.reason_code == "RELEASE_DB_OPEN_FAILED"

    def test_read_connection_is_query_only(self, layout, app_conn):
        reader = database.open_read_connection(layout.app_db_path)
        assert reader.execute(
            "SELECT COUNT(*) FROM world_registry").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            reader.execute(
                "INSERT INTO app_settings(key, value_json) VALUES ('x','1')")
        reader.close()

    def test_readonly_file_mode_writes_nothing(self, layout, app_conn):
        before = layout.app_db_path.stat().st_mtime_ns
        conn = database.open_readonly_file(layout.app_db_path)
        assert conn.execute("SELECT value FROM app_meta"
                            " WHERE key='schema_version'").fetchone()[0] == "1"
        conn.close()
        assert layout.app_db_path.stat().st_mtime_ns == before


class TestAtomicCommitAndRevision:  # TEST-RELEASE-002：RULE-RELEASE-005/008
    def test_state_and_events_commit_together(self, world_conn, created_world):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id, game_time=7)
        from src.persistence import event_log
        assert event_log.tip_revision(world_conn) == 1
        meta = schema.read_world_meta(world_conn)
        assert meta["revision"] == 1 and meta["game_time"] == 7

    def test_rollback_keeps_revision_and_events(self, world_conn,
                                                created_world):
        from src.persistence import event_log
        world_id = created_world["world_id"]
        world_conn.execute("BEGIN IMMEDIATE")
        try:
            event_log.append_event(world_conn, {
                "revision": 1, "event_id": make_ulid_factory()(),
                "world_id": world_id, "event_type": "test.tick",
                "event_schema_version": 1, "game_time": 1,
                "causation_id": None, "correlation_id": None,
                "payload_json": "{}", "render_json": None,
                "created_at": "2026-07-28T10:00:00.000Z"})
            world_conn.execute(
                "UPDATE world_meta SET revision=1 WHERE id=1")
            raise RuntimeError("模拟事务失败")
        except RuntimeError:
            world_conn.rollback()
        assert event_log.tip_revision(world_conn) == 0
        assert schema.read_world_meta(world_conn)["revision"] == 0

    def test_gap_insert_rejected(self, world_conn, created_world):
        from src.persistence import event_log
        with pytest.raises(ReleaseError) as exc:
            event_log.append_event(world_conn, {
                "revision": 5, "event_id": make_ulid_factory()(),
                "world_id": created_world["world_id"], "event_type": "t",
                "event_schema_version": 1, "game_time": 1,
                "causation_id": None, "correlation_id": None,
                "payload_json": "{}", "render_json": None,
                "created_at": "2026-07-28T10:00:00.000Z"})
        assert exc.value.reason_code == "RELEASE_EVENT_GAP_DETECTED"


class TestSecretExclusion:  # TEST-RELEASE-003：RULE-RELEASE-006
    def test_no_secret_shapes_in_databases(self, world_conn, created_world):
        from src.persistence import secret_scan
        append_tick(world_conn, created_world["world_id"],
                    payload={"note": "普通内容"})
        db_file = world_conn.execute("PRAGMA database_list").fetchall()[0][2]
        with open(db_file, "rb") as fh:
            report = secret_scan.scan_bytes(fh.read(), ())
        key_hits = [h for h in report["hits"] if h["rule"] == "a_key_shape"]
        assert key_hits == []


class TestCheckpointAndCrashHandoff:  # TEST-RELEASE-004：RULE-RELEASE-007
    def test_clean_checkpoint_truncates_wal(self, layout, created_world,
                                            world_conn):
        append_tick(world_conn, created_world["world_id"])
        db_path = layout.world_db_path(created_world["world_id"])
        assert database.wal_file_size(db_path) >= 0
        database.checkpoint_truncate(world_conn)
        assert database.wal_file_size(db_path) == 0

    def test_crash_wal_recovers_committed_revision(self, layout,
                                                   created_world):
        """崩溃语义：已提交事务留在 WAL；新连接经 WAL 重放读到一致状态"""
        world_id = created_world["world_id"]
        db_path = layout.world_db_path(world_id)
        conn = database.open_write_connection(db_path)
        append_tick(conn, world_id, game_time=3)
        # 不 checkpoint：已提交事务驻留 WAL（崩溃后的恢复面）
        assert database.wal_file_size(db_path) > 0
        # 新连接经 WAL 重放读到已提交 Revision（RULE-RELEASE-041 L1 无损前提）
        reader = database.open_readonly_file(db_path)
        from src.persistence import event_log
        assert event_log.tip_revision(reader) == 1
        assert schema.read_world_meta(reader)["game_time"] == 3
        reader.close()
        database.close_write_connection(db_path, conn)

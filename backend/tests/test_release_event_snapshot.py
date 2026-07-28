"""TEST-RELEASE-009..012：Snapshot 与 Event Log 持久化（DOC-RELEASE-003）"""
from __future__ import annotations

import json
import sqlite3

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_ulid_factory,
                             make_utc_factory)

from src.persistence import database, event_log, replay, snapshots, zstd_codec
from src.persistence.constants import ReleaseError


class TestAppendOnlyAndContinuity:  # TEST-RELEASE-009：RULE-RELEASE-017..019
    def test_update_rejected_by_trigger(self, world_conn, created_world):
        append_tick(world_conn, created_world["world_id"])
        with pytest.raises(sqlite3.IntegrityError):
            world_conn.execute(
                "UPDATE event_log SET game_time=99 WHERE revision=1")
        world_conn.rollback()

    def test_delete_rejected_by_trigger(self, world_conn, created_world):
        append_tick(world_conn, created_world["world_id"])
        with pytest.raises(sqlite3.IntegrityError):
            world_conn.execute("DELETE FROM event_log WHERE revision=1")
        world_conn.rollback()

    def test_gap_detected_on_append_and_verify(self, world_conn, created_world):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id)
        # 直接 SQL 跳过 revision=2 插入 3（绕过 append_event 校验）
        world_conn.execute(
            "INSERT INTO event_log(revision, event_id, world_id, event_type,"
            " event_schema_version, game_time, payload_json, created_at)"
            " VALUES (3,?,?,?,1,1,'{}','2026-07-28T10:00:00.000Z')",
            (make_ulid_factory()(), world_id, "test.tick"))
        world_conn.commit()
        report = event_log.verify_event_continuity(world_conn, 1)
        assert report["ok"] is False and report["gaps"] == [2]

    def test_envelope_validation(self, world_conn, created_world):
        world_id = created_world["world_id"]
        base = {"revision": 1, "event_id": make_ulid_factory()(),
                "world_id": world_id, "event_type": "t",
                "event_schema_version": 1, "game_time": 0,
                "causation_id": None, "correlation_id": None,
                "payload_json": "{}", "render_json": None,
                "created_at": "2026-07-28T10:00:00.000Z"}
        for mutate in (
                lambda e: e.pop("event_type"),
                lambda e: e.update(event_id="not-a-ulid"),
                lambda e: e.update(payload_json="{unparseable"),
                lambda e: e.update(created_at="2026-07-28 10:00:00")):
            event = dict(base)
            mutate(event)
            with pytest.raises(ReleaseError) as exc:
                event_log.append_event(world_conn, event)
            assert exc.value.reason_code == "RELEASE_EVENT_ENVELOPE_INVALID"
            world_conn.rollback()

    def test_forbidden_content_rejected(self, world_conn, created_world):
        world_id = created_world["world_id"]
        base = {"revision": 1, "event_id": make_ulid_factory()(),
                "world_id": world_id, "event_type": "t",
                "event_schema_version": 1, "game_time": 0,
                "causation_id": None, "correlation_id": None,
                "render_json": None,
                "created_at": "2026-07-28T10:00:00.000Z"}
        for payload in ('{"reasoning_content": "秘密思考"}',
                        '{"key": "sk-abcdefgh12345678"}'):
            with pytest.raises(ReleaseError) as exc:
                event_log.append_event(
                    world_conn, {**base, "payload_json": payload})
            assert exc.value.reason_code == "RELEASE_EVENT_CONTENT_FORBIDDEN"
            world_conn.rollback()


class TestSnapshotAnchorAndAtomicWrite:  # TEST-RELEASE-010
    def test_snapshot_anchor_and_roundtrip(self, world_conn, created_world,
                                           layout):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id, game_time=5)
        snap_dir = layout.world_subdir(world_id, "snapshots")
        meta = snapshots.build_snapshot(world_conn, snap_dir, "auto_save",
                                        utc_now=make_utc_factory(),
                                        new_ulid=make_ulid_factory())
        assert meta["anchor_revision"] == 1
        # 原子写入：目录无临时文件残留
        assert not list(snap_dir.glob("*.tmp"))
        loaded = snapshots.load_latest_valid_snapshot(world_conn, snap_dir)
        assert loaded["anchor_revision"] == 1
        assert loaded["game_time"] == 5
        assert loaded["state_tables"]["world_meta"][0]["world_id"] == world_id

    def test_zstd_frame_is_standard(self, world_conn, created_world, layout):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id)
        snap_dir = layout.world_subdir(world_id, "snapshots")
        meta = snapshots.build_snapshot(world_conn, snap_dir, "auto_save")
        raw = (snap_dir / meta["file_name"]).read_bytes()
        assert zstd_codec.is_zstd_frame(raw)
        content = json.loads(zstd_codec.decompress(raw))
        assert content["snapshot_format_version"] == 1

    def test_same_anchor_reuses_snapshot(self, world_conn, created_world,
                                         layout):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id)
        snap_dir = layout.world_subdir(world_id, "snapshots")
        first = snapshots.build_snapshot(world_conn, snap_dir, "auto_save")
        second = snapshots.build_snapshot(world_conn, snap_dir, "manual_save")
        assert second["reused"] is True
        assert first["snapshot_id"] == second["snapshot_id"]
        count = world_conn.execute(
            "SELECT COUNT(*) FROM snapshot_meta").fetchone()[0]
        assert count == 1

    def test_corrupt_snapshot_treated_as_missing(self, world_conn,
                                                 created_world, layout):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id)
        snap_dir = layout.world_subdir(world_id, "snapshots")
        meta = snapshots.build_snapshot(world_conn, snap_dir, "auto_save")
        (snap_dir / meta["file_name"]).write_bytes(b"corrupted-bytes")
        assert snapshots.load_latest_valid_snapshot(world_conn,
                                                    snap_dir) is None

    def test_orphan_temp_cleanup(self, tmp_path):
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        (snap_dir / "1-x.snap.zst.tmp").write_bytes(b"half")
        (snap_dir / "keep.txt").write_text("k", encoding="utf-8")
        removed = snapshots.cleanup_orphan_temp_files(snap_dir)
        assert removed == ["1-x.snap.zst.tmp"]
        assert (snap_dir / "keep.txt").is_file()


class TestSnapshotRetention:  # TEST-RELEASE-011：RULE-RELEASE-022
    def _advance_and_snapshot(self, conn, world_id, snap_dir, n=1):
        for _ in range(n):
            append_tick(conn, world_id, game_time=1)
        return snapshots.build_snapshot(conn, snap_dir, "revision_interval")

    def test_retention_keeps_two_newest(self, world_conn, created_world,
                                        layout):
        world_id = created_world["world_id"]
        snap_dir = layout.world_subdir(world_id, "snapshots")
        for _ in range(4):
            self._advance_and_snapshot(world_conn, world_id, snap_dir)
        deleted = snapshots.enforce_snapshot_retention(world_conn, snap_dir)
        assert len(deleted) == 2
        remaining = world_conn.execute(
            "SELECT anchor_revision FROM snapshot_meta"
            " ORDER BY anchor_revision").fetchall()
        assert [r[0] for r in remaining] == [3, 4]
        assert len(list(snap_dir.glob("*.snap.zst"))) == 2

    def test_referenced_snapshot_never_deleted(self, world_conn,
                                               created_world, layout):
        from src.persistence import saves
        world_id = created_world["world_id"]
        snap_dir = layout.world_subdir(world_id, "snapshots")
        first = self._advance_and_snapshot(world_conn, world_id, snap_dir)
        # SaveRecord（含 Trash 内）引用 → 引用保护
        world_conn.execute(
            "INSERT INTO save_records(save_id, kind, slot, timeline_id,"
            " anchor_revision, snapshot_id, game_time, display_label,"
            " created_at, trashed_at) VALUES (?,?,NULL,?,?,?,?,?,?,NULL)",
            (make_ulid_factory()(), "auto",
             world_conn.execute("SELECT timeline_id FROM world_meta"
                                " WHERE id=1").fetchone()[0],
             first["anchor_revision"], first["snapshot_id"], 1, "保留",
             "2026-07-28T10:00:00.000Z"))
        world_conn.commit()
        for _ in range(3):
            self._advance_and_snapshot(world_conn, world_id, snap_dir)
        deleted = snapshots.enforce_snapshot_retention(world_conn, snap_dir)
        assert first["snapshot_id"] not in deleted
        assert (snap_dir / first["file_name"]).is_file()


class TestDeterministicReplay:  # TEST-RELEASE-012：RULE-RELEASE-023/024
    def setup_method(self):
        replay.EVENT_APPLIERS.clear()
        replay.UPCASTERS.clear()
        replay.UPCAST_VALIDATORS.clear()
        replay.EVENT_SCHEMA_CURRENT.clear()

    def _snapshot(self):
        return {"state_tables": {"world_meta": []}, "domain_projections": {},
                "anchor_revision": 0, "game_time": 0}

    def test_replay_twice_byte_identical(self):
        replay.register_event(
            "t.inc", 1,
            lambda state, payload: state["state_tables"]
            .setdefault("acc", []).append(payload["v"]))
        tail = [{"revision": i, "event_type": "t.inc",
                 "event_schema_version": 1, "game_time": i,
                 "payload_json": json.dumps({"v": i})} for i in (1, 2, 3)]
        first = replay.replay(self._snapshot(), tail)
        second = replay.replay(self._snapshot(), tail)
        assert replay.state_hash(first) == replay.state_hash(second)
        assert first["revision"] == 3 and first["state_tables"]["acc"] == [1, 2, 3]

    def test_unknown_event_stops_replay(self):
        with pytest.raises(ReleaseError) as exc:
            replay.replay(self._snapshot(), [
                {"revision": 1, "event_type": "unknown.e",
                 "event_schema_version": 1, "game_time": 1,
                 "payload_json": "{}"}])
        assert exc.value.reason_code == "RELEASE_REPLAY_UNKNOWN_EVENT"

    def test_gap_in_tail_stops_replay(self):
        replay.register_event("t.inc", 1, lambda s, p: None)
        with pytest.raises(ReleaseError) as exc:
            replay.replay(self._snapshot(), [
                {"revision": 2, "event_type": "t.inc",
                 "event_schema_version": 1, "game_time": 1,
                 "payload_json": "{}"}])
        assert exc.value.reason_code == "RELEASE_EVENT_GAP_DETECTED"

    def test_upcaster_chain_with_validation(self):
        replay.register_event("t.evo", 3, lambda s, p: None,
                              validators=lambda p: "v" in p)
        replay.register_upcaster("t.evo", 1,
                                 lambda p: {"v": p["v"] + "-v2"})
        replay.register_upcaster("t.evo", 2,
                                 lambda p: {"v": p["v"] + "-v3"})
        result = replay.upcast_payload("t.evo", 1, {"v": "base"})
        assert result == {"v": "base-v2-v3"}

    def test_upcaster_failure_stops(self):
        replay.register_event("t.evo", 2, lambda s, p: None,
                              validators=lambda p: "v" in p)
        # 缺 v1→v2 的 upcaster：失败而非跳过
        with pytest.raises(ReleaseError) as exc:
            replay.upcast_payload("t.evo", 1, {"v": "x"})
        assert exc.value.reason_code == "RELEASE_REPLAY_UPCAST_FAILED"

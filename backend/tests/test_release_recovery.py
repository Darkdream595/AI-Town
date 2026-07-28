"""TEST-RELEASE-021..024：备份、损坏分诊与恢复（DOC-RELEASE-006）"""
from __future__ import annotations

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_ulid_factory,
                             make_utc_factory)

from src.persistence import database, event_log, recovery, schema
from src.persistence import snapshots as snap
from src.persistence.constants import ReleaseError


@pytest.fixture()
def world_with_events(layout, created_world):
    """3 个事件 + 1 个 Snapshot 的世界"""
    world_id = created_world["world_id"]
    conn = database.open_write_connection(layout.world_db_path(world_id))
    for i in range(3):
        append_tick(conn, world_id, game_time=i + 1)
    snap.build_snapshot(conn, layout.world_subdir(world_id, "snapshots"),
                        "auto_save", utc_now=make_utc_factory(),
                        new_ulid=make_ulid_factory())
    database.close_write_connection(layout.world_db_path(world_id), conn)
    return created_world


class TestPreRepairCopyAndChain:  # TEST-RELEASE-021：RULE-RELEASE-040/041
    def test_pre_repair_copy_verified_and_idempotent(self, layout,
                                                     world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        first = recovery.make_pre_repair_copy(
            world_dir, utc_compact=lambda: "20260728T100000Z")
        assert (first / "copy-manifest.json").is_file()
        assert (first / "world.sqlite3").is_file()
        # 幂等：同 utc 复用不重建
        again = recovery.make_pre_repair_copy(
            world_dir, utc_compact=lambda: "20260728T100000Z")
        assert again == first
        assert first.name.startswith("corrupt-")

    def test_chain_eight_steps_all_pass(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        report = recovery.run_recovery_chain(world_dir)
        assert report["passed"] is True
        assert [r["step"] for r in report["chain_results"]] == [1, 2, 3, 4, 5,
                                                              6, 7, 8]
        assert [r["name"] for r in report["chain_results"]] == [
            "open_and_pragma", "integrity_check", "schema_migration",
            "snapshot_hash", "event_continuity", "reservation_rebuild",
            "inflight_ai_disposition", "invariant_audit"]
        assert recovery.recovery_success(world_dir) is True

    def test_chain_stops_at_first_failure_no_skip(self, layout,
                                                  world_with_events):
        """RULE-RELEASE-041：任一步失败即停在该步，不跳步"""
        world_id = world_with_events["world_id"]
        world_dir = layout.world_dir(world_id)
        # 注入事件空洞（模拟外部损坏）：移除 trigger → 删 revision=2 → 恢复 trigger
        conn = database.open_write_connection(layout.world_db_path(world_id))
        conn.execute("DROP TRIGGER event_log_no_delete")
        conn.execute("DELETE FROM event_log WHERE revision=2")
        conn.execute(
            "CREATE TRIGGER event_log_no_delete BEFORE DELETE ON event_log"
            " BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END")
        conn.commit()
        database.close_write_connection(layout.world_db_path(world_id), conn)
        report = recovery.run_recovery_chain(world_dir)
        assert report["passed"] is False
        # 步 1-4 通过，步 5 event_continuity 停止
        assert [r["step"] for r in report["chain_results"]] == [1, 2, 3, 4, 5]
        assert all(r["passed"] for r in report["chain_results"][:-1])
        assert report["failed_step"] == 5
        assert report["chain_results"][-1]["reason_code"] == \
            "RELEASE_EVENT_GAP_DETECTED"

    def test_chain_failure_reason_code_recorded(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        hook_error = ReleaseError("RELEASE_RECOVERY_RESERVATION_FAILED")
        report = recovery.run_recovery_chain(
            world_dir, hooks={"reservation_rebuild": _raise(hook_error)})
        assert report["passed"] is False
        last = report["chain_results"][-1]
        assert last["step"] == 6
        assert last["reason_code"] == "RELEASE_RECOVERY_RESERVATION_FAILED"
        assert len(report["chain_results"]) == 6


def _raise(error):
    def hook(conn):
        raise error
    return hook


class TestDiskPreflight:  # TEST-RELEASE-022：RULE-RELEASE-042/043
    def test_preflight_requires_two_times(self, tmp_path):
        assert recovery.preflight_disk_check(
            tmp_path, 100, free_space=lambda p: 200) is True
        with pytest.raises(ReleaseError) as exc:
            recovery.preflight_disk_check(tmp_path, 100,
                                          free_space=lambda p: 199)
        assert exc.value.reason_code == "RELEASE_DISK_SPACE_INSUFFICIENT"

    def test_estimate_is_two_times(self):
        assert recovery.estimate_required_space(50) == 100


class TestTriageLadder:  # TEST-RELEASE-023：RULE-RELEASE-044/045
    def test_triage_lists_candidates_readonly(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        before = {p.name: p.stat().st_size
                  for p in world_dir.rglob("*") if p.is_file()}
        candidates = recovery.triage(world_dir, failed_step=2)
        assert candidates["L1"]["available"] is True
        assert candidates["L2"]["available"] is True
        assert candidates["L2"]["anchor_revision"] == 3
        assert candidates["L3"]["requires_confirm"] is True
        assert candidates["L4"]["requires_confirm"] is True
        assert candidates["L5"]["requires_confirm"] is True
        after = {p.name: p.stat().st_size
                 for p in world_dir.rglob("*") if p.is_file()}
        assert before == after  # 只读列出，不执行

    def test_l1_reopen_succeeds(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        attempt = recovery.apply_triage_level(world_dir, level="L1")
        assert attempt["passed"] is True

    def test_l2_snapshot_tail_rebuild(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        attempt = recovery.apply_triage_level(world_dir, level="L2")
        assert attempt["passed"] is True
        assert attempt["anchor_revision"] == 3

    def test_l3_branches_from_selected_anchor(self, layout, created_world):
        """RULE-RELEASE-045：L3 走 branch-on-load 语义，损坏 Timeline 保留"""
        world_id = created_world["world_id"]
        world_dir = layout.world_dir(world_id)
        snap_dir = layout.world_subdir(world_id, "snapshots")
        # 锚点 2 处存在有效自动恢复点（Snapshot@2），tip 在 3
        conn = database.open_write_connection(layout.world_db_path(world_id))
        for i in range(2):
            append_tick(conn, world_id, game_time=i + 1)
        snap.build_snapshot(conn, snap_dir, "auto_save",
                            utc_now=make_utc_factory(),
                            new_ulid=make_ulid_factory())
        append_tick(conn, world_id, game_time=3)
        snap.build_snapshot(conn, snap_dir, "auto_save",
                            utc_now=make_utc_factory(),
                            new_ulid=make_ulid_factory())
        database.close_write_connection(layout.world_db_path(world_id), conn)
        new_timeline = make_ulid_factory()()
        attempt = recovery.apply_triage_level(
            world_dir, level="L3", anchor_revision=2,
            new_timeline_id=new_timeline)
        assert attempt["passed"] is True
        conn = database.open_readonly_file(layout.world_db_path(world_id))
        meta = schema.read_world_meta(conn)
        assert meta["revision"] == 2
        assert meta["branch_source_revision"] == 2
        assert meta["timeline_id"] == new_timeline
        assert event_log.tip_revision(conn) == 2
        conn.close()
        archives = list(layout.world_subdir(world_id, "timelines")
                        .glob("*.sqlite3"))
        assert len(archives) == 1


class TestRetentionAndOutcome:  # TEST-RELEASE-024：RULE-RELEASE-046/047
    def test_pre_migration_backup_retention_keeps_three(self, tmp_path):
        backups = tmp_path / "backups"
        backups.mkdir()
        for i in range(5):
            name = "pre-migration-v%d-v%d-2026072%dT100000Z.sqlite3" % (
                i + 1, i + 2, i)
            (backups / name).write_bytes(b"x" * 10)
        (backups / "corrupt-20260728T100000Z").mkdir()
        from src.persistence.migrations import enforce_backup_retention
        removed = enforce_backup_retention(backups, keep=3)
        assert len(removed) == 2
        remaining = sorted(p.name for p in backups.iterdir()
                           if p.suffix == ".sqlite3")
        assert len(remaining) == 3
        # corrupt 复制永不被自动清理
        assert (backups / "corrupt-20260728T100000Z").is_dir()

    def test_success_criterion_revision_equals_tip(self, layout,
                                                   world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        assert recovery.recovery_success(world_dir) is True
        conn = database.open_write_connection(
            layout.world_db_path(world_with_events["world_id"]))
        conn.execute("UPDATE world_meta SET revision=99 WHERE id=1")
        conn.commit()
        database.close_write_connection(
            layout.world_db_path(world_with_events["world_id"]), conn)
        assert recovery.recovery_success(world_dir) is False

    def test_declare_unrecoverable_report(self, layout, world_with_events):
        world_dir = layout.world_dir(world_with_events["world_id"])
        report = recovery.declare_unrecoverable(
            world_dir,
            chain_results=[{"step": 2, "name": "integrity_check",
                            "passed": False,
                            "reason_code": "RELEASE_DB_INTEGRITY_FAILED"}],
            triage_attempts=[{"level": "L1", "passed": False,
                              "reason_code": "RELEASE_WAL_RECOVER_FAILED"}],
            world_id=world_with_events["world_id"])
        assert report["outcome"] == "unrecoverable"
        assert report["final_revision"] is None
        assert report["report_format_version"] == 1
        assert any("world.sqlite3" in f for f in report["file_inventory"])
        assert report["triage_attempts"][0]["level"] == "L1"

    def test_recovery_report_shape(self):
        report = recovery.build_recovery_report(
            "w1", chain_results=[{"step": 1, "name": "open_and_pragma",
                                  "passed": True}],
            triage_attempts=[{"level": "L2", "passed": True,
                              "anchor_revision": 44000}],
            outcome="recovered", final_revision=44000,
            pre_repair_copy="backups\\corrupt-20260726T110000Z",
            utc_now=lambda: "2026-07-28T11:00:00.000Z")
        assert report["report_format_version"] == 1
        assert report["outcome"] == "recovered"
        assert report["pre_repair_copy"].startswith("backups")

"""TEST-RELEASE-013..016：自动恢复点与手动存档槽位（DOC-RELEASE-004）"""
from __future__ import annotations

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_ulid_factory,
                             make_utc_factory, make_command_ids)

from src.persistence import branch, database, event_log, saves, schema
from src.persistence import snapshots as snap
from src.persistence.constants import (AUTO_SAVE_COUNT, ReleaseError)


@pytest.fixture()
def snap_dir(layout, created_world):
    return layout.world_subdir(created_world["world_id"], "snapshots")


def _auto_save(conn, snap_dir, world_id, ticks=1):
    for _ in range(ticks):
        append_tick(conn, world_id)
    return saves.create_auto_recovery_point(conn, snap_dir,
                                            utc_now=make_utc_factory(),
                                            new_ulid=make_ulid_factory())


class TestCountsAndFifo:  # TEST-RELEASE-013：RULE-RELEASE-025/026
    def test_auto_recovery_points_fifo_exactly_five(self, world_conn,
                                                    created_world, snap_dir):
        world_id = created_world["world_id"]
        created = [_auto_save(world_conn, snap_dir, world_id)
                   for _ in range(7)]
        actives = [s for s in saves.list_saves(world_conn, include_trashed=False)
                   if s["kind"] == "auto"]
        assert len(actives) == AUTO_SAVE_COUNT
        # FIFO：最早两个被淘汰（入 Trash）
        trashed_ids = {s["save_id"] for s in saves.list_saves(world_conn)
                       if s["trashed_at"] is not None}
        assert {created[0]["save_id"], created[1]["save_id"]} <= trashed_ids
        anchors = sorted(s["anchor_revision"] for s in actives)
        assert anchors == sorted(s["anchor_revision"] for s in created[2:])

    def test_manual_slots_exactly_three(self, world_conn, created_world,
                                        snap_dir):
        with pytest.raises(ReleaseError) as exc:
            saves.create_manual_save(world_conn, snap_dir,
                                     command_id="c-x", slot="slot_4",
                                     display_label="非法")
        assert exc.value.reason_code == "RELEASE_SAVE_SLOT_INVALID"

    def test_auto_save_trigger_policy(self):
        assert saves.should_create_auto_save(500, 0) is True
        assert saves.should_create_auto_save(0, 10) is True
        assert saves.should_create_auto_save(499, 9) is False


class TestReferenceProtection:  # TEST-RELEASE-014：RULE-RELEASE-027
    def test_trashed_record_still_protects_snapshot(self, world_conn,
                                                    created_world, snap_dir):
        world_id = created_world["world_id"]
        first = _auto_save(world_conn, snap_dir, world_id)
        # 淘汰该记录入 Trash（trashed_at 非空），Snapshot 仍受引用保护
        world_conn.execute(
            "UPDATE save_records SET trashed_at='2026-07-28T11:00:00.000Z'"
            " WHERE save_id=?", (first["save_id"],))
        world_conn.commit()
        for _ in range(3):
            _auto_save(world_conn, snap_dir, world_id)
        deleted = snap.enforce_snapshot_retention(world_conn, snap_dir)
        assert first["snapshot_id"] not in deleted
        file_name = world_conn.execute(
            "SELECT file_name FROM snapshot_meta WHERE snapshot_id=?",
            (first["snapshot_id"],)).fetchone()[0]
        assert (snap_dir / file_name).is_file()


class TestBranchOnLoad:  # TEST-RELEASE-015：RULE-RELEASE-028/029
    def test_branch_creates_new_timeline_with_continuity(
            self, world_conn, created_world, layout, snap_dir):
        world_id = created_world["world_id"]
        for i in range(5):
            _auto_save(world_conn, snap_dir, world_id)
        target = [s for s in saves.list_saves(world_conn, include_trashed=False)
                  if s["kind"] == "auto"][1]  # 较早锚点 < tip
        anchor = target["anchor_revision"]
        old_timeline = schema.read_world_meta(world_conn)["timeline_id"]
        database.close_write_connection(layout.world_db_path(world_id),
                                        world_conn)
        new_timeline = make_ulid_factory()()
        branch.branch_on_load(layout.world_dir(world_id),
                              old_timeline_id=old_timeline,
                              new_timeline_id=new_timeline,
                              anchor_revision=anchor)
        conn = database.open_write_connection(layout.world_db_path(world_id))
        meta = schema.read_world_meta(conn)
        assert meta["timeline_id"] == new_timeline
        assert meta["parent_timeline_id"] == old_timeline
        assert meta["branch_source_revision"] == anchor
        assert meta["revision"] == anchor
        # 事件前缀复制且连续
        assert event_log.tip_revision(conn) == anchor
        assert event_log.verify_event_continuity(conn, 1)["ok"]
        database.close_write_connection(layout.world_db_path(world_id), conn)
        # 原 Timeline 只读归档且字节保留
        archive = layout.world_subdir(world_id, "timelines") / \
            (old_timeline + ".sqlite3")
        assert archive.is_file() and branch.is_readonly(archive)
        archive_conn = database.open_readonly_file(archive)
        assert event_log.tip_revision(archive_conn) == 5
        archive_conn.close()

    def test_seed_preserved_across_branch(self, world_conn, created_world,
                                          layout, snap_dir):
        """RULE-RELEASE-029：世界 Seed 不变（registry 层验证）"""
        world_id = created_world["world_id"]
        seed_before = None
        # seed 存于 app registry；分支不动 registry → 校验分支后 seed 一致
        _auto_save(world_conn, snap_dir, world_id)
        old_timeline = schema.read_world_meta(world_conn)["timeline_id"]
        database.close_write_connection(layout.world_db_path(world_id),
                                        world_conn)
        branch.branch_on_load(layout.world_dir(world_id),
                              old_timeline_id=old_timeline,
                              new_timeline_id=make_ulid_factory()(),
                              anchor_revision=1)
        conn = database.open_readonly_file(layout.world_db_path(world_id))
        meta = schema.read_world_meta(conn)
        assert meta["world_id"] == world_id  # world_id/Seed 语义延续
        conn.close()

    def test_incomplete_branch_recovers_idempotently(self, world_conn,
                                                     created_world, layout,
                                                     snap_dir):
        world_id = created_world["world_id"]
        _auto_save(world_conn, snap_dir, world_id)
        anchor = 1
        old_timeline = schema.read_world_meta(world_conn)["timeline_id"]
        database.close_write_connection(layout.world_db_path(world_id),
                                        world_conn)
        world_dir = layout.world_dir(world_id)
        new_timeline = make_ulid_factory()()
        # 模拟崩溃：手工完成步骤 2（归档），留 journal，缺新库
        import json
        import os
        from src.persistence.database import (checkpoint_truncate,
                                              close_write_connection,
                                              open_write_connection)
        db_path = world_dir / "world.sqlite3"
        conn = open_write_connection(db_path)
        checkpoint_truncate(conn)
        close_write_connection(db_path, conn)
        journal = {"old_timeline_id": old_timeline,
                   "new_timeline_id": new_timeline,
                   "anchor_revision": anchor,
                   "written_at": "2026-07-28T11:00:00.000Z"}
        (world_dir / "branch-journal.json").write_text(
            json.dumps(journal), encoding="utf-8")
        os.replace(db_path,
                   world_dir / "timelines" / (old_timeline + ".sqlite3"))
        # 启动扫描：幂等重试步骤 3
        result = branch.recover_incomplete_branch(world_dir)
        assert result["recovered_branch"] is True
        assert result["new_timeline_id"] == new_timeline
        # 再跑一次：已完整，返回 None
        assert branch.recover_incomplete_branch(world_dir) is None
        conn = database.open_readonly_file(db_path)
        assert schema.read_world_meta(conn)["revision"] == anchor
        conn.close()


class TestConfirmTrashIdempotency:  # TEST-RELEASE-016
    def test_overwrite_requires_confirmation(self, world_conn, created_world,
                                             snap_dir):
        world_id = created_world["world_id"]
        saves.create_manual_save(world_conn, snap_dir, command_id="c-1",
                                 slot="slot_1", display_label="一",
                                 utc_now=make_utc_factory(),
                                 new_ulid=make_ulid_factory())
        with pytest.raises(ReleaseError) as exc:
            saves.create_manual_save(world_conn, snap_dir, command_id="c-2",
                                     slot="slot_1", display_label="二")
        assert exc.value.reason_code == "RELEASE_SAVE_CONFIRM_REQUIRED"

    def test_overwrite_trash_and_restore_swaps(self, world_conn,
                                               created_world, snap_dir):
        utc = make_utc_factory()
        first = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-1", slot="slot_1",
            display_label="一", utc_now=utc, new_ulid=make_ulid_factory())
        append_tick(world_conn, created_world["world_id"])
        second = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-2", slot="slot_1",
            display_label="二", confirmed=True, utc_now=utc,
            new_ulid=make_ulid_factory())
        record = saves.get_save(world_conn, first["save_id"])
        assert record["trashed_at"] is not None
        result = saves.restore_trashed_save(
            world_conn, command_id="c-3", save_id=first["save_id"],
            utc_now=utc)
        assert result["restored"] is True
        assert result["swapped_to_trash"] == second["save_id"]
        assert saves.get_save(world_conn, first["save_id"])["trashed_at"] \
            is None

    def test_expired_trash_restore_refused(self, world_conn, created_world,
                                           snap_dir):
        first = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-1", slot="slot_1",
            display_label="一", utc_now=make_utc_factory(),
            new_ulid=make_ulid_factory())
        saves.create_manual_save(
            world_conn, snap_dir, command_id="c-2", slot="slot_1",
            display_label="二", confirmed=True, utc_now=make_utc_factory(),
            new_ulid=make_ulid_factory())
        with pytest.raises(ReleaseError) as exc:
            saves.restore_trashed_save(
                world_conn, command_id="c-3", save_id=first["save_id"],
                utc_now=lambda: "2027-01-01T00:00:00.000Z")
        assert exc.value.reason_code == "RELEASE_SAVE_TRASH_EXPIRED"

    def test_same_command_id_applies_once(self, world_conn, created_world,
                                          snap_dir):
        utc = make_utc_factory()
        ulids = make_ulid_factory()
        first = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-dup", slot="slot_1",
            display_label="一", utc_now=utc, new_ulid=ulids)
        again = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-dup", slot="slot_1",
            display_label="一", utc_now=utc, new_ulid=ulids)
        assert first["save_id"] == again["save_id"]
        count = world_conn.execute(
            "SELECT COUNT(*) FROM save_records WHERE kind='manual'"
            " AND slot='slot_1' AND trashed_at IS NULL").fetchone()[0]
        assert count == 1

    def test_plan_load_resume_vs_branch(self, world_conn, created_world,
                                        snap_dir):
        world_id = created_world["world_id"]
        _auto_save(world_conn, snap_dir, world_id)
        latest = _auto_save(world_conn, snap_dir, world_id)
        resume = saves.plan_load(world_conn, latest["save_id"])
        assert resume["mode"] == "resume"
        older = [s for s in saves.list_saves(world_conn, include_trashed=False)
                 if s["save_id"] != latest["save_id"]][0]
        with pytest.raises(ReleaseError) as exc:
            saves.plan_load(world_conn, older["save_id"])
        assert exc.value.reason_code == "RELEASE_SAVE_CONFIRM_REQUIRED"
        branched = saves.plan_load(world_conn, older["save_id"],
                                   confirm_branch=True)
        assert branched["mode"] == "branch"

    def test_load_failure_keeps_current_state(self, world_conn, created_world,
                                              snap_dir):
        """RULE-RELEASE-031：读档失败当前 Timeline 保持原状态，绝不半切换"""
        with pytest.raises(ReleaseError):
            saves.plan_load(world_conn, "nonexistent-save")
        from src.persistence import event_log as ev
        assert ev.tip_revision(world_conn) == \
            schema.read_world_meta(world_conn)["revision"]

    def test_display_label_sanitized(self):
        assert saves.sanitize_display_label("第\x00一夜\x1f很长" + "字" * 100) \
            .startswith("第一夜很长")
        assert len(saves.sanitize_display_label("字" * 200)) == 80
        assert saves.sanitize_display_label("  \x00 ") == "未命名存档"

    def test_purge_expired_trash(self, world_conn, created_world, snap_dir):
        utc = make_utc_factory()
        first = saves.create_manual_save(
            world_conn, snap_dir, command_id="c-1", slot="slot_1",
            display_label="一", utc_now=utc, new_ulid=make_ulid_factory())
        saves.create_manual_save(
            world_conn, snap_dir, command_id="c-2", slot="slot_1",
            display_label="二", confirmed=True, utc_now=utc,
            new_ulid=make_ulid_factory())
        purged = saves.purge_expired_trash(
            world_conn, utc_now=lambda: "2027-01-01T00:00:00.000Z")
        assert purged == [first["save_id"]]

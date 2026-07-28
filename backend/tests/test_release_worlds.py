"""TEST-RELEASE-017..020：多世界管理与导入导出（DOC-RELEASE-005）"""
from __future__ import annotations

import zipfile

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_ulid_factory,
                             make_utc_factory, force_rmtree)

from src.persistence import database, transfer, worlds
from src.persistence.constants import ReleaseError


@pytest.fixture(autouse=True)
def _reset_open_guard():
    yield
    worlds._OPEN_WORLD["world_id"] = None


class TestSingleOpenAndAtomicCreate:  # TEST-RELEASE-017：RULE-RELEASE-032/033
    def test_create_three_worlds_consistent(self, registry, layout):
        ids = []
        for i in range(3):
            created = registry.create_world(command_id="cmd-w%d" % i,
                                            display_name="世界%d" % i)
            ids.append(created["world_id"])
        rows = registry.list_worlds()
        assert len(rows) == 3
        for world_id in ids:
            assert layout.world_dir(world_id).is_dir()
            assert layout.world_db_path(world_id).is_file()
        seeds = {r["seed_hex"] for r in rows}
        assert seeds == {"cd" * 16}  # 注入的确定性 seed_fn

    def test_second_open_refused(self, registry):
        first = registry.create_world(command_id="cmd-a", display_name="A")
        second = registry.create_world(command_id="cmd-b", display_name="B")
        registry.open_world(command_id="cmd-o1", world_id=first["world_id"])
        with pytest.raises(ReleaseError) as exc:
            registry.open_world(command_id="cmd-o2",
                                world_id=second["world_id"])
        assert exc.value.reason_code == "RELEASE_WORLD_ALREADY_OPEN"
        # 同一世界重复打开允许（幂等串行）
        again = registry.open_world(command_id="cmd-o3",
                                    world_id=first["world_id"])
        assert again["opened"] is True

    def test_create_failure_leaves_no_half_directory(self, layout, app_conn):
        def exploding_seed():
            raise RuntimeError("seed 故障")
        failing = worlds.WorldRegistry(layout, app_conn, seed_fn=exploding_seed)
        with pytest.raises(RuntimeError):
            failing.create_world(command_id="cmd-x", display_name="X")
        assert layout.iter_world_dirs() == []
        assert app_conn.execute(
            "SELECT COUNT(*) FROM world_registry").fetchone()[0] == 0

    def test_create_idempotent_by_command_id(self, registry):
        first = registry.create_world(command_id="cmd-dup",
                                      display_name="同一个")
        second = registry.create_world(command_id="cmd-dup",
                                       display_name="同一个")
        assert first["world_id"] == second["world_id"]
        assert len(registry.list_worlds()) == 1


class TestTrashRestorePurgeAndScan:  # TEST-RELEASE-018：RULE-RELEASE-034/038
    def test_delete_restore_cycle(self, registry, layout):
        created = registry.create_world(command_id="cmd-a", display_name="A")
        world_id = created["world_id"]
        registry.delete_world(command_id="cmd-d", world_id=world_id,
                              confirmed=True)
        assert registry.get_world(world_id)["lifecycle"] == "trashed"
        assert layout.trash_world_dir(world_id).is_dir()
        assert not layout.world_dir(world_id).exists()
        registry.restore_world(command_id="cmd-r", world_id=world_id)
        record = registry.get_world(world_id)
        assert record["lifecycle"] == "closed"
        assert record["deleted_at"] is None
        assert layout.world_db_path(world_id).is_file()

    def test_delete_requires_confirmation(self, registry):
        created = registry.create_world(command_id="cmd-a", display_name="A")
        with pytest.raises(ReleaseError) as exc:
            registry.delete_world(command_id="cmd-d",
                                  world_id=created["world_id"])
        assert exc.value.reason_code == "RELEASE_SAVE_CONFIRM_REQUIRED"

    def test_purge_expired_trash_with_audit(self, layout, app_conn):
        past = worlds.WorldRegistry(
            layout, app_conn,
            utc_now=lambda: "2026-01-01T00:00:00.000Z")
        created = past.create_world(command_id="cmd-a", display_name="A")
        world_id = created["world_id"]
        past.delete_world(command_id="cmd-d", world_id=world_id,
                          confirmed=True)
        now = worlds.WorldRegistry(
            layout, app_conn,
            utc_now=lambda: "2026-07-28T00:00:00.000Z")
        purged = now.purge_expired_trash()
        assert purged == [world_id]
        assert not layout.trash_world_dir(world_id).exists()
        assert app_conn.execute(
            "SELECT COUNT(*) FROM world_registry").fetchone()[0] == 0
        audit = app_conn.execute(
            "SELECT action, world_id FROM audit_log"
            " WHERE action='world_purged'").fetchone()
        assert audit is not None and audit["world_id"] == world_id

    def test_consistency_scan_marks_needs_attention(self, registry, layout):
        created = registry.create_world(command_id="cmd-a", display_name="A")
        world_id = created["world_id"]
        # 孤儿目录：无 registry 记录
        orphan = layout.ensure_world_layout(make_ulid_factory()())
        # 悬空记录：有记录无目录
        force_rmtree(layout.world_dir(world_id))
        scan = registry.scan_consistency()
        assert orphan.name in scan["orphan_directories"]
        assert world_id in scan["dangling_records"]
        assert set(scan["needs_attention"]) == {orphan.name, world_id}


class TestExportImport:  # TEST-RELEASE-019：RULE-RELEASE-035/036
    def test_export_package_contents_and_manifest(self, registry, layout,
                                                  app_conn, tmp_path):
        created = registry.create_world(command_id="cmd-a", display_name="导出 源")
        world_id = created["world_id"]
        out = tmp_path / "exports"
        report = transfer.export_world(
            layout, app_conn, world_id=world_id, target_path=out,
            app_package_version="1.0.0", utc_now=make_utc_factory())
        with zipfile.ZipFile(report["target"]) as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "world.sqlite3" in names
            # 边界：logs/diagnostics/backups/secrets 一律不入包
            assert not any(n.startswith(("logs/", "diagnostics/",
                                         "backups/", "secrets/"))
                           for n in names)
            import json
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["package_kind"] == "aitown-world-export"
        assert manifest["world_id"] == world_id
        assert manifest["display_name"] == "导出 源"
        assert manifest["schema_version"] == 1

    def test_import_conflict_assigns_new_id(self, registry, layout, app_conn,
                                            tmp_path):
        created = registry.create_world(command_id="cmd-a", display_name="源")
        world_id = created["world_id"]
        report = transfer.export_world(
            layout, app_conn, world_id=world_id, target_path=tmp_path,
            app_package_version="1.0.0", utc_now=make_utc_factory())
        imported = transfer.import_world(
            layout, app_conn, source_path=report["target"],
            new_ulid=make_ulid_factory())
        assert imported["world_id"] != world_id
        assert imported["origin_world_id"] == world_id
        row = app_conn.execute(
            "SELECT origin_world_id FROM world_registry WHERE world_id=?",
            (imported["world_id"],)).fetchone()
        assert row["origin_world_id"] == world_id
        assert layout.world_db_path(imported["world_id"]).is_file()

    def test_import_validation_failure_lands_nothing(self, registry, layout,
                                                     app_conn, tmp_path):
        created = registry.create_world(command_id="cmd-a", display_name="源")
        report = transfer.export_world(
            layout, app_conn, world_id=created["world_id"],
            target_path=tmp_path, app_package_version="1.0.0",
            utc_now=make_utc_factory())
        # 篡改包内数据库字节但不改 manifest → SHA-256 校验必须拒绝
        tampered = tmp_path / "tampered.zip"
        with zipfile.ZipFile(report["target"]) as zin, \
                zipfile.ZipFile(tampered, "w") as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "world.sqlite3":
                    data = data + b"tamper"
                zout.writestr(name, data)
        before = {p.name for p in layout.iter_world_dirs()}
        with pytest.raises(ReleaseError) as exc:
            transfer.import_world(layout, app_conn, source_path=tampered,
                                  new_ulid=make_ulid_factory())
        assert exc.value.reason_code == "RELEASE_IMPORT_INVALID"
        assert {p.name for p in layout.iter_world_dirs()} == before

    def test_zip_slip_rejected(self, tmp_path):
        import json
        evil = tmp_path / "evil.zip"
        manifest = {"package_format_version": 1,
                    "package_kind": "aitown-world-export",
                    "world_id": make_ulid_factory()(),
                    "origin_world_id": None, "display_name": "evil",
                    "seed_hex": "ab" * 16, "schema_version": 1,
                    "app_package_version": "1.0.0",
                    "exported_at": "2026-07-28T10:00:00.000Z",
                    "files": [{"path": "../../evil.txt", "sha256": "0" * 64,
                               "size_bytes": 3}]}
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("../../evil.txt", "bad")
        with pytest.raises(ReleaseError) as exc:
            transfer._assert_zip_entry_safe("../../evil.txt")
        assert exc.value.reason_code == "RELEASE_IMPORT_INVALID"
        with pytest.raises(ReleaseError):
            transfer._assert_zip_entry_safe("C:/abs/path.txt")
        with pytest.raises(ReleaseError):
            transfer._assert_zip_entry_safe("timelines/CON.sqlite3")

    def test_import_too_new_refused(self, registry, layout, app_conn,
                                    tmp_path):
        created = registry.create_world(command_id="cmd-a", display_name="源")
        report = transfer.export_world(
            layout, app_conn, world_id=created["world_id"],
            target_path=tmp_path, app_package_version="9.9.9",
            utc_now=make_utc_factory())
        import json
        import hashlib
        hacked = tmp_path / "hacked.zip"
        with zipfile.ZipFile(report["target"]) as zin, \
                zipfile.ZipFile(hacked, "w") as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name == "manifest.json":
                    m = json.loads(data)
                    m["schema_version"] = 99
                    data = json.dumps(m, sort_keys=True).encode()
                zout.writestr(name, data)
        with pytest.raises(ReleaseError) as exc:
            transfer.import_world(layout, app_conn, source_path=hacked,
                                  new_ulid=make_ulid_factory())
        assert exc.value.reason_code == "RELEASE_IMPORT_TOO_NEW"


class TestDisplayNameAndAudit:  # TEST-RELEASE-020：RULE-RELEASE-037/039
    def test_rename_only_changes_registry_row(self, registry, layout):
        created = registry.create_world(command_id="cmd-a",
                                        display_name="旧名字")
        world_id = created["world_id"]
        registry.rename_world(command_id="cmd-r", world_id=world_id,
                              display_name="新 名字🎮")
        assert registry.get_world(world_id)["display_name"] == "新 名字🎮"
        # 路径永远只用 world_id，重命名不动文件系统
        assert layout.world_dir(world_id).is_dir()

    def test_unicode_display_name_and_paths(self, registry, layout):
        created = registry.create_world(command_id="cmd-u",
                                        display_name="王冠溪 存档一 🏰")
        assert layout.world_dir(created["world_id"]).is_dir()

    def test_audit_log_records_operations(self, registry, app_conn):
        created = registry.create_world(command_id="cmd-a", display_name="A")
        world_id = created["world_id"]
        registry.delete_world(command_id="cmd-d", world_id=world_id,
                              confirmed=True)
        actions = [r[0] for r in app_conn.execute(
            "SELECT action FROM audit_log ORDER BY at").fetchall()]
        assert "world_created" in actions
        assert "world_trashed" in actions

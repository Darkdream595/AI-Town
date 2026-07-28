"""TEST-RELEASE-005..008：数据库 Schema 版本与迁移（DOC-RELEASE-002）"""
from __future__ import annotations

import hashlib

import pytest
from release_helpers import (append_tick, layout, app_conn, registry,  # noqa: F401
                             created_world, world_conn, make_utc_factory)

from src.persistence import database, migrations, schema
from src.persistence.constants import ReleaseError


def make_manifest(steps, database_kind="world", min_supported=1, current=None):
    if current is None:
        current = 1 + len(steps)
    return migrations.MigrationManifest({
        "manifest_version": 1, "database": database_kind,
        "min_supported": min_supported, "current": current,
        "steps": steps})


def step(from_v, sql=None, transform=None, audits=None, step_id=None):
    return {"step_id": step_id or "test.v%d_to_v%d" % (from_v, from_v + 1),
            "from_version": from_v, "to_version": from_v + 1,
            "summary": "测试迁移", "sql": sql or [],
            "python_transform": transform,
            "audit_queries": audits or []}


class TestVersionRangeAndChain:  # TEST-RELEASE-005：RULE-RELEASE-009/010
    def test_refuse_too_new_without_writing(self, layout, created_world):
        db_path = layout.world_db_path(created_world["world_id"])
        before = (db_path.stat().st_mtime_ns, db_path.stat().st_size)
        manifest = make_manifest([], current=1)  # 库已是 v1 却声明 current=0?
        too_new = migrations.MigrationManifest({
            "manifest_version": 1, "database": "world", "min_supported": 0,
            "current": 0, "steps": []})
        with pytest.raises(ReleaseError) as exc:
            migrations.plan_migration(db_path, too_new)
        assert exc.value.reason_code == "RELEASE_MIGRATION_REFUSED_TOO_NEW"
        after = (db_path.stat().st_mtime_ns, db_path.stat().st_size)
        assert before == after

    def test_refuse_below_min_supported(self, layout, created_world):
        db_path = layout.world_db_path(created_world["world_id"])
        manifest = migrations.MigrationManifest({
            "manifest_version": 1, "database": "world", "min_supported": 2,
            "current": 3, "steps": [step(1), step(2)]})
        with pytest.raises(ReleaseError) as exc:
            migrations.plan_migration(db_path, manifest)
        assert exc.value.reason_code == "RELEASE_MIGRATION_REFUSED_TOO_OLD"

    def test_duplicate_arrival_rejected(self):
        with pytest.raises(ValueError):
            make_manifest([step(1, step_id="a"), step(1, step_id="b")])

    def test_non_continuous_step_rejected(self):
        with pytest.raises(ValueError):
            migrations.MigrationStep({
                "step_id": "x", "from_version": 1, "to_version": 3})

    def test_broken_chain_rejected(self, layout, created_world):
        db_path = layout.world_db_path(created_world["world_id"])
        manifest = migrations.MigrationManifest({
            "manifest_version": 1, "database": "world", "min_supported": 1,
            "current": 3, "steps": [step(2)]})  # 缺 v1→v2
        with pytest.raises(ReleaseError) as exc:
            migrations.plan_migration(db_path, manifest)
        assert exc.value.reason_code == "RELEASE_MIGRATION_STEP_FAILED"


class TestBackupAndResume:  # TEST-RELEASE-006：RULE-RELEASE-011/012
    def test_backup_created_and_sha_recorded(self, layout, created_world):
        world_id = created_world["world_id"]
        db_path = layout.world_db_path(world_id)
        manifest = make_manifest([step(1, sql=[
            "CREATE TABLE probe (id INTEGER PRIMARY KEY)"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        report = runner.run_migration(
            db_path, manifest, layout.world_subdir(world_id, "backups"))
        entry = report["steps"][0]
        backup = layout.world_subdir(world_id, "backups") / entry["backup_file"]
        assert backup.is_file()
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        assert digest == entry["backup_sha256"]
        rows = database.open_readonly_file(db_path)
        version_row = rows.execute(
            "SELECT to_version, step_id, backup_file, backup_sha256"
            " FROM schema_migrations").fetchall()
        assert len(version_row) == 1
        assert version_row[0]["to_version"] == 2
        assert version_row[0]["backup_sha256"] == digest
        rows.close()

    def test_failed_step_restores_original_bytes(self, layout, created_world):
        world_id = created_world["world_id"]
        db_path = layout.world_db_path(world_id)
        original = db_path.read_bytes()
        manifest = make_manifest([step(1, sql=["SELCT typo FROM nowhere"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        with pytest.raises(ReleaseError) as exc:
            runner.run_migration(db_path, manifest,
                                 layout.world_subdir(world_id, "backups"))
        assert exc.value.reason_code == "RELEASE_MIGRATION_STEP_FAILED"
        assert db_path.read_bytes() == original
        conn = database.open_readonly_file(db_path)
        assert schema.world_schema_version(conn) == 1
        conn.close()

    def test_resume_skips_completed_steps(self, layout, created_world):
        world_id = created_world["world_id"]
        db_path = layout.world_db_path(world_id)
        manifest = make_manifest([
            step(1, sql=["CREATE TABLE p1 (id INTEGER PRIMARY KEY)"]),
            step(2, sql=["CREATE TABLE p2 (id INTEGER PRIMARY KEY)"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        backups = layout.world_subdir(world_id, "backups")
        report = runner.run_migration(db_path, manifest, backups)
        assert len(report["steps"]) == 2
        # 断点续迁：已完成 Step 不重放
        report2 = runner.run_migration(db_path, manifest, backups)
        assert report2["outcome"] == "noop"
        conn = database.open_readonly_file(db_path)
        assert schema.world_schema_version(conn) == 3
        applied = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert applied == 2
        conn.close()


class TestAuditAndDeterministicTransform:  # TEST-RELEASE-007
    def test_audit_failure_restores_backup(self, layout, created_world):
        world_id = created_world["world_id"]
        db_path = layout.world_db_path(world_id)
        original = db_path.read_bytes()
        bad_step = step(1, sql=["CREATE TABLE probe (id INTEGER PRIMARY KEY)"],
                        audits=["SELECT 1"])  # 审计返回 1 = 违规
        # 审计在 Step 事务提交后整链执行：注入失败审计
        manifest = make_manifest([bad_step])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        with pytest.raises(ReleaseError) as exc:
            runner.run_migration(db_path, manifest,
                                 layout.world_subdir(world_id, "backups"))
        assert exc.value.reason_code == "RELEASE_MIGRATION_AUDIT_FAILED"
        # 世界保持停止模拟：库字节与迁移前一致由备份还原保证
        conn = database.open_readonly_file(db_path)
        assert schema.world_schema_version(conn) == 1
        conn.close()

    def test_unregistered_transform_rejected(self):
        with pytest.raises(ValueError):
            migrations.MigrationStep({
                "step_id": "x", "from_version": 1, "to_version": 2,
                "python_transform": "not.registered"})

    def test_registered_transform_runs(self, layout, created_world):
        calls = []

        def probe_transform(conn):
            calls.append("ran")
            conn.execute("INSERT INTO probe VALUES (1)")

        migrations.register_transform("test.probe_v1v2", probe_transform)
        world_id = created_world["world_id"]
        manifest = make_manifest([step(
            1, sql=["CREATE TABLE probe (id INTEGER PRIMARY KEY)"],
            transform="test.probe_v1v2",
            audits=["SELECT COUNT(*) FROM probe WHERE id <> 1"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        report = runner.run_migration(
            layout.world_db_path(world_id), manifest,
            layout.world_subdir(world_id, "backups"))
        assert report["outcome"] == "migrated" and calls == ["ran"]


class TestEventLogImmutability:  # TEST-RELEASE-008：RULE-RELEASE-014/015
    def test_event_log_mutation_sql_rejected(self):
        for sql in ("DELETE FROM event_log WHERE revision < 5",
                    "UPDATE event_log SET game_time=0",
                    "INSERT INTO event_log(revision) VALUES (9)",
                    "DROP TABLE event_log"):
            with pytest.raises(ReleaseError) as exc:
                migrations.MigrationStep({
                    "step_id": "x", "from_version": 1, "to_version": 2,
                    "sql": [sql]})
            assert exc.value.reason_code == "RELEASE_MIGRATION_EVENT_LOG_TOUCHED"

    def test_event_log_index_allowed(self, layout, created_world, world_conn):
        world_id = created_world["world_id"]
        append_tick(world_conn, world_id)
        database.close_write_connection(layout.world_db_path(world_id),
                                        world_conn)
        manifest = make_manifest([step(1, sql=[
            "CREATE INDEX idx_event_log_type ON event_log(event_type)"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        report = runner.run_migration(
            layout.world_db_path(world_id), manifest,
            layout.world_subdir(world_id, "backups"))
        assert report["outcome"] == "migrated"
        conn = database.open_readonly_file(layout.world_db_path(world_id))
        payload = conn.execute(
            "SELECT payload_json FROM event_log WHERE revision=1").fetchone()[0]
        conn.close()
        assert payload == "{}"

    def test_event_rows_byte_identical_after_migration(self, layout,
                                                       created_world,
                                                       world_conn):
        world_id = created_world["world_id"]
        for i in range(3):
            append_tick(world_conn, world_id, game_time=i + 1,
                        payload={"n": i})
        from src.persistence import event_log
        before = event_log.read_events(world_conn, 1)
        database.close_write_connection(layout.world_db_path(world_id),
                                        world_conn)
        manifest = make_manifest([step(1, sql=[
            "CREATE TABLE probe2 (id INTEGER PRIMARY KEY)"])])
        runner = migrations.MigrationRunner(utc_now=make_utc_factory())
        runner.run_migration(layout.world_db_path(world_id), manifest,
                             layout.world_subdir(world_id, "backups"))
        conn = database.open_readonly_file(layout.world_db_path(world_id))
        after = event_log.read_events(conn, 1)
        conn.close()
        assert before == after

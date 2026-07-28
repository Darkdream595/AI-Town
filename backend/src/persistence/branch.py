"""
branch-on-load（DOC-RELEASE-004 RULE-RELEASE-028..029）

读取非 tip 存档：
1. 暂停世界并完成写队列（调用方职责，DOC-TIME-009 Quiescence）
2. 当前 world.sqlite3 checkpoint 后移入 timelines\\<old>.sqlite3 并置只读
3. 以引用 Snapshot + 事件前缀（revision <= anchor）构建新 world.sqlite3：
   新 timeline_id、parent_timeline_id、branch_source_revision
4. Recovery Audit 后进入 paused_ready（调用方职责）

原子性：任一步失败整体回退、原 Timeline 不变；步骤 2/3 之间崩溃由
branch-journal.json 支撑启动幂等重试（§7）。
Revision 从 branch_source_revision 继续严格递增；Seed 不变（RULE-RELEASE-029）。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import event_log as evlog
from . import schema as sch
from . import snapshots as snap
from .constants import ReleaseError
from .database import (checkpoint_truncate, close_write_connection,
                       open_readonly_file, open_write_connection)

JOURNAL_NAME = "branch-journal.json"


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _set_readonly(path: Path) -> None:
    os.chmod(path, 0o444)


def _clear_readonly(path: Path) -> None:
    os.chmod(path, 0o666)


def _write_journal(world_dir: Path, payload: dict) -> None:
    tmp = world_dir / (JOURNAL_NAME + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp, world_dir / JOURNAL_NAME)


def read_journal(world_dir: Path | str) -> dict | None:
    path = Path(world_dir) / JOURNAL_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _remove_journal(world_dir: Path) -> None:
    journal = world_dir / JOURNAL_NAME
    if journal.exists():
        journal.unlink()


def branch_on_load(world_dir: Path | str, *, old_timeline_id: str,
                   new_timeline_id: str, anchor_revision: int,
                   utc_now=_default_utc) -> dict:
    """执行步骤 2/3；崩溃可经 recover_incomplete_branch 幂等续跑"""
    world_dir = Path(world_dir)
    db_path = world_dir / "world.sqlite3"
    timelines_dir = world_dir / "timelines"
    timelines_dir.mkdir(exist_ok=True)

    journal = {"old_timeline_id": old_timeline_id,
               "new_timeline_id": new_timeline_id,
               "anchor_revision": anchor_revision,
               "written_at": utc_now()}
    _write_journal(world_dir, journal)

    # --- 步骤 2：归档当前 Timeline ---
    archive_path = timelines_dir / (old_timeline_id + ".sqlite3")
    if db_path.exists():
        conn = open_write_connection(db_path)
        try:
            checkpoint_truncate(conn)
        finally:
            close_write_connection(db_path, conn)
        os.replace(db_path, archive_path)
        _set_readonly(archive_path)
    elif not archive_path.exists():
        raise ReleaseError("RELEASE_BRANCH_INCOMPLETE",
                           {"detail": "活动库与归档库同时缺失"})

    # --- 步骤 3：构建新 Timeline ---
    _build_branched_db(world_dir, journal)
    _remove_journal(world_dir)
    return {"archived": archive_path.name,
            "new_timeline_id": new_timeline_id,
            "branch_source_revision": anchor_revision}


def _build_branched_db(world_dir: Path, journal: dict) -> None:
    """幂等构建：已存在合法新库则跳过；来源数据只读（§7）"""
    world_dir = Path(world_dir)
    db_path = world_dir / "world.sqlite3"
    anchor = journal["anchor_revision"]
    source = _locate_source_db(world_dir, journal["old_timeline_id"])
    snapshot = _load_anchor_snapshot(world_dir, source, anchor)
    if db_path.exists():
        db_path.unlink()  # 半成品重建：来源只读，重建安全
    conn = open_write_connection(db_path)
    try:
        sch.create_world_database(conn, _read_world_id(source),
                                  journal["new_timeline_id"])
        conn.execute(
            "UPDATE world_meta SET parent_timeline_id=?,"
            " branch_source_revision=?, revision=?, game_time=? WHERE id=1",
            (journal["old_timeline_id"], anchor, anchor,
             snapshot["game_time"]))
        # 状态表：以引用 Snapshot 的行集为准（world_meta 行除外，已新写）
        for table, rows in snapshot["state_tables"].items():
            if table == "world_meta":
                continue
            for row in rows:
                columns = ",".join('"{}"'.format(c) for c in row)
                marks = ",".join("?" for _ in row)
                conn.execute('INSERT INTO "{}"({}) VALUES ({})'.format(
                    table, columns, marks), tuple(row.values()))
        # domain 投影恢复
        for name, data in snapshot.get("domain_projections", {}).items():
            restorer = sch.PROJECTION_RESTORERS.get(name)
            if restorer is not None:
                restorer(conn, data)
        # 事件前缀复制（RULE-RELEASE-018 连续性以复制后本库为准）
        prefix = evlog.read_events(source, 1, anchor)
        for row in prefix:
            conn.execute(
                "INSERT INTO event_log(revision, event_id, world_id,"
                " event_type, event_schema_version, game_time, causation_id,"
                " correlation_id, payload_json, render_json, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (row["revision"], row["event_id"], row["world_id"],
                 row["event_type"], row["event_schema_version"],
                 row["game_time"], row["causation_id"], row["correlation_id"],
                 row["payload_json"], row["render_json"], row["created_at"]))
        # 锚点及更早的 snapshot_meta 行随库携带（文件仍在共享 snapshots\\）
        rows = source.execute(
            "SELECT * FROM snapshot_meta WHERE anchor_revision <= ?",
            (anchor,)).fetchall()
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO snapshot_meta(snapshot_id,"
                " anchor_revision, file_name, file_sha256, created_at,"
                " trigger) VALUES (?,?,?,?,?,?)",
                (row["snapshot_id"], row["anchor_revision"], row["file_name"],
                 row["file_sha256"], row["created_at"], row["trigger"]))
        conn.commit()
    finally:
        close_write_connection(db_path, conn)
    source.close()


def _locate_source_db(world_dir: Path, old_timeline_id: str) -> sqlite3.Connection:
    archive = world_dir / "timelines" / (old_timeline_id + ".sqlite3")
    if archive.is_file():
        return open_readonly_file(archive)
    raise ReleaseError("RELEASE_BRANCH_INCOMPLETE",
                       {"detail": "来源 Timeline 归档缺失"})


def _read_world_id(source: sqlite3.Connection) -> str:
    row = source.execute("SELECT world_id FROM world_meta WHERE id=1").fetchone()
    if row is None:
        raise ReleaseError("RELEASE_DB_CORRUPT_METADATA",
                           {"detail": "来源库 world_meta 缺失"})
    return row[0]


def _load_anchor_snapshot(world_dir: Path, source: sqlite3.Connection,
                          anchor: int) -> dict:
    snapshot = snap.load_latest_valid_snapshot(
        source, world_dir / "snapshots", max_revision=anchor)
    if snapshot is None:
        raise ReleaseError("RELEASE_SNAPSHOT_UNAVAILABLE",
                           {"anchor_revision": anchor})
    return snapshot


def recover_incomplete_branch(world_dir: Path | str) -> dict | None:
    """§7：步骤 2/3 之间崩溃——world.sqlite3 缺失但归档与 journal 存在，
    自动幂等重试步骤 3；已完整则返回 None"""
    world_dir = Path(world_dir)
    journal = read_journal(world_dir)
    if journal is None:
        return None
    db_path = world_dir / "world.sqlite3"
    if db_path.exists():
        _remove_journal(world_dir)
        return None
    _build_branched_db(world_dir, journal)
    _remove_journal(world_dir)
    return {"recovered_branch": True,
            "new_timeline_id": journal["new_timeline_id"],
            "branch_source_revision": journal["anchor_revision"]}


def is_readonly(path: Path | str) -> bool:
    return not os.access(path, os.W_OK)

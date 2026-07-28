"""
多世界注册表生命周期（DOC-RELEASE-005）

- RULE-RELEASE-032：同一时刻至多一个 open 世界；并发打开按 command_id 幂等拒绝
- RULE-RELEASE-033：CSPRNG 生成 ULID 与 128-bit Seed；同事务创建，失败整体回退
- RULE-RELEASE-034：删除默认可恢复（trash\\ 30 天）；Purge 需确认或到期清理 + 审计
- RULE-RELEASE-037：display_name 仅显示用；路径永远只用 world_id
- RULE-RELEASE-038：启动一致性扫描（孤儿目录/悬空记录 → needs_attention）
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.foundation.id_generator import generate_ulid

from . import saves as saves_mod
from . import schema as sch
from . import snapshots as snap
from .constants import TRASH_RETENTION_DAYS, ReleaseError
from .database import (checkpoint_truncate, close_write_connection,
                       open_write_connection)
from .paths import UserDataLayout, force_rmtree

#: 进程内单开守卫（RULE-RELEASE-032）
_OPEN_WORLD: dict[str, str | None] = {"world_id": None}


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc)


def _default_seed() -> str:
    """128-bit Seed（RULE-RELEASE-033，CSPRNG）"""
    return secrets.token_hex(16)


def open_world_id() -> str | None:
    return _OPEN_WORLD["world_id"]


class WorldRegistry:
    """DES-RELEASE-010 生命周期状态机的持久层执行体"""

    def __init__(self, layout: UserDataLayout, app_conn: sqlite3.Connection,
                 utc_now=_default_utc, new_ulid=generate_ulid,
                 seed_fn=_default_seed) -> None:
        self.layout = layout
        self.conn = app_conn
        self._utc_now = utc_now
        self._new_ulid = new_ulid
        self._seed_fn = seed_fn

    # ------------------------------------------------------------ 查询
    def get_world(self, world_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM world_registry WHERE world_id=?",
            (world_id,)).fetchone()
        if row is None:
            raise ReleaseError("RELEASE_WORLD_NOT_FOUND",
                               {"world_id": world_id})
        record = dict(row)
        record["lifecycle"] = self._lifecycle_of(record)
        return record

    def list_worlds(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM world_registry ORDER BY created_at ASC").fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["lifecycle"] = self._lifecycle_of(record)
            result.append(record)
        return result

    def _lifecycle_of(self, record: dict) -> str:
        if record["deleted_at"] is not None:
            return "trashed"
        if _OPEN_WORLD["world_id"] == record["world_id"]:
            return "active"
        return "closed"

    def _idempotent(self, command_id: str, payload: dict, fn) -> dict:
        row = self.conn.execute(
            "SELECT payload_hash, result_json FROM idempotency_keys"
            " WHERE command_id=?", (command_id,)).fetchone()
        payload_hash = hashlib.sha256(
            snap.canonical_json_bytes(payload)).hexdigest()
        if row is not None:
            if row[0] != payload_hash:
                raise ReleaseError("RELEASE_WORLD_OPEN_FAILED",
                                   {"detail": "command_id 载荷冲突"})
            return json.loads(row[1])
        result = fn()
        self.conn.execute(
            "INSERT INTO idempotency_keys(command_id, payload_hash,"
            " result_json, created_at) VALUES (?,?,?,?)",
            (command_id, payload_hash,
             json.dumps(result, sort_keys=True, ensure_ascii=False),
             self._utc_now()))
        self.conn.commit()
        return result

    def _audit(self, action: str, world_id: str | None,
               detail: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_log(audit_id, at, action, world_id, detail_json)"
            " VALUES (?,?,?,?,?)",
            (self._new_ulid(), self._utc_now(), action, world_id,
             json.dumps(detail, sort_keys=True) if detail else None))
        self.conn.commit()

    # ------------------------------------------------------------ 创建
    def create_world(self, *, command_id: str, display_name: str) -> dict:
        """RULE-RELEASE-033：任一步失败整体回退且不留半创建目录"""
        payload = {"op": "create_world", "display_name": str(display_name)}

        def do_create() -> dict:
            world_id = self._new_ulid()
            seed_hex = self._seed_fn()
            timeline_id = self._new_ulid()
            created_at = self._utc_now()
            world_dir = self.layout.ensure_world_layout(world_id)
            db_path = self.layout.world_db_path(world_id)
            conn = None
            try:
                conn = open_write_connection(db_path)
                sch.create_world_database(conn, world_id, timeline_id)
                self.conn.execute(
                    "INSERT INTO world_registry(world_id, display_name,"
                    " seed_hex, schema_version, created_at, last_opened_at,"
                    " deleted_at, origin_world_id)"
                    " VALUES (?,?,?,?,?,NULL,NULL,NULL)",
                    (world_id, payload["display_name"], seed_hex,
                     sch.WORLD_SCHEMA_CURRENT, created_at))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                if conn is not None:
                    close_write_connection(db_path, conn)
                force_rmtree(world_dir)
                raise
            close_write_connection(db_path, conn)
            self._audit("world_created", world_id)
            return {"world_id": world_id, "display_name": payload["display_name"],
                    "seed_hex": seed_hex, "timeline_id": timeline_id,
                    "schema_version": sch.WORLD_SCHEMA_CURRENT,
                    "created_at": created_at}

        return self._idempotent(command_id, payload, do_create)

    # ------------------------------------------------------------ 打开/关闭
    def open_world(self, *, command_id: str, world_id: str) -> dict:
        """RULE-RELEASE-032：单开约束；注册表校验后由恢复链接管（DOC-RELEASE-006）"""
        payload = {"op": "open_world", "world_id": world_id}

        def do_open() -> dict:
            record = self.get_world(world_id)
            if record["lifecycle"] == "trashed":
                raise ReleaseError("RELEASE_WORLD_NOT_FOUND",
                                   {"world_id": world_id, "state": "trashed"})
            current = _OPEN_WORLD["world_id"]
            if current is not None and current != world_id:
                raise ReleaseError("RELEASE_WORLD_ALREADY_OPEN",
                                   {"open_world_id": current})
            _OPEN_WORLD["world_id"] = world_id
            self.conn.execute(
                "UPDATE world_registry SET last_opened_at=? WHERE world_id=?",
                (self._utc_now(), world_id))
            self.conn.commit()
            self._audit("world_opened", world_id)
            return {"world_id": world_id, "opened": True}

        return self._idempotent(command_id, payload, do_open)

    def close_world(self, *, command_id: str) -> dict:
        """DOC-RELEASE-001 §6：暂停 Tick → 在途事务 → checkpoint → 关库；
        RULE-RELEASE-022/026：干净关闭必建 Snapshot 与自动恢复点"""
        payload = {"op": "close_world"}

        def do_close() -> dict:
            world_id = _OPEN_WORLD["world_id"]
            if world_id is None:
                return {"closed": False, "detail": "no_open_world"}
            db_path = self.layout.world_db_path(world_id)
            snapshots_dir = self.layout.world_subdir(world_id, "snapshots")
            conn = open_write_connection(db_path)
            snapshot_meta = None
            try:
                meta = snap.build_snapshot(conn, snapshots_dir,
                                           "clean_shutdown",
                                           utc_now=self._utc_now,
                                           new_ulid=self._new_ulid)
                saves_mod.record_auto_save(conn, meta, utc_now=self._utc_now,
                                           new_ulid=self._new_ulid)
                checkpoint_truncate(conn)
                snapshot_meta = meta
            finally:
                close_write_connection(db_path, conn)
            _OPEN_WORLD["world_id"] = None
            self._audit("world_closed", world_id)
            return {"closed": True, "world_id": world_id,
                    "snapshot": snapshot_meta}

        return self._idempotent(command_id, payload, do_close)

    def rename_world(self, *, command_id: str, world_id: str,
                     display_name: str) -> dict:
        """RULE-RELEASE-037：重命名只改 registry 行，路径不变"""
        payload = {"op": "rename_world", "world_id": world_id,
                   "display_name": str(display_name)}

        def do_rename() -> dict:
            self.get_world(world_id)
            self.conn.execute(
                "UPDATE world_registry SET display_name=? WHERE world_id=?",
                (payload["display_name"], world_id))
            self.conn.commit()
            self._audit("world_renamed", world_id)
            return {"world_id": world_id,
                    "display_name": payload["display_name"]}

        return self._idempotent(command_id, payload, do_rename)

    # ------------------------------------------------------------ 删除/还原/Purge
    def delete_world(self, *, command_id: str, world_id: str,
                     confirmed: bool = False) -> dict:
        """RULE-RELEASE-034：软删除 30 天可还原；当前 open 世界须先关闭"""
        payload = {"op": "delete_world", "world_id": world_id}

        def do_delete() -> dict:
            record = self.get_world(world_id)
            if record["lifecycle"] == "trashed":
                return {"world_id": world_id, "trashed": True,
                        "already": True}
            if record["lifecycle"] == "active":
                raise ReleaseError("RELEASE_WORLD_OPEN_FAILED",
                                   {"detail": "世界仍打开"})
            if not confirmed:
                raise ReleaseError("RELEASE_SAVE_CONFIRM_REQUIRED",
                                   {"op": "delete_world"})
            self.conn.execute(
                "UPDATE world_registry SET deleted_at=? WHERE world_id=?",
                (self._utc_now(), world_id))
            self.conn.commit()
            self._move_to_trash(world_id)
            self._audit("world_trashed", world_id)
            return {"world_id": world_id, "trashed": True,
                    "deleted_at": self._utc_now()}

        return self._idempotent(command_id, payload, do_delete)

    def _move_to_trash(self, world_id: str) -> None:
        """原子移动；跨卷失败回退复制+校验+删除（§7）"""
        source = self.layout.world_dir(world_id)
        target = self.layout.trash_world_dir(world_id)
        if target.exists():
            force_rmtree(target)
        try:
            shutil.move(str(source), str(target))
        except OSError:
            shutil.copytree(str(source), str(target))
            self._verify_tree_equal(source, target)
            force_rmtree(source)

    @staticmethod
    def _verify_tree_equal(source: Path, target: Path) -> None:
        def fingerprint(root: Path) -> dict:
            result = {}
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    result[str(path.relative_to(root))] = path.stat().st_size
            return result
        if fingerprint(source) != fingerprint(target):
            raise ReleaseError("RELEASE_IO_ERROR",
                               {"detail": "跨卷复制校验失败"})

    def restore_world(self, *, command_id: str, world_id: str) -> dict:
        """30 天内整体还原（RULE-RELEASE-034）"""
        payload = {"op": "restore_world", "world_id": world_id}

        def do_restore() -> dict:
            record = self.get_world(world_id)
            if record["lifecycle"] != "trashed":
                raise ReleaseError("RELEASE_WORLD_NOT_FOUND",
                                   {"world_id": world_id,
                                    "state": record["lifecycle"]})
            deadline = _parse_utc(record["deleted_at"]) + timedelta(
                days=TRASH_RETENTION_DAYS)
            if _parse_utc(self._utc_now()) > deadline:
                raise ReleaseError("RELEASE_SAVE_TRASH_EXPIRED",
                                   {"world_id": world_id})
            source = self.layout.trash_world_dir(world_id)
            target = self.layout.world_dir(world_id)
            if not source.exists():
                raise ReleaseError("RELEASE_WORLD_NEEDS_ATTENTION",
                                   {"detail": "trash 目录缺失"})
            if target.exists():
                raise ReleaseError("RELEASE_WORLD_OPEN_FAILED",
                                   {"detail": "目标目录已存在"})
            shutil.move(str(source), str(target))
            self.conn.execute(
                "UPDATE world_registry SET deleted_at=NULL WHERE world_id=?",
                (world_id,))
            self.conn.commit()
            self._audit("world_restored", world_id)
            return {"world_id": world_id, "restored": True}

        return self._idempotent(command_id, payload, do_restore)

    def purge_world(self, *, command_id: str, world_id: str,
                    confirmed: bool = False) -> dict:
        """RULE-RELEASE-034：Purge 仅玩家二次确认或启动清理到期执行"""
        payload = {"op": "purge_world", "world_id": world_id}

        def do_purge() -> dict:
            record = self.get_world(world_id)
            if record["lifecycle"] != "trashed":
                raise ReleaseError("RELEASE_WORLD_NOT_FOUND",
                                   {"world_id": world_id,
                                    "state": record["lifecycle"]})
            if not confirmed:
                raise ReleaseError("RELEASE_SAVE_CONFIRM_REQUIRED",
                                   {"op": "purge_world"})
            force_rmtree(self.layout.trash_world_dir(world_id))
            self.conn.execute(
                "DELETE FROM world_registry WHERE world_id=?", (world_id,))
            self.conn.commit()
            self._audit("world_purged", world_id,
                        {"path": "player_confirmed"})
            return {"world_id": world_id, "purged": True}

        return self._idempotent(command_id, payload, do_purge)

    def purge_expired_trash(self) -> list[str]:
        """启动清理任务：超期条目物理删除并写审计日志（RULE-RELEASE-034）"""
        now = _parse_utc(self._utc_now())
        purged: list[str] = []
        for record in self.list_worlds():
            if record["lifecycle"] != "trashed":
                continue
            deadline = _parse_utc(record["deleted_at"]) + timedelta(
                days=TRASH_RETENTION_DAYS)
            if now <= deadline:
                continue
            world_id = record["world_id"]
            force_rmtree(self.layout.trash_world_dir(world_id))
            self.conn.execute(
                "DELETE FROM world_registry WHERE world_id=?", (world_id,))
            self.conn.commit()
            self._audit("world_purged", world_id, {"path": "expired"})
            purged.append(world_id)
        return purged

    # ------------------------------------------------------------ 一致性扫描
    def scan_consistency(self) -> dict:
        """RULE-RELEASE-038：孤儿目录与悬空记录标记 needs_attention，只读列出"""
        registered = {r["world_id"] for r in self.list_worlds()}
        world_dirs = {p.name for p in self.layout.iter_world_dirs()}
        trash_dirs = {p.name for p in self.layout.iter_trash_dirs()}
        orphans = sorted(world_dirs - registered)
        dangling = sorted(
            wid for wid in registered
            if wid not in world_dirs and wid not in trash_dirs)
        return {"orphan_directories": orphans,
                "dangling_records": dangling,
                "needs_attention": sorted(orphans + dangling)}

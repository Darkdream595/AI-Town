"""
Snapshot 生成、加载与保留（DOC-RELEASE-003）

- RULE-RELEASE-020：只锚定完整已提交 Revision；生成期间新事务不混入
- RULE-RELEASE-021：write-temp → fsync → 原子 rename；同事务记录 snapshot_meta；
  哈希校验失败的 Snapshot 视为不存在
- RULE-RELEASE-022：触发点固定；每 Timeline 至少保留最近 2 个有效 Snapshot；
  删除前确认无 SaveRecord 引用
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.foundation.id_generator import generate_ulid

from . import schema as sch
from . import zstd_codec
from .constants import (SNAPSHOT_FORMAT_VERSION, SNAPSHOT_KEEP_MIN,
                        SNAPSHOT_TRIGGERS, ReleaseError)


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def canonical_json_bytes(obj: object) -> bytes:
    """Canonical JSON：键排序、UTF-8、无多余空白（DOC-RELEASE-003 §3）"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _export_state_tables(conn: sqlite3.Connection) -> dict:
    """导出注册表全部状态表完整行集；缺表即校验失败（§5.2）"""
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    tables: dict[str, list] = {}
    for name in sch.STATE_TABLE_REGISTRY:
        if name not in existing:
            raise ReleaseError("RELEASE_SNAPSHOT_INVALID",
                               {"missing_table": name})
        rows = conn.execute(
            'SELECT * FROM "{}" ORDER BY rowid'.format(name)).fetchall()
        tables[name] = [dict(r) for r in rows]
    return tables


def build_snapshot(conn: sqlite3.Connection, snapshots_dir: Path | str,
                   trigger: str, utc_now=_default_utc,
                   new_ulid=generate_ulid) -> dict:
    """DES-RELEASE-007：在写队列内取一致读视图生成 Snapshot 并登记元数据

    anchor_revision 唯一：当前 Revision 已有校验通过的 Snapshot 时直接复用，
    不重复写文件（同一锚点的规范化状态必然逐字节相同）。
    """
    if trigger not in SNAPSHOT_TRIGGERS:
        raise ValueError(f"非法 Snapshot 触发类型: {trigger}")
    snapshots_dir = Path(snapshots_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    meta = sch.read_world_meta(conn)
    existing = conn.execute(
        "SELECT * FROM snapshot_meta WHERE anchor_revision=?",
        (meta["revision"],)).fetchone()
    if existing is not None:
        try:
            load_snapshot_file(snapshots_dir, existing["file_name"],
                               existing["file_sha256"])
            return {"snapshot_id": existing["snapshot_id"],
                    "anchor_revision": existing["anchor_revision"],
                    "file_name": existing["file_name"],
                    "file_sha256": existing["file_sha256"],
                    "trigger": existing["trigger"], "reused": True}
        except ReleaseError:
            pass  # 既有锚点文件损坏：重建覆盖（哈希失败视为不存在）
        conn.execute("DELETE FROM snapshot_meta WHERE snapshot_id=?",
                     (existing["snapshot_id"],))
    snapshot_id = new_ulid()
    content = {
        "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
        "snapshot_id": snapshot_id,
        "world_id": meta["world_id"],
        "timeline_id": meta["timeline_id"],
        "anchor_revision": meta["revision"],
        "game_time": meta["game_time"],
        "schema_version": meta["schema_version"],
        "state_tables": _export_state_tables(conn),
        "domain_projections": {
            name: exporter(conn)
            for name, exporter in sch.PROJECTION_EXPORTERS.items()},
    }
    content["content_sha256"] = _sha256_bytes(canonical_json_bytes(content))
    file_name = "{}-{}{}".format(meta["revision"], snapshot_id,
                                 ".snap.zst")
    payload = zstd_codec.compress(canonical_json_bytes(content))
    # RULE-RELEASE-021：write-temp → fsync → 原子 rename
    tmp_path = snapshots_dir / (file_name + ".tmp")
    final_path = snapshots_dir / file_name
    with open(tmp_path, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, final_path)
    file_hash = _sha256_file(final_path)
    conn.execute(
        "INSERT INTO snapshot_meta(snapshot_id, anchor_revision, file_name,"
        " file_sha256, created_at, trigger) VALUES (?,?,?,?,?,?)",
        (snapshot_id, meta["revision"], file_name, file_hash, utc_now(),
         trigger))
    conn.commit()
    return {"snapshot_id": snapshot_id, "anchor_revision": meta["revision"],
            "file_name": file_name, "file_sha256": file_hash,
            "trigger": trigger}


def load_snapshot_file(snapshots_dir: Path | str, file_name: str,
                       expected_sha256: str) -> dict:
    """读取并校验 Snapshot 文件；哈希失败视为不存在（RULE-RELEASE-021）"""
    path = Path(snapshots_dir) / file_name
    if not path.is_file():
        raise ReleaseError("RELEASE_SNAPSHOT_UNAVAILABLE",
                           {"file_name": file_name})
    if _sha256_file(path) != expected_sha256:
        raise ReleaseError("RELEASE_SNAPSHOT_HASH_MISMATCH",
                           {"file_name": file_name})
    content = json.loads(zstd_codec.decompress(path.read_bytes()))
    embedded = content.pop("content_sha256", None)
    if embedded != _sha256_bytes(canonical_json_bytes(content)):
        raise ReleaseError("RELEASE_SNAPSHOT_HASH_MISMATCH",
                           {"file_name": file_name, "scope": "content"})
    content["content_sha256"] = embedded
    return content


def load_latest_valid_snapshot(conn: sqlite3.Connection,
                               snapshots_dir: Path | str,
                               max_revision: int | None = None) -> dict | None:
    """DES-RELEASE-007：取 anchor 最大且校验通过的 Snapshot；无效回退更早"""
    sql = "SELECT * FROM snapshot_meta"
    params: tuple = ()
    if max_revision is not None:
        sql += " WHERE anchor_revision <= ?"
        params = (max_revision,)
    rows = conn.execute(sql + " ORDER BY anchor_revision DESC",
                        params).fetchall()
    for row in rows:
        try:
            snapshot = load_snapshot_file(snapshots_dir, row["file_name"],
                                          row["file_sha256"])
        except ReleaseError:
            continue  # 哈希失败/文件缺失视为不存在，回退更早（§7）
        snapshot["_meta"] = dict(row)
        return snapshot
    return None


def referenced_snapshot_ids(conn: sqlite3.Connection) -> set[str]:
    """被任何 SaveRecord（含 Save Trash 内）引用的 Snapshot（RULE-RELEASE-027）"""
    rows = conn.execute(
        "SELECT DISTINCT snapshot_id FROM save_records").fetchall()
    return {r[0] for r in rows}


def enforce_snapshot_retention(conn: sqlite3.Connection,
                               snapshots_dir: Path | str,
                               keep: int = SNAPSHOT_KEEP_MIN) -> list[str]:
    """RULE-RELEASE-022：保留最近 keep 个校验通过的 Snapshot；
    删除前确认存在更新有效 Snapshot 且无任何 SaveRecord 引用"""
    snapshots_dir = Path(snapshots_dir)
    rows = conn.execute(
        "SELECT * FROM snapshot_meta ORDER BY anchor_revision DESC").fetchall()
    valid: list[sqlite3.Row] = []
    for row in rows:
        try:
            load_snapshot_file(snapshots_dir, row["file_name"],
                               row["file_sha256"])
            valid.append(row)
        except ReleaseError:
            continue
    protected = referenced_snapshot_ids(conn)
    deleted: list[str] = []
    for row in valid[keep:]:
        if row["snapshot_id"] in protected:
            continue  # 引用保护：绝不删除（§10 验收）
        path = snapshots_dir / row["file_name"]
        if path.exists():
            path.unlink()
        conn.execute("DELETE FROM snapshot_meta WHERE snapshot_id=?",
                     (row["snapshot_id"],))
        deleted.append(row["snapshot_id"])
    conn.commit()
    return deleted


def cleanup_orphan_temp_files(snapshots_dir: Path | str) -> list[str]:
    """§7：Snapshot 写入中途崩溃只留下临时文件；启动时清理"""
    snapshots_dir = Path(snapshots_dir)
    if not snapshots_dir.is_dir():
        return []
    removed = []
    for path in snapshots_dir.iterdir():
        if path.suffix == ".tmp":
            path.unlink()
            removed.append(path.name)
    return removed

"""
世界导出/导入（DOC-RELEASE-005 RULE-RELEASE-035..036）

- 导出：世界 closed + checkpoint 后进行；包只含 manifest、数据库（活动与归档
  Timeline）、snapshots\\、saves\\；禁止 logs/diagnostics/backups/Secret/绝对路径
- 导入：校验 manifest schema、逐文件 SHA-256、schema_version ∈ 支持区间；
  world_id 冲突分配新 ULID 并记录 origin_world_id；任何失败不落地文件
- zip-slip 防护：拒绝绝对路径、`..`、盘符与保留设备名
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import schema as sch
from . import secret_scan
from .constants import (DISK_PREFLIGHT_MULTIPLIER, PACKAGE_FILE_SUFFIX,
                        PACKAGE_FORMAT_VERSION, PACKAGE_KIND, ReleaseError)
from .database import (checkpoint_truncate, close_write_connection,
                       open_write_connection)
from .paths import UserDataLayout, force_rmtree, sanitize_ascii_filename

#: 导出内容白名单（RULE-RELEASE-035）
_EXPORT_INCLUDE = ("world.sqlite3", "timelines", "snapshots", "saves")

_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *{"COM%d" % i for i in range(1, 10)},
                   *{"LPT%d" % i for i in range(1, 10)}}


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_export_files(world_dir: Path) -> list[Path]:
    files: list[Path] = []
    main = world_dir / "world.sqlite3"
    if main.is_file():
        files.append(main)
    for subdir in ("timelines", "snapshots", "saves"):
        base = world_dir / subdir
        if base.is_dir():
            files.extend(sorted(p for p in base.rglob("*") if p.is_file()))
    return files


def export_world(layout: UserDataLayout, app_conn: sqlite3.Connection,
                 *, world_id: str, target_path: Path | str,
                 app_package_version: str, utc_now=_default_utc,
                 free_space=None) -> dict:
    """DES-RELEASE-011：全有或全无；Secret 扫描命中即中止（RULE-RELEASE-035）"""
    row = app_conn.execute(
        "SELECT * FROM world_registry WHERE world_id=?", (world_id,)).fetchone()
    if row is None:
        raise ReleaseError("RELEASE_WORLD_NOT_FOUND", {"world_id": world_id})
    world_dir = layout.world_dir(world_id)
    if not world_dir.is_dir():
        raise ReleaseError("RELEASE_WORLD_NEEDS_ATTENTION",
                           {"detail": "世界目录缺失"})
    db_path = layout.world_db_path(world_id)
    conn = open_write_connection(db_path)
    try:
        checkpoint_truncate(conn)
    finally:
        close_write_connection(db_path, conn)

    files = _iter_export_files(world_dir)
    file_entries = []
    for path in files:
        relative = path.relative_to(world_dir).as_posix()
        file_entries.append({"path": relative,
                             "sha256": _sha256_file(path),
                             "size_bytes": path.stat().st_size})
    manifest = {
        "package_format_version": PACKAGE_FORMAT_VERSION,
        "package_kind": PACKAGE_KIND,
        "world_id": row["world_id"],
        "origin_world_id": row["origin_world_id"],
        "display_name": row["display_name"],
        "seed_hex": row["seed_hex"],
        "schema_version": row["schema_version"],
        "app_package_version": app_package_version,
        "exported_at": utc_now(),
        "files": file_entries,
    }
    # Secret 扫描（与 DOC-RELEASE-010 同一扫描器）：manifest 与文件内容
    manifest_bytes = json.dumps(manifest, ensure_ascii=False,
                                sort_keys=True).encode("utf-8")
    structural_hashes = tuple(
        [manifest["seed_hex"]] + [e["sha256"] for e in file_entries])
    scan = secret_scan.scan_bytes(manifest_bytes, (world_dir,),
                                  excluded_values=structural_hashes)
    if not scan["clean"]:
        raise ReleaseError("RELEASE_SECRET_SCAN_HIT",
                           {"scope": "manifest", "hits": len(scan["hits"])})
    for path in files:
        scan = secret_scan.scan_paths([path], (world_dir,))
        if not scan["clean"]:
            raise ReleaseError("RELEASE_SECRET_SCAN_HIT",
                               {"scope": path.name})

    target_path = Path(target_path)
    if target_path.is_dir():
        name = "{}-{}{}".format(
            sanitize_ascii_filename(row["display_name"]), world_id,
            PACKAGE_FILE_SUFFIX)
        target_path = target_path / name
    # RULE-RELEASE-042：磁盘预检（导出按内容 2 倍估算）
    total = sum(e["size_bytes"] for e in file_entries)
    free = (free_space or (lambda p: shutil.disk_usage(str(p.parent)).free))(
        target_path)
    if free < total * DISK_PREFLIGHT_MULTIPLIER:
        raise ReleaseError("RELEASE_DISK_SPACE_INSUFFICIENT",
                           {"required": total * DISK_PREFLIGHT_MULTIPLIER})

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED,
                             allowZip64=True) as zf:
            zf.writestr("manifest.json", manifest_bytes)
            for path in files:
                zf.write(path, path.relative_to(world_dir).as_posix())
        # 导出后复验：重开 zip 核对逐文件哈希
        _verify_zip_hashes(tmp_path, file_entries)
        tmp_path.replace(target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return {"target": str(target_path), "files": len(file_entries),
            "size_bytes": target_path.stat().st_size}


def _verify_zip_hashes(zip_path: Path, entries: list[dict]) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for entry in entries:
            with zf.open(entry["path"]) as fh:
                digest = hashlib.sha256()
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ReleaseError("RELEASE_EXPORT_BLOCKED",
                                   {"detail": "导出复验哈希不符",
                                    "path": entry["path"]})


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------

def _assert_zip_entry_safe(name: str) -> None:
    """zip-slip 防护（§9）"""
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise ReleaseError("RELEASE_IMPORT_INVALID",
                           {"entry": name, "reason": "absolute_path"})
    parts = name.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ReleaseError("RELEASE_IMPORT_INVALID",
                           {"entry": name, "reason": "parent_traversal"})
    stem = parts[-1].split(".")[0].upper()
    if stem in _RESERVED_NAMES:
        raise ReleaseError("RELEASE_IMPORT_INVALID",
                           {"entry": name, "reason": "reserved_name"})


def import_world(layout: UserDataLayout, app_conn: sqlite3.Connection,
                 *, source_path: Path | str, new_ulid,
                 min_supported: int = sch.WORLD_SCHEMA_MIN_SUPPORTED,
                 current: int = sch.WORLD_SCHEMA_CURRENT,
                 free_space=None) -> dict:
    """RULE-RELEASE-036：任何校验失败不落地任何文件"""
    source_path = Path(source_path)
    if not source_path.is_file():
        raise ReleaseError("RELEASE_IMPORT_INVALID", {"reason": "not_found"})
    with zipfile.ZipFile(source_path) as zf:
        names = zf.namelist()
        for name in names:
            _assert_zip_entry_safe(name)
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (KeyError, ValueError):
            raise ReleaseError("RELEASE_IMPORT_INVALID",
                               {"reason": "manifest_unreadable"})
        _validate_manifest(manifest, min_supported, current)
        # 逐文件 SHA-256 校验（在解压落地之前）
        file_entries = {e["path"]: e for e in manifest["files"]}
        for relative, entry in file_entries.items():
            _assert_zip_entry_safe(relative)
            if relative not in names:
                raise ReleaseError("RELEASE_IMPORT_INVALID",
                                   {"entry": relative, "reason": "missing"})
            with zf.open(relative) as fh:
                digest = hashlib.sha256()
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ReleaseError("RELEASE_IMPORT_INVALID",
                                   {"entry": relative, "reason": "sha256"})

        # world_id 冲突 → 新 ULID + origin_world_id（§7）
        original_id = manifest["world_id"]
        world_id = original_id
        origin_world_id = None
        registered = {r[0] for r in app_conn.execute(
            "SELECT world_id FROM world_registry").fetchall()}
        existing_dirs = {p.name for p in layout.iter_world_dirs()} \
            | {p.name for p in layout.iter_trash_dirs()}
        if world_id in registered or world_id in existing_dirs:
            world_id = new_ulid()
            origin_world_id = original_id

        total = sum(e["size_bytes"] for e in manifest["files"])
        free = (free_space
                or (lambda p: shutil.disk_usage(str(p)).free))(layout.worlds_dir)
        if free < total * DISK_PREFLIGHT_MULTIPLIER:
            raise ReleaseError("RELEASE_DISK_SPACE_INSUFFICIENT",
                               {"required": total * DISK_PREFLIGHT_MULTIPLIER})

        # 解压到临时目录，全部完成后原子改名（全有或全无）
        world_dir = layout.ensure_world_layout(world_id)
        staging = layout.worlds_dir / (".staging-" + world_id)
        if staging.exists():
            force_rmtree(staging)
        staging.mkdir(parents=True)
        try:
            for relative in file_entries:
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(relative) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
            for path in staging.rglob("*"):
                if path.is_file():
                    destination = world_dir / path.relative_to(staging)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(destination))
        except Exception:
            force_rmtree(staging)
            force_rmtree(world_dir)
            raise
        force_rmtree(staging)

    app_conn.execute(
        "INSERT INTO world_registry(world_id, display_name, seed_hex,"
        " schema_version, created_at, last_opened_at, deleted_at,"
        " origin_world_id) VALUES (?,?,?,?,?,NULL,NULL,?)",
        (world_id, manifest["display_name"], manifest["seed_hex"],
         manifest["schema_version"], _default_utc(), origin_world_id))
    app_conn.commit()
    return {"world_id": world_id, "origin_world_id": origin_world_id,
            "display_name": manifest["display_name"],
            "schema_version": manifest["schema_version"]}


def _validate_manifest(manifest: dict, min_supported: int,
                       current: int) -> None:
    required = ("package_format_version", "package_kind", "world_id",
                "display_name", "seed_hex", "schema_version",
                "app_package_version", "exported_at", "files")
    if not isinstance(manifest, dict) or any(k not in manifest
                                             for k in required):
        raise ReleaseError("RELEASE_IMPORT_INVALID", {"reason": "schema"})
    if manifest["package_kind"] != PACKAGE_KIND:
        raise ReleaseError("RELEASE_IMPORT_INVALID", {"reason": "kind"})
    if int(manifest["package_format_version"]) != PACKAGE_FORMAT_VERSION:
        raise ReleaseError("RELEASE_IMPORT_INVALID", {"reason": "format"})
    version = int(manifest["schema_version"])
    if version > current:
        raise ReleaseError("RELEASE_IMPORT_TOO_NEW",
                           {"schema_version": version})
    if version < min_supported:
        raise ReleaseError("RELEASE_IMPORT_TOO_OLD",
                           {"schema_version": version,
                            "min_supported": min_supported})

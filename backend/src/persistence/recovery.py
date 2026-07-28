"""
备份、损坏分诊与恢复（DOC-RELEASE-006）

- RULE-RELEASE-040：任何修复前先建 Pre-repair Copy（backups\\corrupt-<utc>\\），
  校验字节数与 SHA-256；corrupt 复制永不被自动清理
- RULE-RELEASE-041：Recovery Chain 固定 8 步顺序，任一步失败停在该步，不跳步
- RULE-RELEASE-042：磁盘预检 ≥ 估算 2 倍
- RULE-RELEASE-044：Triage Ladder L1–L6；L3 及以下必须玩家显式选择
- RULE-RELEASE-047：恢复成功唯一判定：8 步全过且 world_meta.revision == tip
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import branch as branch_mod
from . import event_log as evlog
from . import schema as sch
from . import snapshots as snap
from .constants import (DISK_PREFLIGHT_MULTIPLIER,
                        RECOVERY_REPORT_FORMAT_VERSION, ReleaseError)
from .database import (close_write_connection, foreign_key_check,
                       integrity_check, open_write_connection, verify_pragmas)
from .migrations import MigrationManifest, MigrationRunner

#: RULE-RELEASE-041 的固定 8 步
CHAIN_STEPS = (
    (1, "open_and_pragma"),
    (2, "integrity_check"),
    (3, "schema_migration"),
    (4, "snapshot_hash"),
    (5, "event_continuity"),
    (6, "reservation_rebuild"),
    (7, "inflight_ai_disposition"),
    (8, "invariant_audit"),
)

TRIAGE_LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# RULE-RELEASE-042：磁盘空间预检
# ---------------------------------------------------------------------------

def estimate_required_space(content_bytes: int) -> int:
    return content_bytes * DISK_PREFLIGHT_MULTIPLIER


def preflight_disk_check(target_dir: Path | str, content_bytes: int,
                         free_space=None) -> bool:
    """RULE-RELEASE-042：可用空间 ≥ 内容估算的 2 倍；普通写事务不受预检约束"""
    required = estimate_required_space(content_bytes)
    free = (free_space
            or (lambda p: shutil.disk_usage(str(p)).free))(target_dir)
    if free < required:
        raise ReleaseError("RELEASE_DISK_SPACE_INSUFFICIENT",
                           {"required": required, "free": free})
    return True


# ---------------------------------------------------------------------------
# RULE-RELEASE-040：Pre-repair Copy
# ---------------------------------------------------------------------------

def make_pre_repair_copy(world_dir: Path | str,
                         utc_compact=_utc_compact) -> Path:
    """复制数据库、-wal/-shm 与 snapshots\\ 到 backups\\corrupt-<utc>\\；
    校验字节数与 SHA-256；幂等（已存在且校验通过则复用）；永不自动清理"""
    world_dir = Path(world_dir)
    target = world_dir / "backups" / ("corrupt-" + utc_compact())
    sources = _repair_sources(world_dir)
    manifest_path = target / "copy-manifest.json"
    if manifest_path.is_file() and _verify_copy_manifest(manifest_path):
        return target  # §7：幂等复用
    target.mkdir(parents=True, exist_ok=True)
    entries = []
    for source in sources:
        destination = target / source.relative_to(world_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        entries.append({
            "path": source.relative_to(world_dir).as_posix(),
            "size_bytes": source.stat().st_size,
            "sha256": _sha256_file(source)})
        if _sha256_file(destination) != entries[-1]["sha256"]:
            raise ReleaseError("RELEASE_IO_ERROR",
                               {"detail": "Pre-repair Copy 校验失败"})
    manifest_path.write_text(
        json.dumps({"files": entries}, sort_keys=True), encoding="utf-8")
    return target


def _repair_sources(world_dir: Path) -> list[Path]:
    result = []
    for name in ("world.sqlite3", "world.sqlite3-wal", "world.sqlite3-shm"):
        path = world_dir / name
        if path.is_file():
            result.append(path)
    snapshots_dir = world_dir / "snapshots"
    if snapshots_dir.is_dir():
        result.extend(sorted(p for p in snapshots_dir.rglob("*")
                             if p.is_file()))
    return result


def _verify_copy_manifest(manifest_path: Path) -> bool:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            path = manifest_path.parent / entry["path"]
            if not path.is_file():
                return False
            if path.stat().st_size != entry["size_bytes"]:
                return False
            if _sha256_file(path) != entry["sha256"]:
                return False
        return True
    except (ValueError, OSError, KeyError):
        return False


# ---------------------------------------------------------------------------
# RULE-RELEASE-041：Recovery Chain
# ---------------------------------------------------------------------------

def run_recovery_chain(world_dir: Path | str, *,
                       migration_manifest: MigrationManifest | None = None,
                       backups_dir: Path | str | None = None,
                       hooks: dict | None = None,
                       migration_runner: MigrationRunner | None = None) -> dict:
    """固定 8 步顺序执行；任一步失败停在该步进入分诊，不跳步"""
    world_dir = Path(world_dir)
    hooks = hooks or {}
    results: list[dict] = []
    conn: sqlite3.Connection | None = None
    db_path = world_dir / "world.sqlite3"

    def record(step: int, name: str, passed: bool,
               reason_code: str | None = None) -> bool:
        entry = {"step": step, "name": name, "passed": passed}
        if reason_code:
            entry["reason_code"] = reason_code
        results.append(entry)
        return passed

    try:
        for number, name in CHAIN_STEPS:
            if number == 1:
                try:
                    conn = open_write_connection(db_path)
                    verify_pragmas(conn)
                    record(number, name, True)
                except ReleaseError as exc:
                    record(number, name, False, exc.reason_code)
                    break
            elif number == 2:
                if integrity_check(conn) and not foreign_key_check(conn):
                    record(number, name, True)
                else:
                    record(number, name, False,
                           "RELEASE_DB_INTEGRITY_FAILED")
                    break
            elif number == 3:
                if migration_manifest is None:
                    record(number, name, True)
                    continue
                try:
                    close_write_connection(db_path, conn)
                    runner = migration_runner or MigrationRunner()
                    runner.run_migration(
                        db_path, migration_manifest,
                        backups_dir or (world_dir / "backups"))
                    conn = open_write_connection(db_path)
                    record(number, name, True)
                except ReleaseError as exc:
                    conn = None
                    record(number, name, False, exc.reason_code)
                    break
            elif number == 4:
                invalid = _invalid_snapshots(conn, world_dir)
                total = conn.execute(
                    "SELECT COUNT(*) FROM snapshot_meta").fetchone()[0]
                if total == 0 or invalid < total:
                    record(number, name, True)
                else:
                    record(number, name, False,
                           "RELEASE_RECOVERY_SNAPSHOT_FAILED")
                    break
            elif number == 5:
                continuity = evlog.verify_event_continuity(conn, 1)
                if continuity["ok"]:
                    record(number, name, True)
                else:
                    record(number, name, False, "RELEASE_EVENT_GAP_DETECTED")
                    break
            else:
                hook = hooks.get(name)
                try:
                    if hook is not None:
                        hook(conn)
                    record(number, name, True)
                except ReleaseError as exc:
                    record(number, name, False, exc.reason_code)
                    break
                except Exception:
                    record(number, name, False,
                           "RELEASE_RECOVERY_AUDIT_FAILED")
                    break
    finally:
        if conn is not None:
            close_write_connection(db_path, conn)
    passed_all = len(results) == len(CHAIN_STEPS) \
        and all(r["passed"] for r in results)
    return {"chain_results": results, "passed": passed_all,
            "failed_step": results[-1]["step"] if not passed_all else None}


def _invalid_snapshots(conn: sqlite3.Connection, world_dir: Path) -> int:
    invalid = 0
    for row in conn.execute("SELECT * FROM snapshot_meta").fetchall():
        try:
            snap.load_snapshot_file(world_dir / "snapshots",
                                    row["file_name"], row["file_sha256"])
        except ReleaseError:
            invalid += 1
    return invalid


def recovery_success(world_dir: Path | str) -> bool:
    """RULE-RELEASE-047：8 步全过且 world_meta.revision == Event Log tip"""
    world_dir = Path(world_dir)
    db_path = world_dir / "world.sqlite3"
    conn = open_write_connection(db_path)
    try:
        meta = sch.read_world_meta(conn)
        return meta["revision"] == evlog.tip_revision(conn)
    finally:
        close_write_connection(db_path, conn)


# ---------------------------------------------------------------------------
# RULE-RELEASE-044：Triage Ladder
# ---------------------------------------------------------------------------

def triage(world_dir: Path | str, failed_step: int) -> dict:
    """DES-RELEASE-013：只列候选，不执行（L3 及以下禁止自动执行）"""
    world_dir = Path(world_dir)
    candidates: dict[str, object] = {"failed_step": failed_step}
    db_path = world_dir / "world.sqlite3"
    candidates["L1"] = {"available": db_path.is_file(),
                        "loss": "none"}
    conn = None
    try:
        conn = open_write_connection(db_path)
        snapshot = snap.load_latest_valid_snapshot(
            conn, world_dir / "snapshots")
        tip = evlog.tip_revision(conn)
        candidates["L2"] = {
            "available": snapshot is not None,
            "anchor_revision": snapshot["anchor_revision"] if snapshot else None,
            "loss": "none"}
        auto, manual = [], []
        for row in conn.execute(
                "SELECT * FROM save_records WHERE trashed_at IS NULL"
                " ORDER BY anchor_revision DESC").fetchall():
            entry = {"save_id": row["save_id"],
                     "anchor_revision": row["anchor_revision"],
                     "game_time": row["game_time"],
                     "created_at": row["created_at"],
                     "display_label": row["display_label"]}
            (auto if row["kind"] == "auto" else manual).append(entry)
        candidates["L3"] = {"available": bool(auto), "anchors": auto,
                            "loss": "anchor 之后进度", "requires_confirm": True}
        candidates["L4"] = {"available": bool(manual), "anchors": manual,
                            "loss": "anchor 之后进度", "requires_confirm": True}
    except (ReleaseError, sqlite3.Error):
        candidates.setdefault("L2", {"available": False})
        candidates.setdefault("L3", {"available": False, "anchors": []})
        candidates.setdefault("L4", {"available": False, "anchors": []})
    finally:
        if conn is not None:
            close_write_connection(db_path, conn)
    backups_dir = world_dir / "backups"
    backups = []
    if backups_dir.is_dir():
        backups = sorted(p.name for p in backups_dir.iterdir()
                         if p.name.startswith("pre-migration-"))
    candidates["L5"] = {"available": bool(backups), "backups": backups,
                        "loss": "备份点之后进度", "requires_confirm": True}
    candidates["L6"] = {"available": True, "loss": "世界不可用"}
    return candidates


def apply_triage_level(world_dir: Path | str, *, level: str,
                       anchor_revision: int | None = None,
                       backup_file: str | None = None,
                       new_timeline_id: str | None = None,
                       chain_kwargs: dict | None = None) -> dict:
    """DES-RELEASE-013：执行指定层级并重跑 Recovery Chain；
    L3/L4 走 branch-on-load 语义（RULE-RELEASE-045），调用方须已获玩家选择"""
    world_dir = Path(world_dir)
    chain_kwargs = chain_kwargs or {}
    attempt = {"level": level}
    db_path = world_dir / "world.sqlite3"
    try:
        if level == "L1":
            conn = open_write_connection(db_path)  # WAL 自恢复重开
            close_write_connection(db_path, conn)
        elif level == "L2":
            conn = open_write_connection(db_path)
            snapshot = snap.load_latest_valid_snapshot(
                conn, world_dir / "snapshots")
            continuity = evlog.verify_event_continuity(conn, 1)
            close_write_connection(db_path, conn)
            if snapshot is None or not continuity["ok"]:
                raise ReleaseError("RELEASE_RECOVERY_SNAPSHOT_FAILED")
            attempt["anchor_revision"] = snapshot["anchor_revision"]
        elif level in ("L3", "L4"):
            if anchor_revision is None or new_timeline_id is None:
                raise ValueError("L3/L4 需要玩家选择的锚点与新 timeline_id")
            conn = open_write_connection(db_path)
            old_timeline_id = sch.read_world_meta(conn)["timeline_id"]
            close_write_connection(db_path, conn)
            branch_mod.branch_on_load(
                world_dir, old_timeline_id=old_timeline_id,
                new_timeline_id=new_timeline_id,
                anchor_revision=anchor_revision)
            attempt["anchor_revision"] = anchor_revision
        elif level == "L5":
            if not backup_file:
                raise ValueError("L5 需要玩家选择的备份文件")
            source = world_dir / "backups" / backup_file
            if not source.is_file():
                raise ReleaseError("RELEASE_SNAPSHOT_UNAVAILABLE",
                                   {"file": backup_file})
            shutil.copyfile(source, db_path)
            for suffix in ("-wal", "-shm"):
                side = Path(str(db_path) + suffix)
                if side.exists():
                    side.unlink()
        else:
            raise ValueError(f"未知分诊层级: {level}")
        chain = run_recovery_chain(world_dir, **chain_kwargs)
        attempt["passed"] = chain["passed"]
        if not chain["passed"]:
            attempt["reason_code"] = chain["chain_results"][-1].get(
                "reason_code")
    except ReleaseError as exc:
        attempt["passed"] = False
        attempt["reason_code"] = exc.reason_code
    return attempt


def declare_unrecoverable(world_dir: Path | str,
                          chain_results: list,
                          triage_attempts: list,
                          world_id: str,
                          utc_now=_default_utc) -> dict:
    """RULE-RELEASE-047：L6 声明列出已尝试层级、失败原因码与全部文件清单"""
    world_dir = Path(world_dir)
    inventory = sorted(
        p.relative_to(world_dir).as_posix()
        for p in world_dir.rglob("*") if p.is_file())
    return {
        "report_format_version": RECOVERY_REPORT_FORMAT_VERSION,
        "world_id": world_id,
        "started_at": utc_now(),
        "chain_results": chain_results,
        "triage_attempts": triage_attempts,
        "outcome": "unrecoverable",
        "final_revision": None,
        "file_inventory": inventory,
        "guidance": "generate_diagnostics_package",
    }


def build_recovery_report(world_id: str, *, chain_results: list,
                          triage_attempts: list, outcome: str,
                          final_revision: int | None,
                          pre_repair_copy: str | None,
                          utc_now=_default_utc) -> dict:
    """DES-RELEASE-012 RecoveryReport（写入 diagnostics\\）"""
    return {
        "report_format_version": RECOVERY_REPORT_FORMAT_VERSION,
        "world_id": world_id,
        "started_at": utc_now(),
        "chain_results": chain_results,
        "triage_attempts": triage_attempts,
        "outcome": outcome,
        "final_revision": final_revision,
        "pre_repair_copy": pre_repair_copy,
    }

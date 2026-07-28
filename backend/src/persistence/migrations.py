"""
数据库 Schema 版本与迁移（DOC-RELEASE-002）

- RULE-RELEASE-009：version > current 拒绝打开且不写入任何字节；< min_supported 拒绝
- RULE-RELEASE-010：只前向；链由注册 MigrationStep 唯一确定；禁跳版本/降级
- RULE-RELEASE-011：每个 Step 前 checkpoint + Pre-migration Backup + SHA-256 核对
- RULE-RELEASE-012：每 Step 独立 BEGIN IMMEDIATE 事务，同事务更新 schema_version
  并写 schema_migrations；重启后从持久化版本续迁，不重复已完成 Step
- RULE-RELEASE-013：Post-migration Audit（integrity / FK / 审计查询）失败即还原备份
- RULE-RELEASE-014：迁移不得改写、删除或重排 event_log 历史行
- RULE-RELEASE-016：python_transform 只接受构建期注册的确定性纯函数
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .constants import (DISK_PREFLIGHT_MULTIPLIER, PRE_MIGRATION_BACKUP_KEEP,
                        ReleaseError)
from .database import (checkpoint_truncate, foreign_key_check, integrity_check,
                       open_readonly_file, open_write_connection,
                       close_write_connection)
from . import schema as sch


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc_compact(iso: str) -> str:
    return re.sub(r"[-:]", "", iso).replace("T", "T").split(".")[0] + "Z"


#: 构建期注册的确定性 Python 变换（RULE-RELEASE-016）：
#: 输入只有本库连接与 Step 常量；禁止网络/随机数/系统时间/库外文件
PYTHON_TRANSFORMS: dict[str, object] = {}


def register_transform(transform_id: str, fn) -> None:
    PYTHON_TRANSFORMS[transform_id] = fn


class MigrationStep:
    __slots__ = ("step_id", "from_version", "to_version", "summary",
                 "sql", "python_transform", "audit_queries")

    def __init__(self, raw: dict) -> None:
        self.step_id = str(raw["step_id"])
        self.from_version = int(raw["from_version"])
        self.to_version = int(raw["to_version"])
        self.summary = str(raw.get("summary", ""))
        self.sql = [str(s) for s in raw.get("sql", [])]
        self.python_transform = raw.get("python_transform")
        self.audit_queries = [str(q) for q in raw.get("audit_queries", [])]
        if self.to_version != self.from_version + 1:
            raise ValueError(f"MigrationStep 版本不连续: {self.step_id}")
        if self.python_transform is not None \
                and self.python_transform not in PYTHON_TRANSFORMS:
            raise ValueError(f"未注册的 python_transform: {self.python_transform}")
        _assert_event_log_untouched(self)


#: RULE-RELEASE-014：拒绝对 event_log 的改写/删除/重排（允许 CREATE INDEX / ALTER）
_EVENT_LOG_MUTATION = re.compile(
    r"\b(?:UPDATE|DELETE|INSERT|REPLACE|DROP)\b[^;]*\bevent_log\b",
    re.IGNORECASE)


def _assert_event_log_untouched(step: MigrationStep) -> None:
    for statement in step.sql:
        if _EVENT_LOG_MUTATION.search(statement):
            raise ReleaseError("RELEASE_MIGRATION_EVENT_LOG_TOUCHED",
                               {"step_id": step.step_id})


class MigrationManifest:
    """发布包内置只读注册清单（DOC-RELEASE-002 §5.2）"""

    def __init__(self, raw: dict) -> None:
        self.manifest_version = int(raw.get("manifest_version", 1))
        self.database = str(raw["database"])  # "app" | "world"
        self.min_supported = int(raw["min_supported"])
        self.current = int(raw["current"])
        self.steps = [MigrationStep(s) for s in raw.get("steps", [])]
        # 链唯一性校验：min_supported..current 每版本至多一个入边 Step
        arrivals: dict[int, str] = {}
        for step in self.steps:
            if step.to_version in arrivals:
                raise ValueError(f"迁移链不唯一: v{step.to_version}")
            arrivals[step.to_version] = step.step_id

    def chain(self, from_version: int, to_version: int) -> list[MigrationStep]:
        """按版本序取 from_version → to_version 的唯一 Step 序列；断链即错误"""
        ordered = sorted(self.steps, key=lambda s: s.from_version)
        result: list[MigrationStep] = []
        cursor = from_version
        while cursor < to_version:
            nxt = next((s for s in ordered if s.from_version == cursor), None)
            if nxt is None:
                raise ReleaseError("RELEASE_MIGRATION_STEP_FAILED",
                                   {"detail": f"迁移链断裂于 v{cursor}"})
            result.append(nxt)
            cursor = nxt.to_version
        return result


class MigrationPlan:
    def __init__(self, steps: list[MigrationStep], from_version: int,
                 to_version: int) -> None:
        self.steps = steps
        self.from_version = from_version
        self.to_version = to_version

    @property
    def needed(self) -> bool:
        return bool(self.steps)


def _read_version(db_path: Path, kind: str) -> int:
    """只读读取版本（RULE-RELEASE-009：拒绝打开时不写入任何字节）"""
    conn = open_readonly_file(db_path)
    try:
        if kind == "app":
            return sch.app_schema_version(conn)
        return sch.world_schema_version(conn)
    finally:
        conn.close()


def plan_migration(db_path: Path | str, manifest: MigrationManifest) -> MigrationPlan:
    """DES-RELEASE-004：计算 Migration Chain；超界拒绝打开"""
    db_path = Path(db_path)
    version = _read_version(db_path, manifest.database)
    if version > manifest.current:
        raise ReleaseError("RELEASE_MIGRATION_REFUSED_TOO_NEW",
                           {"db_version": version, "current": manifest.current})
    if version < manifest.min_supported:
        raise ReleaseError("RELEASE_MIGRATION_REFUSED_TOO_OLD",
                           {"db_version": version,
                            "min_supported": manifest.min_supported})
    steps = manifest.chain(version, manifest.current)
    return MigrationPlan(steps, version, manifest.current)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_name(step: MigrationStep, utc: str) -> str:
    return ("pre-migration-v{}-v{}-{}.sqlite3"
            .format(step.from_version, step.to_version, _utc_compact(utc)))


class MigrationRunner:
    """DES-RELEASE-004：迁移由 RELEASE 独占执行，Domain 模块不感知"""

    def __init__(self, utc_now=_default_utc, monotonic=time.monotonic,
                 free_space=None) -> None:
        self._utc_now = utc_now
        self._monotonic = monotonic
        #: 可用空间探测（RULE-RELEASE-042 预检），测试可注入
        self._free_space = free_space or (
            lambda p: shutil.disk_usage(str(p)).free)
        #: 当前 Step 的 Pre-migration Backup 路径（失败还原用）
        self._pending_backup = None

    def run_migration(self, db_path: Path | str, manifest: MigrationManifest,
                      backups_dir: Path | str, on_migrated=None) -> dict:
        """逐 Step 执行；任一失败：回滚当前事务、还原该 Step 备份、停止后续"""
        db_path = Path(db_path)
        backups_dir = Path(backups_dir)
        backups_dir.mkdir(parents=True, exist_ok=True)
        plan = plan_migration(db_path, manifest)
        report = {"database": manifest.database, "from_version": plan.from_version,
                  "to_version": plan.to_version, "steps": [], "outcome": "noop"}
        if not plan.needed:
            return report

        # RULE-RELEASE-042：磁盘预检（最大单库 2 倍估算）
        required = db_path.stat().st_size * DISK_PREFLIGHT_MULTIPLIER
        if self._free_space(backups_dir) < required:
            raise ReleaseError("RELEASE_DISK_SPACE_INSUFFICIENT",
                               {"required": required})

        conn = open_write_connection(db_path)
        try:
            current = self._persisted_version(conn, manifest.database)
            # §7：schema_migrations 与 schema_version 不一致视为损坏，不猜测继续
            self._assert_consistent(conn, current)
            for step in plan.steps:
                if step.from_version < current:
                    continue  # 断点续迁：已完成 Step 不重放
                if step.from_version != current:
                    raise ReleaseError("RELEASE_DB_CORRUPT_METADATA",
                                       {"detail": "迁移链与持久化版本错位"})
                try:
                    entry = self._run_step(conn, step, db_path, backups_dir)
                except (sqlite3.Error, ReleaseError) as exc:
                    # RULE-RELEASE-013：关库后还原该 Step 备份，停止后续 Step
                    backup = self._pending_backup
                    close_write_connection(db_path, conn)
                    conn = None
                    if backup is not None and backup.is_file():
                        self._restore_backup(db_path, backup)
                    if isinstance(exc, ReleaseError) and \
                            exc.reason_code == "RELEASE_MIGRATION_BACKUP_FAILED":
                        raise
                    raise ReleaseError("RELEASE_MIGRATION_STEP_FAILED",
                                       {"step_id": step.step_id,
                                        "error": type(exc).__name__})
                report["steps"].append(entry)
                current = step.to_version
            try:
                self._post_migration_audit(conn, plan.steps)
            except ReleaseError:
                # 审计失败：恢复最近一次 Step 前备份，世界保持停止模拟
                close_write_connection(db_path, conn)
                conn = None
                if report["steps"]:
                    self._restore_backup(
                        db_path, backups_dir / report["steps"][-1]["backup_file"])
                raise
            report["outcome"] = "migrated"
            if on_migrated is not None:
                on_migrated(conn, plan.from_version, plan.to_version)
            conn.commit()
        finally:
            if conn is not None:
                close_write_connection(db_path, conn)
        enforce_backup_retention(backups_dir)
        return report

    def _persisted_version(self, conn, kind: str) -> int:
        if kind == "app":
            return sch.app_schema_version(conn)
        return sch.world_schema_version(conn)

    def _assert_consistent(self, conn, version: int) -> None:
        row = conn.execute(
            "SELECT MAX(to_version) FROM schema_migrations").fetchone()
        max_applied = row[0] if row and row[0] is not None else 0
        if max_applied > version:
            raise ReleaseError("RELEASE_DB_CORRUPT_METADATA",
                               {"detail": "schema_migrations 领先于 schema_version"})

    def _run_step(self, conn, step: MigrationStep, db_path: Path,
                  backups_dir: Path) -> dict:
        started = self._monotonic()
        utc = self._utc_now()
        # RULE-RELEASE-011：checkpoint → 备份 → 校验 SHA-256；失败则迁移不得开始
        conn.commit()
        checkpoint_truncate(conn)
        backup_file = _backup_name(step, utc)
        backup_path = backups_dir / backup_file
        #: 失败路径由 run_migration 关库后按此路径还原
        self._pending_backup = backup_path
        shutil.copyfile(db_path, backup_path)
        src_hash = _sha256_file(db_path)
        if _sha256_file(backup_path) != src_hash:
            raise ReleaseError("RELEASE_MIGRATION_BACKUP_FAILED",
                               {"step_id": step.step_id})
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in step.sql:
                conn.execute(statement)
            if step.python_transform is not None:
                PYTHON_TRANSFORMS[step.python_transform](conn)
            self._set_version(conn, step)
            conn.execute(
                "INSERT INTO schema_migrations"
                "(to_version, step_id, applied_at, duration_ms,"
                " backup_file, backup_sha256) VALUES (?,?,?,?,?,?)",
                (step.to_version, step.step_id, utc, 0, backup_file, src_hash))
            conn.commit()
        except (sqlite3.Error, ReleaseError):
            conn.rollback()
            raise
        duration_ms = int((self._monotonic() - started) * 1000)
        conn.execute(
            "UPDATE schema_migrations SET duration_ms=?"
            " WHERE to_version=?", (duration_ms, step.to_version))
        conn.commit()
        self._pending_backup = None
        return {"step_id": step.step_id, "from_version": step.from_version,
                "to_version": step.to_version, "duration_ms": duration_ms,
                "backup_file": backup_file, "backup_sha256": src_hash}

    def _set_version(self, conn, step: MigrationStep) -> None:
        # 由调用方告知数据库类型：manifest.database 经 step 不可知，故两表都尝试
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('app_meta','world_meta')").fetchall()
        names = {r[0] for r in row}
        if "app_meta" in names:
            sch.set_app_schema_version(conn, step.to_version)
        elif "world_meta" in names:
            sch.set_world_schema_version(conn, step.to_version)

    def _restore_backup(self, db_path: Path, backup_path: Path) -> None:
        """RULE-RELEASE-013：审计/Step 失败即恢复 Pre-migration Backup"""
        tmp = db_path.with_suffix(".restore-tmp")
        shutil.copyfile(backup_path, tmp)
        # 清掉可能残留的 wal/shm，避免旧 WAL 重放进还原库
        for suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + suffix)
            if side.exists():
                side.unlink()
        tmp.replace(db_path)

    def _post_migration_audit(self, conn, steps: list[MigrationStep]) -> None:
        """RULE-RELEASE-013：integrity ok + FK 空集 + 审计查询全过（返回 0 违规）"""
        if not integrity_check(conn):
            raise ReleaseError("RELEASE_MIGRATION_AUDIT_FAILED",
                               {"check": "integrity_check"})
        fk_rows = foreign_key_check(conn)
        if fk_rows:
            raise ReleaseError("RELEASE_MIGRATION_AUDIT_FAILED",
                               {"check": "foreign_key_check",
                                "violations": len(fk_rows)})
        for step in steps:
            for query in step.audit_queries:
                rows = conn.execute(query).fetchall()
                violations = 0 if not rows else int(rows[0][0] or 0)
                if violations != 0:
                    raise ReleaseError("RELEASE_MIGRATION_AUDIT_FAILED",
                                       {"step_id": step.step_id,
                                        "violations": violations})


def enforce_backup_retention(backups_dir: Path | str,
                             keep: int = PRE_MIGRATION_BACKUP_KEEP) -> list[str]:
    """RULE-RELEASE-046：Pre-migration 备份每世界保留最近 3 份；corrupt 永不清理"""
    backups_dir = Path(backups_dir)
    if not backups_dir.is_dir():
        return []
    backups = sorted(
        (p for p in backups_dir.iterdir()
         if p.name.startswith("pre-migration-") and p.suffix == ".sqlite3"),
        key=lambda p: p.name)
    removed: list[str] = []
    while len(backups) > keep:
        victim = backups.pop(0)
        victim.unlink()
        removed.append(victim.name)
    return removed

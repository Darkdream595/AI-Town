"""
脱敏诊断包（DOC-RELEASE-010）

- RULE-RELEASE-076：内容白名单固定；打包前全量过 Secret Scanner，
  任一命中即中止，绝不产出「部分脱敏」的包
- RULE-RELEASE-077：不含任何 world.sqlite3 / Timeline 归档 / Snapshot /
  存档与导出包；数据库信息仅以摘要出现
- RULE-RELEASE-078：ULID 与注册稳定 ID 可明文；display_name 例外允许明文
"""

from __future__ import annotations

import io
import json
import platform
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import secret_scan
from .constants import (DIAG_FORMAT_VERSION, SCANNER_RULESET_VERSION,
                        ReleaseError)
from .paths import UserDataLayout
from .recovery import preflight_disk_check

#: DES-RELEASE-021 内容白名单
WHITELIST = ("manifest.json", "system.json", "package.json", "settings.json",
             "worlds-summary.json", "recovery/", "logs/")

#: RULE-RELEASE-074：日志轮转与保留策略
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_RETENTION_DAYS = 14
LOG_TOTAL_MAX_BYTES = 200 * 1024 * 1024


def content_hash(text: str) -> str:
    """Content Hashing（§3）：sha256:<hex>+len 替代自由文本原文"""
    import hashlib
    data = str(text).encode("utf-8")
    return "sha256:{}+{}".format(hashlib.sha256(data).hexdigest(), len(data))


def enforce_log_retention(logs_dir: Path | str, *, now=None) -> dict:
    """RULE-RELEASE-074：保留 14 天且总量 ≤ 200 MiB，超限先删最旧"""
    import datetime as _dt
    logs_dir = Path(logs_dir)
    if not logs_dir.is_dir():
        return {"removed": [], "total_bytes": 0}
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=LOG_RETENTION_DAYS)
    files = [p for p in logs_dir.glob("app-*.log*") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime)
    removed: list[str] = []
    for path in list(files):
        mtime = _dt.datetime.fromtimestamp(path.stat().st_mtime,
                                           _dt.timezone.utc)
        if mtime < cutoff:
            removed.append(path.name)
            path.unlink()
            files.remove(path)
    total = sum(p.stat().st_size for p in files)
    while total > LOG_TOTAL_MAX_BYTES and files:
        victim = files.pop(0)
        total -= victim.stat().st_size
        removed.append(victim.name)
        victim.unlink()
    return {"removed": removed, "total_bytes": total}


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_diagnostics_package(layout: UserDataLayout, *,
                              app_conn: sqlite3.Connection,
                              package_version: str, build_id: str,
                              settings: dict,
                              key_masked_status: str | None,
                              worlds_summary: list[dict],
                              release_manifest_summary: dict | None = None,
                              utc_now=_default_utc,
                              utc_compact=_utc_compact,
                              free_space=None) -> dict:
    """DES-RELEASE-021：收集白名单 → Secret Scanner → 全净打 zip"""
    diagnostics_dir = layout.diagnostics_dir
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()

    members: dict[str, bytes] = {}
    members["system.json"] = _json_bytes(_system_info())
    members["package.json"] = _json_bytes(
        release_manifest_summary or {"release_manifest": "absent"})
    members["settings.json"] = _json_bytes({
        "settings": settings,
        "deepseek_key_status": key_masked_status or "not_configured"})
    members["worlds-summary.json"] = _json_bytes({"worlds": worlds_summary})

    # recovery\\*.json（本身已脱敏，DES-RELEASE-012）
    for path in sorted(diagnostics_dir.glob("recovery-*.json")):
        if path.is_file():
            members["recovery/" + path.name] = path.read_bytes()

    # logs\\ 最近 7 天（Emission-time Redaction 已在写入侧执行）
    logs_dir = layout.logs_dir
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    if logs_dir.is_dir():
        for path in sorted(logs_dir.glob("app-*.log*")):
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if mtime >= cutoff:
                members["logs/" + path.name] = path.read_bytes()

    manifest = {
        "diag_format_version": DIAG_FORMAT_VERSION,
        "generated_at": generated_at,
        "package_version": package_version,
        "build_id": build_id,
        "scanner_ruleset_version": SCANNER_RULESET_VERSION,
        "scan_result": "clean",
        "included": sorted(
            {name if "/" not in name else name.split("/")[0] + "/"
             for name in members} | {"manifest.json"}),
    }
    members["manifest.json"] = _json_bytes(manifest)

    # RULE-RELEASE-076：打包前全量扫描，任一命中即中止
    allowed = (layout.root,)
    hits: list[dict] = []
    for name, data in members.items():
        report = secret_scan.scan_bytes(data, allowed)
        for hit in report["hits"]:
            hits.append({**hit, "member": name})
    if hits:
        raise ReleaseError("RELEASE_SECRET_SCAN_HIT",
                           {"hits": len(hits),
                            "rules": sorted({h["rule"] for h in hits})})

    target = diagnostics_dir / ("aitown-diag-" + utc_compact() + ".zip")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    payload = buffer.getvalue()
    preflight_disk_check(diagnostics_dir, len(payload), free_space)
    target.write_bytes(payload)
    return {"target": str(target), "size_bytes": len(payload),
            "members": sorted(members), "scan_result": "clean"}


def _json_bytes(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      indent=2).encode("utf-8")


def _system_info() -> dict:
    import locale
    return {
        "os": platform.platform(),
        "os_version": platform.version(),
        "locale": locale.getpreferredencoding(False),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
    }


def summarize_world(db_path: Path | str) -> dict:
    """RULE-RELEASE-077：数据库仅以摘要出现（版本/完整性/行数/大小）"""
    import sqlite3 as _sqlite3
    from .database import integrity_check
    db_path = Path(db_path)
    summary = {"file": db_path.name,
               "size_bytes": db_path.stat().st_size if db_path.is_file() else 0}
    try:
        conn = _sqlite3.connect("file:{}?mode=ro".format(
            db_path.as_posix()), uri=True)
        try:
            summary["integrity"] = "ok" if integrity_check(conn) else "failed"
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            summary["tables"] = {
                name: conn.execute(
                    'SELECT COUNT(*) FROM "{}"'.format(name)).fetchone()[0]
                for (name,) in tables}
            try:
                row = conn.execute(
                    "SELECT revision, schema_version, game_time"
                    " FROM world_meta WHERE id=1").fetchone()
                if row:
                    summary["revision"] = row[0]
                    summary["schema_version"] = row[1]
                    summary["game_time"] = row[2]
            except _sqlite3.Error:
                pass
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM save_records").fetchone()
                summary["save_count"] = row[0]
            except _sqlite3.Error:
                pass
        finally:
            conn.close()
    except _sqlite3.Error:
        summary["integrity"] = "unreadable"
    return summary

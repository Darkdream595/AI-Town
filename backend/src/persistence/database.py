"""
SQLite 连接策略（DOC-RELEASE-001）

- RULE-RELEASE-003：所有数据库打开时必须设置 WAL / foreign_keys=ON /
  busy_timeout=5000 / synchronous=NORMAL
- RULE-RELEASE-004：每数据库进程内只有一个 Write Connection；
  读操作使用独立只读连接（query_only=ON），不得升级为写
- RULE-RELEASE-007：干净退出时 wal_checkpoint(TRUNCATE)
- §8：数据库打开失败/PRAGMA 校验失败 → 世界不进入模拟
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .constants import ReleaseError

#: RULE-RELEASE-003 的连接级 PRAGMA 期望值
REQUIRED_PRAGMAS = {
    "journal_mode": "wal",
    "foreign_keys": 1,
    "busy_timeout": 5000,
    "synchronous": 1,  # NORMAL
}

#: 进程内单写入注册表：normalized path -> connection（RULE-RELEASE-004）
_WRITE_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def _key(path: Path | str) -> str:
    return str(Path(path).resolve()).lower()


def open_write_connection(path: Path | str) -> sqlite3.Connection:
    """打开数据库唯一写连接；同库第二次打开写连接即拒绝"""
    key = _key(path)
    if key in _WRITE_CONNECTIONS:
        raise ReleaseError("RELEASE_DB_OPEN_FAILED",
                           {"path_key": key, "reason": "writer_exists"})
    try:
        conn = sqlite3.connect(str(path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        _apply_write_pragmas(conn)
        verify_pragmas(conn)
    except ReleaseError:
        raise
    except sqlite3.Error as exc:
        raise ReleaseError("RELEASE_DB_OPEN_FAILED", {"error": type(exc).__name__})
    _WRITE_CONNECTIONS[key] = conn
    return conn


def open_read_connection(path: Path | str) -> sqlite3.Connection:
    """只读查询连接：query_only=ON，不得升级为写（RULE-RELEASE-004）"""
    try:
        conn = sqlite3.connect(str(path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=5000")
    except sqlite3.Error as exc:
        raise ReleaseError("RELEASE_DB_OPEN_FAILED", {"error": type(exc).__name__})
    return conn


def open_readonly_file(path: Path | str) -> sqlite3.Connection:
    """以只读模式打开文件（迁移前读取版本等，保证不写入任何字节，RULE-RELEASE-009）"""
    uri = "file:{}?mode=ro".format(Path(path).as_posix())
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise ReleaseError("RELEASE_DB_OPEN_FAILED", {"error": type(exc).__name__})
    return conn


def _apply_write_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")


def verify_pragmas(conn: sqlite3.Connection) -> dict:
    """PRAGMA 校验（§8：校验失败世界不进入模拟）"""
    actual = {
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
        "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
        "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
    }
    for key, expected in REQUIRED_PRAGMAS.items():
        value = actual[key]
        if isinstance(expected, str):
            ok = str(value).lower() == expected
        else:
            ok = int(value) == expected
        if not ok:
            conn.close()
            raise ReleaseError("RELEASE_DB_PRAGMA_FAILED",
                               {"pragma": key, "actual": str(value)})
    return actual


def close_write_connection(path: Path | str, conn: sqlite3.Connection) -> None:
    """关闭并注销写连接"""
    key = _key(path)
    try:
        conn.close()
    finally:
        if _WRITE_CONNECTIONS.get(key) is conn:
            del _WRITE_CONNECTIONS[key]


def checkpoint_truncate(conn: sqlite3.Connection) -> None:
    """干净退出 checkpoint（RULE-RELEASE-007）；成功后 -wal 长度为 0"""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def checkpoint_passive(conn: sqlite3.Connection) -> None:
    """写队列空闲时的 PASSIVE checkpoint（DOC-RELEASE-001 §7）"""
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")


def wal_file_size(db_path: Path | str) -> int:
    wal = Path(str(db_path) + "-wal")
    return wal.stat().st_size if wal.is_file() else 0


def integrity_check(conn: sqlite3.Connection) -> bool:
    """PRAGMA integrity_check 返回 ok（RULE-RELEASE-013）"""
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    return len(rows) == 1 and rows[0][0] == "ok"


def foreign_key_check(conn: sqlite3.Connection) -> list:
    """PRAGMA foreign_key_check 返回空集为通过（RULE-RELEASE-013）"""
    return conn.execute("PRAGMA foreign_key_check").fetchall()


def assert_writer_exclusive(path: Path | str) -> None:
    """供装配层断言：该库当前无写连接（测试收尾清理校验用）"""
    if _key(path) in _WRITE_CONNECTIONS:
        raise ReleaseError("RELEASE_DB_OPEN_FAILED", {"reason": "writer_leaked"})

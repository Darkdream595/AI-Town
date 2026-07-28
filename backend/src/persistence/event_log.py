"""
追加式 Domain Event Log（DOC-RELEASE-003）

- RULE-RELEASE-017：只允许 INSERT；trigger 拒绝 UPDATE/DELETE
- RULE-RELEASE-018：revision 同一 Timeline 内从 1 开始严格连续无空洞
- RULE-RELEASE-019：完整 Envelope 字段；payload/render 为可解析 JSON；
  禁止 Secret、API Key 与 reasoning_content
"""

from __future__ import annotations

import json
import re
import sqlite3

from src.foundation.id_generator import is_valid_ulid

from .constants import ReleaseError

ENVELOPE_FIELDS = ("revision", "event_id", "world_id", "event_type",
                   "event_schema_version", "game_time", "causation_id",
                   "correlation_id", "payload_json", "render_json", "created_at")

_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

#: RULE-RELEASE-019：事件内容禁区的确定性可检测部分
_FORBIDDEN_PAYLOAD_KEY = re.compile(r'reasoning_content', re.IGNORECASE)
_KEY_SHAPE = re.compile(r"sk-[A-Za-z0-9]{8,}")


def validate_envelope(event: dict) -> None:
    """RULE-RELEASE-019：Envelope 完备性与格式校验"""
    missing = [f for f in ENVELOPE_FIELDS if f not in event]
    if missing:
        raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                           {"missing": ",".join(missing)})
    if not isinstance(event["revision"], int) or event["revision"] < 1:
        raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                           {"field": "revision"})
    if not is_valid_ulid(event["event_id"]):
        raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                           {"field": "event_id"})
    if not isinstance(event["event_type"], str) or not event["event_type"]:
        raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                           {"field": "event_type"})
    for json_field in ("payload_json", "render_json"):
        text = event[json_field]
        if text is None and json_field == "render_json":
            continue
        if not isinstance(text, str):
            raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                               {"field": json_field})
        try:
            json.loads(text)
        except ValueError:
            raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                               {"field": json_field, "detail": "unparseable"})
        if _FORBIDDEN_PAYLOAD_KEY.search(text) or _KEY_SHAPE.search(text):
            raise ReleaseError("RELEASE_EVENT_CONTENT_FORBIDDEN",
                               {"field": json_field})
    if not _RFC3339.match(str(event["created_at"])):
        raise ReleaseError("RELEASE_EVENT_ENVELOPE_INVALID",
                           {"field": "created_at"})


def append_event(conn: sqlite3.Connection, event: dict) -> None:
    """DES-RELEASE-007：仅供 Repository commit 内部同事务调用"""
    validate_envelope(event)
    expected = tip_revision(conn) + 1
    if event["revision"] != expected:
        raise ReleaseError("RELEASE_EVENT_GAP_DETECTED",
                           {"expected": expected, "got": event["revision"]})
    conn.execute(
        "INSERT INTO event_log(revision, event_id, world_id, event_type,"
        " event_schema_version, game_time, causation_id, correlation_id,"
        " payload_json, render_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (event["revision"], event["event_id"], event["world_id"],
         event["event_type"], event["event_schema_version"],
         event["game_time"], event.get("causation_id"),
         event.get("correlation_id"), event["payload_json"],
         event.get("render_json"), event["created_at"]))


def tip_revision(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(revision) FROM event_log").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def read_events(conn: sqlite3.Connection, from_revision: int,
                to_revision: int | None = None) -> list[dict]:
    sql = ("SELECT * FROM event_log WHERE revision >= ?"
           + (" AND revision <= ?" if to_revision is not None else "")
           + " ORDER BY revision ASC")
    params = (from_revision,) if to_revision is None \
        else (from_revision, to_revision)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def verify_event_continuity(conn: sqlite3.Connection, from_revision: int = 1,
                            to_revision: int | None = None) -> dict:
    """DES-RELEASE-007：连续性校验；发现空洞即判定损坏（RULE-RELEASE-018）"""
    rows = read_events(conn, from_revision, to_revision)
    gaps: list[int] = []
    expected = from_revision
    for row in rows:
        while expected < row["revision"]:
            gaps.append(expected)
            expected += 1
        expected = row["revision"] + 1
    return {"ok": not gaps, "gaps": gaps, "checked": len(rows),
            "tip": rows[-1]["revision"] if rows else from_revision - 1}

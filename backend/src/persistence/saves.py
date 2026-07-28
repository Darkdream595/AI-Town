"""
自动恢复点与手动存档槽位（DOC-RELEASE-004）

- RULE-RELEASE-025：自动恢复点恰好 5 个（FIFO）；手动槽位恰好 3 个；产品常量
- RULE-RELEASE-026：触发固定：干净关闭必建；每 10 game minutes 或 500 Revision
- RULE-RELEASE-027：SaveRecord 只引用哈希校验通过的 Snapshot；引用保护
- RULE-RELEASE-030：覆盖非空槽位需确认；被覆盖记录入 Save Trash 7 天可还原
- RULE-RELEASE-031：全部存档操作幂等（command_id 经 idempotency_keys 去重）
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.foundation.id_generator import generate_ulid

from . import event_log as evlog
from . import snapshots as snap
from .constants import (AUTO_SAVE_COUNT, AUTO_SAVE_GAME_MINUTES,
                        AUTO_SAVE_REVISION_INTERVAL, MANUAL_SLOTS,
                        SAVE_TRASH_DAYS, ReleaseError)
from .snapshots import canonical_json_bytes


def _default_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc)


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LABEL_MAX = 80


def sanitize_display_label(text: str) -> str:
    """§9：玩家自定义标签经长度与字符过滤"""
    cleaned = _CONTROL_CHARS.sub("", str(text)).strip()
    return cleaned[:_LABEL_MAX] or "未命名存档"


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _idempotent(conn: sqlite3.Connection, command_id: str, payload: dict,
                utc_now, fn) -> dict:
    """RULE-RELEASE-031：同一 command_id 重复提交只生效一次（§10 验收）"""
    row = conn.execute(
        "SELECT payload_hash, result_json FROM idempotency_keys"
        " WHERE command_id=?", (command_id,)).fetchone()
    payload_hash = _payload_hash(payload)
    if row is not None:
        if row[0] != payload_hash:
            raise ReleaseError("RELEASE_SAVE_NOT_FOUND",
                               {"detail": "command_id 载荷冲突"})
        return json.loads(row[1])
    result = fn()
    conn.execute(
        "INSERT INTO idempotency_keys(command_id, payload_hash, result_json,"
        " created_at) VALUES (?,?,?,?)",
        (command_id, payload_hash,
         json.dumps(result, sort_keys=True, ensure_ascii=False), utc_now()))
    conn.commit()
    return result


def _auto_label(game_time: int) -> str:
    return "自动恢复点 · 第 {} 游戏日".format(game_time // 1440 + 1)


def _record_row_to_dict(row: sqlite3.Row, tip: int) -> dict:
    record = dict(row)
    record["will_branch_on_load"] = record["anchor_revision"] < tip
    return record


def should_create_auto_save(revisions_since_last: int,
                            game_minutes_since_last: int) -> bool:
    """RULE-RELEASE-026：每 10 game minutes 或每 500 Revision（先到者）"""
    return (revisions_since_last >= AUTO_SAVE_REVISION_INTERVAL
            or game_minutes_since_last >= AUTO_SAVE_GAME_MINUTES)


def create_manual_save(conn: sqlite3.Connection, snapshots_dir: Path | str,
                       *, command_id: str, slot: str, display_label: str,
                       confirmed: bool = False, utc_now=_default_utc,
                       new_ulid=generate_ulid) -> dict:
    """DES-RELEASE-009：手动存档到 slot_1..3；覆盖非空槽位需 confirmed"""
    if slot not in MANUAL_SLOTS:
        raise ReleaseError("RELEASE_SAVE_SLOT_INVALID", {"slot": slot})
    payload = {"op": "manual_save", "slot": slot,
               "label": sanitize_display_label(display_label)}

    def do_save() -> dict:
        occupant = conn.execute(
            "SELECT save_id FROM save_records WHERE kind='manual' AND slot=?"
            " AND trashed_at IS NULL", (slot,)).fetchone()
        if occupant is not None and not confirmed:
            raise ReleaseError("RELEASE_SAVE_CONFIRM_REQUIRED",
                               {"slot": slot})
        meta = snap.build_snapshot(conn, snapshots_dir, "manual_save",
                                   utc_now=utc_now, new_ulid=new_ulid)
        world = conn.execute(
            "SELECT timeline_id, game_time FROM world_meta WHERE id=1"
            ).fetchone()
        save_id = new_ulid()
        now = utc_now()
        if occupant is not None:
            # RULE-RELEASE-030：被覆盖记录移入 Save Trash
            conn.execute("UPDATE save_records SET trashed_at=? WHERE save_id=?",
                         (now, occupant[0]))
        conn.execute(
            "INSERT INTO save_records(save_id, kind, slot, timeline_id,"
            " anchor_revision, snapshot_id, game_time, display_label,"
            " created_at, trashed_at) VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (save_id, "manual", slot, world["timeline_id"],
             meta["anchor_revision"], meta["snapshot_id"],
             world["game_time"], payload["label"], now))
        conn.commit()
        return {"save_id": save_id, "kind": "manual", "slot": slot,
                "anchor_revision": meta["anchor_revision"],
                "snapshot_id": meta["snapshot_id"],
                "game_time": world["game_time"],
                "display_label": payload["label"], "created_at": now,
                "overwrote": occupant[0] if occupant else None}

    return _idempotent(conn, command_id, payload, utc_now, do_save)


def record_auto_save(conn: sqlite3.Connection, snapshot_meta: dict,
                     utc_now=_default_utc, new_ulid=generate_ulid) -> dict:
    """基于既有 Snapshot 登记自动恢复点并 FIFO 维持恰好 5 个（RULE-RELEASE-025）"""
    world = conn.execute(
        "SELECT timeline_id, game_time FROM world_meta WHERE id=1").fetchone()
    save_id = new_ulid()
    now = utc_now()
    conn.execute(
        "INSERT INTO save_records(save_id, kind, slot, timeline_id,"
        " anchor_revision, snapshot_id, game_time, display_label,"
        " created_at, trashed_at) VALUES (?,?,NULL,?,?,?,?,?,?,NULL)",
        (save_id, "auto", world["timeline_id"],
         snapshot_meta["anchor_revision"], snapshot_meta["snapshot_id"],
         world["game_time"], _auto_label(world["game_time"]), now))
    actives = conn.execute(
        "SELECT save_id FROM save_records WHERE kind='auto'"
        " AND trashed_at IS NULL ORDER BY created_at ASC").fetchall()
    evicted: list[str] = []
    while len(actives) > AUTO_SAVE_COUNT:
        oldest = actives.pop(0)
        conn.execute("UPDATE save_records SET trashed_at=? WHERE save_id=?",
                     (now, oldest[0]))
        evicted.append(oldest[0])
    conn.commit()
    return {"save_id": save_id, "kind": "auto",
            "anchor_revision": snapshot_meta["anchor_revision"],
            "snapshot_id": snapshot_meta["snapshot_id"],
            "game_time": world["game_time"],
            "display_label": _auto_label(world["game_time"]),
            "created_at": now, "evicted": evicted}


def create_auto_recovery_point(conn: sqlite3.Connection,
                               snapshots_dir: Path | str,
                               *, utc_now=_default_utc,
                               new_ulid=generate_ulid) -> dict:
    """RULE-RELEASE-026：系统内部创建；复用 Snapshot 任务（DOC-RELEASE-003）"""
    meta = snap.build_snapshot(conn, snapshots_dir, "auto_save",
                               utc_now=utc_now, new_ulid=new_ulid)
    return record_auto_save(conn, meta, utc_now=utc_now, new_ulid=new_ulid)


def list_saves(conn: sqlite3.Connection, include_trashed: bool = True) -> list[dict]:
    """DES-RELEASE-009：含 Save Trash 标记与 will_branch_on_load"""
    tip = evlog.tip_revision(conn)
    sql = "SELECT * FROM save_records"
    if not include_trashed:
        sql += " WHERE trashed_at IS NULL"
    rows = conn.execute(sql + " ORDER BY created_at DESC").fetchall()
    return [_record_row_to_dict(r, tip) for r in rows]


def get_save(conn: sqlite3.Connection, save_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM save_records WHERE save_id=?", (save_id,)).fetchone()
    if row is None:
        raise ReleaseError("RELEASE_SAVE_NOT_FOUND", {"save_id": save_id})
    return _record_row_to_dict(row, evlog.tip_revision(conn))


def plan_load(conn: sqlite3.Connection, save_id: str,
              confirm_branch: bool = False) -> dict:
    """RULE-RELEASE-028：tip 存档 = Resume；更早锚点默认 branch-on-load（需确认）"""
    record = get_save(conn, save_id)
    if record["trashed_at"] is not None:
        raise ReleaseError("RELEASE_SAVE_NOT_FOUND",
                           {"save_id": save_id, "state": "trashed"})
    if not record["will_branch_on_load"]:
        return {"mode": "resume", "save": record}
    if not confirm_branch:
        raise ReleaseError("RELEASE_SAVE_CONFIRM_REQUIRED",
                           {"save_id": save_id})
    return {"mode": "branch", "save": record}


def restore_trashed_save(conn: sqlite3.Connection, *, command_id: str,
                         save_id: str, utc_now=_default_utc) -> dict:
    """RULE-RELEASE-030：Save Trash 7 天内一键还原到原槽位/列表"""
    payload = {"op": "restore_save", "save_id": save_id}

    def do_restore() -> dict:
        row = conn.execute(
            "SELECT * FROM save_records WHERE save_id=?", (save_id,)).fetchone()
        if row is None or row["trashed_at"] is None:
            raise ReleaseError("RELEASE_SAVE_NOT_FOUND",
                               {"save_id": save_id, "state": "not_trashed"})
        deadline = _parse_utc(row["trashed_at"]) + timedelta(days=SAVE_TRASH_DAYS)
        now = _parse_utc(utc_now())
        if now > deadline:
            raise ReleaseError("RELEASE_SAVE_TRASH_EXPIRED",
                               {"save_id": save_id})
        swapped = None
        if row["kind"] == "manual":
            occupant = conn.execute(
                "SELECT save_id FROM save_records WHERE kind='manual'"
                " AND slot=? AND trashed_at IS NULL", (row["slot"],)).fetchone()
            if occupant is not None:
                conn.execute(
                    "UPDATE save_records SET trashed_at=? WHERE save_id=?",
                    (utc_now(), occupant[0]))
                swapped = occupant[0]
        conn.execute(
            "UPDATE save_records SET trashed_at=NULL WHERE save_id=?",
            (save_id,))
        conn.commit()
        return {"save_id": save_id, "restored": True, "swapped_to_trash": swapped}

    return _idempotent(conn, command_id, payload, utc_now, do_restore)


def purge_expired_trash(conn: sqlite3.Connection,
                        utc_now=_default_utc) -> list[str]:
    """§6.5：Save Trash 7 天到期物理删除记录行（不删共享 Snapshot）"""
    now = _parse_utc(utc_now())
    rows = conn.execute(
        "SELECT save_id, trashed_at FROM save_records"
        " WHERE trashed_at IS NOT NULL").fetchall()
    purged: list[str] = []
    for row in rows:
        if now > _parse_utc(row["trashed_at"]) + timedelta(days=SAVE_TRASH_DAYS):
            conn.execute("DELETE FROM save_records WHERE save_id=?",
                         (row["save_id"],))
            purged.append(row["save_id"])
    conn.commit()
    return purged

"""
幂等存储（DOC-BACKEND-010 RULE-BACKEND-055..057）

- (world_id, command_id) 唯一；含 payload_hash、result_ref、committed_revision、recorded_at
- 记录必须与状态变更、DomainEvent 在同一数据库事务写入；协议层拒绝不产生记录
- 命中幂等键直接返回原 CommandReceipt；hash 不一致 → BACKEND_IDEMPOTENCY_CONFLICT
- Retention：每世界至少 max(30 game days, 100000 条)；裁剪只在 Snapshot 检查点整批执行，
  且不早于 Event Log 重连补发窗口
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation.errors import ApiError

RETENTION_MIN_RECORDS = 100_000
RETENTION_MIN_GAME_DAYS = 30


def canonical_payload_hash(payload: object) -> str:
    """键排序、无空白序列化后的 SHA-256（杜绝字段顺序差异造成伪冲突）"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyRecord:
    world_id: str
    command_id: str
    payload_hash: str
    result_ref: str
    result_kind: str  # committed / failed
    committed_revision: Optional[int]
    recorded_at: str
    game_time: int = 0
    sequence: int = 0

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "world_id": self.world_id,
            "command_id": self.command_id,
            "payload_hash": self.payload_hash,
            "result_ref": self.result_ref,
            "result_kind": self.result_kind,
            "committed_revision": self.committed_revision,
            "recorded_at": self.recorded_at,
            "game_time": self.game_time,
        }


class IdempotencyConflict(Exception):
    pass


class IdempotencyStore:
    """内存实现（SQLite 适配由 persistence 阶段提供；接口一致）"""

    def __init__(self, utc_now: Callable[[], str]) -> None:
        self._utc_now = utc_now
        self._records: Dict[Tuple[str, str], IdempotencyRecord] = {}
        self._sequence = 0

    def lookup(self, world_id: str, command_id: str,
               payload_hash: str) -> Optional[IdempotencyRecord]:
        """命中返回原记录；hash 不一致 → BACKEND_IDEMPOTENCY_CONFLICT"""
        record = self._records.get((world_id, command_id))
        if record is None:
            return None
        if record.payload_hash != payload_hash:
            raise ApiError("BACKEND_IDEMPOTENCY_CONFLICT", {
                "world_id": world_id,
                "command_id": command_id,
                "reason_code": "payload_hash_mismatch",
            })
        return record

    def stage(self, record: IdempotencyRecord) -> IdempotencyRecord:
        """UoW 内调用：写入记录（与状态/事件同一事务语义由 UoW 保证）"""
        self._sequence += 1
        record.sequence = self._sequence
        self._records[(record.world_id, record.command_id)] = record
        return record

    def count(self, world_id: Optional[str] = None) -> int:
        if world_id is None:
            return len(self._records)
        return sum(1 for key in self._records if key[0] == world_id)

    def prune_at_checkpoint(self, world_id: str,
                            keep_min_records: int = RETENTION_MIN_RECORDS,
                            keep_min_game_days: int = RETENTION_MIN_GAME_DAYS,
                            current_game_day: int = 0,
                            min_sequence_floor: int = 0) -> int:
        """
        Snapshot 检查点整批裁剪：保留最新 keep_min_records 条，
        且不裁 game_time 在 keep_min_game_days 内的记录，
        sequence ≤ min_sequence_floor 之外（Event Log 补发窗口保护由调用方给出）。
        返回裁剪条数。
        """
        records = sorted(
            (r for key, r in self._records.items() if key[0] == world_id),
            key=lambda r: r.sequence,
        )
        if len(records) <= keep_min_records:
            return 0
        removable = records[: len(records) - keep_min_records]
        game_day_floor = current_game_day - keep_min_game_days
        pruned = 0
        for record in removable:
            if record.sequence > min_sequence_floor and min_sequence_floor > 0:
                continue
            if record.game_time // 1440 >= game_day_floor and game_day_floor > 0:
                continue
            del self._records[(record.world_id, record.command_id)]
            pruned += 1
        return pruned

    def all_records(self, world_id: str) -> List[IdempotencyRecord]:
        return sorted(
            (r for key, r in self._records.items() if key[0] == world_id),
            key=lambda r: r.sequence,
        )

"""
追加式事件日志（RULE-FOUNDATION-022/027 的 EVENT 侧落地）

- 全世界一条 append-only 日志；revision 从 0 单调递增
- entry 一经提交不得修改、删除或重排
- Oracle 与 Golden Replay 只读本日志与已提交状态
"""

from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional


class EventLogError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class AppendOnlyEventLog:
    def __init__(self, world_id: str, id_factory: Callable[[], str]) -> None:
        self._world_id = world_id
        self._id_factory = id_factory
        self._entries: List[Dict] = []

    def append(
        self,
        event_type: str,
        payload: dict,
        game_time: int,
        caused_by_command_id: Optional[str] = None,
    ) -> Dict:
        entry = {
            "event_id": self._id_factory(),
            "event_type": event_type,
            "world_id": self._world_id,
            "revision": len(self._entries),
            "game_time": game_time,
            "caused_by_command_id": caused_by_command_id,
            "payload": copy.deepcopy(payload),
        }
        self._entries.append(entry)
        return entry

    def entries(self) -> List[Dict]:
        return list(self._entries)

    def timeline(self) -> List[tuple]:
        """(revision, event_type) 序列——Scenario Fixture 预期时间线的对比基"""
        return [(e["revision"], e["event_type"]) for e in self._entries]

    def __len__(self) -> int:
        return len(self._entries)

    def snapshot(self) -> int:
        return len(self._entries)

    def restore(self, snapshot: int) -> None:
        del self._entries[snapshot:]

    def export_state(self) -> list:
        return copy.deepcopy(self._entries)

    def import_state(self, data: list) -> None:
        self._entries = copy.deepcopy(data)

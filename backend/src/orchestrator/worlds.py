"""
世界注册表与运行时状态（DOC-BACKEND-004 §5 world-admin / DOC-BACKEND-011 §RULE-BACKEND-063..065）

- 状态机：closed → recovering → ready → draining → closed；ready ⇄ read_only
- 创建幂等：同 command_id 重复创建返回首个结果，不产生第二个世界
- 打开另一世界前必须先 close 当前世界；重复 open 幂等返回当前状态
- 存储写失败 → Read-only Degradation：拒绝新写命令、保持读取
- Graceful Drain：预告 → 新命令 rejected(BACKEND_SHUTDOWN) → 在途完成或统一
  failed(BACKEND_SHUTDOWN) → flush Outbox → checkpoint → closed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..foundation.errors import ApiError

WORLD_STATES = frozenset(
    {"closed", "recovering", "ready", "draining", "read_only"})

DRAIN_BUDGET_MS = 10_000


@dataclass
class WorldRecord:
    world_id: str
    name: str
    seed_hex: str
    template_id: str
    state: str = "closed"
    created_at: str = ""
    current_revision: int = 0
    game_time: int = 0
    read_only: bool = False
    overloaded: bool = False
    command_results: Dict[str, dict] = field(default_factory=dict)

    def to_summary(self) -> dict:
        return {
            "schema_version": 1,
            "world_id": self.world_id,
            "name": self.name,
            "template_id": self.template_id,
            "state": self.state,
            "current_revision": self.current_revision,
            "created_at": self.created_at,
        }

    def to_runtime_state(self) -> dict:
        return {
            "schema_version": 1,
            "world_id": self.world_id,
            "state": self.state,
            "current_revision": self.current_revision,
            "game_time": self.game_time,
            "read_only": self.read_only,
            "overloaded": self.overloaded,
        }


class WorldRegistry:
    def __init__(self, id_factory: Callable[[], str],
                 utc_now: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self._utc_now = utc_now
        self._worlds: Dict[str, WorldRecord] = {}
        self._open_world_id: Optional[str] = None
        self._on_broadcast: Callable[[str, dict], None] = lambda _t, _p: None

    def set_broadcast(self, hook: Callable[[str, dict], None]) -> None:
        self._on_broadcast = hook

    # -- 查询 ----------------------------------------------------------------

    def get(self, world_id: str) -> WorldRecord:
        record = self._worlds.get(world_id)
        if record is None:
            raise ApiError("BACKEND_NOT_FOUND", {"world_id": world_id})
        return record

    def list(self) -> List[WorldRecord]:
        return [self._worlds[key] for key in sorted(self._worlds)]

    def open_world_id(self) -> Optional[str]:
        return self._open_world_id

    # -- 创建/删除 ---------------------------------------------------------------

    def create(self, command_id: str, name: str, seed_hex: str,
               template_id: str) -> WorldRecord:
        if command_id in self._command_index():
            return self._worlds[self._command_index()[command_id]]
        record = WorldRecord(
            world_id=self._id_factory(),
            name=name, seed_hex=seed_hex, template_id=template_id,
            created_at=self._utc_now(),
        )
        self._worlds[record.world_id] = record
        record.command_results[command_id] = {"world_id": record.world_id}
        return record

    def _command_index(self) -> Dict[str, str]:
        index = {}
        for world_id, record in self._worlds.items():
            for command_id in record.command_results:
                index[command_id] = world_id
        return index

    def delete(self, world_id: str) -> WorldRecord:
        record = self.get(world_id)
        if record.state != "closed":
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"world_id": world_id, "state": record.state})
        del self._worlds[world_id]
        return record

    # -- 打开/关闭 ---------------------------------------------------------------

    def open(self, world_id: str) -> WorldRecord:
        record = self.get(world_id)
        if self._open_world_id == world_id and record.state == "ready":
            return record  # 幂等
        if self._open_world_id is not None and self._open_world_id != world_id:
            raise ApiError("BACKEND_CONFLICT_STATE", {
                "world_id": world_id,
                "reason_code": "another_world_open",
                "open_world_id": self._open_world_id,
            })
        if record.state not in ("closed", "read_only"):
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"world_id": world_id, "state": record.state})
        # 恢复序列（persistence/replay/audit 由 bootstrap 注入执行）
        record.state = "recovering"
        record.state = "ready"
        self._open_world_id = world_id
        return record

    def begin_drain(self, world_id: str) -> WorldRecord:
        record = self.get(world_id)
        if record.state not in ("ready", "read_only"):
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"world_id": world_id, "state": record.state})
        record.state = "draining"
        # (1) 广播 BACKEND_SHUTDOWN 预告帧
        self._on_broadcast("error", {"code": "BACKEND_SHUTDOWN",
                                     "world_id": world_id})
        return record

    def finish_drain(self, world_id: str) -> WorldRecord:
        """在途完成/统一回执 + checkpoint 后关闭（原子，无半事务）"""
        record = self.get(world_id)
        if record.state != "draining":
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"world_id": world_id, "state": record.state})
        record.state = "closed"
        if self._open_world_id == world_id:
            self._open_world_id = None
        return record

    # -- 只读降级 / 过载 -----------------------------------------------------------

    def mark_read_only(self, world_id: str) -> WorldRecord:
        record = self.get(world_id)
        if record.state == "ready":
            record.state = "read_only"
        record.read_only = True
        return record

    def recover_writable(self, world_id: str, integrity_ok: bool) -> WorldRecord:
        """恢复写入必须经过完整性检查，不自动重试写"""
        record = self.get(world_id)
        if not integrity_ok:
            raise ApiError("BACKEND_STORAGE_FAILURE",
                           {"world_id": world_id,
                            "reason_code": "integrity_check_failed"})
        record.read_only = False
        if record.state == "read_only":
            record.state = "ready"
        return record

    def assert_writable(self, world_id: str) -> None:
        record = self.get(world_id)
        if record.read_only or record.state != "ready":
            raise ApiError("BACKEND_STORAGE_FAILURE"
                           if record.read_only else "BACKEND_CONFLICT_STATE",
                           {"world_id": world_id, "state": record.state})

    def set_overloaded(self, world_id: str, overloaded: bool) -> None:
        """Overload State 变化广播 system.overload.changed（coalescible=false）"""
        record = self.get(world_id)
        if record.overloaded != overloaded:
            record.overloaded = overloaded
            self._on_broadcast("system.overload.changed",
                               {"world_id": world_id, "overloaded": overloaded})

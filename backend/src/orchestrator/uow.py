"""
Unit of Work 提交协议与 World Writer（DOC-BACKEND-010 RULE-BACKEND-058/010/059）

- 单一 World Writer 串行：BEGIN → 写状态 → append 事件 → 写幂等记录 →
  消费/释放 Reservation → Commit Check → COMMIT → Revision +1
- 任一步失败整体回滚、Revision 不变、不发布任何事件
- 幂等命中直接返回原回执；committed/failed 两种终局都物化
- External Effect 不进 UoW：提交意图事件 → 异步执行 → 结果以新命令回队列重校验
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..foundation.errors import ApiError
from .commands import (
    CommandRegistry,
    check_strict_revision,
    make_receipt,
)
from .events import validate_event_envelope
from .idempotency import IdempotencyRecord, IdempotencyStore, canonical_payload_hash

#: UoW 步骤（故障注入点）
UOW_STEPS = (
    "begin", "write_state", "append_events", "write_idempotency",
    "consume_reservations", "commit_check", "commit",
)


class StorageFailure(Exception):
    """存储层故障（含故障注入）：当前 UoW 回滚、Revision 不变"""


@dataclass
class WorldData:
    state: dict = field(default_factory=dict)
    events: List[dict] = field(default_factory=list)
    revision: int = 0
    reservations: List[dict] = field(default_factory=list)


class WorldStore:
    """内存持久化 port（SQLite 适配由 persistence 阶段按同接口实现）"""

    def __init__(self) -> None:
        self._worlds: Dict[str, WorldData] = {}
        self.fail_at: Optional[str] = None  # 故障注入：步骤名
        self.step_log: List[str] = []       # 测试观察：已执行步骤序列

    def open_world(self, world_id: str) -> WorldData:
        data = self._worlds.get(world_id)
        if data is None:
            data = WorldData()
            self._worlds[world_id] = data
        return data

    def get(self, world_id: str) -> WorldData:
        return self.open_world(world_id)

    def current_revision(self, world_id: str) -> int:
        return self.get(world_id).revision

    def _step(self, name: str) -> None:
        self.step_log.append(name)
        if self.fail_at == name:
            raise StorageFailure(name)

    def apply_uow(self, world_id: str, uow: "UnitOfWork",
                  idempotency: IdempotencyStore,
                  commit_check: Callable[[dict], List[str]]) -> int:
        """RULE-BACKEND-058 顺序；任一步 StorageFailure → 全部不生效"""
        data = self.open_world(world_id)
        self._step("begin")
        #  staging 缓冲区先备好；失败即抛，data 不被触碰（回滚语义）
        self._step("write_state")
        self._step("append_events")
        self._step("write_idempotency")
        self._step("consume_reservations")
        self._step("commit_check")
        violations = commit_check({
            "world_id": world_id,
            "staged_state": uow.staged_state,
            "staged_events": uow.staged_events,
            "staged_reservations": uow.staged_reservations,
        })
        if violations:
            raise ApiError("BACKEND_INTERNAL_INVARIANT",
                           {"reason_code": f"commit_check:{violations[0]}"})
        self._step("commit")
        # —— 提交点：此前任何失败都不触及 data ——
        data.state.update(uow.staged_state)
        data.events.extend(uow.staged_events)
        for record in uow.staged_idempotency:
            idempotency.stage(record)
        data.reservations.extend(uow.staged_reservations)
        data.revision += 1
        return data.revision


class UnitOfWork:
    def __init__(self, world_id: str, base_revision: int) -> None:
        self.world_id = world_id
        self.base_revision = base_revision
        self.staged_state: Dict[str, object] = {}
        self.staged_events: List[dict] = []
        self.staged_idempotency: List[IdempotencyRecord] = []
        self.staged_reservations: List[dict] = []

    def stage_state(self, key: str, value: object) -> None:
        self.staged_state[key] = value

    def stage_events(self, events: List[dict]) -> None:
        self.staged_events.extend(events)

    def stage_idempotency(self, record: IdempotencyRecord) -> None:
        self.staged_idempotency.append(record)

    def stage_reservations(self, outcomes: List[dict]) -> None:
        self.staged_reservations.extend(outcomes)


class WorldWriter:
    """每世界唯一串行提交者（DES-BACKEND-010 run_uow 仅此处调用）"""

    def __init__(self, store: WorldStore, idempotency: IdempotencyStore,
                 commands: CommandRegistry, events,
                 id_factory: Callable[[], str],
                 utc_now: Callable[[], str],
                 domain_apply: Callable[[str, str, dict, dict], dict],
                 commit_check: Optional[Callable[[dict], List[str]]] = None,
                 on_storage_failure: Optional[Callable[[str], None]] = None) -> None:
        self._store = store
        self._idempotency = idempotency
        self._commands = commands
        self._events = events
        self._id_factory = id_factory
        self._utc_now = utc_now
        self._domain_apply = domain_apply
        self._commit_check = commit_check or (lambda _ctx: [])
        self._on_storage_failure = on_storage_failure

    def lookup_receipt(self, world_id: str, command_id: str,
                       payload_hash: str) -> Optional[dict]:
        record = self._idempotency.lookup(world_id, command_id, payload_hash)
        return record.receipt if record else None

    def execute(self, envelope: dict, game_time: int = 0) -> dict:
        """幂等查询 → UoW 提交/回滚 → 恰好一份终局回执"""
        world_id = envelope["world_id"]
        command_id = envelope["command_id"]
        payload_hash = canonical_payload_hash(envelope["payload"])
        spec = self._commands.get(envelope["type"])

        # 幂等命中：直接返回原回执（只读查询，不占事务）
        record = self._idempotency.lookup(world_id, command_id, payload_hash)
        if record is not None:
            return record.receipt

        # Strict Revision 以执行时刻为准；单写者 ⇒ next_revision 提交前可确定
        current = self._store.current_revision(world_id)
        try:
            check_strict_revision(spec, envelope["expected_revision"], current)
        except ApiError as exc:
            # 协议层拒绝：不写幂等记录
            return make_receipt(command_id, "rejected", error=exc.to_error_object())
        next_revision = current + 1

        uow = UnitOfWork(world_id, current)
        context = {
            "world_id": world_id,
            "command_id": command_id,
            "revision": next_revision,
            "game_time": game_time,
            "id_factory": self._id_factory,
        }
        domain_error: Optional[ApiError] = None
        try:
            result = self._domain_apply(world_id, envelope["type"],
                                        envelope["payload"], context)
            for key, value in result.get("state", {}).items():
                uow.stage_state(key, value)
            events = result.get("events", [])
            for event in events:
                validate_event_envelope(self._events, event)
            uow.stage_events(events)
            uow.stage_reservations(result.get("reservations", []))
        except ApiError as exc:
            domain_error = exc
        except Exception:  # noqa: BLE001 - Domain 未登记异常按内部错误
            domain_error = ApiError("BACKEND_INTERNAL_INVARIANT",
                                    {"reason_code": "domain_exception"})

        if domain_error is not None:
            # Domain 拒绝：failed 回执物化——空状态/事件，仅幂等记录随 UoW 提交
            uow.staged_state.clear()
            uow.staged_events.clear()
            uow.staged_reservations.clear()
            receipt = make_receipt(command_id, "failed",
                                   error=domain_error.to_error_object())
            uow.stage_idempotency(_make_record(
                envelope, payload_hash, receipt, None, self._utc_now(), game_time))
        else:
            receipt = make_receipt(
                command_id, "committed", committed_revision=next_revision,
                event_ids=[e["event_id"] for e in uow.staged_events])
            uow.stage_idempotency(_make_record(
                envelope, payload_hash, receipt, next_revision,
                self._utc_now(), game_time))

        try:
            revision = self._store.apply_uow(
                world_id, uow, self._idempotency, self._commit_check)
        except StorageFailure:
            # 回滚：Revision 不变、不发布事件；世界上报只读降级
            if self._on_storage_failure is not None:
                self._on_storage_failure(world_id)
            return make_receipt(
                command_id, "failed",
                error=ApiError("BACKEND_STORAGE_FAILURE").to_error_object())
        if domain_error is None:
            receipt["committed_revision"] = revision
        return receipt


def _make_record(envelope: dict, payload_hash: str, receipt: dict,
                 revision: Optional[int], recorded_at: str,
                 game_time: int) -> IdempotencyRecord:
    record = IdempotencyRecord(
        world_id=envelope["world_id"],
        command_id=envelope["command_id"],
        payload_hash=payload_hash,
        result_ref=f"receipt/{envelope['command_id']}",
        result_kind=receipt["result"] if receipt["result"] in ("committed", "failed") else "failed",
        committed_revision=revision,
        recorded_at=recorded_at,
        game_time=game_time,
    )
    record.receipt = receipt  # 物化回执（内存实现随记录携带）
    return record

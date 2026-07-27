"""
后果传播与善后任务（DOC-EVENT-005）

- 幂等键 (world_event_id, consequence_id)；重放记 consequence_replayed
- 目标实体不存在 → completed_noop
- owner_unavailable = transient 重试；port_rejected = terminal 留 pending
- Aftermath Task 六类；pending 未清不得 archived（镇长可 cancel 放行，带审计标记）
- 经济后果只发 Region Modifier（稳定 ID）；认知按公开程度分发，绝不注入 Secret
- 地图后果必须 NavigationPatch + WorldDiff（经 MapChangeCommitter）
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .constants import AFTERMATH_TASK_TRANSITIONS
from .templates import ConsequenceSpec, EventTemplateRegistry


class ConsequenceError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class OwnerUnavailable(Exception):
    """transient：owner 暂不可用，后果留 pending_transient 稍后重试"""


class PortRejected(Exception):
    """terminal：owner 拒绝，后果留 pending_terminal 不再重试"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class ConsequenceRecord:
    world_event_id: str
    consequence_id: str
    status: str  # completed / completed_noop / pending_transient / pending_terminal
    attempts: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "world_event_id": self.world_event_id,
            "consequence_id": self.consequence_id,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }

    @staticmethod
    def from_dict(data: dict) -> "ConsequenceRecord":
        return ConsequenceRecord(
            world_event_id=data["world_event_id"],
            consequence_id=data["consequence_id"],
            status=data["status"],
            attempts=data["attempts"],
            last_error=data["last_error"],
        )


@dataclass
class AftermathTask:
    task_id: str
    world_event_id: str
    task_kind: str
    state: str
    parameters: dict
    created_game_time: int
    version: int = 0
    assignee: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "world_event_id": self.world_event_id,
            "task_kind": self.task_kind,
            "state": self.state,
            "parameters": copy.deepcopy(self.parameters),
            "created_game_time": self.created_game_time,
            "version": self.version,
            "assignee": self.assignee,
        }

    @staticmethod
    def from_dict(data: dict) -> "AftermathTask":
        return AftermathTask(
            schema_version=data["schema_version"],
            task_id=data["task_id"],
            world_event_id=data["world_event_id"],
            task_kind=data["task_kind"],
            state=data["state"],
            parameters=copy.deepcopy(data["parameters"]),
            created_game_time=data["created_game_time"],
            version=data["version"],
            assignee=data["assignee"],
        )


class AftermathBoard:
    def __init__(self, event_log: object, id_factory: Callable[[], str],
                 templates: EventTemplateRegistry) -> None:
        self._log = event_log
        self._id_factory = id_factory
        self._templates = templates
        self._tasks: Dict[str, AftermathTask] = {}

    def get(self, task_id: str) -> AftermathTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise ConsequenceError("aftermath_task_unknown", task_id) from None

    def all(self) -> List[AftermathTask]:
        return list(self._tasks.values())

    def pending_count(self, world_event_id: str) -> int:
        return sum(
            1 for t in self._tasks.values()
            if t.world_event_id == world_event_id and t.state in ("pending", "in_progress")
        )

    def create_from_event(self, event: object, game_time: int) -> List[str]:
        """事件进入 aftermath 时按模板 aftermath_plan 生成任务"""
        template = self._templates.get(event.event_template_id)
        task_ids: List[str] = []
        for spec in template.aftermath_plan:
            task_ids.append(self.register(
                event.world_event_id, spec.task_kind, dict(spec.parameters), game_time,
            ))
        return task_ids

    def register(self, world_event_id: str, task_kind: str,
                 parameters: dict, game_time: int) -> str:
        task = AftermathTask(
            task_id=self._id_factory(),
            world_event_id=world_event_id,
            task_kind=task_kind,
            state="pending",
            parameters=copy.deepcopy(parameters),
            created_game_time=game_time,
        )
        self._tasks[task.task_id] = task
        self._log.append(
            "aftermath_task.registered",
            {"task_id": task.task_id, "world_event_id": world_event_id,
             "task_kind": task_kind},
            game_time,
        )
        return task.task_id

    def _transition(self, task: AftermathTask, target: str, game_time: int,
                    mayor: bool, admin: bool) -> AftermathTask:
        if (task.state, target) not in AFTERMATH_TASK_TRANSITIONS:
            raise ConsequenceError(
                "state_transition_illegal", f"{task.state} → {target}"
            )
        if target == "cancelled" and not (mayor or admin):
            raise ConsequenceError("aftermath_cancel_forbidden", "mayor/admin only")
        task.state = target
        task.version += 1
        self._log.append(
            f"aftermath_task.{target}",
            {"task_id": task.task_id, "world_event_id": task.world_event_id,
             "mayor_marked": mayor, "admin_marked": admin},
            game_time,
        )
        return task

    def start(self, task_id: str, game_time: int, expected_version: int,
              assignee: Optional[str] = None) -> AftermathTask:
        task = self.get(task_id)
        if task.version != expected_version:
            raise ConsequenceError("version_stale", f"{task.version} != {expected_version}")
        task.assignee = assignee
        return self._transition(task, "in_progress", game_time, mayor=False, admin=False)

    def complete(self, task_id: str, game_time: int, expected_version: int) -> AftermathTask:
        task = self.get(task_id)
        if task.version != expected_version:
            raise ConsequenceError("version_stale", f"{task.version} != {expected_version}")
        return self._transition(task, "completed", game_time, mayor=False, admin=False)

    def cancel(self, task_id: str, game_time: int, expected_version: int,
               mayor: bool = False, admin: bool = False) -> AftermathTask:
        task = self.get(task_id)
        if task.version != expected_version:
            raise ConsequenceError("version_stale", f"{task.version} != {expected_version}")
        return self._transition(task, "cancelled", game_time, mayor=mayor, admin=admin)

    def export_state(self) -> dict:
        return {tid: t.to_dict() for tid, t in self._tasks.items()}

    def import_state(self, data: dict) -> None:
        self._tasks = {tid: AftermathTask.from_dict(t) for tid, t in data.items()}


class ConsequenceDispatcher:
    """
    阶段后果分发。ports 路由：
      econ.register_region_modifier / resident.notify / map（committer 四件套）/
      memory.distribute / quest.offer / environment.apply
    """

    def __init__(
        self,
        templates: EventTemplateRegistry,
        event_log: object,
        econ_port: object,
        resident_port: object,
        memory_port: object,
        map_consequence_handler: Optional[Callable[[dict, dict, int], None]] = None,
        quest_offer_handler: Optional[Callable[[dict, dict, int], None]] = None,
        environment_handler: Optional[Callable[[dict, dict, int], None]] = None,
    ) -> None:
        self._templates = templates
        self._log = event_log
        self._econ = econ_port
        self._resident = resident_port
        self._memory = memory_port
        self._map_handler = map_consequence_handler
        self._quest_handler = quest_offer_handler
        self._environment_handler = environment_handler
        self._records: Dict[Tuple[str, str], ConsequenceRecord] = {}

    def records(self) -> List[ConsequenceRecord]:
        return list(self._records.values())

    def record_of(self, world_event_id: str, consequence_id: str) -> Optional[ConsequenceRecord]:
        return self._records.get((world_event_id, consequence_id))

    def dispatch_phase(self, event: object, phase: str, game_time: int) -> None:
        template = self._templates.get(event.event_template_id)
        for spec in template.consequence_plan:
            if spec.phase != phase:
                continue
            self._dispatch_one(event, spec, game_time)

    def _dispatch_one(self, event: object, spec: ConsequenceSpec, game_time: int) -> None:
        key = (event.world_event_id, spec.consequence_id)
        if key in self._records and self._records[key].status in (
            "completed", "completed_noop", "pending_terminal",
        ):
            self._log.append(
                "consequence_replayed",
                {"world_event_id": event.world_event_id,
                 "consequence_id": spec.consequence_id},
                game_time,
            )
            return
        record = self._records.get(key) or ConsequenceRecord(
            world_event_id=event.world_event_id,
            consequence_id=spec.consequence_id,
            status="pending_transient",
        )
        record.attempts += 1
        try:
            self._route(event, spec, game_time)
            record.status = "completed"
            record.last_error = None
        except TargetMissing:
            record.status = "completed_noop"
            record.last_error = None
        except OwnerUnavailable as exc:
            record.status = "pending_transient"
            record.last_error = str(exc)
        except PortRejected as exc:
            record.status = "pending_terminal"
            record.last_error = exc.code
        self._records[key] = record
        self._log.append(
            "consequence.dispatched",
            {
                "world_event_id": event.world_event_id,
                "consequence_id": spec.consequence_id,
                "phase": spec.phase,
                "status": record.status,
                "attempts": record.attempts,
            },
            game_time,
        )

    def _route(self, event: object, spec: ConsequenceSpec, game_time: int) -> None:
        params = dict(spec.parameters)
        if spec.target_domain == "econ":
            # 经济后果只发 Region Modifier，稳定 ID：同一后果重复分发不产生第二个 modifier
            modifier_id = params.get("modifier_id") or (
                f"region_modifier.{event.world_event_id}.{spec.consequence_id}"
            )
            self._econ.register_region_modifier(
                modifier_id=modifier_id,
                region_id=params["region_id"],
                modifier=dict(params.get("modifier", {})),
                evidence_id=event.world_event_id,
            )
        elif spec.target_domain == "resident":
            self._resident.notify(
                params["resident_id"], spec.port, dict(params.get("content", {})),
                evidence_id=event.world_event_id,
            )
        elif spec.target_domain == "memory":
            # 认知按公开程度分发；绝不注入 Secret（publicity 由模板约束）
            self._memory.distribute(
                publicity=spec.publicity,
                audience=dict(params.get("audience", {})),
                content=dict(params.get("content", {})),
                evidence_id=event.world_event_id,
            )
        elif spec.target_domain == "map":
            if self._map_handler is None:
                raise OwnerUnavailable("map handler not bound")
            self._map_handler(event, params, game_time)
        elif spec.target_domain == "quest":
            if self._quest_handler is None:
                raise OwnerUnavailable("quest handler not bound")
            self._quest_handler(event, params, game_time)
        elif spec.target_domain == "environment":
            if self._environment_handler is None:
                raise OwnerUnavailable("environment handler not bound")
            self._environment_handler(event, params, game_time)

    def retry_pending(self, occurrence: dict, events_by_id: Dict[str, object]) -> dict:
        """occurrence kind=consequence_retry：重试 pending_transient 记录"""
        key = occurrence["occurrence_key"]
        game_time = occurrence["game_time"]
        retried: List[str] = []
        for record in self._records.values():
            if record.status != "pending_transient":
                continue
            event = events_by_id.get(record.world_event_id)
            if event is None:
                continue
            template = self._templates.get(event.event_template_id)
            spec = next(
                (s for s in template.consequence_plan
                 if s.consequence_id == record.consequence_id),
                None,
            )
            if spec is None:
                continue
            self._dispatch_one(event, spec, game_time)
            retried.append(record.consequence_id)
        self._log.append(
            "consequence.retry_run",
            {"occurrence_key": key, "retried": retried},
            game_time,
        )
        return {"status": "processed", "retried": retried}

    def export_state(self) -> dict:
        return {f"{k[0]}|{k[1]}": v.to_dict() for k, v in self._records.items()}

    def import_state(self, data: dict) -> None:
        self._records = {}
        for key, value in data.items():
            record = ConsequenceRecord.from_dict(value)
            self._records[(record.world_event_id, record.consequence_id)] = record


class TargetMissing(Exception):
    """目标实体不存在：后果记 completed_noop"""

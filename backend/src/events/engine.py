"""
WorldEvent 引擎（DOC-EVENT-001）

- 生命周期 candidate→scheduled→active→escalated|resolved|failed|expired→aftermath→archived
- 时间驱动转换只经 TIME Scheduled Event（occurrence），禁止逐 Tick 扫描
- 三层防重：occurrence key / (world_id, command_id) / 语义窗口去重
- 激活时检查 Narrative Pressure Budget、active 上限、crisis 并发与冷却
- admin 来源必须带审计标记（RULE-FOUNDATION-030）
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .budget import BudgetError, NarrativePressureLedger
from .constants import (
    ACTIVE_EVENT_CAP,
    EVENT_SOURCES,
    EVENT_TRANSITIONS,
    SEVERITIES,
    TERMINAL_EVENT_STATES,
)
from .templates import EventTemplateRegistry, TemplateError


class EventError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class WorldEvent:
    world_event_id: str
    event_template_id: str
    source: str
    source_evidence_id: Optional[str]
    severity: str
    state: str
    scope: dict
    parameters: dict
    scheduled_start: Optional[int]
    deadline: Optional[int]
    created_game_time: int
    version: int = 0
    aftermath_task_ids: List[str] = field(default_factory=list)
    occurrence_key: Optional[str] = None
    admin_marked: bool = False
    archive_reason: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "world_event_id": self.world_event_id,
            "event_template_id": self.event_template_id,
            "source": self.source,
            "source_evidence_id": self.source_evidence_id,
            "severity": self.severity,
            "state": self.state,
            "scope": copy.deepcopy(self.scope),
            "parameters": copy.deepcopy(self.parameters),
            "scheduled_start": self.scheduled_start,
            "deadline": self.deadline,
            "created_game_time": self.created_game_time,
            "version": self.version,
            "aftermath_task_ids": list(self.aftermath_task_ids),
            "occurrence_key": self.occurrence_key,
            "admin_marked": self.admin_marked,
            "archive_reason": self.archive_reason,
        }

    @staticmethod
    def from_dict(data: dict) -> "WorldEvent":
        return WorldEvent(
            schema_version=data["schema_version"],
            world_event_id=data["world_event_id"],
            event_template_id=data["event_template_id"],
            source=data["source"],
            source_evidence_id=data["source_evidence_id"],
            severity=data["severity"],
            state=data["state"],
            scope=copy.deepcopy(data["scope"]),
            parameters=copy.deepcopy(data["parameters"]),
            scheduled_start=data["scheduled_start"],
            deadline=data["deadline"],
            created_game_time=data["created_game_time"],
            version=data["version"],
            aftermath_task_ids=list(data["aftermath_task_ids"]),
            occurrence_key=data["occurrence_key"],
            admin_marked=data["admin_marked"],
            archive_reason=data["archive_reason"],
        )


#: 状态 → 后果阶段（DOC-EVENT-005）
_PHASE_BY_STATE = {
    "scheduled": "on_scheduled",
    "active": "on_active",
    "escalated": "on_escalated",
    "aftermath": "on_aftermath",
}


class EventEngine:
    def __init__(
        self,
        world_id: str,
        templates: EventTemplateRegistry,
        budget: NarrativePressureLedger,
        event_log: object,
        id_factory: Callable[[], str],
        scene_exists: Callable[[str], bool],
    ) -> None:
        self._world_id = world_id
        self._templates = templates
        self._budget = budget
        self._log = event_log
        self._id_factory = id_factory
        self._scene_exists = scene_exists
        self._events: Dict[str, WorldEvent] = {}
        self._command_results: Dict[str, dict] = {}
        self._occurrences: Dict[str, dict] = {}
        #: 后果阶段分发钩子（consequences 模块注册）
        self._phase_dispatchers: List[Callable[[WorldEvent, str, int], None]] = []
        #: archive 前 pending Aftermath Task 检查（consequences 模块注册）
        self._pending_aftermath_check: Optional[Callable[[str], int]] = None
        self._aftermath_task_factory: Optional[Callable[[WorldEvent, int], List[str]]] = None

    # -- 装配钩子 -------------------------------------------------------------

    def register_phase_dispatcher(self, dispatcher: Callable[[WorldEvent, str, int], None]) -> None:
        self._phase_dispatchers.append(dispatcher)

    def bind_aftermath(
        self,
        pending_check: Callable[[str], int],
        task_factory: Callable[[WorldEvent, int], List[str]],
    ) -> None:
        self._pending_aftermath_check = pending_check
        self._aftermath_task_factory = task_factory

    # -- 查询 -----------------------------------------------------------------

    def get(self, world_event_id: str) -> WorldEvent:
        try:
            return self._events[world_event_id]
        except KeyError:
            raise EventError("world_event_unknown", world_event_id) from None

    def all(self) -> List[WorldEvent]:
        return list(self._events.values())

    def active_events(self) -> List[WorldEvent]:
        return [e for e in self._events.values() if e.state in ("active", "escalated")]

    def non_archived(self, event_template_id: str, scope: dict) -> List[WorldEvent]:
        return [
            e for e in self._events.values()
            if e.event_template_id == event_template_id
            and e.scope == scope
            and e.state != "archived"
        ]

    # -- 实例化（三层防重） ------------------------------------------------------

    def instantiate(
        self,
        command_id: str,
        event_template_id: str,
        source: str,
        source_evidence_id: Optional[str],
        scope: dict,
        parameters: dict,
        game_time: int,
        severity: Optional[str] = None,
        scheduled_start: Optional[int] = None,
        deadline: Optional[int] = None,
        occurrence_key: Optional[str] = None,
        admin: bool = False,
    ) -> WorldEvent:
        # 防重层 2：命令幂等
        if command_id in self._command_results:
            cached = self._command_results[command_id]
            return self.get(cached["world_event_id"])
        try:
            template = self._templates.get(event_template_id)
        except TemplateError as exc:
            raise EventError(exc.code, str(exc)) from None
        # 来源许可
        if source not in EVENT_SOURCES or source not in template.allowed_sources:
            raise EventError("source_not_permitted", f"{source} → {event_template_id}")
        if source == "admin" and not admin:
            raise EventError("source_not_permitted", "admin source requires admin mark")
        try:
            template.validate_parameters(parameters)
            template.validate_scope(scope)
        except TemplateError as exc:
            raise EventError(exc.code, str(exc)) from None
        if not self._scene_exists(scope["scene_id"]):
            raise EventError("scope_invalid", f"scene {scope['scene_id']} unknown")
        chosen_severity = severity or template.default_severity
        if chosen_severity not in SEVERITIES:
            raise EventError("parameters_invalid", f"severity {chosen_severity}")
        # 防重层 1：occurrence key
        if occurrence_key is not None and occurrence_key in self._occurrences:
            raise EventError("occurrence_replayed", occurrence_key)
        # 防重层 3：语义窗口
        for existing in self.non_archived(event_template_id, scope):
            if game_time - existing.created_game_time < template.dedup_window_game_minutes:
                raise EventError(
                    "duplicate_semantic_window",
                    f"{event_template_id}@{json.dumps(scope, sort_keys=True)}",
                )
        concurrent = sum(
            1 for e in self._events.values()
            if e.event_template_id == event_template_id and e.state in ("active", "escalated")
        )
        if concurrent >= template.max_concurrent_instances:
            raise EventError("max_concurrent_exceeded", event_template_id)

        event = WorldEvent(
            world_event_id=self._id_factory(),
            event_template_id=event_template_id,
            source=source,
            source_evidence_id=source_evidence_id,
            severity=chosen_severity,
            state="candidate",
            scope=copy.deepcopy(scope),
            parameters=copy.deepcopy(parameters),
            scheduled_start=scheduled_start,
            deadline=deadline,
            created_game_time=game_time,
            occurrence_key=occurrence_key,
            admin_marked=(source == "admin"),
        )
        self._events[event.world_event_id] = event
        if occurrence_key is not None:
            self._occurrences[occurrence_key] = {"world_event_id": event.world_event_id}
        self._log.append(
            "world_event.instantiated",
            {
                "world_event_id": event.world_event_id,
                "event_template_id": event_template_id,
                "source": source,
                "source_evidence_id": source_evidence_id,
                "severity": chosen_severity,
                "scope": copy.deepcopy(scope),
                "admin_marked": event.admin_marked,
            },
            game_time,
            caused_by_command_id=command_id,
        )
        if scheduled_start is not None:
            self._apply_transition(event, "scheduled", game_time, reason="scheduled_start")
        self._command_results[command_id] = {"world_event_id": event.world_event_id}
        return event

    # -- 状态迁移 -----------------------------------------------------------------

    def transition(
        self,
        world_event_id: str,
        target: str,
        game_time: int,
        expected_version: int,
        reason: Optional[str] = None,
        admin: bool = False,
        cooldown_game_minutes: int = 0,
    ) -> WorldEvent:
        event = self.get(world_event_id)
        if event.version != expected_version:
            raise EventError("version_stale", f"{event.version} != {expected_version}")
        return self._do_transition(
            event, target, game_time, reason=reason, admin=admin,
            cooldown_game_minutes=cooldown_game_minutes,
        )

    def _apply_transition(self, event: WorldEvent, target: str, game_time: int,
                          reason: Optional[str]) -> None:
        """实例化内部的合法迁移（candidate→scheduled），不走版本校验"""
        event.state = target
        event.version += 1
        self._log.append(
            f"world_event.{target}",
            {"world_event_id": event.world_event_id, "reason": reason},
            game_time,
        )
        phase = _PHASE_BY_STATE.get(target)
        if phase:
            self._dispatch_phase(event, phase, game_time)

    def _do_transition(
        self, event: WorldEvent, target: str, game_time: int,
        reason: Optional[str], admin: bool, cooldown_game_minutes: int,
    ) -> WorldEvent:
        if (event.state, target) not in EVENT_TRANSITIONS:
            raise EventError("state_transition_illegal", f"{event.state} → {target}")
        template = self._templates.get(event.event_template_id)
        if target == "active":
            if event.state == "scheduled":
                if event.scheduled_start is not None and game_time < event.scheduled_start:
                    raise EventError("state_transition_illegal", "before scheduled_start")
                if event.deadline is not None and game_time > event.deadline:
                    raise EventError("deadline_passed", event.world_event_id)
            if len(self.active_events()) >= ACTIVE_EVENT_CAP:
                raise EventError("budget_exceeded", "active event cap 16")
            try:
                self._budget.check_cooldown(
                    event.event_template_id, event.scope["scene_id"], game_time,
                    cooldown_game_minutes, template.is_disaster, admin=admin,
                )
                self._budget.reserve(event.world_event_id, event.severity, game_time)
            except BudgetError as exc:
                raise EventError(exc.code, str(exc)) from None
            self._budget.mark_activation(
                event.event_template_id, event.scope["scene_id"], game_time
            )
        if target == "aftermath":
            self._budget.release_to_aftermath(event.world_event_id, game_time)
        if target == "archived":
            pending = self._pending_aftermath_check(event.world_event_id) if self._pending_aftermath_check else 0
            if pending > 0:
                raise EventError(
                    "state_transition_illegal",
                    f"{pending} pending aftermath tasks block archive",
                )
            self._budget.drop(event.world_event_id)
            event.archive_reason = reason
        event.state = target
        event.version += 1
        self._log.append(
            f"world_event.{target}",
            {
                "world_event_id": event.world_event_id,
                "event_template_id": event.event_template_id,
                "severity": event.severity,
                "reason": reason,
                "admin_marked": event.admin_marked or admin,
            },
            game_time,
        )
        if target in TERMINAL_EVENT_STATES:
            self._dispatch_phase(event, "on_terminal", game_time)
        else:
            phase = _PHASE_BY_STATE.get(target)
            if phase:
                self._dispatch_phase(event, phase, game_time)
        if target == "aftermath" and self._aftermath_task_factory is not None:
            event.aftermath_task_ids.extend(self._aftermath_task_factory(event, game_time))
        return event

    def _dispatch_phase(self, event: WorldEvent, phase: str, game_time: int) -> None:
        for dispatcher in self._phase_dispatchers:
            dispatcher(event, phase, game_time)

    # -- TIME Scheduled Event 入口 -------------------------------------------------

    def on_occurrence(self, occurrence: dict) -> dict:
        """
        occurrence: {occurrence_key, kind, game_time, payload}
        kind ∈ event_activate / event_deadline；幂等：同 key 重放返回首次结果
        """
        key = occurrence["occurrence_key"]
        if key in self._occurrences:
            return {"status": "replayed", "result": self._occurrences[key]}
        kind = occurrence["kind"]
        game_time = occurrence["game_time"]
        payload = occurrence.get("payload", {})
        if kind not in ("event_activate", "event_deadline"):
            raise EventError("occurrence_kind_unknown", kind)
        event = self.get(payload["world_event_id"])
        result: dict
        if kind == "event_activate":
            if event.state != "scheduled":
                result = {"status": "skipped", "state": event.state}
            elif event.deadline is not None and game_time > event.deadline:
                self._do_transition(event, "expired", game_time,
                                    reason="deadline_passed", admin=False, cooldown_game_minutes=0)
                result = {"status": "expired"}
            else:
                self._do_transition(event, "active", game_time,
                                    reason="scheduled_due", admin=False,
                                    cooldown_game_minutes=payload.get("cooldown_game_minutes", 0))
                result = {"status": "activated"}
        else:  # event_deadline
            if event.state in ("candidate", "scheduled"):
                self._do_transition(event, "expired", game_time,
                                    reason="deadline_passed", admin=False, cooldown_game_minutes=0)
                result = {"status": "expired"}
            else:
                result = {"status": "skipped", "state": event.state}
        self._occurrences[key] = result
        return {"status": "processed", "result": result}

    # -- 导出/导入 ------------------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "events": {eid: e.to_dict() for eid, e in self._events.items()},
            "command_results": copy.deepcopy(self._command_results),
            "occurrences": copy.deepcopy(self._occurrences),
        }

    def import_state(self, data: dict) -> None:
        self._events = {eid: WorldEvent.from_dict(e) for eid, e in data["events"].items()}
        self._command_results = copy.deepcopy(data["command_results"])
        self._occurrences = copy.deepcopy(data["occurrences"])

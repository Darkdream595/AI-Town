"""
触发器评估与冲突裁决（DOC-EVENT-002）

- condition 受限谓词纯函数求值；字段缺失 = False + 警告
- 裁决排序 (severity 降, priority 降, trigger_id 字典序)
- 互斥：exclusion_tags 交集非空且 scope 相交 → 拒绝
- 抽样流 `event.trigger.<trigger_id 末段>`；(trigger_id, occurrence_key) 幂等
- 预算/冷却在实例化前预检；灾害冷却下限 4320 分钟
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .budget import NarrativePressureLedger
from .constants import SEVERITY_WEIGHT
from .engine import EventEngine, EventError
from .rng import EventRngHub
from .templates import TriggerRegistry, TriggerSpec


class TriggerError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def resolve_path(projection: dict, path: str):
    """dotted path 求值；任一段缺失返回 _MISSING 哨兵"""
    cursor = projection
    for segment in path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return _MISSING
        cursor = cursor[segment]
    return cursor


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover
        return "<missing>"


_MISSING = _Missing()


def evaluate_condition(condition: dict, projection: dict) -> Tuple[bool, List[str]]:
    """all_of 全部子句为真才为真；缺失字段 → 子句 False + 警告"""
    warnings: List[str] = []
    for clause in condition["all_of"]:
        predicate, path, expected = clause
        value = resolve_path(projection, path)
        if value is _MISSING:
            warnings.append(f"projection field missing: {path}")
            return False, warnings
        if predicate == "projection_equals":
            ok = value == expected
        elif predicate == "projection_at_least":
            ok = isinstance(value, (int, float)) and value >= expected
        elif predicate == "projection_at_most":
            ok = isinstance(value, (int, float)) and value <= expected
        elif predicate == "projection_in":
            ok = value in expected
        else:  # 注册期已拦截；求值期 fail closed
            raise TriggerError("condition_schema_invalid", predicate)
        if not ok:
            return False, warnings
    return True, warnings


def scopes_intersect(a: dict, b: dict) -> bool:
    """scope 相交：同 scene 且共有键取值不冲突"""
    if a.get("scene_id") != b.get("scene_id"):
        return False
    for key in ("region_id", "parcel_id"):
        if key in a and key in b and a[key] != b[key]:
            return False
    return True


class TriggerEngine:
    def __init__(
        self,
        triggers: TriggerRegistry,
        engine: EventEngine,
        budget: NarrativePressureLedger,
        rng_hub: EventRngHub,
        id_factory: Callable[[], str],
        event_log: object,
        whitelist_paths: Optional[frozenset] = None,
    ) -> None:
        self._triggers = triggers
        self._engine = engine
        self._budget = budget
        self._rng = rng_hub
        self._id_factory = id_factory
        self._log = event_log
        #: condition 允许引用的 projection 路径白名单；None = 不限制（测试装配时必须显式给）
        self._whitelist_paths = whitelist_paths
        self._evaluations: Dict[str, dict] = {}

    def validate_paths(self) -> None:
        """装配期校验：所有注册 trigger 的条件路径必须在白名单内"""
        if self._whitelist_paths is None:
            return
        for spec in self._triggers.all():
            for clause in spec.condition["all_of"]:
                if clause[1] not in self._whitelist_paths:
                    raise TriggerError(
                        "condition_schema_invalid",
                        f"{spec.trigger_id}: path {clause[1]} not whitelisted",
                    )

    def _template_tags(self, event_template_id: str) -> frozenset:
        tags: set = set()
        for spec in self._triggers.all():
            if spec.event_template_id == event_template_id:
                tags |= set(spec.exclusion_tags)
        return frozenset(tags)

    def _excluded_by_active(self, spec: TriggerSpec, scope: dict) -> bool:
        for event in self._engine.active_events():
            active_tags = self._template_tags(event.event_template_id)
            if spec.exclusion_tags & active_tags and scopes_intersect(scope, event.scope):
                return True
        return False

    def evaluate(self, occurrence: dict, projection: dict, source: str = "time") -> dict:
        """
        周期评估入口（TIME Scheduled Event，kind=trigger_eval）。
        occurrence: {occurrence_key, kind, game_time}
        """
        key = occurrence["occurrence_key"]
        if key in self._evaluations:
            return {"status": "replayed", "result": self._evaluations[key]}
        game_time = occurrence["game_time"]
        fired: List[dict] = []
        rejected: List[dict] = []
        warnings: List[str] = []

        # 1) 收集条件成立且来源许可的候选
        candidates: List[Tuple[int, int, str, TriggerSpec]] = []
        for spec in self._triggers.all():
            if source not in spec.allowed_sources:
                rejected.append({"trigger_id": spec.trigger_id, "code": "source_not_permitted"})
                continue
            ok, clause_warnings = evaluate_condition(spec.condition, projection)
            warnings.extend(f"{spec.trigger_id}: {w}" for w in clause_warnings)
            if not ok:
                continue
            rank = -SEVERITY_WEIGHT[spec.severity]
            candidates.append((rank, -spec.trigger_priority, spec.trigger_id, spec))

        # 2) 裁决排序：(severity 降, priority 降, trigger_id 字典序)
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))

        # 3) 按序预检预算/冷却/互斥后抽样触发
        chosen: List[TriggerSpec] = []
        for _rank, _prio, _tid, spec in candidates:
            scope = {"scene_id": projection.get("scene_id", "")}
            template = self._engine._templates.get(spec.event_template_id)
            if not self._budget.can_activate(spec.severity, game_time):
                rejected.append({"trigger_id": spec.trigger_id, "code": "budget_exceeded"})
                continue
            if self._budget.cooldown_remaining(
                spec.event_template_id, scope["scene_id"], game_time,
                spec.cooldown_game_minutes, template.is_disaster,
            ) > 0:
                rejected.append({"trigger_id": spec.trigger_id, "code": "cooldown_active"})
                continue
            if self._excluded_by_active(spec, scope):
                rejected.append({"trigger_id": spec.trigger_id, "code": "exclusion_conflict"})
                continue
            if any(
                spec.exclusion_tags & other.exclusion_tags
                for other in chosen
            ):
                rejected.append({"trigger_id": spec.trigger_id, "code": "exclusion_conflict"})
                continue
            draw = self._rng.trigger_stream(spec.trigger_id).draw_probability_millionths()
            if draw >= int(spec.activation_chance_0_to_1 * 1_000_000):
                rejected.append({"trigger_id": spec.trigger_id, "code": "chance_missed", "draw": draw})
                continue
            command_id = self._id_factory()
            try:
                event = self._engine.instantiate(
                    command_id=command_id,
                    event_template_id=spec.event_template_id,
                    source=source,
                    source_evidence_id=spec.trigger_id,
                    scope=scope,
                    parameters=dict(spec.parameters),
                    game_time=game_time,
                    severity=spec.severity,
                    occurrence_key=f"{key}:{spec.trigger_id}",
                )
                self._engine.transition(
                    event.world_event_id, "active", game_time,
                    expected_version=event.version,
                    reason=f"trigger:{spec.trigger_id}",
                    cooldown_game_minutes=spec.cooldown_game_minutes,
                )
            except EventError as exc:
                # 预期拒绝（语义窗口/并发上限等）不是失败：记录后继续后续候选
                rejected.append({"trigger_id": spec.trigger_id, "code": exc.code})
                continue
            chosen.append(spec)
            fired.append({"trigger_id": spec.trigger_id, "world_event_id": event.world_event_id})

        result = {"fired": fired, "rejected": rejected, "warnings": warnings}
        self._evaluations[key] = result
        self._log.append(
            "trigger.evaluated",
            {"occurrence_key": key, "fired": len(fired), "rejected": len(rejected)},
            game_time,
        )
        return {"status": "processed", "result": result}

    def export_state(self) -> dict:
        return {"evaluations": dict(self._evaluations)}

    def import_state(self, data: dict) -> None:
        self._evaluations = dict(data["evaluations"])

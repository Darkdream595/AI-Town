"""
模板注册表：EventTemplate / Trigger / QuestTemplate（DOC-EVENT-001/002/004）

- 注册表 fail closed：未知 ID 一律抛错，绝不默认放行
- Trigger condition 为受限谓词集，schema 在注册时校验
- Director 可见的模板必须显式列入 director 白名单（RULE-EVENT-015）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .constants import (
    AFTERMATH_TASK_KINDS,
    CONSEQUENCE_CAP,
    CONSEQUENCE_PHASES,
    CONSEQUENCE_TARGET_DOMAINS,
    EVENT_SOURCES,
    OBJECTIVE_KINDS,
    OBJECTIVE_ORDERINGS,
    SEVERITIES,
)


class TemplateError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------------------
# 后果计划（DOC-EVENT-005）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsequenceSpec:
    consequence_id: str
    phase: str  # CONSEQUENCE_PHASES
    target_domain: str  # CONSEQUENCE_TARGET_DOMAINS
    port: str  # 目标域端口方法名（封闭枚举由分发器校验）
    parameters: dict = field(default_factory=dict)
    #: 公开程度：public / scene / participants；认知分发不得注入 Secret
    publicity: str = "public"

    def __post_init__(self) -> None:
        if self.phase not in CONSEQUENCE_PHASES:
            raise TemplateError("consequence_phase_invalid", self.phase)
        if self.target_domain not in CONSEQUENCE_TARGET_DOMAINS:
            raise TemplateError("consequence_target_invalid", self.target_domain)
        if self.publicity not in ("public", "scene", "participants"):
            raise TemplateError("consequence_publicity_invalid", self.publicity)


@dataclass(frozen=True)
class AftermathTaskSpec:
    task_kind: str  # AFTERMATH_TASK_KINDS
    parameters: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.task_kind not in AFTERMATH_TASK_KINDS:
            raise TemplateError("aftermath_kind_invalid", self.task_kind)


# ---------------------------------------------------------------------------
# EventTemplate（DOC-EVENT-001）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventTemplate:
    event_template_id: str
    name: str
    default_severity: str
    allowed_sources: frozenset
    max_concurrent_instances: int
    dedup_window_game_minutes: int
    #: 允许的 parameters 键集合（严格校验，多余键拒绝）
    parameter_fields: frozenset = frozenset()
    required_parameters: frozenset = frozenset()
    consequence_plan: Tuple[ConsequenceSpec, ...] = ()
    aftermath_plan: Tuple[AftermathTaskSpec, ...] = ()
    is_disaster: bool = False
    #: 可携带的 scope 键（scene_id 必有；其余按模板声明）
    scope_fields: frozenset = frozenset({"scene_id"})

    def __post_init__(self) -> None:
        if self.default_severity not in SEVERITIES:
            raise TemplateError("severity_invalid", self.default_severity)
        unknown_sources = set(self.allowed_sources) - set(EVENT_SOURCES)
        if unknown_sources:
            raise TemplateError("source_invalid", str(sorted(unknown_sources)))
        if len(self.consequence_plan) > CONSEQUENCE_CAP:
            raise TemplateError("consequence_cap_exceeded", self.event_template_id)
        if self.max_concurrent_instances < 1:
            raise TemplateError("template_concurrency_invalid", self.event_template_id)
        if not self.required_parameters <= set(self.parameter_fields):
            raise TemplateError("template_parameters_invalid", "required ⊄ fields")

    def validate_parameters(self, parameters: dict) -> None:
        extra = set(parameters) - set(self.parameter_fields)
        if extra:
            raise TemplateError("parameters_invalid", f"extra: {sorted(extra)}")
        missing = set(self.required_parameters) - set(parameters)
        if missing:
            raise TemplateError("parameters_invalid", f"missing: {sorted(missing)}")

    def validate_scope(self, scope: dict) -> None:
        if "scene_id" not in scope:
            raise TemplateError("scope_invalid", "scene_id required")
        extra = set(scope) - set(self.scope_fields)
        if extra:
            raise TemplateError("scope_invalid", f"extra: {sorted(extra)}")


class EventTemplateRegistry:
    def __init__(self) -> None:
        self._templates: Dict[str, EventTemplate] = {}

    def register(self, template: EventTemplate) -> None:
        if template.event_template_id in self._templates:
            raise TemplateError("template_duplicate", template.event_template_id)
        self._templates[template.event_template_id] = template

    def get(self, event_template_id: str) -> EventTemplate:
        try:
            return self._templates[event_template_id]
        except KeyError:
            raise TemplateError("event_template_unknown", event_template_id) from None

    def has(self, event_template_id: str) -> bool:
        return event_template_id in self._templates

    def all(self) -> Tuple[EventTemplate, ...]:
        return tuple(self._templates.values())


# ---------------------------------------------------------------------------
# Trigger 注册项（DOC-EVENT-002）
# ---------------------------------------------------------------------------

#: 受限谓词集：只有这些子句允许出现在 condition 中
CONDITION_CLAUSES = frozenset(
    {"projection_equals", "projection_at_least", "projection_at_most", "projection_in"}
)


def validate_condition(condition: dict) -> None:
    """condition 为 {"all_of": [clause, ...]}；clause 为 [谓词, 路径, 期望值]"""
    if set(condition) != {"all_of"}:
        raise TemplateError("condition_schema_invalid", "only all_of supported")
    clauses = condition["all_of"]
    if not isinstance(clauses, list):
        raise TemplateError("condition_schema_invalid", "all_of must be a list")
    for clause in clauses:
        if not isinstance(clause, (list, tuple)) or len(clause) != 3:
            raise TemplateError("condition_schema_invalid", f"clause shape: {clause!r}")
        if clause[0] not in CONDITION_CLAUSES:
            raise TemplateError("condition_schema_invalid", clause[0])
        if not isinstance(clause[1], str) or not clause[1]:
            raise TemplateError("condition_schema_invalid", "path must be non-empty str")


@dataclass(frozen=True)
class TriggerSpec:
    trigger_id: str
    event_template_id: str
    allowed_sources: frozenset
    severity: str
    trigger_priority: int
    condition: dict
    activation_chance_0_to_1: float
    cooldown_game_minutes: int
    exclusion_tags: frozenset = frozenset()
    parameters: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise TemplateError("severity_invalid", self.severity)
        unknown_sources = set(self.allowed_sources) - set(EVENT_SOURCES)
        if unknown_sources:
            raise TemplateError("source_invalid", str(sorted(unknown_sources)))
        if not 0.0 <= self.activation_chance_0_to_1 <= 1.0:
            raise TemplateError("activation_chance_invalid", self.trigger_id)
        if self.cooldown_game_minutes < 0:
            raise TemplateError("cooldown_invalid", self.trigger_id)
        validate_condition(self.condition)


class TriggerRegistry:
    def __init__(self) -> None:
        self._triggers: Dict[str, TriggerSpec] = {}

    def register(self, spec: TriggerSpec) -> None:
        if spec.trigger_id in self._triggers:
            raise TemplateError("trigger_duplicate", spec.trigger_id)
        self._triggers[spec.trigger_id] = spec

    def get(self, trigger_id: str) -> TriggerSpec:
        try:
            return self._triggers[trigger_id]
        except KeyError:
            raise TemplateError("trigger_unknown", trigger_id) from None

    def all(self) -> Tuple[TriggerSpec, ...]:
        return tuple(self._triggers.values())


# ---------------------------------------------------------------------------
# QuestTemplate（DOC-EVENT-004）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    kind: str  # OBJECTIVE_KINDS
    params: dict = field(default_factory=dict)
    count_required: int = 1

    def __post_init__(self) -> None:
        if self.kind not in OBJECTIVE_KINDS:
            raise TemplateError("objective_schema_invalid", self.kind)
        if self.count_required < 1:
            raise TemplateError("objective_schema_invalid", "count_required < 1")


@dataclass(frozen=True)
class RewardSpec:
    reward_kind: str  # currency / item / deed_right ...
    parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class QuestTemplate:
    quest_template_id: str
    name: str
    objectives: Tuple[ObjectiveSpec, ...]
    objective_ordering: str = "parallel"
    deadline_game_minutes: Optional[int] = None
    #: offered 过期 → expired；accepted/active 到期按 failure_policy → failed/expired
    failure_policy: str = "failed"
    rewards: Tuple[RewardSpec, ...] = ()
    #: 参与者角色约束：{role: min_count}
    participant_roles: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.objective_ordering not in OBJECTIVE_ORDERINGS:
            raise TemplateError("objective_schema_invalid", self.objective_ordering)
        if self.failure_policy not in ("failed", "expired"):
            raise TemplateError("failure_policy_invalid", self.failure_policy)
        if not self.objectives:
            raise TemplateError("objective_schema_invalid", "empty objectives")
        seen = set()
        for objective in self.objectives:
            if objective.objective_id in seen:
                raise TemplateError("objective_schema_invalid", f"dup {objective.objective_id}")
            seen.add(objective.objective_id)
        if self.deadline_game_minutes is not None and self.deadline_game_minutes <= 0:
            raise TemplateError("deadline_invalid", self.quest_template_id)


class QuestTemplateRegistry:
    def __init__(self) -> None:
        self._templates: Dict[str, QuestTemplate] = {}

    def register(self, template: QuestTemplate) -> None:
        if template.quest_template_id in self._templates:
            raise TemplateError("quest_template_duplicate", template.quest_template_id)
        self._templates[template.quest_template_id] = template

    def get(self, quest_template_id: str) -> QuestTemplate:
        try:
            return self._templates[quest_template_id]
        except KeyError:
            raise TemplateError("quest_template_unknown", quest_template_id) from None

    def all(self) -> Tuple[QuestTemplate, ...]:
        return tuple(self._templates.values())


# ---------------------------------------------------------------------------
# Director 白名单（RULE-EVENT-015）
# ---------------------------------------------------------------------------


class DirectorWhitelist:
    """Director 可提议的模板集合；空集合 = 跳过评审、不调模型"""

    def __init__(self) -> None:
        self._allowed: set = set()

    def allow(self, event_template_id: str) -> None:
        self._allowed.add(event_template_id)

    def is_allowed(self, event_template_id: str) -> bool:
        return event_template_id in self._allowed

    def is_empty(self) -> bool:
        return not self._allowed

    def export(self) -> list:
        return sorted(self._allowed)

    def import_(self, data: list) -> None:
        self._allowed = set(data)

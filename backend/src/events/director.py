"""
AI Director（DOC-EVENT-003）

- WorldSummaryProjection 白名单输入：只允许 public.* 公开统计，禁私人记忆/Secret
- DirectorProposalV1 strict schema；修复最多一次
- 管线：Schema → 模板白名单/参数 → 预算/冷却/互斥/Scope → instantiate(source=director)
- Director 无特权：与任何来源走同一预算/冷却/互斥检查
- 每次评审至多 1 提案；每日 Director 来源上限 4；连续 3 次 terminal 失败 → 间隔延长到 1440
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from .budget import NarrativePressureLedger
from .constants import (
    DIRECTOR_DAILY_PROPOSAL_CAP,
    DIRECTOR_FAILURE_BACKOFF_INTERVAL,
    DIRECTOR_MAX_CONSECUTIVE_FAILURES,
    DIRECTOR_REVIEW_INTERVAL,
    GAME_DAY_MINUTES,
)
from .engine import EventEngine, EventError
from .templates import DirectorWhitelist, EventTemplateRegistry, TemplateError


class DirectorError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: DirectorProposalV1 字段（additionalProperties=false）
PROPOSAL_FIELDS = frozenset(
    {"proposal_kind", "event_template_id", "parameters", "narrative_reason"}
)
PROPOSAL_REQUIRED = frozenset(
    {"proposal_kind", "event_template_id", "parameters", "narrative_reason"}
)
_TEMPLATE_ID_RE = re.compile(r"^event\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

DIRECTOR_PROMPT_ID = "event-director/v1"
DIRECTOR_MODEL = "deepseek-v4-flash"
DIRECTOR_REASONING_EFFORT = "high"


def validate_proposal(data: object) -> List[str]:
    """返回错误列表；空列表 = 合法"""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["proposal not an object"]
    extra = set(data) - PROPOSAL_FIELDS
    if extra:
        errors.append(f"additionalProperties: {sorted(extra)}")
    missing = PROPOSAL_REQUIRED - set(data)
    if missing:
        errors.append(f"missing: {sorted(missing)}")
    if errors:
        return errors
    if data["proposal_kind"] != "world_event":
        errors.append("proposal_kind must be world_event")
    if not isinstance(data["event_template_id"], str) or not _TEMPLATE_ID_RE.match(
        data["event_template_id"]
    ):
        errors.append("event_template_id pattern mismatch")
    if not isinstance(data["parameters"], dict):
        errors.append("parameters must be object")
    if not isinstance(data["narrative_reason"], str) or not (
        1 <= len(data["narrative_reason"]) <= 500
    ):
        errors.append("narrative_reason must be 1..500 chars")
    return errors


def repair_proposal(data: object) -> object:
    """唯一允许的修复：剥离额外字段后重验（其余一律不修）"""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in PROPOSAL_FIELDS}
    return data


class WorldSummaryProjectionBuilder:
    """
    白名单投影：只允许注册 public.* 路径的提供者；
    白名单为空 = 跳过评审、不调模型
    """

    def __init__(self) -> None:
        self._providers: Dict[str, Callable[[], object]] = {}

    def register_field(self, path: str, provider: Callable[[], object]) -> None:
        if not path.startswith("public."):
            raise DirectorError(
                "projection_field_forbidden", f"{path}: only public.* statistics allowed"
            )
        self._providers[path] = provider

    def is_empty(self) -> bool:
        return not self._providers

    def build(self, game_time: int) -> dict:
        projection: dict = {"game_time": game_time}
        for path, provider in self._providers.items():
            cursor = projection
            segments = path.split(".")
            for segment in segments[:-1]:
                cursor = cursor.setdefault(segment, {})
            cursor[segments[-1]] = provider()
        return projection

    def export(self) -> list:
        return sorted(self._providers)


class DirectorReview:
    def __init__(
        self,
        engine: EventEngine,
        templates: EventTemplateRegistry,
        whitelist: DirectorWhitelist,
        budget: NarrativePressureLedger,
        model_port: object,
        event_log: object,
        id_factory: Callable[[], str],
    ) -> None:
        self._engine = engine
        self._templates = templates
        self._whitelist = whitelist
        self._budget = budget
        self._model = model_port
        self._log = event_log
        self._id_factory = id_factory
        self._last_review_time: Optional[int] = None
        self._interval = DIRECTOR_REVIEW_INTERVAL
        self._consecutive_failures = 0
        self._daily_counts: Dict[int, int] = {}
        self._reviews: Dict[str, dict] = {}

    def _record_failure(self, game_time: int, code: str) -> dict:
        self._consecutive_failures += 1
        if self._consecutive_failures >= DIRECTOR_MAX_CONSECUTIVE_FAILURES:
            self._interval = DIRECTOR_FAILURE_BACKOFF_INTERVAL
        self._last_review_time = game_time
        self._log.append(
            "director.review_failed",
            {"code": code, "consecutive_failures": self._consecutive_failures},
            game_time,
        )
        return {"status": "failed", "code": code}

    def _record_success(self, game_time: int) -> None:
        self._consecutive_failures = 0
        self._interval = DIRECTOR_REVIEW_INTERVAL
        self._last_review_time = game_time

    def run_review(self, occurrence: dict, projection: dict) -> dict:
        """
        评审入口（TIME phase 4，kind=director_review）。
        occurrence: {occurrence_key, kind, game_time}
        """
        key = occurrence["occurrence_key"]
        if key in self._reviews:
            return {"status": "replayed", "result": self._reviews[key]}
        game_time = occurrence["game_time"]

        if self._whitelist.is_empty():
            result = {"status": "skipped", "reason": "whitelist_empty"}
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        if (
            self._last_review_time is not None
            and game_time - self._last_review_time < self._interval
        ):
            result = {"status": "skipped", "reason": "interval_not_due"}
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        projection_time = projection.get("game_time")
        if projection_time is None or game_time - projection_time > DIRECTOR_REVIEW_INTERVAL:
            result = self._record_failure(game_time, "projection_stale")
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        game_day = game_time // GAME_DAY_MINUTES
        if self._daily_counts.get(game_day, 0) >= DIRECTOR_DAILY_PROPOSAL_CAP:
            result = {"status": "skipped", "reason": "daily_cap_reached"}
            self._reviews[key] = result
            return {"status": "processed", "result": result}

        # 模型调用：prompt event-director/v1，deepseek-v4-flash，Thinking on，effort high
        try:
            raw = self._model.complete(
                prompt_id=DIRECTOR_PROMPT_ID,
                model=DIRECTOR_MODEL,
                thinking=True,
                reasoning_effort=DIRECTOR_REASONING_EFFORT,
                projection=projection,
            )
        except Exception:
            result = self._record_failure(game_time, "model_unavailable")
            self._reviews[key] = result
            return {"status": "processed", "result": result}

        if raw is None:
            self._record_success(game_time)
            result = {"status": "no_proposal"}
            self._reviews[key] = result
            self._log.append("director.review_no_proposal", {}, game_time)
            return {"status": "processed", "result": result}

        # Schema 校验，修复最多一次
        errors = validate_proposal(raw)
        if errors:
            repaired = repair_proposal(raw)
            errors = validate_proposal(repaired)
            if errors:
                result = self._record_failure(game_time, "proposal_schema_invalid")
                self._reviews[key] = result
                return {"status": "processed", "result": result}
            raw = repaired

        template_id = raw["event_template_id"]
        if not self._whitelist.is_allowed(template_id):
            result = self._record_failure(game_time, "template_not_whitelisted")
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        try:
            template = self._templates.get(template_id)
        except TemplateError:
            result = self._record_failure(game_time, "template_not_whitelisted")
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        parameters = raw["parameters"]
        try:
            template.validate_parameters(parameters)
        except TemplateError:
            result = self._record_failure(game_time, "template_parameters_invalid")
            self._reviews[key] = result
            return {"status": "processed", "result": result}
        scope = parameters.pop("scope", None) or {"scene_id": projection.get("scene_id", "")}
        try:
            template.validate_scope(scope)
        except TemplateError as exc:
            result = self._record_failure(game_time, exc.code)
            self._reviews[key] = result
            return {"status": "processed", "result": result}

        # Director 无特权：预算/冷却/互斥/Scope 与任何来源同权
        try:
            event = self._engine.instantiate(
                command_id=self._id_factory(),
                event_template_id=template_id,
                source="director",
                source_evidence_id=key,
                scope=scope,
                parameters=parameters,
                game_time=game_time,
                occurrence_key=f"{key}:director",
            )
            self._engine.transition(
                event.world_event_id, "active", game_time,
                expected_version=event.version, reason="director_proposal",
            )
        except EventError as exc:
            result = self._record_failure(game_time, exc.code)
            self._reviews[key] = result
            return {"status": "processed", "result": result}

        self._daily_counts[game_day] = self._daily_counts.get(game_day, 0) + 1
        self._record_success(game_time)
        self._log.append(
            "director.proposal_accepted",
            {
                "world_event_id": event.world_event_id,
                "event_template_id": template_id,
                "narrative_reason": raw["narrative_reason"],
            },
            game_time,
        )
        result = {"status": "accepted", "world_event_id": event.world_event_id}
        self._reviews[key] = result
        return {"status": "processed", "result": result}

    def export_state(self) -> dict:
        return {
            "last_review_time": self._last_review_time,
            "interval": self._interval,
            "consecutive_failures": self._consecutive_failures,
            "daily_counts": dict(self._daily_counts),
            "reviews": dict(self._reviews),
        }

    def import_state(self, data: dict) -> None:
        self._last_review_time = data["last_review_time"]
        self._interval = data["interval"]
        self._consecutive_failures = data["consecutive_failures"]
        self._daily_counts = dict(data["daily_counts"])
        self._reviews = dict(data["reviews"])

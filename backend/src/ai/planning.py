"""
Daily Plan、Hourly Intent 与三层计划状态机

符合 DOC-AI-006：
- RULE-AI-032：artifact 携带 observed Revision、expiry、dependency fingerprint 和 version
- RULE-AI-033：安全/critical Need/健康限制/Encounter/目标不可用/deadline miss/关键依赖变化 → stale/abort
- RULE-AI-034：stale plan 先记录 stale_reason_code 再 replan，不改写旧计划
- RULE-AI-035：成功只由 committed event 满足 registered condition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlanStatus(str, Enum):
    """计划状态（DOC-AI-006 §4）

    proposed -> active -> satisfied | abandoned | expired | superseded
    active -> stale -> superseded | abandoned
    """

    PROPOSED = "proposed"
    ACTIVE = "active"
    SATISFIED = "satisfied"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    STALE = "stale"


#: 合法状态边（TEST-AI-021）
PLAN_STATE_EDGES: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.PROPOSED: frozenset({PlanStatus.ACTIVE, PlanStatus.ABANDONED}),
    PlanStatus.ACTIVE: frozenset(
        {
            PlanStatus.SATISFIED,
            PlanStatus.ABANDONED,
            PlanStatus.EXPIRED,
            PlanStatus.SUPERSEDED,
            PlanStatus.STALE,
        }
    ),
    PlanStatus.STALE: frozenset({PlanStatus.SUPERSEDED, PlanStatus.ABANDONED}),
    PlanStatus.SATISFIED: frozenset(),
    PlanStatus.ABANDONED: frozenset(),
    PlanStatus.EXPIRED: frozenset(),
    PlanStatus.SUPERSEDED: frozenset(),
}

#: 每 Resident 上限（DOC-AI-006 §9）
MAX_ACTIVE_DAILY_PLANS = 1
MAX_ACTIVE_HOURLY_INTENTS = 1
MAX_DAILY_GOALS = 8
MAX_CANDIDATE_ACTIONS = 6
MAX_ABORT_CONDITIONS = 8


class PlanTransitionError(Exception):
    """非法状态边"""


@dataclass
class DailyGoal:
    """Daily Plan 单目标（DES-AI-006）"""

    goal_id: str
    priority: int  # 0..100
    success_condition_id: str
    abandon_condition_ids: list[str]
    target_game_time: Optional[int]


@dataclass
class DailyPlan:
    """Daily Plan artifact（schema.ai.daily_plan.v1）"""

    schema_version: int
    plan_id: str
    resident_id: str
    observed_revision: int
    game_day_index: int
    goals: list[DailyGoal]
    risk_response_ids: list[str]
    dependency_fingerprint: str
    expires_at_game_time: int
    status: PlanStatus = PlanStatus.PROPOSED
    stale_reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.goals) > MAX_DAILY_GOALS:
            raise ValueError(f"Daily goals 超限: {len(self.goals)} > {MAX_DAILY_GOALS}")

    def transition_to(self, new_status: PlanStatus, reason_code: Optional[str] = None) -> None:
        """状态迁移，非法边拒绝（幂等：同状态重复迁移为 no-op）"""
        if new_status == self.status:
            return
        if new_status not in PLAN_STATE_EDGES[self.status]:
            raise PlanTransitionError(f"非法计划状态迁移: {self.status.value} -> {new_status.value}")
        if new_status == PlanStatus.STALE:
            # RULE-AI-034：先记录 stale_reason_code
            self.stale_reason_code = reason_code
        self.status = new_status

    def check_expiry(self, current_game_time: int) -> bool:
        """到期检查；到期即从 active 转 expired"""
        if self.status == PlanStatus.ACTIVE and current_game_time >= self.expires_at_game_time:
            self.transition_to(PlanStatus.EXPIRED)
            return True
        return False

    def mark_stale_if_dependency_changed(self, current_fingerprint: str, reason_code: str) -> bool:
        """关键 dependency version 变化 → stale（RULE-AI-033）"""
        if self.status != PlanStatus.ACTIVE:
            return False
        if current_fingerprint != self.dependency_fingerprint:
            self.transition_to(PlanStatus.STALE, reason_code=reason_code)
            return True
        return False

    def satisfy_goal_by_committed_condition(self, condition_id: str) -> list[str]:
        """
        由 committed event 满足 registered condition（RULE-AI-035）

        返回被满足的 goal_id 列表；全部满足后计划转 satisfied。
        """
        satisfied_goal_ids = [g.goal_id for g in self.goals if g.success_condition_id == condition_id]
        if satisfied_goal_ids and self.status == PlanStatus.ACTIVE:
            remaining = [g for g in self.goals if g.goal_id not in satisfied_goal_ids]
            if not remaining:
                self.transition_to(PlanStatus.SATISFIED)
        return satisfied_goal_ids


@dataclass
class HourlyIntent:
    """Hourly Intent artifact（schema.ai.hourly_intent.v1）"""

    schema_version: int
    intent_id: str
    parent_plan_id: str
    goal_id: str
    observed_revision: int
    candidate_action_ids: list[str]
    expected_start_game_time: int
    expires_at_game_time: int
    abort_condition_ids: list[str]
    dependency_fingerprint: str
    status: PlanStatus = PlanStatus.PROPOSED
    stale_reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if len(self.candidate_action_ids) > MAX_CANDIDATE_ACTIONS:
            raise ValueError(
                f"candidate actions 超限: {len(self.candidate_action_ids)} > {MAX_CANDIDATE_ACTIONS}"
            )
        if len(self.abort_condition_ids) > MAX_ABORT_CONDITIONS:
            raise ValueError(
                f"abort conditions 超限: {len(self.abort_condition_ids)} > {MAX_ABORT_CONDITIONS}"
            )

    def transition_to(self, new_status: PlanStatus, reason_code: Optional[str] = None) -> None:
        if new_status == self.status:
            return
        if new_status not in PLAN_STATE_EDGES[self.status]:
            raise PlanTransitionError(f"非法意图状态迁移: {self.status.value} -> {new_status.value}")
        if new_status == PlanStatus.STALE:
            self.stale_reason_code = reason_code
        self.status = new_status

    def check_expiry(self, current_game_time: int) -> bool:
        if self.status == PlanStatus.ACTIVE and current_game_time >= self.expires_at_game_time:
            self.transition_to(PlanStatus.EXPIRED)
            return True
        return False

    def check_abort_conditions(self, active_condition_ids: set[str]) -> Optional[str]:
        """abort condition 触发检查；返回触发的 condition ID"""
        if self.status != PlanStatus.ACTIVE:
            return None
        for condition_id in self.abort_condition_ids:
            if condition_id in active_condition_ids:
                self.transition_to(PlanStatus.ABANDONED, reason_code=condition_id)
                return condition_id
        return None


@dataclass
class PlanLedger:
    """每 Resident 计划台账：active Daily 1、Hourly 1（DOC-AI-006 §9）"""

    resident_id: str
    daily_plans: list[DailyPlan] = field(default_factory=list)
    hourly_intents: list[HourlyIntent] = field(default_factory=list)

    def activate_daily_plan(self, plan: DailyPlan) -> None:
        """激活新 Daily Plan；旧 active 计划转 superseded"""
        for existing in self.daily_plans:
            if existing.status == PlanStatus.ACTIVE:
                existing.transition_to(PlanStatus.SUPERSEDED, reason_code="new_daily_plan")
        plan.transition_to(PlanStatus.ACTIVE)
        self.daily_plans.append(plan)

    def activate_hourly_intent(self, intent: HourlyIntent) -> None:
        for existing in self.hourly_intents:
            if existing.status == PlanStatus.ACTIVE:
                existing.transition_to(PlanStatus.SUPERSEDED, reason_code="new_hourly_intent")
        intent.transition_to(PlanStatus.ACTIVE)
        self.hourly_intents.append(intent)

    def active_daily_plan(self) -> Optional[DailyPlan]:
        return next((p for p in self.daily_plans if p.status == PlanStatus.ACTIVE), None)

    def active_hourly_intent(self) -> Optional[HourlyIntent]:
        return next((i for i in self.hourly_intents if i.status == PlanStatus.ACTIVE), None)

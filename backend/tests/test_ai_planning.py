"""
测试三层计划（Daily Plan / Hourly Intent）

覆盖 TEST-AI-021/022/023/024（DOC-AI-006 §11）
"""

import pytest

from src.ai import (
    DailyGoal,
    DailyPlan,
    HourlyIntent,
    PlanLedger,
    PlanStatus,
    PlanTransitionError,
)

from ai_helpers import ULID_A, ULID_B


def _daily_plan(**overrides) -> DailyPlan:
    defaults = dict(
        schema_version=1,
        plan_id="01K1AB2CD3EF4GH5JK6MNP7QRS",
        resident_id=ULID_A,
        observed_revision=84,
        game_day_index=2,
        goals=[
            DailyGoal(
                goal_id="goal.daily.obtain_medicine",
                priority=80,
                success_condition_id="inventory.has_healing_item",
                abandon_condition_ids=["danger_detected"],
                target_game_time=2100,
            )
        ],
        risk_response_ids=["response.seek_safety"],
        dependency_fingerprint="sha256:93ff3d7c",
        expires_at_game_time=2880,
    )
    defaults.update(overrides)
    return DailyPlan(**defaults)


def _hourly_intent(**overrides) -> HourlyIntent:
    defaults = dict(
        schema_version=1,
        intent_id="01K1AB2CD3EF4GH5JK6MNP7QRV",
        parent_plan_id="01K1AB2CD3EF4GH5JK6MNP7QRS",
        goal_id="goal.daily.obtain_medicine",
        observed_revision=84,
        candidate_action_ids=["move_to", "buy"],
        expected_start_game_time=1830,
        expires_at_game_time=1950,
        abort_condition_ids=["shop_closed", "insufficient_funds", "danger_detected"],
        dependency_fingerprint="sha256:7ea5018d",
    )
    defaults.update(overrides)
    return HourlyIntent(**defaults)


class TestPlanStateMachine:
    """TEST-AI-021：schema、state 与 expiry"""

    def test_daily_plan_lifecycle(self):
        plan = _daily_plan()
        assert plan.status == PlanStatus.PROPOSED
        plan.transition_to(PlanStatus.ACTIVE)
        assert plan.status == PlanStatus.ACTIVE

    def test_illegal_transition_rejected(self):
        plan = _daily_plan()
        with pytest.raises(PlanTransitionError):
            plan.transition_to(PlanStatus.SATISFIED)  # proposed 不能直接 satisfied

    def test_terminal_state_no_exit(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        plan.transition_to(PlanStatus.SATISFIED)
        with pytest.raises(PlanTransitionError):
            plan.transition_to(PlanStatus.ACTIVE)

    def test_expiry_transition(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        assert not plan.check_expiry(current_game_time=2879)
        assert plan.check_expiry(current_game_time=2880)
        assert plan.status == PlanStatus.EXPIRED

    def test_stale_then_superseded(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        plan.transition_to(PlanStatus.STALE, reason_code="dependency_changed")
        assert plan.stale_reason_code == "dependency_changed"
        plan.transition_to(PlanStatus.SUPERSEDED)

    def test_idempotent_activation(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        plan.transition_to(PlanStatus.ACTIVE)  # 同状态迁移为 no-op
        assert plan.status == PlanStatus.ACTIVE

    def test_daily_goals_limit(self):
        goals = [
            DailyGoal(
                goal_id=f"goal.{index}",
                priority=50,
                success_condition_id=f"cond.{index}",
                abandon_condition_ids=[],
                target_game_time=None,
            )
            for index in range(9)
        ]
        with pytest.raises(ValueError):
            _daily_plan(goals=goals)


class TestStaleAbortMatrix:
    """TEST-AI-022：dependency stale/abort matrix"""

    def test_dependency_fingerprint_change_marks_stale(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        assert plan.mark_stale_if_dependency_changed("sha256:changed", "navigation_revision_changed")
        assert plan.status == PlanStatus.STALE
        assert plan.stale_reason_code == "navigation_revision_changed"

    def test_same_fingerprint_not_stale(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        assert not plan.mark_stale_if_dependency_changed("sha256:93ff3d7c", "x")
        assert plan.status == PlanStatus.ACTIVE

    def test_hourly_intent_abort_condition(self):
        intent = _hourly_intent(status=PlanStatus.ACTIVE)
        triggered = intent.check_abort_conditions({"shop_closed"})
        assert triggered == "shop_closed"
        assert intent.status == PlanStatus.ABANDONED

    def test_hourly_intent_expiry(self):
        intent = _hourly_intent(status=PlanStatus.ACTIVE)
        assert intent.check_expiry(current_game_time=1950)
        assert intent.status == PlanStatus.EXPIRED


class TestCommittedConditionSatisfies:
    """TEST-AI-023：committed condition 才满足 goal（RULE-AI-035）"""

    def test_goal_satisfied_by_committed_condition(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        satisfied = plan.satisfy_goal_by_committed_condition("inventory.has_healing_item")
        assert satisfied == ["goal.daily.obtain_medicine"]
        assert plan.status == PlanStatus.SATISFIED

    def test_unrelated_condition_does_not_satisfy(self):
        plan = _daily_plan(status=PlanStatus.ACTIVE)
        satisfied = plan.satisfy_goal_by_committed_condition("some.other_condition")
        assert satisfied == []
        assert plan.status == PlanStatus.ACTIVE


class TestPlanLedgerBounds:
    """TEST-AI-024：replan-loop/上限约束"""

    def test_active_daily_plan_superseded_by_new(self):
        ledger = PlanLedger(resident_id=ULID_A)
        plan1 = _daily_plan(plan_id=ULID_A)
        plan2 = _daily_plan(plan_id=ULID_B)
        ledger.activate_daily_plan(plan1)
        ledger.activate_daily_plan(plan2)
        assert plan1.status == PlanStatus.SUPERSEDED
        assert plan2.status == PlanStatus.ACTIVE
        assert ledger.active_daily_plan() is plan2

    def test_active_hourly_intent_superseded_by_new(self):
        ledger = PlanLedger(resident_id=ULID_A)
        intent1 = _hourly_intent(intent_id=ULID_A)
        intent2 = _hourly_intent(intent_id=ULID_B)
        ledger.activate_hourly_intent(intent1)
        ledger.activate_hourly_intent(intent2)
        assert intent1.status == PlanStatus.SUPERSEDED
        assert ledger.active_hourly_intent() is intent2

    def test_candidate_actions_limit(self):
        with pytest.raises(ValueError):
            _hourly_intent(candidate_action_ids=["a", "b", "c", "d", "e", "f", "g"])

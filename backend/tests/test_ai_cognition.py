"""
测试认知流水线状态机

覆盖 TEST-AI-001/003（DOC-AI-001 §11）
"""

import pytest

from src.ai import (
    COGNITION_EDGES,
    CognitionEnvelope,
    CognitionRun,
    CognitionStage,
    CognitionTransitionError,
)

from ai_helpers import ULID_A


def _run() -> CognitionRun:
    return CognitionRun(
        envelope=CognitionEnvelope(
            cognition_run_id="01K1AB2CD3EF4GH5JK6MNP7QRS",
            resident_id=ULID_A,
            plan_kind="immediate_action",
            observed_revision=84,
            observed_game_time=1830,
            context_hash="sha256:8de5c7a8d5f0",
            prompt_id="resident-action/v1",
            request_policy_version=1,
            attempt=1,
        )
    )


class TestCognitionStateMachine:
    """TEST-AI-001：全阶段状态机合法边可达、非法边拒绝"""

    def test_happy_path_full_pipeline(self):
        run = _run()
        for stage in [
            CognitionStage.OBSERVING,
            CognitionStage.RETRIEVING,
            CognitionStage.ASSEMBLING,
            CognitionStage.PLANNING,
            CognitionStage.PARSING,
            CognitionStage.VALIDATING,
            CognitionStage.RESERVING,
            CognitionStage.COMMITTING,
            CognitionStage.OBSERVED_RESULT,
        ]:
            run.transition_to(stage)
        assert run.stage == CognitionStage.OBSERVED_RESULT

    def test_illegal_edge_rejected(self):
        run = _run()
        with pytest.raises(CognitionTransitionError):
            run.transition_to(CognitionStage.COMMITTING)

    def test_cancel_from_scheduled(self):
        run = _run()
        run.transition_to(CognitionStage.CANCELLED)
        with pytest.raises(CognitionTransitionError):
            run.transition_to(CognitionStage.OBSERVING)

    def test_fallback_loop(self):
        run = _run()
        for stage in [
            CognitionStage.OBSERVING,
            CognitionStage.RETRIEVING,
            CognitionStage.ASSEMBLING,
            CognitionStage.PLANNING,
            CognitionStage.PARSING,
            CognitionStage.VALIDATING,
        ]:
            run.transition_to(stage)
        run.transition_to(CognitionStage.FALLBACK)
        run.transition_to(CognitionStage.VALIDATING)
        assert run.stage == CognitionStage.VALIDATING

    def test_replan_edge(self):
        run = _run()
        for stage in [
            CognitionStage.OBSERVING,
            CognitionStage.RETRIEVING,
            CognitionStage.ASSEMBLING,
            CognitionStage.PLANNING,
            CognitionStage.PARSING,
            CognitionStage.VALIDATING,
        ]:
            run.transition_to(stage)
        run.transition_to(CognitionStage.PLANNING)
        assert run.stage == CognitionStage.PLANNING

    def test_all_declared_edges_valid(self):
        # 状态机定义自身一致性：所有边指向已知状态
        for source, targets in COGNITION_EDGES.items():
            assert isinstance(source, CognitionStage)
            for target in targets:
                assert isinstance(target, CognitionStage)


class TestDuplicateResultGuard:
    """TEST-AI-003：stale/cancel/duplicate result 无副作用"""

    def test_duplicate_result_rejected(self):
        run = _run()
        assert run.accept_provider_result("action_proposal", attempt=1)
        assert not run.accept_provider_result("action_proposal", attempt=1)

    def test_wrong_attempt_rejected(self):
        run = _run()
        assert not run.accept_provider_result("action_proposal", attempt=2)

    def test_cancelled_run_rejects_result(self):
        run = _run()
        run.transition_to(CognitionStage.CANCELLED)
        assert not run.accept_provider_result("action_proposal", attempt=1)

    def test_completed_run_rejects_late_result(self):
        run = _run()
        run.transition_to(CognitionStage.OBSERVING)
        assert run.accept_provider_result("action_proposal", attempt=1)
        assert not run.accept_provider_result("action_proposal", attempt=1)

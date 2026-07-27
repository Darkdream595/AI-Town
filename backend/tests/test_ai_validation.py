"""
测试 Action 校验、修复与重规划

覆盖 TEST-AI-037/038/039/040（DOC-AI-010 §11）
"""

import json

import pytest

from src.ai import (
    ReplanLoopBreaker,
    RepairNotPossibleError,
    ValidationOutcomeKind,
    ValidationPipeline,
    ValidationStage,
    attempt_bounded_repair,
    decode_proposal,
    verify_intent_preserved,
)

from ai_helpers import ULID_A, make_proposal_bytes, make_valid_proposal


def _pipeline(**kwargs) -> ValidationPipeline:
    return ValidationPipeline(**kwargs)


class TestStageOrderingAndOutcomeMatrix:
    """TEST-AI-037：stage ordering/outcome matrix"""

    def test_valid_proposal_passes(self):
        outcome = _pipeline().validate(
            outcome_id="o1",
            proposal_id="p1",
            raw_bytes=make_proposal_bytes("wait"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.VALID
        assert outcome.stage == ValidationStage.DOMAIN_LATEST_STATE

    def test_schema_error_stage(self):
        payload = make_valid_proposal("wait")
        del payload["goal"]
        outcome = _pipeline().validate(
            outcome_id="o2",
            proposal_id="p2",
            raw_bytes=json.dumps(payload).encode("utf-8"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.REPLAN_REQUIRED
        assert outcome.stage == ValidationStage.STRICT_SCHEMA
        assert outcome.repair_patch is None  # 无白名单可修复项时不伪造 repair

    def test_cross_field_stage(self):
        payload = make_valid_proposal("talk")
        payload["target_entity_id"] = None
        outcome = _pipeline().validate(
            outcome_id="o3",
            proposal_id="p3",
            raw_bytes=json.dumps(payload).encode("utf-8"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.REPLAN_REQUIRED
        assert outcome.stage == ValidationStage.CROSS_FIELD_SEMANTIC
        assert "target_required" in outcome.reason_codes

    def test_domain_validator_replan(self):
        outcome = _pipeline(
            domain_validators={"wait": lambda proposal: "deadline_missed"}
        ).validate(
            outcome_id="o4",
            proposal_id="p4",
            raw_bytes=make_proposal_bytes("wait"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=87,
        )
        assert outcome.outcome == ValidationOutcomeKind.REPLAN_REQUIRED
        assert outcome.stage == ValidationStage.DOMAIN_LATEST_STATE
        assert outcome.reason_codes == ("deadline_missed",)


class TestRepairWhitelist:
    """TEST-AI-038：repair whitelist/intention immutability"""

    def test_strip_code_fence(self):
        inner = json.dumps(make_valid_proposal("wait"))
        fenced = f"```json\n{inner}\n```".encode("utf-8")
        result = attempt_bounded_repair(fenced)
        assert "strip_code_fence" in result.applied_operations
        decoded = decode_proposal(result.repaired_bytes)
        assert decoded.action == "wait"

    def test_empty_spoken_text_normalized(self):
        payload = make_valid_proposal("talk")
        payload["spoken_text"] = ""
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        result = attempt_bounded_repair(raw)
        assert "normalize_empty_spoken_text" in result.applied_operations
        decoded = decode_proposal(result.repaired_bytes)
        assert decoded.spoken_text is None

    def test_unrepairable_rejected(self):
        with pytest.raises(RepairNotPossibleError):
            attempt_bounded_repair(b"totally broken {{{")

    def test_no_repair_when_nothing_to_fix(self):
        with pytest.raises(RepairNotPossibleError):
            attempt_bounded_repair(make_proposal_bytes("wait"))

    def test_intent_preserved_check(self):
        before = decode_proposal(make_proposal_bytes("wait"))
        after_same = decode_proposal(make_proposal_bytes("wait"))
        assert verify_intent_preserved(before, after_same)

        changed = make_valid_proposal("wait")
        changed["parameters"]["duration_game_minutes"] = 99
        after_changed = decode_proposal(json.dumps(changed).encode("utf-8"))
        assert not verify_intent_preserved(before, after_changed)

    def test_pipeline_repairable_outcome(self):
        inner = json.dumps(make_valid_proposal("wait"))
        fenced = f"```json\n{inner}\n```".encode("utf-8")
        outcome = _pipeline().validate(
            outcome_id="o5",
            proposal_id="p5",
            raw_bytes=fenced,
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.REPAIRABLE
        assert outcome.allowed_retry is True


class TestForbiddenOutcome:
    """TEST-AI-039：forbidden/no-secret/no-auto-downgrade"""

    def test_forbidden_capability(self):
        outcome = _pipeline(
            capability_checker=lambda actor, action: "permission_denied"
        ).validate(
            outcome_id="o6",
            proposal_id="p6",
            raw_bytes=make_proposal_bytes("wait"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.FORBIDDEN
        assert outcome.audit_severity == "security"
        # 不回显隐藏事实：reason 只有 code
        assert outcome.reason_codes == ("permission_denied",)

    def test_forbidden_not_downgraded(self):
        # 禁止将 forbidden action 自动降格成另一有副作用 action
        outcome = _pipeline(
            capability_checker=lambda actor, action: "admin_only" if action == "build" else None
        ).validate(
            outcome_id="o7",
            proposal_id="p7",
            raw_bytes=make_proposal_bytes("build"),
            actor_id=ULID_A,
            observed_revision=84,
            latest_revision=84,
        )
        assert outcome.outcome == ValidationOutcomeKind.FORBIDDEN
        assert outcome.allowed_retry is False


class TestReplanLoopBreaker:
    """TEST-AI-040 相关：loop breaker（DOC-AI-010 §8）"""

    def test_three_same_reason_replans_trigger_breaker(self):
        breaker = ReplanLoopBreaker()
        assert not breaker.record_replan("shop_closed", game_time=100)
        assert not breaker.record_replan("shop_closed", game_time=105)
        assert breaker.record_replan("shop_closed", game_time=108)

    def test_different_reasons_no_breaker(self):
        breaker = ReplanLoopBreaker()
        assert not breaker.record_replan("shop_closed", 100)
        assert not breaker.record_replan("quote_changed", 105)
        assert not breaker.record_replan("target_unavailable", 108)

    def test_window_expiry_resets(self):
        breaker = ReplanLoopBreaker()
        breaker.record_replan("shop_closed", game_time=100)
        breaker.record_replan("shop_closed", game_time=105)
        # 超出 10 游戏分钟窗口
        assert not breaker.record_replan("shop_closed", game_time=120)

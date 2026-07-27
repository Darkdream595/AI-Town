"""
TEST-PLAYER-005..008：玩家移动、预测与权威校准（DOC-PLAYER-002）

- TEST-PLAYER-005：WASD/Shift、对角归一化和速率限制
- TEST-PLAYER-006：PlayerCommand/NPC ActionProposal MAP parity
- TEST-PLAYER-007：collision、动态 Door 与 Scene transition
- TEST-PLAYER-008：prediction、乱序、Snapshot 与 stuck-key recovery
"""

import math

import pytest

from src.player.movement import (
    InputLatch,
    MoveIntentValidator,
    MovementValidationError,
    ReconciliationState,
    ReconciliationStateMachine,
    ReconciliationTrigger,
    SpeedMode,
)

BINDING = "01K1BNDG000000000000000001"


def _raw(**overrides):
    base = {
        "schema_version": 1,
        "command_id": "cmd-move-1",
        "expected_revision": 44,
        "input_sequence": 731,
        "sample_duration_ms": 50,
        "direction": {"x": 1, "y": 0},
        "speed_mode": "walk",
        "client_observed_scene_id": "scene.crowncreek.town",
    }
    base.update(overrides)
    return base


class TestIntentShapeAndRate:
    """TEST-PLAYER-005"""

    def test_valid_intent_accepted(self):
        intent = MoveIntentValidator().validate_shape(_raw())
        assert intent.speed_mode is SpeedMode.WALK
        assert intent.normalized_direction() == (1.0, 0.0)

    def test_diagonal_is_normalized_no_extra_speed(self):
        intent = MoveIntentValidator().validate_shape(
            _raw(direction={"x": 1, "y": 1})
        )
        nx, ny = intent.normalized_direction()
        # §5：对角线归一化，合速度长度恒为 1
        assert math.isclose(math.hypot(nx, ny), 1.0)
        assert math.isclose(nx, math.sqrt(0.5))

    def test_zero_direction_rejected(self):
        with pytest.raises(MovementValidationError) as exc:
            MoveIntentValidator().validate_shape(_raw(direction={"x": 0, "y": 0}))
        assert exc.value.code == "PLAYER_INTENT_DIRECTION_ZERO"

    @pytest.mark.parametrize("bad", [2, -2, 0.5, float("nan"), float("inf"), True, "1"])
    def test_illegal_direction_components_rejected(self, bad):
        with pytest.raises(MovementValidationError) as exc:
            MoveIntentValidator().validate_shape(_raw(direction={"x": bad, "y": 0}))
        assert exc.value.code == "PLAYER_INTENT_DIRECTION_INVALID"

    @pytest.mark.parametrize("duration", [0, 101, -5, 50.5, "50"])
    def test_sample_duration_bounds(self, duration):
        with pytest.raises(MovementValidationError):
            MoveIntentValidator().validate_shape(_raw(sample_duration_ms=duration))

    def test_fast_walk_mode(self):
        intent = MoveIntentValidator().validate_shape(_raw(speed_mode="fast_walk"))
        assert intent.speed_mode is SpeedMode.FAST_WALK

    def test_unknown_speed_mode_rejected(self):
        with pytest.raises(MovementValidationError) as exc:
            MoveIntentValidator().validate_shape(_raw(speed_mode="sprint"))
        assert exc.value.code == "PLAYER_INTENT_SPEED_MODE_INVALID"

    def test_unknown_field_rejected(self):
        with pytest.raises(MovementValidationError) as exc:
            MoveIntentValidator().validate_shape(_raw(teleport_to={"x": 1, "y": 1}))
        assert exc.value.code == "PLAYER_INTENT_UNKNOWN_FIELD"

    def test_rate_limit_25_per_second(self):
        validator = MoveIntentValidator()
        for i in range(25):
            validator.check_rate_limit(BINDING, now_ms=i * 10)
        with pytest.raises(MovementValidationError) as exc:
            validator.check_rate_limit(BINDING, now_ms=250)
        assert exc.value.code == "PLAYER_INTENT_RATE_LIMITED"
        # 1 秒后窗口滑动恢复
        validator.check_rate_limit(BINDING, now_ms=1100)


class TestSequenceIdempotency:
    """TEST-PLAYER-006/008 的序号部分：与 NPC 相同的序号语义"""

    def test_same_sequence_same_payload_replays_receipt(self):
        validator = MoveIntentValidator()
        intent = validator.validate_shape(_raw())
        assert validator.check_sequence(BINDING, intent) is None
        validator.record_receipt(BINDING, intent, _receipt(intent))
        replay = validator.check_sequence(BINDING, intent)
        assert replay is not None and replay.accepted is True

    def test_same_sequence_different_payload_conflicts(self):
        validator = MoveIntentValidator()
        first = validator.validate_shape(_raw())
        validator.record_receipt(BINDING, first, _receipt(first))
        conflicting = validator.validate_shape(_raw(direction={"x": 0, "y": 1}))
        with pytest.raises(MovementValidationError) as exc:
            validator.check_sequence(BINDING, conflicting)
        assert exc.value.code == "PLAYER_INPUT_SEQUENCE_CONFLICT"

    def test_stale_sequence_ignored_after_confirmation(self):
        validator = MoveIntentValidator()
        validator.confirm_sequence(BINDING, 800)
        intent = validator.validate_shape(_raw(input_sequence=731))
        receipt = validator.check_sequence(BINDING, intent)
        assert receipt is not None
        assert receipt.accepted is False
        assert receipt.reason_code == "PLAYER_INTENT_SEQUENCE_STALE"


def _receipt(intent):
    from src.player.movement import CommandReceipt

    return CommandReceipt(
        command_id=intent.command_id,
        input_sequence=intent.input_sequence,
        accepted=True,
        confirmed_revision=intent.expected_revision,
    )


class TestReconciliationStateMachine:
    """TEST-PLAYER-008：prediction、乱序、Snapshot 收敛"""

    def test_happy_path_cycle(self):
        sm = ReconciliationStateMachine()
        assert sm.state is ReconciliationState.SYNCED
        sm.transition(ReconciliationTrigger.SEND_INTENT)
        assert sm.state is ReconciliationState.PREDICTING
        sm.transition(ReconciliationTrigger.AWAIT_ACK)
        assert sm.state is ReconciliationState.AWAITING_ACK
        sm.transition(ReconciliationTrigger.ACK_CONFIRMED)
        assert sm.state is ReconciliationState.SYNCED

    def test_correction_path(self):
        sm = ReconciliationStateMachine()
        sm.transition(ReconciliationTrigger.SEND_INTENT)
        sm.transition(ReconciliationTrigger.AWAIT_ACK)
        sm.transition(ReconciliationTrigger.CORRECTION_NEEDED)
        assert sm.state is ReconciliationState.CORRECTING
        sm.transition(ReconciliationTrigger.CORRECTION_APPLIED)
        assert sm.state is ReconciliationState.SYNCED

    def test_revision_gap_requires_snapshot(self):
        sm = ReconciliationStateMachine()
        sm.transition(ReconciliationTrigger.SEND_INTENT)
        sm.transition(ReconciliationTrigger.REVISION_GAP)
        assert sm.state is ReconciliationState.SNAPSHOT_REQUIRED
        # §8：Revision gap 不猜测中间碰撞
        with pytest.raises(MovementValidationError):
            sm.transition(ReconciliationTrigger.ACK_CONFIRMED)
        sm.transition(ReconciliationTrigger.SNAPSHOT_INSTALLED)
        assert sm.state is ReconciliationState.SYNCED

    def test_illegal_transition_rejected(self):
        sm = ReconciliationStateMachine()
        with pytest.raises(MovementValidationError) as exc:
            sm.transition(ReconciliationTrigger.CORRECTION_APPLIED)
        assert exc.value.code == "PLAYER_RECONCILIATION_TRANSITION_INVALID"


class TestInputLatchClearing:
    """TEST-PLAYER-008：stuck-key recovery（RULE-PLAYER-009）"""

    @pytest.mark.parametrize(
        "reason", ["blur", "modal", "mode_switch", "disconnect", "scene_change"]
    )
    def test_any_context_loss_clears_latch(self, reason):
        sm = ReconciliationStateMachine()
        latch = InputLatch()
        latch.press("KeyW")
        latch.press("KeyD")
        sm.transition(ReconciliationTrigger.SEND_INTENT)
        sm.transition(ReconciliationTrigger.CLEAR_INPUT, clear_reason=reason)
        latch.clear()
        assert latch.pressed() == frozenset()
        assert sm.state is ReconciliationState.INPUT_CLEARED
        assert sm.clear_reasons[-1] == reason
        sm.transition(ReconciliationTrigger.RESUME_INPUT)
        assert sm.state is ReconciliationState.SYNCED

    def test_pressed_state_sampling_no_key_repeat_accumulation(self):
        latch = InputLatch()
        # 浏览器自动重复 keydown：pressed-state 采样结果不变
        for _ in range(10):
            latch.press("KeyW")
        assert latch.direction_vector() == (0, -1)
        latch.press("KeyD")
        assert latch.direction_vector() == (1, -1)

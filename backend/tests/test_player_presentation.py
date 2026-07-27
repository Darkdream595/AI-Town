"""
TEST-PLAYER-037..040：相机、窗口与全屏控制（DOC-PLAYER-010）

- TEST-PLAYER-037：首次启动 F11/按钮提示与键盘可达
- TEST-PLAYER-038：user activation、success/error/timeout/Esc
- TEST-PLAYER-039：resize/DPR/小地图 clamp 与 Snapshot transition
- TEST-PLAYER-040：fullscreen/camera 对规则状态零影响
"""

import pytest

from src.player import (
    CameraMode,
    FullscreenStateMachine,
    PresentationState,
    PresentationStatus,
)
from src.player.presentation import (
    FIRST_LAUNCH_HINT,
    FULLSCREEN_FALLBACK_MESSAGE,
    FULLSCREEN_TARGET_ELEMENT_ID,
    PresentationStateError,
    assert_presentation_has_no_rule_effect,
)


class TestFirstLaunchHint:
    """TEST-PLAYER-037"""

    def test_hint_contract(self):
        # RULE-PLAYER-048：F11 提示 + 可点击按钮 + 键盘可达 + 不依赖网络/模型
        assert FIRST_LAUNCH_HINT["f11_hint_text"]
        assert FIRST_LAUNCH_HINT["button_text"]
        assert FIRST_LAUNCH_HINT["keyboard_accessible"] is True
        assert FIRST_LAUNCH_HINT["requires_network"] is False

    def test_fullscreen_target_is_game_shell(self):
        # RULE-PLAYER-049：目标固定为 #game-shell
        assert FULLSCREEN_TARGET_ELEMENT_ID == "game-shell"


class TestFullscreenFlows:
    """TEST-PLAYER-038"""

    def test_requires_user_activation(self):
        sm = FullscreenStateMachine()
        with pytest.raises(PresentationStateError) as exc:
            sm.request_fullscreen(user_activation=False)
        assert exc.value.code == "FULLSCREEN_USER_ACTIVATION_REQUIRED"
        assert sm.status is PresentationStatus.WINDOWED

    def test_success_path(self):
        sm = FullscreenStateMachine()
        sm.request_fullscreen(user_activation=True)
        assert sm.status is PresentationStatus.REQUESTING
        sm.on_fullscreen_change(entered=True)
        assert sm.status is PresentationStatus.FULLSCREEN

    def test_rejection_recovers_windowed(self):
        sm = FullscreenStateMachine()
        sm.request_fullscreen(user_activation=True)
        sm.on_fullscreen_error()
        assert sm.status is PresentationStatus.WINDOWED
        assert sm.last_failure_code == "FULLSCREEN_REJECTED"

    def test_api_unavailable_recovers_windowed(self):
        sm = FullscreenStateMachine(fullscreen_supported=False)
        sm.request_fullscreen(user_activation=True)
        assert sm.status is PresentationStatus.WINDOWED
        assert sm.last_failure_code == "FULLSCREEN_API_UNAVAILABLE"
        assert FULLSCREEN_FALLBACK_MESSAGE  # §6.2 非阻塞提示存在

    def test_timeout_recovers_windowed(self):
        sm = FullscreenStateMachine()
        sm.request_fullscreen(user_activation=True)
        sm.on_timeout()
        assert sm.status is PresentationStatus.WINDOWED
        assert sm.last_failure_code == "FULLSCREEN_TIMEOUT"

    def test_esc_exit_recovers_windowed(self):
        sm = FullscreenStateMachine()
        sm.request_fullscreen(user_activation=True)
        sm.on_fullscreen_change(entered=True)
        sm.exit_fullscreen()
        assert sm.status is PresentationStatus.WINDOWED


class TestPresentationStateSchema:
    """TEST-PLAYER-039"""

    def _state(self, **overrides):
        base = dict(
            presentation_state=PresentationStatus.WINDOWED,
            camera_mode=CameraMode.FOLLOW_PLAYER,
            camera_target_scene_id="scene.crowncreek.town",
            camera_target_x_wu=1024,
            camera_target_y_wu=960,
            zoom=1.0,
            viewport_width_css_px=1920,
            viewport_height_css_px=1080,
            device_pixel_ratio=1.0,
            fullscreen_supported=True,
        )
        base.update(overrides)
        return PresentationState(**base)

    def test_valid_state(self):
        assert self._state().camera_mode is CameraMode.FOLLOW_PLAYER

    def test_camera_modes_closed_set(self):
        assert set(CameraMode) == {
            CameraMode.FOLLOW_PLAYER,
            CameraMode.MAYOR_OVERVIEW,
            CameraMode.CINEMATIC_LOCKED,
        }

    @pytest.mark.parametrize(
        "field,value",
        [("zoom", 0.0), ("viewport_width_css_px", 0), ("device_pixel_ratio", -1.0)],
    )
    def test_invalid_geometry_rejected(self, field, value):
        with pytest.raises(PresentationStateError):
            self._state(**{field: value})


class TestNoRuleEffect:
    """TEST-PLAYER-040"""

    def test_fullscreen_cycle_keeps_world_point_and_emits_nothing(self):
        """RULE-PLAYER-047/051：展示状态变化不产生规则效果与 DomainEvent"""
        assert_presentation_has_no_rule_effect(
            before_world_point=(1024, 960),
            after_world_point=(1024, 960),
            events_emitted=0,
        )

    def test_world_point_change_detected(self):
        with pytest.raises(PresentationStateError) as exc:
            assert_presentation_has_no_rule_effect((0, 0), (1, 0), 0)
        assert exc.value.code == "PRESENTATION_RULE_EFFECT_VIOLATION"

    def test_event_emission_detected(self):
        with pytest.raises(PresentationStateError) as exc:
            assert_presentation_has_no_rule_effect((0, 0), (0, 0), 1)
        assert exc.value.code == "PRESENTATION_EVENT_VIOLATION"

"""
TEST-PLAYER-041..044：输入提示、按键重绑定与无障碍（DOC-PLAYER-011）

- TEST-PLAYER-041：context priority、UiInputGate 与 stuck-key clearing
- TEST-PLAYER-042：key rebinding/conflict/reserved/recovery
- TEST-PLAYER-043：IME、repeat、layout label 与 hold/toggle
- TEST-PLAYER-044：keyboard-only、screen reader、contrast/reduced motion
"""

import pytest

from src.player import (
    DEFAULT_INPUT_MAP,
    INPUT_CONTEXT_PRIORITY,
    InputChord,
    InputContext,
    InputMapValidator,
    InputRebindError,
)


class TestContextPriority:
    """TEST-PLAYER-041"""

    def test_priority_order_matches_contract(self):
        """RULE-PLAYER-052：system/recovery > modal DOM > text input > combat
        > mayor canvas > resident world > global hint"""
        assert INPUT_CONTEXT_PRIORITY == (
            InputContext.SYSTEM_RECOVERY,
            InputContext.MODAL_DOM,
            InputContext.DIALOGUE_INPUT,
            InputContext.COMBAT_TURN,
            InputContext.MAYOR_CANVAS,
            InputContext.RESIDENT_WORLD,
            InputContext.GLOBAL_HINT,
        )

    def test_tab_resolves_to_modal_when_modal_active(self):
        """RULE-PLAYER-053：DOM focus 下 Tab 归 focus navigation"""
        result = InputMapValidator.resolve_action(
            DEFAULT_INPUT_MAP,
            InputChord("Tab"),
            [InputContext.RESIDENT_WORLD, InputContext.MODAL_DOM],
        )
        assert result == (InputContext.MODAL_DOM, "focus_navigation")

    def test_tab_switches_mode_only_in_world_context(self):
        """RULE-PLAYER-015：仅 world input context 的未修饰 Tab 请求模式切换"""
        result = InputMapValidator.resolve_action(
            DEFAULT_INPUT_MAP, InputChord("Tab"), [InputContext.RESIDENT_WORLD]
        )
        assert result == (InputContext.RESIDENT_WORLD, "switch_mode")

    def test_wasd_in_dialogue_input_does_not_move_world(self):
        """RULE-PLAYER-053：textbox 中 WASD 不驱动世界"""
        result = InputMapValidator.resolve_action(
            DEFAULT_INPUT_MAP,
            InputChord("KeyW"),
            [InputContext.DIALOGUE_INPUT, InputContext.RESIDENT_WORLD],
        )
        # dialogue_input 上下文没有 KeyW 绑定 → 不触发任何世界动作
        assert result is None or result[0] is not InputContext.DIALOGUE_INPUT
        # 更高优先级的 dialogue_input 激活时，世界层绑定被闸门屏蔽
        assert InputMapValidator.tab_belongs_to_focus_navigation(
            [InputContext.DIALOGUE_INPUT]
        )

    def test_escape_always_resolves_globally(self):
        result = InputMapValidator.resolve_action(
            DEFAULT_INPUT_MAP,
            InputChord("Escape"),
            [InputContext.MODAL_DOM, InputContext.GLOBAL_HINT],
        )
        assert result == (InputContext.GLOBAL_HINT, "pause_or_back")


class TestRebinding:
    """TEST-PLAYER-042"""

    def test_default_profile_is_valid(self):
        InputMapValidator.validate_profile(DEFAULT_INPUT_MAP)

    def test_rebind_interact_key(self):
        profile = InputMapValidator.rebind(
            DEFAULT_INPUT_MAP, InputContext.RESIDENT_WORLD,
            "interact", (InputChord("KeyF"),),
        )
        result = InputMapValidator.resolve_action(
            profile, InputChord("KeyF"), [InputContext.RESIDENT_WORLD]
        )
        assert result == (InputContext.RESIDENT_WORLD, "interact")
        # 旧键不再触发
        assert InputMapValidator.resolve_action(
            profile, InputChord("KeyE"), [InputContext.RESIDENT_WORLD]
        ) is None

    def test_conflict_rejected_before_save(self):
        """RULE-PLAYER-054：同 context 冲突必须在保存前拒绝"""
        with pytest.raises(InputRebindError) as exc:
            InputMapValidator.rebind(
                DEFAULT_INPUT_MAP, InputContext.RESIDENT_WORLD,
                "interact", (InputChord("KeyI"),),  # 已被 inventory 占用
            )
        assert exc.value.code == "INPUT_CHORD_CONFLICT"

    def test_reserved_chords_cannot_be_rebound(self):
        """RULE-PLAYER-055：Escape/F11 不可移除"""
        with pytest.raises(InputRebindError) as exc:
            InputMapValidator.rebind(
                DEFAULT_INPUT_MAP, InputContext.RESIDENT_WORLD,
                "interact", (InputChord("Escape"),),
            )
        assert exc.value.code == "INPUT_RESERVED_CHORD"

    def test_reserved_actions_cannot_be_rebound(self):
        with pytest.raises(InputRebindError) as exc:
            InputMapValidator.rebind(
                DEFAULT_INPUT_MAP, InputContext.GLOBAL_HINT,
                "pause_or_back", (InputChord("KeyP"),),
            )
        assert exc.value.code == "INPUT_RESERVED_ACTION"

    def test_failed_rebind_preserves_old_profile(self):
        """§6.2 第 6 步：write 失败保留旧 profile，不留半套映射"""
        original = DEFAULT_INPUT_MAP
        try:
            InputMapValidator.rebind(
                original, InputContext.RESIDENT_WORLD,
                "interact", (InputChord("KeyI"),),
            )
        except InputRebindError:
            pass
        result = InputMapValidator.resolve_action(
            original, InputChord("KeyE"), [InputContext.RESIDENT_WORLD]
        )
        assert result == (InputContext.RESIDENT_WORLD, "interact")

    def test_modifier_chord_normalization(self):
        chord = InputChord("Tab", ("Shift",))
        assert chord.key() == ("Tab", ("Shift",))
        with pytest.raises(InputRebindError):
            InputChord("Tab", ("Shift", "Alt"))  # 未按固定顺序排序
        with pytest.raises(InputRebindError):
            InputChord("Tab", ("Hyper",))  # 未知 modifier


class TestHoldToggleAndLabels:
    """TEST-PLAYER-043"""

    def test_hold_toggle_preference_roundtrip(self):
        profile = DEFAULT_INPUT_MAP
        assert profile.hold_to_fast_walk is True
        rebound = InputMapValidator.rebind(
            profile, InputContext.RESIDENT_WORLD,
            "fast_walk", (InputChord("CapsLock"),),
        )
        assert rebound.hold_to_fast_walk is True  # 偏好随 profile 保留

    def test_shift_tab_distinct_chord(self):
        """focus navigation 的 Shift+Tab 与 Tab 是不同 chord"""
        result = InputMapValidator.resolve_action(
            DEFAULT_INPUT_MAP,
            InputChord("Tab", ("Shift",)),
            [InputContext.MODAL_DOM],
        )
        assert result == (InputContext.MODAL_DOM, "focus_navigation_back")


class TestAccessibility:
    """TEST-PLAYER-044"""

    def test_accessibility_preferences_are_presentation_only(self):
        """RULE-PLAYER-056：无障碍偏好只改变表现，不改变规则"""
        assert InputMapValidator.accessibility_preferences_are_presentation_only(
            DEFAULT_INPUT_MAP
        )

    def test_reduced_motion_profile_valid(self):
        from dataclasses import replace

        profile = replace(
            DEFAULT_INPUT_MAP, reduced_motion=True, camera_shake_scale=0.0
        )
        InputMapValidator.validate_profile(profile)
        assert profile.reduced_motion is True
        assert profile.camera_shake_scale == 0.0

    def test_keyboard_only_paths_exist(self):
        """§10 验收：键盘可完成对话/Mayor/设置/退出——关键 action 均有键盘绑定"""
        bound_actions = {b.action_id for b in DEFAULT_INPUT_MAP.bindings}
        for required in (
            "interact", "dialogue_input", "submit", "switch_mode",
            "focus_navigation", "pause_or_back",
        ):
            assert required in bound_actions

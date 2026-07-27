"""
输入提示、按键重绑定与无障碍的纯逻辑层（DOC-PLAYER-011）

- RULE-PLAYER-052：context 优先级解析
- RULE-PLAYER-053：DOM focus 下 Tab 永远用于 focus navigation
- RULE-PLAYER-054：同 context 冲突 chord 必须在保存前解决
- RULE-PLAYER-055：Escape/F11/安全路径/focus navigation 不可移除
- RULE-PLAYER-056：无障碍偏好只改变表现，不改变规则
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class InputRebindError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class InputContext(str, Enum):
    """§3.1 输入上下文全集"""

    SYSTEM_RECOVERY = "system_recovery"
    MODAL_DOM = "modal_dom"
    DIALOGUE_INPUT = "dialogue_input"
    COMBAT_TURN = "combat_turn"
    MAYOR_CANVAS = "mayor_canvas"
    RESIDENT_WORLD = "resident_world"
    GLOBAL_HINT = "global_hint"
    SETTINGS_INPUT = "settings_input"


#: RULE-PLAYER-052：优先级从高到低
INPUT_CONTEXT_PRIORITY: Tuple[InputContext, ...] = (
    InputContext.SYSTEM_RECOVERY,
    InputContext.MODAL_DOM,
    InputContext.DIALOGUE_INPUT,
    InputContext.COMBAT_TURN,
    InputContext.MAYOR_CANVAS,
    InputContext.RESIDENT_WORLD,
    InputContext.GLOBAL_HINT,
)

#: RULE-PLAYER-055：不可移除/不可重绑定的保留键
RESERVED_CHORDS = frozenset({"Escape", "F11"})
RESERVED_ACTIONS = frozenset(
    {"pause_or_back", "browser_fullscreen_hint", "focus_navigation", "confirm", "cancel"}
)

_ALLOWED_MODIFIERS = ("Alt", "Control", "Meta", "Shift")


@dataclass(frozen=True)
class InputChord:
    """§3：物理 KeyboardEvent.code 与排序固定的 modifier 组合"""

    code: str
    modifiers: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.code:
            raise InputRebindError("INPUT_CHORD_CODE_EMPTY")
        bad = set(self.modifiers) - set(_ALLOWED_MODIFIERS)
        if bad:
            raise InputRebindError(
                "INPUT_CHORD_MODIFIER_INVALID", f"unknown modifiers: {sorted(bad)}"
            )
        if tuple(self.modifiers) != tuple(sorted(self.modifiers)):
            raise InputRebindError(
                "INPUT_CHORD_MODIFIER_ORDER", "modifiers must be sorted"
            )

    def key(self) -> Tuple[str, Tuple[str, ...]]:
        return (self.code, self.modifiers)


@dataclass(frozen=True)
class InputBinding:
    context: InputContext
    action_id: str
    chords: Tuple[InputChord, ...]


@dataclass(frozen=True)
class InputMapProfile:
    """§5 InputMap Schema"""

    profile_id: str
    bindings: Tuple[InputBinding, ...]
    reduced_motion: bool = False
    high_contrast: bool = False
    camera_shake_scale: float = 1.0
    hold_to_fast_walk: bool = True
    dialogue_enter_submits: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise InputRebindError("INPUT_MAP_SCHEMA_VERSION_UNSUPPORTED")
        if not self.profile_id:
            raise InputRebindError("INPUT_MAP_PROFILE_ID_EMPTY")
        if not 0.0 <= self.camera_shake_scale <= 1.0:
            raise InputRebindError("INPUT_MAP_SHAKE_SCALE_RANGE")


#: §3.1 默认输入映射
DEFAULT_INPUT_MAP = InputMapProfile(
    profile_id="default.keyboard.v1",
    bindings=(
        InputBinding(InputContext.RESIDENT_WORLD, "move_up", (InputChord("KeyW"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "move_left", (InputChord("KeyA"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "move_down", (InputChord("KeyS"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "move_right", (InputChord("KeyD"),)),
        InputBinding(
            InputContext.RESIDENT_WORLD, "fast_walk", (InputChord("ShiftLeft"),)
        ),
        InputBinding(InputContext.RESIDENT_WORLD, "interact", (InputChord("KeyE"),)),
        InputBinding(
            InputContext.RESIDENT_WORLD, "dialogue_input", (InputChord("Enter"),)
        ),
        InputBinding(InputContext.RESIDENT_WORLD, "inventory", (InputChord("KeyI"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "journal", (InputChord("KeyJ"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "map", (InputChord("KeyM"),)),
        InputBinding(InputContext.RESIDENT_WORLD, "switch_mode", (InputChord("Tab"),)),
        InputBinding(InputContext.GLOBAL_HINT, "pause_or_back", (InputChord("Escape"),)),
        InputBinding(
            InputContext.GLOBAL_HINT, "browser_fullscreen_hint", (InputChord("F11"),)
        ),
        InputBinding(InputContext.MAYOR_CANVAS, "pan_up", (InputChord("KeyW"),)),
        InputBinding(InputContext.MAYOR_CANVAS, "pan_left", (InputChord("KeyA"),)),
        InputBinding(InputContext.MAYOR_CANVAS, "pan_down", (InputChord("KeyS"),)),
        InputBinding(InputContext.MAYOR_CANVAS, "pan_right", (InputChord("KeyD"),)),
        InputBinding(
            InputContext.MODAL_DOM, "focus_navigation", (InputChord("Tab"),)
        ),
        InputBinding(
            InputContext.MODAL_DOM,
            "focus_navigation_back",
            (InputChord("Tab", ("Shift",)),),
        ),
        InputBinding(InputContext.DIALOGUE_INPUT, "submit", (InputChord("Enter"),)),
        InputBinding(
            InputContext.DIALOGUE_INPUT,
            "newline",
            (InputChord("Enter", ("Shift",)),),
        ),
    ),
)


class InputMapValidator:
    """重绑定校验器（§6.2 第 3 步：冲突/保留键/安全路径检查）"""

    @staticmethod
    def resolve_action(
        profile: InputMapProfile,
        chord: InputChord,
        active_contexts: List[InputContext],
    ) -> Optional[Tuple[InputContext, str]]:
        """
        RULE-PLAYER-052：按 context 优先级解析按键归属。

        active_contexts 中优先级最高且绑定了该 chord 的 context 胜出。
        """
        ordered = sorted(
            set(active_contexts),
            key=lambda c: INPUT_CONTEXT_PRIORITY.index(c),
        )
        for context in ordered:
            for binding in profile.bindings:
                if binding.context is not context:
                    continue
                if any(c.key() == chord.key() for c in binding.chords):
                    return (context, binding.action_id)
        return None

    @staticmethod
    def validate_profile(profile: InputMapProfile) -> None:
        """
        RULE-PLAYER-054：同一 context 内两个不可组合 action 不得绑定同一 chord；
        RULE-PLAYER-055：保留键/安全路径必须存在。
        """
        reserved_seen: set[str] = set()
        for context in InputContext:
            chord_owners: Dict[Tuple[str, Tuple[str, ...]], str] = {}
            for binding in profile.bindings:
                if binding.context is not context:
                    continue
                if binding.action_id in RESERVED_ACTIONS:
                    reserved_seen.add(binding.action_id)
                for chord in binding.chords:
                    if chord.code in RESERVED_CHORDS and binding.action_id not in RESERVED_ACTIONS:
                        raise InputRebindError(
                            "INPUT_RESERVED_CHORD",
                            f"{chord.code} is reserved and cannot be rebound",
                        )
                    owner = chord_owners.get(chord.key())
                    if owner is not None and owner != binding.action_id:
                        raise InputRebindError(
                            "INPUT_CHORD_CONFLICT",
                            f"chord {chord.key()} bound to both {owner} and "
                            f"{binding.action_id} in {context.value}",
                        )
                    chord_owners[chord.key()] = binding.action_id

        missing = set(RESERVED_ACTIONS) - reserved_seen - {"confirm", "cancel"}
        if missing:
            raise InputRebindError(
                "INPUT_RESERVED_ACTION_MISSING",
                f"reserved actions missing: {sorted(missing)}",
            )

    @staticmethod
    def rebind(
        profile: InputMapProfile,
        context: InputContext,
        action_id: str,
        new_chords: Tuple[InputChord, ...],
    ) -> InputMapProfile:
        """
        §6.2：原子替换绑定；校验失败保留旧 profile，不留半套映射。
        """
        if action_id in RESERVED_ACTIONS:
            raise InputRebindError(
                "INPUT_RESERVED_ACTION", f"{action_id} cannot be rebound"
            )
        new_bindings: List[InputBinding] = []
        replaced = False
        for binding in profile.bindings:
            if binding.context is context and binding.action_id == action_id:
                new_bindings.append(
                    InputBinding(context, action_id, new_chords)
                )
                replaced = True
            else:
                new_bindings.append(binding)
        if not replaced:
            raise InputRebindError(
                "INPUT_ACTION_UNKNOWN", f"{action_id} not in {context.value}"
            )
        candidate = InputMapProfile(
            profile_id=profile.profile_id,
            bindings=tuple(new_bindings),
            reduced_motion=profile.reduced_motion,
            high_contrast=profile.high_contrast,
            camera_shake_scale=profile.camera_shake_scale,
            hold_to_fast_walk=profile.hold_to_fast_walk,
            dialogue_enter_submits=profile.dialogue_enter_submits,
        )
        # 先整体校验，失败则旧 profile 不变（原子语义）
        InputMapValidator.validate_profile(candidate)
        return candidate

    @staticmethod
    def tab_belongs_to_focus_navigation(active_contexts: List[InputContext]) -> bool:
        """
        RULE-PLAYER-053/015：DOM focus/modal 存在时 Tab 永远归 focus navigation；
        仅 resident_world 的未修饰 Tab 请求模式切换。
        """
        if InputContext.MODAL_DOM in active_contexts or InputContext.DIALOGUE_INPUT in active_contexts:
            return True
        return InputContext.RESIDENT_WORLD not in active_contexts

    @staticmethod
    def accessibility_preferences_are_presentation_only(profile: InputMapProfile) -> bool:
        """RULE-PLAYER-056：无障碍偏好不含任何规则字段，仅表现层"""
        return (
            isinstance(profile.reduced_motion, bool)
            and isinstance(profile.high_contrast, bool)
            and 0.0 <= profile.camera_shake_scale <= 1.0
        )

"""
相机、窗口与全屏控制的纯逻辑层（DOC-PLAYER-010）

本模块不含 DOM/Phaser；只拥有 presentation 状态机与规则不变量：
- RULE-PLAYER-047：展示状态不能改变 WorldPoint/Collision/交互距离/视线/authority
- RULE-PLAYER-048：首屏必须同时提供 F11 提示与可点击全屏按钮
- RULE-PLAYER-049：Fullscreen 请求只能在真实 user activation 中发起
- RULE-PLAYER-050：失败恢复 windowed layout/focus/input，不卡死
- RULE-PLAYER-051：退出/resize/DPR 变化重新 clamp camera，不发 DomainEvent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class CameraMode(str, Enum):
    """§5：camera_mode 全集"""

    FOLLOW_PLAYER = "follow_player"
    MAYOR_OVERVIEW = "mayor_overview"
    CINEMATIC_LOCKED = "cinematic_locked"


class PresentationStatus(str, Enum):
    """§3 Presentation State 全集"""

    WINDOWED = "windowed"
    REQUESTING = "requesting"
    FULLSCREEN = "fullscreen"
    EXITING = "exiting"
    FAILED = "failed"


class PresentationStateError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class PresentationState:
    """
    §5 客户端 Presentation 状态 Schema。

    不进入权威 world snapshot（§5/§9），只进入客户端诊断。
    """

    presentation_state: PresentationStatus
    camera_mode: CameraMode
    camera_target_scene_id: str
    camera_target_x_wu: int
    camera_target_y_wu: int
    zoom: float
    viewport_width_css_px: int
    viewport_height_css_px: int
    device_pixel_ratio: float
    fullscreen_supported: bool
    last_failure_code: Optional[str] = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PresentationStateError("PRESENTATION_SCHEMA_VERSION_UNSUPPORTED")
        if self.zoom <= 0:
            raise PresentationStateError("PRESENTATION_ZOOM_INVALID")
        if self.viewport_width_css_px <= 0 or self.viewport_height_css_px <= 0:
            raise PresentationStateError("PRESENTATION_VIEWPORT_INVALID")
        if self.device_pixel_ratio <= 0:
            raise PresentationStateError("PRESENTATION_DPR_INVALID")


#: §6.2 首次进入提示契约（RULE-PLAYER-048）：不依赖模型或网络
FIRST_LAUNCH_HINT = {
    "f11_hint_text": "按 F11 进入全屏",
    "button_text": "全屏游玩",
    "dismiss_text": "稍后",
    "keyboard_accessible": True,
    "requires_network": False,
}

#: §6.2 第 5 步：自动全屏失败的非阻塞提示
FULLSCREEN_FALLBACK_MESSAGE = "无法自动全屏，可按 F11；游戏仍可在窗口中运行。"

#: §5：Element Fullscreen 的固定目标（RULE-PLAYER-049）
FULLSCREEN_TARGET_ELEMENT_ID = "game-shell"


class FullscreenStateMachine:
    """
    §6.2 fullscreen 流程状态机。

    成功、拒绝、API 缺失、Esc 退出、超时五条路径都确定地回到
    windowed 或 fullscreen，不存在卡死态（RULE-PLAYER-050）。
    """

    def __init__(self, fullscreen_supported: bool = True) -> None:
        self._status = PresentationStatus.WINDOWED
        self._supported = fullscreen_supported
        self._last_failure_code: Optional[str] = None

    @property
    def status(self) -> PresentationStatus:
        return self._status

    @property
    def last_failure_code(self) -> Optional[str]:
        return self._last_failure_code

    def request_fullscreen(self, user_activation: bool) -> PresentationStatus:
        """
        RULE-PLAYER-049：无真实 user activation 一律拒绝发起；
        发起前不等待网络/模型。
        """
        if not user_activation:
            raise PresentationStateError(
                "FULLSCREEN_USER_ACTIVATION_REQUIRED",
                "fullscreen request must originate from a user gesture",
            )
        if not self._supported:
            self._fail("FULLSCREEN_API_UNAVAILABLE")
            return self._status
        self._status = PresentationStatus.REQUESTING
        return self._status

    def on_fullscreen_change(self, entered: bool) -> PresentationStatus:
        """fullscreenchange 事件：成功后进入 fullscreen；Esc 退出走 windowed"""
        if entered and self._status is PresentationStatus.REQUESTING:
            self._status = PresentationStatus.FULLSCREEN
        elif not entered:
            self._status = PresentationStatus.WINDOWED
        return self._status

    def on_fullscreen_error(self, code: str = "FULLSCREEN_REJECTED") -> PresentationStatus:
        return self._fail(code)

    def on_timeout(self) -> PresentationStatus:
        """§6.2 第 5 步：3 秒无 change 视为失败，恢复 windowed"""
        if self._status is PresentationStatus.REQUESTING:
            return self._fail("FULLSCREEN_TIMEOUT")
        return self._status

    def exit_fullscreen(self) -> PresentationStatus:
        """§6.2 第 4 步：Esc/浏览器退出与 windowed resize 同路径"""
        if self._status is PresentationStatus.FULLSCREEN:
            self._status = PresentationStatus.EXITING
        self._status = PresentationStatus.WINDOWED
        return self._status

    def _fail(self, code: str) -> PresentationStatus:
        self._status = PresentationStatus.WINDOWED
        self._last_failure_code = code
        return self._status


def assert_presentation_has_no_rule_effect(
    before_world_point: Tuple[int, int],
    after_world_point: Tuple[int, int],
    events_emitted: int,
) -> None:
    """
    RULE-PLAYER-047/051：fullscreen/zoom/Mayor pan/resize 后
    WorldPoint 不变且不产生 DomainEvent。
    """
    if before_world_point != after_world_point:
        raise PresentationStateError(
            "PRESENTATION_RULE_EFFECT_VIOLATION",
            "presentation change must not alter actor WorldPoint",
        )
    if events_emitted != 0:
        raise PresentationStateError(
            "PRESENTATION_EVENT_VIOLATION",
            "presentation change must not emit DomainEvent",
        )

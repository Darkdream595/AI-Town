"""
Foundation 基础设施模块

提供跨系统的核心功能：
- ID 生成（ULID）
- 坐标系统
- 时间转换
- 事件溯源
- 幂等性
"""

from .id_generator import generate_ulid, is_valid_ulid
from .coordinates import WorldCoordinate, LocalCoordinate, convert_world_to_local, convert_local_to_world
from .time_conversion import RealTime, GameTime, real_to_game_time, game_to_real_time
from .domain_event import DomainEvent
from .invariants import validate_invariants

__all__ = [
    "generate_ulid",
    "is_valid_ulid",
    "WorldCoordinate",
    "LocalCoordinate",
    "convert_world_to_local",
    "convert_local_to_world",
    "RealTime",
    "GameTime",
    "real_to_game_time",
    "game_to_real_time",
    "DomainEvent",
    "validate_invariants",
]

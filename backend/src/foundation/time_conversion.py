"""
时间转换工具

符合 DOC-FOUNDATION-006 规范：
- RealTime: 现实时间（Unix 时间戳，毫秒）
- GameTime: 游戏时间（游戏分钟，从世界创建起算）
- RULE-FOUNDATION-048: 1 现实秒 = 1 游戏分钟
- RULE-FOUNDATION-049: 时间戳序列化为 RFC 3339 UTC
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# RULE-FOUNDATION-048: 时间转换率
GAME_MINUTES_PER_REAL_SECOND = 1
REAL_MS_PER_GAME_MINUTE = 1000  # 1 游戏分钟 = 1000 现实毫秒


@dataclass
class RealTime:
    """
    现实时间（Real Time）

    - 单位：Unix 时间戳（毫秒）
    - 序列化格式：RFC 3339 UTC
    """
    timestamp_ms: int

    @classmethod
    def now(cls) -> "RealTime":
        """获取当前现实时间"""
        return cls(timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000))

    @classmethod
    def from_iso(cls, iso_string: str) -> "RealTime":
        """从 ISO 8601 字符串创建"""
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return cls(timestamp_ms=int(dt.timestamp() * 1000))

    def to_iso(self) -> str:
        """转换为 ISO 8601 字符串（RFC 3339 UTC）"""
        dt = datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)
        return dt.isoformat().replace('+00:00', 'Z')

    def to_datetime(self) -> datetime:
        """转换为 datetime 对象"""
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)


@dataclass
class GameTime:
    """
    游戏时间（Game Time）

    - 单位：游戏分钟（从世界创建起算）
    - 整数值，无小数
    """
    game_minutes: int

    def to_hours_minutes(self) -> tuple[int, int]:
        """转换为小时和分钟"""
        hours = self.game_minutes // 60
        minutes = self.game_minutes % 60
        return (hours, minutes)

    def to_days_hours_minutes(self) -> tuple[int, int, int]:
        """转换为天、小时和分钟"""
        days = self.game_minutes // (60 * 24)
        remaining_minutes = self.game_minutes % (60 * 24)
        hours = remaining_minutes // 60
        minutes = remaining_minutes % 60
        return (days, hours, minutes)


def real_to_game_time(
    real_time: RealTime,
    world_creation_time: RealTime
) -> GameTime:
    """
    现实时间 → 游戏时间

    Args:
        real_time: 当前现实时间
        world_creation_time: 世界创建时的现实时间

    Returns:
        GameTime: 游戏时间（游戏分钟）

    Examples:
        >>> creation = RealTime(timestamp_ms=1000000)
        >>> current = RealTime(timestamp_ms=1060000)  # 60 秒后
        >>> game_time = real_to_game_time(current, creation)
        >>> game_time.game_minutes
        60
    """
    elapsed_ms = real_time.timestamp_ms - world_creation_time.timestamp_ms

    if elapsed_ms < 0:
        raise ValueError("real_time cannot be before world_creation_time")

    # RULE-FOUNDATION-048: 1 现实秒 = 1 游戏分钟
    game_minutes = elapsed_ms // REAL_MS_PER_GAME_MINUTE

    return GameTime(game_minutes=int(game_minutes))


def game_to_real_time(
    game_time: GameTime,
    world_creation_time: RealTime
) -> RealTime:
    """
    游戏时间 → 现实时间

    Args:
        game_time: 游戏时间
        world_creation_time: 世界创建时的现实时间

    Returns:
        RealTime: 对应的现实时间

    Examples:
        >>> creation = RealTime(timestamp_ms=1000000)
        >>> game_time = GameTime(game_minutes=60)
        >>> real_time = game_to_real_time(game_time, creation)
        >>> real_time.timestamp_ms
        1060000
    """
    elapsed_ms = game_time.game_minutes * REAL_MS_PER_GAME_MINUTE
    real_timestamp_ms = world_creation_time.timestamp_ms + elapsed_ms

    return RealTime(timestamp_ms=real_timestamp_ms)

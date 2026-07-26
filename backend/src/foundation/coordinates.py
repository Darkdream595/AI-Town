"""
坐标系统

符合 DOC-FOUNDATION-006 和 DOC-MAP-001 规范：
- 世界坐标（World Units, wu）：权威坐标系统
- 本地坐标（Tile + 偏移）：用于地图编辑
- RULE-FOUNDATION-040: 1 tile = 32 wu
- RULE-FOUNDATION-042: 精度为 1/16 wu
"""

from dataclasses import dataclass
from typing import Tuple

# RULE-FOUNDATION-040: 坐标单位常量
TILE_SIZE = 32  # 1 tile = 32 wu
WU_PRECISION = 1 / 16  # 精度为 1/16 wu


@dataclass
class WorldCoordinate:
    """
    世界坐标（World Units）

    - 原点：地图左上角
    - X 轴：向右为正
    - Y 轴：向下为正
    - 单位：wu（世界单位）
    """
    x_wu: float
    y_wu: float

    def __post_init__(self):
        """验证坐标精度"""
        # RULE-FOUNDATION-042: 量化到 1/16 wu
        self.x_wu = round(self.x_wu / WU_PRECISION) * WU_PRECISION
        self.y_wu = round(self.y_wu / WU_PRECISION) * WU_PRECISION

    def distance_to(self, other: "WorldCoordinate") -> float:
        """
        计算到另一个坐标的欧几里得距离

        Args:
            other: 目标坐标

        Returns:
            float: 距离（wu）
        """
        dx = self.x_wu - other.x_wu
        dy = self.y_wu - other.y_wu
        return (dx ** 2 + dy ** 2) ** 0.5

    def to_tuple(self) -> Tuple[float, float]:
        """返回 (x, y) 元组"""
        return (self.x_wu, self.y_wu)


@dataclass
class LocalCoordinate:
    """
    本地坐标（Tile + 偏移）

    用于地图编辑和区域内定位
    - tile_x, tile_y: 瓦片坐标（整数）
    - offset_x_wu, offset_y_wu: 瓦片内偏移（0-31 wu）
    """
    tile_x: int
    tile_y: int
    offset_x_wu: float = 0.0
    offset_y_wu: float = 0.0

    def __post_init__(self):
        """验证偏移量范围"""
        # 偏移量必须在 [0, TILE_SIZE) 范围内
        if not (0 <= self.offset_x_wu < TILE_SIZE):
            raise ValueError(f"offset_x_wu must be in [0, {TILE_SIZE}), got {self.offset_x_wu}")
        if not (0 <= self.offset_y_wu < TILE_SIZE):
            raise ValueError(f"offset_y_wu must be in [0, {TILE_SIZE}), got {self.offset_y_wu}")

        # 量化到 1/16 wu
        self.offset_x_wu = round(self.offset_x_wu / WU_PRECISION) * WU_PRECISION
        self.offset_y_wu = round(self.offset_y_wu / WU_PRECISION) * WU_PRECISION


def convert_world_to_local(world_coord: WorldCoordinate) -> LocalCoordinate:
    """
    世界坐标 → 本地坐标

    Args:
        world_coord: 世界坐标

    Returns:
        LocalCoordinate: 本地坐标（tile + 偏移）

    Examples:
        >>> wc = WorldCoordinate(x_wu=96.0, y_wu=64.0)
        >>> lc = convert_world_to_local(wc)
        >>> lc.tile_x, lc.tile_y
        (3, 2)
        >>> lc.offset_x_wu, lc.offset_y_wu
        (0.0, 0.0)
    """
    tile_x = int(world_coord.x_wu // TILE_SIZE)
    tile_y = int(world_coord.y_wu // TILE_SIZE)
    offset_x_wu = world_coord.x_wu % TILE_SIZE
    offset_y_wu = world_coord.y_wu % TILE_SIZE

    return LocalCoordinate(
        tile_x=tile_x,
        tile_y=tile_y,
        offset_x_wu=offset_x_wu,
        offset_y_wu=offset_y_wu
    )


def convert_local_to_world(local_coord: LocalCoordinate) -> WorldCoordinate:
    """
    本地坐标 → 世界坐标

    Args:
        local_coord: 本地坐标

    Returns:
        WorldCoordinate: 世界坐标

    Examples:
        >>> lc = LocalCoordinate(tile_x=3, tile_y=2, offset_x_wu=16.0, offset_y_wu=8.0)
        >>> wc = convert_local_to_world(lc)
        >>> wc.x_wu, wc.y_wu
        (112.0, 72.0)
    """
    x_wu = local_coord.tile_x * TILE_SIZE + local_coord.offset_x_wu
    y_wu = local_coord.tile_y * TILE_SIZE + local_coord.offset_y_wu

    return WorldCoordinate(x_wu=x_wu, y_wu=y_wu)

"""
可行走区域定义

符合 DOC-MAP-005 规范：
- RULE-MAP-017: Walkable Surface 结构化 Polygon
- RULE-MAP-018: 合法站立要求 Agent Disc 完整包含
- RULE-MAP-019: 玩家与 NPC 相同 Profile 得到相同结果
- RULE-MAP-020: Road 是 Terrain Tag，不是图片颜色
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from ..foundation.coordinates import WorldCoordinate


# ==================== Terrain Tags ====================

class TerrainTag(str, Enum):
    """
    地形标签

    RULE-MAP-020: Road 是 Terrain Tag
    """
    ROAD_PRIMARY = "road.primary"
    ROAD_SECONDARY = "road.secondary"
    FLOOR = "floor"
    GRASS = "grass"
    ROUGH = "rough"


# 基础 cost 表（单位：千分之一，用于精确计算）
TERRAIN_BASE_COST = {
    TerrainTag.ROAD_PRIMARY: 800,
    TerrainTag.ROAD_SECONDARY: 900,
    TerrainTag.FLOOR: 1000,
    TerrainTag.GRASS: 1100,
    TerrainTag.ROUGH: 1400,
}


# ==================== Walkable Surface ====================

@dataclass(frozen=True)
class WalkableSurface:
    """
    可行走表面

    RULE-MAP-017: 使用结构化 Polygon，边界包含在 Walkable Set 中
    """
    surface_id: str
    scene_id: str
    vertices_wu: List[Tuple[float, float]]  # 闭合 Polygon 顶点
    terrain_tag: TerrainTag
    base_cost_q1000: int  # 千分之一单位的基础代价
    allowed_profile_tags: List[str]

    def __post_init__(self):
        """验证 Surface 合法性"""
        if len(self.vertices_wu) < 3:
            raise ValueError(f"Surface {self.surface_id}: must have at least 3 vertices")

        # 验证 base_cost 在合理范围内
        if not (0 < self.base_cost_q1000 <= 10000):
            raise ValueError(f"Surface {self.surface_id}: base_cost_q1000 must be in (0, 10000]")

    def contains_point(self, point: WorldCoordinate) -> bool:
        """
        判断点是否在 Polygon 内（使用 Ray Casting 算法）

        边界上的点视为包含在内
        """
        x, y = point.x_wu, point.y_wu
        n = len(self.vertices_wu)
        inside = False

        p1x, p1y = self.vertices_wu[0]
        for i in range(1, n + 1):
            p2x, p2y = self.vertices_wu[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside


# ==================== Agent Profile ====================

@dataclass(frozen=True)
class AgentProfile:
    """
    Agent 移动 Profile

    定义 Agent 的物理属性和能力标签
    """
    radius_wu: float  # Agent 半径
    clearance_wu: float  # 额外安全间隙
    tags: List[str]  # 能力标签（如 ["ground"]）

    def get_total_radius(self) -> float:
        """获取总半径（radius + clearance）"""
        return self.radius_wu + self.clearance_wu


# 默认人形 Profile
DEFAULT_HUMANOID_PROFILE = AgentProfile(
    radius_wu=10.0,
    clearance_wu=2.0,
    tags=["ground"]
)


# ==================== Position Legality ====================

class PositionLegality(str, Enum):
    """位置合法性结果"""
    LEGAL = "legal"
    OUT_OF_BOUNDS = "out_of_bounds"
    NOT_ON_WALKABLE_SURFACE = "not_on_walkable_surface"
    DISC_EXCEEDS_SURFACE = "disc_exceeds_surface"
    PROFILE_TAG_MISMATCH = "profile_tag_mismatch"


@dataclass(frozen=True)
class StandabilityResult:
    """站立性检查结果"""
    legality: PositionLegality
    surface_id: Optional[str] = None
    terrain_tag: Optional[TerrainTag] = None
    effective_cost_q1000: Optional[int] = None


# ==================== Walkability System ====================

class WalkabilitySystem:
    """
    可行走性系统

    管理 Walkable Surface 的注册和查询
    """

    def __init__(self, scene_id: str, scene_bounds: 'SceneBounds'):
        """
        初始化可行走性系统

        Args:
            scene_id: Scene 标识符
            scene_bounds: Scene 边界
        """
        self.scene_id = scene_id
        self.scene_bounds = scene_bounds
        self.surfaces: List[WalkableSurface] = []

    def add_surface(self, surface: WalkableSurface):
        """添加可行走表面"""
        if surface.scene_id != self.scene_id:
            raise ValueError(f"Surface scene_id {surface.scene_id} does not match system scene_id {self.scene_id}")
        self.surfaces.append(surface)

    def is_standable(
        self,
        point: WorldCoordinate,
        profile: AgentProfile
    ) -> StandabilityResult:
        """
        检查位置是否可站立

        RULE-MAP-018: 合法站立要求 Agent Disc 完整位于 Walkable Set

        Args:
            point: 要检查的位置
            profile: Agent Profile

        Returns:
            StandabilityResult: 站立性检查结果
        """
        # 1. 检查边界（包括 Agent Disc）
        total_radius = profile.get_total_radius()
        if not self.scene_bounds.contains_with_radius(point, total_radius):
            return StandabilityResult(legality=PositionLegality.OUT_OF_BOUNDS)

        # 2. 找到包含该点的所有 Surface
        matching_surfaces = []
        for surface in self.surfaces:
            # 检查 profile tags 匹配
            profile_match = any(tag in surface.allowed_profile_tags for tag in profile.tags)
            if not profile_match:
                continue

            # 检查点是否在 Surface 内
            if surface.contains_point(point):
                matching_surfaces.append(surface)

        if not matching_surfaces:
            return StandabilityResult(legality=PositionLegality.NOT_ON_WALKABLE_SURFACE)

        # 3. 检查 Agent Disc 是否完全在某个 Surface 内
        # 简化实现：采样圆周上的点检查是否都在 Surface 内
        disc_legal_surfaces = []
        for surface in matching_surfaces:
            if self._is_disc_fully_in_surface(point, total_radius, surface):
                disc_legal_surfaces.append(surface)

        if not disc_legal_surfaces:
            return StandabilityResult(legality=PositionLegality.DISC_EXCEEDS_SURFACE)

        # 4. 选择最低 cost 的 Surface（重叠时）
        best_surface = min(disc_legal_surfaces, key=lambda s: (s.base_cost_q1000, s.surface_id))

        return StandabilityResult(
            legality=PositionLegality.LEGAL,
            surface_id=best_surface.surface_id,
            terrain_tag=best_surface.terrain_tag,
            effective_cost_q1000=best_surface.base_cost_q1000
        )

    def _is_disc_fully_in_surface(
        self,
        center: WorldCoordinate,
        radius: float,
        surface: WalkableSurface
    ) -> bool:
        """
        检查以 center 为圆心、radius 为半径的圆盘是否完全在 Surface 内

        采样策略：检查圆心和圆周上 8 个方向的点
        """
        # 检查圆心
        if not surface.contains_point(center):
            return False

        # 检查圆周上 8 个方向的点
        import math
        for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
            angle_rad = math.radians(angle_deg)
            test_x = center.x_wu + radius * math.cos(angle_rad)
            test_y = center.y_wu + radius * math.sin(angle_rad)
            test_point = WorldCoordinate(x_wu=test_x, y_wu=test_y)

            if not surface.contains_point(test_point):
                return False

        return True

    def surface_tags_at(self, point: WorldCoordinate) -> List[TerrainTag]:
        """
        获取点所在的所有 Surface 的 Terrain Tags

        按 base_cost 排序（最低优先）
        """
        matching_surfaces = [
            surface for surface in self.surfaces
            if surface.contains_point(point)
        ]

        # 按 cost 排序
        matching_surfaces.sort(key=lambda s: (s.base_cost_q1000, s.surface_id))

        return [surface.terrain_tag for surface in matching_surfaces]

    def get_surface_count(self) -> int:
        """获取 Surface 数量"""
        return len(self.surfaces)

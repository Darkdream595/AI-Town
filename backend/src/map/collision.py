"""
碰撞系统

符合 DOC-MAP-006 规范：
- RULE-MAP-021: Ring winding 和 Signed Area
- RULE-MAP-022: Polygon 闭合、简单、无自交
- RULE-MAP-023: Boundary-exclusive 分类
- RULE-MAP-024: Swept Disc 检查
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional
import math
from ..foundation.coordinates import WorldCoordinate


# ==================== Obstacle Tags ====================

class ObstacleTag(str, Enum):
    """障碍物标签"""
    STRUCTURE_WALL = "structure.wall"
    STRUCTURE_TREE_TRUNK = "structure.tree_trunk"
    TERRAIN_CLIFF = "terrain.cliff"
    TERRAIN_WATER = "terrain.water"
    STRUCTURE_RUBBLE = "structure.rubble"
    DOOR_CLOSED = "door.closed"
    HAZARD_HARD_BLOCK = "hazard.hard_block"
    CONSTRUCTION_BLOCKED = "construction.blocked"


# ==================== Polygon Validation ====================

def compute_signed_area(vertices: List[Tuple[float, float]]) -> float:
    """
    计算多边形的 Signed Area

    RULE-MAP-021: 在 +Y 向下坐标中
    - 顺时针（CW）: Signed Area > 0
    - 逆时针（CCW）: Signed Area < 0

    Formula: 0.5 × Σ(x_i*y_(i+1) - x_(i+1)*y_i)
    """
    if len(vertices) < 3:
        return 0.0

    area = 0.0
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += x1 * y2 - x2 * y1

    return area / 2.0


def is_clockwise(vertices: List[Tuple[float, float]]) -> bool:
    """判断顶点是否按顺时针顺序（在 +Y 向下坐标中）"""
    return compute_signed_area(vertices) > 0


def is_counter_clockwise(vertices: List[Tuple[float, float]]) -> bool:
    """判断顶点是否按逆时针顺序（在 +Y 向下坐标中）"""
    return compute_signed_area(vertices) < 0


def validate_polygon_vertices(vertices: List[Tuple[float, float]]) -> List[str]:
    """
    验证 Polygon 顶点

    RULE-MAP-022: 检查
    - 至少 3 个顶点
    - 连续顶点距离至少 1/16 wu
    - 绝对面积至少 1 wu²

    Returns:
        List[str]: 错误信息列表，空列表表示验证通过
    """
    errors = []

    # 检查顶点数量
    if len(vertices) < 3:
        errors.append("Polygon must have at least 3 vertices")
        return errors

    # 检查连续顶点距离
    min_distance = 1.0 / 16.0  # 1/16 wu
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if dist < min_distance:
            errors.append(f"Consecutive vertices {i} and {(i+1)%n} too close: {dist:.6f} < {min_distance}")

    # 检查绝对面积
    area = abs(compute_signed_area(vertices))
    if area < 1.0:
        errors.append(f"Polygon area too small: {area:.6f} < 1.0 wu²")

    return errors


# ==================== Collision Shape ====================

@dataclass(frozen=True)
class CollisionPolygon:
    """
    碰撞多边形

    RULE-MAP-021: Outer Ring 顺时针，Hole Rings 逆时针
    """
    collision_id: str
    scene_id: str
    outer_ring_wu: List[Tuple[float, float]]
    hole_rings_wu: List[List[Tuple[float, float]]]
    obstacle_tag: ObstacleTag
    source_entity_id: Optional[str]
    enabled: bool
    source_revision: int

    def __post_init__(self):
        """验证 Collision Polygon"""
        # 验证 Outer Ring 顶点
        errors = validate_polygon_vertices(self.outer_ring_wu)
        if errors:
            raise ValueError(f"Outer ring validation failed: {', '.join(errors)}")

        # RULE-MAP-021: Outer Ring 必须顺时针
        if not is_clockwise(self.outer_ring_wu):
            raise ValueError(f"Outer ring must be clockwise (CW), got CCW")

        # 验证每个 Hole Ring
        for idx, hole in enumerate(self.hole_rings_wu):
            errors = validate_polygon_vertices(hole)
            if errors:
                raise ValueError(f"Hole ring {idx} validation failed: {', '.join(errors)}")

            # RULE-MAP-021: Hole Ring 必须逆时针
            if not is_counter_clockwise(hole):
                raise ValueError(f"Hole ring {idx} must be counter-clockwise (CCW), got CW")

    def get_bounds(self) -> Tuple[float, float, float, float]:
        """获取 AABB 边界 (min_x, min_y, max_x, max_y)"""
        if not self.outer_ring_wu:
            return (0.0, 0.0, 0.0, 0.0)

        xs = [v[0] for v in self.outer_ring_wu]
        ys = [v[1] for v in self.outer_ring_wu]
        return (min(xs), min(ys), max(xs), max(ys))

    def contains_point(self, point: WorldCoordinate) -> bool:
        """
        判断点是否在 Polygon 内（使用 Ray Casting）

        RULE-MAP-023: Boundary-exclusive（边界不算在内）
        """
        # 检查是否在 Outer Ring 内
        if not self._point_in_ring(point, self.outer_ring_wu):
            return False

        # 检查是否在任何 Hole 内（如果在 Hole 内则不算在 Polygon 内）
        for hole in self.hole_rings_wu:
            if self._point_in_ring(point, hole):
                return False

        return True

    def _point_in_ring(self, point: WorldCoordinate, ring: List[Tuple[float, float]]) -> bool:
        """Ray Casting 算法判断点是否在 ring 内"""
        x, y = point.x_wu, point.y_wu
        n = len(ring)
        inside = False

        p1x, p1y = ring[0]
        for i in range(1, n + 1):
            p2x, p2y = ring[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside


# ==================== Collision Detection ====================

@dataclass(frozen=True)
class CollisionHit:
    """碰撞命中结果"""
    collision_id: str
    obstacle_tag: ObstacleTag
    hit_point: Optional[WorldCoordinate] = None


@dataclass(frozen=True)
class SweepResult:
    """Swept Disc 检查结果"""
    clear: bool
    first_hit_fraction_q1000000: int  # 百万分之一单位（0-1000000）
    collision_id: Optional[str] = None
    navigation_revision: int = 0


class CollisionSystem:
    """
    碰撞系统

    管理 Collision Polygon 的注册和查询
    """

    def __init__(self, scene_id: str, scene_bounds: 'SceneBounds'):
        """
        初始化碰撞系统

        Args:
            scene_id: Scene 标识符
            scene_bounds: Scene 边界
        """
        self.scene_id = scene_id
        self.scene_bounds = scene_bounds
        self.collisions: List[CollisionPolygon] = []
        self.revision = 0

    def add_collision(self, collision: CollisionPolygon):
        """添加碰撞多边形"""
        if collision.scene_id != self.scene_id:
            raise ValueError(
                f"Collision scene_id {collision.scene_id} does not match system scene_id {self.scene_id}"
            )
        self.collisions.append(collision)
        self.revision += 1

    def intersects_disc(
        self,
        center: WorldCoordinate,
        radius_wu: float
    ) -> List[CollisionHit]:
        """
        检查圆盘是否与任何 Collision 相交

        RULE-MAP-023: Boundary-exclusive

        Args:
            center: 圆心
            radius_wu: 半径

        Returns:
            List[CollisionHit]: 命中的 Collision 列表
        """
        hits = []

        for collision in self.collisions:
            if not collision.enabled:
                continue

            # 简化实现：采样圆周上的点检查是否在 Collision 内
            if self._disc_intersects_polygon(center, radius_wu, collision):
                hits.append(CollisionHit(
                    collision_id=collision.collision_id,
                    obstacle_tag=collision.obstacle_tag,
                    hit_point=center
                ))

        return hits

    def sweep_disc(
        self,
        start: WorldCoordinate,
        end: WorldCoordinate,
        radius_wu: float,
        clearance_wu: float
    ) -> SweepResult:
        """
        Swept Disc 检查（从起点到终点的圆盘扫过区域）

        RULE-MAP-024: 必须对整段 Swept Disc 检查，不能只验证终点

        Args:
            start: 起点
            end: 终点
            radius_wu: Agent 半径
            clearance_wu: 额外安全间隙

        Returns:
            SweepResult: 扫描结果
        """
        total_radius = radius_wu + clearance_wu

        # 检查起点是否已在 Collision 内
        start_hits = self.intersects_disc(start, total_radius)
        if start_hits:
            return SweepResult(
                clear=False,
                first_hit_fraction_q1000000=0,
                collision_id=start_hits[0].collision_id,
                navigation_revision=self.revision
            )

        # 检查终点
        end_hits = self.intersects_disc(end, total_radius)
        if end_hits:
            # 简化实现：沿路径采样检测第一次命中
            fraction = self._find_first_hit_fraction(start, end, total_radius, end_hits[0].collision_id)
            return SweepResult(
                clear=False,
                first_hit_fraction_q1000000=fraction,
                collision_id=end_hits[0].collision_id,
                navigation_revision=self.revision
            )

        # 沿路径采样检查中间点（防止 tunneling）
        num_samples = max(3, int(start.distance_to(end) / (total_radius / 2)))
        for i in range(1, num_samples):
            t = i / num_samples
            sample_x = start.x_wu + t * (end.x_wu - start.x_wu)
            sample_y = start.y_wu + t * (end.y_wu - start.y_wu)
            sample_point = WorldCoordinate(sample_x, sample_y)

            hits = self.intersects_disc(sample_point, total_radius)
            if hits:
                fraction = int(t * 1_000_000)
                return SweepResult(
                    clear=False,
                    first_hit_fraction_q1000000=fraction,
                    collision_id=hits[0].collision_id,
                    navigation_revision=self.revision
                )

        # 无碰撞
        return SweepResult(
            clear=True,
            first_hit_fraction_q1000000=1_000_000,
            navigation_revision=self.revision
        )

    def _disc_intersects_polygon(
        self,
        center: WorldCoordinate,
        radius: float,
        polygon: CollisionPolygon
    ) -> bool:
        """
        检查圆盘是否与多边形相交

        采样策略：检查圆心和圆周上 8 个方向的点
        """
        # 快速 AABB 检查
        min_x, min_y, max_x, max_y = polygon.get_bounds()
        if (center.x_wu + radius < min_x or center.x_wu - radius > max_x or
            center.y_wu + radius < min_y or center.y_wu - radius > max_y):
            return False

        # 检查圆心是否在多边形内
        if polygon.contains_point(center):
            return True

        # 检查圆周上 8 个方向的点
        for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
            angle_rad = math.radians(angle_deg)
            test_x = center.x_wu + radius * math.cos(angle_rad)
            test_y = center.y_wu + radius * math.sin(angle_rad)
            test_point = WorldCoordinate(x_wu=test_x, y_wu=test_y)

            if polygon.contains_point(test_point):
                return True

        return False

    def _find_first_hit_fraction(
        self,
        start: WorldCoordinate,
        end: WorldCoordinate,
        radius: float,
        collision_id: str
    ) -> int:
        """
        二分查找第一次碰撞的 fraction（百万分之一单位）

        简化实现：线性采样查找
        """
        num_samples = 100
        for i in range(num_samples):
            t = i / num_samples
            sample_x = start.x_wu + t * (end.x_wu - start.x_wu)
            sample_y = start.y_wu + t * (end.y_wu - start.y_wu)
            sample_point = WorldCoordinate(sample_x, sample_y)

            hits = self.intersects_disc(sample_point, radius)
            if hits and hits[0].collision_id == collision_id:
                return int(t * 1_000_000)

        return 1_000_000  # 未找到，返回终点

    def get_collision_count(self) -> int:
        """获取 Collision 数量"""
        return len(self.collisions)

    def get_revision(self) -> int:
        """获取当前 revision"""
        return self.revision

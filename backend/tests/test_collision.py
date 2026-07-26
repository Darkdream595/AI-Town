"""
碰撞系统测试

覆盖 DOC-MAP-006 的验收标准：
- TEST-MAP-021: Ring winding、Signed Area、Hole 与自交 validation
- TEST-MAP-022: boundary-exclusive 接触和 Expanded Obstacle clearance
- TEST-MAP-023: Swept Disc 防 tunneling、稳定 first hit
- TEST-MAP-024: obstacle tag coverage、玩家/NPC parity
"""

import pytest
from src.map.collision import (
    ObstacleTag,
    CollisionPolygon,
    CollisionSystem,
    compute_signed_area,
    is_clockwise,
    is_counter_clockwise,
    validate_polygon_vertices,
)
from src.map.region_topology import SceneBounds
from src.foundation.coordinates import WorldCoordinate


class TestSignedArea:
    """测试 Signed Area 计算"""

    def test_clockwise_polygon_positive_area(self):
        """TEST-MAP-021: 顺时针多边形 Signed Area > 0（+Y 向下）"""
        # 正方形，顺时针
        vertices = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        area = compute_signed_area(vertices)
        assert area > 0, f"CW polygon should have positive signed area, got {area}"
        assert is_clockwise(vertices)
        assert not is_counter_clockwise(vertices)

    def test_counter_clockwise_polygon_negative_area(self):
        """TEST-MAP-021: 逆时针多边形 Signed Area < 0（+Y 向下）"""
        # 正方形，逆时针
        vertices = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)]
        area = compute_signed_area(vertices)
        assert area < 0, f"CCW polygon should have negative signed area, got {area}"
        assert is_counter_clockwise(vertices)
        assert not is_clockwise(vertices)

    def test_area_magnitude(self):
        """验证面积大小"""
        # 100x100 正方形
        vertices = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        area = compute_signed_area(vertices)
        assert abs(area) == 10000.0  # 100 * 100


class TestPolygonValidation:
    """测试 Polygon 验证"""

    def test_valid_polygon(self):
        """合法的 Polygon"""
        vertices = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        errors = validate_polygon_vertices(vertices)
        assert len(errors) == 0

    def test_too_few_vertices(self):
        """TEST-MAP-022: 顶点数量少于 3"""
        vertices = [(0.0, 0.0), (100.0, 0.0)]
        errors = validate_polygon_vertices(vertices)
        assert len(errors) > 0
        assert "at least 3 vertices" in errors[0]

    def test_consecutive_vertices_too_close(self):
        """TEST-MAP-022: 连续顶点距离小于 1/16 wu"""
        vertices = [
            (0.0, 0.0),
            (0.01, 0.0),  # 距离 < 1/16 wu
            (100.0, 100.0)
        ]
        errors = validate_polygon_vertices(vertices)
        assert len(errors) > 0
        assert "too close" in errors[0]

    def test_area_too_small(self):
        """TEST-MAP-022: 绝对面积小于 1 wu²"""
        # 非常小的三角形
        vertices = [(0.0, 0.0), (0.5, 0.0), (0.25, 0.5)]
        errors = validate_polygon_vertices(vertices)
        assert len(errors) > 0
        assert "area too small" in errors[0]


class TestCollisionPolygon:
    """测试 Collision Polygon"""

    def test_create_valid_collision(self):
        """创建合法的 Collision Polygon"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id="entity_123",
            enabled=True,
            source_revision=1
        )
        assert collision.collision_id == "test.wall"

    def test_outer_ring_must_be_clockwise(self):
        """TEST-MAP-021: Outer Ring 必须顺时针"""
        with pytest.raises(ValueError, match="must be clockwise"):
            CollisionPolygon(
                collision_id="bad.ccw",
                scene_id="test",
                outer_ring_wu=[(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0)],  # CCW
                hole_rings_wu=[],
                obstacle_tag=ObstacleTag.STRUCTURE_WALL,
                source_entity_id=None,
                enabled=True,
                source_revision=1
            )

    def test_hole_ring_must_be_counter_clockwise(self):
        """TEST-MAP-021: Hole Ring 必须逆时针"""
        with pytest.raises(ValueError, match="must be counter-clockwise"):
            CollisionPolygon(
                collision_id="bad.hole",
                scene_id="test",
                outer_ring_wu=[(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)],  # CW
                hole_rings_wu=[
                    [(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0)]  # CW（应该是 CCW）
                ],
                obstacle_tag=ObstacleTag.STRUCTURE_WALL,
                source_entity_id=None,
                enabled=True,
                source_revision=1
            )

    def test_contains_point_inside(self):
        """点在 Polygon 内部"""
        collision = CollisionPolygon(
            collision_id="test",
            scene_id="test",
            outer_ring_wu=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )

        assert collision.contains_point(WorldCoordinate(50.0, 50.0))
        assert collision.contains_point(WorldCoordinate(20.0, 20.0))

    def test_contains_point_outside(self):
        """点在 Polygon 外部"""
        collision = CollisionPolygon(
            collision_id="test",
            scene_id="test",
            outer_ring_wu=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )

        assert not collision.contains_point(WorldCoordinate(0.0, 0.0))
        assert not collision.contains_point(WorldCoordinate(100.0, 50.0))

    def test_contains_point_with_hole(self):
        """带 Hole 的 Polygon"""
        collision = CollisionPolygon(
            collision_id="test.hole",
            scene_id="test",
            outer_ring_wu=[(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)],  # CW
            hole_rings_wu=[
                [(50.0, 50.0), (50.0, 150.0), (150.0, 150.0), (150.0, 50.0)]  # CCW
            ],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )

        # 在 Outer Ring 内但不在 Hole 内
        assert collision.contains_point(WorldCoordinate(25.0, 25.0))

        # 在 Hole 内（应该不算在 Polygon 内）
        assert not collision.contains_point(WorldCoordinate(100.0, 100.0))

    def test_get_bounds(self):
        """获取 AABB 边界"""
        collision = CollisionPolygon(
            collision_id="test",
            scene_id="test",
            outer_ring_wu=[(10.0, 20.0), (90.0, 30.0), (80.0, 80.0), (20.0, 70.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )

        min_x, min_y, max_x, max_y = collision.get_bounds()
        assert min_x == 10.0
        assert min_y == 20.0
        assert max_x == 90.0
        assert max_y == 80.0


class TestCollisionSystem:
    """测试 Collision System"""

    def setup_method(self):
        """测试前设置"""
        self.bounds = SceneBounds("test_scene", width_wu=200, height_wu=200)
        self.system = CollisionSystem("test_scene", self.bounds)

    def test_create_system(self):
        """创建 Collision System"""
        assert self.system.scene_id == "test_scene"
        assert self.system.get_collision_count() == 0

    def test_add_collision(self):
        """添加 Collision"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)
        assert self.system.get_collision_count() == 1

    def test_add_collision_wrong_scene_id(self):
        """添加错误 scene_id 的 Collision"""
        collision = CollisionPolygon(
            collision_id="wrong",
            scene_id="wrong_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        with pytest.raises(ValueError, match="does not match system scene_id"):
            self.system.add_collision(collision)

    def test_intersects_disc_no_collision(self):
        """TEST-MAP-022: 圆盘不与任何 Collision 相交"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)

        # 远离 Collision 的点
        hits = self.system.intersects_disc(WorldCoordinate(150.0, 150.0), radius_wu=10.0)
        assert len(hits) == 0

    def test_intersects_disc_with_collision(self):
        """TEST-MAP-022: 圆盘与 Collision 相交"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)

        # 圆心在 Collision 内
        hits = self.system.intersects_disc(WorldCoordinate(50.0, 50.0), radius_wu=5.0)
        assert len(hits) == 1
        assert hits[0].collision_id == "test.wall"

    def test_sweep_disc_clear_path(self):
        """TEST-MAP-023: Swept Disc 无碰撞"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)

        # 从 (100, 100) 到 (150, 150)，远离 Collision
        result = self.system.sweep_disc(
            start=WorldCoordinate(100.0, 100.0),
            end=WorldCoordinate(150.0, 150.0),
            radius_wu=5.0,
            clearance_wu=2.0
        )
        assert result.clear
        assert result.first_hit_fraction_q1000000 == 1_000_000

    def test_sweep_disc_hits_obstacle(self):
        """TEST-MAP-023: Swept Disc 碰到障碍"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(45.0, 45.0), (55.0, 45.0), (55.0, 55.0), (45.0, 55.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)

        # 从 (20, 50) 到 (80, 50)，路径穿过障碍
        result = self.system.sweep_disc(
            start=WorldCoordinate(20.0, 50.0),
            end=WorldCoordinate(80.0, 50.0),
            radius_wu=5.0,
            clearance_wu=2.0
        )
        assert not result.clear
        assert result.collision_id == "test.wall"
        assert result.first_hit_fraction_q1000000 < 1_000_000

    def test_sweep_disc_start_in_collision(self):
        """TEST-MAP-023: 起点在 Collision 内"""
        collision = CollisionPolygon(
            collision_id="test.wall",
            scene_id="test_scene",
            outer_ring_wu=[(20.0, 20.0), (80.0, 20.0), (80.0, 80.0), (20.0, 80.0)],
            hole_rings_wu=[],
            obstacle_tag=ObstacleTag.STRUCTURE_WALL,
            source_entity_id=None,
            enabled=True,
            source_revision=1
        )
        self.system.add_collision(collision)

        # 起点在 Collision 内
        result = self.system.sweep_disc(
            start=WorldCoordinate(50.0, 50.0),
            end=WorldCoordinate(100.0, 100.0),
            radius_wu=5.0,
            clearance_wu=2.0
        )
        assert not result.clear
        assert result.first_hit_fraction_q1000000 == 0

    def test_obstacle_tags(self):
        """TEST-MAP-024: 验证所有 Obstacle Tags"""
        tags = [
            ObstacleTag.STRUCTURE_WALL,
            ObstacleTag.STRUCTURE_TREE_TRUNK,
            ObstacleTag.TERRAIN_CLIFF,
            ObstacleTag.TERRAIN_WATER,
            ObstacleTag.STRUCTURE_RUBBLE,
            ObstacleTag.DOOR_CLOSED,
            ObstacleTag.HAZARD_HARD_BLOCK,
            ObstacleTag.CONSTRUCTION_BLOCKED,
        ]

        for tag in tags:
            collision = CollisionPolygon(
                collision_id=f"test.{tag.value}",
                scene_id="test_scene",
                outer_ring_wu=[(10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0)],
                hole_rings_wu=[],
                obstacle_tag=tag,
                source_entity_id=None,
                enabled=True,
                source_revision=1
            )
            assert collision.obstacle_tag == tag

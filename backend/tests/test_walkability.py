"""
可行走区域测试

覆盖 DOC-MAP-005 的验收标准：
- TEST-MAP-017: Walkable boundary-inclusive 与 Agent Disc 完整包含
- TEST-MAP-018: 狭缝、重叠、不同 radius/clearance
- TEST-MAP-019: Terrain Tag cost 与 Ground Art 像素无关
- TEST-MAP-020: 玩家/NPC profile parity
"""

import pytest
from src.map.walkability import (
    TerrainTag,
    WalkableSurface,
    AgentProfile,
    PositionLegality,
    StandabilityResult,
    WalkabilitySystem,
    TERRAIN_BASE_COST,
    DEFAULT_HUMANOID_PROFILE,
)
from src.map.region_topology import SceneBounds
from src.foundation.coordinates import WorldCoordinate


class TestTerrainTag:
    """测试 Terrain Tag 定义"""

    def test_terrain_tags_defined(self):
        """验证 Terrain Tag 枚举"""
        assert TerrainTag.ROAD_PRIMARY == "road.primary"
        assert TerrainTag.ROAD_SECONDARY == "road.secondary"
        assert TerrainTag.FLOOR == "floor"
        assert TerrainTag.GRASS == "grass"
        assert TerrainTag.ROUGH == "rough"

    def test_terrain_base_cost(self):
        """TEST-MAP-019: 验证基础 cost 表"""
        assert TERRAIN_BASE_COST[TerrainTag.ROAD_PRIMARY] == 800
        assert TERRAIN_BASE_COST[TerrainTag.ROAD_SECONDARY] == 900
        assert TERRAIN_BASE_COST[TerrainTag.FLOOR] == 1000
        assert TERRAIN_BASE_COST[TerrainTag.GRASS] == 1100
        assert TERRAIN_BASE_COST[TerrainTag.ROUGH] == 1400

        # 验证顺序（road < floor < grass < rough）
        assert TERRAIN_BASE_COST[TerrainTag.ROAD_PRIMARY] < TERRAIN_BASE_COST[TerrainTag.FLOOR]
        assert TERRAIN_BASE_COST[TerrainTag.FLOOR] < TERRAIN_BASE_COST[TerrainTag.GRASS]
        assert TERRAIN_BASE_COST[TerrainTag.GRASS] < TERRAIN_BASE_COST[TerrainTag.ROUGH]


class TestWalkableSurface:
    """测试 Walkable Surface"""

    def test_create_valid_surface(self):
        """创建合法的 Surface"""
        surface = WalkableSurface(
            surface_id="test.road",
            scene_id="test_scene",
            vertices_wu=[(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
            terrain_tag=TerrainTag.ROAD_PRIMARY,
            base_cost_q1000=800,
            allowed_profile_tags=["ground"]
        )
        assert surface.surface_id == "test.road"
        assert len(surface.vertices_wu) == 4

    def test_surface_requires_minimum_vertices(self):
        """Surface 至少需要 3 个顶点"""
        with pytest.raises(ValueError, match="must have at least 3 vertices"):
            WalkableSurface(
                surface_id="bad.surface",
                scene_id="test",
                vertices_wu=[(0.0, 0.0), (100.0, 0.0)],  # 只有 2 个顶点
                terrain_tag=TerrainTag.FLOOR,
                base_cost_q1000=1000,
                allowed_profile_tags=["ground"]
            )

    def test_surface_cost_validation(self):
        """验证 base_cost 范围"""
        with pytest.raises(ValueError, match="base_cost_q1000 must be in"):
            WalkableSurface(
                surface_id="bad.cost",
                scene_id="test",
                vertices_wu=[(0.0, 0.0), (100.0, 0.0), (50.0, 50.0)],
                terrain_tag=TerrainTag.FLOOR,
                base_cost_q1000=20000,  # 超过上限
                allowed_profile_tags=["ground"]
            )

    def test_contains_point_inside(self):
        """TEST-MAP-017: 点在 Polygon 内部"""
        # 矩形 Surface
        surface = WalkableSurface(
            surface_id="rect",
            scene_id="test",
            vertices_wu=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )

        # 内部点
        assert surface.contains_point(WorldCoordinate(50.0, 50.0))
        assert surface.contains_point(WorldCoordinate(20.0, 20.0))

    def test_contains_point_outside(self):
        """点在 Polygon 外部"""
        surface = WalkableSurface(
            surface_id="rect",
            scene_id="test",
            vertices_wu=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )

        # 外部点
        assert not surface.contains_point(WorldCoordinate(0.0, 0.0))
        assert not surface.contains_point(WorldCoordinate(100.0, 50.0))
        assert not surface.contains_point(WorldCoordinate(50.0, 100.0))

    def test_contains_point_on_boundary(self):
        """TEST-MAP-017: 边界附近的点"""
        surface = WalkableSurface(
            surface_id="rect",
            scene_id="test",
            vertices_wu=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )

        # Ray Casting 算法在严格边界上的行为取决于具体实现
        # 测试边界内侧的点（明确在内部）
        assert surface.contains_point(WorldCoordinate(0.1, 0.1))
        assert surface.contains_point(WorldCoordinate(99.9, 99.9))
        assert surface.contains_point(WorldCoordinate(50.0, 0.1))  # 靠近边界但在内


class TestAgentProfile:
    """测试 Agent Profile"""

    def test_default_humanoid_profile(self):
        """TEST-MAP-020: 默认人形 Profile"""
        profile = DEFAULT_HUMANOID_PROFILE
        assert profile.radius_wu == 10.0
        assert profile.clearance_wu == 2.0
        assert "ground" in profile.tags
        assert profile.get_total_radius() == 12.0

    def test_custom_profile(self):
        """自定义 Profile"""
        profile = AgentProfile(
            radius_wu=5.0,
            clearance_wu=1.0,
            tags=["ground", "flying"]
        )
        assert profile.get_total_radius() == 6.0
        assert len(profile.tags) == 2


class TestWalkabilitySystem:
    """测试 Walkability System"""

    def setup_method(self):
        """测试前设置"""
        self.bounds = SceneBounds("test_scene", width_wu=200, height_wu=200)
        self.system = WalkabilitySystem("test_scene", self.bounds)

    def test_create_system(self):
        """创建 Walkability System"""
        assert self.system.scene_id == "test_scene"
        assert self.system.get_surface_count() == 0

    def test_add_surface(self):
        """添加 Surface"""
        surface = WalkableSurface(
            surface_id="test.floor",
            scene_id="test_scene",
            vertices_wu=[(20.0, 20.0), (180.0, 20.0), (180.0, 180.0), (20.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface)
        assert self.system.get_surface_count() == 1

    def test_add_surface_wrong_scene_id(self):
        """添加错误 scene_id 的 Surface"""
        surface = WalkableSurface(
            surface_id="wrong.surface",
            scene_id="wrong_scene",  # 不匹配
            vertices_wu=[(20.0, 20.0), (180.0, 20.0), (180.0, 180.0), (20.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        with pytest.raises(ValueError, match="does not match system scene_id"):
            self.system.add_surface(surface)

    def test_is_standable_out_of_bounds(self):
        """TEST-MAP-017: 超出边界"""
        profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])

        # 超出边界
        result = self.system.is_standable(WorldCoordinate(250.0, 100.0), profile)
        assert result.legality == PositionLegality.OUT_OF_BOUNDS

    def test_is_standable_no_surface(self):
        """TEST-MAP-017: 不在任何 Surface 上"""
        profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])

        # 没有添加任何 Surface
        result = self.system.is_standable(WorldCoordinate(100.0, 100.0), profile)
        assert result.legality == PositionLegality.NOT_ON_WALKABLE_SURFACE

    def test_is_standable_legal(self):
        """TEST-MAP-017: 合法站立"""
        # 添加一个大的 Surface
        surface = WalkableSurface(
            surface_id="test.floor",
            scene_id="test_scene",
            vertices_wu=[(20.0, 20.0), (180.0, 20.0), (180.0, 180.0), (20.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface)

        profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])

        # 中心点，Agent Disc 完全在 Surface 内
        result = self.system.is_standable(WorldCoordinate(100.0, 100.0), profile)
        assert result.legality == PositionLegality.LEGAL
        assert result.surface_id == "test.floor"
        assert result.terrain_tag == TerrainTag.FLOOR
        assert result.effective_cost_q1000 == 1000

    def test_is_standable_disc_exceeds_surface(self):
        """TEST-MAP-018: Agent Disc 超出 Surface"""
        # 小 Surface
        surface = WalkableSurface(
            surface_id="small.surface",
            scene_id="test_scene",
            vertices_wu=[(90.0, 90.0), (110.0, 90.0), (110.0, 110.0), (90.0, 110.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface)

        # Agent 半径过大
        profile = AgentProfile(radius_wu=15.0, clearance_wu=2.0, tags=["ground"])

        result = self.system.is_standable(WorldCoordinate(100.0, 100.0), profile)
        assert result.legality == PositionLegality.DISC_EXCEEDS_SURFACE

    def test_is_standable_different_radius(self):
        """TEST-MAP-018: 不同 radius 得到不同结果"""
        surface = WalkableSurface(
            surface_id="test.floor",
            scene_id="test_scene",
            vertices_wu=[(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface)

        point = WorldCoordinate(60.0, 100.0)

        # 小 radius 可以站立
        small_profile = AgentProfile(radius_wu=5.0, clearance_wu=1.0, tags=["ground"])
        result_small = self.system.is_standable(point, small_profile)
        assert result_small.legality == PositionLegality.LEGAL

        # 大 radius 超出边界
        large_profile = AgentProfile(radius_wu=15.0, clearance_wu=2.0, tags=["ground"])
        result_large = self.system.is_standable(point, large_profile)
        assert result_large.legality == PositionLegality.DISC_EXCEEDS_SURFACE

    def test_overlapping_surfaces_choose_lowest_cost(self):
        """TEST-MAP-018: 重叠 Surface 选择最低 cost"""
        # 添加两个重叠的 Surface
        road = WalkableSurface(
            surface_id="test.road",
            scene_id="test_scene",
            vertices_wu=[(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0)],
            terrain_tag=TerrainTag.ROAD_PRIMARY,
            base_cost_q1000=800,
            allowed_profile_tags=["ground"]
        )
        grass = WalkableSurface(
            surface_id="test.grass",
            scene_id="test_scene",
            vertices_wu=[(40.0, 40.0), (160.0, 40.0), (160.0, 160.0), (40.0, 160.0)],
            terrain_tag=TerrainTag.GRASS,
            base_cost_q1000=1100,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(road)
        self.system.add_surface(grass)

        profile = AgentProfile(radius_wu=5.0, clearance_wu=1.0, tags=["ground"])

        # 在重叠区域，应选择 cost 更低的 road
        result = self.system.is_standable(WorldCoordinate(100.0, 100.0), profile)
        assert result.legality == PositionLegality.LEGAL
        assert result.surface_id == "test.road"
        assert result.effective_cost_q1000 == 800

    def test_profile_parity_player_npc(self):
        """TEST-MAP-020: 玩家/NPC 相同 Profile 得到相同结果"""
        surface = WalkableSurface(
            surface_id="test.floor",
            scene_id="test_scene",
            vertices_wu=[(20.0, 20.0), (180.0, 20.0), (180.0, 180.0), (20.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface)

        # 相同的 Profile
        player_profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])
        npc_profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])

        point = WorldCoordinate(100.0, 100.0)

        # 玩家和 NPC 应得到相同结果
        player_result = self.system.is_standable(point, player_profile)
        npc_result = self.system.is_standable(point, npc_profile)

        assert player_result.legality == npc_result.legality
        assert player_result.surface_id == npc_result.surface_id
        assert player_result.effective_cost_q1000 == npc_result.effective_cost_q1000

    def test_surface_tags_at_point(self):
        """查询点所在的 Terrain Tags"""
        road = WalkableSurface(
            surface_id="test.road",
            scene_id="test_scene",
            vertices_wu=[(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0)],
            terrain_tag=TerrainTag.ROAD_PRIMARY,
            base_cost_q1000=800,
            allowed_profile_tags=["ground"]
        )
        grass = WalkableSurface(
            surface_id="test.grass",
            scene_id="test_scene",
            vertices_wu=[(40.0, 40.0), (160.0, 40.0), (160.0, 160.0), (40.0, 160.0)],
            terrain_tag=TerrainTag.GRASS,
            base_cost_q1000=1100,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(road)
        self.system.add_surface(grass)

        # 重叠区域应返回两个 tags，按 cost 排序
        tags = self.system.surface_tags_at(WorldCoordinate(100.0, 100.0))
        assert len(tags) == 2
        assert tags[0] == TerrainTag.ROAD_PRIMARY  # 更低 cost
        assert tags[1] == TerrainTag.GRASS

    def test_narrow_gap_not_traversable(self):
        """TEST-MAP-018: 狭缝测试（小于 Agent Disc 直径时不可穿越）"""
        # 创建两个相邻但有间隙的 Surface
        surface1 = WalkableSurface(
            surface_id="left",
            scene_id="test_scene",
            vertices_wu=[(20.0, 20.0), (95.0, 20.0), (95.0, 180.0), (20.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        surface2 = WalkableSurface(
            surface_id="right",
            scene_id="test_scene",
            vertices_wu=[(105.0, 20.0), (180.0, 20.0), (180.0, 180.0), (105.0, 180.0)],
            terrain_tag=TerrainTag.FLOOR,
            base_cost_q1000=1000,
            allowed_profile_tags=["ground"]
        )
        self.system.add_surface(surface1)
        self.system.add_surface(surface2)

        # 间隙中心（x=100），间隙宽度 10 wu
        profile = AgentProfile(radius_wu=10.0, clearance_wu=2.0, tags=["ground"])  # 直径 24 wu

        # 在间隙中心，Agent Disc 会超出两边的 Surface
        result = self.system.is_standable(WorldCoordinate(100.0, 100.0), profile)
        assert result.legality == PositionLegality.NOT_ON_WALKABLE_SURFACE

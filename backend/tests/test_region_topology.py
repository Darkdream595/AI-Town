"""
区域拓扑测试

覆盖 DOC-MAP-002 的验收标准：
- TEST-MAP-005: Region、SemanticNode、Anchor 坐标
- TEST-MAP-006: Exit pair 验证
- TEST-MAP-007: Region graph 弱连通性
"""

import pytest
from src.map.region_topology import (
    SceneBounds,
    SemanticNodeKind,
    SemanticNode,
    WorldPoint,
    ProfileConstraints,
    ReachabilityPolicy,
    RegionTopology,
    REGION_SCENE_IDS,
    REGION_BOUNDS,
    validate_exit_pairs,
)
from src.foundation.coordinates import WorldCoordinate


class TestSceneBounds:
    """测试 Scene Bounds"""

    def test_region_bounds_defined(self):
        """TEST-MAP-005: 验证三个 Region 的 Bounds 定义"""
        # RULE-MAP-005: 恰好三个 Region
        assert len(REGION_SCENE_IDS) == 3
        assert len(REGION_BOUNDS) == 3

        # RULE-MAP-006: 固定尺寸
        crown_creek = REGION_BOUNDS["region.crown_creek_town"]
        assert crown_creek.width_wu == 4096
        assert crown_creek.height_wu == 4096

        twilight_forest = REGION_BOUNDS["region.twilight_whisper_forest"]
        assert twilight_forest.width_wu == 4096
        assert twilight_forest.height_wu == 4096

        silver_ash = REGION_BOUNDS["region.silver_ash_mine"]
        assert silver_ash.width_wu == 3072
        assert silver_ash.height_wu == 3072

    def test_contains_half_open_interval(self):
        """TEST-MAP-001: 半开区间边界检查"""
        bounds = SceneBounds("test", width_wu=100, height_wu=100)

        # 内部点
        assert bounds.contains(WorldCoordinate(50, 50))
        assert bounds.contains(WorldCoordinate(0, 0))  # 左上角包含

        # 边界上（右下边界不包含）
        assert not bounds.contains(WorldCoordinate(100, 50))  # 右边界
        assert not bounds.contains(WorldCoordinate(50, 100))  # 下边界
        assert not bounds.contains(WorldCoordinate(100, 100))  # 右下角

        # 外部点
        assert not bounds.contains(WorldCoordinate(-1, 50))
        assert not bounds.contains(WorldCoordinate(50, -1))

    def test_contains_with_radius(self):
        """TEST-MAP-002: 带半径的边界检查（Agent Disc）"""
        bounds = SceneBounds("test", width_wu=100, height_wu=100)

        # 圆心在内，圆盘也在内
        assert bounds.contains_with_radius(WorldCoordinate(50, 50), radius_wu=10)

        # 圆心在内，但圆盘超出边界
        assert not bounds.contains_with_radius(WorldCoordinate(5, 50), radius_wu=10)  # 左边超出
        assert not bounds.contains_with_radius(WorldCoordinate(95, 50), radius_wu=10)  # 右边超出
        assert not bounds.contains_with_radius(WorldCoordinate(50, 5), radius_wu=10)  # 上边超出
        assert not bounds.contains_with_radius(WorldCoordinate(50, 95), radius_wu=10)  # 下边超出


class TestSemanticNode:
    """测试 Semantic Node 结构验证"""

    def test_anchor_node_structure(self):
        """TEST-MAP-005: Anchor 节点结构验证"""
        # 正确的 Anchor
        anchor = SemanticNode(
            id="test.anchor",
            kind=SemanticNodeKind.ANCHOR,
            scene_id="test_scene",
            point=WorldPoint("test_scene", 100.0, 100.0),
            approach_point=None,
            arrival_point=None,
            arrival_fallback_points=[],
            pair_node_id=None,
            target_scene_id=None,
            target_arrival_point=None,
            profile_constraints=ProfileConstraints(
                required_tags=["ground"],
                max_radius_wu=16.0,
                min_clearance_wu=2.0
            ),
            enabled=True,
            reachability_policy=ReachabilityPolicy.REQUIRED,
            availability_condition_id=None
        )
        assert anchor.kind == SemanticNodeKind.ANCHOR

    def test_anchor_must_not_have_exit_fields(self):
        """Anchor 不能有 Exit 专属字段"""
        with pytest.raises(ValueError, match="approach_point must be None"):
            SemanticNode(
                id="bad.anchor",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="test",
                point=WorldPoint("test", 100.0, 100.0),
                approach_point=WorldPoint("test", 90.0, 100.0),  # 不允许
                arrival_point=None,
                arrival_fallback_points=[],
                pair_node_id=None,
                target_scene_id=None,
                target_arrival_point=None,
                profile_constraints=ProfileConstraints(["ground"], 16.0, 2.0),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            )

    def test_exit_node_structure(self):
        """TEST-MAP-006: Exit 节点结构验证"""
        exit_node = SemanticNode(
            id="test.exit",
            kind=SemanticNodeKind.EXIT,
            scene_id="scene_a",
            point=WorldPoint("scene_a", 100.0, 100.0),
            approach_point=WorldPoint("scene_a", 90.0, 100.0),
            arrival_point=WorldPoint("scene_a", 95.0, 100.0),
            arrival_fallback_points=[],
            pair_node_id="test.exit.pair",
            target_scene_id="scene_b",
            target_arrival_point=WorldPoint("scene_b", 200.0, 200.0),
            profile_constraints=ProfileConstraints(["ground"], 16.0, 2.0),
            enabled=True,
            reachability_policy=ReachabilityPolicy.REQUIRED,
            availability_condition_id=None
        )
        assert exit_node.kind == SemanticNodeKind.EXIT

    def test_exit_must_have_all_required_fields(self):
        """Exit 必须有所有必需字段"""
        with pytest.raises(ValueError, match="approach_point must not be None"):
            SemanticNode(
                id="bad.exit",
                kind=SemanticNodeKind.EXIT,
                scene_id="test",
                point=WorldPoint("test", 100.0, 100.0),
                approach_point=None,  # 不允许为 None
                arrival_point=WorldPoint("test", 95.0, 100.0),
                arrival_fallback_points=[],
                pair_node_id="pair",
                target_scene_id="other",
                target_arrival_point=WorldPoint("other", 200.0, 200.0),
                profile_constraints=ProfileConstraints(["ground"], 16.0, 2.0),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            )

    def test_required_node_must_be_enabled(self):
        """RULE-MAP-008: Required Node 必须 enabled"""
        with pytest.raises(ValueError, match="Required node must be enabled"):
            SemanticNode(
                id="bad.required",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="test",
                point=WorldPoint("test", 100.0, 100.0),
                approach_point=None,
                arrival_point=None,
                arrival_fallback_points=[],
                pair_node_id=None,
                target_scene_id=None,
                target_arrival_point=None,
                profile_constraints=ProfileConstraints(["ground"], 16.0, 2.0),
                enabled=False,  # Required 但 disabled
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            )

    def test_scene_id_consistency(self):
        """验证 scene_id 一致性"""
        with pytest.raises(ValueError, match="point.scene_id must match node scene_id"):
            SemanticNode(
                id="bad.scene_id",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="scene_a",
                point=WorldPoint("scene_b", 100.0, 100.0),  # scene_id 不匹配
                approach_point=None,
                arrival_point=None,
                arrival_fallback_points=[],
                pair_node_id=None,
                target_scene_id=None,
                target_arrival_point=None,
                profile_constraints=ProfileConstraints(["ground"], 16.0, 2.0),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            )


class TestRegionTopology:
    """测试 Region Topology 系统"""

    def test_default_topology_loaded(self):
        """TEST-MAP-005: 默认 topology 加载"""
        topology = RegionTopology()

        # 验证 schema version
        assert topology.semantic_schema_version == 1

        # 验证节点数量（3 个 Anchor + 4 个 Exit）
        assert len(topology.nodes) == 7

        # 验证 Anchor 数量
        anchors = topology.get_anchors()
        assert len(anchors) == 3

        # 验证 Exit 数量
        exits = topology.get_exits()
        assert len(exits) == 4

    def test_anchor_coordinates(self):
        """TEST-MAP-005: 验证 Anchor 坐标"""
        topology = RegionTopology()

        # Crown Creek Town Anchor
        crown_anchor = topology.get_node("semantic_anchor.crown_creek.crown_square")
        assert crown_anchor is not None
        assert crown_anchor.point.x_wu == 2048.0
        assert crown_anchor.point.y_wu == 2048.0
        assert crown_anchor.scene_id == "region.crown_creek_town"

        # Twilight Whisper Forest Anchor
        forest_anchor = topology.get_node("semantic_anchor.twilight_whisper.oathkeeper_camp")
        assert forest_anchor is not None
        assert forest_anchor.point.x_wu == 2048.0
        assert forest_anchor.point.y_wu == 3584.0

        # Silver Ash Mine Anchor
        mine_anchor = topology.get_node("semantic_anchor.silver_ash.entry_shed")
        assert mine_anchor is not None
        assert mine_anchor.point.x_wu == 2688.0
        assert mine_anchor.point.y_wu == 1536.0

    def test_get_nodes_by_scene(self):
        """按 Scene 查询节点"""
        topology = RegionTopology()

        crown_nodes = topology.get_nodes_by_scene("region.crown_creek_town")
        # Crown Creek: 1 Anchor + 2 Exits
        assert len(crown_nodes) == 3

        forest_nodes = topology.get_nodes_by_scene("region.twilight_whisper_forest")
        # Forest: 1 Anchor + 1 Exit
        assert len(forest_nodes) == 2

        mine_nodes = topology.get_nodes_by_scene("region.silver_ash_mine")
        # Mine: 1 Anchor + 1 Exit
        assert len(mine_nodes) == 2


class TestExitPairValidation:
    """测试 Exit Pair 验证"""

    def test_default_exit_pairs_valid(self):
        """TEST-MAP-006: 默认 Exit pairs 验证通过"""
        topology = RegionTopology()
        errors = validate_exit_pairs(topology)

        # 应该没有错误
        assert len(errors) == 0

    def test_exit_pair_consistency(self):
        """TEST-MAP-006: 验证 Exit pair 的四方向一致性"""
        topology = RegionTopology()

        # Crown Creek -> Forest
        exit_cf = topology.get_node("semantic_exit.crown_creek.north_forest_gate")
        exit_fc = topology.get_node("semantic_exit.twilight_whisper_forest.south_path")

        # 验证双向引用
        assert exit_cf.pair_node_id == exit_fc.id
        assert exit_fc.pair_node_id == exit_cf.id

        # 验证 target_scene_id
        assert exit_cf.target_scene_id == exit_fc.scene_id
        assert exit_fc.target_scene_id == exit_cf.scene_id

        # 验证 target_arrival_point
        assert exit_cf.target_arrival_point == exit_fc.arrival_point
        assert exit_fc.target_arrival_point == exit_cf.arrival_point

    def test_region_graph_connectivity(self):
        """TEST-MAP-007: Region graph 弱连通性"""
        topology = RegionTopology()

        # 构建邻接表
        adjacency = {}
        for exit_node in topology.get_exits():
            source = exit_node.scene_id
            target = exit_node.target_scene_id
            if source not in adjacency:
                adjacency[source] = []
            adjacency[source].append(target)

        # 从 Crown Creek 开始 BFS
        visited = set()
        queue = ["region.crown_creek_town"]
        visited.add("region.crown_creek_town")

        while queue:
            current = queue.pop(0)
            if current in adjacency:
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

        # 验证三个 Region 都可达
        assert len(visited) == 3
        assert "region.crown_creek_town" in visited
        assert "region.twilight_whisper_forest" in visited
        assert "region.silver_ash_mine" in visited

    def test_all_exits_have_valid_pairs(self):
        """验证所有 Exit 都有有效的 pair"""
        topology = RegionTopology()

        for exit_node in topology.get_exits():
            pair_id = exit_node.pair_node_id
            pair_node = topology.get_node(pair_id)

            # pair 必须存在
            assert pair_node is not None, f"Exit {exit_node.id} pair {pair_id} not found"

            # pair 必须是 Exit
            assert pair_node.kind == SemanticNodeKind.EXIT

            # pair 的 pair 必须指回自己
            assert pair_node.pair_node_id == exit_node.id

"""
区域拓扑定义

符合 DOC-MAP-002 规范：
- RULE-MAP-005: 三个固定 Region Scene
- RULE-MAP-006: Region Bounds 固定尺寸
- RULE-MAP-007: Exit 成对验证
- RULE-MAP-008: Required/Conditional Node 规则
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
from ..foundation.coordinates import WorldCoordinate


# ==================== Scene Bounds ====================

@dataclass(frozen=True)
class SceneBounds:
    """
    Scene 边界

    RULE-MAP-002: 半开区间 [0, width_wu) × [0, height_wu)
    """
    scene_id: str
    width_wu: int
    height_wu: int

    def contains(self, point: WorldCoordinate) -> bool:
        """检查点是否在边界内（半开区间）"""
        return (0 <= point.x_wu < self.width_wu and
                0 <= point.y_wu < self.height_wu)

    def contains_with_radius(self, point: WorldCoordinate, radius_wu: float) -> bool:
        """检查以点为圆心、radius_wu 为半径的圆盘是否完全在边界内"""
        return (radius_wu <= point.x_wu < self.width_wu - radius_wu and
                radius_wu <= point.y_wu < self.height_wu - radius_wu)


# ==================== Semantic Nodes ====================

class SemanticNodeKind(str, Enum):
    """语义节点类型"""
    ANCHOR = "anchor"
    EXIT = "exit"


class ReachabilityPolicy(str, Enum):
    """可达性策略"""
    REQUIRED = "required"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class ProfileConstraints:
    """Profile 约束"""
    required_tags: List[str]
    max_radius_wu: float
    min_clearance_wu: float


@dataclass(frozen=True)
class WorldPoint:
    """
    带 scene_id 的世界点

    RULE-MAP-004: 不同 scene_id 的点不得直接测距
    """
    scene_id: str
    x_wu: float
    y_wu: float

    def to_world_coordinate(self) -> WorldCoordinate:
        """转换为 WorldCoordinate（不带 scene_id）"""
        return WorldCoordinate(x_wu=self.x_wu, y_wu=self.y_wu)

    def __eq__(self, other) -> bool:
        """精确比较（用于 Exit pair 验证）"""
        if not isinstance(other, WorldPoint):
            return False
        return (self.scene_id == other.scene_id and
                self.x_wu == other.x_wu and
                self.y_wu == other.y_wu)


@dataclass(frozen=True)
class SemanticNode:
    """
    语义节点（Anchor 或 Exit）

    严格遵循 DOC-MAP-002 的 14 字段契约
    """
    id: str
    kind: SemanticNodeKind
    scene_id: str
    point: WorldPoint
    approach_point: Optional[WorldPoint]
    arrival_point: Optional[WorldPoint]
    arrival_fallback_points: List[WorldPoint]
    pair_node_id: Optional[str]
    target_scene_id: Optional[str]
    target_arrival_point: Optional[WorldPoint]
    profile_constraints: ProfileConstraints
    enabled: bool
    reachability_policy: ReachabilityPolicy
    availability_condition_id: Optional[str]

    def __post_init__(self):
        """验证节点结构的类型一致性"""
        # 验证 point 的 scene_id 匹配
        if self.point.scene_id != self.scene_id:
            raise ValueError(f"Node {self.id}: point.scene_id must match node scene_id")

        if self.kind == SemanticNodeKind.ANCHOR:
            # Anchor 必须满足的约束
            if self.approach_point is not None:
                raise ValueError(f"Anchor {self.id}: approach_point must be None")
            if self.arrival_point is not None:
                raise ValueError(f"Anchor {self.id}: arrival_point must be None")
            if self.pair_node_id is not None:
                raise ValueError(f"Anchor {self.id}: pair_node_id must be None")
            if self.target_scene_id is not None:
                raise ValueError(f"Anchor {self.id}: target_scene_id must be None")
            if self.target_arrival_point is not None:
                raise ValueError(f"Anchor {self.id}: target_arrival_point must be None")
            if len(self.arrival_fallback_points) != 0:
                raise ValueError(f"Anchor {self.id}: arrival_fallback_points must be empty")

        elif self.kind == SemanticNodeKind.EXIT:
            # Exit 必须满足的约束
            if self.approach_point is None:
                raise ValueError(f"Exit {self.id}: approach_point must not be None")
            if self.arrival_point is None:
                raise ValueError(f"Exit {self.id}: arrival_point must not be None")
            if self.pair_node_id is None:
                raise ValueError(f"Exit {self.id}: pair_node_id must not be None")
            if self.target_scene_id is None:
                raise ValueError(f"Exit {self.id}: target_scene_id must not be None")
            if self.target_arrival_point is None:
                raise ValueError(f"Exit {self.id}: target_arrival_point must not be None")

            # 验证 approach/arrival 的 scene_id
            if self.approach_point.scene_id != self.scene_id:
                raise ValueError(f"Exit {self.id}: approach_point.scene_id must match node scene_id")
            if self.arrival_point.scene_id != self.scene_id:
                raise ValueError(f"Exit {self.id}: arrival_point.scene_id must match node scene_id")

            # 验证 target_arrival_point 的 scene_id
            if self.target_arrival_point.scene_id != self.target_scene_id:
                raise ValueError(f"Exit {self.id}: target_arrival_point.scene_id must match target_scene_id")

        # RULE-MAP-008: Required Node 验证
        if self.reachability_policy == ReachabilityPolicy.REQUIRED:
            if not self.enabled:
                raise ValueError(f"Node {self.id}: Required node must be enabled")
            if self.availability_condition_id is not None:
                raise ValueError(f"Node {self.id}: Required node must not have availability_condition_id")


# ==================== Region Topology ====================

# RULE-MAP-005: 固定的三个 Region Scene ID
REGION_SCENE_IDS = [
    "region.crown_creek_town",
    "region.twilight_whisper_forest",
    "region.silver_ash_mine",
]

# RULE-MAP-006: 固定的 Region Bounds
REGION_BOUNDS = {
    "region.crown_creek_town": SceneBounds(
        scene_id="region.crown_creek_town",
        width_wu=4096,
        height_wu=4096
    ),
    "region.twilight_whisper_forest": SceneBounds(
        scene_id="region.twilight_whisper_forest",
        width_wu=4096,
        height_wu=4096
    ),
    "region.silver_ash_mine": SceneBounds(
        scene_id="region.silver_ash_mine",
        width_wu=3072,
        height_wu=3072
    ),
}


class RegionTopology:
    """
    区域拓扑系统

    管理 Semantic Nodes（Anchor 和 Exit）的注册和查询
    """

    def __init__(self):
        """初始化拓扑系统，加载默认 topology version 1"""
        self.semantic_schema_version = 1
        self.nodes: Dict[str, SemanticNode] = {}
        self._load_default_topology()

    def _load_default_topology(self):
        """加载默认的 topology（来自 DOC-MAP-002 的 canonical manifest）"""
        # 三个 Anchor
        default_nodes = [
            # Crown Creek Town Anchor
            SemanticNode(
                id="semantic_anchor.crown_creek.crown_square",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="region.crown_creek_town",
                point=WorldPoint("region.crown_creek_town", 2048.0, 2048.0),
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
            ),
            # Twilight Whisper Forest Anchor
            SemanticNode(
                id="semantic_anchor.twilight_whisper.oathkeeper_camp",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="region.twilight_whisper_forest",
                point=WorldPoint("region.twilight_whisper_forest", 2048.0, 3584.0),
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
            ),
            # Silver Ash Mine Anchor
            SemanticNode(
                id="semantic_anchor.silver_ash.entry_shed",
                kind=SemanticNodeKind.ANCHOR,
                scene_id="region.silver_ash_mine",
                point=WorldPoint("region.silver_ash_mine", 2688.0, 1536.0),
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
            ),
            # Exit: Crown Creek -> Twilight Forest (north gate)
            SemanticNode(
                id="semantic_exit.crown_creek.north_forest_gate",
                kind=SemanticNodeKind.EXIT,
                scene_id="region.crown_creek_town",
                point=WorldPoint("region.crown_creek_town", 2048.0, 96.0),
                approach_point=WorldPoint("region.crown_creek_town", 2048.0, 160.0),
                arrival_point=WorldPoint("region.crown_creek_town", 2048.0, 128.0),
                arrival_fallback_points=[],
                pair_node_id="semantic_exit.twilight_whisper_forest.south_path",
                target_scene_id="region.twilight_whisper_forest",
                target_arrival_point=WorldPoint("region.twilight_whisper_forest", 2048.0, 3968.0),
                profile_constraints=ProfileConstraints(
                    required_tags=["ground"],
                    max_radius_wu=16.0,
                    min_clearance_wu=2.0
                ),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            ),
            # Exit: Twilight Forest -> Crown Creek (south path)
            SemanticNode(
                id="semantic_exit.twilight_whisper_forest.south_path",
                kind=SemanticNodeKind.EXIT,
                scene_id="region.twilight_whisper_forest",
                point=WorldPoint("region.twilight_whisper_forest", 2048.0, 4000.0),
                approach_point=WorldPoint("region.twilight_whisper_forest", 2048.0, 3936.0),
                arrival_point=WorldPoint("region.twilight_whisper_forest", 2048.0, 3968.0),
                arrival_fallback_points=[],
                pair_node_id="semantic_exit.crown_creek.north_forest_gate",
                target_scene_id="region.crown_creek_town",
                target_arrival_point=WorldPoint("region.crown_creek_town", 2048.0, 128.0),
                profile_constraints=ProfileConstraints(
                    required_tags=["ground"],
                    max_radius_wu=16.0,
                    min_clearance_wu=2.0
                ),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            ),
            # Exit: Crown Creek -> Silver Ash Mine (west road)
            SemanticNode(
                id="semantic_exit.crown_creek.west_mine_road",
                kind=SemanticNodeKind.EXIT,
                scene_id="region.crown_creek_town",
                point=WorldPoint("region.crown_creek_town", 96.0, 2048.0),
                approach_point=WorldPoint("region.crown_creek_town", 160.0, 2048.0),
                arrival_point=WorldPoint("region.crown_creek_town", 128.0, 2048.0),
                arrival_fallback_points=[],
                pair_node_id="semantic_exit.silver_ash_mine.east_entry",
                target_scene_id="region.silver_ash_mine",
                target_arrival_point=WorldPoint("region.silver_ash_mine", 2944.0, 1536.0),
                profile_constraints=ProfileConstraints(
                    required_tags=["ground"],
                    max_radius_wu=16.0,
                    min_clearance_wu=2.0
                ),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            ),
            # Exit: Silver Ash Mine -> Crown Creek (east entry)
            SemanticNode(
                id="semantic_exit.silver_ash_mine.east_entry",
                kind=SemanticNodeKind.EXIT,
                scene_id="region.silver_ash_mine",
                point=WorldPoint("region.silver_ash_mine", 3008.0, 1536.0),
                approach_point=WorldPoint("region.silver_ash_mine", 2912.0, 1536.0),
                arrival_point=WorldPoint("region.silver_ash_mine", 2944.0, 1536.0),
                arrival_fallback_points=[],
                pair_node_id="semantic_exit.crown_creek.west_mine_road",
                target_scene_id="region.crown_creek_town",
                target_arrival_point=WorldPoint("region.crown_creek_town", 128.0, 2048.0),
                profile_constraints=ProfileConstraints(
                    required_tags=["ground"],
                    max_radius_wu=16.0,
                    min_clearance_wu=2.0
                ),
                enabled=True,
                reachability_policy=ReachabilityPolicy.REQUIRED,
                availability_condition_id=None
            ),
        ]

        for node in default_nodes:
            self.nodes[node.id] = node

    def get_node(self, node_id: str) -> Optional[SemanticNode]:
        """根据 ID 获取节点"""
        return self.nodes.get(node_id)

    def get_nodes_by_scene(self, scene_id: str) -> List[SemanticNode]:
        """获取指定 Scene 的所有节点"""
        return [node for node in self.nodes.values() if node.scene_id == scene_id]

    def get_anchors(self) -> List[SemanticNode]:
        """获取所有 Anchor 节点"""
        return [node for node in self.nodes.values() if node.kind == SemanticNodeKind.ANCHOR]

    def get_exits(self) -> List[SemanticNode]:
        """获取所有 Exit 节点"""
        return [node for node in self.nodes.values() if node.kind == SemanticNodeKind.EXIT]


def validate_exit_pairs(topology: RegionTopology) -> List[str]:
    """
    验证所有 Exit 的 pair consistency

    RULE-MAP-007: 检查以下条件：
    - s.target_scene_id == t.scene_id
    - s.target_arrival_point == t.arrival_point
    - t.target_scene_id == s.scene_id
    - t.target_arrival_point == s.arrival_point

    Returns:
        List[str]: 错误信息列表，空列表表示验证通过
    """
    errors = []
    exits = topology.get_exits()

    for exit_node in exits:
        pair_id = exit_node.pair_node_id
        pair_node = topology.get_node(pair_id)

        if pair_node is None:
            errors.append(f"Exit {exit_node.id}: pair_node_id {pair_id} not found")
            continue

        if pair_node.kind != SemanticNodeKind.EXIT:
            errors.append(f"Exit {exit_node.id}: pair {pair_id} is not an Exit")
            continue

        # 检查 target_scene_id 匹配
        if exit_node.target_scene_id != pair_node.scene_id:
            errors.append(
                f"Exit {exit_node.id}: target_scene_id {exit_node.target_scene_id} "
                f"does not match pair scene_id {pair_node.scene_id}"
            )

        # 检查 target_arrival_point 匹配
        if exit_node.target_arrival_point != pair_node.arrival_point:
            errors.append(
                f"Exit {exit_node.id}: target_arrival_point does not match pair arrival_point"
            )

        # 检查反向引用
        if pair_node.target_scene_id != exit_node.scene_id:
            errors.append(
                f"Exit {exit_node.id}: pair {pair_id} target_scene_id does not point back"
            )

        if pair_node.target_arrival_point != exit_node.arrival_point:
            errors.append(
                f"Exit {exit_node.id}: pair {pair_id} target_arrival_point does not point back"
            )

    return errors

"""
MAP 模块：地图、导航和碰撞系统

符合 Phase 3 规范：
- DOC-MAP-001: 世界坐标系
- DOC-MAP-002: 区域拓扑
- DOC-MAP-005: 可行走区域定义
- DOC-MAP-006: 碰撞多边形规格
- DOC-MAP-007: 导航网格和寻路
"""

from .region_topology import (
    SceneBounds,
    SemanticNodeKind,
    SemanticNode,
    RegionTopology,
    validate_exit_pairs,
)
from .walkability import (
    TerrainTag,
    WalkableSurface,
    AgentProfile,
    PositionLegality,
    WalkabilitySystem,
)
from .collision import (
    ObstacleTag,
    CollisionPolygon,
    CollisionHit,
    SweepResult,
    CollisionSystem,
    compute_signed_area,
    is_clockwise,
    is_counter_clockwise,
)
from .navigation import (
    NavigationCell,
    PathStatus,
    PathResult,
    NavigationGrid,
    AStarPathfinder,
    world_to_cell,
)

__all__ = [
    # Region Topology
    "SceneBounds",
    "SemanticNodeKind",
    "SemanticNode",
    "RegionTopology",
    "validate_exit_pairs",
    # Walkability
    "TerrainTag",
    "WalkableSurface",
    "AgentProfile",
    "PositionLegality",
    "WalkabilitySystem",
    # Collision
    "ObstacleTag",
    "CollisionPolygon",
    "CollisionHit",
    "SweepResult",
    "CollisionSystem",
    "compute_signed_area",
    "is_clockwise",
    "is_counter_clockwise",
    # Navigation
    "NavigationCell",
    "PathStatus",
    "PathResult",
    "NavigationGrid",
    "AStarPathfinder",
    "world_to_cell",
]

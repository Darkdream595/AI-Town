"""
导航网格与寻路

符合 DOC-MAP-007 规范：
- RULE-MAP-025: Navigation Cell 固定 16 wu
- RULE-MAP-026: A* 8-neighbor，禁止 Corner Cutting
- RULE-MAP-027: 查询和结果携带 Navigation Revision
- RULE-MAP-028: Heuristic 下界和确定性 tie-break
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Dict, Set
import heapq
import math
from ..foundation.coordinates import WorldCoordinate
from .walkability import AgentProfile, WalkabilitySystem
from .collision import CollisionSystem


# ==================== Constants ====================

# RULE-MAP-025: Navigation Cell 固定 16 wu
NAVIGATION_CELL_SIZE = 16

# RULE-MAP-026: Step costs（千分之一单位）
ORTHOGONAL_STEP_COST = 1000
DIAGONAL_STEP_COST = 1414


# ==================== Navigation Cell ====================

@dataclass(frozen=True)
class NavigationCell:
    """
    导航单元

    RULE-MAP-025: 16 × 16 wu，cell (cx, cy) 中心为 (cx*16+8, cy*16+8)
    """
    cx: int  # Cell X 坐标
    cy: int  # Cell Y 坐标

    def get_center(self) -> WorldCoordinate:
        """获取 cell 中心点"""
        center_x = self.cx * NAVIGATION_CELL_SIZE + NAVIGATION_CELL_SIZE // 2
        center_y = self.cy * NAVIGATION_CELL_SIZE + NAVIGATION_CELL_SIZE // 2
        return WorldCoordinate(x_wu=float(center_x), y_wu=float(center_y))

    def __hash__(self):
        return hash((self.cx, self.cy))

    def __eq__(self, other):
        if not isinstance(other, NavigationCell):
            return False
        return self.cx == other.cx and self.cy == other.cy

    def __lt__(self, other):
        """用于 tie-break: 按 cy, cx 排序"""
        return (self.cy, self.cx) < (other.cy, other.cx)


def world_to_cell(point: WorldCoordinate) -> NavigationCell:
    """世界坐标转换为 Navigation Cell"""
    cx = int(point.x_wu // NAVIGATION_CELL_SIZE)
    cy = int(point.y_wu // NAVIGATION_CELL_SIZE)
    return NavigationCell(cx, cy)


# ==================== Path Result ====================

class PathStatus(str, Enum):
    """路径查询状态"""
    SUCCESS = "success"
    UNREACHABLE = "unreachable"
    INVALID_START = "invalid_start"
    INVALID_GOAL = "invalid_goal"
    STALE_NAVIGATION_REVISION = "stale_navigation_revision"
    BUDGET_EXCEEDED = "budget_exceeded"
    SCENE_NOT_READY = "scene_not_ready"


@dataclass(frozen=True)
class PathResult:
    """路径查询结果"""
    status: PathStatus
    scene_id: str
    navigation_revision: int
    waypoints: List[WorldCoordinate]
    total_cost: int = 0
    expanded_nodes: int = 0


# ==================== Navigation Grid ====================

class NavigationGrid:
    """
    导航网格

    RULE-MAP-025: 由结构化 Walkability/Collision 栅格化为 16 wu 网格
    """

    def __init__(
        self,
        scene_id: str,
        scene_bounds: 'SceneBounds',
        walkability: WalkabilitySystem,
        collision: CollisionSystem,
        profile: AgentProfile
    ):
        """
        初始化导航网格

        Args:
            scene_id: Scene 标识符
            scene_bounds: Scene 边界
            walkability: 可行走性系统
            collision: 碰撞系统
            profile: Agent Profile
        """
        self.scene_id = scene_id
        self.scene_bounds = scene_bounds
        self.walkability = walkability
        self.collision = collision
        self.profile = profile
        self.revision = collision.get_revision()

        # 计算网格尺寸
        self.grid_width = (scene_bounds.width_wu + NAVIGATION_CELL_SIZE - 1) // NAVIGATION_CELL_SIZE
        self.grid_height = (scene_bounds.height_wu + NAVIGATION_CELL_SIZE - 1) // NAVIGATION_CELL_SIZE

        # 栅格化：标记可通行的 cell
        self.traversable_cells: Set[NavigationCell] = set()
        self._rasterize()

        # 计算最小 terrain cost（用于 heuristic）
        self._compute_minimum_costs()

    def _rasterize(self):
        """
        栅格化导航网格

        RULE-MAP-025: cell 可通行当且仅当其 center 通过 is_standable
        """
        for cy in range(self.grid_height):
            for cx in range(self.grid_width):
                cell = NavigationCell(cx, cy)
                center = cell.get_center()

                # 检查 cell 中心是否可站立
                result = self.walkability.is_standable(center, self.profile)
                if result.legality.value == "legal":
                    # 还需要检查是否与 Collision 相交
                    total_radius = self.profile.get_total_radius()
                    hits = self.collision.intersects_disc(center, total_radius)
                    if not hits:
                        self.traversable_cells.add(cell)

    def _compute_minimum_costs(self):
        """计算最小 terrain 和 modifier costs（用于 heuristic）"""
        self.min_terrain_q1000 = 1000  # 默认值
        self.min_modifier_q1000 = 1000

        if not self.traversable_cells:
            return

        # 遍历所有可通行 cell，找到最小 terrain cost
        min_cost = float('inf')
        for cell in self.traversable_cells:
            center = cell.get_center()
            result = self.walkability.is_standable(center, self.profile)
            if result.effective_cost_q1000 is not None:
                min_cost = min(min_cost, result.effective_cost_q1000)

        if min_cost != float('inf'):
            self.min_terrain_q1000 = int(min_cost)

    def is_traversable(self, cell: NavigationCell) -> bool:
        """判断 cell 是否可通行"""
        return cell in self.traversable_cells

    def get_neighbors(self, cell: NavigationCell) -> List[NavigationCell]:
        """
        获取 cell 的 8-neighbor

        RULE-MAP-026: 对角边要求两个相邻正交边均可通行（禁止 Corner Cutting）
        """
        neighbors = []
        cx, cy = cell.cx, cell.cy

        # 四个正交方向
        orthogonal = [
            (cx, cy - 1),  # North
            (cx + 1, cy),  # East
            (cx, cy + 1),  # South
            (cx - 1, cy),  # West
        ]

        # 检查正交邻居
        traversable_orthogonal = []
        for ncx, ncy in orthogonal:
            neighbor = NavigationCell(ncx, ncy)
            if self.is_traversable(neighbor):
                neighbors.append(neighbor)
                traversable_orthogonal.append((ncx, ncy))

        # 四个对角方向（只有当两个相邻正交边都可通行时才可对角移动）
        diagonals = [
            ((cx - 1, cy - 1), [(cx - 1, cy), (cx, cy - 1)]),  # NW: 需要 W 和 N
            ((cx + 1, cy - 1), [(cx + 1, cy), (cx, cy - 1)]),  # NE: 需要 E 和 N
            ((cx + 1, cy + 1), [(cx + 1, cy), (cx, cy + 1)]),  # SE: 需要 E 和 S
            ((cx - 1, cy + 1), [(cx - 1, cy), (cx, cy + 1)]),  # SW: 需要 W 和 S
        ]

        for (ncx, ncy), required in diagonals:
            # RULE-MAP-026: 禁止 Corner Cutting
            if all(req in traversable_orthogonal for req in required):
                neighbor = NavigationCell(ncx, ncy)
                if self.is_traversable(neighbor):
                    neighbors.append(neighbor)

        return neighbors

    def get_edge_cost(self, from_cell: NavigationCell, to_cell: NavigationCell) -> int:
        """
        计算有向边的代价

        RULE-MAP-026: 每条有向边只按 destination cell 中心的 terrain 收费
        完整公式: ceil_div(step_cost * terrain_q1000 * modifier_q1000, 1_000_000) + additive
        """
        # 判断是正交还是对角
        dx = abs(to_cell.cx - from_cell.cx)
        dy = abs(to_cell.cy - from_cell.cy)

        if dx + dy == 1:
            step_cost = ORTHOGONAL_STEP_COST
        elif dx == 1 and dy == 1:
            step_cost = DIAGONAL_STEP_COST
        else:
            raise ValueError(f"Invalid edge: {from_cell} -> {to_cell}")

        # 获取 destination cell 的 terrain cost
        center = to_cell.get_center()
        result = self.walkability.is_standable(center, self.profile)

        if result.effective_cost_q1000 is None:
            return 999999  # 不可通行

        terrain_q1000 = result.effective_cost_q1000
        modifier_q1000 = self.min_modifier_q1000  # 简化实现：使用最小 modifier

        # 完整公式
        numerator = step_cost * terrain_q1000 * modifier_q1000
        scaled_cost = self._ceil_div(numerator, 1_000_000)
        additive_cost = 0  # 简化实现：暂不支持 additive

        return scaled_cost + additive_cost

    def _ceil_div(self, a: int, b: int) -> int:
        """向上取整除法: ceil(a / b) = floor((a + b - 1) / b)"""
        return (a + b - 1) // b


# ==================== A* Pathfinding ====================

class AStarPathfinder:
    """
    A* 寻路算法

    RULE-MAP-028: 确定性 tie-break 和 heuristic 下界
    """

    def __init__(self, grid: NavigationGrid):
        """
        初始化寻路器

        Args:
            grid: 导航网格
        """
        self.grid = grid

    def find_path(
        self,
        start: WorldCoordinate,
        goal: WorldCoordinate,
        max_expanded: int = 100000
    ) -> PathResult:
        """
        查找从 start 到 goal 的路径

        RULE-MAP-028: 确定性算法

        Args:
            start: 起点（世界坐标）
            goal: 终点（世界坐标）
            max_expanded: 最大扩展节点数

        Returns:
            PathResult: 路径结果
        """
        # 转换为 cell 坐标
        start_cell = world_to_cell(start)
        goal_cell = world_to_cell(goal)

        # 验证起点和终点
        if not self.grid.is_traversable(start_cell):
            # 尝试 snap 到最近的合法 cell
            start_cell = self._nearest_legal_cell(start, max_chebyshev=2)
            if start_cell is None:
                return PathResult(
                    status=PathStatus.INVALID_START,
                    scene_id=self.grid.scene_id,
                    navigation_revision=self.grid.revision,
                    waypoints=[]
                )

        if not self.grid.is_traversable(goal_cell):
            goal_cell = self._nearest_legal_cell(goal, max_chebyshev=2)
            if goal_cell is None:
                return PathResult(
                    status=PathStatus.INVALID_GOAL,
                    scene_id=self.grid.scene_id,
                    navigation_revision=self.grid.revision,
                    waypoints=[]
                )

        # 执行 A*
        path_cells, total_cost, expanded = self._astar(start_cell, goal_cell, max_expanded)

        if path_cells is None:
            # 判断是否超出预算
            if expanded >= max_expanded:
                status = PathStatus.BUDGET_EXCEEDED
            else:
                status = PathStatus.UNREACHABLE

            return PathResult(
                status=status,
                scene_id=self.grid.scene_id,
                navigation_revision=self.grid.revision,
                waypoints=[],
                expanded_nodes=expanded
            )

        # 转换为世界坐标 waypoints
        waypoints = [cell.get_center() for cell in path_cells]

        return PathResult(
            status=PathStatus.SUCCESS,
            scene_id=self.grid.scene_id,
            navigation_revision=self.grid.revision,
            waypoints=waypoints,
            total_cost=total_cost,
            expanded_nodes=expanded
        )

    def _astar(
        self,
        start: NavigationCell,
        goal: NavigationCell,
        max_expanded: int
    ) -> Tuple[Optional[List[NavigationCell]], int, int]:
        """
        A* 核心算法

        Returns:
            (path, total_cost, expanded_count) or (None, 0, expanded_count)
        """
        # Priority queue: (f, h, cy, cx, cell)
        # RULE-MAP-028: tie-break 固定为较小 f, h, cy, cx
        open_set = []
        heapq.heappush(open_set, (0, 0, start.cy, start.cx, start))

        came_from: Dict[NavigationCell, NavigationCell] = {}
        g_score: Dict[NavigationCell, int] = {start: 0}
        expanded_count = 0

        while open_set and expanded_count < max_expanded:
            _, _, _, _, current = heapq.heappop(open_set)

            # 到达目标
            if current == goal:
                path = self._reconstruct_path(came_from, current)
                return path, g_score[current], expanded_count

            expanded_count += 1

            # 扩展邻居
            for neighbor in self.grid.get_neighbors(current):
                edge_cost = self.grid.get_edge_cost(current, neighbor)
                tentative_g = g_score[current] + edge_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    h = self._heuristic(neighbor, goal)
                    f = tentative_g + h
                    heapq.heappush(open_set, (f, h, neighbor.cy, neighbor.cx, neighbor))

        # 未找到路径
        return None, 0, expanded_count

    def _heuristic(self, current: NavigationCell, goal: NavigationCell) -> int:
        """
        计算 heuristic（启发式函数）

        RULE-MAP-028: 使用 minimum edge cost 的可证明下界
        """
        dx = abs(goal.cx - current.cx)
        dy = abs(goal.cy - current.cy)

        # 计算最小边代价
        min_orth_edge = self._ceil_div(
            ORTHOGONAL_STEP_COST * self.grid.min_terrain_q1000 * self.grid.min_modifier_q1000,
            1_000_000
        )
        min_diag_edge = self._ceil_div(
            DIAGONAL_STEP_COST * self.grid.min_terrain_q1000 * self.grid.min_modifier_q1000,
            1_000_000
        )

        diagonal_steps = min(dx, dy)
        straight_steps = max(dx, dy) - diagonal_steps

        h = diagonal_steps * min(min_diag_edge, 2 * min_orth_edge) + straight_steps * min_orth_edge

        return h

    def _ceil_div(self, a: int, b: int) -> int:
        """向上取整除法"""
        return (a + b - 1) // b

    def _reconstruct_path(
        self,
        came_from: Dict[NavigationCell, NavigationCell],
        current: NavigationCell
    ) -> List[NavigationCell]:
        """重建路径"""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def _nearest_legal_cell(
        self,
        point: WorldCoordinate,
        max_chebyshev: int = 2
    ) -> Optional[NavigationCell]:
        """
        查找最近的合法 cell

        Chebyshev 半径 2 cells = 32 wu
        按欧氏距离平方、cy、cx 排序
        """
        center_cell = world_to_cell(point)

        candidates = []
        for dy in range(-max_chebyshev, max_chebyshev + 1):
            for dx in range(-max_chebyshev, max_chebyshev + 1):
                cell = NavigationCell(center_cell.cx + dx, center_cell.cy + dy)
                if self.grid.is_traversable(cell):
                    cell_center = cell.get_center()
                    dist_sq = (cell_center.x_wu - point.x_wu) ** 2 + (cell_center.y_wu - point.y_wu) ** 2
                    candidates.append((dist_sq, cell.cy, cell.cx, cell))

        if not candidates:
            return None

        candidates.sort()
        return candidates[0][3]

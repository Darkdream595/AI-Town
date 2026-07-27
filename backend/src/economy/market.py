"""
基础供需与短缺（DOC-ECON-009）

- RULE-ECON-033：三 Region 必需生产链与 DAG
- RULE-ECON-034：Supply/Demand 只由已提交事件更新，按 ActionId 幂等
- RULE-ECON-035：1440 分钟窗口、60 分钟 bucket、速度倍率等价
- RULE-ECON-036：Shortage 两 bucket 滞回；不产生负库存/凭空补货/无限 multiplier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .constants import (
    MARKET_BUCKET_COUNT,
    MARKET_BUCKET_MINUTES,
    MARKET_WINDOW_MINUTES,
    REQUIRED_PRODUCTION_SETS,
    ShortageState,
)


class MarketError(Exception):
    """市场操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# -- 生产链 --


class ProductionChainRegistry:
    """注册有向图；构建期验证必需集合与无环"""

    def __init__(self) -> None:
        self._region_nodes: Dict[str, Set[str]] = {}
        self._edges: List[Tuple[str, str]] = []

    def add_region_chain(
        self,
        region_id: str,
        node_ids: Set[str],
        edges: List[Tuple[str, str]],
    ) -> None:
        self._region_nodes.setdefault(region_id, set()).update(node_ids)
        self._edges.extend(edges)

    def validate(self) -> None:
        for region_id, required in REQUIRED_PRODUCTION_SETS.items():
            registered = self._region_nodes.get(region_id, set())
            if not required <= registered:
                raise MarketError(
                    "market_key_invalid",
                    f"{region_id} missing {sorted(required - registered)}",
                )
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        adjacency: Dict[str, List[str]] = {}
        for source, target in self._edges:
            adjacency.setdefault(source, []).append(target)
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def dfs(node: str) -> None:
            if node in visiting:
                raise MarketError("production_chain_cycle", f"cycle at {node}")
            if node in visited:
                return
            visiting.add(node)
            for nxt in adjacency.get(node, []):
                dfs(nxt)
            visiting.discard(node)
            visited.add(node)

        for node in list(adjacency):
            dfs(node)


def build_default_production_chains() -> ProductionChainRegistry:
    """RULE-ECON-033：首版三 Region 必需链"""
    registry = ProductionChainRegistry()
    registry.add_region_chain(
        "region.duskwood_forest",
        {"material.timber", "material.herb", "material.food_ingredient"},
        [],
    )
    registry.add_region_chain(
        "region.boulder_mine",
        {"material.ore", "material.magic_crystal", "material.stone"},
        [],
    )
    registry.add_region_chain(
        "region.crown_creek_town",
        {
            "material.timber", "material.herb", "material.food_ingredient",
            "material.ore", "material.magic_crystal", "material.stone",
            "product.tool", "product.weapon", "product.potion",
            "product.food", "product.magic_item", "product.building_material",
        },
        [
            ("material.ore", "product.tool"),
            ("material.ore", "product.weapon"),
            ("material.timber", "product.tool"),
            ("material.herb", "product.potion"),
            ("material.food_ingredient", "product.food"),
            ("material.magic_crystal", "product.magic_item"),
            ("material.stone", "product.building_material"),
            ("material.timber", "product.building_material"),
        ],
    )
    registry.validate()
    return registry


# -- ScarcityPolicy（scarcity_q1000 的唯一算法来源） --


@dataclass(frozen=True)
class ScarcityPolicy:
    policy_id: str = "scarcity_policy.local_market.v1"
    policy_version: int = 1
    window_minutes: int = MARKET_WINDOW_MINUTES
    bucket_minutes: int = MARKET_BUCKET_MINUTES
    minimum_q1000: int = 700
    maximum_q1000: int = 2000
    deficit_weight_q1000: int = 600
    unmet_demand_weight_q1000: int = 400
    surplus_relief_weight_q1000: int = 300
    hysteresis_closed_buckets: int = 2
    empty_window_fallback_q1000: int = 1000


DEFAULT_SCARCITY_POLICY = ScarcityPolicy()


def qdiv(numerator: int, denominator: int) -> int:
    """§5：qdiv(n,d)=floor((2*n+d)/(2*d))，正整数域精确 round_half_up"""
    return (2 * numerator + denominator) // (2 * denominator)


def compute_scarcity_q1000(
    available_quantity: int,
    reorder_threshold: int,
    committed_demand_quantity: int,
    unmet_demand_quantity: int,
    policy: ScarcityPolicy = DEFAULT_SCARCITY_POLICY,
    window_empty: bool = False,
) -> int:
    """§5 golden formula；clamp 到 [minimum, maximum]"""
    if window_empty:
        return policy.empty_window_fallback_q1000
    deficit_q1000 = qdiv(
        max(reorder_threshold - available_quantity, 0) * 1000, reorder_threshold
    )
    surplus_q1000 = min(
        qdiv(max(available_quantity - reorder_threshold, 0) * 1000, reorder_threshold),
        1000,
    )
    demand_total = committed_demand_quantity + unmet_demand_quantity
    unmet_q1000 = (
        0 if demand_total == 0 else qdiv(unmet_demand_quantity * 1000, demand_total)
    )
    raw_q1000 = (
        1000
        + qdiv(policy.deficit_weight_q1000 * deficit_q1000, 1000)
        + qdiv(policy.unmet_demand_weight_q1000 * unmet_q1000, 1000)
        - qdiv(policy.surplus_relief_weight_q1000 * surplus_q1000, 1000)
    )
    return max(policy.minimum_q1000, min(policy.maximum_q1000, raw_q1000))


# -- Shortage 滞回状态机 --


@dataclass
class ShortageTracker:
    """§5：两 bucket 滞回；不再叠加第二个价格 multiplier"""

    state: ShortageState = ShortageState.NORMAL
    signal_streak: int = 0

    def update(self, shortage_signal: bool, recovery_signal: bool) -> Tuple[ShortageState, int]:
        if self.state is ShortageState.NORMAL:
            if shortage_signal:
                self.state, self.signal_streak = ShortageState.WATCH, 1
            else:
                self.signal_streak = 0
        elif self.state is ShortageState.WATCH:
            if shortage_signal:
                self.state, self.signal_streak = ShortageState.ACTIVE, 2
            else:
                self.state, self.signal_streak = ShortageState.NORMAL, 0
        elif self.state is ShortageState.ACTIVE:
            if recovery_signal:
                self.state, self.signal_streak = ShortageState.RECOVERING, 1
            else:
                self.signal_streak = 0
        elif self.state is ShortageState.RECOVERING:
            if recovery_signal:
                self.state, self.signal_streak = ShortageState.NORMAL, 0
            else:
                self.state, self.signal_streak = ShortageState.ACTIVE, 0
        return self.state, self.signal_streak


# -- 滚动窗口 --


@dataclass(frozen=True)
class MarketKey:
    region_id: str
    shop_id: str
    item_definition_id: str


class MarketWindow:
    """
    每 market key 固定 24 个小时 bucket，增量 O(1)。

    bucket 归属只由 game_time 决定，因此高倍速批量与逐分钟更新得到相同
    bucket totals（RULE-ECON-035）；0× 不调用即不滚动（RULE-ECON-047）。
    """

    def __init__(self, bucket_minutes: int = MARKET_BUCKET_MINUTES, bucket_count: int = MARKET_BUCKET_COUNT) -> None:
        self._bucket_minutes = bucket_minutes
        self._bucket_count = bucket_count
        # bucket_index -> [supply, committed, unmet]
        self._buckets: Dict[int, List[int]] = {}
        self._seen_action_ids: Set[str] = set()

    def _bucket_index(self, game_time: int) -> int:
        return game_time // self._bucket_minutes

    def _record(self, action_id: str, column: int, quantity: int, game_time: int) -> bool:
        """RULE-ECON-034：同一 ActionId 幂等计一次；返回是否新计入"""
        if action_id in self._seen_action_ids:
            return False
        if quantity <= 0:
            raise MarketError("market_key_invalid", "quantity must be > 0")
        self._seen_action_ids.add(action_id)
        bucket = self._buckets.setdefault(self._bucket_index(game_time), [0, 0, 0])
        bucket[column] += quantity
        return True

    def record_supply(self, action_id: str, quantity: int, game_time: int) -> bool:
        return self._record(action_id, 0, quantity, game_time)

    def record_committed_demand(self, action_id: str, quantity: int, game_time: int) -> bool:
        return self._record(action_id, 1, quantity, game_time)

    def record_unmet_demand(self, action_id: str, quantity: int, game_time: int) -> bool:
        return self._record(action_id, 2, quantity, game_time)

    def totals(self, window_end_game_time: int) -> Tuple[int, int, int]:
        """(supply, committed, unmet) over the last bucket_count closed buckets"""
        end_bucket = self._bucket_index(window_end_game_time)
        start_bucket = end_bucket - self._bucket_count
        supply = committed = unmet = 0
        for index, (s, c, u) in self._buckets.items():
            if start_bucket < index <= end_bucket:
                supply += s
                committed += c
                unmet += u
        return supply, committed, unmet

    def bucket_totals(self) -> Dict[int, Tuple[int, int, int]]:
        return {index: tuple(values) for index, values in sorted(self._buckets.items())}

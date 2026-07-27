"""
制作与资源消耗（DOC-ECON-010）

- RULE-ECON-037：Recipe 版本化、正整数数量、整数时长、有界失败策略
- RULE-ECON-038：开始前原子预留全部输入/容量/工具/worker/Station
- RULE-ECON-039：成功消费/创建/provenance/事件同一事务
- RULE-ECON-040：失败消费 floor(reserved × bps / 10000)，未声明 sink 差额释放
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import MAX_CRAFT_BATCH_SIZE, CraftOrderState, ReservationState, ResourceKind
from .inventory import InventoryError, InventoryManager, ReservationLedger
from .items import ItemRegistry


class CraftingError(Exception):
    """制作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class RecipeIO:
    item_definition_id: str
    quantity: int


@dataclass(frozen=True)
class RecipeDefinition:
    """DES-ECON-010 的运行时形态"""

    recipe_id: str
    recipe_version: int
    inputs: Tuple[RecipeIO, ...]
    outputs: Tuple[RecipeIO, ...]
    tool_capability_ids: Tuple[str, ...]
    station_capability_id: str
    duration_game_minutes: int
    failure_consumption_bps: int
    required_skill_projection: Optional[Dict] = None

    def validate(self) -> None:
        if self.recipe_version < 1:
            raise CraftingError("recipe_version_mismatch", "version must be >= 1")
        if not self.inputs or not self.outputs:
            raise CraftingError("recipe_unknown", "inputs/outputs must be non-empty")
        for entry in (*self.inputs, *self.outputs):
            if entry.quantity <= 0:
                raise CraftingError(
                    "recipe_unknown", f"quantity must be positive: {entry}"
                )
        if self.duration_game_minutes <= 0:
            raise CraftingError("recipe_unknown", "duration must be positive")
        if not (0 <= self.failure_consumption_bps <= 10000):
            raise CraftingError(
                "recipe_unknown", f"failure_consumption_bps {self.failure_consumption_bps}"
            )


class RecipeRegistry:
    """构建期校验 Recipe DAG：无自生产套利环"""

    def __init__(self) -> None:
        self._recipes: Dict[str, RecipeDefinition] = {}

    def register(self, recipe: RecipeDefinition) -> None:
        recipe.validate()
        self._recipes[recipe.recipe_id] = recipe
        self._assert_acyclic()

    def get(self, recipe_id: str, recipe_version: int) -> RecipeDefinition:
        recipe = self._recipes.get(recipe_id)
        if recipe is None:
            raise CraftingError("recipe_unknown", recipe_id)
        if recipe.recipe_version != recipe_version:
            raise CraftingError(
                "recipe_version_mismatch",
                f"expected {recipe_version}, registered {recipe.recipe_version}",
            )
        return recipe

    def _assert_acyclic(self) -> None:
        # item_definition_id -> 能产出它的 recipe
        producers: Dict[str, List[RecipeDefinition]] = {}
        for recipe in self._recipes.values():
            for output in recipe.outputs:
                producers.setdefault(output.item_definition_id, []).append(recipe)

        visiting: set = set()

        def dfs(item_definition_id: str, trail: Tuple[str, ...]) -> None:
            if item_definition_id in visiting:
                raise CraftingError(
                    "production_chain_cycle",
                    f"cycle: {' -> '.join((*trail, item_definition_id))}",
                )
            visiting.add(item_definition_id)
            for recipe in producers.get(item_definition_id, []):
                for input_entry in recipe.inputs:
                    dfs(input_entry.item_definition_id, (*trail, item_definition_id))
            visiting.discard(item_definition_id)

        for recipe in list(self._recipes.values()):
            for output in recipe.outputs:
                dfs(output.item_definition_id, ())


@dataclass
class CraftOrder:
    """DES-ECON-010 CraftOrder"""

    craft_order_id: str
    action_id: str
    recipe_id: str
    recipe_version: int
    batch_size: int
    target_inventory_id: str
    reservation_ids: Tuple[str, ...]
    input_refs: Tuple[Tuple[str, int], ...]  # (batch_id, reserved_quantity)
    tool_item_ids: Tuple[str, ...]
    state: CraftOrderState = CraftOrderState.RESERVED
    seed_stream_position: int = 0
    last_revision: int = 0


class CraftingEngine:
    """原子预留与确定性结算；崩溃恢复 exactly-once"""

    def __init__(
        self,
        reservation_ledger: ReservationLedger,
        item_registry: ItemRegistry,
        inventory_manager: InventoryManager,
    ) -> None:
        self._reservations = reservation_ledger
        self._items = item_registry
        self._inventories = inventory_manager
        self._orders: Dict[str, CraftOrder] = {}
        self._command_results: Dict[str, CraftOrder] = {}

    def get(self, order_id: str) -> CraftOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise CraftingError("craft_recovery_required", f"unknown {order_id}")
        return order

    def begin_order(
        self,
        command_id: str,
        recipe: RecipeDefinition,
        batch_size: int,
        action_id: str,
        worker_id: str,
        target_inventory_id: str,
        input_batches: List[Tuple[str, int, int, str]],  # (batch_id, version, available, source_inventory_id)
        tool_items: List[Tuple[str, int, str]],  # (item_id, version, source_inventory_id)
        station_id: str,
        game_time: int,
        output_unit_weight_grams: int = 0,
    ) -> CraftOrder:
        """RULE-ECON-038：原子预留；任何一步失败释放全部"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        if not (1 <= batch_size <= MAX_CRAFT_BATCH_SIZE):
            raise CraftingError(
                "recipe_unknown", f"batch_size must be 1..{MAX_CRAFT_BATCH_SIZE}"
            )
        # 目标容量先行校验（失败不创建任何 Reservation）
        for output in recipe.outputs:
            self._inventories.can_accept(
                target_inventory_id,
                output.item_definition_id,
                output.quantity * batch_size,
                output_unit_weight_grams,
            )
        required: Dict[str, int] = {}
        for input_entry in recipe.inputs:
            required[input_entry.item_definition_id] = (
                required.get(input_entry.item_definition_id, 0)
                + input_entry.quantity * batch_size
            )
        reservation_ids: List[str] = []
        input_refs: List[Tuple[str, int]] = []
        try:
            for batch_id, version, available, source_inventory_id in input_batches:
                batch = self._items.get_batch(batch_id)
                if batch is None:
                    raise CraftingError("input_missing", batch_id)
                need = required.get(batch["item_definition_id"], 0)
                reservation = self._reservations.reserve(
                    owner_action_id=action_id,
                    binding_id=f"craft_input.{batch_id}",
                    resource_kind=ResourceKind.ITEM_QUANTITY,
                    resource_id=batch_id,
                    resource_version=version,
                    source_inventory_id=source_inventory_id,
                    holder_actor_id=worker_id,
                    quantity=need,
                    created_game_time=game_time,
                    expires_at_game_time=game_time + recipe.duration_game_minutes,
                    request_revision=0,
                    available_quantity=available,
                    current_container_inventory_id=batch["current_container"]["inventory_id"],
                )
                reservation_ids.append(reservation.reservation_id)
                input_refs.append((batch_id, need))
            for item_id, version, source_inventory_id in tool_items:
                instance = self._items.get_instance(item_id)
                if instance is None:
                    raise CraftingError("tool_unavailable", item_id)
                reservation = self._reservations.reserve(
                    owner_action_id=action_id,
                    binding_id=f"craft_tool.{item_id}",
                    resource_kind=ResourceKind.UNIQUE_ITEM,
                    resource_id=item_id,
                    resource_version=version,
                    source_inventory_id=source_inventory_id,
                    holder_actor_id=worker_id,
                    quantity=1,
                    created_game_time=game_time,
                    expires_at_game_time=game_time + recipe.duration_game_minutes,
                    request_revision=0,
                    available_quantity=1,
                    current_container_inventory_id=instance["current_container"]["inventory_id"],
                )
                reservation_ids.append(reservation.reservation_id)
            station_reservation = self._reservations.reserve(
                owner_action_id=action_id,
                binding_id=f"craft_station.{station_id}",
                resource_kind=ResourceKind.CRAFT_STATION,
                resource_id=station_id,
                resource_version=0,
                source_inventory_id=None,
                holder_actor_id=worker_id,
                quantity=1,
                created_game_time=game_time,
                expires_at_game_time=game_time + recipe.duration_game_minutes,
                request_revision=0,
                available_quantity=1,
            )
            reservation_ids.append(station_reservation.reservation_id)
        except (InventoryError, CraftingError):
            for reservation_id in reservation_ids:
                reservation = self._reservations.get(reservation_id)
                if reservation.state is ReservationState.ACTIVE:
                    self._reservations.release(reservation_id)
            raise
        order = CraftOrder(
            craft_order_id=generate_ulid(),
            action_id=action_id,
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.recipe_version,
            batch_size=batch_size,
            target_inventory_id=target_inventory_id,
            reservation_ids=tuple(reservation_ids),
            input_refs=tuple(input_refs),
            tool_item_ids=tuple(item_id for item_id, _v, _s in tool_items),
        )
        self._orders[order.craft_order_id] = order
        self._command_results[command_id] = order
        return order

    def complete(
        self,
        command_id: str,
        order_id: str,
        recipe: RecipeDefinition,
        success: bool,
        game_time: int,
        craft_event_id: Optional[str] = None,
    ) -> CraftOrder:
        """
        RULE-ECON-039/040：成功消费全部输入并创建输出；失败按 floor 规则消费、
        差额释放。同一 command 重放返回原结果（不重复创建输出）。
        """
        if command_id in self._command_results:
            return self._command_results[command_id]
        order = self.get(order_id)
        if order.state not in (CraftOrderState.RESERVED, CraftOrderState.IN_PROGRESS):
            raise CraftingError("craft_recovery_required", order.state.value)
        event_id = craft_event_id or generate_ulid()
        if success:
            for batch_id, reserved in order.input_refs:
                self._items.consume_batch(batch_id, reserved, game_time)
            for output in recipe.outputs:
                created = self._items.create_batch(
                    output.item_definition_id,
                    output.quantity * order.batch_size,
                    order.target_inventory_id,
                    slot_key="slot.craft",
                    source_event_id=event_id,
                    game_time=game_time,
                    provenance_class_id=f"provenance.craft.{recipe.recipe_id}",
                )
                # 输出 provenance 指向 Recipe、输入 heads 与 ActionId
                self._items._append_provenance(
                    created["batch_id"],
                    {
                        "kind": "crafted",
                        "recipe_id": recipe.recipe_id,
                        "recipe_version": recipe.recipe_version,
                        "input_batch_ids": [b for b, _q in order.input_refs],
                        "action_id": order.action_id,
                        "game_time": game_time,
                    },
                )
            order.state = CraftOrderState.COMPLETED
        else:
            for batch_id, reserved in order.input_refs:
                consumed = (reserved * recipe.failure_consumption_bps) // 10000
                consumed = max(0, min(reserved, consumed))
                if consumed:
                    self._items.consume_batch(batch_id, consumed, game_time)
            order.state = CraftOrderState.FAILED
        for reservation_id in order.reservation_ids:
            reservation = self._reservations.get(reservation_id)
            if reservation.state is ReservationState.ACTIVE:
                self._reservations.consume(reservation_id)
        order.last_revision += 1
        self._command_results[command_id] = order
        return order

    def cancel(self, command_id: str, order_id: str) -> CraftOrder:
        """未开始取消：全部 Reservation 释放，无消费"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        order = self.get(order_id)
        if order.state not in (CraftOrderState.RESERVED, CraftOrderState.IN_PROGRESS):
            raise CraftingError("craft_recovery_required", order.state.value)
        for reservation_id in order.reservation_ids:
            reservation = self._reservations.get(reservation_id)
            if reservation.state is ReservationState.ACTIVE:
                self._reservations.release(reservation_id)
        order.state = CraftOrderState.CANCELLED
        self._command_results[command_id] = order
        return order

    @staticmethod
    def failure_consumed_quantity(reserved_quantity: int, failure_consumption_bps: int) -> int:
        """RULE-ECON-040：floor 规则，限定 0..reserved"""
        consumed = (reserved_quantity * failure_consumption_bps) // 10000
        return max(0, min(reserved_quantity, consumed))

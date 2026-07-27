"""
库存与容器规则（DOC-ECON-005）

- RULE-ECON-017：slot/weight/quantity 均不为负且不超限；缓存字段可增量重算
- RULE-ECON-018：容器嵌套深度 ≤2，禁止循环与移入后代
- RULE-ECON-019：access_policy 强制；Client/AI 声称权限无效
- RULE-ECON-020：Reservation 状态机与可用量 overlay，不改变 current_container
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    MAX_CONTAINER_DEPTH,
    InventoryKind,
    InventoryState,
    ReservationState,
    ResourceKind,
)


class InventoryError(Exception):
    """库存操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class Inventory:
    """DES-ECON-005 的运行时形态"""

    inventory_id: str
    owner_entity_id: str
    inventory_kind: InventoryKind
    max_slots: int
    max_weight_grams: int
    access_policy_id: str
    used_slots: int = 0
    total_weight_grams: int = 0
    parent_container_item_id: Optional[str] = None
    state: InventoryState = InventoryState.ACTIVE
    version: int = 0
    schema_version: int = 1


@dataclass
class Reservation:
    """DES-ECON-005 Reservation 运行时形态"""

    reservation_id: str
    owner_action_id: str
    binding_id: str
    resource_kind: ResourceKind
    resource_id: str
    resource_version: int
    source_inventory_id: Optional[str]
    holder_actor_id: str
    quantity: int
    created_game_time: int
    expires_at_game_time: int
    request_revision: int
    state: ReservationState = ReservationState.ACTIVE


#: 访问策略：谁被允许（RULE-ECON-019；私人容器遵守 WORLD consent）
_ACCESS_RULES = {
    "inventory_policy.owner_only": {"owner"},
    "inventory_policy.owner_and_authorized_trade": {"owner", "authorized_trader"},
    "inventory_policy.public": {"owner", "authorized_trader", "visitor"},
}


class InventoryManager:
    """Inventory aggregate：容量、重量缓存与容器层级"""

    def __init__(self) -> None:
        self._inventories: Dict[str, Inventory] = {}
        # inventory_id -> {entity_id: (quantity, unit_weight_grams, mergeable_key)}
        self._contents: Dict[str, Dict[str, Tuple[int, int, Tuple]]] = {}
        # container_item_id -> child_inventory_id
        self._container_children: Dict[str, str] = {}
        # inventory_id -> container_item_id（父容器）
        self._container_parents: Dict[str, str] = {}
        # container_item_id -> 其当前所在 inventory_id
        self._container_item_location: Dict[str, str] = {}

    def create_inventory(
        self,
        owner_entity_id: str,
        inventory_kind: InventoryKind,
        max_slots: int,
        max_weight_grams: int,
        access_policy_id: str = "inventory_policy.owner_and_authorized_trade",
        parent_container_item_id: Optional[str] = None,
    ) -> Inventory:
        inventory = Inventory(
            inventory_id=generate_ulid(),
            owner_entity_id=owner_entity_id,
            inventory_kind=inventory_kind,
            max_slots=max_slots,
            max_weight_grams=max_weight_grams,
            access_policy_id=access_policy_id,
            parent_container_item_id=parent_container_item_id,
        )
        if inventory_kind is not InventoryKind.CONTAINER and parent_container_item_id is not None:
            raise InventoryError(
                "container_cycle", "non-container inventory must not have a parent container"
            )
        self._inventories[inventory.inventory_id] = inventory
        self._contents[inventory.inventory_id] = {}
        return inventory

    def get(self, inventory_id: str) -> Inventory:
        inventory = self._inventories.get(inventory_id)
        if inventory is None:
            raise InventoryError("inventory_unknown", inventory_id)
        return inventory

    def link_container_child(self, container_item_id: str, child_inventory_id: str) -> None:
        """container kind 必须由 container 实例的 child_inventory_id 反向唯一引用"""
        self._container_children[container_item_id] = child_inventory_id
        self._container_parents[child_inventory_id] = container_item_id

    # -- 访问 --

    def check_access(self, inventory_id: str, relationship: str) -> None:
        """RULE-ECON-019：relationship 由服务器投影给出，不由 Client/AI 声称"""
        inventory = self.get(inventory_id)
        allowed = _ACCESS_RULES.get(inventory.access_policy_id, {"owner"})
        if relationship not in allowed:
            raise InventoryError("inventory_access_denied", inventory_id)

    # -- 容量 --

    def can_accept(
        self,
        inventory_id: str,
        entity_id: str,
        quantity: int,
        unit_weight_grams: int,
        mergeable_key: Tuple = (),
    ) -> None:
        inventory = self.get(inventory_id)
        contents = self._contents[inventory_id]
        merges = entity_id in contents and contents[entity_id][2] == mergeable_key
        if not merges and inventory.used_slots + 1 > inventory.max_slots:
            raise InventoryError("slot_limit_exceeded", inventory_id)
        added_weight = quantity * unit_weight_grams
        if inventory.total_weight_grams + added_weight > inventory.max_weight_grams:
            raise InventoryError("weight_limit_exceeded", inventory_id)

    def place(
        self,
        inventory_id: str,
        entity_id: str,
        quantity: int,
        unit_weight_grams: int,
        mergeable_key: Tuple = (),
    ) -> None:
        """RULE-ECON-017：提交时更新缓存字段；负量/超限拒绝"""
        if quantity <= 0 or unit_weight_grams < 0:
            raise InventoryError("insufficient_quantity", "invalid place quantity")
        self.can_accept(inventory_id, entity_id, quantity, unit_weight_grams, mergeable_key)
        inventory = self.get(inventory_id)
        contents = self._contents[inventory_id]
        if entity_id in contents and contents[entity_id][2] == mergeable_key:
            old_q, _w, key = contents[entity_id]
            contents[entity_id] = (old_q + quantity, unit_weight_grams, key)
        else:
            contents[entity_id] = (quantity, unit_weight_grams, mergeable_key)
            inventory.used_slots += 1
        inventory.total_weight_grams += quantity * unit_weight_grams
        inventory.version += 1

    def remove(
        self,
        inventory_id: str,
        entity_id: str,
        quantity: int,
    ) -> None:
        inventory = self.get(inventory_id)
        contents = self._contents[inventory_id]
        if entity_id not in contents:
            raise InventoryError("insufficient_quantity", entity_id)
        old_q, unit_weight, key = contents[entity_id]
        if quantity <= 0 or quantity > old_q:
            raise InventoryError("insufficient_quantity", f"remove {quantity} of {old_q}")
        new_q = old_q - quantity
        if new_q == 0:
            del contents[entity_id]
            inventory.used_slots -= 1
        else:
            contents[entity_id] = (new_q, unit_weight, key)
        inventory.total_weight_grams -= quantity * unit_weight
        inventory.version += 1

    def recompute_cache(self, inventory_id: str) -> Tuple[int, int]:
        """§9：提交时从受影响树增量复核的等价全量重算"""
        contents = self._contents.get(inventory_id, {})
        used_slots = len(contents)
        total_weight = sum(q * w for q, w, _k in contents.values())
        return used_slots, total_weight

    def assert_cache_consistent(self, inventory_id: str) -> None:
        inventory = self.get(inventory_id)
        used_slots, total_weight = self.recompute_cache(inventory_id)
        if (inventory.used_slots, inventory.total_weight_grams) != (used_slots, total_weight):
            raise InventoryError(
                "supply_projection_inconsistent",
                f"cache ({inventory.used_slots},{inventory.total_weight_grams}) != recompute ({used_slots},{total_weight})",
            )

    # -- 容器层级 --

    def container_depth(self, inventory_id: str) -> int:
        depth = 0
        current = inventory_id
        while current in self._container_parents:
            depth += 1
            parent_item = self._container_parents[current]
            current = self._container_item_location.get(parent_item)
            if current is None:
                break
        return depth

    def _child_inventories(self, inventory_id: str) -> List[str]:
        return [
            child_inv
            for child_inv, parent_item in self._container_parents.items()
            if self._container_item_location.get(parent_item) == inventory_id
        ]

    def _descendant_inventories(self, inventory_id: str) -> set:
        descendants = set()
        frontier = [inventory_id]
        while frontier:
            current = frontier.pop()
            for child in self._child_inventories(current):
                if child not in descendants:
                    descendants.add(child)
                    frontier.append(child)
        return descendants

    def _subtree_height_below(self, inventory_id: str) -> int:
        children = self._child_inventories(inventory_id)
        if not children:
            return 0
        return 1 + max(self._subtree_height_below(c) for c in children)

    def locate_container_item(self, container_item_id: str, inventory_id: str) -> None:
        """登记容器实例的物理位置（须先通过 check_place_container）"""
        self.check_place_container(container_item_id, inventory_id)
        self._container_item_location[container_item_id] = inventory_id

    def remove_container_item(self, container_item_id: str) -> None:
        self._container_item_location.pop(container_item_id, None)

    def check_place_container(
        self, container_item_id: str, target_inventory_id: str
    ) -> None:
        """RULE-ECON-018：深度 ≤2，禁止自身包含与祖先循环"""
        child_inventory_id = self._container_children.get(container_item_id)
        if child_inventory_id is not None and child_inventory_id == target_inventory_id:
            raise InventoryError("container_cycle", "container cannot contain itself")
        if child_inventory_id is not None:
            descendants = self._descendant_inventories(child_inventory_id)
            if target_inventory_id in descendants:
                raise InventoryError(
                    "container_cycle", "cannot move container into its descendant"
                )
            below = self._subtree_height_below(child_inventory_id)
        else:
            below = 0
        # 放入后：child 深度 = depth(target)+1，最深后代 = depth(target)+1+below
        if self.container_depth(target_inventory_id) + 1 + below > MAX_CONTAINER_DEPTH:
            raise InventoryError(
                "container_depth_exceeded",
                f"nesting would exceed {MAX_CONTAINER_DEPTH}",
            )

    def effective_weight_grams(self, inventory_id: str, _depth: int = 0) -> int:
        """直接内容加允许深度内子容器内容（§3 Effective Weight）"""
        total = self.recompute_cache(inventory_id)[1]
        if _depth >= MAX_CONTAINER_DEPTH:
            return total
        for child_inv in self._child_inventories(inventory_id):
            total += self.effective_weight_grams(child_inv, _depth + 1)
        return total


class ReservationLedger:
    """
    RULE-ECON-020：Resource Reservation 生命周期。

    active 数量计入可用量扣减，但永不改变 current_container；
    恢复审计：同一资源 active 总和不得超过可用量。
    """

    def __init__(self) -> None:
        self._reservations: Dict[str, Reservation] = {}
        self._by_binding: Dict[Tuple[str, str], str] = {}  # (action_id, binding_id) -> reservation_id

    def reserve(
        self,
        owner_action_id: str,
        binding_id: str,
        resource_kind: ResourceKind,
        resource_id: str,
        resource_version: int,
        source_inventory_id: Optional[str],
        holder_actor_id: str,
        quantity: int,
        created_game_time: int,
        expires_at_game_time: int,
        request_revision: int,
        available_quantity: int,
        current_container_inventory_id: Optional[str] = None,
    ) -> Reservation:
        """
        §5：Item/Batch Reservation 必须断言 source == current container 且版本匹配；
        同一资源不得超额预留；binding 在一个 Action 内唯一。
        """
        if quantity <= 0:
            raise InventoryError("insufficient_quantity", "reservation quantity")
        if resource_kind in (
            ResourceKind.UNIQUE_ITEM,
            ResourceKind.ITEM_QUANTITY,
            ResourceKind.PROPERTY_DEED,
        ):
            if source_inventory_id is None:
                raise InventoryError(
                    "reservation_conflict", f"{resource_kind.value} requires source inventory"
                )
            if current_container_inventory_id != source_inventory_id:
                raise InventoryError(
                    "reservation_conflict", "source != current container"
                )
        binding_key = (owner_action_id, binding_id)
        if binding_key in self._by_binding:
            raise InventoryError(
                "reservation_conflict", f"binding {binding_id} already used in action"
            )
        if self.active_quantity(resource_id) + quantity > available_quantity:
            raise InventoryError(
                "reservation_conflict",
                f"active {self.active_quantity(resource_id)} + {quantity} > {available_quantity}",
            )
        reservation = Reservation(
            reservation_id=generate_ulid(),
            owner_action_id=owner_action_id,
            binding_id=binding_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
            resource_version=resource_version,
            source_inventory_id=source_inventory_id,
            holder_actor_id=holder_actor_id,
            quantity=quantity,
            created_game_time=created_game_time,
            expires_at_game_time=expires_at_game_time,
            request_revision=request_revision,
        )
        self._reservations[reservation.reservation_id] = reservation
        self._by_binding[binding_key] = reservation.reservation_id
        return reservation

    def get(self, reservation_id: str) -> Reservation:
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            raise InventoryError("reservation_conflict", f"unknown {reservation_id}")
        return reservation

    def active_quantity(self, resource_id: str) -> int:
        return sum(
            r.quantity
            for r in self._reservations.values()
            if r.resource_id == resource_id and r.state is ReservationState.ACTIVE
        )

    def availability(self, resource_id: str, total_quantity: int) -> int:
        """可用量 overlay：不改 current_container，只扣减"""
        return total_quantity - self.active_quantity(resource_id)

    def _transition(self, reservation_id: str, to_state: ReservationState) -> Reservation:
        reservation = self.get(reservation_id)
        if reservation.state is not ReservationState.ACTIVE:
            raise InventoryError(
                "reservation_conflict",
                f"reservation {reservation_id} already terminal ({reservation.state.value})",
            )
        reservation.state = to_state
        return reservation

    def consume(self, reservation_id: str) -> Reservation:
        """与 committed leg 同一 UoW"""
        return self._transition(reservation_id, ReservationState.CONSUMED)

    def release(self, reservation_id: str) -> Reservation:
        return self._transition(reservation_id, ReservationState.RELEASED)

    def expire_overdue(self, current_game_time: int) -> List[str]:
        """GameTime 驱动：0× 暂停不调用即不过期（RULE-ECON-047）"""
        expired = []
        for reservation in self._reservations.values():
            if (
                reservation.state is ReservationState.ACTIVE
                and current_game_time > reservation.expires_at_game_time
            ):
                reservation.state = ReservationState.EXPIRED
                expired.append(reservation.reservation_id)
        return expired

    def assert_recovery_consistent(self, available_by_resource: Dict[str, int]) -> None:
        """§9：恢复时全量检查 active 总和不超过资源量"""
        for resource_id, available in available_by_resource.items():
            if self.active_quantity(resource_id) > available:
                raise InventoryError(
                    "reservation_conflict",
                    f"active reservations exceed availability for {resource_id}",
                )

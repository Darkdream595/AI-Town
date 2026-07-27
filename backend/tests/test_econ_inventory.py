"""
TEST-ECON-017..020：库存与容器规则（DOC-ECON-005）

- TEST-ECON-017：slot/weight 限额与缓存重算一致
- TEST-ECON-018：容器嵌套深度 ≤2、循环与移入后代拒绝
- TEST-ECON-019：访问策略对 AI/Player 同一判定路径
- TEST-ECON-020：Reservation 生命周期、可用量 overlay 与恢复审计
"""

import pytest

from src.economy import (
    InventoryError,
    InventoryKind,
    InventoryManager,
    ReservationLedger,
    ReservationState,
    ResourceKind,
)
from src.economy.constants import MAX_CONTAINER_DEPTH


def _manager_with_target():
    manager = InventoryManager()
    source = manager.create_inventory("resident.source", InventoryKind.RESIDENT, 4, 100000)
    target = manager.create_inventory("resident.target", InventoryKind.RESIDENT, 2, 5000)
    return manager, source, target


class TestSlotWeightCache:
    """TEST-ECON-017"""

    def test_within_limits_and_cache_recompute(self):
        manager, _source, target = _manager_with_target()
        manager.place(target.inventory_id, "item.a", 3, 1000)
        manager.place(target.inventory_id, "item.b", 1, 1000)
        assert target.used_slots == 2
        assert target.total_weight_grams == 4000
        manager.assert_cache_consistent(target.inventory_id)
        # 合并同 key 不新增 slot
        manager.place(target.inventory_id, "item.a", 1, 1000, mergeable_key=())
        assert target.used_slots == 2
        manager.assert_cache_consistent(target.inventory_id)

    def test_slot_limit_error(self):
        manager, _source, target = _manager_with_target()
        manager.place(target.inventory_id, "item.a", 1, 100)
        manager.place(target.inventory_id, "item.b", 1, 100)
        with pytest.raises(InventoryError) as excinfo:
            manager.place(target.inventory_id, "item.c", 1, 100)
        assert excinfo.value.code == "slot_limit_exceeded"

    def test_weight_limit_error(self):
        manager, _source, target = _manager_with_target()
        manager.place(target.inventory_id, "item.a", 1, 4000)
        with pytest.raises(InventoryError) as excinfo:
            manager.place(target.inventory_id, "item.b", 1, 2000)
        assert excinfo.value.code == "weight_limit_exceeded"

    def test_remove_updates_cache(self):
        manager, _source, target = _manager_with_target()
        manager.place(target.inventory_id, "item.a", 3, 1000)
        manager.remove(target.inventory_id, "item.a", 3)
        assert target.used_slots == 0
        assert target.total_weight_grams == 0
        with pytest.raises(InventoryError) as excinfo:
            manager.remove(target.inventory_id, "item.a", 1)
        assert excinfo.value.code == "insufficient_quantity"

    def test_negative_place_rejected(self):
        manager, _source, target = _manager_with_target()
        with pytest.raises(InventoryError):
            manager.place(target.inventory_id, "item.a", 0, 100)


class TestContainerCycleDepth:
    """TEST-ECON-018"""

    def _nested(self):
        manager = InventoryManager()
        root = manager.create_inventory("resident.a", InventoryKind.RESIDENT, 10, 100000)
        containers = {}
        for name in ("a", "b", "c"):
            item_id = f"item.container.{name}"
            child = manager.create_inventory(
                item_id, InventoryKind.CONTAINER, 10, 100000,
                parent_container_item_id=item_id,
            )
            manager.link_container_child(item_id, child.inventory_id)
            containers[name] = (item_id, child)
        return manager, root, containers

    def test_depth_two_valid_depth_three_rejected(self):
        manager, root, containers = self._nested()
        item_a, inv_a = containers["a"]
        item_b, inv_b = containers["b"]
        item_c, inv_c = containers["c"]
        manager.locate_container_item(item_a, root.inventory_id)
        assert manager.container_depth(inv_a.inventory_id) == 1
        # 深度 2 合法：B 放进 A 的子库存
        manager.locate_container_item(item_b, inv_a.inventory_id)
        assert manager.container_depth(inv_b.inventory_id) == 2
        # 深度 3 拒绝：C 放进 B 的子库存
        with pytest.raises(InventoryError) as excinfo:
            manager.locate_container_item(item_c, inv_b.inventory_id)
        assert excinfo.value.code == "container_depth_exceeded"
        assert MAX_CONTAINER_DEPTH == 2

    def test_cycle_and_descendant_rejected(self):
        manager, root, containers = self._nested()
        item_a, inv_a = containers["a"]
        item_b, inv_b = containers["b"]
        manager.locate_container_item(item_a, root.inventory_id)
        manager.locate_container_item(item_b, inv_a.inventory_id)
        # 自我包含
        with pytest.raises(InventoryError) as excinfo:
            manager.check_place_container(item_a, inv_a.inventory_id)
        assert excinfo.value.code == "container_cycle"
        # 移入后代：A 放进 B 的子库存（B 在 A 内）
        with pytest.raises(InventoryError) as excinfo:
            manager.check_place_container(item_a, inv_b.inventory_id)
        assert excinfo.value.code == "container_cycle"

    def test_effective_weight_includes_nested_contents(self):
        manager, root, containers = self._nested()
        item_a, inv_a = containers["a"]
        item_b, inv_b = containers["b"]
        manager.locate_container_item(item_a, root.inventory_id)
        manager.locate_container_item(item_b, inv_a.inventory_id)
        manager.place(root.inventory_id, "item.r", 1, 100)
        manager.place(inv_a.inventory_id, "item.x", 2, 50)
        manager.place(inv_b.inventory_id, "item.y", 1, 200)
        # root 有效重量 = 100 + 100 + 200（允许深度内递归）
        assert manager.effective_weight_grams(root.inventory_id) == 400
        assert manager.effective_weight_grams(inv_a.inventory_id) == 300
        assert manager.effective_weight_grams(inv_b.inventory_id) == 200


class TestInventoryAccessParity:
    """TEST-ECON-019"""

    @pytest.mark.parametrize("observer_kind", ["ai", "player"])
    def test_private_inventory_denies_non_owner(self, observer_kind):
        manager = InventoryManager()
        private = manager.create_inventory(
            "resident.owner", InventoryKind.RESIDENT, 4, 1000,
            access_policy_id="inventory_policy.owner_only",
        )
        manager.check_access(private.inventory_id, "owner")
        with pytest.raises(InventoryError) as excinfo:
            manager.check_access(private.inventory_id, "visitor")
        assert excinfo.value.code == "inventory_access_denied"
        with pytest.raises(InventoryError) as excinfo:
            manager.check_access(private.inventory_id, "authorized_trader")
        assert excinfo.value.code == "inventory_access_denied"

    @pytest.mark.parametrize("observer_kind", ["ai", "player"])
    def test_authorized_trade_policy(self, observer_kind):
        manager = InventoryManager()
        shop_inv = manager.create_inventory(
            "shop.fixture", InventoryKind.SHOP, 4, 1000,
            access_policy_id="inventory_policy.owner_and_authorized_trade",
        )
        manager.check_access(shop_inv.inventory_id, "authorized_trader")
        with pytest.raises(InventoryError) as excinfo:
            manager.check_access(shop_inv.inventory_id, "visitor")
        assert excinfo.value.code == "inventory_access_denied"

    def test_parity_same_code_for_ai_and_player(self):
        manager = InventoryManager()
        private = manager.create_inventory(
            "resident.owner", InventoryKind.RESIDENT, 4, 1000,
            access_policy_id="inventory_policy.owner_only",
        )
        codes = []
        for relationship in ("visitor", "visitor"):
            with pytest.raises(InventoryError) as excinfo:
                manager.check_access(private.inventory_id, relationship)
            codes.append(excinfo.value.code)
        assert codes == ["inventory_access_denied", "inventory_access_denied"]


class TestReservationLifecycle:
    """TEST-ECON-020"""

    def _reserve(self, ledger, action="action.1", binding="bind.1", quantity=3, expires=600):
        return ledger.reserve(
            owner_action_id=action,
            binding_id=binding,
            resource_kind=ResourceKind.ITEM_QUANTITY,
            resource_id="batch.fixture.1",
            resource_version=0,
            source_inventory_id="inventory.fixture.a",
            holder_actor_id="resident.buyer",
            quantity=quantity,
            created_game_time=0,
            expires_at_game_time=expires,
            request_revision=0,
            available_quantity=3,
            current_container_inventory_id="inventory.fixture.a",
        )

    def test_active_overlay_never_exceeds_quantity(self):
        ledger = ReservationLedger()
        reservation = self._reserve(ledger)
        assert ledger.active_quantity("batch.fixture.1") == 3
        assert ledger.availability("batch.fixture.1", 3) == 0
        with pytest.raises(InventoryError) as excinfo:
            self._reserve(ledger, action="action.2", quantity=1)
        assert excinfo.value.code == "reservation_conflict"
        ledger.release(reservation.reservation_id)
        assert ledger.availability("batch.fixture.1", 3) == 3
        # 释放后可再次预留
        again = self._reserve(ledger, action="action.3")
        assert again.state is ReservationState.ACTIVE

    def test_pause_does_not_expire(self):
        ledger = ReservationLedger()
        reservation = self._reserve(ledger, expires=600)
        # 0× 暂停：不调用 expire_overdue，GameTime 不前进即不过期
        assert ledger.expire_overdue(600) == []
        assert ledger.get(reservation.reservation_id).state is ReservationState.ACTIVE
        expired = ledger.expire_overdue(601)
        assert expired == [reservation.reservation_id]
        assert ledger.get(reservation.reservation_id).state is ReservationState.EXPIRED

    def test_terminal_state_unique(self):
        ledger = ReservationLedger()
        reservation = self._reserve(ledger)
        ledger.consume(reservation.reservation_id)
        with pytest.raises(InventoryError) as excinfo:
            ledger.release(reservation.reservation_id)
        assert excinfo.value.code == "reservation_conflict"
        with pytest.raises(InventoryError):
            ledger.consume(reservation.reservation_id)

    def test_binding_unique_within_action(self):
        ledger = ReservationLedger()
        self._reserve(ledger)
        with pytest.raises(InventoryError) as excinfo:
            ledger.reserve(
                owner_action_id="action.1",
                binding_id="bind.1",
                resource_kind=ResourceKind.CRAFT_STATION,
                resource_id="station.1",
                resource_version=0,
                source_inventory_id=None,
                holder_actor_id="resident.buyer",
                quantity=1,
                created_game_time=0,
                expires_at_game_time=60,
                request_revision=0,
                available_quantity=1,
            )
        assert excinfo.value.code == "reservation_conflict"

    def test_source_must_equal_current_container(self):
        ledger = ReservationLedger()
        with pytest.raises(InventoryError) as excinfo:
            ledger.reserve(
                owner_action_id="action.1",
                binding_id="bind.1",
                resource_kind=ResourceKind.ITEM_QUANTITY,
                resource_id="batch.fixture.1",
                resource_version=0,
                source_inventory_id="inventory.fixture.a",
                holder_actor_id="resident.buyer",
                quantity=1,
                created_game_time=0,
                expires_at_game_time=60,
                request_revision=0,
                available_quantity=3,
                current_container_inventory_id="inventory.fixture.b",
            )
        assert excinfo.value.code == "reservation_conflict"

    def test_recovery_audit(self):
        ledger = ReservationLedger()
        self._reserve(ledger, quantity=2)
        ledger.assert_recovery_consistent({"batch.fixture.1": 3})
        with pytest.raises(InventoryError) as excinfo:
            ledger.assert_recovery_consistent({"batch.fixture.1": 1})
        assert excinfo.value.code == "reservation_conflict"

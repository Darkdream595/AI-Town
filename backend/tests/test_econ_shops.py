"""
TEST-ECON-025..028：商店与服务（DOC-ECON-007）

- TEST-ECON-025：半开区间 [480,1080) 边界与跨午夜拆分
- TEST-ECON-026：stock/staff/node/capacity 组合的确定性拒绝
- TEST-ECON-027：服务完成与员工离岗取消退款
- TEST-ECON-028：Offer 披露对 AI/Player 一致且无隐藏字段
"""

import pytest

from src.economy import (
    OpeningInterval,
    ServiceDefinition,
    ServiceOrderManager,
    Shop,
    ShopError,
    ShopState,
    build_local_offer,
    can_accept_order,
    is_open_at,
    make_cross_midnight_intervals,
)


def _shop(intervals=None, state=ShopState.OPEN):
    return Shop(
        shop_id="shop.fixture.1",
        shop_definition_id="shop_def.fixture.1",
        sales_inventory_id="inventory.fixture.shop",
        revenue_account_id="account.fixture.shop",
        workplace_id="workplace.fixture.1",
        service_node_id="node.fixture.1",
        opening_intervals=intervals if intervals is not None else [OpeningInterval(0, 480, 1080)],
        required_staff_roles=["role.clerk"],
        service_definition_ids=["service.fixture.repair"],
        state=state,
    )


class TestOpeningIntervals:
    """TEST-ECON-025"""

    def test_half_open_boundaries(self):
        intervals = [OpeningInterval(0, 480, 1080)]
        states = [is_open_at(intervals, 0, minute) for minute in (479, 480, 1079, 1080)]
        assert states == [False, True, True, False]

    def test_reversed_or_empty_interval_rejected(self):
        with pytest.raises(ShopError) as excinfo:
            OpeningInterval(0, 1080, 480)
        assert excinfo.value.code == "opening_interval_invalid"
        with pytest.raises(ShopError):
            OpeningInterval(0, 600, 600)

    def test_cross_midnight_split(self):
        intervals = make_cross_midnight_intervals(0, 1200, 120)
        assert len(intervals) == 2
        assert is_open_at(intervals, 0, 1200)
        assert is_open_at(intervals, 0, 1439)
        assert not is_open_at(intervals, 0, 1199)
        assert is_open_at(intervals, 1, 0)
        assert is_open_at(intervals, 1, 119)
        assert not is_open_at(intervals, 1, 120)

    def test_same_day_not_split(self):
        intervals = make_cross_midnight_intervals(2, 480, 1080)
        assert intervals == [OpeningInterval(2, 480, 1080)]


class TestShopReservations:
    """TEST-ECON-026"""

    def test_can_accept_order_all_conditions(self):
        can_accept_order(_shop(), 0, 600, staff_covered=True, service_node_ready=True)

    def test_condition_combinations_deterministic(self):
        cases = [
            # (state, minute, staff, node, door, expected_code)
            (ShopState.OPEN, 479, True, True, True, "shop_closed"),
            (ShopState.TEMPORARILY_CLOSED, 600, True, True, True, "shop_closed"),
            (ShopState.SUSPENDED, 600, True, True, True, "shop_suspended"),
            (ShopState.DECOMMISSIONED, 600, True, True, True, "shop_suspended"),
            (ShopState.OPEN, 600, False, True, True, "staff_unavailable"),
            (ShopState.OPEN, 600, True, False, True, "service_node_unavailable"),
            (ShopState.OPEN, 600, True, True, False, "service_node_unavailable"),
        ]
        for state, minute, staff, node, door, expected in cases:
            with pytest.raises(ShopError) as excinfo:
                can_accept_order(
                    _shop(state=state), 0, minute,
                    staff_covered=staff, service_node_ready=node, door_unlocked=door,
                )
            assert excinfo.value.code == expected, (state, minute, staff, node, door)

    def test_service_capacity_full(self):
        shop = _shop()
        definition = ServiceDefinition(
            service_definition_id="service.fixture.repair",
            price_copper_feather=200,
            expected_duration_minutes=60,
            cancel_refund_bps=5000,
        )
        manager = ServiceOrderManager(service_capacity=1)
        first = manager.start_order(
            "cmd-order-1", shop, definition, "resident.buyer", 600,
            staff_covered=True, service_node_ready=True, day_index=0, minute=600,
        )
        assert first.state == "in_progress"
        with pytest.raises(ShopError) as excinfo:
            manager.start_order(
                "cmd-order-2", shop, definition, "resident.buyer2", 600,
                staff_covered=True, service_node_ready=True, day_index=0, minute=600,
            )
        assert excinfo.value.code in ("out_of_stock", "service_capacity_full")

    def test_start_order_idempotent(self):
        shop = _shop()
        definition = ServiceDefinition(
            service_definition_id="service.fixture.repair",
            price_copper_feather=200,
            expected_duration_minutes=60,
            cancel_refund_bps=5000,
        )
        manager = ServiceOrderManager(service_capacity=1)
        first = manager.start_order(
            "cmd-order-1", shop, definition, "resident.buyer", 600,
            True, True, 0, 600,
        )
        replay = manager.start_order(
            "cmd-order-1", shop, definition, "resident.buyer", 600,
            True, True, 0, 600,
        )
        assert replay.service_order_id == first.service_order_id


class TestServiceCancelRefund:
    """TEST-ECON-027"""

    def _definition(self, refund_bps=5000):
        return ServiceDefinition(
            service_definition_id="service.fixture.repair",
            price_copper_feather=200,
            expected_duration_minutes=60,
            cancel_refund_bps=refund_bps,
        )

    def test_complete_delivers_once(self):
        manager = ServiceOrderManager()
        order = manager.start_order(
            "cmd-1", _shop(), self._definition(), "resident.buyer", 600, True, True, 0, 600
        )
        completed = manager.complete_order("cmd-complete", order.service_order_id)
        assert completed.state == "completed"
        assert completed.delivered
        assert completed.refund_copper_feather == 0
        with pytest.raises(ShopError) as excinfo:
            manager.complete_order("cmd-complete-2", order.service_order_id)
        assert excinfo.value.code == "service_order_terminal"

    def test_staff_leave_cancels_with_policy_refund(self):
        manager = ServiceOrderManager()
        definition = self._definition(refund_bps=5000)
        order = manager.start_order(
            "cmd-1", _shop(), definition, "resident.buyer", 600, True, True, 0, 600
        )
        cancelled = manager.cancel_with_refund("cmd-cancel", order.service_order_id, definition)
        assert cancelled.state == "refunded"
        assert not cancelled.delivered  # 无部分交付
        assert cancelled.refund_copper_feather == 100  # floor(200 × 5000 / 10000)
        with pytest.raises(ShopError) as excinfo:
            manager.cancel_with_refund("cmd-cancel-2", order.service_order_id, definition)
        assert excinfo.value.code == "service_order_terminal"

    def test_zero_refund_policy(self):
        manager = ServiceOrderManager()
        definition = self._definition(refund_bps=0)
        order = manager.start_order(
            "cmd-1", _shop(), definition, "resident.buyer", 600, True, True, 0, 600
        )
        cancelled = manager.cancel_with_refund("cmd-cancel", order.service_order_id, definition)
        assert cancelled.refund_copper_feather == 0

    def test_refund_bps_range_validated(self):
        with pytest.raises(ShopError) as excinfo:
            ServiceDefinition("s", 100, 30, 10001)
        assert excinfo.value.code == "service_policy_invalid"


class TestOfferDisclosureParity:
    """TEST-ECON-028"""

    def test_ai_and_player_identical_offer(self):
        shop = _shop()
        offers = [{"item_definition_id": "item.potion.healing_small", "unit_price_copper_feather": 135}]
        ai_offer = build_local_offer(shop, True, 1080, offers, observer_kind="ai")
        player_offer = build_local_offer(shop, True, 1080, offers, observer_kind="player")
        assert ai_offer == player_offer

    def test_offer_has_no_hidden_fields(self):
        shop = _shop()
        offer = build_local_offer(
            _shop(), True, 1080,
            [{"item_definition_id": "item.potion.healing_small", "unit_price_copper_feather": 135}],
            observer_kind="player",
        )
        assert set(offer) == {
            "shop_id", "shop_definition_id", "state", "open_now",
            "next_opening_boundary_game_time", "offers", "service_definition_ids",
        }
        hidden_markers = ("cost", "stock", "staff", "margin", "inventory", "revenue")
        for key in offer:
            assert not any(marker in key for marker in hidden_markers)

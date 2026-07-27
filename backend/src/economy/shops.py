"""
商店与服务（DOC-ECON-007）

- RULE-ECON-025：开门条件 = Opening Interval + state=open + Staff Coverage + 服务节点可用
- RULE-ECON-026：sale 预留库存与买方容量；service 额外预留员工/slot/输入
- RULE-ECON-027：闭店不取消已提交 sale；服务按 Definition 完成或退款
- RULE-ECON-028：Offer 为权威 projection；Client/AI 声称不能绕过验证
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import ShopState


class ShopError(Exception):
    """商店操作失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class OpeningInterval:
    """半开区间 [start_minute, end_minute)；禁止 start > end 的模糊表达"""

    day_index: int
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if self.end_minute <= self.start_minute:
            raise ShopError(
                "opening_interval_invalid",
                f"[{self.start_minute},{self.end_minute}) is empty or reversed",
            )

    def contains(self, day_index: int, minute: int) -> bool:
        return self.day_index == day_index and self.start_minute <= minute < self.end_minute


def make_cross_midnight_intervals(
    day_index: int, start_minute: int, end_minute: int
) -> List[OpeningInterval]:
    """§7：跨午夜营业拆为两个 day interval"""
    if end_minute > start_minute:
        return [OpeningInterval(day_index, start_minute, end_minute)]
    return [
        OpeningInterval(day_index, start_minute, 1440),
        OpeningInterval(day_index + 1, 0, end_minute),
    ]


def is_open_at(intervals: List[OpeningInterval], day_index: int, minute: int) -> bool:
    return any(interval.contains(day_index, minute) for interval in intervals)


@dataclass
class Shop:
    """DES-ECON-007 的运行时形态"""

    shop_id: str
    shop_definition_id: str
    sales_inventory_id: str
    revenue_account_id: str
    workplace_id: str
    service_node_id: str
    opening_intervals: List[OpeningInterval]
    required_staff_roles: List[str]
    service_definition_ids: List[str]
    state: ShopState = ShopState.OPEN
    version: int = 0
    schema_version: int = 1


def can_accept_order(
    shop: Shop,
    day_index: int,
    minute: int,
    staff_covered: bool,
    service_node_ready: bool,
    door_unlocked: bool = True,
) -> None:
    """RULE-ECON-025/§7：全部权威条件满足才接受新订单"""
    if shop.state is ShopState.SUSPENDED or shop.state is ShopState.DECOMMISSIONED:
        raise ShopError("shop_suspended", shop.shop_id)
    if shop.state is ShopState.TEMPORARILY_CLOSED:
        raise ShopError("shop_closed", shop.shop_id)
    if not is_open_at(shop.opening_intervals, day_index, minute):
        raise ShopError("shop_closed", f"outside opening intervals at {day_index}:{minute}")
    if not staff_covered:
        raise ShopError("staff_unavailable", shop.shop_id)
    if not service_node_ready or not door_unlocked:
        raise ShopError("service_node_unavailable", shop.shop_id)


#: RULE-ECON-028/§9：Offer 只允许披露的公开字段
_OFFER_PUBLIC_FIELDS = frozenset(
    {
        "shop_id", "shop_definition_id", "state", "open_now",
        "next_opening_boundary_game_time", "offers", "service_definition_ids",
    }
)


def build_local_offer(
    shop: Shop,
    open_now: bool,
    next_boundary_game_time: int,
    offers: List[Dict],
    observer_kind: str,
) -> Dict:
    """
    RULE-ECON-028：本地 Offer 投影。

    observer_kind（player/ai）走完全同一构造路径（parity）；
    成本、完整库存、员工私人状态不进入 Offer。
    """
    offer = {
        "shop_id": shop.shop_id,
        "shop_definition_id": shop.shop_definition_id,
        "state": shop.state.value,
        "open_now": open_now,
        "next_opening_boundary_game_time": next_boundary_game_time,
        "offers": list(offers),
        "service_definition_ids": list(shop.service_definition_ids),
    }
    assert set(offer) <= _OFFER_PUBLIC_FIELDS, "offer disclosure boundary violated"
    return offer


@dataclass(frozen=True)
class ServiceDefinition:
    """输入资源、价格、交付条件与取消规则"""

    service_definition_id: str
    price_copper_feather: int
    expected_duration_minutes: int
    cancel_refund_bps: int  # 取消时按价格退款的比例（0..10000）
    input_resource_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (0 <= self.cancel_refund_bps <= 10000):
            raise ShopError("service_policy_invalid", "cancel_refund_bps out of range")


@dataclass
class ServiceOrder:
    """预留付款、资源、员工与服务位的 Transaction workflow"""

    service_order_id: str
    shop_id: str
    service_definition_id: str
    buyer_entity_id: str
    price_copper_feather: int
    started_game_time: int
    state: str = "in_progress"  # in_progress / completed / refunded
    delivered: bool = False
    refund_copper_feather: int = 0


class ServiceOrderManager:
    """RULE-ECON-027：服务明确完成或按策略退款，不静默吞款、无部分交付"""

    def __init__(self, service_capacity: int = 1) -> None:
        self._service_capacity = service_capacity
        self._orders: Dict[str, ServiceOrder] = {}
        self._command_results: Dict[str, ServiceOrder] = {}

    def start_order(
        self,
        command_id: str,
        shop: Shop,
        definition: ServiceDefinition,
        buyer_entity_id: str,
        game_time: int,
        staff_covered: bool,
        service_node_ready: bool,
        day_index: int,
        minute: int,
    ) -> ServiceOrder:
        if command_id in self._command_results:
            return self._command_results[command_id]
        can_accept_order(shop, day_index, minute, staff_covered, service_node_ready)
        active = sum(1 for o in self._orders.values() if o.state == "in_progress")
        if active >= self._service_capacity:
            raise ShopError("service_capacity_full", shop.shop_id)
        order = ServiceOrder(
            service_order_id=generate_ulid(),
            shop_id=shop.shop_id,
            service_definition_id=definition.service_definition_id,
            buyer_entity_id=buyer_entity_id,
            price_copper_feather=definition.price_copper_feather,
            started_game_time=game_time,
        )
        self._orders[order.service_order_id] = order
        self._command_results[command_id] = order
        return order

    def complete_order(self, command_id: str, service_order_id: str) -> ServiceOrder:
        order = self._require(service_order_id)
        if order.state != "in_progress":
            raise ShopError("service_order_terminal", order.state)
        order.state = "completed"
        order.delivered = True
        return order

    def cancel_with_refund(
        self, command_id: str, service_order_id: str, definition: ServiceDefinition
    ) -> ServiceOrder:
        """闭店中断/员工离岗按取消策略处理；无部分交付"""
        order = self._require(service_order_id)
        if order.state != "in_progress":
            raise ShopError("service_order_terminal", order.state)
        order.state = "refunded"
        order.delivered = False
        order.refund_copper_feather = (
            order.price_copper_feather * definition.cancel_refund_bps
        ) // 10000
        return order

    def _require(self, service_order_id: str) -> ServiceOrder:
        order = self._orders.get(service_order_id)
        if order is None:
            raise ShopError("service_order_unknown", service_order_id)
        return order

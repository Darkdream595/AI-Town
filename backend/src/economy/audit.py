"""
经济守恒、平衡与恢复测试（DOC-ECON-012）

- RULE-ECON-045：每事务后守恒检查（currency/ownership/quantity/capacity/Reservation）
- RULE-ECON-046：Recovery Barrier 解除前全量恢复审计
- RULE-ECON-047：0.5×..4× 相同 GameTime 终点相同 state hash；0× 不变
- RULE-ECON-048：模拟 envelope：无负余额/无界 Quote/永久 Reservation/无来源物品
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants import ItemState, ReservationState
from .currency import CurrencyLedger
from .inventory import InventoryManager, ReservationLedger
from .items import ItemRegistry
from .pricing import canonical_json


@dataclass(frozen=True)
class ConservationReport:
    """守恒审计结果；violations 为空即通过"""

    passed: bool
    violations: Tuple[str, ...]


def run_conservation_audit(
    currency_ledger: CurrencyLedger,
    item_registry: ItemRegistry,
    inventory_manager: InventoryManager,
    reservation_ledger: ReservationLedger,
    available_by_resource: Optional[Dict[str, int]] = None,
    allowlisted_net_delta: int = 0,
) -> ConservationReport:
    """
    RULE-ECON-045/046：增量/全量不变量检查。

    - Ledger 重放余额 == 已提交余额（source/sink 之外净 delta 为 allowlisted）
    - active Item/Batch 恰有一个 ownership 索引
    - stack quantity 为正整数
    - Inventory 缓存与重算一致
    - active Reservation 不超过可用量
    """
    violations: List[str] = []

    accounts = [currency_ledger.get(aid) for aid in currency_ledger.snapshot()]
    replayed = CurrencyLedger.replay(accounts, currency_ledger.events())
    committed = currency_ledger.snapshot()
    for account_id, balance in committed.items():
        if replayed.get(account_id, 0) + allowlisted_net_delta != balance and replayed.get(account_id, 0) != balance:
            violations.append(f"currency_replay_mismatch:{account_id}")
        if balance < 0:
            violations.append(f"negative_balance:{account_id}")

    for item_id, record in item_registry._instances.items():
        is_active = record["state"] == ItemState.ACTIVE.value
        indexed = item_registry.ownership_index_count(item_id) == 1
        if is_active != indexed:
            violations.append(f"unique_ownership_violation:{item_id}")
    for batch_id, record in item_registry._batches.items():
        is_active = record["state"] == ItemState.ACTIVE.value
        indexed = item_registry.ownership_index_count(batch_id) == 1
        if is_active != indexed:
            violations.append(f"batch_ownership_violation:{batch_id}")
        if is_active and record["quantity"] <= 0:
            violations.append(f"non_positive_quantity:{batch_id}")
        if not item_registry.provenance_chain(batch_id):
            violations.append(f"provenance_missing:{batch_id}")

    for inventory_id in list(inventory_manager._inventories):
        try:
            inventory_manager.assert_cache_consistent(inventory_id)
        except Exception as exc:  # noqa: BLE001 - 审计聚合所有违例
            violations.append(f"inventory_cache_mismatch:{inventory_id}:{exc}")

    if available_by_resource:
        for resource_id, available in available_by_resource.items():
            if reservation_ledger.active_quantity(resource_id) > available:
                violations.append(f"reservation_overcommit:{resource_id}")

    return ConservationReport(passed=not violations, violations=tuple(violations))


def economy_state_hash(
    currency_ledger: CurrencyLedger,
    extra_parts: Optional[Dict] = None,
) -> str:
    """RULE-ECON-047：速度等价比较的 state hash"""
    payload = {"balances": currency_ledger.snapshot()}
    if extra_parts:
        payload.update(extra_parts)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# -- Test Registry 契约（DOC-ECON-012 §5） --

_REGISTRY_REQUIRED_KEYS = frozenset({"test_id", "fixture_id", "case_id", "runner", "oracle", "command_sequence"})
_EXPECTED_TEST_IDS = frozenset(f"TEST-ECON-{index:03d}" for index in range(1, 45))


def validate_test_registry(registry: Dict) -> None:
    """
    TEST-ECON-045 的 registry 审计：恰好覆盖 TEST-ECON-001..044 且唯一，
    fixture 可解析、case/runner/oracle 非空、command_sequence 至少一项。
    """
    fixtures = {f["fixture_id"] for f in registry.get("fixtures", [])}
    cases = registry.get("cases", [])
    seen: set = set()
    for case in cases:
        missing = _REGISTRY_REQUIRED_KEYS - set(case)
        if missing:
            raise ValueError(f"registry case missing keys: {sorted(missing)}")
        test_id = case["test_id"]
        if test_id in seen:
            raise ValueError(f"duplicate test_id {test_id}")
        seen.add(test_id)
        if case["fixture_id"] not in fixtures:
            raise ValueError(f"unresolvable fixture {case['fixture_id']}")
        for field_name in ("case_id", "runner", "oracle"):
            if not case[field_name]:
                raise ValueError(f"empty {field_name} in {test_id}")
        if not case["command_sequence"]:
            raise ValueError(f"empty command_sequence in {test_id}")
    if seen != _EXPECTED_TEST_IDS:
        raise ValueError(
            f"registry must cover TEST-ECON-001..044 exactly: "
            f"missing={sorted(_EXPECTED_TEST_IDS - seen)} extra={sorted(seen - _EXPECTED_TEST_IDS)}"
        )


# -- Balance Envelope（RULE-ECON-048） --


@dataclass(frozen=True)
class BalanceEnvelope:
    """1/7/30 日模拟允许的有界范围"""

    max_unit_price_copper_feather: int
    max_active_reservations: int
    max_open_wage_claims: int
    max_shortage_streak: int
    min_total_currency: int = 0


@dataclass(frozen=True)
class SimulationObservation:
    """模拟终点的最小观测"""

    game_days: int
    max_seen_unit_price: int
    max_seen_active_reservations: int
    open_wage_claims: int
    max_shortage_streak: int
    min_seen_balance: int
    total_currency_delta_outside_allowlist: int
    unowned_active_items: int


def check_balance_envelope(
    observation: SimulationObservation, envelope: BalanceEnvelope
) -> Tuple[str, ...]:
    """RULE-ECON-048：任一越界即违例（返回空元组 = 通过）"""
    violations: List[str] = []
    if observation.max_seen_unit_price > envelope.max_unit_price_copper_feather:
        violations.append("unbounded_quote")
    if observation.max_seen_active_reservations > envelope.max_active_reservations:
        violations.append("permanent_active_reservation")
    if observation.open_wage_claims > envelope.max_open_wage_claims:
        violations.append("unbounded_wage_claims")
    if observation.max_shortage_streak > envelope.max_shortage_streak:
        violations.append("unbounded_shortage")
    if observation.min_seen_balance < 0:
        violations.append("negative_balance")
    if observation.total_currency_delta_outside_allowlist != 0:
        violations.append("unsourced_currency")
    if observation.unowned_active_items > 0:
        violations.append("unsourced_item")
    return tuple(violations)

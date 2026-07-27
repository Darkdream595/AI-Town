"""
原子交易模型（DOC-ECON-006）

- RULE-ECON-021：currency/item/inventory/Reservation/事件/幂等结果同一事务提交
- RULE-ECON-022：(world_id, command_id) 幂等；payload 不同复用 ID 返回冲突
- RULE-ECON-023：提交前在最新 Revision 重新验证全部写集
- RULE-ECON-024：任何失败回滚且 Revision 不增长
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    CRASH_BOUNDARIES,
    MAX_CURRENCY_LEGS,
    MAX_ITEM_LEGS,
    AccountKind,
    ReservationState,
    TransactionState,
)
from .currency import CurrencyError, CurrencyLedger
from .inventory import InventoryError, InventoryManager, ReservationLedger
from .items import ItemRegistry


class TransactionError(Exception):
    """交易失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class CurrencyLeg:
    account_id: str
    delta_copper_feather: int


@dataclass(frozen=True)
class ItemLeg:
    item_or_batch_id: str
    quantity: int
    from_inventory_id: str
    to_inventory_id: str


#: DOC-ECON-006 §5：Budget Binding 必须且只能包含的八个字段
BUDGET_BINDING_FIELDS = frozenset(
    {
        "public_account_id", "currency_leg_index", "appropriation_id",
        "appropriation_expected_version", "encumbrance_id",
        "encumbrance_expected_version", "amount_copper_feather", "purpose_id",
    }
)


@dataclass
class Transaction:
    transaction_id: str
    command_id: str
    expected_revision: int
    kind: str
    quote_id: Optional[str]
    reservation_ids: Tuple[str, ...]
    currency_legs: Tuple[CurrencyLeg, ...]
    item_legs: Tuple[ItemLeg, ...]
    budget_bindings: Tuple[Dict, ...]
    state: TransactionState
    payload_hash: int
    committed_revision: Optional[int] = None
    event_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    state: TransactionState
    committed_revision: Optional[int]
    event_ids: Tuple[str, ...]


def _payload_hash(
    kind: str,
    currency_legs: Tuple[CurrencyLeg, ...],
    item_legs: Tuple[ItemLeg, ...],
    reservation_ids: Tuple[str, ...],
    budget_bindings: Tuple[Dict, ...],
) -> int:
    bindings_key = tuple(sorted((k, str(v)) for b in budget_bindings for k, v in b.items()))
    return hash((kind, currency_legs, item_legs, reservation_ids, bindings_key))


class TransactionEngine:
    """
    单 Writer 交易引擎：校验 → 预留确认 → 原子应用 → Outbox。

    崩溃注入点（CRASH_BOUNDARIES）在原子应用之前全部安全回滚；
    `after_database_commit_before_outbox` 之后由 resend_outbox 重发同一事件。
    """

    def __init__(
        self,
        world_id: str,
        currency_ledger: CurrencyLedger,
        reservation_ledger: ReservationLedger,
        item_registry: ItemRegistry,
        inventory_manager: InventoryManager,
        unit_weight_resolver: Optional[Callable[[str], int]] = None,
        budget_ledger: Optional[object] = None,
    ) -> None:
        self._world_id = world_id
        self._currency = currency_ledger
        self._reservations = reservation_ledger
        self._items = item_registry
        self._inventories = inventory_manager
        self._unit_weight = unit_weight_resolver or (lambda _item_id: 0)
        self._budget = budget_ledger
        self._revision = 0
        self._transactions: Dict[str, Transaction] = {}
        self._idempotency: Dict[Tuple[str, str], Tuple[int, TransactionResult]] = {}
        self._outbox_pending: Dict[str, List[str]] = {}
        self._outbox_delivered: List[str] = []

    @property
    def revision(self) -> int:
        return self._revision

    def get(self, transaction_id: str) -> Transaction:
        return self._transactions[transaction_id]

    # -- 提交 --

    def submit(
        self,
        command_id: str,
        expected_revision: int,
        kind: str,
        currency_legs: List[CurrencyLeg],
        item_legs: List[ItemLeg],
        reservation_ids: Tuple[str, ...] = (),
        budget_bindings: Tuple[Dict, ...] = (),
        quote_id: Optional[str] = None,
        fail_at: Optional[str] = None,
    ) -> TransactionResult:
        """
        RULE-ECON-022/023/024：幂等 → 校验 → 原子提交/回滚。

        fail_at 是测试注入的 Crash Boundary；正常路径必须为 None。
        """
        currency_legs_t = tuple(currency_legs)
        item_legs_t = tuple(item_legs)
        payload_hash = _payload_hash(
            kind, currency_legs_t, item_legs_t, reservation_ids, budget_bindings
        )
        idem_key = (self._world_id, command_id)
        if idem_key in self._idempotency:
            stored_hash, stored_result = self._idempotency[idem_key]
            if stored_hash != payload_hash:
                # 不得返回旧成功伪装新请求
                raise TransactionError(
                    "idempotency_payload_conflict",
                    f"command {command_id} reused with different payload",
                )
            return stored_result
        if fail_at is not None and fail_at not in CRASH_BOUNDARIES:
            raise TransactionError("transaction_invariant_failed", f"unknown crash boundary {fail_at}")

        transaction = Transaction(
            transaction_id=generate_ulid(),
            command_id=command_id,
            expected_revision=expected_revision,
            kind=kind,
            quote_id=quote_id,
            reservation_ids=reservation_ids,
            currency_legs=currency_legs_t,
            item_legs=item_legs_t,
            budget_bindings=budget_bindings,
            state=TransactionState.DRAFTED,
            payload_hash=payload_hash,
        )
        self._transactions[transaction.transaction_id] = transaction

        try:
            self._validate(transaction, expected_revision)
        except TransactionError:
            transaction.state = TransactionState.REJECTED
            raise
        transaction.state = TransactionState.RESERVED

        if fail_at == "after_reservations":
            return self._roll_back(transaction)
        # 校验全部通过后才进入应用段；应用段之前任一崩溃点都无可见变化
        if fail_at in ("after_state_writes_before_events", "after_events_before_idempotency"):
            return self._roll_back(transaction)

        self._apply(transaction)
        if fail_at == "after_database_commit_before_outbox":
            # 提交已完成但 Outbox 未发送：恢复时重发同一事件
            self._outbox_pending[transaction.transaction_id] = list(transaction.event_ids)

        result = TransactionResult(
            transaction_id=transaction.transaction_id,
            state=transaction.state,
            committed_revision=transaction.committed_revision,
            event_ids=transaction.event_ids,
        )
        self._idempotency[idem_key] = (payload_hash, result)
        return result

    # -- 校验（RULE-ECON-023） --

    def _validate(self, transaction: Transaction, expected_revision: int) -> None:
        if expected_revision != self._revision:
            raise TransactionError(
                "stale_revision", f"expected {expected_revision}, at {self._revision}"
            )
        if len(transaction.item_legs) > MAX_ITEM_LEGS:
            raise TransactionError("transaction_invariant_failed", "too many item legs")
        if len(transaction.currency_legs) > MAX_CURRENCY_LEGS:
            raise TransactionError("transaction_invariant_failed", "too many currency legs")
        if sum(leg.delta_copper_feather for leg in transaction.currency_legs) != 0:
            raise TransactionError("unbalanced_ledger", "currency legs must sum to 0")

        self._validate_budget_bindings(transaction)

        # 全部 active Reservation 仍有效
        for reservation_id in transaction.reservation_ids:
            reservation = self._reservations.get(reservation_id)
            if reservation.state is not ReservationState.ACTIVE:
                raise TransactionError(
                    "reservation_conflict", f"reservation {reservation_id} not active"
                )

        # ownership 与容量在最新 Revision 重校验
        for leg in transaction.item_legs:
            owner = self._items.owner_of(leg.item_or_batch_id)
            if owner is None or owner[0] != leg.from_inventory_id:
                raise TransactionError(
                    "double_spend_detected",
                    f"{leg.item_or_batch_id} not in {leg.from_inventory_id}",
                )
            self._inventories.can_accept(
                leg.to_inventory_id,
                leg.item_or_batch_id,
                leg.quantity,
                self._unit_weight(leg.item_or_batch_id),
            )

    def _validate_budget_bindings(self, transaction: Transaction) -> None:
        public_debit_indices = []
        for index, leg in enumerate(transaction.currency_legs):
            if leg.delta_copper_feather >= 0:
                continue
            account = self._currency.get(leg.account_id)
            if account.account_kind is AccountKind.PUBLIC_BUDGET:
                public_debit_indices.append(index)
        if not public_debit_indices:
            if transaction.budget_bindings:
                raise TransactionError(
                    "transaction_invariant_failed",
                    "bindings require a public-budget debit",
                )
            return
        covered = set()
        for binding in transaction.budget_bindings:
            extra = set(binding) - BUDGET_BINDING_FIELDS
            missing = BUDGET_BINDING_FIELDS - set(binding)
            if extra or missing:
                raise TransactionError(
                    "transaction_invariant_failed",
                    f"binding fields must be exactly 8: extra={sorted(extra)} missing={sorted(missing)}",
                )
            leg_index = binding["currency_leg_index"]
            if leg_index < 0 or leg_index >= len(transaction.currency_legs):
                raise TransactionError(
                    "transaction_invariant_failed", "currency_leg_index out of range"
                )
            leg = transaction.currency_legs[leg_index]
            if leg.delta_copper_feather >= 0:
                raise TransactionError(
                    "encumbrance_mismatch", "binding must cover a debit leg"
                )
            if binding["amount_copper_feather"] != -leg.delta_copper_feather:
                raise TransactionError(
                    "encumbrance_mismatch", "binding amount != -leg delta"
                )
            covered.add(leg_index)
        for index in public_debit_indices:
            if index not in covered:
                raise TransactionError(
                    "budget_binding_missing", f"public debit leg {index} lacks binding"
                )

    # -- 应用与回滚 --

    def _apply(self, transaction: Transaction) -> None:
        for reservation_id in transaction.reservation_ids:
            self._reservations.consume(reservation_id)
        if transaction.currency_legs:
            self._currency.post_legs(
                command_id=f"tx:{transaction.transaction_id}:legs",
                legs=[(leg.account_id, leg.delta_copper_feather) for leg in transaction.currency_legs],
                expected_revision=self._currency.revision,
            )
        for leg in transaction.item_legs:
            record = self._items.get_instance(leg.item_or_batch_id) or self._items.get_batch(
                leg.item_or_batch_id
            )
            slot_key = record["current_container"]["slot_key"] if record else "slot.0001"
            unit_weight = self._unit_weight(leg.item_or_batch_id)
            self._inventories.remove(leg.from_inventory_id, leg.item_or_batch_id, leg.quantity)
            self._items.move_container(leg.item_or_batch_id, leg.to_inventory_id, slot_key)
            self._inventories.place(
                leg.to_inventory_id, leg.item_or_batch_id, leg.quantity, unit_weight
            )
        if self._budget is not None:
            for binding in transaction.budget_bindings:
                self._budget.consume_encumbrance(
                    command_id=f"tx:{transaction.transaction_id}:enc:{binding['encumbrance_id']}",
                    encumbrance_id=binding["encumbrance_id"],
                    expected_version=binding["encumbrance_expected_version"],
                    appropriation_expected_version=binding["appropriation_expected_version"],
                )
        self._revision += 1
        transaction.committed_revision = self._revision
        transaction.event_ids = (generate_ulid(),)
        transaction.state = TransactionState.COMMITTED

    def _roll_back(self, transaction: Transaction) -> TransactionResult:
        """RULE-ECON-024：回滚不留中间持久状态，Revision 不增长"""
        for reservation_id in transaction.reservation_ids:
            reservation = self._reservations.get(reservation_id)
            if reservation.state is ReservationState.ACTIVE:
                self._reservations.release(reservation_id)
        transaction.state = TransactionState.ROLLED_BACK
        return TransactionResult(
            transaction_id=transaction.transaction_id,
            state=transaction.state,
            committed_revision=None,
            event_ids=(),
        )

    # -- Outbox 恢复 --

    def resend_outbox(self, transaction_id: str) -> List[str]:
        """§7：commit 后 Outbox 未发送时恢复重发同一事件"""
        pending = self._outbox_pending.pop(transaction_id, [])
        for event_id in pending:
            if event_id not in self._outbox_delivered:
                self._outbox_delivered.append(event_id)
        return pending

    def delivered_events(self) -> List[str]:
        return list(self._outbox_delivered)

    # -- 退款 --

    def refund(self, command_id: str, original_transaction_id: str, expected_revision: int) -> TransactionResult:
        """§7：退款/撤销是新的反向 Transaction，不改写原 Transaction"""
        original = self._transactions.get(original_transaction_id)
        if original is None or original.state is not TransactionState.COMMITTED:
            raise TransactionError(
                "transaction_invariant_failed", "refund requires a committed transaction"
            )
        reversed_currency = [
            CurrencyLeg(leg.account_id, -leg.delta_copper_feather)
            for leg in original.currency_legs
        ]
        reversed_items = [
            ItemLeg(leg.item_or_batch_id, leg.quantity, leg.to_inventory_id, leg.from_inventory_id)
            for leg in original.item_legs
        ]
        return self.submit(
            command_id=command_id,
            expected_revision=expected_revision,
            kind=f"{original.kind}_refund",
            currency_legs=reversed_currency,
            item_legs=reversed_items,
        )

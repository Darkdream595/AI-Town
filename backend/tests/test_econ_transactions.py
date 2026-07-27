"""
TEST-ECON-021..024：原子交易模型（DOC-ECON-006）

- TEST-ECON-021：含税费 sale 单事务原子可见
- TEST-ECON-022：(world, command) 幂等与 payload hash 冲突
- TEST-ECON-023：最后一件 unique 并发购买只有一个 committed
- TEST-ECON-024：四个 Crash Boundary 全成或全败、Outbox 重发、退款新事务
"""

import pytest

from src.economy import (
    AccountKind,
    CurrencyLedger,
    CurrencyLeg,
    InventoryKind,
    InventoryManager,
    ItemLeg,
    ItemRegistry,
    ReservationLedger,
    ReservationState,
    ResourceKind,
    TransactionEngine,
    TransactionError,
    TransactionState,
)

AUTHORITIES = frozenset({"world_bootstrap"})

_UNIQUE_DEFINITION = {
    "schema_version": 1,
    "item_definition_id": "item.fixture.unique",
    "item_kind": "unique",
    "display_name_key": "item.name.unique",
    "unit_weight_grams": 100,
    "max_stack_quantity": 1,
    "tags": [],
    "quality_grade_min": 0,
    "quality_grade_max": 9,
    "kind_config": {},
}


def _engine_with_shop():
    ledger = CurrencyLedger()
    buyer = ledger.open_account("cmd-open-b", "resident.buyer", AccountKind.RESIDENT, 0)
    seller = ledger.open_account("cmd-open-s", "shop.seller", AccountKind.SHOP, 0)
    public = ledger.open_account("cmd-open-p", "town.public", AccountKind.PUBLIC_BUDGET, 0)
    ledger.mint("cmd-mint-b", buyer.account_id, 110, "world_bootstrap", AUTHORITIES)
    items = ItemRegistry()
    items.register_definition(dict(_UNIQUE_DEFINITION))
    inventories = InventoryManager()
    shop_inv = inventories.create_inventory("shop.seller", InventoryKind.SHOP, 10, 100000)
    buyer_inv = inventories.create_inventory("resident.buyer", InventoryKind.RESIDENT, 10, 100000)
    item = items.create_instance(
        "item.fixture.unique", shop_inv.inventory_id, "slot.1", "event.stock", 0
    )
    inventories.place(shop_inv.inventory_id, item["item_id"], 1, 0)
    reservations = ReservationLedger()
    engine = TransactionEngine("world.fixture", ledger, reservations, items, inventories)
    return {
        "engine": engine, "ledger": ledger, "items": items, "inventories": inventories,
        "reservations": reservations, "buyer": buyer, "seller": seller, "public": public,
        "shop_inv": shop_inv, "buyer_inv": buyer_inv, "item": item,
    }


def _sale_legs(ctx, total=110, tax=10):
    return [
        CurrencyLeg(ctx["buyer"].account_id, -total),
        CurrencyLeg(ctx["seller"].account_id, total - tax),
        CurrencyLeg(ctx["public"].account_id, tax),
    ]


def _item_leg(ctx):
    return [ItemLeg(
        ctx["item"]["item_id"], 1,
        ctx["shop_inv"].inventory_id, ctx["buyer_inv"].inventory_id,
    )]


class TestAtomicSale:
    """TEST-ECON-021"""

    def test_sale_with_tax_single_revision(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        revision_before = engine.revision
        result = engine.submit(
            "cmd-sale-1", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx),
        )
        assert result.state is TransactionState.COMMITTED
        assert engine.revision - revision_before == 1
        assert result.committed_revision == engine.revision
        assert len(result.event_ids) == 1
        # 货币、物品、事件同一 Revision 后全部可见
        assert ctx["ledger"].get(ctx["buyer"].account_id).balance_copper_feather == 0
        assert ctx["ledger"].get(ctx["seller"].account_id).balance_copper_feather == 100
        assert ctx["ledger"].get(ctx["public"].account_id).balance_copper_feather == 10
        assert ctx["items"].owner_of(ctx["item"]["item_id"])[0] == ctx["buyer_inv"].inventory_id
        ctx["inventories"].assert_cache_consistent(ctx["shop_inv"].inventory_id)
        ctx["inventories"].assert_cache_consistent(ctx["buyer_inv"].inventory_id)

    def test_unbalanced_legs_rejected(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        legs = [CurrencyLeg(ctx["buyer"].account_id, -100)]
        with pytest.raises(TransactionError) as excinfo:
            engine.submit("cmd-bad", engine.revision, "shop_sale", legs, [])
        assert excinfo.value.code == "unbalanced_ledger"
        assert engine.revision == 0

    def test_stale_revision_rejected(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        with pytest.raises(TransactionError) as excinfo:
            engine.submit("cmd-stale", engine.revision + 1, "shop_sale", _sale_legs(ctx), _item_leg(ctx))
        assert excinfo.value.code == "stale_revision"


class TestPayloadHashIdempotency:
    """TEST-ECON-022"""

    def test_same_command_same_payload_returns_original(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        first = engine.submit("cmd-x", engine.revision, "shop_sale", _sale_legs(ctx), _item_leg(ctx))
        replay = engine.submit("cmd-x", engine.revision, "shop_sale", _sale_legs(ctx), _item_leg(ctx))
        assert replay.transaction_id == first.transaction_id
        assert engine.revision == 1  # commit 只发生一次

    def test_same_command_different_payload_conflict(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        engine.submit("cmd-x", engine.revision, "shop_sale", _sale_legs(ctx), _item_leg(ctx))
        with pytest.raises(TransactionError) as excinfo:
            engine.submit(
                "cmd-x", engine.revision, "shop_sale",
                _sale_legs(ctx, total=100, tax=10), _item_leg(ctx),
            )
        assert excinfo.value.code == "idempotency_payload_conflict"


class TestLastItemDoubleSpend:
    """TEST-ECON-023"""

    def test_concurrent_buyers_only_one_commits(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        reservations = ctx["reservations"]
        item_id = ctx["item"]["item_id"]

        def _reserve(action_id):
            return reservations.reserve(
                owner_action_id=action_id, binding_id="buy.unique",
                resource_kind=ResourceKind.UNIQUE_ITEM, resource_id=item_id,
                resource_version=0,
                source_inventory_id=ctx["shop_inv"].inventory_id,
                holder_actor_id=action_id, quantity=1,
                created_game_time=0, expires_at_game_time=60, request_revision=0,
                available_quantity=1,
                current_container_inventory_id=ctx["shop_inv"].inventory_id,
            )

        winner = _reserve("action.buy.a")
        with pytest.raises(Exception) as excinfo:
            _reserve("action.buy.b")
        assert excinfo.value.code == "reservation_conflict"

        result = engine.submit(
            "cmd-sale-a", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx), reservation_ids=(winner.reservation_id,),
        )
        assert result.state is TransactionState.COMMITTED
        assert ctx["items"].ownership_index_count(item_id) == 1
        assert reservations.get(winner.reservation_id).state is ReservationState.CONSUMED

        # 败者即使拿到旧 Reservation/位置信息也无法再提交同一物品
        ctx["buyer2"] = ctx["ledger"].open_account("cmd-open-b2", "resident.buyer2", AccountKind.RESIDENT, 0)
        ctx["ledger"].mint("cmd-mint-b2", ctx["buyer2"].account_id, 110, "world_bootstrap", AUTHORITIES)
        legs = [
            CurrencyLeg(ctx["buyer2"].account_id, -110),
            CurrencyLeg(ctx["seller"].account_id, 100),
            CurrencyLeg(ctx["public"].account_id, 10),
        ]
        with pytest.raises(TransactionError) as excinfo:
            engine.submit("cmd-sale-b", engine.revision, "shop_sale", legs, _item_leg(ctx))
        assert excinfo.value.code == "double_spend_detected"
        assert engine.revision == 1

    def test_consumed_reservation_cannot_commit_again(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        reservations = ctx["reservations"]
        reservation = reservations.reserve(
            owner_action_id="action.buy.a", binding_id="buy.unique",
            resource_kind=ResourceKind.UNIQUE_ITEM, resource_id=ctx["item"]["item_id"],
            resource_version=0,
            source_inventory_id=ctx["shop_inv"].inventory_id,
            holder_actor_id="action.buy.a", quantity=1,
            created_game_time=0, expires_at_game_time=60, request_revision=0,
            available_quantity=1,
            current_container_inventory_id=ctx["shop_inv"].inventory_id,
        )
        engine.submit(
            "cmd-sale-a", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx), reservation_ids=(reservation.reservation_id,),
        )
        with pytest.raises(TransactionError) as excinfo:
            engine.submit(
                "cmd-sale-c", engine.revision, "shop_sale",
                _sale_legs(ctx), [], reservation_ids=(reservation.reservation_id,),
            )
        assert excinfo.value.code == "reservation_conflict"


class TestCrashAndRefund:
    """TEST-ECON-024"""

    @pytest.mark.parametrize(
        "boundary",
        ["after_reservations", "after_state_writes_before_events", "after_events_before_idempotency"],
    )
    def test_pre_commit_boundaries_leave_no_partial_state(self, boundary):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        reservations = ctx["reservations"]
        reservation = reservations.reserve(
            owner_action_id="action.buy.a", binding_id="buy.unique",
            resource_kind=ResourceKind.UNIQUE_ITEM, resource_id=ctx["item"]["item_id"],
            resource_version=0,
            source_inventory_id=ctx["shop_inv"].inventory_id,
            holder_actor_id="action.buy.a", quantity=1,
            created_game_time=0, expires_at_game_time=60, request_revision=0,
            available_quantity=1,
            current_container_inventory_id=ctx["shop_inv"].inventory_id,
        )
        balances_before = ctx["ledger"].snapshot()
        result = engine.submit(
            "cmd-crash", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx),
            reservation_ids=(reservation.reservation_id,), fail_at=boundary,
        )
        assert result.state is TransactionState.ROLLED_BACK
        assert engine.revision == 0
        assert ctx["ledger"].snapshot() == balances_before
        assert ctx["items"].owner_of(ctx["item"]["item_id"])[0] == ctx["shop_inv"].inventory_id
        # 回滚释放 Reservation，恢复后可重新提交且最多 commit 一次
        assert reservations.get(reservation.reservation_id).state is ReservationState.RELEASED
        second = reservations.reserve(
            owner_action_id="action.buy.b", binding_id="buy.unique",
            resource_kind=ResourceKind.UNIQUE_ITEM, resource_id=ctx["item"]["item_id"],
            resource_version=0,
            source_inventory_id=ctx["shop_inv"].inventory_id,
            holder_actor_id="action.buy.b", quantity=1,
            created_game_time=0, expires_at_game_time=60, request_revision=0,
            available_quantity=1,
            current_container_inventory_id=ctx["shop_inv"].inventory_id,
        )
        retry = engine.submit(
            "cmd-retry", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx), reservation_ids=(second.reservation_id,),
        )
        assert retry.state is TransactionState.COMMITTED
        assert engine.revision == 1

    def test_post_commit_boundary_resends_outbox(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        result = engine.submit(
            "cmd-crash-outbox", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx),
            fail_at="after_database_commit_before_outbox",
        )
        assert result.state is TransactionState.COMMITTED
        assert engine.revision == 1
        assert engine.delivered_events() == []
        resent = engine.resend_outbox(result.transaction_id)
        assert list(resent) == list(result.event_ids)
        assert engine.delivered_events() == list(result.event_ids)
        # 重发幂等：第二次不产生重复事件
        assert engine.resend_outbox(result.transaction_id) == []
        assert engine.delivered_events() == list(result.event_ids)

    def test_unknown_boundary_rejected(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        with pytest.raises(TransactionError) as excinfo:
            engine.submit(
                "cmd-bad-boundary", engine.revision, "shop_sale",
                _sale_legs(ctx), _item_leg(ctx), fail_at="after_everything",
            )
        assert excinfo.value.code == "transaction_invariant_failed"

    def test_refund_is_new_reverse_transaction(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        ledger = ctx["ledger"]
        # 无税 sale：buyer -100, seller +100
        legs = [
            CurrencyLeg(ctx["buyer"].account_id, -100),
            CurrencyLeg(ctx["seller"].account_id, 100),
        ]
        result = engine.submit("cmd-sale-1", engine.revision, "shop_sale", legs, _item_leg(ctx))
        refund = engine.refund("cmd-refund-1", result.transaction_id, engine.revision)
        assert refund.transaction_id != result.transaction_id
        assert refund.state is TransactionState.COMMITTED
        # 退款后货币与物品都回到原状
        assert ledger.get(ctx["buyer"].account_id).balance_copper_feather == 110
        assert ledger.get(ctx["seller"].account_id).balance_copper_feather == 0
        assert ctx["items"].owner_of(ctx["item"]["item_id"])[0] == ctx["shop_inv"].inventory_id
        # 原 Transaction 不被改写
        assert engine.get(result.transaction_id).state is TransactionState.COMMITTED

    def test_refund_of_public_credit_requires_binding(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        # 含公共税的 sale：退款的反向 legs 会从 PUBLIC_BUDGET 扣款，必须带 binding
        result = engine.submit(
            "cmd-sale-tax", engine.revision, "shop_sale",
            _sale_legs(ctx), _item_leg(ctx),
        )
        with pytest.raises(TransactionError) as excinfo:
            engine.refund("cmd-refund-tax", result.transaction_id, engine.revision)
        assert excinfo.value.code == "budget_binding_missing"

    def test_refund_requires_committed_original(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        with pytest.raises(TransactionError) as excinfo:
            engine.refund("cmd-refund-x", "tx.ghost", engine.revision)
        assert excinfo.value.code == "transaction_invariant_failed"

    def test_budget_binding_requires_exact_fields(self):
        ctx = _engine_with_shop()
        engine = ctx["engine"]
        ledger = ctx["ledger"]
        ledger.mint("cmd-mint-p", ctx["public"].account_id, 5000, "world_bootstrap", AUTHORITIES)
        contractor = ledger.open_account("cmd-open-c", "resident.contractor", AccountKind.RESIDENT, 0)
        legs = [
            CurrencyLeg(ctx["public"].account_id, -1000),
            CurrencyLeg(contractor.account_id, 1000),
        ]
        binding = {
            "public_account_id": ctx["public"].account_id,
            "currency_leg_index": 0,
            "appropriation_id": "appropriation.1",
            "appropriation_expected_version": 1,
            "encumbrance_id": "encumbrance.1",
            "encumbrance_expected_version": 1,
            "amount_copper_feather": 1000,
            "purpose_id": "purpose.road",
        }
        with pytest.raises(TransactionError) as excinfo:
            engine.submit(
                "cmd-bind-extra", engine.revision, "public_works",
                legs, [], budget_bindings=({**binding, "note": "off-book"},),
            )
        assert excinfo.value.code == "transaction_invariant_failed"
        with pytest.raises(TransactionError) as excinfo:
            engine.submit(
                "cmd-bind-missing", engine.revision, "public_works",
                legs, [],
                budget_bindings=({k: v for k, v in binding.items() if k != "purpose_id"},),
            )
        assert excinfo.value.code == "transaction_invariant_failed"
        # 公共 debit leg 缺 binding 拒绝
        with pytest.raises(TransactionError) as excinfo:
            engine.submit("cmd-bind-none", engine.revision, "public_works", legs, [])
        assert excinfo.value.code == "budget_binding_missing"

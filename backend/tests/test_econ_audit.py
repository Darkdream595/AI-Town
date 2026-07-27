"""
TEST-ECON-045..048：经济守恒、平衡与恢复测试（DOC-ECON-012）

- TEST-ECON-045：场景审计通过；注入违例必检出
- TEST-ECON-046：Snapshot/Event 重放与恢复审计一致
- TEST-ECON-047：不同批量同 state hash；暂停不变
- TEST-ECON-048：registry 契约校验与 30 日 envelope 边界
"""

import pytest

from src.economy import (
    AccountKind,
    BalanceEnvelope,
    CurrencyLedger,
    InventoryKind,
    InventoryManager,
    ItemRegistry,
    ReservationLedger,
    ResourceKind,
    SimulationObservation,
    check_balance_envelope,
    economy_state_hash,
    run_conservation_audit,
    validate_test_registry,
)

AUTHORITIES = frozenset({"world_bootstrap"})

_STACKABLE_DEFINITION = {
    "schema_version": 1,
    "item_definition_id": "item.fixture.stackable",
    "item_kind": "stackable",
    "display_name_key": "item.name.stackable",
    "unit_weight_grams": 100,
    "max_stack_quantity": 99,
    "tags": [],
    "quality_grade_min": 0,
    "quality_grade_max": 9,
    "kind_config": {"merge_field_ids": ["quality_grade", "condition_key"]},
}

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


def _scenario():
    """最小守恒场景：mint 入账 + 转账 + unique/batch + 库存缓存 + Reservation"""
    ledger = CurrencyLedger()
    buyer = ledger.open_account("cmd-open-b", "resident.buyer", AccountKind.RESIDENT, 0)
    seller = ledger.open_account("cmd-open-s", "shop.seller", AccountKind.SHOP, 0)
    ledger.mint("cmd-mint", buyer.account_id, 1000, "world_bootstrap", AUTHORITIES)
    ledger.post_legs(
        "cmd-transfer",
        [(buyer.account_id, -300), (seller.account_id, 300)],
        ledger.revision,
    )
    items = ItemRegistry()
    items.register_definition(dict(_UNIQUE_DEFINITION))
    items.register_definition(dict(_STACKABLE_DEFINITION))
    inventories = InventoryManager()
    shop_inv = inventories.create_inventory("shop.seller", InventoryKind.SHOP, 10, 100000)
    item = items.create_instance(
        "item.fixture.unique", shop_inv.inventory_id, "slot.1", "event.stock", 0
    )
    batch = items.create_batch(
        "item.fixture.stackable", 10, shop_inv.inventory_id, "slot.2", "event.stock", 0
    )
    inventories.place(shop_inv.inventory_id, item["item_id"], 1, 100)
    inventories.place(shop_inv.inventory_id, batch["batch_id"], 10, 100)
    reservations = ReservationLedger()
    reservations.reserve(
        owner_action_id="action.hold", binding_id="hold.batch",
        resource_kind=ResourceKind.ITEM_QUANTITY, resource_id=batch["batch_id"],
        resource_version=0, source_inventory_id=shop_inv.inventory_id,
        holder_actor_id="resident.buyer", quantity=2,
        created_game_time=0, expires_at_game_time=600, request_revision=0,
        available_quantity=10,
        current_container_inventory_id=shop_inv.inventory_id,
    )
    return {
        "ledger": ledger, "items": items, "inventories": inventories,
        "reservations": reservations, "buyer": buyer, "seller": seller,
        "shop_inv": shop_inv, "item": item, "batch": batch,
    }


def _audit(ctx, **kwargs):
    return run_conservation_audit(
        ctx["ledger"], ctx["items"], ctx["inventories"], ctx["reservations"], **kwargs
    )


class TestPerTransactionConservation:
    """TEST-ECON-045"""

    def test_clean_scenario_passes(self):
        ctx = _scenario()
        report = _audit(ctx, available_by_resource={ctx["batch"]["batch_id"]: 10})
        assert report.passed
        assert report.violations == ()

    def test_injected_balance_tamper_detected(self):
        ctx = _scenario()
        ctx["seller"].balance_copper_feather += 1
        report = _audit(ctx)
        assert not report.passed
        assert any(v.startswith("currency_replay_mismatch") for v in report.violations)

    def test_injected_negative_balance_detected(self):
        ctx = _scenario()
        # 直接注入负余额（绕过 post_legs 校验）
        ctx["buyer"].balance_copper_feather = -5
        report = _audit(ctx)
        assert not report.passed
        assert any(v.startswith("negative_balance") for v in report.violations)

    def test_injected_ownership_loss_detected(self):
        ctx = _scenario()
        ctx["items"]._ownership_index.pop(ctx["item"]["item_id"])
        report = _audit(ctx)
        assert not report.passed
        assert any(v.startswith("unique_ownership_violation") for v in report.violations)

    def test_injected_reservation_overcommit_detected(self):
        ctx = _scenario()
        report = _audit(ctx, available_by_resource={ctx["batch"]["batch_id"]: 1})
        assert not report.passed
        assert any(v.startswith("reservation_overcommit") for v in report.violations)

    def test_injected_inventory_cache_drift_detected(self):
        ctx = _scenario()
        ctx["shop_inv"].used_slots = 99
        report = _audit(ctx)
        assert not report.passed
        assert any(v.startswith("inventory_cache_mismatch") for v in report.violations)


class TestSnapshotReplayRecovery:
    """TEST-ECON-046"""

    def test_replay_rebuilds_committed_projection(self):
        ctx = _scenario()
        ledger = ctx["ledger"]
        accounts = [ledger.get(aid) for aid in ledger.snapshot()]
        replayed = CurrencyLedger.replay(accounts, ledger.events())
        assert replayed == ledger.snapshot()

    def test_recovery_barrier_full_audit(self):
        ctx = _scenario()
        # 恢复屏障解除前：账本重放 + ownership + 库存缓存 + Reservation 全量审计
        report = _audit(ctx, available_by_resource={ctx["batch"]["batch_id"]: 10})
        assert report.passed
        ctx["reservations"].assert_recovery_consistent({ctx["batch"]["batch_id"]: 10})
        for inventory_id in (ctx["shop_inv"].inventory_id,):
            ctx["inventories"].assert_cache_consistent(inventory_id)


class _CanonicalProjection:
    """把随机 ULID 账户名归一化为固定键后的 state hash 投影"""

    def __init__(self, balances):
        self._balances = balances

    def snapshot(self):
        return dict(self._balances)


class TestSpeedStateHashEquivalence:
    """TEST-ECON-047"""

    def _run_script(self, transfer_chunk: int) -> str:
        ledger = CurrencyLedger()
        buyer = ledger.open_account("cmd-open-b", "resident.buyer", AccountKind.RESIDENT, 0)
        seller = ledger.open_account("cmd-open-s", "shop.seller", AccountKind.SHOP, 0)
        ledger.mint("cmd-mint", buyer.account_id, 1000, "world_bootstrap", AUTHORITIES)
        # 同一经济序列在不同倍率下只是批量不同，终点余额相同
        remaining = 300
        index = 0
        while remaining > 0:
            step = min(transfer_chunk, remaining)
            ledger.post_legs(
                f"cmd-transfer-{index}",
                [(buyer.account_id, -step), (seller.account_id, step)],
                ledger.revision,
            )
            remaining -= step
            index += 1
        canonical = {
            "buyer": ledger.get(buyer.account_id).balance_copper_feather,
            "seller": ledger.get(seller.account_id).balance_copper_feather,
        }
        return economy_state_hash(_CanonicalProjection(canonical))

    @pytest.mark.parametrize("chunk", [1, 25, 60, 300])
    def test_all_speeds_same_state_hash(self, chunk):
        assert self._run_script(chunk) == self._run_script(300)

    def test_pause_keeps_hash(self):
        ledger = CurrencyLedger()
        buyer = ledger.open_account("cmd-open-b", "resident.buyer", AccountKind.RESIDENT, 0)
        ledger.mint("cmd-mint", buyer.account_id, 1000, "world_bootstrap", AUTHORITIES)
        before = economy_state_hash(ledger)
        # 0× 暂停：没有任何新命令，hash 不变
        assert economy_state_hash(ledger) == before


def _valid_registry():
    fixtures = [
        {"fixture_id": f"econ.fixture.{index}", "initial_state": {}}
        for index in range(1, 12)
    ]
    cases = [
        {
            "test_id": f"TEST-ECON-{index:03d}",
            "fixture_id": f"econ.fixture.{(index - 1) % 11 + 1}",
            "case_id": f"case_{index}",
            "runner": f"economy.runner.{index}",
            "oracle": "True",
            "command_sequence": ["noop"],
        }
        for index in range(1, 45)
    ]
    return {"test_registry_version": 1, "fixtures": fixtures, "cases": cases}


class TestRegistryAndEnvelope:
    """TEST-ECON-048"""

    def test_valid_registry_accepted(self):
        validate_test_registry(_valid_registry())

    def test_duplicate_test_id_rejected(self):
        registry = _valid_registry()
        registry["cases"][1] = dict(registry["cases"][1], test_id="TEST-ECON-001")
        with pytest.raises(ValueError, match="duplicate"):
            validate_test_registry(registry)

    def test_missing_test_id_rejected(self):
        registry = _valid_registry()
        registry["cases"] = registry["cases"][:-1]
        with pytest.raises(ValueError, match="TEST-ECON"):
            validate_test_registry(registry)

    def test_unresolvable_fixture_rejected(self):
        registry = _valid_registry()
        registry["cases"][0] = dict(registry["cases"][0], fixture_id="econ.fixture.ghost")
        with pytest.raises(ValueError, match="fixture"):
            validate_test_registry(registry)

    def test_empty_fields_rejected(self):
        for field in ("case_id", "runner", "oracle"):
            registry = _valid_registry()
            registry["cases"][0] = dict(registry["cases"][0], **{field: ""})
            with pytest.raises(ValueError):
                validate_test_registry(registry)
        registry = _valid_registry()
        registry["cases"][0] = dict(registry["cases"][0], command_sequence=[])
        with pytest.raises(ValueError):
            validate_test_registry(registry)

    def _observation(self, **overrides):
        values = {
            "game_days": 30,
            "max_seen_unit_price": 300,
            "max_seen_active_reservations": 16,
            "open_wage_claims": 2,
            "max_shortage_streak": 4,
            "min_seen_balance": 0,
            "total_currency_delta_outside_allowlist": 0,
            "unowned_active_items": 0,
        }
        values.update(overrides)
        return SimulationObservation(**values)

    def _envelope(self):
        return BalanceEnvelope(
            max_unit_price_copper_feather=300,
            max_active_reservations=16,
            max_open_wage_claims=2,
            max_shortage_streak=4,
        )

    def test_envelope_accepts_bounded_simulation(self):
        assert check_balance_envelope(self._observation(), self._envelope()) == ()

    @pytest.mark.parametrize(
        "override,expected_violation",
        [
            ({"max_seen_unit_price": 301}, "unbounded_quote"),
            ({"max_seen_active_reservations": 17}, "permanent_active_reservation"),
            ({"open_wage_claims": 3}, "unbounded_wage_claims"),
            ({"max_shortage_streak": 5}, "unbounded_shortage"),
            ({"min_seen_balance": -1}, "negative_balance"),
            ({"total_currency_delta_outside_allowlist": 1}, "unsourced_currency"),
            ({"unowned_active_items": 1}, "unsourced_item"),
        ],
    )
    def test_envelope_violations_detected(self, override, expected_violation):
        violations = check_balance_envelope(self._observation(**override), self._envelope())
        assert expected_violation in violations

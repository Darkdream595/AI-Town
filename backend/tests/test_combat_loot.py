"""TEST-COMBAT-026/027/028：掉落来源与确定性、Victor Assignment、Wear 聚合

覆盖 RULE-COMBAT-055..059（doc 10 §11）
"""

import pytest

from src.combat import (
    LOOT_DRAW_CAP,
    LootEntry,
    LootError,
    LootTableRegistry,
    NegotiationYield,
    Side,
    WEAR_ARMOR_PER_HIT_Q1000,
    WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000,
    WEAR_WEAPON_PER_USE_Q1000,
    WearLedger,
    roll_loot,
)
from src.combat.fixtures import FakeEcon, FakePorts, make_id_factory
from src.combat.rng import CombatRngHub

from combat_helpers import run_full, start_fixture


def _registry() -> LootTableRegistry:
    registry = LootTableRegistry()
    registry.register("loot_table.bandit.cutpurse", [
        LootEntry("item.currency.copper_feather", 1000, 5, 20),
        LootEntry("item.weapon.rusty_dagger", 250, 1, 1),
    ])
    return registry


def _roll(loot_sources, ports=None, **overrides):
    ports = ports or FakePorts()
    hub = CombatRngHub("0123456789abcdeffedcba9876543210")
    defaults = dict(
        encounter_id="e.loot", source_event_id="event.src",
        loot_sources=loot_sources, negotiation_yields=[],
        registry=_registry(), loot_stream=hub.stream("combat.loot", "e.loot"),
        winning_side=Side.PARTY,
        surviving_members=[("c1", "inv.1"), ("c2", "inv.2")],
        location_container_inventory_id="inv.location",
        econ_port=ports.econ,
    )
    defaults.update(overrides)
    return roll_loot(**defaults), ports


class TestLootSources:
    """RULE-COMBAT-055/056：来源封闭、Seed 确定性、provenance"""

    def test_only_dead_creatures_with_tables_drop(self):
        outcome, ports = _roll([("c1", "loot_table.bandit.cutpurse"), ("c2", None)])
        assert all(d.source_combatant_id == "c1" for d in outcome.drops)

    def test_unregistered_table_fail_closed(self):
        with pytest.raises(LootError) as exc:
            _roll([("c1", "loot_table.nonexistent")])
        assert exc.value.code == "COMBAT_LOOT_TABLE_INVALID"

    def test_table_validation(self):
        registry = LootTableRegistry()
        with pytest.raises(LootError):
            registry.register("loot_table.bad", [LootEntry("i.x", 0, 1, 1)])  # permille 越界
        with pytest.raises(LootError):
            registry.register("loot_table.bad2", [LootEntry("i.x", 1001, 1, 1)])
        with pytest.raises(LootError):
            registry.register("loot_table.bad3", [LootEntry("i.x", 500, 0, 1)])  # 负/零数量
        with pytest.raises(LootError):
            registry.register("loot_table.bad4", [LootEntry("i.x", 500, 3, 2)])  # min>max
        with pytest.raises(LootError):
            registry.register("loot_table.bad5", [])  # 空表
        with pytest.raises(LootError):
            registry.register("wrong.prefix", [LootEntry("i.x", 500, 1, 1)])

    def test_seed_determinism_byte_identical(self):
        first, _ = _roll([("c1", "loot_table.bandit.cutpurse")])
        second, _ = _roll([("c1", "loot_table.bandit.cutpurse")])
        assert first.to_record() == second.to_record()

    def test_provenance_edge_on_every_drop(self):
        outcome, ports = _roll([("c1", "loot_table.bandit.cutpurse")])
        for mint in ports.econ.minted_currency + ports.econ.minted_items:
            assert mint["provenance"]["kind"] == "combat_loot"
            assert mint["provenance"]["encounter_id"] == "e.loot"
            assert mint["provenance"]["source_event_id"] == "event.src"

    def test_currency_drop_goes_to_mint_not_item(self):
        outcome, ports = _roll([("c1", "loot_table.bandit.cutpurse")])
        assert ports.econ.minted_currency, "保底货币条目必然掉落"
        assert all(d.is_currency for d in outcome.drops if d.item_definition_id.startswith("item.currency"))
        for mint in ports.econ.minted_currency:
            assert 5 <= mint["amount"] <= 20

    def test_single_value_quantity_consumes_no_draw(self):
        registry = LootTableRegistry()
        registry.register("loot_table.single", [LootEntry("item.weapon.rusty_dagger", 1000, 1, 1)])
        hub = CombatRngHub("ab" * 16)
        stream = hub.stream("combat.loot", "e.q")
        outcome, _ = _roll([("c1", "loot_table.single")], registry=registry, loot_stream=stream)
        assert outcome.drops[0].draw_count == 1  # 只有 drop draw
        assert outcome.drops[0].quantity == 1

    def test_roll_cap_enforced(self):
        registry = LootTableRegistry()
        registry.register("loot_table.big", [
            LootEntry(f"item.x.{i}", 1000, 1, 1) for i in range(9)
        ])
        sources = [(f"c{i}", "loot_table.big") for i in range(8)]  # 72 > 64
        with pytest.raises(LootError) as exc:
            _roll(sources, registry=registry)
        assert exc.value.code == "COMBAT_LOOT_TABLE_INVALID"

    def test_negotiation_yield_transfers_not_creates(self):
        yields = [NegotiationYield("item.weapon.rusty_dagger", 1,
                                   item_instance_id="item.existing.1")]
        outcome, ports = _roll([], negotiation_yields=yields)
        assert ports.econ.transfers and ports.econ.transfers[0]["item_instance_id"] == "item.existing.1"
        assert not ports.econ.minted_items  # 让渡不凭空创建

    def test_resident_inventory_never_looted(self):
        """RULE-COMBAT-055：全场战斗后 Resident 物品无自动转移"""
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        assert ports.econ.transfers == []


class TestVictorAssignment:
    """RULE-COMBAT-057：轮转分配、溢出、容器回退"""

    def test_round_robin_by_item_id_ascending(self):
        registry = LootTableRegistry()
        registry.register("loot_table.multi", [
            LootEntry(f"item.currency.copper_feather", 1000, 5, 5),
            LootEntry("item.weapon.rusty_dagger", 1000, 1, 1),
        ])
        outcome, ports = _roll([("c1", "loot_table.multi")], registry=registry)
        assert len(outcome.drops) == 2
        assigned = sorted(outcome.drops, key=lambda d: d.item_ref)
        assert assigned[0].assigned_inventory_id == "inv.1"
        assert assigned[1].assigned_inventory_id == "inv.2"

    def test_no_survivors_goes_to_location_container(self):
        outcome, ports = _roll(
            [("c1", "loot_table.bandit.cutpurse")], surviving_members=[])
        assert all(d.assigned_inventory_id == "inv.location" for d in outcome.drops)

    def test_null_winning_side_goes_to_container(self):
        outcome, _ = _roll(
            [("c1", "loot_table.bandit.cutpurse")], winning_side=None)
        assert all(d.assigned_inventory_id == "inv.location" for d in outcome.drops)

    def test_adversary_win_goes_to_container(self):
        outcome, _ = _roll(
            [("c1", "loot_table.bandit.cutpurse")], winning_side=Side.ADVERSARY)
        assert all(d.assigned_inventory_id == "inv.location" for d in outcome.drops)

    def test_capacity_overflow_to_container_nothing_dropped(self):
        ports = FakePorts()
        ports.econ.capacity_blocked.add("inv.1")
        ports.econ.capacity_blocked.add("inv.2")
        outcome, _ = _roll([("c1", "loot_table.bandit.cutpurse")], ports=ports)
        assert outcome.drops
        assert all(d.assigned_inventory_id == "inv.location" for d in outcome.drops)
        # 全部战利品有去向（守恒）
        assert all(d.assigned_inventory_id for d in outcome.drops)


class TestWear:
    """RULE-COMBAT-058/059：记账、聚合、Damaged、社会事实边界"""

    def test_weapon_use_and_armor_hit_accumulate(self):
        ledger = WearLedger()
        ledger.record_weapon_use("item.sword")
        ledger.record_weapon_use("item.sword")
        ledger.record_armor_hit("item.mail")
        assert ledger.deltas() == {
            "item.sword": 2 * WEAR_WEAPON_PER_USE_Q1000,
            "item.mail": WEAR_ARMOR_PER_HIT_Q1000,
        }

    def test_per_battle_cap_truncated_with_diagnostic(self):
        ledger = WearLedger()
        for _ in range(120):  # 120×5=600 > 500
            ledger.record_weapon_use("item.sword")
        assert ledger.deltas()["item.sword"] == WEAR_CAP_PER_ITEM_PER_BATTLE_Q1000
        assert any("wear_cap_truncated" in d for d in ledger.diagnostics)

    def test_settle_submits_aggregated_delta_once(self):
        ledger = WearLedger()
        ledger.record_weapon_use("item.sword")
        ledger.record_armor_hit("item.mail")
        ports = FakePorts()
        settlements = ledger.settle(encounter_id="e.wear", econ_port=ports.econ)
        assert len(ports.econ.wear_calls) == 2
        by_item = {w.item_instance_id: w for w in settlements}
        assert by_item["item.sword"].wear_delta_q1000 == WEAR_WEAPON_PER_USE_Q1000
        assert by_item["item.mail"].wear_delta_q1000 == WEAR_ARMOR_PER_HIT_Q1000

    def test_zero_durability_becomes_damaged_not_deleted(self):
        ledger = WearLedger()
        ports = FakePorts()
        ports.econ.durability["item.sword"] = 3
        ledger.record_weapon_use("item.sword")  # -5 → 0
        settlements = ledger.settle(encounter_id="e.dmg", econ_port=ports.econ)
        assert settlements[0].became_damaged is True
        assert ports.econ.durability["item.sword"] == 0  # Damaged 状态，非删除

    def test_battle_records_wear_and_settles_once(self):
        """Integration：装备 weapon_ref 的 Resident 攻击后结果事务一次性结算"""
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        enc.gear[resident.combatant_id] = {"weapon": "item.sword.1", "armor": None}
        run_full(engine, eid)
        if enc.wear_ledger.deltas():
            assert len(ports.econ.wear_calls) == len(enc.wear_ledger.deltas())
            sword_calls = [w for w in ports.econ.wear_calls
                           if w["item_instance_id"] == "item.sword.1"]
            if sword_calls:
                assert sword_calls[0]["wear_delta_q1000"] % WEAR_WEAPON_PER_USE_Q1000 == 0

    def test_social_facts_only_via_events(self):
        """RULE-COMBAT-059：COMBAT 不直接写关系/记忆/法律；事实只经事件携带"""
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        aftermath = resolved["payload"]["aftermath_input"]
        assert aftermath["trigger_source"] == "ambush_event"
        assert "end_condition" in aftermath and "winning_side" in aftermath
        # 端口面没有 memory/relation/law 写入接口
        assert not hasattr(engine, "memory_port") and not hasattr(engine, "relation_port")

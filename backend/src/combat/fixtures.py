"""
战斗测试 fixture 注册表与覆盖审计（DOC-COMBAT-012）

- DES-COMBAT-012：六个核心 fixture 以 Stable Catalog ID 注册
- FakeModelProvider：按配置返回固定响应或模拟超时/不可用/取消/非法输出
- FakePorts：全部引擎端口的 recording fake，支持失败注入
- 确定性 id_factory：零填充 26 位十进制，字典序 == 数值序（Golden Replay 用）
- TEST_COVERAGE_MATRIX：doc 12 §5.3 的机械拷贝；audit_rule_coverage 校验并集
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .constants import Side
from .decisions import (
    ModelTimeoutError,
    ProviderUnavailableError,
    RequestCancelledError,
)
from .engine import CombatEngine, NegotiationDecision
from .loot import LootEntry, LootTableRegistry, NegotiationYield
from .sheets import CreatureTemplate, Stats
from .status import StatusStore, build_default_statuses

DUEL_SEED_HEX = "0123456789abcdeffedcba9876543210"


class DeterministicIdFactory:
    """确定性 ID：字典序与生成序一致；可快照/恢复（Golden Replay 与崩溃恢复用）"""

    def __init__(self) -> None:
        self.counter = 0

    def __call__(self) -> str:
        self.counter += 1
        return f"{self.counter:026d}"

    def snapshot(self) -> int:
        return self.counter

    def restore(self, value: int) -> None:
        self.counter = value


def make_id_factory() -> DeterministicIdFactory:
    return DeterministicIdFactory()


# ---------------------------------------------------------------------------
# Fake 端口
# ---------------------------------------------------------------------------


class FakeEcon:
    """CombatEconPort 的 recording fake；容量/失败可注入"""

    def __init__(self, id_factory: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self.minted_items: List[Dict] = []
        self.minted_currency: List[Dict] = []
        self.transfers: List[Dict] = []
        self.deposits: List[Tuple[str, str]] = []
        self.wear_calls: List[Dict] = []
        self.consumed: List[str] = []
        self.capacity_blocked: set = set()
        self.durability: Dict[str, int] = {}
        self.fail_next_mint = False

    def mint_loot_item(self, *, item_definition_id, quantity, idempotency_key, provenance) -> str:
        if self.fail_next_mint:
            self.fail_next_mint = False
            raise RuntimeError("econ failure injected")
        item_ref = self._id_factory()
        self.minted_items.append({
            "item_ref": item_ref,
            "item_definition_id": item_definition_id,
            "quantity": quantity,
            "idempotency_key": idempotency_key,
            "provenance": dict(provenance),
        })
        return item_ref

    def mint_currency(self, *, amount_copper_feather, idempotency_key, provenance) -> str:
        if self.fail_next_mint:
            self.fail_next_mint = False
            raise RuntimeError("econ failure injected")
        event_ref = self._id_factory()
        self.minted_currency.append({
            "event_ref": event_ref,
            "amount": amount_copper_feather,
            "idempotency_key": idempotency_key,
            "provenance": dict(provenance),
        })
        return event_ref

    def transfer_yield_item(self, *, item_instance_id, idempotency_key, provenance) -> None:
        self.transfers.append({
            "item_instance_id": item_instance_id,
            "idempotency_key": idempotency_key,
            "provenance": dict(provenance),
        })

    def deposit_to_inventory(self, *, item_ref, inventory_id) -> bool:
        if inventory_id in self.capacity_blocked:
            return False
        self.deposits.append((item_ref, inventory_id))
        return True

    def apply_wear(self, *, item_instance_id, wear_delta_q1000, idempotency_key) -> bool:
        before = self.durability.get(item_instance_id, 1000)
        after = max(0, before - wear_delta_q1000)
        self.durability[item_instance_id] = after
        became_damaged = after == 0
        self.wear_calls.append({
            "item_instance_id": item_instance_id,
            "wear_delta_q1000": wear_delta_q1000,
            "idempotency_key": idempotency_key,
            "became_damaged": became_damaged,
        })
        return became_damaged

    def consume_item(self, *, item_instance_id, idempotency_key) -> None:
        self.consumed.append(item_instance_id)


class FakeReservationPort:
    def __init__(self) -> None:
        self.acquired: List[Tuple[Tuple[str, ...], str]] = []
        self.released: List[Tuple[Tuple[str, ...], str]] = []
        self.locked_entities: set = set()
        self.fail_on_entities: set = set()

    def acquire(self, entity_refs, encounter_id) -> bool:
        if any(ref in self.locked_entities or ref in self.fail_on_entities for ref in entity_refs):
            return False
        self.locked_entities.update(entity_refs)
        self.acquired.append((tuple(entity_refs), encounter_id))
        return True

    def release(self, entity_refs, encounter_id) -> None:
        self.locked_entities.difference_update(entity_refs)
        self.released.append((tuple(entity_refs), encounter_id))


class FakePausePort:
    def __init__(self, id_factory: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self.acquired: List[Tuple[str, str, str]] = []
        self.released: List[str] = []

    def acquire(self, reason, encounter_id) -> str:
        token_id = self._id_factory()
        self.acquired.append((token_id, reason, encounter_id))
        return token_id

    def release(self, token_id) -> None:
        self.released.append(token_id)


class FakeSettlementPort:
    """health/mana/finals 共用；duplicate 键去重；支持失败注入"""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.applied: List[Dict] = []
        self._seen: Dict[str, str] = {}
        self.fail_next = False

    def apply(self, *, idempotency_key, payload) -> str:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError(f"{self.kind} settlement failure injected")
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]
        ref = f"{self.kind}-ref-{len(self.applied)}"
        self._seen[idempotency_key] = ref
        self.applied.append({"idempotency_key": idempotency_key, "payload": payload, "ref": ref})
        return ref

    def apply_settlement(self, *, idempotency_key, settlements) -> str:
        return self.apply(idempotency_key=idempotency_key, payload=settlements)

    def apply_finals(self, *, idempotency_key, finals) -> str:
        return self.apply(idempotency_key=idempotency_key, payload=finals)


class FakePorts:
    """全部引擎端口的聚合 fake；测试可直接断言 recording"""

    def __init__(self, id_factory: Optional[Callable[[], str]] = None) -> None:
        self.id_factory = id_factory or make_id_factory()
        self.lifecycle: Dict[str, str] = {}
        self.resident_sources: Dict[str, Dict] = {}
        self.creature_templates: Dict[str, CreatureTemplate] = {}
        self.abilities: Dict[str, List[Dict]] = {}
        self.spells: Dict[str, List[Dict]] = {}
        self.items: Dict[str, List[Dict]] = {}
        self.duel_permits: set = set()
        self.surrender_accepts: bool = False
        self.negotiation_decisions: Dict[str, NegotiationDecision] = {}
        self.registered_terms: set = set()
        self.captivity_holders: Dict[Side, Dict] = {}
        self.valid_locations: set = set()
        self.safe_points: Dict[str, str] = {}
        self.inventories: Dict[str, str] = {}
        self.reservation = FakeReservationPort()
        self.pause = FakePausePort(self.id_factory)
        self.econ = FakeEcon(self.id_factory)
        self.health = FakeSettlementPort("health")
        self.mana = FakeSettlementPort("mana")
        self.finals = FakeSettlementPort("finals")
        self.loot_registry = LootTableRegistry()

    # -- 装配辅助 --

    def add_resident(self, entity_ref: str, *, stats: Dict, hp_max: int, mp_max: int,
                     hp_current: Optional[int] = None, mp_current: Optional[int] = None,
                     reach: bool = False, weapon_ref: Optional[str] = None,
                     armor_ref: Optional[str] = None, lifecycle: str = "active") -> None:
        self.lifecycle[entity_ref] = lifecycle
        self.resident_sources[entity_ref] = {
            "hp_current": hp_max if hp_current is None else hp_current,
            "hp_max": hp_max,
            "mp_current": mp_max if mp_current is None else mp_current,
            "mp_max": mp_max,
            "race_base": dict(stats),
            "skill_bonus": {},
            "equipment_bonus": {},
            "equipment_refs": [r for r in (weapon_ref, armor_ref) if r],
            "weapon_ref": weapon_ref,
            "armor_ref": armor_ref,
            "reach": reach,
        }
        self.inventories.setdefault(entity_ref, f"inv.{entity_ref}")
        self.safe_points.setdefault(entity_ref, "loc.safe_point")

    def add_creature(self, entity_ref: str, *, stats: Dict, hp_max: int, mp_max: int = 0,
                     loot_table_id: Optional[str] = None, reach: bool = False,
                     template_id: Optional[str] = None) -> None:
        self.lifecycle[entity_ref] = "active"
        self.creature_templates[entity_ref] = CreatureTemplate(
            template_id=template_id or f"template.{entity_ref}",
            stats=Stats(
                hp_current=hp_max, hp_max=hp_max, mp_current=mp_max, mp_max=mp_max,
                strength=stats.get("strength", 10), defense=stats.get("defense", 10),
                magic=stats.get("magic", 5), resistance=stats.get("resistance", 5),
                agility=stats.get("agility", 10), focus=stats.get("focus", 10),
            ),
            loot_table_id=loot_table_id,
            reach=reach,
        )

    def build_engine(self, world_seed_hex: str = DUEL_SEED_HEX) -> CombatEngine:
        id_factory = self.id_factory
        return CombatEngine(
            world_seed_hex=world_seed_hex,
            lifecycle_of=lambda ref: self.lifecycle.get(ref, "active"),
            reservation_port=self.reservation,
            pause_port=self.pause,
            resident_source_of=lambda ref: self.resident_sources[ref],
            creature_template_of=lambda ref: self.creature_templates[ref],
            duel_permit_valid=lambda event_id: event_id in self.duel_permits,
            ability_provider=lambda ref: self.abilities.get(ref, []),
            spell_provider=lambda ref: self.spells.get(ref, []),
            item_provider=lambda ref: self.items.get(ref, []),
            surrender_policy=lambda actor, opposing: self.surrender_accepts,
            negotiation_policy=lambda term, actor, opposing: self.negotiation_decisions.get(
                term, NegotiationDecision(accepted=False)
            ),
            negotiation_term_registered=lambda term: term in self.registered_terms,
            captivity_holder_of=lambda side: self.captivity_holders.get(side),
            location_validator=lambda loc: not self.valid_locations or loc in self.valid_locations,
            safe_point_of=lambda ref: self.safe_points[ref],
            inventory_of=lambda ref: self.inventories[ref],
            econ_port=self.econ,
            resident_health_port=self.health,
            mana_settlement_port=self.mana,
            resident_finals_port=self.finals,
            loot_registry=self.loot_registry,
            status_store_factory=lambda: StatusStore(build_default_statuses(), id_factory),
            id_factory=id_factory,
        )


# ---------------------------------------------------------------------------
# FakeModelProvider（RULE-COMBAT-066：默认测试不使用真实模型）
# ---------------------------------------------------------------------------


class FakeModelProvider:
    """mode: fixed / timeout / unavailable / cancelled / invalid / mixed"""

    def __init__(self, mode: str = "fixed") -> None:
        self.mode = mode
        self.calls: List[Dict] = []

    def complete(self, *, model_id, prompt_id, context, deadline_ms) -> str:
        self.calls.append({"model_id": model_id, "prompt_id": prompt_id, "context": context})
        if self.mode == "timeout":
            raise ModelTimeoutError("fake timeout")
        if self.mode == "unavailable":
            raise ProviderUnavailableError("fake provider down")
        if self.mode == "cancelled":
            raise RequestCancelledError("fake cancelled")
        if self.mode == "invalid":
            return "这不是 JSON，无法解析"
        # fixed：从上下文合法集合中选第一个攻击性 option（确定性）
        options = context["legal_options"]
        chosen = None
        for option in options:
            if option["kind"] in ("attack", "skill", "cast_spell", "use_item") and option[
                "legal_target_sets"
            ]:
                chosen = option
                break
        if chosen is None:
            chosen = next(o for o in options if o["kind"] == "defend")
        target_set = chosen["legal_target_sets"][0] if chosen["legal_target_sets"] else None
        return json.dumps({
            "encounter_id": context["encounter_id"],
            "turn_index": context["turn_index"],
            "action_option_id": chosen["option_id"],
            "target_combatant_ids": target_set["combatant_ids"][: target_set["max_targets"]]
            if target_set
            else [],
            "negotiation_term_id": None,
        })


# ---------------------------------------------------------------------------
# 驱动辅助：自动跑完整场遭遇
# ---------------------------------------------------------------------------


def run_encounter_to_end(
    engine: CombatEngine,
    encounter_id: str,
    decision_service=None,
    *,
    player_script: Optional[Callable[[CombatEngine, str], None]] = None,
    max_turns: int = 5000,
) -> Dict:
    """逐 Turn 驱动：AI 走 decision_service，玩家走 player_script；终结后 Resolve"""
    from .decisions import CombatDecisionService
    from .constants import EncounterState

    service = decision_service or CombatDecisionService(engine, FakeModelProvider("fixed"))
    turns = 0
    while True:
        encounter = engine._require(encounter_id)
        if encounter.state is EncounterState.RESOLVING:
            return engine.resolve_encounter(
                f"{encounter_id}:resolve", encounter_id, encounter.revision
            )
        if encounter.state is EncounterState.ENDED:
            return {
                "encounter_id": encounter_id,
                "resolved_event_id": encounter.resolved_event_id,
                "state": "ended",
                "revision": encounter.revision,
            }
        turns += 1
        if turns > max_turns:
            raise AssertionError("encounter did not terminate within max_turns")
        pending = engine.pending_ai_combatant(encounter_id)
        if pending is not None:
            service.request_combat_decision(encounter_id, encounter.turn_index)
        else:
            if player_script is None:
                raise AssertionError("player turn without script")
            player_script(engine, encounter_id)


# ---------------------------------------------------------------------------
# DES-COMBAT-012：六个核心 fixture
# ---------------------------------------------------------------------------

ELISE_STATS = {"strength": 42, "defense": 35, "magic": 18, "resistance": 22, "agility": 39, "focus": 27}
GUARD_STATS = {"strength": 45, "defense": 40, "magic": 8, "resistance": 18, "agility": 25, "focus": 22}
CUTPURSE_STATS = {"strength": 30, "defense": 20, "magic": 5, "resistance": 10, "agility": 33, "focus": 20}
BRUTE_STATS = {"strength": 38, "defense": 26, "magic": 3, "resistance": 8, "agility": 20, "focus": 15}


def fixture_duel_2v2(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.duel_2v2：2 Resident 对 2 Creature，主链路"""
    ports = ports or FakePorts()
    ports.add_resident("resident.apothecary.elise", stats=ELISE_STATS, hp_max=30, mp_max=10)
    ports.add_resident("resident.guard.bram", stats=GUARD_STATS, hp_max=40, mp_max=4)
    ports.add_creature("creature.bandit.cutpurse", stats=CUTPURSE_STATS, hp_max=22,
                       loot_table_id="loot_table.bandit.cutpurse")
    ports.add_creature("creature.bandit.brute", stats=BRUTE_STATS, hp_max=30,
                       loot_table_id="loot_table.bandit.brute")
    ports.loot_registry.register("loot_table.bandit.cutpurse", [
        LootEntry("item.currency.copper_feather", 1000, 5, 20),
        LootEntry("item.weapon.rusty_dagger", 250, 1, 1),
    ])
    ports.loot_registry.register("loot_table.bandit.brute", [
        LootEntry("item.currency.copper_feather", 1000, 8, 15),
        LootEntry("item.material.cloth_scrap", 500, 1, 3),
    ])
    engine = ports.build_engine(DUEL_SEED_HEX)
    payload = {
        "world_id": "world.fixture",
        "trigger_source": "ambush_event",
        "trigger_event_id": "event.ambush.001",
        "started_at_game_time": 1830,
        "location_container_inventory_id": "inv.location.clearing",
        "party": [
            {"entity_ref": "resident.apothecary.elise", "kind": "player_resident",
             "formation_slot": "front_left"},
            {"entity_ref": "resident.guard.bram", "kind": "resident",
             "formation_slot": "front_right"},
        ],
        "adversary": [
            {"entity_ref": "creature.bandit.cutpurse", "kind": "creature"},
            {"entity_ref": "creature.bandit.brute", "kind": "creature"},
        ],
    }
    return engine, payload, ports


def fixture_full_party_4v4(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.full_party_4v4：满编前后排、站位与 Reach"""
    ports = ports or FakePorts()
    ports.add_resident("resident.vanguard.ash", stats=GUARD_STATS, hp_max=44, mp_max=4)
    ports.add_resident("resident.fencer.rei", stats=ELISE_STATS, hp_max=32, mp_max=8, reach=True)
    ports.add_resident("resident.mage.iona", stats={"strength": 12, "defense": 15, "magic": 48,
                                                    "resistance": 30, "agility": 28, "focus": 40},
                       hp_max=24, mp_max=30)
    ports.add_resident("resident.healer.pax", stats={"strength": 10, "defense": 18, "magic": 40,
                                                     "resistance": 34, "agility": 22, "focus": 30},
                       hp_max=26, mp_max=26)
    for index in range(4):
        ports.add_creature(f"creature.wolf.{index}", stats=CUTPURSE_STATS, hp_max=18)
    ports.spells["resident.mage.iona"] = [{
        "spell_id": "spell.elemental.ember_bolt", "mp_cost": 4,
        "formula_ref": "combat_formula.v1.magical_single", "power_q1000": 1200,
        "target_kind": "enemy_single",
    }]
    ports.spells["resident.healer.pax"] = [{
        "spell_id": "spell.restoration.mend", "mp_cost": 5,
        "formula_ref": "combat_formula.v1.healing_single", "power_q1000": 900,
        "target_kind": "ally_single",
    }]
    engine = ports.build_engine(DUEL_SEED_HEX)
    payload = {
        "world_id": "world.fixture",
        "trigger_source": "scripted_quest",
        "trigger_event_id": "event.quest.wolves",
        "started_at_game_time": 2000,
        "location_container_inventory_id": "inv.location.forest",
        "party": [
            {"entity_ref": "resident.vanguard.ash", "kind": "player_resident",
             "formation_slot": "front_left"},
            {"entity_ref": "resident.fencer.rei", "kind": "resident",
             "formation_slot": "front_right"},
            {"entity_ref": "resident.mage.iona", "kind": "resident",
             "formation_slot": "rear_left"},
            {"entity_ref": "resident.healer.pax", "kind": "resident",
             "formation_slot": "rear_right"},
        ],
        "adversary": [
            {"entity_ref": f"creature.wolf.{index}", "kind": "creature"} for index in range(4)
        ],
    }
    return engine, payload, ports


def fixture_nonviolent_exit(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.nonviolent_exit：投降/谈判/逃跑三出口"""
    ports = ports or FakePorts()
    ports.add_resident("resident.trader.mira", stats=ELISE_STATS, hp_max=28, mp_max=8)
    ports.add_creature("creature.bandit.toll", stats=CUTPURSE_STATS, hp_max=22,
                       loot_table_id="loot_table.bandit.cutpurse")
    ports.loot_registry.register("loot_table.bandit.cutpurse", [
        LootEntry("item.currency.copper_feather", 1000, 5, 20),
    ])
    ports.registered_terms.add("negotiation.offer_payment")
    ports.negotiation_decisions["negotiation.offer_payment"] = NegotiationDecision(
        accepted=True,
        ends_encounter=True,
        yields=(NegotiationYield("item.currency.copper_feather", 30, is_currency=True),),
    )
    engine = ports.build_engine(DUEL_SEED_HEX)
    payload = {
        "world_id": "world.fixture",
        "trigger_source": "aggro_contact",
        "trigger_event_id": "event.aggro.toll",
        "started_at_game_time": 2100,
        "location_container_inventory_id": "inv.location.road",
        "party": [
            {"entity_ref": "resident.trader.mira", "kind": "player_resident",
             "formation_slot": "front_left"},
        ],
        "adversary": [{"entity_ref": "creature.bandit.toll", "kind": "creature"}],
    }
    return engine, payload, ports


def fixture_wipeout(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.wipeout：全队 down 与 outcome 映射降级支路"""
    ports = ports or FakePorts()
    weak = {"strength": 8, "defense": 5, "magic": 5, "resistance": 5, "agility": 10, "focus": 8}
    ports.add_resident("resident.farmer.otto", stats=weak, hp_max=14, mp_max=0)
    ports.add_resident("resident.child.lili", stats=weak, hp_max=10, mp_max=0)
    ports.add_creature("creature.bear.alpha", stats={"strength": 90, "defense": 40, "magic": 5,
                                                     "resistance": 20, "agility": 30, "focus": 35},
                       hp_max=80, loot_table_id="loot_table.bear.alpha")
    ports.loot_registry.register("loot_table.bear.alpha", [
        LootEntry("item.material.bear_pelt", 1000, 1, 2),
    ])
    engine = ports.build_engine(DUEL_SEED_HEX)
    payload = {
        "world_id": "world.fixture",
        "trigger_source": "defense_response",
        "trigger_event_id": "event.defense.bear",
        "started_at_game_time": 2200,
        "location_container_inventory_id": "inv.location.farm",
        "party": [
            {"entity_ref": "resident.farmer.otto", "kind": "player_resident",
             "formation_slot": "front_left"},
            {"entity_ref": "resident.child.lili", "kind": "resident",
             "formation_slot": "front_right"},
        ],
        "adversary": [{"entity_ref": "creature.bear.alpha", "kind": "creature"}],
    }
    return engine, payload, ports


def fixture_model_offline(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.model_offline：全故障 provider 下 fallback 全程推进"""
    engine, payload, ports = fixture_duel_2v2(ports)
    return engine, payload, ports


def fixture_round_cap(ports: Optional[FakePorts] = None) -> Tuple[CombatEngine, Dict, FakePorts]:
    """fixture.combat.round_cap：双方 pass，驱动 round_cap_forced"""
    ports = ports or FakePorts()
    ports.add_resident("resident.duelist.one", stats=ELISE_STATS, hp_max=30, mp_max=5)
    ports.add_creature("creature.training.dummy", stats={"strength": 5, "defense": 5, "magic": 1,
                                                         "resistance": 1, "agility": 5, "focus": 5},
                       hp_max=40)
    engine = ports.build_engine(DUEL_SEED_HEX)
    payload = {
        "world_id": "world.fixture",
        "trigger_source": "arena_duel",
        "trigger_event_id": "event.duel.permit.001",
        "started_at_game_time": 2300,
        "location_container_inventory_id": "inv.location.arena",
        "party": [
            {"entity_ref": "resident.duelist.one", "kind": "player_resident",
             "formation_slot": "front_left"},
        ],
        "adversary": [{"entity_ref": "creature.training.dummy", "kind": "creature"}],
    }
    ports.duel_permits.add("event.duel.permit.001")
    return engine, payload, ports


FIXTURE_REGISTRY: Dict[str, Callable] = {
    "fixture.combat.duel_2v2": fixture_duel_2v2,
    "fixture.combat.full_party_4v4": fixture_full_party_4v4,
    "fixture.combat.nonviolent_exit": fixture_nonviolent_exit,
    "fixture.combat.wipeout": fixture_wipeout,
    "fixture.combat.model_offline": fixture_model_offline,
    "fixture.combat.round_cap": fixture_round_cap,
}


# ---------------------------------------------------------------------------
# doc 12 §5.3 测试矩阵（机械拷贝）与覆盖审计
# ---------------------------------------------------------------------------


def _rules(spec: str) -> List[str]:
    """"RULE-COMBAT-001..006" 展开为显式 ID 列表"""
    ids: List[str] = []
    for part in spec.split(","):
        part = part.strip()
        if ".." in part:
            head, tail = part.split("..")
            prefix = head.rsplit("-", 1)[0]
            start = int(head.rsplit("-", 1)[1])
            ids.extend(f"{prefix}-{n:03d}" for n in range(start, int(tail) + 1))
        else:
            ids.append(part)
    return ids


TEST_COVERAGE_MATRIX: Dict[str, Dict] = {
    "TEST-COMBAT-001": {"layer": "Unit/Contract", "rules": _rules("RULE-COMBAT-001..006")},
    "TEST-COMBAT-002": {"layer": "Unit", "rules": _rules("RULE-COMBAT-008..009")},
    "TEST-COMBAT-003": {"layer": "Unit", "rules": _rules("RULE-COMBAT-010..011")},
    "TEST-COMBAT-004": {"layer": "Integration", "rules": _rules("RULE-COMBAT-007, RULE-COMBAT-012")},
    "TEST-COMBAT-005": {"layer": "Unit", "rules": _rules("RULE-COMBAT-013..015")},
    "TEST-COMBAT-006": {"layer": "Unit", "rules": _rules("RULE-COMBAT-016")},
    "TEST-COMBAT-007": {"layer": "Integration", "rules": _rules("RULE-COMBAT-017..018")},
    "TEST-COMBAT-008": {"layer": "Unit", "rules": _rules("RULE-COMBAT-019")},
    "TEST-COMBAT-009": {"layer": "Property", "rules": _rules("RULE-COMBAT-020..023")},
    "TEST-COMBAT-010": {"layer": "Unit/Contract", "rules": _rules("RULE-COMBAT-024..025")},
    "TEST-COMBAT-011": {"layer": "Unit", "rules": _rules("RULE-COMBAT-026..028")},
    "TEST-COMBAT-012": {"layer": "Unit", "rules": _rules("RULE-COMBAT-029..030")},
    "TEST-COMBAT-013": {"layer": "Integration", "rules": _rules("RULE-COMBAT-031")},
    "TEST-COMBAT-014": {"layer": "Unit", "rules": _rules("RULE-COMBAT-032..034")},
    "TEST-COMBAT-015": {"layer": "Integration", "rules": _rules("RULE-COMBAT-035")},
    "TEST-COMBAT-016": {"layer": "Property/Contract", "rules": _rules("RULE-COMBAT-036..037")},
    "TEST-COMBAT-017": {"layer": "Contract", "rules": _rules("RULE-COMBAT-038..039")},
    "TEST-COMBAT-018": {"layer": "Unit", "rules": _rules("RULE-COMBAT-040")},
    "TEST-COMBAT-019": {"layer": "Integration", "rules": _rules("RULE-COMBAT-041..043")},
    "TEST-COMBAT-020": {"layer": "Unit/E2E", "rules": _rules("RULE-COMBAT-044..045")},
    "TEST-COMBAT-021": {"layer": "Integration", "rules": _rules("RULE-COMBAT-046..047")},
    "TEST-COMBAT-022": {"layer": "Browser E2E", "rules": _rules("RULE-COMBAT-048")},
    "TEST-COMBAT-023": {"layer": "Unit", "rules": _rules("RULE-COMBAT-049")},
    "TEST-COMBAT-024": {"layer": "Property", "rules": _rules("RULE-COMBAT-050..051, RULE-COMBAT-053")},
    "TEST-COMBAT-025": {"layer": "Integration", "rules": _rules("RULE-COMBAT-052, RULE-COMBAT-054")},
    "TEST-COMBAT-026": {"layer": "Unit", "rules": _rules("RULE-COMBAT-055..056")},
    "TEST-COMBAT-027": {"layer": "Unit", "rules": _rules("RULE-COMBAT-057")},
    "TEST-COMBAT-028": {"layer": "Integration/Contract", "rules": _rules("RULE-COMBAT-058..059")},
    "TEST-COMBAT-029": {"layer": "Integration", "rules": _rules("RULE-COMBAT-060")},
    "TEST-COMBAT-030": {"layer": "Integration", "rules": _rules("RULE-COMBAT-061")},
    "TEST-COMBAT-031": {"layer": "Crash Point Matrix", "rules": _rules("RULE-COMBAT-062..063")},
    "TEST-COMBAT-032": {"layer": "Contract", "rules": _rules("RULE-COMBAT-064")},
    "TEST-COMBAT-033": {"layer": "Golden Replay", "rules": []},
    "TEST-COMBAT-034": {"layer": "Simulation", "rules": _rules("RULE-COMBAT-041, RULE-COMBAT-066")},
    "TEST-COMBAT-035": {"layer": "Simulation", "rules": _rules("RULE-COMBAT-051, RULE-COMBAT-060..061")},
    "TEST-COMBAT-036": {"layer": "Audit", "rules": _rules("RULE-COMBAT-065..066")},
}


def audit_rule_coverage() -> List[str]:
    """RULE-COMBAT-065：001..066 每条至少在矩阵一行；返回缺失清单（空为通过）"""
    covered = set()
    for row in TEST_COVERAGE_MATRIX.values():
        covered.update(row["rules"])
    missing = [
        f"RULE-COMBAT-{n:03d}" for n in range(1, 67) if f"RULE-COMBAT-{n:03d}" not in covered
    ]
    return missing


def audit_fixtures() -> List[str]:
    """六个核心 fixture 全部注册且可加载；返回问题清单（空为通过）"""
    problems: List[str] = []
    for fixture_id in (
        "fixture.combat.duel_2v2",
        "fixture.combat.full_party_4v4",
        "fixture.combat.nonviolent_exit",
        "fixture.combat.wipeout",
        "fixture.combat.model_offline",
        "fixture.combat.round_cap",
    ):
        builder = FIXTURE_REGISTRY.get(fixture_id)
        if builder is None:
            problems.append(f"missing {fixture_id}")
            continue
        try:
            engine, payload, ports = builder()
            result = engine.start_encounter(f"{fixture_id}:start", payload)
            if not result["encounter_id"]:
                problems.append(f"{fixture_id} empty encounter_id")
        except Exception as exc:  # fixture 必须开箱可跑
            problems.append(f"{fixture_id} failed: {exc}")
    return problems

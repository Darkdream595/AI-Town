"""
Encounter aggregate 与回合机（DOC-COMBAT-001/002/003/006/009/011）

- 唯一创建入口 StartEncounterCommand：五种触发源、Reservation 全锁或回滚、
  combat Pause Token 同事务、单世界活跃上限 1
- RULE-COMBAT-008：initiative = agility*1000 + tiebreak draw(1000)，
  按 combatant_id 升序消费 combat.initiative 流，降序冻结一轮
- RULE-COMBAT-010/011：Turn 状态机封闭；stale/非 owner/错 phase 拒绝且无状态变化
- RULE-COMBAT-013..018：服务器派生 LegalCombatOption[]，非空不变量，
  surrender/talk/flee 由注册 policy 与公式确定性判定
- RULE-COMBAT-032..036：In-Encounter HP/MP 唯一权威；Settlement 恰好一次聚合落账
- RULE-COMBAT-060/061：Result Transaction 七步固定顺序、失败恢复快照、Resolve 幂等
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from ..foundation import generate_ulid
from .constants import (
    BASIC_ATTACK_FORMULA_REF,
    BASIC_ATTACK_POWER_Q1000,
    FLEE_FORMULA_REF,
    FORMATION_SLOTS,
    INJURY_BRUISES,
    INJURY_BRUISES_MIN_Q1000,
    INJURY_DEEP_WOUNDS,
    INJURY_DEEP_WOUNDS_MIN_Q1000,
    INJURY_SEVERE_TRAUMA,
    OPTION_CANDIDATE_CAP,
    PARTY_MAX_MEMBERS,
    RECENT_TURNS_CAP,
    ROUND_CAP,
    ActionKind,
    CombatantKind,
    CombatantState,
    EncounterState,
    EndCondition,
    Phase,
    Side,
    SkipReason,
    TriggerSource,
    TurnStatus,
)
from .endings import evaluate_end_conditions, map_defeat_outcomes
from .formulas import resolve_formula
from .loot import (
    CombatEconPort,
    LootOutcome,
    LootTableRegistry,
    NegotiationYield,
    WearLedger,
    roll_loot,
)
from .rng import CombatRngHub
from .sheets import CombatantSheet, CreatureTemplate, derive_combatant_sheet
from .status import StatusStore

ENCOUNTER_SCHEMA_VERSION = 1
TURN_SCHEMA_VERSION = 1
RESOLVED_SCHEMA_VERSION = 1
SETTLEMENT_SCHEMA_VERSION = 1

#: switch_position 的相邻关系（同排左右、同列前后；不含对角）
ADJACENT_SLOTS = {
    "front_left": ("front_right", "rear_left"),
    "front_right": ("front_left", "rear_right"),
    "rear_left": ("rear_right", "front_left"),
    "rear_right": ("rear_left", "front_right"),
}
FRONT_SLOTS = frozenset({"front_left", "front_right"})

AI_CONTROLLED_KINDS = frozenset(
    {CombatantKind.RESIDENT, CombatantKind.CREATURE, CombatantKind.SUMMON}
)


class CombatEngineError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------------------
# 端口契约（测试用 recording fake；集成时接真实 owner 域）
# ---------------------------------------------------------------------------


class ReservationPort(Protocol):
    def acquire(self, entity_refs: List[str], encounter_id: str) -> bool: ...
    def release(self, entity_refs: List[str], encounter_id: str) -> None: ...


class PausePort(Protocol):
    def acquire(self, reason: str, encounter_id: str) -> str: ...
    def release(self, token_id: str) -> None: ...


class ResidentHealthPort(Protocol):
    def apply_settlement(self, *, idempotency_key: str, settlements: List[Dict]) -> str: ...


class ManaSettlementPort(Protocol):
    def apply_settlement(self, *, idempotency_key: str, settlements: List[Dict]) -> str: ...


class ResidentFinalsPort(Protocol):
    def apply_finals(self, *, idempotency_key: str, finals: List[Dict]) -> str: ...


@dataclass(frozen=True)
class NegotiationDecision:
    """注册谈判 policy 的确定性输出"""

    accepted: bool
    ends_encounter: bool = False
    yields: Tuple[NegotiationYield, ...] = ()


# ---------------------------------------------------------------------------
# DES-COMBAT-003：LegalCombatOption
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LegalTargetSet:
    set_id: str
    combatant_ids: Tuple[str, ...]
    min_targets: int
    max_targets: int

    def to_record(self) -> Dict:
        return {
            "set_id": self.set_id,
            "combatant_ids": list(self.combatant_ids),
            "min_targets": self.min_targets,
            "max_targets": self.max_targets,
        }


@dataclass(frozen=True)
class LegalCombatOption:
    option_id: str
    kind: ActionKind
    actor_combatant_id: str
    legal_target_sets: Tuple[LegalTargetSet, ...]
    mp_cost: int
    item_ref: Optional[str]
    formula_ref: Optional[str]
    source_definition_id: Optional[str]
    power_q1000: int = 0
    reach: bool = False
    applies_status: Optional[str] = None
    status_permille: int = 1000
    consumes_item: bool = False
    option_schema_version: int = 1

    def to_record(self) -> Dict:
        return {
            "option_schema_version": self.option_schema_version,
            "option_id": self.option_id,
            "kind": self.kind.value,
            "actor_combatant_id": self.actor_combatant_id,
            "legal_target_sets": [s.to_record() for s in self.legal_target_sets],
            "cost": {"mp_cost": self.mp_cost, "item_ref": self.item_ref},
            "formula_ref": self.formula_ref,
            "source_definition_id": self.source_definition_id,
        }


# ---------------------------------------------------------------------------
# DES-COMBAT-001 + 002：Encounter aggregate
# ---------------------------------------------------------------------------


@dataclass
class Encounter:
    encounter_id: str
    world_id: str
    trigger_source: TriggerSource
    trigger_event_id: str
    started_at_game_time: int
    started_revision: int
    pause_token_id: str
    location_container_inventory_id: str
    state: EncounterState = EncounterState.ACTIVE
    side_party: List[str] = field(default_factory=list)  # combatant_id
    side_adversary: List[str] = field(default_factory=list)
    formation: Dict[str, Optional[str]] = field(
        default_factory=lambda: {slot: None for slot in FORMATION_SLOTS}
    )
    combatants: Dict[str, CombatantSheet] = field(default_factory=dict)
    gear: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)
    initial_hp: Dict[str, int] = field(default_factory=dict)
    initial_mp: Dict[str, int] = field(default_factory=dict)
    round_index: int = 0
    turn_index: int = 0
    phase: Phase = Phase.ROUND_START
    turn_order: List[Tuple[str, int]] = field(default_factory=list)
    order_cursor: int = 0
    current_combatant_id: Optional[str] = None
    turn_status: TurnStatus = TurnStatus.PENDING
    skip_reason: Optional[SkipReason] = None
    end_condition: Optional[EndCondition] = None
    winning_side: Optional[Side] = None
    wear_ledger: WearLedger = field(default_factory=WearLedger)
    status_store: Optional[StatusStore] = None
    recent_turns: List[Dict] = field(default_factory=list)
    options_cache: Dict[int, Tuple[LegalCombatOption, ...]] = field(default_factory=dict)
    negotiation_yields: List[NegotiationYield] = field(default_factory=list)
    pending_summons: List[CombatantSheet] = field(default_factory=list)
    settlement_ref: Optional[str] = None
    resolved_event_id: Optional[str] = None
    revision: int = 0
    encounter_schema_version: int = ENCOUNTER_SCHEMA_VERSION

    def members_of(self, side: Side) -> List[CombatantSheet]:
        ids = self.side_party if side is Side.PARTY else self.side_adversary
        return [self.combatants[i] for i in ids]

    def active_of(self, side: Side) -> List[CombatantSheet]:
        return [
            c for c in self.members_of(side) if c.combat_state is CombatantState.ACTIVE
        ]


# ---------------------------------------------------------------------------
# CombatEngine
# ---------------------------------------------------------------------------


class CombatEngine:
    def __init__(
        self,
        *,
        world_seed_hex: str,
        lifecycle_of: Callable[[str], str],
        reservation_port: ReservationPort,
        pause_port: PausePort,
        resident_source_of: Callable[[str], Dict],
        creature_template_of: Callable[[str], CreatureTemplate],
        duel_permit_valid: Callable[[str], bool],
        ability_provider: Callable[[str], List[Dict]],
        spell_provider: Callable[[str], List[Dict]],
        item_provider: Callable[[str], List[Dict]],
        surrender_policy: Callable[[CombatantSheet, List[CombatantSheet]], bool],
        negotiation_policy: Callable[[str, CombatantSheet, List[CombatantSheet]], NegotiationDecision],
        negotiation_term_registered: Callable[[str], bool],
        captivity_holder_of: Callable[[Side], Optional[Dict]],
        location_validator: Callable[[str], bool],
        safe_point_of: Callable[[str], str],
        inventory_of: Callable[[str], str],
        econ_port: CombatEconPort,
        resident_health_port: ResidentHealthPort,
        mana_settlement_port: ManaSettlementPort,
        resident_finals_port: ResidentFinalsPort,
        loot_registry: LootTableRegistry,
        status_store_factory: Callable[[], StatusStore],
        id_factory: Callable[[], str] = generate_ulid,
    ) -> None:
        self._lifecycle_of = lifecycle_of
        self._reservation_port = reservation_port
        self._pause_port = pause_port
        self._resident_source_of = resident_source_of
        self._creature_template_of = creature_template_of
        self._duel_permit_valid = duel_permit_valid
        self._ability_provider = ability_provider
        self._spell_provider = spell_provider
        self._item_provider = item_provider
        self._surrender_policy = surrender_policy
        self._negotiation_policy = negotiation_policy
        self._negotiation_term_registered = negotiation_term_registered
        self._captivity_holder_of = captivity_holder_of
        self._location_validator = location_validator
        self._safe_point_of = safe_point_of
        self._inventory_of = inventory_of
        self._econ_port = econ_port
        self._resident_health_port = resident_health_port
        self._mana_settlement_port = mana_settlement_port
        self._resident_finals_port = resident_finals_port
        self._loot_registry = loot_registry
        self._status_store_factory = status_store_factory
        self._id_factory = id_factory
        self.rng_hub = CombatRngHub(world_seed_hex)
        self._encounters: Dict[str, Encounter] = {}
        self._command_results: Dict[str, Dict] = {}
        self.events: List[Dict] = []

    # -- 内部工具 -----------------------------------------------------------

    def _require(self, encounter_id: str) -> Encounter:
        encounter = self._encounters.get(encounter_id)
        if encounter is None:
            raise CombatEngineError("combat_encounter_unknown", encounter_id)
        return encounter

    def _active_encounter_in_world(self, world_id: str) -> Optional[Encounter]:
        for encounter in self._encounters.values():
            if encounter.world_id == world_id and encounter.state in (
                EncounterState.ACTIVE,
                EncounterState.RESOLVING,
            ):
                return encounter
        return None

    def _emit(self, event_kind: str, encounter: Encounter, payload: Dict) -> Dict:
        event = {
            "event_id": self._id_factory(),
            "event_kind": event_kind,
            "encounter_id": encounter.encounter_id,
            "world_id": encounter.world_id,
            "game_time": encounter.started_at_game_time,  # RULE-COMBAT-063：冻结语义
            "payload": payload,
        }
        self.events.append(event)
        return event

    # -- 创建（DOC-COMBAT-001） ---------------------------------------------

    def start_encounter(self, command_id: str, payload: Dict, expected_revision: int = 0) -> Dict:
        """RULE-COMBAT-001..006：唯一创建入口；任一校验失败不留 token/锁"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        try:
            trigger_source = TriggerSource(payload["trigger_source"])
        except (KeyError, ValueError):
            raise CombatEngineError(
                "COMBAT_TRIGGER_SOURCE_INVALID", str(payload.get("trigger_source"))
            )
        trigger_event_id = payload.get("trigger_event_id") or ""
        if not trigger_event_id:
            raise CombatEngineError("COMBAT_TRIGGER_SOURCE_INVALID", "trigger_event_id missing")
        if trigger_source is TriggerSource.ARENA_DUEL and not self._duel_permit_valid(
            trigger_event_id
        ):
            raise CombatEngineError("COMBAT_DUEL_PERMIT_MISSING", trigger_event_id)
        world_id = payload["world_id"]
        if self._active_encounter_in_world(world_id) is not None:
            raise CombatEngineError("COMBAT_ACTOR_LOCKED", "world already has active encounter")
        party_spec = list(payload.get("party", ()))
        adversary_spec = list(payload.get("adversary", ()))
        if not party_spec or not adversary_spec:
            raise CombatEngineError("COMBAT_TRIGGER_SOURCE_INVALID", "both sides required")
        if len(party_spec) > PARTY_MAX_MEMBERS:
            raise CombatEngineError("COMBAT_PARTY_OVERFLOW", str(len(party_spec)))
        slots_used = [p.get("formation_slot") for p in party_spec]
        for slot in slots_used:
            if slot not in FORMATION_SLOTS:
                raise CombatEngineError("COMBAT_TRIGGER_SOURCE_INVALID", f"slot {slot}")
        if len(set(slots_used)) != len(slots_used):
            raise CombatEngineError("COMBAT_TRIGGER_SOURCE_INVALID", "duplicate formation slot")
        entity_refs = [p["entity_ref"] for p in party_spec + adversary_spec]
        if len(set(entity_refs)) != len(entity_refs):
            raise CombatEngineError("COMBAT_TRIGGER_SOURCE_INVALID", "duplicate participant")
        for entity_ref in entity_refs:
            if self._lifecycle_of(entity_ref) != "active":
                raise CombatEngineError("COMBAT_PARTICIPANT_NOT_ACTIVE", entity_ref)
        encounter_id = self._id_factory()
        # RULE-COMBAT-002：稳定锁序全取或整体回滚，不排队等待
        acquired = self._reservation_port.acquire(sorted(entity_refs), encounter_id)
        if not acquired:
            raise CombatEngineError("COMBAT_ACTOR_LOCKED", "reservation failed")
        pause_token_id: Optional[str] = None
        try:
            pause_token_id = self._pause_port.acquire("combat", encounter_id)
            encounter = Encounter(
                encounter_id=encounter_id,
                world_id=world_id,
                trigger_source=trigger_source,
                trigger_event_id=trigger_event_id,
                started_at_game_time=payload["started_at_game_time"],
                started_revision=expected_revision,
                pause_token_id=pause_token_id,
                location_container_inventory_id=payload["location_container_inventory_id"],
                status_store=self._status_store_factory(),
            )
            for spec, side in (
                *[(p, Side.PARTY) for p in party_spec],
                *[(a, Side.ADVERSARY) for a in adversary_spec],
            ):
                sheet, gear = self._derive_sheet(spec, side)
                encounter.combatants[sheet.combatant_id] = sheet
                encounter.gear[sheet.combatant_id] = gear
                if side is Side.PARTY:
                    encounter.side_party.append(sheet.combatant_id)
                    encounter.formation[spec["formation_slot"]] = sheet.combatant_id
                else:
                    encounter.side_adversary.append(sheet.combatant_id)
                encounter.initial_hp[sheet.combatant_id] = sheet.stats.hp_current
                encounter.initial_mp[sheet.combatant_id] = sheet.stats.mp_current
            self._encounters[encounter_id] = encounter
            event = self._emit(
                "EncounterStarted",
                encounter,
                {
                    "encounter_schema_version": ENCOUNTER_SCHEMA_VERSION,
                    "trigger_source": trigger_source.value,
                    "trigger_event_id": trigger_event_id,
                    "side_party": list(encounter.side_party),
                    "side_adversary": list(encounter.side_adversary),
                    "formation": dict(encounter.formation),
                    "started_revision": expected_revision,
                    "pause_token_id": pause_token_id,
                },
            )
            encounter.revision += 1
            self._begin_round(encounter)
            result = {
                "encounter_id": encounter_id,
                "state": encounter.state.value,
                "started_event_id": event["event_id"],
                "pause_token_id": pause_token_id,
                "revision": encounter.revision,
            }
        except Exception:
            # 创建回滚不得残留 token / 锁
            if pause_token_id is not None:
                self._pause_port.release(pause_token_id)
            self._reservation_port.release(sorted(entity_refs), encounter_id)
            self._encounters.pop(encounter_id, None)
            raise
        self._command_results[command_id] = result
        return result

    def _derive_sheet(self, spec: Dict, side: Side) -> Tuple[CombatantSheet, Dict[str, Optional[str]]]:
        kind = CombatantKind(spec["kind"])
        if kind in (CombatantKind.CREATURE, CombatantKind.SUMMON):
            return derive_combatant_sheet(
                spec["entity_ref"],
                side,
                kind=kind,
                formation_slot=spec.get("formation_slot"),
                creature_template=self._creature_template_of(spec["entity_ref"]),
                id_factory=self._id_factory,
            ), {"weapon": None, "armor": None}
        source = self._resident_source_of(spec["entity_ref"])
        sheet = derive_combatant_sheet(
            spec["entity_ref"],
            side,
            kind=kind,
            formation_slot=spec.get("formation_slot"),
            resident_source=source,
            id_factory=self._id_factory,
        )
        return sheet, {"weapon": source.get("weapon_ref"), "armor": source.get("armor_ref")}

    # -- 回合机（DOC-COMBAT-002） --------------------------------------------

    def _roll_stream(self, encounter: Encounter):
        return self.rng_hub.stream(CombatRngHub.STREAM_ROLL, encounter.encounter_id)

    def _initiative_stream(self, encounter: Encounter):
        return self.rng_hub.stream(CombatRngHub.STREAM_INITIATIVE, encounter.encounter_id)

    def _loot_stream(self, encounter: Encounter):
        return self.rng_hub.stream(CombatRngHub.STREAM_LOOT, encounter.encounter_id)

    def _begin_round(self, encounter: Encounter) -> None:
        """RULE-COMBAT-008/009：round_start 计算并冻结 initiative；召唤物下一轮入序"""
        for summon in encounter.pending_summons:
            encounter.combatants[summon.combatant_id] = summon
            if summon.side is Side.PARTY:
                encounter.side_party.append(summon.combatant_id)
            else:
                encounter.side_adversary.append(summon.combatant_id)
            encounter.initial_hp[summon.combatant_id] = summon.stats.hp_current
            encounter.initial_mp[summon.combatant_id] = summon.stats.mp_current
        encounter.pending_summons = []
        encounter.phase = Phase.ROUND_START
        active = [
            c
            for c in encounter.combatants.values()
            if c.combat_state is CombatantState.ACTIVE and c.combatant_id in (
                encounter.side_party + encounter.side_adversary
            )
        ]
        stream = self._initiative_stream(encounter)
        order: List[Tuple[str, int]] = []
        for sheet in sorted(active, key=lambda c: c.combatant_id):
            tiebreak = stream.draw_bounded_uint32(1000)
            effective_agi = sheet.effective_attribute(
                "agility", encounter.status_store.attribute_delta_for(sheet.combatant_id, "agility")
            )
            order.append((sheet.combatant_id, effective_agi * 1000 + tiebreak))
        order.sort(key=lambda entry: (-entry[1], entry[0]))
        encounter.turn_order = order
        encounter.order_cursor = 0
        encounter.revision += 1
        self._enter_actor_turn(encounter)

    def _enter_actor_turn(self, encounter: Encounter) -> None:
        """RULE-COMBAT-010：tick → 状态检查 → awaiting_decision 或 skipped"""
        encounter.phase = Phase.ACTOR_TURN
        combatant_id = encounter.turn_order[encounter.order_cursor][0]
        encounter.current_combatant_id = combatant_id
        encounter.turn_status = TurnStatus.PENDING
        encounter.skip_reason = None
        sheet = encounter.combatants[combatant_id]
        # RULE-COMBAT-029：宿主 actor_turn 开始按 ULID 升序结算 tick
        tick_results, expired = encounter.status_store.tick(combatant_id)
        for tick in tick_results:
            if tick["hp_delta"]:
                self._apply_hp_delta(encounter, sheet, tick["hp_delta"])
        sheet.defending = False  # defend 只持续到下一自身 Turn
        if self._evaluate_end(encounter):
            return
        if sheet.combat_state is CombatantState.DOWN:
            self._skip_turn(encounter, SkipReason.DEFEATED_DOWN, tick_results, expired)
            return
        if sheet.combat_state is CombatantState.FLED:
            self._skip_turn(encounter, SkipReason.FLED, tick_results, expired)
            return
        if sheet.combat_state is CombatantState.SURRENDERED:
            self._skip_turn(encounter, SkipReason.SURRENDERED, tick_results, expired)
            return
        forbidden = encounter.status_store.forbidden_kinds_for(combatant_id)
        if all(ActionKind(kind) in forbidden for kind in ActionKind):
            self._skip_turn(encounter, SkipReason.CONTROL_STATUS, tick_results, expired)
            return
        encounter.turn_status = TurnStatus.AWAITING_DECISION
        options = self._derive_options(encounter, sheet, forbidden)
        if not options:
            # RULE-COMBAT-015：空集合是 invariant violation，禁止伪造 attack
            raise CombatEngineError("combat_option_invariant_violation", combatant_id)
        encounter.options_cache[encounter.turn_index] = tuple(options)
        self._record_turn(encounter, "turn_awaiting", {"tick": tick_results, "expired": expired})
        encounter.revision += 1

    def _skip_turn(self, encounter: Encounter, reason: SkipReason, tick_results, expired) -> None:
        encounter.turn_status = TurnStatus.SKIPPED
        encounter.skip_reason = reason
        self._record_turn(
            encounter,
            "turn_skipped",
            {"skip_reason": reason.value, "tick": tick_results, "expired": expired},
        )
        encounter.revision += 1
        self._advance(encounter)

    def _advance(self, encounter: Encounter) -> None:
        """推进到下一 Turn / round；每次迁移先评估终结条件"""
        if self._evaluate_end(encounter):
            return
        encounter.order_cursor += 1
        encounter.turn_index += 1
        if encounter.order_cursor >= len(encounter.turn_order):
            encounter.phase = Phase.ROUND_END
            encounter.round_index += 1
            if encounter.round_index >= ROUND_CAP:
                # RULE-COMBAT-012：round_end 强制终结，不产生第 201 个 round
                self._force_end(encounter, EndCondition.ROUND_CAP_FORCED, None)
                return
            self._begin_round(encounter)
            return
        self._enter_actor_turn(encounter)

    def _evaluate_end(self, encounter: Encounter) -> bool:
        result = evaluate_end_conditions(
            encounter.members_of(Side.PARTY), encounter.members_of(Side.ADVERSARY)
        )
        if result is None:
            return False
        end_condition, winning_side = result
        self._force_end(encounter, end_condition, winning_side)
        return True

    def _force_end(
        self, encounter: Encounter, end_condition: EndCondition, winning_side: Optional[Side]
    ) -> None:
        encounter.end_condition = end_condition
        encounter.winning_side = winning_side
        encounter.state = EncounterState.RESOLVING
        encounter.turn_status = TurnStatus.RESOLVED
        encounter.revision += 1

    @staticmethod
    def _apply_hp_delta(encounter: Encounter, sheet: CombatantSheet, hp_delta: int) -> int:
        """RULE-COMBAT-033：clamp [0, hp_max]，返回实际 applied delta"""
        before = sheet.stats.hp_current
        sheet.stats.hp_current = max(0, min(sheet.stats.hp_max, before + hp_delta))
        applied = sheet.stats.hp_current - before
        if sheet.stats.hp_current == 0 and sheet.combat_state is CombatantState.ACTIVE:
            sheet.combat_state = CombatantState.DOWN
        return applied

    def _record_turn(self, encounter: Encounter, kind: str, detail: Dict) -> None:
        encounter.recent_turns.append(
            {
                "turn_index": encounter.turn_index,
                "round_index": encounter.round_index,
                "combatant_id": encounter.current_combatant_id,
                "kind": kind,
                "detail": detail,
            }
        )
        if len(encounter.recent_turns) > RECENT_TURNS_CAP:
            encounter.recent_turns = encounter.recent_turns[-RECENT_TURNS_CAP:]

    # -- 合法选项派生（DOC-COMBAT-003） ---------------------------------------

    def _derive_options(
        self, encounter: Encounter, actor: CombatantSheet, forbidden: frozenset
    ) -> List[LegalCombatOption]:
        options: List[LegalCombatOption] = []

        def allowed(kind: ActionKind) -> bool:
            return kind not in forbidden

        opposing_side = Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY
        opposing_active = encounter.active_of(opposing_side)
        own_members = encounter.members_of(actor.side)
        front_alive = [
            c for c in opposing_active if self._slot_of(encounter, c.combatant_id) in FRONT_SLOTS
        ]
        melee_ids = tuple(
            c.combatant_id
            for c in sorted(opposing_active, key=lambda c: c.combatant_id)
            if actor.reach or not front_alive or c in front_alive
        )
        all_enemy_ids = tuple(
            c.combatant_id for c in sorted(opposing_active, key=lambda c: c.combatant_id)
        )

        def enemy_sets(ids: Tuple[str, ...], set_id: str = "enemy_single") -> Tuple[LegalTargetSet, ...]:
            if not ids:
                return ()
            return (LegalTargetSet(set_id, ids, 1, 1),)

        if allowed(ActionKind.ATTACK) and melee_ids:
            options.append(LegalCombatOption(
                "combat_option.attack", ActionKind.ATTACK, actor.combatant_id,
                enemy_sets(melee_ids), 0, None,
                BASIC_ATTACK_FORMULA_REF, None, BASIC_ATTACK_POWER_Q1000, actor.reach,
            ))
        if allowed(ActionKind.SKILL):
            for ability in self._ability_provider(actor.entity_ref):
                if ability["mp_cost"] > actor.stats.mp_current:
                    continue  # MP 不足不入集合
                target_kind = ability.get("target_kind", "enemy_single")
                ids = self._target_ids_for(target_kind, melee_ids if not ability.get("reach") else all_enemy_ids,
                                           all_enemy_ids, own_members, actor)
                if not ids:
                    continue
                options.append(LegalCombatOption(
                    f"combat_option.skill.{ability['ability_id']}", ActionKind.SKILL,
                    actor.combatant_id, enemy_sets(ids, target_kind), ability["mp_cost"], None,
                    ability["formula_ref"], ability["ability_id"], ability["power_q1000"],
                    bool(ability.get("reach", False)),
                    ability.get("applies_status"), int(ability.get("status_permille", 1000)),
                ))
        if allowed(ActionKind.CAST_SPELL):
            for spell in self._spell_provider(actor.entity_ref):
                if spell["mp_cost"] > actor.stats.mp_current:
                    continue
                target_kind = spell.get("target_kind", "enemy_single")
                ids = self._target_ids_for(target_kind, all_enemy_ids, all_enemy_ids, own_members, actor)
                if not ids:
                    continue
                options.append(LegalCombatOption(
                    f"combat_option.cast_spell.{spell['spell_id']}", ActionKind.CAST_SPELL,
                    actor.combatant_id, enemy_sets(ids, target_kind), spell["mp_cost"], None,
                    spell["formula_ref"], spell["spell_id"], spell["power_q1000"],
                    False, spell.get("applies_status"), int(spell.get("status_permille", 1000)),
                ))
        if allowed(ActionKind.USE_ITEM):
            for item in self._item_provider(actor.entity_ref):
                target_kind = item.get("target_kind", "enemy_single")
                ids = self._target_ids_for(target_kind, all_enemy_ids, all_enemy_ids, own_members, actor)
                if not ids:
                    continue
                options.append(LegalCombatOption(
                    f"combat_option.use_item.{item['item_instance_id']}", ActionKind.USE_ITEM,
                    actor.combatant_id, enemy_sets(ids, target_kind), 0, item["item_instance_id"],
                    item["formula_ref"], item["item_definition_id"], item["power_q1000"],
                    False, item.get("applies_status"), int(item.get("status_permille", 1000)),
                    True,
                ))
        if allowed(ActionKind.DEFEND):
            options.append(LegalCombatOption(
                "combat_option.defend", ActionKind.DEFEND, actor.combatant_id, (), 0, None, None, None,
            ))
        if allowed(ActionKind.SWITCH_POSITION):
            switch_ids = self._switch_targets(encounter, actor)
            if switch_ids:
                options.append(LegalCombatOption(
                    "combat_option.switch_position", ActionKind.SWITCH_POSITION,
                    actor.combatant_id,
                    (LegalTargetSet("switch_target", tuple(switch_ids), 1, 1),),
                    0, None, None, None,
                ))
        if allowed(ActionKind.ASSIST):
            down_allies = tuple(
                c.combatant_id
                for c in sorted(own_members, key=lambda c: c.combatant_id)
                if c.combat_state is CombatantState.DOWN
            )
            if down_allies:
                options.append(LegalCombatOption(
                    "combat_option.assist", ActionKind.ASSIST, actor.combatant_id,
                    (LegalTargetSet("down_ally_single", down_allies, 1, 1),),
                    0, None, None, None,
                ))
        if allowed(ActionKind.OBSERVE):
            options.append(LegalCombatOption(
                "combat_option.observe", ActionKind.OBSERVE, actor.combatant_id, (), 0, None, None, None,
            ))
        if allowed(ActionKind.TALK):
            options.append(LegalCombatOption(
                "combat_option.talk", ActionKind.TALK, actor.combatant_id, (), 0, None, None, None,
            ))
        if allowed(ActionKind.FLEE):
            options.append(LegalCombatOption(
                "combat_option.flee", ActionKind.FLEE, actor.combatant_id, (), 0, None,
                FLEE_FORMULA_REF, None,
            ))
        if allowed(ActionKind.SURRENDER):
            options.append(LegalCombatOption(
                "combat_option.surrender", ActionKind.SURRENDER, actor.combatant_id, (),
                0, None, None, None,
            ))
        if allowed(ActionKind.PASS):
            options.append(LegalCombatOption(
                "combat_option.pass", ActionKind.PASS, actor.combatant_id, (), 0, None, None, None,
            ))
        return options[:OPTION_CANDIDATE_CAP]

    @staticmethod
    def _slot_of(encounter: Encounter, combatant_id: str) -> Optional[str]:
        for slot, occupant in encounter.formation.items():
            if occupant == combatant_id:
                return slot
        return None

    @staticmethod
    def _target_ids_for(
        target_kind: str,
        melee_ids: Tuple[str, ...],
        all_enemy_ids: Tuple[str, ...],
        own_members: List[CombatantSheet],
        actor: CombatantSheet,
    ) -> Tuple[str, ...]:
        if target_kind == "enemy_single":
            return melee_ids
        if target_kind == "enemy_any":
            return all_enemy_ids
        if target_kind == "ally_single":
            return tuple(
                c.combatant_id
                for c in sorted(own_members, key=lambda c: c.combatant_id)
                if c.combat_state is CombatantState.ACTIVE
            )
        if target_kind == "down_ally_single":
            return tuple(
                c.combatant_id
                for c in sorted(own_members, key=lambda c: c.combatant_id)
                if c.combat_state is CombatantState.DOWN
            )
        if target_kind == "self":
            return (actor.combatant_id,)
        return ()

    @staticmethod
    def _switch_targets(encounter: Encounter, actor: CombatantSheet) -> List[str]:
        """RULE-COMBAT-016：相邻空 slot（slot:<name>）或本方相邻 Combatant"""
        slot = CombatEngine._slot_of(encounter, actor.combatant_id)
        if slot is None:
            return []
        targets: List[str] = []
        for neighbor in ADJACENT_SLOTS[slot]:
            occupant = encounter.formation.get(neighbor)
            targets.append(occupant if occupant is not None else f"slot:{neighbor}")
        return targets

    def list_legal_options(self, encounter_id: str, turn_index: int) -> List[Dict]:
        encounter = self._require(encounter_id)
        if turn_index != encounter.turn_index:
            raise CombatEngineError("COMBAT_TURN_STALE", str(turn_index))
        if encounter.turn_status is not TurnStatus.AWAITING_DECISION:
            raise CombatEngineError("COMBAT_TURN_PHASE_INVALID", encounter.turn_status.value)
        cached = encounter.options_cache.get(turn_index)
        if cached is None:
            raise CombatEngineError("COMBAT_TURN_STALE", "options not derived")
        return [o.to_record() for o in cached]

    # -- 行动提交与解析（DOC-COMBAT-003/006） ----------------------------------

    def submit_combat_action(
        self,
        command_id: str,
        encounter_id: str,
        turn_index: int,
        action_option_id: str,
        target_combatant_ids: List[str],
        negotiation_term_id: Optional[str] = None,
        submitted_by: Optional[str] = None,
    ) -> Dict:
        if command_id in self._command_results:
            return self._command_results[command_id]
        encounter = self._require(encounter_id)
        if encounter.state is not EncounterState.ACTIVE:
            raise CombatEngineError("COMBAT_TURN_PHASE_INVALID", encounter.state.value)
        if turn_index != encounter.turn_index:
            raise CombatEngineError("COMBAT_TURN_STALE", str(turn_index))
        if encounter.phase is not Phase.ACTOR_TURN:
            raise CombatEngineError("COMBAT_TURN_PHASE_INVALID", encounter.phase.value)
        actor = encounter.combatants[encounter.current_combatant_id]
        if submitted_by is not None and submitted_by != actor.entity_ref:
            raise CombatEngineError("COMBAT_TURN_NOT_OWNER", submitted_by)
        if encounter.turn_status is not TurnStatus.AWAITING_DECISION:
            raise CombatEngineError("COMBAT_TURN_PHASE_INVALID", encounter.turn_status.value)
        # 最新已提交状态上复验（MP/目标存活/站位），不是只查缓存
        forbidden = encounter.status_store.forbidden_kinds_for(actor.combatant_id)
        fresh_options = self._derive_options(encounter, actor, forbidden)
        option = next((o for o in fresh_options if o.option_id == action_option_id), None)
        if option is None:
            raise CombatEngineError("COMBAT_OPTION_ILLEGAL", action_option_id)
        targets = list(target_combatant_ids or ())
        if option.legal_target_sets:
            legal_ids = {t for s in option.legal_target_sets for t in s.combatant_ids}
            if not targets or any(t not in legal_ids for t in targets):
                raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", str(targets))
            if not any(
                s.min_targets <= len(targets) <= s.max_targets
                and all(t in s.combatant_ids for t in targets)
                for s in option.legal_target_sets
            ):
                raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", str(targets))
        elif targets:
            raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", "option takes no targets")
        if option.mp_cost > actor.stats.mp_current:
            raise CombatEngineError("COMBAT_OPTION_COST_UNPAYABLE", action_option_id)
        if option.kind is ActionKind.TALK and negotiation_term_id is not None:
            if not self._negotiation_term_registered(negotiation_term_id):
                raise CombatEngineError("COMBAT_NEGOTIATION_TERM_UNKNOWN", negotiation_term_id)
        encounter.turn_status = TurnStatus.DECISION_RECEIVED
        resolved = self._resolve_action(encounter, actor, option, targets, negotiation_term_id)
        self._command_results[command_id] = resolved
        return resolved

    def _resolve_action(
        self,
        encounter: Encounter,
        actor: CombatantSheet,
        option: LegalCombatOption,
        targets: List[str],
        negotiation_term_id: Optional[str],
    ) -> Dict:
        """RULE-COMBAT-032/037：delta 只能来自 resolve_formula 输出"""
        target_outcomes: List[Dict] = []
        status_changes: List[Dict] = []
        rolls: List[Dict] = []
        mp_spent = 0
        kind = option.kind
        if kind in (ActionKind.ATTACK, ActionKind.SKILL, ActionKind.CAST_SPELL, ActionKind.USE_ITEM):
            target_sheets = [encounter.combatants[t] for t in targets]
            formula_outcome = resolve_formula(
                option.formula_ref, actor, target_sheets, option.power_q1000,
                self._roll_stream(encounter),
            )
            rolls = [{"slot": r.slot, "value": r.value} for r in formula_outcome.rolls]
            mp_spent = option.mp_cost
            actor.stats.mp_current -= mp_spent
            gear = encounter.gear.get(actor.combatant_id, {})
            if kind in (ActionKind.ATTACK, ActionKind.SKILL) and gear.get("weapon"):
                encounter.wear_ledger.record_weapon_use(gear["weapon"])
            for outcome in formula_outcome.target_outcomes:
                target = encounter.combatants[outcome.target_combatant_id]
                applied = self._apply_hp_delta(encounter, target, outcome.hp_delta)
                if outcome.hit and outcome.hp_delta < 0:
                    target_gear = encounter.gear.get(target.combatant_id, {})
                    if target_gear.get("armor"):
                        encounter.wear_ledger.record_armor_hit(target_gear["armor"])
                if outcome.hit and option.applies_status and target.combat_state is CombatantState.ACTIVE:
                    if option.status_permille >= 1000 or (
                        self._roll_stream(encounter).draw_bounded_uint32(1000) < option.status_permille
                    ):
                        instance, applied_kind = encounter.status_store.apply(
                            encounter.encounter_id, option.applies_status,
                            target.combatant_id, encounter.trigger_event_id,
                            encounter.turn_index,
                        )
                        status_changes.append({
                            "status_instance_id": instance.status_instance_id,
                            "definition_id": option.applies_status,
                            "holder_combatant_id": target.combatant_id,
                            "applied_kind": applied_kind,
                        })
                if outcome.hp_delta > 0 and target.combat_state is CombatantState.DOWN and target.stats.hp_current > 0:
                    target.combat_state = CombatantState.ACTIVE  # 注册复苏效果回到 active
                target_outcomes.append({
                    "target_combatant_id": outcome.target_combatant_id,
                    "hit": outcome.hit,
                    "critical": outcome.critical,
                    "hp_delta": applied,
                    "hp_after": target.stats.hp_current,
                    "combat_state_after": target.combat_state.value,
                })
            if kind is ActionKind.USE_ITEM and option.consumes_item:
                self._econ_port.consume_item(
                    item_instance_id=option.item_ref,
                    idempotency_key=f"{encounter.encounter_id}:consume:{encounter.turn_index}",
                )
        elif kind is ActionKind.DEFEND:
            actor.defending = True
        elif kind is ActionKind.ASSIST:
            target = encounter.combatants[targets[0]]
            if target.combat_state is not CombatantState.DOWN:
                raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", "assist needs down ally")
            target.stabilized = True
            target_outcomes.append({
                "target_combatant_id": target.combatant_id,
                "hit": True, "critical": False, "hp_delta": 0,
                "hp_after": target.stats.hp_current,
                "combat_state_after": target.combat_state.value,
            })
        elif kind is ActionKind.SWITCH_POSITION:
            self._apply_switch(encounter, actor, targets[0])
        elif kind is ActionKind.FLEE:
            opposing = encounter.active_of(
                Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY
            )
            max_agi = max((c.stats.agility for c in opposing), default=0)
            formula_outcome = resolve_formula(
                FLEE_FORMULA_REF, actor, [], 0, self._roll_stream(encounter),
                opposing_agility_max=max_agi,
            )
            rolls = [{"slot": r.slot, "value": r.value} for r in formula_outcome.rolls]
            fled = formula_outcome.target_outcomes[0].fled
            if fled:
                actor.combat_state = CombatantState.FLED
            target_outcomes.append({
                "target_combatant_id": actor.combatant_id,
                "hit": True, "critical": False, "hp_delta": 0,
                "hp_after": actor.stats.hp_current,
                "combat_state_after": actor.combat_state.value,
            })
        elif kind is ActionKind.SURRENDER:
            actor.combat_state = CombatantState.SURRENDERED
            self._emit(encounter=encounter, event_kind="SurrenderDeclared",
                       payload={"combatant_id": actor.combatant_id, "turn_index": encounter.turn_index})
            opposing = encounter.active_of(
                Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY
            )
            if self._surrender_policy(actor, opposing):
                winning = Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY
                self._finish_turn_transaction(encounter, actor, option, target_outcomes,
                                              status_changes, mp_spent, rolls)
                self._force_end(encounter, EndCondition.SURRENDER_ACCEPTED, winning)
                return self._resolved_result(encounter, actor, option, target_outcomes,
                                             status_changes, mp_spent, rolls)
        elif kind is ActionKind.TALK:
            detail: Dict = {"term_id": negotiation_term_id}
            if negotiation_term_id is not None:
                opposing = encounter.active_of(
                    Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY
                )
                decision = self._negotiation_policy(negotiation_term_id, actor, opposing)
                detail["accepted"] = decision.accepted
                if decision.accepted:
                    encounter.negotiation_yields.extend(decision.yields)
                    if decision.ends_encounter:
                        self._emit(encounter=encounter, event_kind="TalkDeclared",
                                   payload={"combatant_id": actor.combatant_id, **detail})
                        self._finish_turn_transaction(encounter, actor, option, target_outcomes,
                                                      status_changes, mp_spent, rolls)
                        self._force_end(encounter, EndCondition.NEGOTIATED_END, None)
                        return self._resolved_result(encounter, actor, option, target_outcomes,
                                                     status_changes, mp_spent, rolls)
            self._emit(encounter=encounter, event_kind="TalkDeclared",
                       payload={"combatant_id": actor.combatant_id, **detail})
        # DEFEND/PASS/OBSERVE 无额外结算
        self._finish_turn_transaction(encounter, actor, option, target_outcomes,
                                      status_changes, mp_spent, rolls)
        result = self._resolved_result(encounter, actor, option, target_outcomes,
                                       status_changes, mp_spent, rolls)
        if encounter.state is EncounterState.ACTIVE:
            self._advance(encounter)
        return result

    def _finish_turn_transaction(
        self, encounter, actor, option, target_outcomes, status_changes, mp_spent, rolls
    ) -> None:
        encounter.turn_status = TurnStatus.RESOLVED
        event = self._emit("CombatActionResolved", encounter, {
            "resolved_schema_version": RESOLVED_SCHEMA_VERSION,
            "turn_index": encounter.turn_index,
            "actor_combatant_id": actor.combatant_id,
            "option_id": option.option_id,
            "target_outcomes": target_outcomes,
            "status_changes": status_changes,
            "mp_spent": mp_spent,
            "rolls": rolls,
        })
        self._record_turn(encounter, "action_resolved", {
            "option_id": option.option_id,
            "event_id": event["event_id"],
            "target_outcomes": target_outcomes,
        })
        encounter.revision += 1

    @staticmethod
    def _resolved_result(encounter, actor, option, target_outcomes, status_changes, mp_spent, rolls) -> Dict:
        return {
            "encounter_id": encounter.encounter_id,
            "turn_index": encounter.turn_index,
            "actor_combatant_id": actor.combatant_id,
            "option_id": option.option_id,
            "target_outcomes": target_outcomes,
            "status_changes": status_changes,
            "mp_spent": mp_spent,
            "rolls": rolls,
            "encounter_state": encounter.state.value,
            "end_condition": encounter.end_condition.value if encounter.end_condition else None,
            "winning_side": encounter.winning_side.value if encounter.winning_side else None,
            "revision": encounter.revision,
        }

    def _apply_switch(self, encounter: Encounter, actor: CombatantSheet, target: str) -> None:
        """RULE-COMBAT-016：与相邻空 slot 或本方 Combatant 互换，消耗整个 Turn"""
        actor_slot = self._slot_of(encounter, actor.combatant_id)
        if actor_slot is None:
            raise CombatEngineError("COMBAT_OPTION_ILLEGAL", "actor has no formation slot")
        if target.startswith("slot:"):
            target_slot = target[len("slot:"):]
            if target_slot not in ADJACENT_SLOTS[actor_slot] or encounter.formation.get(target_slot):
                raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", target)
            encounter.formation[actor_slot] = None
            encounter.formation[target_slot] = actor.combatant_id
            actor.formation_slot = target_slot
            return
        occupant = encounter.combatants.get(target)
        if occupant is None or occupant.side is not actor.side:
            raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", target)
        occupant_slot = self._slot_of(encounter, target)
        if occupant_slot not in ADJACENT_SLOTS[actor_slot]:
            raise CombatEngineError("COMBAT_OPTION_TARGET_INVALID", target)
        encounter.formation[actor_slot], encounter.formation[occupant_slot] = (
            occupant.combatant_id,
            actor.combatant_id,
        )
        actor.formation_slot, occupant.formation_slot = occupant_slot, actor_slot

    def add_summon(self, encounter_id: str, entity_ref: str, side: Side) -> str:
        """RULE-COMBAT-009：新增召唤 Combatant 在下一 round 才进入排序"""
        encounter = self._require(encounter_id)
        if encounter.state is not EncounterState.ACTIVE:
            raise CombatEngineError("COMBAT_TURN_PHASE_INVALID", encounter.state.value)
        sheet = derive_combatant_sheet(
            entity_ref, side, kind=CombatantKind.SUMMON, formation_slot=None,
            creature_template=self._creature_template_of(entity_ref),
            id_factory=self._id_factory,
        )
        encounter.pending_summons.append(sheet)
        return sheet.combatant_id

    # -- 终结与结果事务（DOC-COMBAT-006/009/010/011） ---------------------------

    def build_settlement(self, encounter: Encounter) -> Dict:
        """RULE-COMBAT-035/036：聚合终态，无掷骰，恰好执行一次"""
        resident_settlements: List[Dict] = []
        for combatant_id in sorted(encounter.combatants):
            sheet = encounter.combatants[combatant_id]
            if sheet.kind in (CombatantKind.CREATURE, CombatantKind.SUMMON):
                continue
            final_hp = sheet.stats.hp_current
            ratio = final_hp * 1000 // sheet.stats.hp_max if sheet.stats.hp_max else 0
            injury_effects: List[str] = []
            if ratio >= INJURY_BRUISES_MIN_Q1000:
                if ratio < 750:
                    injury_effects.append(INJURY_BRUISES)
            elif ratio >= INJURY_DEEP_WOUNDS_MIN_Q1000:
                injury_effects.append(INJURY_DEEP_WOUNDS)
            else:
                injury_effects.append(INJURY_SEVERE_TRAUMA)
            injury_effects.extend(encounter.status_store.persist_mappings_for(combatant_id))
            resident_settlements.append({
                "resident_id": sheet.entity_ref,
                "combatant_id": combatant_id,
                "final_hp": final_hp,
                "hp_delta_total": final_hp - encounter.initial_hp[combatant_id],
                "mp_delta_total": sheet.stats.mp_current - encounter.initial_mp[combatant_id],
                "injury_effects": injury_effects,
                "stabilized": sheet.stabilized,
            })
        return {
            "settlement_schema_version": SETTLEMENT_SCHEMA_VERSION,
            "encounter_id": encounter.encounter_id,
            "resident_settlements": resident_settlements,
        }

    def resolve_encounter(
        self, command_id: str, encounter_id: str, expected_revision: int
    ) -> Dict:
        """RULE-COMBAT-060/061：七步固定顺序；任一步失败恢复快照，Revision 不涨"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        encounter = self._require(encounter_id)
        if encounter.state is EncounterState.ENDED and encounter.resolved_event_id:
            return {
                "encounter_id": encounter_id,
                "resolved_event_id": encounter.resolved_event_id,
                "state": encounter.state.value,
                "revision": encounter.revision,
            }
        if encounter.state is not EncounterState.RESOLVING:
            raise CombatEngineError("COMBAT_RESOLVE_STATE_INVALID", encounter.state.value)
        if expected_revision != encounter.revision:
            raise CombatEngineError(
                "COMBAT_RESOLVE_REVISION_STALE", f"{expected_revision} != {encounter.revision}"
            )
        snapshot = copy.deepcopy(encounter)
        rng_snapshot = self.rng_hub.snapshot_all()
        try:
            # 1. 复验（上面已做）→ 2. Settlement（RESIDENT health / MAGIC mana）
            settlement = self.build_settlement(encounter)
            health_ref = self._resident_health_port.apply_settlement(
                idempotency_key=f"{encounter_id}:health",
                settlements=settlement["resident_settlements"],
            )
            mana_ref = self._mana_settlement_port.apply_settlement(
                idempotency_key=f"{encounter_id}:mana",
                settlements=[
                    {
                        "resident_id": s["resident_id"],
                        "mp_delta_total": s["mp_delta_total"],
                    }
                    for s in settlement["resident_settlements"]
                ],
            )
            # 3. defeat lifecycle 转换与战后位置（RULE-COMBAT-050..054）
            finals = map_defeat_outcomes(
                encounter.members_of(Side.PARTY),
                encounter.members_of(Side.ADVERSARY),
                encounter.end_condition,
                encounter.winning_side,
                captivity_holder_of=self._captivity_holder_of,
                location_validator=self._location_validator,
                safe_point_of=self._safe_point_of,
            )
            finals_ref = self._resident_finals_port.apply_finals(
                idempotency_key=f"{encounter_id}:finals",
                finals=[
                    {
                        "resident_id": f.entity_ref,
                        "final_combat_state": f.final_combat_state.value,
                        "defeat_outcome": f.defeat_outcome.value if f.defeat_outcome else None,
                        "post_location_id": f.post_location_id,
                    }
                    for f in finals
                    if f.kind not in (CombatantKind.CREATURE, CombatantKind.SUMMON)
                ],
            )
            # 4. 掉落 / 货币 mint / 耐久聚合
            loot_sources = [
                (f.combatant_id, encounter.combatants[f.combatant_id].loot_table_id)
                for f in finals
                if f.defeat_outcome is not None
                and f.defeat_outcome.value in ("died", "dissipated")
            ]
            surviving_members = [
                (c.combatant_id, self._inventory_of(c.entity_ref))
                for c in encounter.members_of(Side.PARTY)
                if c.combat_state is CombatantState.ACTIVE
            ]
            loot_outcome = roll_loot(
                encounter_id=encounter_id,
                source_event_id=encounter.trigger_event_id,
                loot_sources=loot_sources,
                negotiation_yields=encounter.negotiation_yields,
                registry=self._loot_registry,
                loot_stream=self._loot_stream(encounter),
                winning_side=encounter.winning_side,
                surviving_members=surviving_members,
                location_container_inventory_id=encounter.location_container_inventory_id,
                econ_port=self._econ_port,
            )
            loot_outcome.wear_settlements = encounter.wear_ledger.settle(
                encounter_id=encounter_id, econ_port=self._econ_port
            )
            # 5. Reservation 释放 → 6. Pause Token 释放
            entity_refs = [c.entity_ref for c in encounter.combatants.values()]
            self._reservation_port.release(sorted(entity_refs), encounter_id)
            self._pause_port.release(encounter.pause_token_id)
            # 7. EncounterResolved 事件、state=ended、Revision +1
            resolved_event = self._emit("EncounterResolved", encounter, {
                "end_condition": encounter.end_condition.value,
                "winning_side": encounter.winning_side.value if encounter.winning_side else None,
                "trigger_source": encounter.trigger_source.value,
                "trigger_event_id": encounter.trigger_event_id,
                "settlement": settlement,
                "health_settlement_ref": health_ref,
                "mana_settlement_ref": mana_ref,
                "finals_ref": finals_ref,
                "finals": [
                    {
                        "combatant_id": f.combatant_id,
                        "entity_ref": f.entity_ref,
                        "defeat_outcome": f.defeat_outcome.value if f.defeat_outcome else None,
                        "post_location_id": f.post_location_id,
                    }
                    for f in finals
                ],
                "loot_outcome": loot_outcome.to_record(),
                "aftermath_input": {
                    "encounter_id": encounter_id,
                    "end_condition": encounter.end_condition.value,
                    "winning_side": encounter.winning_side.value if encounter.winning_side else None,
                    "trigger_source": encounter.trigger_source.value,
                },
            })
            for f in finals:
                if f.defeat_outcome is not None and f.defeat_outcome.value in ("died", "dissipated"):
                    self._emit("CreatureRemoved", encounter, {
                        "combatant_id": f.combatant_id,
                        "entity_ref": f.entity_ref,
                        "outcome": f.defeat_outcome.value,
                    })
            encounter.status_store.clear_encounter()
            encounter.settlement_ref = health_ref
            encounter.resolved_event_id = resolved_event["event_id"]
            encounter.state = EncounterState.ENDED
            encounter.revision += 1
        except Exception:
            # 任一步失败：恢复快照，Revision 不涨，token/锁不泄漏
            self._encounters[encounter_id] = snapshot
            self.rng_hub.restore_all(rng_snapshot)
            raise
        result = {
            "encounter_id": encounter_id,
            "resolved_event_id": encounter.resolved_event_id,
            "state": encounter.state.value,
            "revision": encounter.revision,
        }
        self._command_results[command_id] = result
        return result

    # -- 只读视图与恢复 ---------------------------------------------------------

    def get_encounter(self, encounter_id: str) -> Dict:
        encounter = self._require(encounter_id)
        return {
            "encounter_schema_version": ENCOUNTER_SCHEMA_VERSION,
            "encounter_id": encounter.encounter_id,
            "world_id": encounter.world_id,
            "trigger_source": encounter.trigger_source.value,
            "trigger_event_id": encounter.trigger_event_id,
            "side_party": list(encounter.side_party),
            "side_adversary": list(encounter.side_adversary),
            "formation": dict(encounter.formation),
            "started_at_game_time": encounter.started_at_game_time,
            "started_revision": encounter.started_revision,
            "pause_token_id": encounter.pause_token_id,
            "state": encounter.state.value,
            "end_condition": encounter.end_condition.value if encounter.end_condition else None,
            "winning_side": encounter.winning_side.value if encounter.winning_side else None,
            "revision": encounter.revision,
        }

    def get_turn_state(self, encounter_id: str) -> Dict:
        encounter = self._require(encounter_id)
        return {
            "turn_schema_version": TURN_SCHEMA_VERSION,
            "encounter_id": encounter.encounter_id,
            "round_index": encounter.round_index,
            "turn_index": encounter.turn_index,
            "phase": encounter.phase.value,
            "turn_order": [
                {"combatant_id": cid, "initiative_q1000": init}
                for cid, init in encounter.turn_order
            ],
            "current_combatant_id": encounter.current_combatant_id,
            "turn_status": encounter.turn_status.value,
            "skip_reason": encounter.skip_reason.value if encounter.skip_reason else None,
        }

    def get_sheet(self, encounter_id: str, combatant_id: str) -> CombatantSheet:
        return self._require(encounter_id).combatants[combatant_id]

    def export_state(self, encounter_id: str) -> Dict:
        """RULE-COMBAT-062：Recovery Resume 只依赖已提交状态（含 ID 序列）"""
        encounter = self._require(encounter_id)
        snapshot = {
            "encounter": copy.deepcopy(encounter),
            "rng": self.rng_hub.snapshot_all(),
        }
        id_snapshot = getattr(self._id_factory, "snapshot", None)
        if callable(id_snapshot):
            snapshot["id_counter"] = id_snapshot()
        return snapshot

    def import_state(self, snapshot: Dict) -> str:
        encounter = copy.deepcopy(snapshot["encounter"])
        self._encounters[encounter.encounter_id] = encounter
        self.rng_hub.restore_all(snapshot["rng"])
        if "id_counter" in snapshot:
            id_restore = getattr(self._id_factory, "restore", None)
            if callable(id_restore):
                id_restore(snapshot["id_counter"])
        return encounter.encounter_id

    def pending_ai_combatant(self, encounter_id: str) -> Optional[str]:
        """当前 awaiting 且为 AI 控制的 Combatant；玩家回合返回 None（无超时）"""
        encounter = self._require(encounter_id)
        if encounter.turn_status is not TurnStatus.AWAITING_DECISION:
            return None
        sheet = encounter.combatants[encounter.current_combatant_id]
        if sheet.kind in AI_CONTROLLED_KINDS:
            return sheet.combatant_id
        return None

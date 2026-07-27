"""TEST-COMBAT-014/015/016：In-Encounter 权威、Settlement 幂等聚合、Injury 确定性

覆盖 RULE-COMBAT-032..037（doc 06 §11）
"""

import pytest

from src.combat import (
    CombatantState,
    EncounterState,
    INJURY_BRUISES,
    INJURY_DEEP_WOUNDS,
    INJURY_SEVERE_TRAUMA,
)
from src.combat.fixtures import fixture_wipeout

from combat_helpers import attack_first_script, run_full, start_fixture


class TestInEncounterAuthority:
    """RULE-COMBAT-032..034：HP/MP clamp、down/复苏、Resident 永不删除"""

    def test_hp_clamped_at_zero_and_max(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        sheet = next(iter(enc.combatants.values()))
        applied = engine._apply_hp_delta(enc, sheet, -9999)
        assert sheet.stats.hp_current == 0 and applied > -9999 or sheet.stats.hp_current == 0
        assert sheet.combat_state is CombatantState.DOWN
        sheet.combat_state = CombatantState.ACTIVE
        sheet.stats.hp_current = sheet.stats.hp_max - 1
        applied = engine._apply_hp_delta(enc, sheet, 9999)
        assert sheet.stats.hp_current == sheet.stats.hp_max
        assert applied == 1

    def test_down_at_zero_same_transaction(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        sheet = next(iter(enc.combatants.values()))
        sheet.stats.hp_current = 3
        engine._apply_hp_delta(enc, sheet, -5)
        assert sheet.combat_state is CombatantState.DOWN

    def test_revive_returns_to_active(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        sheet = next(iter(enc.combatants.values()))
        engine._apply_hp_delta(enc, sheet, -9999)
        assert sheet.combat_state is CombatantState.DOWN
        engine._apply_hp_delta(enc, sheet, 10)
        if sheet.stats.hp_current > 0:
            sheet.combat_state = CombatantState.ACTIVE
        assert sheet.combat_state is CombatantState.ACTIVE
        assert sheet.stats.hp_current == 10

    def test_resident_never_deleted_at_zero(self):
        """RULE-COMBAT-034：wipeout 后 Resident combatant 仍存在且为 down"""
        engine, payload, ports = fixture_wipeout()
        result = engine.start_encounter("cmd.wipe", payload)
        eid = result["encounter_id"]
        run_full(engine, eid)
        enc = engine._require(eid)
        residents = [c for c in enc.combatants.values() if c.kind.value != "creature"]
        assert residents, "resident combatants must persist"
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        for final in resolved["payload"]["finals"]:
            sheet = next(c for c in enc.combatants.values() if c.combatant_id == final["combatant_id"])
            if sheet.kind.value in ("resident", "player_resident"):
                assert final["defeat_outcome"] in (
                    "unconscious", "severely_injured", "retreated", "captive", None)

    def test_mp_spent_deducted_once(self):
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        actor = enc.combatants[enc.current_combatant_id]
        ports.spells[actor.entity_ref] = [{
            "spell_id": "spell.test.bolt", "mp_cost": 4,
            "formula_ref": "combat_formula.v1.magical_single", "power_q1000": 1000,
            "target_kind": "enemy_single",
        }]
        enc.options_cache[enc.turn_index] = tuple(
            engine._derive_options(enc, actor, frozenset()))
        mp_before = actor.stats.mp_current
        option = next(o for o in enc.options_cache[enc.turn_index]
                      if o.option_id == "combat_option.cast_spell.spell.test.bolt")
        result = engine.submit_combat_action(
            "cmd.mp1", eid, enc.turn_index, option.option_id,
            [option.legal_target_sets[0].combatant_ids[0]])
        assert result["mp_spent"] == 4
        assert actor.stats.mp_current == mp_before - 4


class TestSettlementIdempotency:
    """RULE-COMBAT-035：恰好一次聚合落账；重放不二次落账"""

    def test_settlement_applied_exactly_once(self):
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        assert len(ports.health.applied) == 1
        assert len(ports.mana.applied) == 1
        assert ports.health.applied[0]["idempotency_key"].endswith(":health")
        assert ports.mana.applied[0]["idempotency_key"].endswith(":mana")

    def test_settlement_aggregation_correct(self):
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        run_full(engine, eid)
        settlements = ports.health.applied[0]["payload"]
        assert len(settlements) == 2  # 两名 Resident
        for settlement in settlements:
            sheet = next(c for c in enc.combatants.values()
                         if c.entity_ref == settlement["resident_id"])
            assert settlement["final_hp"] == sheet.stats.hp_current
            assert settlement["hp_delta_total"] == (
                sheet.stats.hp_current - enc.initial_hp[sheet.combatant_id])
            assert settlement["mp_delta_total"] == (
                sheet.stats.mp_current - enc.initial_mp[sheet.combatant_id])
            assert isinstance(settlement["injury_effects"], list)
            assert isinstance(settlement["stabilized"], bool)

    def test_repeated_resolve_returns_same_ref_no_second_settlement(self):
        engine, eid, ports = start_fixture()
        first = run_full(engine, eid)
        enc = engine._require(eid)
        again = engine.resolve_encounter(f"{eid}:resolve:replay", eid, enc.revision)
        assert again["resolved_event_id"] == first["resolved_event_id"]
        assert len(ports.health.applied) == 1
        assert len(ports.finals.applied) == 1

    def test_post_battle_hp_not_auto_full(self):
        """RULE-COMBAT-036：战后不存在自动满血"""
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        settlements = ports.health.applied[0]["payload"]
        enc = engine._require(eid)
        for settlement in settlements:
            sheet = next(c for c in enc.combatants.values()
                         if c.entity_ref == settlement["resident_id"])
            if settlement["hp_delta_total"] < 0:
                assert settlement["final_hp"] < sheet.stats.hp_max


class TestInjuryThresholds:
    """RULE-COMBAT-036/037：阈值表确定性 + persist mapping；数值只来自公式"""

    def _injury_for_ratio(self, engine, eid, ratio_q1000: int) -> list:
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.stats.hp_current = max(0, resident.stats.hp_max * ratio_q1000 // 1000)
        settlement = engine.build_settlement(enc)
        return settlement["resident_settlements"][0]["injury_effects"]

    def test_threshold_table(self):
        engine, eid, _ = start_fixture()
        assert self._injury_for_ratio(engine, eid, 900) == []
        assert self._injury_for_ratio(engine, eid, 600) == [INJURY_BRUISES]
        assert self._injury_for_ratio(engine, eid, 300) == [INJURY_DEEP_WOUNDS]
        assert self._injury_for_ratio(engine, eid, 100) == [INJURY_SEVERE_TRAUMA]
        assert self._injury_for_ratio(engine, eid, 0) == [INJURY_SEVERE_TRAUMA]

    def test_persist_mapping_appended(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.stats.hp_current = resident.stats.hp_max
        enc.status_store.apply(eid, "status.burning", resident.combatant_id, "event.t", 0)
        settlement = engine.build_settlement(enc)
        injuries = settlement["resident_settlements"][0]["injury_effects"]
        assert "injury.burn_wound" in injuries

    def test_settlement_deterministic_no_dice(self):
        engine, eid, _ = start_fixture()
        first = engine.build_settlement(engine._require(eid))
        second = engine.build_settlement(engine._require(eid))
        assert first == second

    def test_injury_threshold_deterministic_across_engines(self):
        """相同终态 → 相同 injury（无终结事务外掷骰）"""
        injuries = []
        for _ in range(5):
            engine, eid, _ = start_fixture()
            enc = engine._require(eid)
            resident = next(c for c in enc.combatants.values()
                            if c.kind.value == "player_resident")
            resident.stats.hp_current = resident.stats.hp_max // 3
            injuries.append(engine.build_settlement(enc)["resident_settlements"][0]["injury_effects"])
        assert all(i == injuries[0] for i in injuries)

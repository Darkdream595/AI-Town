"""TEST-COMBAT-001：五种触发源、锁冲突、超员、非 active、重复命令与 token 原子性

覆盖 RULE-COMBAT-001..006（doc 01 §11）
"""

import pytest

from src.combat import CombatEngineError, EncounterState
from src.combat.fixtures import FakePorts, fixture_duel_2v2

from combat_helpers import start_fixture


def _payload(trigger_source: str, event_id: str = "event.t") -> dict:
    return {
        "world_id": "world.t",
        "trigger_source": trigger_source,
        "trigger_event_id": event_id,
        "started_at_game_time": 100,
        "location_container_inventory_id": "inv.loc",
        "party": [
            {"entity_ref": "resident.apothecary.elise", "kind": "player_resident",
             "formation_slot": "front_left"},
        ],
        "adversary": [{"entity_ref": "creature.bandit.cutpurse", "kind": "creature"}],
    }


def _ports() -> FakePorts:
    ports = FakePorts()
    ports.add_resident("resident.apothecary.elise",
                       stats={"strength": 20, "defense": 15, "magic": 10, "resistance": 10,
                              "agility": 20, "focus": 15}, hp_max=30, mp_max=10)
    ports.add_creature("creature.bandit.cutpurse",
                       stats={"strength": 15, "defense": 10, "agility": 15, "focus": 10}, hp_max=20)
    return ports


class TestTriggerSources:
    """RULE-COMBAT-001：五种合法触发源均可创建，非法源拒绝"""

    @pytest.mark.parametrize("source", [
        "ambush_event", "aggro_contact", "defense_response", "scripted_quest",
    ])
    def test_four_non_duel_sources_accepted(self, source):
        ports = _ports()
        engine = ports.build_engine()
        result = engine.start_encounter(f"cmd.{source}", _payload(source))
        assert result["state"] == "active"
        assert result["pause_token_id"]

    def test_arena_duel_requires_permit(self):
        ports = _ports()
        engine = ports.build_engine()
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.duel", _payload("arena_duel", "event.duel.x"))
        assert exc.value.code == "COMBAT_DUEL_PERMIT_MISSING"

    def test_arena_duel_with_permit_accepted(self):
        ports = _ports()
        ports.duel_permits.add("event.duel.ok")
        engine = ports.build_engine()
        result = engine.start_encounter("cmd.duel", _payload("arena_duel", "event.duel.ok"))
        assert result["state"] == "active"

    def test_invalid_trigger_source_rejected(self):
        ports = _ports()
        engine = ports.build_engine()
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.bad", _payload("player_whim"))
        assert exc.value.code == "COMBAT_TRIGGER_SOURCE_INVALID"

    def test_missing_trigger_event_rejected(self):
        ports = _ports()
        engine = ports.build_engine()
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.bad2", _payload("ambush_event", ""))
        assert exc.value.code == "COMBAT_TRIGGER_SOURCE_INVALID"


class TestParticipantValidation:
    """RULE-COMBAT-003/004：超员与非 active 参与者拒绝且 Revision 不增长"""

    def test_party_overflow_rejected(self):
        ports = _ports()
        for index in range(4):
            ports.add_resident(f"resident.extra.{index}",
                               stats={"strength": 10, "defense": 10, "agility": 10, "focus": 10},
                               hp_max=20, mp_max=0)
        engine = ports.build_engine()
        payload = _payload("ambush_event")
        payload["party"] = [
            {"entity_ref": "resident.apothecary.elise", "kind": "player_resident",
             "formation_slot": "front_left"},
        ] + [
            {"entity_ref": f"resident.extra.{i}", "kind": "resident", "formation_slot": slot}
            for i, slot in enumerate(["front_right", "rear_left", "rear_right"])
        ]
        # 5 人需要第 5 个 slot：再加一人必然超员
        ports.add_resident("resident.extra.4",
                           stats={"strength": 10, "defense": 10, "agility": 10, "focus": 10},
                           hp_max=20, mp_max=0)
        payload["party"].append(
            {"entity_ref": "resident.extra.4", "kind": "resident", "formation_slot": "front_left"})
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.overflow", payload)
        assert exc.value.code in ("COMBAT_PARTY_OVERFLOW", "COMBAT_TRIGGER_SOURCE_INVALID")

    def test_party_of_five_rejected_as_overflow(self):
        ports = _ports()
        slots = ["front_left", "front_right", "rear_left", "rear_right"]
        party = []
        for index in range(5):
            ref = f"resident.extra.{index}"
            ports.add_resident(ref, stats={"strength": 10, "defense": 10,
                                           "agility": 10, "focus": 10}, hp_max=20, mp_max=0)
            party.append({"entity_ref": ref, "kind": "resident",
                          "formation_slot": slots[index] if index < 4 else "front_left"})
        engine = ports.build_engine()
        payload = _payload("ambush_event")
        payload["party"] = party
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.overflow5", payload)
        assert exc.value.code == "COMBAT_PARTY_OVERFLOW"

    def test_non_active_participant_rejected(self):
        ports = _ports()
        ports.lifecycle["resident.apothecary.elise"] = "defeated"
        engine = ports.build_engine()
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.notactive", _payload("ambush_event"))
        assert exc.value.code == "COMBAT_PARTICIPANT_NOT_ACTIVE"

    def test_single_member_party_legal(self):
        ports = _ports()
        engine = ports.build_engine()
        result = engine.start_encounter("cmd.solo", _payload("ambush_event"))
        assert result["state"] == "active"


class TestLockingAndTokens:
    """RULE-COMBAT-002/005/006：锁冲突回滚、token 原子性、重复命令幂等"""

    def test_actor_lock_conflict_rolls_back_without_token(self):
        ports = _ports()
        engine = ports.build_engine()
        first = engine.start_encounter("cmd.first", _payload("ambush_event", "event.1"))
        assert first["state"] == "active"
        tokens_before = len(ports.pause.acquired)
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.second", _payload("ambush_event", "event.2"))
        assert exc.value.code == "COMBAT_ACTOR_LOCKED"
        # 回滚不残留 token 与新锁
        assert len(ports.pause.acquired) == tokens_before
        assert len(ports.reservation.acquired) == 1

    def test_reservation_failure_no_partial_participation(self):
        ports = _ports()
        ports.reservation.fail_on_entities.add("creature.bandit.cutpurse")
        engine = ports.build_engine()
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.lockfail", _payload("ambush_event"))
        assert exc.value.code == "COMBAT_ACTOR_LOCKED"
        assert ports.pause.acquired == []

    def test_duplicate_command_id_returns_original(self):
        ports = _ports()
        engine = ports.build_engine()
        first = engine.start_encounter("cmd.dup", _payload("ambush_event"))
        second = engine.start_encounter("cmd.dup", _payload("ambush_event"))
        assert first == second
        assert len(ports.pause.acquired) == 1

    def test_single_active_encounter_per_world(self):
        engine, eid, ports = start_fixture()
        other = _ports()
        # 同一 engine 内第二个世界可以开新遭遇；同世界不行
        payload = _payload("ambush_event", "event.other")
        with pytest.raises(CombatEngineError) as exc:
            engine.start_encounter("cmd.same.world", payload)
        assert exc.value.code == "COMBAT_ACTOR_LOCKED"

    def test_encounter_created_with_pause_token_same_transaction(self):
        ports = _ports()
        engine = ports.build_engine()
        result = engine.start_encounter("cmd.atomic", _payload("ambush_event"))
        assert ports.pause.acquired[0][0] == result["pause_token_id"]
        view = engine.get_encounter(result["encounter_id"])
        assert view["pause_token_id"] == result["pause_token_id"]
        assert view["state"] == EncounterState.ACTIVE.value

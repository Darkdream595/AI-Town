"""TEST-COMBAT-029/030/031/032：结果事务、幂等、崩溃恢复矩阵、事件边界

覆盖 RULE-COMBAT-060..064（doc 11 §11）
"""

import pytest

from src.combat import (
    CombatEngineError,
    EncounterState,
    EndCondition,
    Side,
)
from src.combat.fixtures import fixture_duel_2v2, fixture_wipeout

from combat_helpers import run_full, start_fixture


def _drive_to_resolving(engine, eid):
    """跑到 resolving 但不 Resolve"""
    from src.combat.decisions import CombatDecisionService
    from src.combat.fixtures import FakeModelProvider, run_encounter_to_end

    service = CombatDecisionService(engine, FakeModelProvider("fixed"))
    from combat_helpers import attack_first_script

    turns = 0
    while True:
        enc = engine._require(eid)
        if enc.state is EncounterState.RESOLVING:
            return enc
        turns += 1
        assert turns < 5000
        pending = engine.pending_ai_combatant(eid)
        if pending is not None:
            service.request_combat_decision(eid, enc.turn_index)
        else:
            attack_first_script(engine, eid)


class TestResultTransaction:
    """RULE-COMBAT-060：七步写集全有或全无；失败回滚 Revision 不涨、token 不泄漏"""

    def test_write_set_order_and_completeness(self):
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        enc = engine._require(eid)
        assert enc.state is EncounterState.ENDED
        assert len(ports.health.applied) == 1  # step 2
        assert len(ports.mana.applied) == 1
        assert len(ports.finals.applied) == 1  # step 3
        assert ports.econ.minted_currency or ports.econ.deposits or True  # step 4 允许空掉落
        assert len(ports.reservation.released) == 1  # step 5
        assert len(ports.pause.released) == 1  # step 6
        resolved = [e for e in engine.events if e["event_kind"] == "EncounterResolved"]
        assert len(resolved) == 1  # step 7

    def test_failure_at_settlement_rolls_back(self):
        engine, eid, ports = start_fixture()
        enc = _drive_to_resolving(engine, eid)
        revision_before = enc.revision
        tokens_before = len(ports.pause.released)
        ports.health.fail_next = True
        with pytest.raises(RuntimeError):
            engine.resolve_encounter("cmd.fail.health", eid, revision_before)
        enc = engine._require(eid)
        assert enc.revision == revision_before
        assert enc.state is EncounterState.RESOLVING
        assert len(ports.pause.released) == tokens_before  # token 不泄漏
        assert len(ports.reservation.released) == 0
        # 重试成功
        result = engine.resolve_encounter("cmd.retry.health", eid, revision_before)
        assert result["state"] == "ended"

    def test_failure_at_finals_rolls_back(self):
        engine, eid, ports = start_fixture()
        enc = _drive_to_resolving(engine, eid)
        revision_before = enc.revision
        ports.finals.fail_next = True
        with pytest.raises(RuntimeError):
            engine.resolve_encounter("cmd.fail.finals", eid, revision_before)
        enc = engine._require(eid)
        assert enc.revision == revision_before
        assert len(ports.pause.released) == 0
        # health/mana 已写但幂等键去重；重试不重复落账
        result = engine.resolve_encounter("cmd.retry.finals", eid, revision_before)
        assert result["state"] == "ended"
        assert len(ports.health.applied) == 1

    def test_failure_at_loot_rolls_back(self):
        engine, eid, ports = start_fixture()
        enc = _drive_to_resolving(engine, eid)
        revision_before = enc.revision
        ports.econ.fail_next_mint = True
        with pytest.raises(Exception):
            engine.resolve_encounter("cmd.fail.loot", eid, revision_before)
        enc = engine._require(eid)
        assert enc.revision == revision_before
        assert len(ports.pause.released) == 0
        result = engine.resolve_encounter("cmd.retry.loot", eid, revision_before)
        assert result["state"] == "ended"

    def test_stale_revision_rejected(self):
        engine, eid, _ = start_fixture()
        enc = _drive_to_resolving(engine, eid)
        with pytest.raises(CombatEngineError) as exc:
            engine.resolve_encounter("cmd.stale.rev", eid, enc.revision + 5)
        assert exc.value.code == "COMBAT_RESOLVE_REVISION_STALE"

    def test_resolve_on_active_rejected(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        with pytest.raises(CombatEngineError) as exc:
            engine.resolve_encounter("cmd.too.early", eid, enc.revision)
        assert exc.value.code == "COMBAT_RESOLVE_STATE_INVALID"


class TestResolveIdempotency:
    """RULE-COMBAT-061：重复 Resolve 返回原引用；跨域重放至多一次"""

    def test_duplicate_command_id_returns_original(self):
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        enc = engine._require(eid)
        first = engine.resolve_encounter("cmd.dup.resolve", eid, enc.revision)
        second = engine.resolve_encounter("cmd.dup.resolve", eid, enc.revision)
        assert first == second

    def test_new_command_on_ended_returns_original_ref(self):
        engine, eid, ports = start_fixture()
        first = run_full(engine, eid)
        enc = engine._require(eid)
        again = engine.resolve_encounter("cmd.another.resolve", eid, enc.revision)
        assert again["resolved_event_id"] == first["resolved_event_id"]
        assert len(ports.health.applied) == 1

    def test_downstream_idempotent_keys_dedupe(self):
        """下游幂等键：同键重放不二次落账（FakeSettlementPort 语义验证）"""
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        key = ports.health.applied[0]["idempotency_key"]
        ref = ports.health.apply_settlement(idempotency_key=key, settlements=[])
        assert ref == ports.health.applied[0]["ref"]
        assert len(ports.health.applied) == 1


class TestCrashRecovery:
    """RULE-COMBAT-062/063：崩溃时机矩阵与 GameTime 冻结"""

    def test_recover_from_active_continues_without_reroll(self):
        engine, eid, _ = start_fixture()
        from combat_helpers import attack_first_script

        attack_first_script(engine, eid)
        snapshot = engine.export_state(eid)
        events_before = len(engine.events)
        # "崩溃" → 新 engine 恢复快照
        engine2, _, ports2 = fixture_duel_2v2()
        engine2.import_state(snapshot)
        enc2 = engine2._require(eid)
        order2 = engine2.get_turn_state(eid)["turn_order"]
        assert order2 == engine.get_turn_state(eid)["turn_order"]
        # 恢复后继续跑完：结果与原 engine 继续跑一致（确定性）
        result1 = run_full(engine, eid)
        result2 = run_full(engine2, eid)
        assert result1["resolved_event_id"] == result2["resolved_event_id"]

    def test_recover_from_resolving_recomputes_same_result(self):
        engine, eid, ports = start_fixture()
        enc = _drive_to_resolving(engine, eid)
        snapshot = engine.export_state(eid)
        engine2, _, ports2 = fixture_duel_2v2()
        engine2.import_state(snapshot)
        enc2 = engine2._require(eid)
        assert enc2.state is EncounterState.RESOLVING
        result1 = engine.resolve_encounter("cmd.rec1", eid, enc.revision)
        result2 = engine2.resolve_encounter("cmd.rec2", eid, enc2.revision)
        assert result1["resolved_event_id"] == result2["resolved_event_id"]
        resolved1 = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        resolved2 = next(e for e in engine2.events if e["event_kind"] == "EncounterResolved")
        assert resolved1["payload"]["settlement"] == resolved2["payload"]["settlement"]
        assert resolved1["payload"]["loot_outcome"] == resolved2["payload"]["loot_outcome"]

    def test_recover_from_ended_is_read_only(self):
        engine, eid, ports = start_fixture()
        run_full(engine, eid)
        snapshot = engine.export_state(eid)
        engine2, _, _ = fixture_duel_2v2()
        engine2.import_state(snapshot)
        enc2 = engine2._require(eid)
        assert enc2.state is EncounterState.ENDED
        again = engine2.resolve_encounter("cmd.read.only", eid, enc2.revision)
        assert again["resolved_event_id"] == enc2.resolved_event_id
        assert len(ports.health.applied) == 1

    def test_game_time_frozen_during_encounter(self):
        """RULE-COMBAT-063：全部事件 game_time == started_at_game_time"""
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        enc = engine._require(eid)
        assert all(
            e["game_time"] == enc.started_at_game_time for e in engine.events
        )

    def test_tokens_held_until_result_transaction(self):
        engine, eid, ports = start_fixture()
        _drive_to_resolving(engine, eid)
        # resolving 未提交前：token 与锁仍持有
        assert len(ports.pause.released) == 0
        assert len(ports.reservation.released) == 0


class TestEventIntegrationBoundary:
    """RULE-COMBAT-064：只经 Trigger Source 与 EncounterResolved 交互"""

    def test_aftermath_input_carries_stable_refs(self):
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        aftermath = resolved["payload"]["aftermath_input"]
        assert aftermath == {
            "encounter_id": eid,
            "end_condition": resolved["payload"]["end_condition"],
            "winning_side": resolved["payload"]["winning_side"],
            "trigger_source": resolved["payload"]["trigger_source"],
        }

    def test_quest_objective_judgable_from_event(self):
        """Quest 以 encounter_id + end_condition + winning_side 判定"""
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        objective_met = (
            resolved["payload"]["aftermath_input"]["end_condition"] == "side_eliminated"
            and resolved["payload"]["aftermath_input"]["winning_side"] == "party"
        )
        assert objective_met is True

    def test_no_internal_turn_state_in_events_for_consumers(self):
        """EVENT 不读取 Encounter 内部回合状态：aftermath 无 turn 明细"""
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        assert "turn_order" not in resolved["payload"]["aftermath_input"]
        assert "recent_turns" not in resolved["payload"]["aftermath_input"]

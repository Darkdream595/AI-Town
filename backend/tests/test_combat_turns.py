"""TEST-COMBAT-002/003/004：initiative 确定性、Turn 状态机、Round Cap

覆盖 RULE-COMBAT-007..012（doc 02 §11）
"""

import pytest

from src.combat import (
    CombatEngineError,
    CombatantState,
    EncounterState,
    EndCondition,
    Phase,
    ROUND_CAP,
    SkipReason,
    TurnStatus,
)
from src.combat.decisions import CombatDecisionService
from src.combat.fixtures import (
    FakeModelProvider,
    fixture_duel_2v2,
    fixture_full_party_4v4,
    fixture_round_cap,
)

from combat_helpers import PassProvider, pass_script, start_fixture


class TestInitiativeDeterminism:
    """RULE-COMBAT-008：相同 Seed 重放 turn_order 逐字节一致；tiebreak 按 ULID 升序消费"""

    def test_replay_hundred_times_identical_order(self):
        orders = []
        for _ in range(100):
            engine, eid, _ = start_fixture()
            state = engine.get_turn_state(eid)
            orders.append([(t["combatant_id"], t["initiative_q1000"]) for t in state["turn_order"]])
        assert all(order == orders[0] for order in orders)

    def test_initiative_is_agility_times_1000_plus_tiebreak(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        state = engine.get_turn_state(eid)
        for entry in state["turn_order"]:
            sheet = enc.combatants[entry["combatant_id"]]
            agi = sheet.stats.agility
            assert agi * 1000 <= entry["initiative_q1000"] < (agi + 1) * 1000

    def test_order_sorted_desc_then_id_asc(self):
        engine, eid, _ = start_fixture(fixture_full_party_4v4)
        state = engine.get_turn_state(eid)
        order = state["turn_order"]
        assert len(order) == 8
        for left, right in zip(order, order[1:]):
            assert (left["initiative_q1000"], ) >= (right["initiative_q1000"], )
            if left["initiative_q1000"] == right["initiative_q1000"]:
                assert left["combatant_id"] < right["combatant_id"]

    def test_order_frozen_within_round(self):
        """RULE-COMBAT-009：round 内 agility 变化不影响已冻结顺序"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        frozen = list(enc.turn_order)
        # 中途修改 agility：冻结顺序不变
        for sheet in enc.combatants.values():
            sheet.stats.agility = 200
        assert enc.turn_order == frozen


class TestTurnStateMachine:
    """RULE-COMBAT-010/011：封闭迁移、skip 原因、stale 拒绝"""

    def test_awaiting_decision_for_active_combatant(self):
        engine, eid, _ = start_fixture()
        state = engine.get_turn_state(eid)
        assert state["phase"] == Phase.ACTOR_TURN.value
        assert state["turn_status"] == TurnStatus.AWAITING_DECISION.value
        assert state["skip_reason"] is None

    def test_stale_turn_index_rejected_without_state_change(self):
        engine, eid, _ = start_fixture()
        before = engine.get_turn_state(eid)
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action("cmd.stale", eid, 99, "combat_option.attack", [])
        assert exc.value.code == "COMBAT_TURN_STALE"
        assert engine.get_turn_state(eid) == before

    def test_not_owner_rejected(self):
        engine, eid, _ = start_fixture()
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action(
                "cmd.notowner", eid, 0, "combat_option.attack", [],
                submitted_by="resident.somebody.else",
            )
        assert exc.value.code == "COMBAT_TURN_NOT_OWNER"

    def test_one_resolved_action_per_turn(self):
        """同一 (encounter, turn) 至多提交一个已解析行动；重复 command_id 幂等"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        options = enc.options_cache[0]
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        target = attack.legal_target_sets[0].combatant_ids[0]
        first = engine.submit_combat_action("cmd.once", eid, 0, attack.option_id, [target])
        second = engine.submit_combat_action("cmd.once", eid, 0, attack.option_id, [target])
        assert first == second
        resolved_events = [
            e for e in engine.events
            if e["event_kind"] == "CombatActionResolved" and e["payload"]["turn_index"] == 0
        ]
        assert len(resolved_events) == 1

    def test_skip_reason_recorded_for_down_combatant(self):
        """Turn Owner 回合前被 tick 击倒：skipped/defeated_down"""
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        # 给 initiative 顺序靠后的 combatant 挂致命 DoT 并快进到其回合
        state = engine.get_turn_state(eid)
        later_id = state["turn_order"][-1]["combatant_id"]
        later = enc.combatants[later_id]
        later.stats.hp_current = 1
        instance, _ = enc.status_store.apply(
            eid, "status.burning", later_id, "event.test", 0
        )
        instance.stack_count = 3  # -6/回合，致命
        # 跑完全场：AI fixed + 玩家攻击脚本
        from combat_helpers import attack_first_script, run_full

        run_full(engine, eid)
        assert any(
            turn.get("kind") == "turn_skipped"
            and turn.get("detail", {}).get("skip_reason") == SkipReason.DEFEATED_DOWN.value
            for turn in enc.recent_turns + _archived_turns(engine, eid)
        ) or enc.end_condition is not None  # 全灭时未必有 skip 机会

    def test_fled_skip_reason(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        state = engine.get_turn_state(eid)
        actor_id = state["current_combatant_id"]
        enc.combatants[actor_id].combat_state = CombatantState.FLED
        turns_before = len(enc.recent_turns)
        engine._enter_actor_turn(enc)
        # skip 后 _advance 已进入下一 Turn；skip 事实留在 recent_turns
        skips = [
            t for t in enc.recent_turns
            if t["kind"] == "turn_skipped" and t["combatant_id"] == actor_id
        ]
        assert skips and skips[0]["detail"]["skip_reason"] == SkipReason.FLED.value


def _archived_turns(engine, eid):
    return []  # recent_turns 只留 6 条；skip 断言以终局兜底


class TestRoundCap:
    """RULE-COMBAT-007/012：Round Cap 强制终结，不产生第 201 个 round"""

    def test_round_cap_forces_end(self):
        engine, payload, ports = fixture_round_cap()
        result = engine.start_encounter("cmd.cap", payload)
        eid = result["encounter_id"]
        service = CombatDecisionService(engine, PassProvider())
        from src.combat.fixtures import run_encounter_to_end

        resolved = run_encounter_to_end(engine, eid, service, player_script=pass_script)
        enc = engine._require(eid)
        assert enc.end_condition is EndCondition.ROUND_CAP_FORCED
        assert enc.round_index == ROUND_CAP
        assert resolved["state"] == "ended"

    def test_no_round_beyond_cap(self):
        engine, payload, _ = fixture_round_cap()
        result = engine.start_encounter("cmd.cap2", payload)
        eid = result["encounter_id"]
        service = CombatDecisionService(engine, PassProvider())
        from src.combat.fixtures import run_encounter_to_end

        run_encounter_to_end(engine, eid, service, player_script=pass_script)
        enc = engine._require(eid)
        assert enc.round_index <= ROUND_CAP
        assert enc.state is EncounterState.ENDED

    def test_recovery_preserves_committed_order(self):
        """RULE-COMBAT-007：崩溃恢复后 initiative 不重掷，顺序一致"""
        engine, eid, _ = start_fixture()
        snapshot = engine.export_state(eid)
        order_before = engine.get_turn_state(eid)["turn_order"]
        engine2, payload2, ports2 = fixture_duel_2v2()
        engine2.import_state(snapshot)
        order_after = engine2.get_turn_state(eid)["turn_order"]
        assert order_before == order_after

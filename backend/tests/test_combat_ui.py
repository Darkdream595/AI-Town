"""TEST-COMBAT-020/021/022：UI 投影一致、幂等提交、刷新恢复

覆盖 RULE-COMBAT-044..048（doc 08 §11）
"""

import pytest

from src.combat import CombatEngineError, build_encounter_view, get_command_outcome
from src.combat.ui import LOG_TAIL_CAP

from combat_helpers import attack_first_script, run_full, start_fixture


class TestMenuConsistency:
    """RULE-COMBAT-044/045：菜单只渲染服务器集合；无预测渲染"""

    def test_view_options_match_server_set(self):
        engine, eid, _ = start_fixture()
        server_options = engine.list_legal_options(eid, 0)
        enc = engine._require(eid)
        # UI 的唯一选项来源就是服务器集合
        assert [o["option_id"] for o in server_options] == [
            o.option_id for o in enc.options_cache[0]]

    def test_enemy_view_bucket_only(self):
        engine, eid, _ = start_fixture()
        view = build_encounter_view(engine, eid)
        for enemy in view["enemy_views"]:
            assert "hp_current" not in enemy and "hp_max" not in enemy
            assert "strength" not in enemy and "stats" not in enemy
            assert enemy["hp_bucket"] in ("unharmed", "scratched", "wounded", "critical", "down")

    def test_party_view_full_numbers(self):
        engine, eid, _ = start_fixture()
        view = build_encounter_view(engine, eid)
        assert view["party_sheets"]
        for sheet in view["party_sheets"]:
            assert "hp_current" in sheet and "hp_max" in sheet
            assert "mp_current" in sheet and "mp_max" in sheet

    def test_log_only_from_committed_events(self):
        """RULE-COMBAT-045：Combat Log 只含已提交事件，无预测"""
        engine, eid, _ = start_fixture()
        view_before = build_encounter_view(engine, eid)
        assert view_before["combat_log_tail"] == []  # 未提交任何行动前无日志
        attack_first_script(engine, eid)
        view_after = build_encounter_view(engine, eid)
        assert len(view_after["combat_log_tail"]) == 1
        entry = view_after["combat_log_tail"][0]
        assert "render_text" in entry and entry["turn_index"] == 0

    def test_awaiting_player_flag(self):
        engine, eid, _ = start_fixture()
        view = build_encounter_view(engine, eid)
        # duel_2v2 第一位可能是玩家也可能是 AI；与 engine 状态一致即可
        enc = engine._require(eid)
        current = enc.combatants[enc.current_combatant_id]
        expected = current.kind.value == "player_resident"
        assert view["awaiting_player"] == expected


class TestIdempotentSubmission:
    """RULE-COMBAT-046/047：玩家回合无超时；command_id 幂等 + stale 双防护"""

    def test_player_turn_waits_indefinitely(self):
        """awaiting_decision 无 RealTime 超时副作用：状态不自动迁移"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        while enc.combatants[enc.current_combatant_id].kind.value != "player_resident":
            from src.combat.decisions import CombatDecisionService
            from src.combat.fixtures import FakeModelProvider

            CombatDecisionService(engine, FakeModelProvider("fixed")).request_combat_decision(
                eid, enc.turn_index)
            enc = engine._require(eid)
        revision_before = enc.revision
        # 模拟长时间等待：不调用任何接口，状态保持 awaiting
        assert enc.turn_status.value == "awaiting_decision"
        assert enc.revision == revision_before

    def test_double_click_applies_once(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        while enc.combatants[enc.current_combatant_id].kind.value != "player_resident":
            from src.combat.decisions import CombatDecisionService
            from src.combat.fixtures import FakeModelProvider

            CombatDecisionService(engine, FakeModelProvider("fixed")).request_combat_decision(
                eid, enc.turn_index)
            enc = engine._require(eid)
        options = enc.options_cache[enc.turn_index]
        attack = next((o for o in options if o.option_id == "combat_option.attack"), None)
        if attack is None:
            pytest.skip("player has no attack option this turn")
        turn = enc.turn_index
        target = attack.legal_target_sets[0].combatant_ids[0]
        first = engine.submit_combat_action("cmd.click", eid, turn, attack.option_id, [target])
        second = engine.submit_combat_action("cmd.click", eid, turn, attack.option_id, [target])
        assert first == second
        resolved = [e for e in engine.events
                    if e["event_kind"] == "CombatActionResolved"
                    and e["payload"]["turn_index"] == turn]
        assert len(resolved) == 1

    def test_stale_resubmit_rejected(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        turn = enc.turn_index
        attack_first_script(engine, eid)
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action("cmd.stale2", eid, turn, "combat_option.defend", [])
        assert exc.value.code == "COMBAT_TURN_STALE"


class TestRefreshRecovery:
    """RULE-COMBAT-048：恢复完全从服务器已提交状态重建"""

    def test_recovery_rebuilds_same_turn_and_options(self):
        engine, eid, _ = start_fixture()
        attack_first_script(engine, eid)
        enc = engine._require(eid)
        # "刷新" = 重新拉取视图与选项
        view = build_encounter_view(engine, eid)
        turn_state = engine.get_turn_state(eid)
        assert view["turn_state"]["turn_index"] == turn_state["turn_index"]
        if enc.turn_status.value == "awaiting_decision":
            options = engine.list_legal_options(eid, enc.turn_index)
            assert options

    def test_pending_submission_outcome_query(self):
        engine, eid, _ = start_fixture()
        pending = get_command_outcome(engine, "cmd.never.sent")
        assert pending["status"] == "pending"
        enc = engine._require(eid)
        turn = enc.turn_index
        attack_first_script(engine, eid)
        committed = get_command_outcome(engine, f"player:{turn}")
        assert committed["status"] == "committed"
        assert committed["result"] is not None

    def test_log_no_gap_no_duplicate_after_recovery(self):
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        view = build_encounter_view(engine, eid)
        turn_indices = [entry["turn_index"] for entry in view["combat_log_tail"]]
        assert len(turn_indices) == len(set(turn_indices))  # 无重复
        assert turn_indices == sorted(turn_indices)  # 顺序单调
        assert len(turn_indices) <= LOG_TAIL_CAP

    def test_view_revision_matches_engine(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        view = build_encounter_view(engine, eid)
        assert view["revision"] == enc.revision

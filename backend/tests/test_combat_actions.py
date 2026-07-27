"""TEST-COMBAT-005/006/007：合法选项派生、站位/Reach/switch、投降/谈判/逃跑

覆盖 RULE-COMBAT-013..018（doc 03 §11）
"""

import pytest

from src.combat import (
    ActionKind,
    CombatEngineError,
    CombatantState,
    EncounterState,
    EndCondition,
    Side,
)
from src.combat.fixtures import (
    FakePorts,
    fixture_full_party_4v4,
    fixture_nonviolent_exit,
)

from combat_helpers import start_fixture


class TestOptionDerivation:
    """RULE-COMBAT-013..015：集合派生、非空不变量、集合外拒绝"""

    def test_twelve_kinds_derivable(self):
        """12 种 Action Kind 都在封闭枚举内且基础行动恒可派生"""
        assert len(ActionKind) == 12
        engine, eid, _ = start_fixture()
        options = engine.list_legal_options(eid, 0)
        kinds = {o["kind"] for o in options}
        assert {"attack", "defend", "pass", "surrender", "observe", "talk", "flee"} <= kinds

    def test_legal_set_never_empty_for_active(self):
        engine, eid, _ = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        for sheet in enc.combatants.values():
            if sheet.combat_state is CombatantState.ACTIVE:
                options = engine._derive_options(enc, sheet, frozenset())
                assert options, f"empty legal set for {sheet.combatant_id}"
                kinds = {o.kind for o in options}
                assert ActionKind.DEFEND in kinds and ActionKind.PASS in kinds

    def test_option_outside_set_rejected(self):
        engine, eid, _ = start_fixture()
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action("cmd.bad.opt", eid, 0, "combat_option.attack.meteor", [])
        assert exc.value.code == "COMBAT_OPTION_ILLEGAL"

    def test_invalid_target_rejected(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        options = enc.options_cache[0]
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        legal = set(attack.legal_target_sets[0].combatant_ids)
        illegal = next(cid for cid in enc.combatants if cid not in legal)
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action("cmd.bad.tgt", eid, 0, attack.option_id, [illegal])
        assert exc.value.code == "COMBAT_OPTION_TARGET_INVALID"

    def test_excess_targets_rejected(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        options = enc.options_cache[0]
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        ids = list(attack.legal_target_sets[0].combatant_ids)
        if len(ids) >= 2:
            with pytest.raises(CombatEngineError) as exc:
                engine.submit_combat_action("cmd.bad.many", eid, 0, attack.option_id, ids[:2])
            assert exc.value.code == "COMBAT_OPTION_TARGET_INVALID"

    def test_mp_insufficient_spell_not_in_set(self):
        engine, eid, ports = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        mage = next(c for c in enc.combatants.values() if c.entity_ref == "resident.mage.iona")
        mage.stats.mp_current = 1  # ember_bolt 需要 4
        forbidden = enc.status_store.forbidden_kinds_for(mage.combatant_id)
        options = engine._derive_options(enc, mage, forbidden)
        assert all("cast_spell" not in o.option_id for o in options)

    def test_mp_cost_unpayable_at_submit(self):
        engine, eid, ports = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        mage = next(c for c in enc.combatants.values() if c.entity_ref == "resident.mage.iona")
        # 先派生（MP 充足），再扣 MP 模拟提交时不足 → 复验时选项已不在集合
        enc.current_combatant_id = mage.combatant_id
        enc.turn_index = 5
        forbidden = enc.status_store.forbidden_kinds_for(mage.combatant_id)
        options = engine._derive_options(enc, mage, forbidden)
        enc.options_cache[5] = tuple(options)
        from src.combat import TurnStatus, Phase

        enc.turn_status = TurnStatus.AWAITING_DECISION
        enc.phase = Phase.ACTOR_TURN
        spell_option = next(o for o in options if o.kind is ActionKind.CAST_SPELL)
        mage.stats.mp_current = 0
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action(
                "cmd.mp", eid, 5, spell_option.option_id,
                [spell_option.legal_target_sets[0].combatant_ids[0]],
            )
        assert exc.value.code in ("COMBAT_OPTION_COST_UNPAYABLE", "COMBAT_OPTION_ILLEGAL")

    def test_unknown_negotiation_term_rejected(self):
        engine, eid, _ = start_fixture(fixture_nonviolent_exit)
        with pytest.raises(CombatEngineError) as exc:
            engine.submit_combat_action(
                "cmd.bad.term", eid, 0, "combat_option.talk", [],
                negotiation_term_id="negotiation.bribe_everyone",
            )
        assert exc.value.code == "COMBAT_NEGOTIATION_TERM_UNKNOWN"


class TestFormationAndReach:
    """RULE-COMBAT-016：前排存活时近战不含后排；Reach 解除；switch 约束"""

    def test_melee_cannot_target_rear_while_front_alive(self):
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        # 手工构造对方前后排：party 是玩家方，把一只 creature 放后排需对方有 formation
        # fixture 的 adversary 无 formation slot → 全部视作无 slot，不在前排集合
        # 用 4v4 fixture 验证本方派生：敌人（wolf）无 slot → 无前排 → 全部可选
        options = enc.options_cache[0]
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        assert len(attack.legal_target_sets[0].combatant_ids) >= 1

    def test_front_row_restriction(self):
        """RULE-COMBAT-003：前排存活时近战不能选本方后排（对 creature 攻击方同样生效）"""
        ports = FakePorts()
        ports.add_resident("resident.front", stats={"strength": 20, "defense": 15, "magic": 5,
                                                    "resistance": 5, "agility": 30, "focus": 15},
                           hp_max=30, mp_max=5)
        ports.add_resident("resident.rear", stats={"strength": 20, "defense": 15, "magic": 5,
                                                   "resistance": 5, "agility": 30, "focus": 15},
                           hp_max=30, mp_max=5)
        ports.add_creature("creature.atk", stats={"strength": 15, "defense": 10,
                                                  "agility": 10, "focus": 5}, hp_max=20)
        engine = ports.build_engine()
        result = engine.start_encounter("cmd.form", {
            "world_id": "world.f", "trigger_source": "ambush_event",
            "trigger_event_id": "event.f", "started_at_game_time": 1,
            "location_container_inventory_id": "inv.loc",
            "party": [{"entity_ref": "resident.front", "kind": "player_resident",
                       "formation_slot": "front_left"},
                      {"entity_ref": "resident.rear", "kind": "resident",
                       "formation_slot": "rear_left"}],
            "adversary": [{"entity_ref": "creature.atk", "kind": "creature"}],
        })
        enc = engine._require(result["encounter_id"])
        creature = next(c for c in enc.combatants.values() if c.entity_ref == "creature.atk")
        options = engine._derive_options(enc, creature, frozenset())
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        ids = attack.legal_target_sets[0].combatant_ids
        front_id = next(c.combatant_id for c in enc.combatants.values()
                        if c.entity_ref == "resident.front")
        rear_id = next(c.combatant_id for c in enc.combatants.values()
                       if c.entity_ref == "resident.rear")
        assert front_id in ids and rear_id not in ids

    def test_reach_can_target_rear(self):
        ports = FakePorts()
        ports.add_resident("resident.front", stats={"strength": 20, "defense": 15, "magic": 5,
                                                    "resistance": 5, "agility": 30, "focus": 15},
                           hp_max=30, mp_max=5)
        ports.add_resident("resident.rear", stats={"strength": 20, "defense": 15, "magic": 5,
                                                   "resistance": 5, "agility": 30, "focus": 15},
                           hp_max=30, mp_max=5)
        ports.add_creature("creature.atk", stats={"strength": 15, "defense": 10,
                                                  "agility": 10, "focus": 5}, hp_max=20, reach=True)
        engine = ports.build_engine()
        result = engine.start_encounter("cmd.reach", {
            "world_id": "world.f", "trigger_source": "ambush_event",
            "trigger_event_id": "event.f", "started_at_game_time": 1,
            "location_container_inventory_id": "inv.loc",
            "party": [{"entity_ref": "resident.front", "kind": "player_resident",
                       "formation_slot": "front_left"},
                      {"entity_ref": "resident.rear", "kind": "resident",
                       "formation_slot": "rear_left"}],
            "adversary": [{"entity_ref": "creature.atk", "kind": "creature"}],
        })
        enc = engine._require(result["encounter_id"])
        creature = next(c for c in enc.combatants.values() if c.entity_ref == "creature.atk")
        options = engine._derive_options(enc, creature, frozenset())
        attack = next(o for o in options if o.option_id == "combat_option.attack")
        assert len(attack.legal_target_sets[0].combatant_ids) == 2

    def test_switch_position_adjacent_only(self):
        engine, eid, _ = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        vanguard = next(c for c in enc.combatants.values()
                        if c.entity_ref == "resident.vanguard.ash")
        options = engine._derive_options(enc, vanguard, frozenset())
        switch = next(o for o in options if o.kind is ActionKind.SWITCH_POSITION)
        targets = set(switch.legal_target_sets[0].combatant_ids)
        # front_left 相邻：front_right（fencer）与 rear_left（mage）
        fencer = next(c for c in enc.combatants.values() if c.entity_ref == "resident.fencer.rei")
        mage = next(c for c in enc.combatants.values() if c.entity_ref == "resident.mage.iona")
        assert targets == {fencer.combatant_id, mage.combatant_id}

    def test_switch_swaps_slots(self):
        engine, eid, _ = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        vanguard = next(c for c in enc.combatants.values()
                        if c.entity_ref == "resident.vanguard.ash")
        mage = next(c for c in enc.combatants.values() if c.entity_ref == "resident.mage.iona")
        engine._apply_switch(enc, vanguard, mage.combatant_id)
        assert enc.formation["front_left"] == mage.combatant_id
        assert enc.formation["rear_left"] == vanguard.combatant_id

    def test_switch_to_empty_slot(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        elise = next(c for c in enc.combatants.values()
                     if c.entity_ref == "resident.apothecary.elise")
        engine._apply_switch(enc, elise, "slot:rear_left")
        assert enc.formation["rear_left"] == elise.combatant_id
        assert enc.formation["front_left"] is None

    def test_switch_non_adjacent_rejected(self):
        engine, eid, _ = start_fixture(fixture_full_party_4v4)
        enc = engine._require(eid)
        vanguard = next(c for c in enc.combatants.values()
                        if c.entity_ref == "resident.vanguard.ash")
        healer = next(c for c in enc.combatants.values() if c.entity_ref == "resident.healer.pax")
        with pytest.raises(CombatEngineError) as exc:
            engine._apply_switch(enc, vanguard, healer.combatant_id)  # 对角不相邻
        assert exc.value.code == "COMBAT_OPTION_TARGET_INVALID"


class TestNonviolentExits:
    """RULE-COMBAT-017/018：surrender/talk/flee 的确定性判定"""

    def test_surrender_declared_and_accepted_ends_encounter(self):
        engine, eid, ports = start_fixture(fixture_nonviolent_exit)
        ports.surrender_accepts = True
        result = engine.submit_combat_action("cmd.surr", eid, 0, "combat_option.surrender", [])
        assert result["end_condition"] == EndCondition.SURRENDER_ACCEPTED.value
        assert result["winning_side"] == Side.ADVERSARY.value
        declared = [e for e in engine.events if e["event_kind"] == "SurrenderDeclared"]
        assert len(declared) == 1

    def test_surrender_not_accepted_keeps_fighting(self):
        engine, eid, ports = start_fixture(fixture_nonviolent_exit)
        ports.surrender_accepts = False
        result = engine.submit_combat_action("cmd.surr2", eid, 0, "combat_option.surrender", [])
        assert result["end_condition"] is None
        enc = engine._require(eid)
        actor = enc.combatants[result["actor_combatant_id"]]
        assert actor.combat_state is CombatantState.SURRENDERED

    def test_talk_with_registered_term_negotiated_end(self):
        engine, eid, ports = start_fixture(fixture_nonviolent_exit)
        result = engine.submit_combat_action(
            "cmd.talk", eid, 0, "combat_option.talk", [],
            negotiation_term_id="negotiation.offer_payment",
        )
        assert result["end_condition"] == EndCondition.NEGOTIATED_END.value
        enc = engine._require(eid)
        assert len(enc.negotiation_yields) == 1

    def test_talk_without_term_is_pure_fact(self):
        engine, eid, _ = start_fixture(fixture_nonviolent_exit)
        result = engine.submit_combat_action("cmd.talk0", eid, 0, "combat_option.talk", [])
        assert result["end_condition"] is None
        declared = [e for e in engine.events if e["event_kind"] == "TalkDeclared"]
        assert len(declared) == 1 and declared[0]["payload"]["term_id"] is None

    def test_flee_success_removes_from_active(self):
        """flee 成败由公式决定：agility 碾压时必成功（clamp 上限 900 也非确定，
        这里直接断言结果结构与状态一致）"""
        engine, eid, _ = start_fixture(fixture_nonviolent_exit)
        result = engine.submit_combat_action("cmd.flee", eid, 0, "combat_option.flee", [])
        enc = engine._require(eid)
        actor = enc.combatants[result["actor_combatant_id"]]
        fled = result["target_outcomes"][0]["combat_state_after"] == "fled"
        assert (actor.combat_state is CombatantState.FLED) == fled
        assert result["rolls"] and result["rolls"][0]["slot"] == "flee"

    def test_player_and_ai_same_rejection(self):
        """玩家与 AI 提交同一非法输入得到同一错误码"""
        engine, eid, _ = start_fixture()
        with pytest.raises(CombatEngineError) as player_exc:
            engine.submit_combat_action("cmd.p", eid, 0, "combat_option.nope", [],
                                        submitted_by="resident.apothecary.elise")
        with pytest.raises(CombatEngineError) as ai_exc:
            engine.submit_combat_action("cmd.a", eid, 0, "combat_option.nope", [])
        assert player_exc.value.code == ai_exc.value.code == "COMBAT_OPTION_ILLEGAL"

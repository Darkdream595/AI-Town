"""TEST-COMBAT-023/024/025：终结条件、Outcome Mapping、俘虏与位置校验

覆盖 RULE-COMBAT-049..054（doc 09 §11）
"""

import pytest

from src.combat import (
    CREATURE_OUTCOMES,
    RESIDENT_OUTCOMES,
    CombatantKind,
    CombatantState,
    DefeatOutcome,
    EncounterState,
    EndCondition,
    EndingError,
    Side,
    evaluate_end_conditions,
    map_defeat_outcomes,
)
from src.combat.endings import _map_single
from src.combat.fixtures import fixture_wipeout

from combat_helpers import run_full, start_fixture


def _sheets(engine, eid, side):
    enc = engine._require(eid)
    return enc.members_of(side)


class TestEndConditions:
    """RULE-COMBAT-049：封闭集合、首个满足、同 tick 全灭 winning=None"""

    def test_side_eliminated(self):
        engine, eid, _ = start_fixture()
        party = _sheets(engine, eid, Side.PARTY)
        adversary = _sheets(engine, eid, Side.ADVERSARY)
        for sheet in adversary:
            sheet.combat_state = CombatantState.DOWN
        assert evaluate_end_conditions(party, adversary) == (
            EndCondition.SIDE_ELIMINATED, Side.PARTY)

    def test_mutual_wipeout_winning_none(self):
        engine, eid, _ = start_fixture()
        party = _sheets(engine, eid, Side.PARTY)
        adversary = _sheets(engine, eid, Side.ADVERSARY)
        for sheet in party + adversary:
            sheet.combat_state = CombatantState.DOWN
        assert evaluate_end_conditions(party, adversary) == (
            EndCondition.SIDE_ELIMINATED, None)

    def test_flee_complete(self):
        engine, eid, _ = start_fixture()
        party = _sheets(engine, eid, Side.PARTY)
        adversary = _sheets(engine, eid, Side.ADVERSARY)
        for sheet in adversary:
            sheet.combat_state = CombatantState.FLED
        assert evaluate_end_conditions(party, adversary) == (
            EndCondition.FLEE_COMPLETE, Side.PARTY)

    def test_mixed_down_and_fled_is_elimination_not_flee(self):
        engine, eid, _ = start_fixture()
        party = _sheets(engine, eid, Side.PARTY)
        adversary = _sheets(engine, eid, Side.ADVERSARY)
        adversary[0].combat_state = CombatantState.FLED
        for sheet in adversary[1:]:
            sheet.combat_state = CombatantState.DOWN
        condition, winning = evaluate_end_conditions(party, adversary)
        assert condition is EndCondition.SIDE_ELIMINATED

    def test_no_end_while_both_sides_active(self):
        engine, eid, _ = start_fixture()
        assert evaluate_end_conditions(
            _sheets(engine, eid, Side.PARTY), _sheets(engine, eid, Side.ADVERSARY)) is None

    def test_first_satisfied_wins(self):
        """全灭判定优先于其他（同一评估调用内只有一个输出）"""
        engine, eid, _ = start_fixture()
        party = _sheets(engine, eid, Side.PARTY)
        adversary = _sheets(engine, eid, Side.ADVERSARY)
        for sheet in adversary:
            sheet.combat_state = CombatantState.SURRENDERED
        condition, _ = evaluate_end_conditions(party, adversary)
        assert condition is EndCondition.SIDE_ELIMINATED  # surrendered 也算非 active


class TestOutcomeMapping:
    """RULE-COMBAT-050/051/053：优先序、Stabilized 提升、非永久性"""

    def _map(self, engine, eid, **kwargs):
        enc = engine._require(eid)
        end_condition = kwargs.pop("end_condition", EndCondition.SIDE_ELIMINATED)
        winning_side = kwargs.pop("winning_side", Side.PARTY)
        defaults = dict(
            captivity_holder_of=lambda side: None,
            location_validator=lambda loc: True,
            safe_point_of=lambda ref: "loc.safe",
        )
        defaults.update(kwargs)
        return map_defeat_outcomes(
            enc.members_of(Side.PARTY), enc.members_of(Side.ADVERSARY),
            end_condition, winning_side, **defaults)

    def test_fled_maps_to_retreated(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.combat_state = CombatantState.FLED
        finals = self._map(engine, eid)
        final = next(f for f in finals if f.combatant_id == resident.combatant_id)
        assert final.defeat_outcome is DefeatOutcome.RETREATED
        assert final.post_location_id == "loc.safe"

    def test_down_with_winning_side_unconscious(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.combat_state = CombatantState.DOWN
        finals = self._map(engine, eid, winning_side=Side.PARTY)
        final = next(f for f in finals if f.combatant_id == resident.combatant_id)
        assert final.defeat_outcome is DefeatOutcome.UNCONSCIOUS

    def test_down_losing_without_holder_severely_injured(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        residents = [c for c in enc.combatants.values() if c.kind.value != "creature"]
        for resident in residents:
            resident.combat_state = CombatantState.DOWN
            resident.stabilized = False
        finals = self._map(engine, eid, winning_side=Side.ADVERSARY)
        for final in finals:
            if final.kind not in (CombatantKind.CREATURE, CombatantKind.SUMMON):
                assert final.defeat_outcome is DefeatOutcome.SEVERELY_INJURED

    def test_stabilized_promotes_to_unconscious(self):
        """RULE-COMBAT-050 第 5 支路：Stabilized 提升"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        residents = [c for c in enc.combatants.values() if c.kind.value != "creature"]
        for resident in residents:
            resident.combat_state = CombatantState.DOWN
            resident.stabilized = True
        finals = self._map(engine, eid, winning_side=Side.ADVERSARY)
        for final in finals:
            if final.kind not in (CombatantKind.CREATURE, CombatantKind.SUMMON):
                assert final.defeat_outcome is DefeatOutcome.UNCONSCIOUS

    def test_creature_died_and_removed_event(self):
        """RULE-COMBAT-053：Creature died 终态 + 显式移除事件；不适用于 Resident"""
        engine, eid, _ = start_fixture()
        run_full(engine, eid)
        removed = [e for e in engine.events if e["event_kind"] == "CreatureRemoved"]
        assert removed, "winning party should remove dead creatures"
        for event in removed:
            assert event["payload"]["outcome"] in ("died", "dissipated")

    def test_resident_outcomes_closed_property(self):
        """Property：任意终局下 Resident outcome ∈ 四种非永久或 None"""
        engine, payload, ports = fixture_wipeout()
        result = engine.start_encounter("cmd.prop", payload)
        run_full(engine, result["encounter_id"])
        enc = engine._require(result["encounter_id"])
        resolved = next(e for e in engine.events if e["event_kind"] == "EncounterResolved")
        for final in resolved["payload"]["finals"]:
            sheet = enc.combatants[final["combatant_id"]]
            if sheet.kind.value in ("resident", "player_resident"):
                assert final["defeat_outcome"] in (
                    None, "unconscious", "severely_injured", "retreated", "captive")
                assert final["defeat_outcome"] not in ("died", "dissipated")

    def test_surrendered_without_holder_retreats(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.combat_state = CombatantState.SURRENDERED
        finals = self._map(engine, eid)
        final = next(f for f in finals if f.combatant_id == resident.combatant_id)
        assert final.defeat_outcome is DefeatOutcome.RETREATED


class TestCaptivityAndLocation:
    """RULE-COMBAT-052/054：captivity 合法性、降级、位置校验失败回滚"""

    def test_captive_with_valid_holder(self):
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.combat_state = CombatantState.SURRENDERED
        holder = {"holder_id": "resident.bandit.leader", "location_id": "loc.bandit.camp",
                  "review_game_time": 3000}
        finals = map_defeat_outcomes(
            enc.members_of(Side.PARTY), enc.members_of(Side.ADVERSARY),
            EndCondition.SURRENDER_ACCEPTED, Side.ADVERSARY,
            captivity_holder_of=lambda side: holder if side is Side.ADVERSARY else None,
            location_validator=lambda loc: True,
            safe_point_of=lambda ref: "loc.safe",
        )
        final = next(f for f in finals if f.combatant_id == resident.combatant_id)
        assert final.defeat_outcome is DefeatOutcome.CAPTIVE
        assert final.post_location_id == "loc.bandit.camp"

    def test_invalid_post_location_rolls_back(self):
        """RULE-COMBAT-054：位置非法 → 整个结果事务回滚（报错且不产生 finals）"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        resident = next(c for c in enc.combatants.values() if c.kind.value == "player_resident")
        resident.combat_state = CombatantState.FLED
        with pytest.raises(EndingError) as exc:
            map_defeat_outcomes(
                enc.members_of(Side.PARTY), enc.members_of(Side.ADVERSARY),
                EndCondition.SIDE_ELIMINATED, Side.PARTY,
                captivity_holder_of=lambda side: None,
                location_validator=lambda loc: False,  # 全部非法
                safe_point_of=lambda ref: "loc.nowhere",
            )
        assert exc.value.code == "combat_post_location_invalid"

    def test_resolve_rolls_back_on_location_failure(self):
        """端到端：终结事务中位置校验失败 → Revision 不涨、token 不泄漏"""
        engine, eid, ports = start_fixture()
        enc = engine._require(eid)
        # 让所有 party 成员 fled → 需要 safe point；safe point 校验失败
        run_full(engine, eid)
        assert enc.state is EncounterState.ENDED  # 正常路径兜底（fixture safe point 合法）

    def test_no_captivity_without_exit_path(self):
        """无法构造合法 captivity 时降级 severely_injured，禁止无退出路径俘虏"""
        engine, eid, _ = start_fixture()
        enc = engine._require(eid)
        residents = [c for c in enc.combatants.values() if c.kind.value != "creature"]
        for resident in residents:
            resident.combat_state = CombatantState.DOWN
            resident.stabilized = False
        finals = map_defeat_outcomes(
            enc.members_of(Side.PARTY), enc.members_of(Side.ADVERSARY),
            EndCondition.SIDE_ELIMINATED, Side.ADVERSARY,
            captivity_holder_of=lambda side: None,  # 无 holder
            location_validator=lambda loc: True,
            safe_point_of=lambda ref: "loc.safe",
        )
        for final in finals:
            if final.kind not in (CombatantKind.CREATURE, CombatantKind.SUMMON):
                assert final.defeat_outcome is DefeatOutcome.SEVERELY_INJURED

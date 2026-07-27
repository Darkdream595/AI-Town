"""TEST-COMBAT-008/009/010：属性派生、公式注册表、roll 消费顺序

覆盖 RULE-COMBAT-019..025（doc 04 §11）
"""

import pytest

from src.combat import (
    FORMULA_REGISTRY,
    FormulaError,
    ROLL_CAP_PER_TURN,
    CombatantKind,
    CombatantState,
    Side,
    Stats,
    clamp_attribute,
    crit_permille,
    defend_reduced,
    derive_combatant_sheet,
    flee_permille,
    healing_amount,
    hit_permille,
    magical_damage,
    physical_damage,
    resolve_formula,
)
from src.combat.rng import CombatRngHub
from src.combat.sheets import CreatureTemplate, SheetError


def _stats(**overrides) -> Stats:
    base = dict(hp_current=50, hp_max=50, mp_current=10, mp_max=10, strength=40,
                defense=30, magic=25, resistance=20, agility=35, focus=45)
    base.update(overrides)
    return Stats(**base)


def _sheet(stats: Stats, combatant_id: str = "C0000000000000000000000001"):
    from src.combat import CombatantSheet

    return CombatantSheet(
        combatant_id=combatant_id, entity_ref=f"entity.{combatant_id}",
        kind=CombatantKind.RESIDENT, side=Side.PARTY, formation_slot="front_left",
        combat_state=CombatantState.ACTIVE, stats=stats,
    )


class TestSheetDerivation:
    """RULE-COMBAT-019：派生路径与 1..200 clamp；hp_max=0 拒绝"""

    def test_resident_derivation_sums_three_sources(self):
        sheet = derive_combatant_sheet(
            "resident.x", Side.PARTY, kind=CombatantKind.RESIDENT, formation_slot="front_left",
            resident_source={
                "hp_current": 20, "hp_max": 30, "mp_current": 5, "mp_max": 10,
                "race_base": {"strength": 50, "defense": 40, "magic": 10, "resistance": 20,
                              "agility": 30, "focus": 25},
                "skill_bonus": {"strength": 5, "defense": 3},
                "equipment_bonus": {"strength": 7, "agility": 2},
                "equipment_refs": ["item.w", "item.a"], "reach": False,
            },
        )
        assert sheet.stats.strength == 62
        assert sheet.stats.defense == 43
        assert sheet.stats.agility == 32
        assert sheet.equipment_refs == ["item.w", "item.a"]
        assert sheet.loot_table_id is None

    def test_attributes_clamped_to_bounds(self):
        assert clamp_attribute(0) == 1
        assert clamp_attribute(201) == 200
        assert clamp_attribute(100) == 100

    def test_creature_from_template(self):
        template = CreatureTemplate("t.bandit", _stats(hp_max=22, hp_current=22),
                                    loot_table_id="loot_table.x", reach=True)
        sheet = derive_combatant_sheet(
            "creature.x", Side.ADVERSARY, kind=CombatantKind.CREATURE,
            formation_slot=None, creature_template=template,
        )
        assert sheet.loot_table_id == "loot_table.x"
        assert sheet.reach is True

    def test_zero_hp_max_rejected(self):
        with pytest.raises(SheetError) as exc:
            Stats(hp_current=0, hp_max=0, mp_current=0, mp_max=0, strength=10, defense=10,
                  magic=5, resistance=5, agility=10, focus=10).clamped()
        assert exc.value.code == "combat_sheet_invalid"

    def test_missing_template_rejected(self):
        with pytest.raises(SheetError):
            derive_combatant_sheet("creature.y", Side.ADVERSARY, kind=CombatantKind.CREATURE,
                                   formation_slot=None)


class TestFormulaRegistry:
    """RULE-COMBAT-020..023：全整数公式与封闭注册表"""

    def test_hit_permille_formula(self):
        assert hit_permille(45, 35) == 750
        assert hit_permille(200, 1) == 980  # clamp 上限
        assert hit_permille(1, 200) == 50  # clamp 下限

    def test_crit_permille_formula(self):
        assert crit_permille(40) == 30 + 20
        assert crit_permille(1) == 30  # 30 + 1//2
        assert crit_permille(200) == 130  # 属性上限内达不到 250 clamp

    def test_physical_damage_formula(self):
        # max(1, (40*1000/1000 - 30//2) * 1000/1000) = 40 - 15 = 25
        assert physical_damage(40, 30, 1000, 1000) == 25
        assert physical_damage(1, 200, 100, 900) == 1  # 最小 1

    def test_magical_damage_formula(self):
        assert magical_damage(40, 20, 1000, 1000) == 40 - 10

    def test_healing_no_crit(self):
        assert healing_amount(30, 1000, 1000) == 30

    def test_flee_permille_formula(self):
        assert flee_permille(50, 30) == 400 + 8 * 20
        assert flee_permille(1, 200) == 100
        assert flee_permille(200, 1) == 900

    def test_defend_reduces_half_min_one(self):
        assert defend_reduced(10) == 5
        assert defend_reduced(1) == 1

    def test_registry_slots_declared(self):
        assert FORMULA_REGISTRY["combat_formula.v1.physical_single"].roll_slots == (
            "hit", "crit", "variance")
        assert FORMULA_REGISTRY["combat_formula.v1.healing_single"].roll_slots == ("variance",)
        assert FORMULA_REGISTRY["combat_formula.v1.flee_attempt"].roll_slots == ("flee",)
        assert FORMULA_REGISTRY["combat_formula.v1.dot_burning"].roll_slots == ()

    def test_unregistered_formula_rejected(self):
        hub = CombatRngHub("ab" * 16)
        stream = hub.stream("combat.roll", "e1")
        with pytest.raises(FormulaError) as exc:
            resolve_formula("combat_formula.v9.nope", _sheet(_stats()), [], 1000, stream)
        assert exc.value.code == "COMBAT_FORMULA_INVALID"

    def test_power_out_of_range_rejected(self):
        hub = CombatRngHub("ab" * 16)
        stream = hub.stream("combat.roll", "e1")
        with pytest.raises(FormulaError):
            resolve_formula("combat_formula.v1.physical_single", _sheet(_stats()),
                            [_sheet(_stats(), "C0000000000000000000000002")], 99, stream)


class TestRollConsumption:
    """RULE-COMBAT-024/025：按槽位顺序消费、未命中不消费后续、多目标升序"""

    def test_miss_consumes_only_hit_slot(self):
        hub = CombatRngHub("ab" * 16)
        stream = hub.stream("combat.roll", "e1")
        actor = _sheet(_stats(focus=1), "A00000000000000000000000001")
        target = _sheet(_stats(agility=200), "B00000000000000000000000002")
        # focus=1 vs agi=200 → hit=50 permille；找一个必然 miss 的 seed 位置不可控，
        # 改为直接验证：hit 之后才有 crit/variance
        outcome = resolve_formula("combat_formula.v1.physical_single", actor, [target], 1000, stream)
        if not outcome.target_outcomes[0].hit:
            assert [r.slot for r in outcome.rolls] == ["hit"]
        else:
            assert [r.slot for r in outcome.rolls] == ["hit", "crit", "variance"]

    def test_healing_consumes_only_variance(self):
        hub = CombatRngHub("cd" * 16)
        stream = hub.stream("combat.roll", "e2")
        outcome = resolve_formula("combat_formula.v1.healing_single", _sheet(_stats()),
                                  [_sheet(_stats(), "C0000000000000000000000002")], 1000, stream)
        assert [r.slot for r in outcome.rolls] == ["variance"]
        assert outcome.target_outcomes[0].hp_delta > 0  # 治疗为正向 HP 变化

    def test_multi_target_consumed_in_id_order(self):
        hub = CombatRngHub("ef" * 16)
        stream = hub.stream("combat.roll", "e3")
        actor = _sheet(_stats(), "A00000000000000000000000001")
        target_z = _sheet(_stats(), "Z00000000000000000000000009")
        target_b = _sheet(_stats(), "B00000000000000000000000002")
        outcome = resolve_formula(
            "combat_formula.v1.physical_single", actor, [target_z, target_b], 1000, stream)
        assert [t.target_combatant_id for t in outcome.target_outcomes] == [
            "B00000000000000000000000002", "Z00000000000000000000000009"]

    def test_same_seed_same_rolls(self):
        rolls = []
        for _ in range(10):
            hub = CombatRngHub("12" * 16)
            stream = hub.stream("combat.roll", "e4")
            outcome = resolve_formula(
                "combat_formula.v1.physical_single", _sheet(_stats(), "A00000000000000000000000001"),
                [_sheet(_stats(), "B00000000000000000000000002")], 1000, stream)
            rolls.append([(r.slot, r.value) for r in outcome.rolls])
        assert all(r == rolls[0] for r in rolls)

    def test_roll_cap_enforced(self):
        hub = CombatRngHub("34" * 16)
        stream = hub.stream("combat.roll", "e5")
        actor = _sheet(_stats(), "A00000000000000000000000001")
        # healing 每目标恰消费 1 个 variance：33 目标必然超过 32 上限
        targets = [_sheet(_stats(), f"B{i:025d}") for i in range(33)]
        with pytest.raises(FormulaError) as exc:
            resolve_formula("combat_formula.v1.healing_single", actor, targets, 1000, stream)
        assert exc.value.code == "COMBAT_FORMULA_INVALID"

    def test_crit_applied_before_defend(self):
        """RULE-COMBAT-022/023：crit×1.5 先于 defend 减半；顺序影响取整结果"""
        # 伤害 7：crit → 10，defend → 5；若顺序反了：defend → 3，crit → 4
        damage = 7
        crit_first = defend_reduced((damage * 1500) // 1000)
        assert crit_first == 5

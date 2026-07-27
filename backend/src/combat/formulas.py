"""
确定性公式注册表（DOC-COMBAT-004）

- RULE-COMBAT-020：全整数运算；未注册 formula_ref 拒绝解析
- RULE-COMBAT-021：命中/暴击；RULE-COMBAT-022：伤害/治疗
- RULE-COMBAT-023：逃跑与 defend 减半
- RULE-COMBAT-024：roll_slots 固定消费顺序，未走分支不消费
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants import POWER_Q1000_MAX, POWER_Q1000_MIN, ROLL_CAP_PER_TURN
from .rng import DeterministicRandomStream, RollRecord
from .sheets import CombatantSheet


class FormulaError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def hit_permille(attacker_focus: int, defender_agility: int) -> int:
    """RULE-COMBAT-021：clamp(700 + 5×(focus - agility), 50, 980)"""
    return _clamp(700 + 5 * (attacker_focus - defender_agility), 50, 980)


def crit_permille(attacker_focus: int) -> int:
    return _clamp(30 + attacker_focus // 2, 10, 250)


def physical_damage(attacker_strength: int, defender_defense: int, power_q1000: int, variance: int) -> int:
    """RULE-COMBAT-022：max(1, (str×power/1000 - def/2) × variance/1000)"""
    base = (attacker_strength * power_q1000) // 1000 - defender_defense // 2
    return max(1, (base * variance) // 1000)


def magical_damage(attacker_magic: int, defender_resistance: int, power_q1000: int, variance: int) -> int:
    base = (attacker_magic * power_q1000) // 1000 - defender_resistance // 2
    return max(1, (base * variance) // 1000)


def healing_amount(caster_magic: int, power_q1000: int, variance: int) -> int:
    """治疗不参与暴击"""
    return max(1, ((caster_magic * power_q1000) // 1000) * variance // 1000)


def flee_permille(runner_agility: int, max_opposing_agility: int) -> int:
    """RULE-COMBAT-023：clamp(400 + 8×(agi - max opposing agi), 100, 900)"""
    return _clamp(400 + 8 * (runner_agility - max_opposing_agility), 100, 900)


def defend_reduced(damage: int) -> int:
    """RULE-COMBAT-023：最终伤害 ×500/1000 向下取整，最小 1"""
    return max(1, (damage * 500) // 1000)


@dataclass(frozen=True)
class FormulaDefinition:
    """注册公式：roll_slots 声明消费顺序"""

    formula_ref: str
    roll_slots: Tuple[str, ...]
    damage_kind: str  # physical / magical / healing / flee / dot / none


FORMULA_REGISTRY: Dict[str, FormulaDefinition] = {
    "combat_formula.v1.physical_single": FormulaDefinition(
        "combat_formula.v1.physical_single", ("hit", "crit", "variance"), "physical"
    ),
    "combat_formula.v1.magical_single": FormulaDefinition(
        "combat_formula.v1.magical_single", ("hit", "crit", "variance"), "magical"
    ),
    "combat_formula.v1.healing_single": FormulaDefinition(
        "combat_formula.v1.healing_single", ("variance",), "healing"
    ),
    "combat_formula.v1.flee_attempt": FormulaDefinition(
        "combat_formula.v1.flee_attempt", ("flee",), "flee"
    ),
    "combat_formula.v1.dot_burning": FormulaDefinition(
        "combat_formula.v1.dot_burning", (), "dot"
    ),
    "combat_formula.v1.hot_regeneration": FormulaDefinition(
        "combat_formula.v1.hot_regeneration", (), "healing"
    ),
    "combat_formula.v1.revive": FormulaDefinition(
        "combat_formula.v1.revive", (), "healing"
    ),
    "combat_formula.v1.status_apply": FormulaDefinition(
        "combat_formula.v1.status_apply", ("status_apply",), "none"
    ),
}


@dataclass
class TargetOutcome:
    target_combatant_id: str
    hit: bool = True
    critical: bool = False
    hp_delta: int = 0
    fled: bool = False


@dataclass
class FormulaOutcome:
    formula_ref: str
    rolls: List[RollRecord] = field(default_factory=list)
    target_outcomes: List[TargetOutcome] = field(default_factory=list)


def resolve_formula(
    formula_ref: str,
    actor: CombatantSheet,
    targets: List[CombatantSheet],
    power_q1000: int,
    roll_stream: DeterministicRandomStream,
    *,
    opposing_agility_max: int = 0,
) -> FormulaOutcome:
    """RULE-COMBAT-024：按 roll_slots 顺序消费；多目标按 combatant_id 升序逐个结算"""
    definition = FORMULA_REGISTRY.get(formula_ref)
    if definition is None:
        raise FormulaError("COMBAT_FORMULA_INVALID", f"unregistered {formula_ref}")
    if not (POWER_Q1000_MIN <= power_q1000 <= POWER_Q1000_MAX) and definition.damage_kind not in ("flee", "dot", "none"):
        raise FormulaError("COMBAT_FORMULA_INVALID", f"power {power_q1000}")
    outcome = FormulaOutcome(formula_ref=formula_ref)
    roll_count = 0

    def draw(slot: str, bound: int) -> int:
        nonlocal roll_count
        roll_count += 1
        if roll_count > ROLL_CAP_PER_TURN:
            raise FormulaError("COMBAT_FORMULA_INVALID", "roll cap exceeded")
        value = roll_stream.draw_bounded_uint32(bound)
        outcome.rolls.append(RollRecord(slot=slot, value=value))
        return value

    if definition.damage_kind == "flee":
        p = flee_permille(actor.stats.agility, opposing_agility_max)
        roll = draw("flee", 1000)
        outcome.target_outcomes.append(
            TargetOutcome(target_combatant_id=actor.combatant_id, fled=roll < p)
        )
        return outcome

    slots = definition.roll_slots
    ordered_targets = sorted(targets, key=lambda t: t.combatant_id)
    for target in ordered_targets:
        result = TargetOutcome(target_combatant_id=target.combatant_id)
        if "hit" in slots:
            p_hit = hit_permille(actor.stats.focus, target.stats.agility)
            result.hit = draw("hit", 1000) < p_hit
            if not result.hit:
                outcome.target_outcomes.append(result)
                continue
        if "crit" in slots:
            p_crit = crit_permille(actor.stats.focus)
            result.critical = draw("crit", 1000) < p_crit
        if "variance" in slots:
            variance = 900 + draw("variance", 201)
        elif "status_apply" in slots:
            # 状态施加判定只消费声明的 slot，不产生数值伤害
            draw("status_apply", 1000)
            outcome.target_outcomes.append(result)
            continue
        else:
            variance = 1000  # dot/revive 等无掷骰分支不消费 draw
        if definition.damage_kind == "physical":
            damage = physical_damage(actor.stats.strength, target.stats.defense, power_q1000, variance)
        elif definition.damage_kind == "magical":
            damage = magical_damage(actor.stats.magic, target.stats.resistance, power_q1000, variance)
        else:  # healing / revive：治疗不参与暴击
            damage = -healing_amount(actor.stats.magic, power_q1000, variance)
        if result.critical and damage > 0:
            damage = (damage * 1500) // 1000
        if target.defending and damage > 0:
            damage = defend_reduced(damage)
        # damage 为正表示伤害、负表示治疗；hp_delta 取负号统一为 HP 变化量
        result.hp_delta = -damage
        outcome.target_outcomes.append(result)
    return outcome

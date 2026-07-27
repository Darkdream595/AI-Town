"""
战斗属性快照（DOC-COMBAT-004 §3/§5，RULE-COMBAT-019）

- CombatantSheet 是 Encounter 内权威；Overworld 属性不被逐回合改写
- Resident 型按 race_base + skill_bonus + equipment_bonus 派生并 clamp 1..200
- Creature 型直接取注册 template；hp_max=0 是上游数据错误，拒绝创建
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..foundation import generate_ulid
from .constants import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    CombatantKind,
    CombatantState,
    Side,
)


class SheetError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


ATTRIBUTE_NAMES = ("strength", "defense", "magic", "resistance", "agility", "focus")


@dataclass
class Stats:
    hp_current: int
    hp_max: int
    mp_current: int
    mp_max: int
    strength: int
    defense: int
    magic: int
    resistance: int
    agility: int
    focus: int

    def clamped(self) -> "Stats":
        for name in ATTRIBUTE_NAMES:
            value = getattr(self, name)
            setattr(self, name, max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, value)))
        if self.hp_max <= 0:
            raise SheetError("combat_sheet_invalid", "hp_max must be positive")
        self.hp_current = max(0, min(self.hp_max, self.hp_current))
        self.mp_current = max(0, min(self.mp_max, self.mp_current))
        return self


@dataclass
class CombatantSheet:
    """DES-COMBAT-004：Encounter 创建时派生的权威快照"""

    combatant_id: str
    entity_ref: str
    kind: CombatantKind
    side: Side
    formation_slot: Optional[str]
    combat_state: CombatantState
    stats: Stats
    status_effect_ids: List[str] = field(default_factory=list)
    equipment_refs: List[str] = field(default_factory=list)
    defending: bool = False  # RULE-COMBAT-023：至下一自身 Turn 前伤害减半
    stabilized: bool = False  # RULE-COMBAT-050：assist 稳定化标记
    reach: bool = False  # RULE-COMBAT-003/016：近战可选后排
    loot_table_id: Optional[str] = None
    sheet_schema_version: int = 1

    def effective_attribute(self, name: str, status_deltas: int = 0) -> int:
        """RULE-COMBAT-030：有效属性 = clamp(基础 + 活跃实例 deltas 之和)"""
        base = getattr(self.stats, name)
        return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, base + status_deltas))


@dataclass(frozen=True)
class CreatureTemplate:
    """注册 Creature 模板（构建期数据）"""

    template_id: str
    stats: Stats
    loot_table_id: Optional[str] = None
    reach: bool = False


def clamp_attribute(value: int) -> int:
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, value))


def derive_combatant_sheet(
    entity_ref: str,
    side: Side,
    *,
    kind: CombatantKind,
    formation_slot: Optional[str],
    creature_template: Optional[CreatureTemplate] = None,
    resident_source: Optional[Dict] = None,
    id_factory: Callable[[], str] = generate_ulid,
) -> CombatantSheet:
    """RULE-COMBAT-019：两种派生路径；数值只从已提交 projection 读取

    resident_source: {hp_current, hp_max, mp_current, mp_max, race_base: {attr: int},
                      skill_bonus: {attr: int}, equipment_bonus: {attr: int},
                      equipment_refs: [...], reach: bool}
    """
    if kind in (CombatantKind.CREATURE, CombatantKind.SUMMON):
        if creature_template is None:
            raise SheetError("combat_sheet_invalid", f"template missing for {entity_ref}")
        stats = Stats(**creature_template.stats.__dict__).clamped()
        return CombatantSheet(
            combatant_id=id_factory(),
            entity_ref=entity_ref,
            kind=kind,
            side=side,
            formation_slot=formation_slot,
            combat_state=CombatantState.ACTIVE,
            stats=stats,
            equipment_refs=[],
            reach=creature_template.reach,
            loot_table_id=creature_template.loot_table_id,
        )
    if resident_source is None:
        raise SheetError("combat_sheet_invalid", f"resident source missing for {entity_ref}")
    attributes = {}
    for name in ATTRIBUTE_NAMES:
        derived = (
            resident_source["race_base"].get(name, 10)
            + resident_source["skill_bonus"].get(name, 0)
            + resident_source["equipment_bonus"].get(name, 0)
        )
        attributes[name] = clamp_attribute(derived)
    stats = Stats(
        hp_current=resident_source["hp_current"],
        hp_max=resident_source["hp_max"],
        mp_current=resident_source["mp_current"],
        mp_max=resident_source["mp_max"],
        **attributes,
    ).clamped()
    return CombatantSheet(
        combatant_id=id_factory(),
        entity_ref=entity_ref,
        kind=kind,
        side=side,
        formation_slot=formation_slot,
        combat_state=CombatantState.ACTIVE,
        stats=stats,
        equipment_refs=list(resident_source.get("equipment_refs", ())),
        reach=bool(resident_source.get("reach", False)),
        loot_table_id=None,  # Resident 永不掉落（RULE-COMBAT-055）
    )

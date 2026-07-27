"""
终结条件与 Outcome Mapping（DOC-COMBAT-009）

- RULE-COMBAT-049：封闭终结条件，首个满足者生效，纯函数
- RULE-COMBAT-050：Resident Outcome 确定性优先序，Stabilized 提升
- RULE-COMBAT-051：永不产生 Resident death/delete
- RULE-COMBAT-052：无法构造合法 captivity 时降级 severely_injured
- RULE-COMBAT-054：战后位置必须通过 MAP 校验，失败整体回滚
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .constants import (
    CREATURE_OUTCOMES,
    RESIDENT_OUTCOMES,
    CombatantKind,
    CombatantState,
    DefeatOutcome,
    EndCondition,
    Side,
)
from .sheets import CombatantSheet


class EndingError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def evaluate_end_conditions(
    party: List[CombatantSheet],
    adversary: List[CombatantSheet],
    forced: Optional[EndCondition] = None,
) -> Optional[Tuple[EndCondition, Optional[Side]]]:
    """RULE-COMBAT-049：纯函数；首个满足者生效；同 tick 全灭 winning_side=None"""
    if forced is not None:
        if forced is EndCondition.ROUND_CAP_FORCED:
            return (forced, None)
        return (forced, None)
    party_alive = [c for c in party if c.combat_state is CombatantState.ACTIVE]
    adversary_alive = [c for c in adversary if c.combat_state is CombatantState.ACTIVE]
    if not party_alive and not adversary_alive:
        # 双方同时全灭：winning_side=null
        return (EndCondition.SIDE_ELIMINATED, None)
    if not party_alive:
        if party and all(c.combat_state is CombatantState.FLED for c in party):
            return (EndCondition.FLEE_COMPLETE, Side.ADVERSARY)
        return (EndCondition.SIDE_ELIMINATED, Side.ADVERSARY)
    if not adversary_alive:
        if adversary and all(c.combat_state is CombatantState.FLED for c in adversary):
            return (EndCondition.FLEE_COMPLETE, Side.PARTY)
        return (EndCondition.SIDE_ELIMINATED, Side.PARTY)
    return None


@dataclass(frozen=True)
class CombatantFinal:
    """DES-COMBAT-009 的终局条目"""

    combatant_id: str
    entity_ref: str
    kind: CombatantKind
    final_combat_state: CombatantState
    defeat_outcome: Optional[DefeatOutcome]
    post_location_id: Optional[str]


def map_defeat_outcomes(
    party: List[CombatantSheet],
    adversary: List[CombatantSheet],
    end_condition: EndCondition,
    winning_side: Optional[Side],
    *,
    captivity_holder_of: Callable[[Side], Optional[Dict]],
    location_validator: Callable[[str], bool],
    safe_point_of: Callable[[str], str],
) -> List[CombatantFinal]:
    """RULE-COMBAT-050：确定性优先序；同输入同输出

    captivity_holder_of(side) -> {holder_id, location_id, review_game_time} | None
    safe_point_of(entity_ref) -> 注册安全点 location_id
    """
    finals: List[CombatantFinal] = []
    for side, members in ((Side.PARTY, party), (Side.ADVERSARY, adversary)):
        opposing = Side.ADVERSARY if side is Side.PARTY else Side.PARTY
        for sheet in members:
            finals.append(
                _map_single(
                    sheet, side, opposing, members, winning_side,
                    captivity_holder_of=captivity_holder_of,
                    location_validator=location_validator,
                    safe_point_of=safe_point_of,
                )
            )
    return finals


def _map_single(
    sheet: CombatantSheet,
    side: Side,
    opposing: Side,
    own_members: List[CombatantSheet],
    winning_side: Optional[Side],
    *,
    captivity_holder_of: Callable[[Side], Optional[Dict]],
    location_validator: Callable[[str], bool],
    safe_point_of: Callable[[str], str],
) -> CombatantFinal:
    if sheet.kind in (CombatantKind.CREATURE, CombatantKind.SUMMON):
        # RULE-COMBAT-053：Creature/summon 终态 died/dissipated/fled
        if sheet.combat_state is CombatantState.DOWN:
            outcome = DefeatOutcome.DISSIPATED if sheet.kind is CombatantKind.SUMMON else DefeatOutcome.DIED
        elif sheet.combat_state is CombatantState.FLED:
            outcome = DefeatOutcome.FLED
        else:
            outcome = None
        return CombatantFinal(
            sheet.combatant_id, sheet.entity_ref, sheet.kind,
            sheet.combat_state, outcome, None,
        )
    # Resident 型：优先序 1..5
    outcome: Optional[DefeatOutcome] = None
    post_location: Optional[str] = None
    if sheet.combat_state is CombatantState.FLED:
        outcome = DefeatOutcome.RETREATED
        post_location = safe_point_of(sheet.entity_ref)
    elif sheet.combat_state is CombatantState.SURRENDERED:
        holder = captivity_holder_of(opposing)
        if holder is not None:
            outcome = DefeatOutcome.CAPTIVE
            post_location = holder["location_id"]
        else:
            outcome = DefeatOutcome.RETREATED  # 无 Valid Holder 就地释放撤离
            post_location = safe_point_of(sheet.entity_ref)
    elif sheet.combat_state is CombatantState.DOWN:
        any_ally_active = any(
            c.combat_state is CombatantState.ACTIVE and c.combatant_id != sheet.combatant_id
            for c in own_members
        )
        if winning_side is side or any_ally_active:
            outcome = DefeatOutcome.UNCONSCIOUS
        else:
            holder = captivity_holder_of(opposing)
            if winning_side is opposing and holder is not None:
                outcome = DefeatOutcome.CAPTIVE
                post_location = holder["location_id"]
            elif sheet.stabilized:
                outcome = DefeatOutcome.UNCONSCIOUS  # Stabilized 提升第 5 支路
            else:
                outcome = DefeatOutcome.SEVERELY_INJURED
    elif sheet.combat_state is CombatantState.ACTIVE:
        # RULE-COMBAT-051：幸存 Resident 保持 active，不进入 defeat
        outcome = None
        post_location = None
    else:
        raise EndingError("COMBAT_OUTCOME_MAPPING_INVALID", sheet.combat_state.value)
    if outcome is not None and outcome not in RESIDENT_OUTCOMES:
        raise EndingError("COMBAT_OUTCOME_MAPPING_INVALID", outcome.value)
    if post_location is not None and not location_validator(post_location):
        # RULE-COMBAT-054：位置不合法 → 整个结果事务回滚
        raise EndingError("combat_post_location_invalid", post_location)
    return CombatantFinal(
        sheet.combatant_id, sheet.entity_ref, sheet.kind,
        sheet.combat_state, outcome, post_location,
    )

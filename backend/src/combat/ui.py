"""
玩家战斗 UI 投影与刷新恢复（DOC-COMBAT-008）

- RULE-COMBAT-044：Action Menu 只渲染服务器派生的 LegalCombatOption[]
- RULE-COMBAT-045：视图只来自已提交事实，无结果预测
- RULE-COMBAT-046：玩家回合无 RealTime 超时
- RULE-COMBAT-047/048：command_id 幂等查询；Refresh Recovery 完全从服务器状态重建
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .constants import CombatantKind, Side, TurnStatus, hp_bucket_of
from .engine import CombatEngine

VIEW_SCHEMA_VERSION = 1

#: Combat Log 尾部条目上限（与 RECENT_TURNS_CAP 对齐）
LOG_TAIL_CAP = 6


def _render_text(event: Dict) -> str:
    """服务器 render 字段：纯文本，只描述已提交结果"""
    payload = event["payload"]
    option_id = payload.get("option_id", "?")
    outcomes = payload.get("target_outcomes", [])
    fragments = []
    for outcome in outcomes:
        delta = outcome.get("hp_delta", 0)
        if delta < 0:
            fragments.append(f"造成 {-delta} 点伤害")
        elif delta > 0:
            fragments.append(f"恢复 {delta} 点生命")
        if not outcome.get("hit", True):
            fragments.append("未命中")
    suffix = "，".join(fragments) if fragments else "无数值效果"
    return f"回合 {payload.get('turn_index')}：{option_id} —— {suffix}。"


def build_encounter_view(
    engine: CombatEngine, encounter_id: str, viewer_side: Side = Side.PARTY
) -> Dict:
    """DES-COMBAT-008：本方完整数值、敌方 hp_bucket 投影、无预测渲染"""
    encounter = engine._require(encounter_id)
    turn_state = engine.get_turn_state(encounter_id)
    party_sheets: List[Dict] = []
    for sheet in encounter.members_of(viewer_side):
        party_sheets.append({
            "combatant_id": sheet.combatant_id,
            "kind": sheet.kind.value,
            "combat_state": sheet.combat_state.value,
            "formation_slot": sheet.formation_slot,
            "hp_current": sheet.stats.hp_current,
            "hp_max": sheet.stats.hp_max,
            "mp_current": sheet.stats.mp_current,
            "mp_max": sheet.stats.mp_max,
            "status_effect_ids": [
                i.definition_id for i in encounter.status_store.instances_of(sheet.combatant_id)
            ],
            "defending": sheet.defending,
        })
    enemy_views: List[Dict] = []
    opposing = Side.ADVERSARY if viewer_side is Side.PARTY else Side.PARTY
    for sheet in encounter.members_of(opposing):
        enemy_views.append({
            "combatant_id": sheet.combatant_id,
            "hp_bucket": hp_bucket_of(sheet.stats.hp_current, sheet.stats.hp_max).value,
            "visible_status_ids": [
                i.definition_id for i in encounter.status_store.instances_of(sheet.combatant_id)
            ],
            "formation_slot": sheet.formation_slot,
            "combat_state": sheet.combat_state.value,
        })
    resolved_events = [
        e for e in engine.events
        if e["encounter_id"] == encounter_id and e["event_kind"] == "CombatActionResolved"
    ]
    combat_log_tail = [
        {"turn_index": e["payload"]["turn_index"], "render_text": _render_text(e)}
        for e in resolved_events[-LOG_TAIL_CAP:]
    ]
    current = encounter.combatants.get(encounter.current_combatant_id or "")
    awaiting_player = (
        encounter.turn_status is TurnStatus.AWAITING_DECISION
        and current is not None
        and current.kind is CombatantKind.PLAYER_RESIDENT
    )
    return {
        "view_schema_version": VIEW_SCHEMA_VERSION,
        "encounter_id": encounter_id,
        "revision": encounter.revision,
        "turn_state": {
            "round_index": turn_state["round_index"],
            "turn_index": turn_state["turn_index"],
            "phase": turn_state["phase"],
            "current_combatant_id": turn_state["current_combatant_id"],
            "turn_status": turn_state["turn_status"],
        },
        "party_sheets": party_sheets,
        "enemy_views": enemy_views,
        "combat_log_tail": combat_log_tail,
        "awaiting_player": awaiting_player,
        "encounter_state": encounter.state.value,
    }


def get_command_outcome(engine: CombatEngine, command_id: str) -> Dict:
    """RULE-COMBAT-047/048：Pending Submission 以原 command_id 查询结局"""
    result = engine._command_results.get(command_id)
    if result is None:
        return {"command_id": command_id, "status": "pending", "result": None}
    return {"command_id": command_id, "status": "committed", "result": result}

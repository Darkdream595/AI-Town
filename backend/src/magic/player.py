"""
玩家施法（DOC-MAGIC-008）

- REQ-MAGIC-015：玩家与 AI 共用七级校验与同一提交管线，无任何操作者特权
- REQ-MAGIC-016：只能施放自己 SpellKnowledge=learned 的注册法术
- RULE-MAGIC-041：镇长模式无 CasterState 不能施法；AdminCommand 不代放法术
- RULE-MAGIC-042：自由文本本身不触发效果，只能解析为选择建议
- RULE-MAGIC-044：每次拒绝返回封闭 reason_code 的中文文案与可行建议
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .casting import CastingEngine, SpellCastCommand, SpellCastCommitted
from .constants import CAST_REASON_CODES


class PlayerCastingError(Exception):
    """玩家施法入口失败；code 复用 DES-MAGIC-005 reason 集或旁路专用码"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-MAGIC-044：封闭 reason_code → (中文文案, 可行建议)；缺失时退回原文
REASON_FEEDBACK_ZH: Dict[str, Tuple[str, str]] = {
    "MAGIC_SPELL_UNKNOWN": ("未注册的法术。", "请从法术面板选择已登记的法术。"),
    "MAGIC_SPELL_NOT_LEARNED": ("尚未学会该法术。", "先通过导师、魔法书或练习学会它。"),
    "MAGIC_CASTER_EXHAUSTED": ("法力枯竭，无法施法。", "休息恢复法力至 30 以上再尝试。"),
    "MAGIC_MANA_INSUFFICIENT": ("法力不足。", "等待法力恢复，或选择消耗更低的法术。"),
    "MAGIC_TARGET_INVALID": ("目标无效。", "重新选择一个有效目标或地面点。"),
    "MAGIC_RANGE_EXCEEDED": ("目标超出射程。", "靠近目标后再施放。"),
    "MAGIC_PREREQUISITE_MISSING": ("前置条件不足。", "提升学派技能等级，或取得所需能力、法术与物品。"),
    "MAGIC_CONSENT_MISSING": ("缺少目标同意或授权。", "先通过对话取得同意，或提供授权事件。"),
    "MAGIC_LEGALITY_PROHIBITED": ("此地禁止施放该法术。", "镇区公共空间禁止攻击性法术，请换个地点。"),
    "MAGIC_ENCOUNTER_RULE_CONFLICT": ("战斗规则冲突。", "只能对交战中的敌人施放攻击性法术。"),
    "stale_revision": ("世界状态已变化。", "请稍后重试。"),
}


def feedback_for(reason_code: Optional[str]) -> Dict:
    """RULE-MAGIC-044：结构化施法反馈；文案缺失退回 reason_code 原文"""
    if reason_code is None:
        return {"reason_code": None, "message_zh": "施法成功。", "suggestion_zh": ""}
    entry = REASON_FEEDBACK_ZH.get(reason_code)
    if entry is None:
        return {"reason_code": reason_code, "message_zh": reason_code, "suggestion_zh": ""}
    return {
        "reason_code": reason_code,
        "message_zh": entry[0],
        "suggestion_zh": entry[1],
    }


def feedback_coverage_complete() -> bool:
    """验收口径：全部封闭 reason_code 都有中文文案映射"""
    return set(REASON_FEEDBACK_ZH) >= set(CAST_REASON_CODES)


@dataclass(frozen=True)
class PlayerCastSpellCommand:
    """DES-MAGIC-008 的玩家命令；client_context 仅遥测，不参与校验"""

    command_id: str
    world_id: str
    expected_revision: int
    actor_resident_id: str
    spell_id: str
    scene_id: str
    game_time: int
    game_day: int
    target_refs: Tuple[str, ...] = ()
    aim_point: Optional[Dict] = None
    authorization_event_ids: Tuple[str, ...] = ()
    caster_position: Dict = field(default_factory=lambda: {"x_wu": 0.0, "y_wu": 0.0})
    client_context: Dict = field(default_factory=dict)

    def to_spell_cast_command(self) -> SpellCastCommand:
        """归一化为 SpellCastCommand；client_context 在此丢弃"""
        return SpellCastCommand(
            command_id=self.command_id,
            world_id=self.world_id,
            expected_revision=self.expected_revision,
            caster_id=self.actor_resident_id,
            spell_id=self.spell_id,
            scene_id=self.scene_id,
            game_time=self.game_time,
            game_day=self.game_day,
            target_refs=self.target_refs,
            aim_point=self.aim_point,
            declared_purpose=self.client_context.get("declared_purpose", "utility"),
            authorization_event_ids=self.authorization_event_ids,
            caster_position=self.caster_position,
        )


class PlayerCastingService:
    """玩家施法入口：归一化后走与 AI 完全相同的 CastingEngine 管线"""

    def __init__(self, engine: CastingEngine) -> None:
        self._engine = engine

    def cast(self, command: PlayerCastSpellCommand) -> SpellCastCommitted:
        """REQ-MAGIC-015：与 AI 同 verdict、同提交、同后果"""
        return self._engine.commit_spell_cast(command.to_spell_cast_command())

    def cast_in_mayor_mode(self, command: PlayerCastSpellCommand) -> SpellCastCommitted:
        """RULE-MAGIC-041：镇长模式无身体、无 CasterState，不能施法"""
        raise PlayerCastingError("MAGIC_CASTER_UNKNOWN", "mayor mode has no caster state")

    def cast_via_admin_command(self, command: PlayerCastSpellCommand) -> SpellCastCommitted:
        """RULE-MAGIC-041：AdminCommand 不得代放法术或注入效果事件"""
        raise PlayerCastingError("magic_admin_bypass_forbidden", command.spell_id)

    def cast_via_freeform_text(self, text: str) -> SpellCastCommitted:
        """RULE-MAGIC-042：自由文本不触发效果，只能产出选择建议"""
        raise PlayerCastingError("magic_freeform_bypass_forbidden", text[:32])

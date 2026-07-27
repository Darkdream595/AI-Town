"""
居民自主施法（DOC-MAGIC-007）

- REQ-MAGIC-013：候选必须 learned、非枯竭、Mana 够、冷却就绪、legality 预判非 prohibited
- REQ-MAGIC-014：模型输出只承载选择，一切结算事实由服务器产生
- RULE-MAGIC-035：候选投影是提示优化不是安全边界，七级校验仍是唯一授权点
- RULE-MAGIC-036：declared_purpose 必须与效果类别一致
- RULE-MAGIC-039：目击输入只源于已提交事件，且不含目标私有状态
- RULE-MAGIC-040：每游戏日 8 次 instant 软预算，超出降权不非法
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from .casting import SpellCastCommitted
from .constants import CANDIDATES_CAP, DAILY_INSTANT_CAST_BUDGET, CastKind
from .effects import EFFECT_PURPOSE_WHITELIST
from .learning import LearningRegistry
from .mana import CasterRegistry, ManaError
from .spells import SpellCatalog, SpellDefinition


class CandidateError(Exception):
    """候选构建/提案语义检查失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: RULE-MAGIC-037：Utility AI fallback 的禁列动作（永不主动施法）
FALLBACK_ACTION_BLACKLIST = frozenset({"cast_spell"})


def fallback_action_allowed(action_kind: str) -> bool:
    """模型不可用时居民只是不施法，不存在降级乱放法术"""
    return action_kind not in FALLBACK_ACTION_BLACKLIST


class DailyCastBudget:
    """RULE-MAGIC-040：per-caster 每游戏日 instant 施法软预算（服务器计数）"""

    def __init__(self, budget: int = DAILY_INSTANT_CAST_BUDGET) -> None:
        self._budget = budget
        self._used: Dict[Tuple[str, int], int] = {}

    @property
    def budget(self) -> int:
        return self._budget

    def used(self, caster_id: str, game_day: int) -> int:
        return self._used.get((caster_id, game_day), 0)

    def remaining(self, caster_id: str, game_day: int) -> int:
        return max(0, self._budget - self.used(caster_id, game_day))

    def over_budget(self, caster_id: str, game_day: int) -> bool:
        return self.used(caster_id, game_day) >= self._budget

    def record(self, committed: SpellCastCommitted, spell: SpellDefinition, game_day: int) -> None:
        """只计 instant 自主施法；ritual 与法器施放不占预算"""
        if spell.cast_kind is not CastKind.INSTANT:
            return
        key = (committed.caster_id, game_day)
        self._used[key] = self._used.get(key, 0) + 1


def check_declared_purpose(spell: SpellDefinition, declared_purpose: str) -> None:
    """RULE-MAGIC-036：用途伪装在校验第 1 级与提案语义层双重拒绝"""
    for binding in spell.effect_bindings:
        allowed = EFFECT_PURPOSE_WHITELIST.get(binding["effect_id"], frozenset())
        if declared_purpose not in allowed:
            raise CandidateError(
                "MAGIC_PURPOSE_MISMATCH",
                f"{binding['effect_id']} cannot declare {declared_purpose}",
            )


def check_targets_visible(target_refs: Tuple[str, ...], visible_entity_ids: Set[str]) -> None:
    """RULE-MAGIC-038：禁止对未感知实体施法（全知瞄准反例）"""
    for target_id in target_refs:
        if target_id not in visible_entity_ids:
            raise CandidateError("magic_target_not_visible", target_id)


def build_candidates(
    caster_id: str,
    game_time: int,
    game_day: int,
    *,
    catalog: SpellCatalog,
    mana_registry: CasterRegistry,
    learning: LearningRegistry,
    legality_preview: Callable[[str, SpellDefinition], str],
    budget: Optional[DailyCastBudget] = None,
) -> Dict:
    """DES-MAGIC-007 候选投影；失败时返回空候选（不阻塞认知流水线）

    legality_preview(caster_id, spell) -> "permitted" / "restricted" / "prohibited"，
    是构建时刻的预判（RULE-MAGIC-028 缓存语义），提交时仍由七级校验重验。
    """
    try:
        caster = mana_registry.get(caster_id)
    except ManaError:
        # 无 CasterState 的角色（如镇长模式）不具备施法能力面
        caster = None
    knowledge = learning.knowledge_of(caster_id)
    entries: List[Dict] = []
    if caster is not None:
        for spell in catalog.all():
            if spell.spell_id not in knowledge.entries:
                continue
            if not learning.is_learned(caster_id, spell.spell_id):
                continue
            if caster.mana_exhausted or caster.mana_current < spell.mana_cost:
                continue
            cooldown_ready = mana_registry.cooldown_ready(caster_id, spell.spell_id, game_time)
            if not cooldown_ready:
                continue
            preview = legality_preview(caster_id, spell)
            if preview == "prohibited":
                # REQ-MAGIC-013：预判 prohibited 不进候选
                continue
            entries.append(
                {
                    "spell_id": spell.spell_id,
                    "school_id": spell.school_id,
                    "mana_cost": spell.mana_cost,
                    "range_wu": spell.range_wu,
                    "target_mode": spell.target_mode.value,
                    "legality_preview": preview,
                    "consent_required": spell.consent_required,
                    "cooldown_ready": cooldown_ready,
                }
            )
    # RULE-MAGIC-040：超预算的 instant 候选降权（排到末尾）但不剔除
    if budget is not None and budget.over_budget(caster_id, game_day):
        entries.sort(key=lambda e: 1 if _is_instant(catalog, e["spell_id"]) else 0)
    entries = entries[:CANDIDATES_CAP]
    context_revision = (caster.state_revision if caster is not None else 0) + knowledge.knowledge_revision
    return {
        "candidate_schema_version": 1,
        "caster_id": caster_id,
        "context_revision": context_revision,
        "candidates": entries,
        "mana_current": caster.mana_current if caster is not None else 0,
        "daily_cast_budget_remaining": (
            budget.remaining(caster_id, game_day) if budget is not None else DAILY_INSTANT_CAST_BUDGET
        ),
    }


def _is_instant(catalog: SpellCatalog, spell_id: str) -> bool:
    return catalog.get(spell_id).cast_kind is CastKind.INSTANT


def make_witness_input(committed: SpellCastCommitted) -> Dict:
    """RULE-MAGIC-039：结构化目击输入；不含 HP 等目标私有状态"""
    return {
        "caster_id": committed.caster_id,
        "spell_id": committed.spell_id,
        "school_id": committed.school_id,
        "legality": committed.legality.value,
        "target_summary": {
            "routed_owners": sorted({r["routed"] for r in committed.effect_results}),
            "effect_kinds": sorted({r["kind"] for r in committed.effect_results}),
        },
    }

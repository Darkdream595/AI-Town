"""
NPC 战术决策与模型降级（DOC-COMBAT-007）

- RULE-COMBAT-038：每 (encounter, turn) 至多一次模型调用；固定 model/prompt
- RULE-COMBAT-039：上下文只含本方完整 sheet、敌方 HP 桶视图、完整合法选项、
  最近 ≤6 Turn 摘要、persona 引用；不含公式与敌方精确数值
- RULE-COMBAT-040：strict decode + 四条件校验；Repair Pass 至多一次
- RULE-COMBAT-041：fallback 触发封闭集，产物与模型产物同一 submit 管线
- RULE-COMBAT-043：每次决策写 Replay Record；重放优先读记录不调模型
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Tuple

from .constants import (
    COMBAT_PROMPT_ID,
    DECISION_DEADLINE_MS,
    MODEL_ID,
    ActionKind,
    CombatantState,
    FallbackReason,
    Side,
    TurnStatus,
    hp_bucket_of,
)
from .engine import CombatEngine, CombatEngineError, LegalCombatOption

DECISION_CONTEXT_SCHEMA_VERSION = 1


class DecisionError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class ModelTimeoutError(Exception):
    pass


class ProviderUnavailableError(Exception):
    pass


class RequestCancelledError(Exception):
    pass


class CombatModelProvider(Protocol):
    """DOC-AI-009 调度层的最小契约；战斗优先级由调度层保证"""

    def complete(self, *, model_id: str, prompt_id: str, context: Dict, deadline_ms: int) -> str:
        """返回模型原始文本；超时/不可用/取消抛对应异常"""
        ...


# ---------------------------------------------------------------------------
# DES-COMBAT-007：CombatDecisionContext
# ---------------------------------------------------------------------------


def build_decision_context(
    engine: CombatEngine,
    encounter_id: str,
    turn_index: int,
    *,
    persona_ref_of,
) -> Dict:
    """RULE-COMBAT-039：知识边界——敌方只有 hp_bucket/可见状态/站位"""
    encounter = engine._require(encounter_id)
    if turn_index != encounter.turn_index or encounter.turn_status is not TurnStatus.AWAITING_DECISION:
        raise DecisionError("COMBAT_TURN_STALE", f"{turn_index}")
    actor = encounter.combatants[encounter.current_combatant_id]
    ally_sheets = []
    for sheet in encounter.members_of(actor.side):
        ally_sheets.append({
            "combatant_id": sheet.combatant_id,
            "kind": sheet.kind.value,
            "combat_state": sheet.combat_state.value,
            "formation_slot": sheet.formation_slot,
            "stats": dict(sheet.stats.__dict__),
            "status_effect_ids": [
                i.definition_id for i in encounter.status_store.instances_of(sheet.combatant_id)
            ],
        })
    enemy_views = []
    for sheet in encounter.members_of(Side.ADVERSARY if actor.side is Side.PARTY else Side.PARTY):
        enemy_views.append({
            "combatant_id": sheet.combatant_id,
            "hp_bucket": hp_bucket_of(sheet.stats.hp_current, sheet.stats.hp_max).value,
            "visible_status_ids": [
                i.definition_id for i in encounter.status_store.instances_of(sheet.combatant_id)
            ],
            "formation_slot": sheet.formation_slot,
            "combat_state": sheet.combat_state.value,
        })
    cached = encounter.options_cache.get(turn_index, ())
    return {
        "context_schema_version": DECISION_CONTEXT_SCHEMA_VERSION,
        "encounter_id": encounter_id,
        "turn_index": turn_index,
        "actor_combatant_id": actor.combatant_id,
        "observed_revision": encounter.revision,
        "ally_sheets": ally_sheets,
        "enemy_views": enemy_views,
        "legal_options": [o.to_record() for o in cached],
        "recent_turns": list(encounter.recent_turns),
        "persona_summary_ref": persona_ref_of(actor.entity_ref),
    }


def context_hash_of(context: Dict) -> str:
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Replay Record（RULE-COMBAT-043）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayRecord:
    encounter_id: str
    turn_index: int
    actor_combatant_id: str
    context_hash: str
    classification: str  # model_decision / fallback_decision
    validated_output: Dict
    fallback_reason: Optional[str]
    model_id: str = MODEL_ID
    prompt_id: str = COMBAT_PROMPT_ID
    repair_used: bool = False


# ---------------------------------------------------------------------------
# 输出校验（RULE-COMBAT-040）
# ---------------------------------------------------------------------------


def _decode_output(raw: str) -> Tuple[Optional[Dict], bool]:
    """返回 (payload, repair_used)；Repair Pass 至多一次且不重新调用模型"""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload, False
    except (json.JSONDecodeError, TypeError):
        pass
    # Repair Pass：截取首个 JSON 对象块再解析一次
    start = raw.find("{") if isinstance(raw, str) else -1
    end = raw.rfind("}") if isinstance(raw, str) else -1
    if 0 <= start < end:
        try:
            payload = json.loads(raw[start : end + 1])
            if isinstance(payload, dict):
                return payload, True
        except json.JSONDecodeError:
            return None, True
    return None, True


def _validate_output(
    payload: Dict,
    *,
    encounter_id: str,
    turn_index: int,
    options: Tuple[LegalCombatOption, ...],
) -> Optional[Dict]:
    """四条件全过返回提交参数；任一违反返回 None；其余文本一律丢弃"""
    if payload.get("encounter_id") != encounter_id:
        return None
    if payload.get("turn_index") != turn_index:
        return None
    option_id = payload.get("action_option_id")
    option = next((o for o in options if o.option_id == option_id), None)
    if option is None:
        return None
    targets = payload.get("target_combatant_ids") or []
    if not isinstance(targets, list) or any(not isinstance(t, str) for t in targets):
        return None
    if option.legal_target_sets:
        if not any(
            s.min_targets <= len(targets) <= s.max_targets
            and all(t in s.combatant_ids for t in targets)
            for s in option.legal_target_sets
        ):
            return None
    elif targets:
        return None
    return {
        "action_option_id": option_id,
        "target_combatant_ids": targets,
        "negotiation_term_id": payload.get("negotiation_term_id"),
    }


# ---------------------------------------------------------------------------
# Tactical Fallback（RULE-COMBAT-041，DOC-AI-011 的确定性选择）
# ---------------------------------------------------------------------------

_OFFENSIVE_KINDS = (
    ActionKind.ATTACK,
    ActionKind.SKILL,
    ActionKind.CAST_SPELL,
    ActionKind.USE_ITEM,
)


def tactical_fallback(options: Tuple[LegalCombatOption, ...]) -> Dict:
    """确定性选择：第一个攻击性 option + 其首个合法目标；否则 defend；集合空是不可能事件"""
    if not options:
        raise DecisionError("fallback_no_legal_candidate", "empty legal options")
    for option in options:
        if option.kind in _OFFENSIVE_KINDS and option.legal_target_sets:
            target_set = option.legal_target_sets[0]
            return {
                "action_option_id": option.option_id,
                "target_combatant_ids": list(target_set.combatant_ids[: target_set.max_targets]),
                "negotiation_term_id": None,
            }
    for option in options:
        if option.kind is ActionKind.DEFEND:
            return {
                "action_option_id": option.option_id,
                "target_combatant_ids": [],
                "negotiation_term_id": None,
            }
    first = options[0]
    targets: List[str] = []
    if first.legal_target_sets:
        target_set = first.legal_target_sets[0]
        targets = list(target_set.combatant_ids[: target_set.max_targets])
    return {
        "action_option_id": first.option_id,
        "target_combatant_ids": targets,
        "negotiation_term_id": None,
    }


# ---------------------------------------------------------------------------
# CombatDecisionService
# ---------------------------------------------------------------------------


@dataclass
class CombatDecisionOutcome:
    classification: str  # model_decision / fallback_decision
    action_option_id: str
    target_combatant_ids: List[str]
    negotiation_term_id: Optional[str]
    submission: Dict
    replay_record: ReplayRecord
    fallback_reason: Optional[str] = None


class CombatDecisionService:
    """每 (encounter, turn) 至多一次模型调用；重放优先读取记录"""

    def __init__(
        self,
        engine: CombatEngine,
        provider: CombatModelProvider,
        *,
        persona_ref_of=lambda entity_ref: None,
        deadline_ms: int = DECISION_DEADLINE_MS,
    ) -> None:
        self._engine = engine
        self._provider = provider
        self._persona_ref_of = persona_ref_of
        self._deadline_ms = deadline_ms
        self._records: Dict[Tuple[str, int], ReplayRecord] = {}

    def replay_records(self) -> List[ReplayRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def record_for(self, encounter_id: str, turn_index: int) -> Optional[ReplayRecord]:
        return self._records.get((encounter_id, turn_index))

    def request_combat_decision(self, encounter_id: str, turn_index: int) -> CombatDecisionOutcome:
        engine = self._engine
        encounter = engine._require(encounter_id)
        if turn_index != encounter.turn_index:
            raise DecisionError("COMBAT_TURN_STALE", str(turn_index))
        actor = encounter.combatants[encounter.current_combatant_id]
        # RULE-COMBAT-043：重放优先读 recorded validated output，不重新调用模型
        existing = self._records.get((encounter_id, turn_index))
        if existing is not None:
            context = build_decision_context(
                engine, encounter_id, turn_index, persona_ref_of=self._persona_ref_of
            )
            if context_hash_of(context) != existing.context_hash:
                raise DecisionError("combat_replay_mismatch", f"{encounter_id}:{turn_index}")
            return self._submit(encounter_id, turn_index, existing)
        context = build_decision_context(
            engine, encounter_id, turn_index, persona_ref_of=self._persona_ref_of
        )
        options = encounter.options_cache.get(turn_index, ())
        context_hash = context_hash_of(context)
        validated: Optional[Dict] = None
        fallback_reason: Optional[FallbackReason] = None
        repair_used = False
        try:
            raw = self._provider.complete(
                model_id=MODEL_ID,
                prompt_id=COMBAT_PROMPT_ID,
                context=context,
                deadline_ms=self._deadline_ms,
            )
        except ModelTimeoutError:
            fallback_reason = FallbackReason.MODEL_TIMEOUT
        except ProviderUnavailableError:
            fallback_reason = FallbackReason.PROVIDER_UNAVAILABLE
        except RequestCancelledError:
            fallback_reason = FallbackReason.CANCELLED
        else:
            payload, repair_used = _decode_output(raw)
            if payload is not None:
                validated = _validate_output(
                    payload, encounter_id=encounter_id, turn_index=turn_index, options=options
                )
            if validated is None:
                fallback_reason = FallbackReason.INVALID_AFTER_REPAIR
        if validated is None:
            validated = tactical_fallback(options)
            classification = "fallback_decision"
        else:
            classification = "model_decision"
        record = ReplayRecord(
            encounter_id=encounter_id,
            turn_index=turn_index,
            actor_combatant_id=actor.combatant_id,
            context_hash=context_hash,
            classification=classification,
            validated_output=validated,
            fallback_reason=fallback_reason.value if fallback_reason else None,
            repair_used=repair_used,
        )
        self._records[(encounter_id, turn_index)] = record
        return self._submit(encounter_id, turn_index, record)

    def _submit(self, encounter_id: str, turn_index: int, record: ReplayRecord) -> CombatDecisionOutcome:
        """RULE-COMBAT-041：模型与 fallback 产物走完全相同的 submit 管线"""
        submission = self._engine.submit_combat_action(
            command_id=f"{encounter_id}:decision:{turn_index}",
            encounter_id=encounter_id,
            turn_index=turn_index,
            action_option_id=record.validated_output["action_option_id"],
            target_combatant_ids=record.validated_output["target_combatant_ids"],
            negotiation_term_id=record.validated_output.get("negotiation_term_id"),
        )
        return CombatDecisionOutcome(
            classification=record.classification,
            action_option_id=record.validated_output["action_option_id"],
            target_combatant_ids=record.validated_output["target_combatant_ids"],
            negotiation_term_id=record.validated_output.get("negotiation_term_id"),
            submission=submission,
            replay_record=record,
            fallback_reason=record.fallback_reason,
        )

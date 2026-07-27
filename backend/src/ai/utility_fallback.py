"""
Utility AI 与 Tactical Utility AI 降级

符合 DOC-AI-011：
- RULE-AI-061：Utility 只从 owner 已给出的合法候选中选择
- RULE-AI-062：同一 state hash/candidate set/policy version 得到同一选择；不调用网络或非 Seed 随机
- RULE-AI-063：Survival 只维持安全/基本 Needs
- RULE-AI-064：Tactical 只选择 legal option
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

#: 候选上限（DOC-AI-011 §9）
MAX_CANDIDATES = 32

#: Survival 候选白名单（DES-AI-011）
SURVIVAL_WHITELIST: frozenset[str] = frozenset(
    {
        "seek_safety",
        "obtain_food",
        "rest_at_authorized_place",
        "seek_healing",
        "leave_hazard",
        "wait_safely",
        "observe_blocker",
    }
)

#: fallback 禁止主动发起的 action（DES-AI-011）
FALLBACK_FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "buy",
        "sell",
        "give_item",
        "craft",
        "gather",
        "explore",
        "cast_spell",
        "start_encounter",
        "build",
        "repair",
    }
)

#: 白名单 candidate 允许映射的 action
_CANDIDATE_ALLOWED_ACTIONS: dict[str, frozenset[str]] = {
    "seek_safety": frozenset({"move_to"}),
    "obtain_food": frozenset({"move_to", "eat"}),
    "rest_at_authorized_place": frozenset({"move_to", "rest"}),
    "seek_healing": frozenset({"move_to", "talk", "use_object"}),
    "leave_hazard": frozenset({"move_to"}),
    "wait_safely": frozenset({"wait"}),
    "observe_blocker": frozenset({"observe"}),
}


@dataclass(frozen=True)
class UtilityInputs:
    """Utility 评分输入（owner projection 的有界整数，q1000 表示千分比）"""

    safety_urgency_q1000: int
    health_urgency_q1000: int
    hunger_urgency_q1000: int
    fatigue_urgency_q1000: int
    completion_likelihood_q1000: int
    path_cost_bucket: int
    recent_repeat_count: int


@dataclass(frozen=True)
class SurvivalCandidate:
    """owner 提供的合法候选"""

    candidate_id: str  # SURVIVAL_WHITELIST 之一
    action_id: str
    target_id: str
    utility: UtilityInputs


def compute_utility_score(utility: UtilityInputs) -> int:
    """DES-AI-011 评分公式（纯整数，确定性）"""
    return (
        utility.safety_urgency_q1000 * 1000
        + utility.health_urgency_q1000 * 800
        + utility.hunger_urgency_q1000 * 600
        + utility.fatigue_urgency_q1000 * 500
        + utility.completion_likelihood_q1000 * 200
        - utility.path_cost_bucket * 50
        - utility.recent_repeat_count * 120
    )


class FallbackNoLegalCandidateError(Exception):
    """fallback_no_legal_candidate（DOC-AI-011 §8）"""


def filter_legal_survival_candidates(candidates: list[SurvivalCandidate]) -> list[SurvivalCandidate]:
    """只保留白名单 candidate 且 action 合法（RULE-AI-063）"""
    legal: list[SurvivalCandidate] = []
    for candidate in candidates[:MAX_CANDIDATES]:
        if candidate.candidate_id not in SURVIVAL_WHITELIST:
            continue
        if candidate.action_id in FALLBACK_FORBIDDEN_ACTIONS:
            continue
        allowed_actions = _CANDIDATE_ALLOWED_ACTIONS.get(candidate.candidate_id)
        if allowed_actions is None or candidate.action_id not in allowed_actions:
            continue
        legal.append(candidate)
    return legal


def select_survival_candidate(candidates: list[SurvivalCandidate]) -> SurvivalCandidate:
    """
    确定性选择：按较高 score、较小 action ID、较小 target ID 决胜（DES-AI-011 / TEST-AI-042）
    """
    legal = filter_legal_survival_candidates(candidates)
    if not legal:
        raise FallbackNoLegalCandidateError("fallback_no_legal_candidate")

    def sort_key(candidate: SurvivalCandidate) -> tuple:
        return (
            -compute_utility_score(candidate.utility),
            candidate.action_id,
            candidate.target_id,
        )

    return min(legal, key=sort_key)


@dataclass(frozen=True)
class LegalCombatOption:
    """COMBAT 提供的合法行动（DOC-COMBAT-006）"""

    option_id: str
    action_id: str  # attack/defend/cast/item/flee/pass/surrender 等（owner 注册）
    target_combatant_id: Optional[str]
    expected_rule_utility_q1000: int
    resource_cost_q1000: int  # 资源保守评分（越大越耗）
    defeats_formal_resident_risk_q1000: int  # 正式居民被击败风险
    is_defense_or_rescue: bool


def select_tactical_option(options: list[LegalCombatOption]) -> LegalCombatOption:
    """
    Tactical Utility：只从 legal set 中确定性选一（RULE-AI-064 / TEST-AI-043）

    评分顺序：避免正式居民被击败 > 明确防御/救援 > 预期规则效用 > 资源保守 > 稳定 option ID。
    无合法主动项时选择 owner 注册 defend/pass/surrender 中可用者。
    """
    if not options:
        raise FallbackNoLegalCandidateError("combat legal set 为空是 COMBAT invariant failure")

    def sort_key(option: LegalCombatOption) -> tuple:
        return (
            option.defeats_formal_resident_risk_q1000,  # 风险越小越优先
            0 if option.is_defense_or_rescue else 1,
            -option.expected_rule_utility_q1000,
            option.resource_cost_q1000,
            option.option_id,
        )

    active_options = [o for o in options if o.action_id not in ("pass", "surrender")]
    if active_options:
        return min(active_options, key=sort_key)
    return min(options, key=sort_key)


@dataclass(frozen=True)
class FallbackEpisode:
    """Fallback Episode 审计（RULE-AI-066）"""

    episode_id: str
    resident_id: str
    trigger: str
    policy_version: int
    candidate_ids: tuple[str, ...]
    chosen_id: Optional[str]
    committed_outcome: Optional[str]
    recovery_condition: str

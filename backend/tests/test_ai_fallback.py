"""
测试 Utility AI 与 Tactical Utility AI 降级

覆盖 TEST-AI-041/042/043/044（DOC-AI-011 §11）
"""

import pytest

from src.ai import (
    FALLBACK_FORBIDDEN_ACTIONS,
    SURVIVAL_WHITELIST,
    FallbackNoLegalCandidateError,
    LegalCombatOption,
    SurvivalCandidate,
    UtilityInputs,
    compute_utility_score,
    select_survival_candidate,
    select_tactical_option,
)


def _utility(**overrides) -> UtilityInputs:
    defaults = dict(
        safety_urgency_q1000=0,
        health_urgency_q1000=0,
        hunger_urgency_q1000=0,
        fatigue_urgency_q1000=0,
        completion_likelihood_q1000=500,
        path_cost_bucket=0,
        recent_repeat_count=0,
    )
    defaults.update(overrides)
    return UtilityInputs(**defaults)


def _candidate(
    candidate_id: str, action_id: str, target_id: str = "target.a", utility: UtilityInputs | None = None
) -> SurvivalCandidate:
    return SurvivalCandidate(
        candidate_id=candidate_id,
        action_id=action_id,
        target_id=target_id,
        utility=utility or _utility(),
    )


class TestSurvivalWhitelist:
    """TEST-AI-041：survival candidate whitelist/forbidden set"""

    def test_whitelist_content(self):
        assert "seek_safety" in SURVIVAL_WHITELIST
        assert "wait_safely" in SURVIVAL_WHITELIST
        assert len(SURVIVAL_WHITELIST) == 7

    def test_forbidden_actions_content(self):
        assert "buy" in FALLBACK_FORBIDDEN_ACTIONS
        assert "cast_spell" in FALLBACK_FORBIDDEN_ACTIONS
        assert "start_encounter" in FALLBACK_FORBIDDEN_ACTIONS

    def test_forbidden_action_filtered(self):
        candidates = [
            _candidate("seek_safety", "move_to"),
            SurvivalCandidate(
                candidate_id="seek_safety",
                action_id="cast_spell",  # 该 candidate 不允许 cast_spell
                target_id="t1",
                utility=_utility(safety_urgency_q1000=1000),
            ),
        ]
        chosen = select_survival_candidate(candidates)
        assert chosen.action_id == "move_to"

    def test_non_whitelist_candidate_filtered(self):
        candidates = [_candidate("rob_shop", "move_to")]
        with pytest.raises(FallbackNoLegalCandidateError):
            select_survival_candidate(candidates)

    def test_empty_candidates(self):
        with pytest.raises(FallbackNoLegalCandidateError):
            select_survival_candidate([])


class TestDeterministicScoring:
    """TEST-AI-042：deterministic score/tie-break"""

    def test_score_formula(self):
        utility = UtilityInputs(
            safety_urgency_q1000=1,
            health_urgency_q1000=1,
            hunger_urgency_q1000=1,
            fatigue_urgency_q1000=1,
            completion_likelihood_q1000=1,
            path_cost_bucket=1,
            recent_repeat_count=1,
        )
        assert compute_utility_score(utility) == (
            1000 + 800 + 600 + 500 + 200 - 50 - 120
        )

    def test_higher_score_wins(self):
        low = _candidate("wait_safely", "wait", utility=_utility(safety_urgency_q1000=0))
        high = _candidate("seek_safety", "move_to", utility=_utility(safety_urgency_q1000=900))
        assert select_survival_candidate([low, high]) is high

    def test_tiebreak_by_action_id_then_target_id(self):
        candidate_b = _candidate("seek_safety", "move_to", target_id="target.b")
        candidate_a = _candidate("seek_safety", "move_to", target_id="target.a")
        assert select_survival_candidate([candidate_b, candidate_a]) is candidate_a

    def test_byte_equivalent_selection_100_times(self):
        candidates = [
            _candidate("seek_safety", "move_to", "t.3", _utility(safety_urgency_q1000=100)),
            _candidate("obtain_food", "eat", "t.1", _utility(hunger_urgency_q1000=200)),
            _candidate("wait_safely", "wait", "t.2", _utility()),
        ]
        first_choice = select_survival_candidate(candidates)
        for _ in range(100):
            assert select_survival_candidate(candidates) == first_choice


class TestTacticalLegalSubset:
    """TEST-AI-043：Tactical legal-option subset"""

    def _options(self) -> list[LegalCombatOption]:
        return [
            LegalCombatOption(
                option_id="opt.attack",
                action_id="attack",
                target_combatant_id="enemy.1",
                expected_rule_utility_q1000=700,
                resource_cost_q1000=100,
                defeats_formal_resident_risk_q1000=300,
                is_defense_or_rescue=False,
            ),
            LegalCombatOption(
                option_id="opt.defend",
                action_id="defend",
                target_combatant_id=None,
                expected_rule_utility_q1000=400,
                resource_cost_q1000=0,
                defeats_formal_resident_risk_q1000=50,
                is_defense_or_rescue=True,
            ),
        ]

    def test_prefers_lower_defeat_risk(self):
        chosen = select_tactical_option(self._options())
        assert chosen.option_id == "opt.defend"

    def test_deterministic(self):
        options = self._options()
        first = select_tactical_option(options)
        for _ in range(50):
            assert select_tactical_option(options) == first

    def test_empty_legal_set_raises(self):
        # 战斗 legal set 为空是 COMBAT invariant failure，不能伪造 attack
        with pytest.raises(FallbackNoLegalCandidateError):
            select_tactical_option([])

    def test_pass_surrender_only_when_no_active(self):
        passive = LegalCombatOption(
            option_id="opt.pass",
            action_id="pass",
            target_combatant_id=None,
            expected_rule_utility_q1000=0,
            resource_cost_q1000=0,
            defeats_formal_resident_risk_q1000=900,
            is_defense_or_rescue=False,
        )
        options = self._options() + [passive]
        chosen = select_tactical_option(options)
        assert chosen.action_id != "pass"
        # 只有被动项时选择 defend/pass/surrender 中可用者
        assert select_tactical_option([passive]) is passive

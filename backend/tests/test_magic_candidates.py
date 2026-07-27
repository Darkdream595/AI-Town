"""
TEST-MAGIC-015..016：居民自主施法（DOC-MAGIC-007）

- TEST-MAGIC-015：候选过滤矩阵、幻觉提案兜底、purpose/可见性反例
- TEST-MAGIC-016：目击输入结构与日施法预算软约束
"""

import pytest

from src.magic import (
    CandidateError,
    DailyCastBudget,
    VerdictClassification,
    build_candidates,
    check_declared_purpose,
    check_targets_visible,
    fallback_action_allowed,
    make_witness_input,
)

from magic_helpers import command, drain_mana, learn, make_engine


def _permitted_preview(_caster_id, _spell):
    return "permitted"


def test_magic_015_candidate_filter_matrix():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight", "spell.restoration.minor_mend",
          "spell.spirit.hex_of_weariness", max_rating=0)
    projection = build_candidates(
        "r.a", 0, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    assert projection["candidate_schema_version"] == 1
    spell_ids = {c["spell_id"] for c in projection["candidates"]}
    # 只有已学法术进入候选（REQ-MAGIC-013）；未学的 9 条不出现
    assert spell_ids == {
        "spell.arcane.glowlight", "spell.restoration.minor_mend", "spell.spirit.hex_of_weariness",
    }
    for entry in projection["candidates"]:
        assert entry["cooldown_ready"]
        assert entry["legality_preview"] == "permitted"
    assert projection["mana_current"] == 60
    assert projection["daily_cast_budget_remaining"] == 8
    # Mana 不足过滤：降到 20 后 hex（35）被剔除
    drain_mana(env, "r.a", 40, "evt.drain.a")
    projection2 = build_candidates(
        "r.a", 0, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    spell_ids2 = {c["spell_id"] for c in projection2["candidates"]}
    assert "spell.spirit.hex_of_weariness" not in spell_ids2
    assert "spell.arcane.glowlight" in spell_ids2
    # 枯竭过滤：再降到枯竭，候选清空
    drain_mana(env, "r.a", 15, "evt.drain.b")
    assert env.mana.get("r.a").mana_exhausted
    projection3 = build_candidates(
        "r.a", 0, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    assert projection3["candidates"] == []


def test_magic_015_cooldown_and_prohibited_preview_filtered():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight", "spell.elemental.kindle_flame")
    env.mana.set_cooldown("r.a", "spell.arcane.glowlight", 100)
    projection = build_candidates(
        "r.a", 50, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    assert {c["spell_id"] for c in projection["candidates"]} == {"spell.elemental.kindle_flame"}
    # 冷却恢复后重新出现
    projection_ready = build_candidates(
        "r.a", 100, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    assert "spell.arcane.glowlight" in {c["spell_id"] for c in projection_ready["candidates"]}
    # 预判 prohibited 的法术不进候选
    projection_prohibited = build_candidates(
        "r.a", 100, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=lambda _c, s: "prohibited" if s.spell_id == "spell.elemental.kindle_flame" else "permitted",
        budget=env.budget,
    )
    assert {c["spell_id"] for c in projection_prohibited["candidates"]} == {"spell.arcane.glowlight"}


def test_magic_015_purpose_and_visibility_counterexamples():
    env = make_engine()
    spell = env.catalog.get("spell.restoration.minor_mend")
    # RULE-MAGIC-036：治疗类效果只能声明 healing
    check_declared_purpose(spell, "healing")
    with pytest.raises(CandidateError) as exc:
        check_declared_purpose(spell, "combat")
    assert exc.value.code == "MAGIC_PURPOSE_MISMATCH"
    hex_spell = env.catalog.get("spell.spirit.hex_of_weariness")
    with pytest.raises(CandidateError):
        check_declared_purpose(hex_spell, "healing")
    # RULE-MAGIC-038：对未感知实体施法在语义层拒绝
    check_targets_visible(("r.x",), {"r.x", "r.y"})
    with pytest.raises(CandidateError) as exc2:
        check_targets_visible(("r.x",), {"r.y"})
    assert exc2.value.code == "magic_target_not_visible"


def test_magic_015_hallucinated_proposal_rejected_by_pipeline():
    # RULE-MAGIC-035：候选是提示优化不是安全边界；幻觉提案由七级校验兜底
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight")
    projection = build_candidates(
        "r.a", 0, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    assert "spell.restoration.minor_mend" not in {
        c["spell_id"] for c in projection["candidates"]
    }
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.a",),
    ))
    assert verdict.classification is VerdictClassification.FORBIDDEN
    assert verdict.reason_code == "MAGIC_SPELL_NOT_LEARNED"
    assert env.engine.revision == 0
    # RULE-MAGIC-037：fallback 永不主动施法
    assert not fallback_action_allowed("cast_spell")
    assert fallback_action_allowed("move_to")


def test_magic_016_witness_input_from_committed_only():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.restoration.minor_mend")
    env.resident_port.set_hp("r.b", 40, 100)
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
    ))
    witness = make_witness_input(committed)
    # RULE-MAGIC-039：恰好五个字段的结构化目击输入
    assert set(witness) == {"caster_id", "spell_id", "school_id", "legality", "target_summary"}
    assert witness["caster_id"] == "r.a"
    assert witness["spell_id"] == "spell.restoration.minor_mend"
    assert witness["school_id"] == "school.restoration"
    assert witness["legality"] == "permitted"
    # 不导出目标私有状态（HP 数值不出现在目击输入中）
    assert "hp_delta" not in str(witness["target_summary"])
    assert "40" not in str(witness["target_summary"])
    assert witness["target_summary"]["routed_owners"] == ["RESIDENT"]


def test_magic_016_daily_budget_soft_constraint():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight", "spell.warding.ley_anchor")
    spell = env.catalog.get("spell.arcane.glowlight")
    # 同游戏日提交 9 次 instant（预算 8）
    for index in range(9):
        committed = env.engine.commit_spell_cast(command(
            env, "r.a", "spell.arcane.glowlight",
            command_id=f"cmd.glow.{index}", game_time=index,
        ))
        env.budget.record(committed, spell, 0)
    assert env.budget.used("r.a", 0) == 9
    assert env.budget.remaining("r.a", 0) == 0
    assert env.budget.over_budget("r.a", 0)
    # RULE-MAGIC-040：超预算不非法，候选投影仅降权（ritual 排在 instant 前）
    projection = build_candidates(
        "r.a", 100, 0,
        catalog=env.catalog, mana_registry=env.mana, learning=env.learning,
        legality_preview=_permitted_preview, budget=env.budget,
    )
    kinds = [c["spell_id"] for c in projection["candidates"]]
    assert set(kinds) == {"spell.arcane.glowlight", "spell.warding.ley_anchor"}
    assert kinds[0] == "spell.warding.ley_anchor"  # 非 instant 优先
    # ritual 提交不占预算
    assert env.budget.used("r.a", 1) == 0

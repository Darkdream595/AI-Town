"""
TEST-MAGIC-013..014：魔法学习与成长（DOC-MAGIC-006）

- TEST-MAGIC-013：三类来源端到端、来源白名单、状态机无降级
- TEST-MAGIC-014：中断/恢复、XP 幂等、知识上限、Admin 来源反例
"""

import pytest

from src.magic import (
    KnowledgeEntry,
    KnowledgeState,
    LearningError,
    LearningRegistry,
    SourceKind,
    build_default_schools,
    build_default_spell_catalog,
    study_work_units_for,
)

from magic_helpers import make_engine


def test_magic_013_three_sources_end_to_end():
    env = make_engine()
    env.mana.register_caster("r.a", 0)
    # 导师来源（restoration 允许 teacher）
    entry = env.learning.begin_study(
        "cmd.study.1", "r.a", "spell.restoration.minor_mend",
        SourceKind.TEACHER, "r.teacher", True,
    )
    assert entry.state is KnowledgeState.STUDYING
    assert entry.required_work_units == 4  # mana 12 → max(4, 2)
    for _ in range(4):
        entry = env.learning.complete_study_checkpoint("r.a", "spell.restoration.minor_mend", 100)
    assert entry.state is KnowledgeState.LEARNED
    assert entry.learned_at_game_time == 100
    assert env.learning.is_learned("r.a", "spell.restoration.minor_mend")
    # 魔法书来源（arcane 允许 spellbook）
    env.learning.begin_study(
        "cmd.study.2", "r.a", "spell.arcane.detect_magic",
        SourceKind.SPELLBOOK, "item.tome.1", True,
    )
    for _ in range(4):
        env.learning.complete_study_checkpoint("r.a", "spell.arcane.detect_magic", 200)
    assert env.learning.is_learned("r.a", "spell.arcane.detect_magic")
    # 练习来源（arcane 允许 practice）
    env.learning.begin_study(
        "cmd.study.3", "r.a", "spell.arcane.glowlight",
        SourceKind.PRACTICE, "practice.self", True,
    )
    for _ in range(4):
        env.learning.complete_study_checkpoint("r.a", "spell.arcane.glowlight", 300)
    assert env.learning.is_learned("r.a", "spell.arcane.glowlight")
    # RULE-MAGIC-029：learned 无降级路径，重复学习拒绝
    with pytest.raises(LearningError) as exc:
        env.learning.begin_study(
            "cmd.study.4", "r.a", "spell.arcane.glowlight",
            SourceKind.PRACTICE, "practice.self", True,
        )
    assert exc.value.code == "MAGIC_ALREADY_LEARNED"


def test_magic_013_source_kind_whitelist_per_school():
    env = make_engine()
    env.mana.register_caster("r.a", 0)
    # warding 不允许 practice 来源
    with pytest.raises(LearningError) as exc:
        env.learning.begin_study(
            "cmd.study.w", "r.a", "spell.warding.reinforce_structure",
            SourceKind.PRACTICE, "practice.self", True,
        )
    assert exc.value.code == "MAGIC_STUDY_SOURCE_UNAVAILABLE"
    # spirit 只允许 teacher
    with pytest.raises(LearningError) as exc2:
        env.learning.begin_study(
            "cmd.study.s", "r.a", "spell.spirit.soothe_spirit",
            SourceKind.SPELLBOOK, "item.tome.x", True,
        )
    assert exc2.value.code == "MAGIC_STUDY_SOURCE_UNAVAILABLE"
    # 来源当前不可用（魔法书不在手边）
    with pytest.raises(LearningError) as exc3:
        env.learning.begin_study(
            "cmd.study.u", "r.a", "spell.arcane.detect_magic",
            SourceKind.SPELLBOOK, "item.tome.far", False,
        )
    assert exc3.value.code == "MAGIC_STUDY_SOURCE_UNAVAILABLE"


def test_magic_013_prerequisite_and_session_conflict():
    ratings = {("r.a", "school.warding"): 30}
    env = make_engine(ratings=ratings)
    env.mana.register_caster("r.a", 0)
    # purify_ground 要求 rating 40
    with pytest.raises(LearningError) as exc:
        env.learning.begin_study(
            "cmd.study.p", "r.a", "spell.warding.purify_ground",
            SourceKind.TEACHER, "r.teacher", True,
        )
    assert exc.value.code == "MAGIC_STUDY_PREREQUISITE_MISSING"
    # 学习会话排他：同学派同法术重复 begin 冲突
    env2 = make_engine()
    env2.mana.register_caster("r.b", 0)
    env2.learning.begin_study(
        "cmd.study.c1", "r.b", "spell.arcane.glowlight",
        SourceKind.PRACTICE, "practice.self", True,
    )
    with pytest.raises(LearningError) as exc2:
        env2.learning.begin_study(
            "cmd.study.c2", "r.b", "spell.arcane.glowlight",
            SourceKind.PRACTICE, "practice.self", True,
        )
    assert exc2.value.code == "magic_study_session_conflict"
    # begin 幂等：同 command_id 重发返回同一会话
    again = env2.learning.begin_study(
        "cmd.study.c1", "r.b", "spell.arcane.glowlight",
        SourceKind.PRACTICE, "practice.self", True,
    )
    assert again.study_long_action_id == env2.learning.knowledge_of("r.b").entries[
        "spell.arcane.glowlight"
    ].study_long_action_id


def test_magic_014_interruption_and_resume():
    env = make_engine()
    env.mana.register_caster("r.a", 0)
    env.learning.begin_study(
        "cmd.study.i", "r.a", "spell.arcane.detect_magic",
        SourceKind.SPELLBOOK, "item.tome.1", True,
    )
    env.learning.complete_study_checkpoint("r.a", "spell.arcane.detect_magic", 10)
    env.learning.complete_study_checkpoint("r.a", "spell.arcane.detect_magic", 20)
    # RULE-MAGIC-031：检查点重验来源失效 → 会话中断、进度保留
    with pytest.raises(LearningError) as exc:
        env.learning.complete_study_checkpoint(
            "r.a", "spell.arcane.detect_magic", 30, source_available=False
        )
    assert exc.value.code == "MAGIC_STUDY_SOURCE_UNAVAILABLE"
    entry = env.learning.knowledge_of("r.a").entries["spell.arcane.detect_magic"]
    assert entry.state is KnowledgeState.STUDYING
    assert entry.study_progress == 2
    assert not entry.source_available
    # 重新取得来源后 resume，进度不丢
    env.learning.resume_study("r.a", "spell.arcane.detect_magic", source_available=True)
    env.learning.complete_study_checkpoint("r.a", "spell.arcane.detect_magic", 40)
    env.learning.complete_study_checkpoint("r.a", "spell.arcane.detect_magic", 50)
    assert env.learning.is_learned("r.a", "spell.arcane.detect_magic")
    assert entry.learned_at_game_time == 50


def test_magic_014_xp_idempotent_per_event():
    catalog = build_default_spell_catalog()
    schools = build_default_schools()
    xp_log = []
    learning = LearningRegistry(
        catalog,
        lambda _c, _s: 100,
        lambda school_id: schools.get(school_id).learning_source_kinds,
        xp_sink=lambda caster, school, event: xp_log.append((caster, school, event)),
    )
    # RULE-MAGIC-033：同 source_event_id 的 XP 只授一次
    learning.grant_cast_xp("r.a", "school.arcane", "evt.cast.1")
    learning.grant_cast_xp("r.a", "school.arcane", "evt.cast.1")
    learning.grant_cast_xp("r.a", "school.arcane", "evt.cast.2")
    assert len(xp_log) == 2
    assert learning.xp_event_count == 2


def test_magic_014_knowledge_cap_and_admin_counterexample():
    env = make_engine(ratings={("r.a", "school.warding"): 30})
    env.mana.register_caster("r.a", 0)
    knowledge = env.learning.knowledge_of("r.a")
    # 填满 64 条知识上限
    for index in range(64):
        knowledge.entries[f"spell.fixture.{index}"] = KnowledgeEntry(
            spell_id=f"spell.fixture.{index}",
            state=KnowledgeState.LEARNED,
            source_kind=SourceKind.INITIALIZATION,
            source_ref="evt.init",
        )
    with pytest.raises(LearningError) as exc:
        env.learning.begin_study(
            "cmd.study.cap", "r.a", "spell.arcane.glowlight",
            SourceKind.PRACTICE, "practice.self", True,
        )
    assert exc.value.code == "magic_knowledge_cap"
    # Admin 反例：学习来源枚举封闭，不存在 admin 通道
    with pytest.raises(ValueError):
        SourceKind("admin")
    # 初始化授予也受门槛校验（模板错误在构建期暴露）
    with pytest.raises(LearningError) as exc2:
        env.learning.grant_initial("r.a", ["spell.warding.purify_ground"], "evt.init", 0)
    assert exc2.value.code == "MAGIC_STUDY_PREREQUISITE_MISSING"


def test_magic_014_work_units_table():
    catalog = build_default_spell_catalog()
    # RULE-MAGIC-031：max(4, mana//10 × 2)
    assert study_work_units_for(catalog.get("spell.arcane.glowlight")) == 4
    assert study_work_units_for(catalog.get("spell.restoration.cleanse_ailment")) == 4
    assert study_work_units_for(catalog.get("spell.warding.purify_ground")) == 6
    assert study_work_units_for(catalog.get("spell.warding.ley_anchor")) == 8

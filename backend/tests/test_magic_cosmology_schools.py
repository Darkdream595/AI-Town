"""
TEST-MAGIC-001..004：世界观与学派（DOC-MAGIC-001/002）

- TEST-MAGIC-001：Cosmology 三条注册、机制挂钩封闭、Canon 冲突拒绝
- TEST-MAGIC-002：六学派固定注册、未知学派 fail closed
- TEST-MAGIC-003：归属冲突仲裁顺序固定
- TEST-MAGIC-004：传送命名禁令（静态层）
"""

import pytest

from src.magic import (
    CosmologyEntry,
    CosmologyError,
    EffectCategory,
    SchoolError,
    arbitrate_school,
    assert_no_teleport_semantics,
    build_default_cosmology,
    build_default_schools,
    lint_school_scope,
)


def test_magic_001_cosmology_registry_closed():
    registry = build_default_cosmology()
    assert len(registry._entries) == 3
    tide = registry.get("magic.cosmology.starweave_tide")
    # REQ-MAGIC-001：唯一环境魔力来源携带恰好两个机制挂钩
    assert set(tide.mechanical_hooks) == {"starweave_tide_modifier", "ley_anchor_presence"}
    # 信仰变体只是叙事，不产生机制
    assert registry.get("magic.cosmology.silver_ash_legacy").mechanical_hooks == ()
    assert registry.all_hooks() == frozenset({"starweave_tide_modifier", "ley_anchor_presence"})


def test_magic_001_second_mechanism_source_rejected():
    registry = build_default_cosmology()
    with pytest.raises(CosmologyError) as exc:
        registry.register(CosmologyEntry(
            cosmology_id="magic.cosmology.blood_moon",
            public_summary="血月赋予另一套魔力来源。",
            belief_variants=(),
            mechanical_hooks=("blood_moon_modifier",),
        ))
    assert exc.value.code == "WORLD_CANON_CONFLICT"
    with pytest.raises(CosmologyError):
        registry.get("magic.cosmology.blood_moon")


def test_magic_001_duplicate_registration_rejected():
    registry = build_default_cosmology()
    with pytest.raises(CosmologyError) as exc:
        registry.register(CosmologyEntry(
            cosmology_id="magic.cosmology.starweave_tide",
            public_summary="重复注册。",
            belief_variants=(),
            mechanical_hooks=(),
        ))
    assert exc.value.code == "WORLD_CANON_CONFLICT"


def test_magic_002_six_schools_fixed():
    schools = build_default_schools()
    assert len(schools) == 6
    names = {s.school_id: s.display_name_zh for s in schools._schools.values()}
    assert names == {
        "school.elemental": "元素",
        "school.restoration": "疗愈",
        "school.warding": "护壁",
        "school.illusion": "幻术",
        "school.spirit": "通灵",
        "school.arcane": "奥术",
    }
    for school in schools._schools.values():
        assert school.vfx_family.startswith("vfx.")
        assert school.default_legal_baseline in ("permitted", "restricted", "prohibited")
        assert school.learning_source_kinds


def test_magic_002_unknown_school_fail_closed():
    schools = build_default_schools()
    with pytest.raises(SchoolError) as exc:
        schools.get("school.blood")
    assert exc.value.code == "FORBIDDEN"
    # 重复注册同 ID 视为注册表冲突
    with pytest.raises(SchoolError) as exc2:
        schools.register(schools.get("school.arcane"))
    assert exc2.value.code == "magic_school_registry_conflict"


def test_magic_003_arbitration_order_fixed():
    # RULE-MAGIC-007：效果类别决定学派，声明不改变归属
    assert arbitrate_school(EffectCategory.HP_CHANGE, "school.elemental") == "school.restoration"
    assert arbitrate_school(EffectCategory.FIRE_OR_MATTER, "school.warding") == "school.elemental"
    assert arbitrate_school(EffectCategory.PERCEPTION, "school.arcane") == "school.illusion"
    assert arbitrate_school(EffectCategory.OTHER, "school.spirit") == "school.spirit"


def test_magic_003_lint_school_scope():
    schools = build_default_schools()
    # 疗愈学派声明 hp_change 类别：一致
    lint_school_scope(schools.get("school.restoration"), EffectCategory.HP_CHANGE)
    # 元素学派声明 hp_change：构建期 lint 拒绝
    with pytest.raises(SchoolError) as exc:
        lint_school_scope(schools.get("school.elemental"), EffectCategory.HP_CHANGE)
    assert exc.value.code == "magic_school_scope_mismatch"


def test_magic_004_teleport_naming_rejected():
    assert_no_teleport_semantics("spell.arcane.glowlight", "magic.effect.conjure_light")
    for forbidden in (
        "spell.arcane.teleport",
        "spell.arcane.Teleport_home",
        "magic.effect.blink_step",
        "magic.effect.TELEPORT",
    ):
        with pytest.raises(SchoolError) as exc:
            assert_no_teleport_semantics(forbidden)
        assert exc.value.code == "magic_teleport_forbidden"

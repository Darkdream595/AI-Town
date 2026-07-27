"""
TEST-MAGIC-007..009：法术数据模型（DOC-MAGIC-004）

- TEST-MAGIC-007：strict decoder 契约（缺字段/多字段/坏枚举/数值越界）
- TEST-MAGIC-008：首版 Catalog 恰好 12 条封闭审计
- TEST-MAGIC-009：六种 target_mode 组合矩阵与 legal_override 收紧方向
"""

import pytest

from src.magic import (
    EFFECT_IDS,
    CastKind,
    LegalOverride,
    SpellError,
    TargetMode,
    build_default_spell_catalog,
    decode_spell_definition,
    study_work_units_for,
    validate_target_arguments,
)


def _record(**overrides):
    record = {
        "schema_version": 1,
        "spell_id": "spell.arcane.fixture",
        "school_id": "school.arcane",
        "display_name_key": "spell.arcane.fixture.name",
        "cast_kind": "instant",
        "target_mode": "self",
        "max_targets": 1,
        "range_wu": 96.0,
        "area_radius_wu": 0.0,
        "mana_cost": 10,
        "cooldown_game_minutes": 0,
        "prerequisites": {
            "min_school_skill_rating": 0,
            "required_ability_ids": [],
            "required_spell_ids": [],
            "required_item_tags": [],
        },
        "legal_override": "inherit",
        "consent_required": False,
        "effect_bindings": [{"effect_id": "magic.effect.detect_magic", "parameters": {}}],
        "presentation_id": "magic.presentation.arcane.fixture",
        "required_work_units": None,
    }
    record.update(overrides)
    return record


def test_magic_007_strict_decode_contract():
    spell = decode_spell_definition(_record())
    assert spell.cast_kind is CastKind.INSTANT
    # 多字段
    with pytest.raises(SpellError) as exc:
        decode_spell_definition(_record(freeform_effect="ignite everything"))
    assert exc.value.code == "spell_schema_additional_property"
    # 缺字段
    record = _record()
    del record["mana_cost"]
    with pytest.raises(SpellError) as exc2:
        decode_spell_definition(record)
    assert exc2.value.code == "spell_schema_missing_field"
    # 坏枚举
    with pytest.raises(SpellError) as exc3:
        decode_spell_definition(_record(cast_kind="chant"))
    assert exc3.value.code == "spell_schema_invalid_enum"
    # 传送命名（Schema 层）
    with pytest.raises(SpellError) as exc4:
        decode_spell_definition(_record(spell_id="spell.arcane.teleport"))
    assert exc4.value.code == "magic_teleport_forbidden"


def test_magic_007_numeric_and_structure_bounds():
    with pytest.raises(SpellError) as exc:
        decode_spell_definition(_record(mana_cost=70))
    assert exc.value.code == "spell_mana_cost_out_of_range"
    with pytest.raises(SpellError) as exc2:
        decode_spell_definition(_record(cooldown_game_minutes=1441))
    assert exc2.value.code == "spell_cooldown_out_of_range"
    # prerequisites 必须恰好四字段
    record = _record()
    record["prerequisites"]["extra_key"] = []
    with pytest.raises(SpellError) as exc3:
        decode_spell_definition(record)
    assert exc3.value.code == "spell_prerequisite_invalid"
    # effect_bindings 非空且每绑定恰好两字段
    with pytest.raises(SpellError) as exc4:
        decode_spell_definition(_record(effect_bindings=[]))
    assert exc4.value.code == "spell_effect_binding_missing"
    with pytest.raises(SpellError) as exc5:
        decode_spell_definition(_record(
            effect_bindings=[{"effect_id": "magic.effect.detect_magic", "parameters": {}, "narrative": "x"}]
        ))
    assert exc5.value.code == "spell_effect_binding_missing"


def test_magic_007_ritual_work_units_rule():
    # ritual 必须声明 work units
    with pytest.raises(SpellError) as exc:
        decode_spell_definition(_record(cast_kind="ritual", required_work_units=None))
    assert exc.value.code == "spell_ritual_work_units_missing"
    # instant 禁止声明
    with pytest.raises(SpellError) as exc2:
        decode_spell_definition(_record(cast_kind="instant", required_work_units=4))
    assert exc2.value.code == "spell_instant_work_units_forbidden"
    ritual = decode_spell_definition(_record(cast_kind="ritual", required_work_units=4))
    assert ritual.required_work_units == 4


def test_magic_008_default_catalog_closed_audit():
    catalog = build_default_spell_catalog()
    # RULE-MAGIC-021：恰好 12 条
    assert len(catalog) == 12
    spells = catalog.all()
    assert len({s.spell_id for s in spells}) == 12
    for spell in spells:
        # REQ-MAGIC-004：每法术恰好一个已注册学派
        assert spell.school_id.startswith("school.")
        # REQ-MAGIC-008：效果全部来自封闭注册表
        for binding in spell.effect_bindings:
            assert binding["effect_id"] in EFFECT_IDS
        # presentation 引用命名规范
        assert spell.presentation_id.startswith("magic.presentation.")
        # REQ-MAGIC-023 包络
        assert 5 <= spell.mana_cost <= 60
        assert 0 <= spell.cooldown_game_minutes <= 1440
        if spell.cast_kind is CastKind.RITUAL:
            assert spell.required_work_units is not None
        else:
            assert spell.required_work_units is None
    # 未知 spell_id fail closed
    with pytest.raises(SpellError) as exc:
        catalog.get("spell.arcane.fireball")
    assert exc.value.code == "MAGIC_SPELL_UNKNOWN"


def test_magic_008_study_work_units_formula():
    catalog = build_default_spell_catalog()
    # RULE-MAGIC-031：max(4, mana//10 × 2)
    assert study_work_units_for(catalog.get("spell.arcane.glowlight")) == 4  # mana 5
    assert study_work_units_for(catalog.get("spell.warding.ley_anchor")) == 8  # mana 40
    assert study_work_units_for(catalog.get("spell.spirit.hex_of_weariness")) == 6  # mana 35


def test_magic_009_target_mode_matrix():
    catalog = build_default_spell_catalog()
    self_spell = catalog.get("spell.arcane.glowlight")  # self
    single = catalog.get("spell.restoration.minor_mend")  # single_entity
    ground = catalog.get("spell.elemental.kindle_flame")  # ground_point
    area = catalog.get("spell.arcane.detect_magic")  # area_around_caster

    # self/none/area：任何 target 或 aim 都非法
    for spell in (self_spell, area):
        validate_target_arguments(spell, [], None)
        with pytest.raises(SpellError):
            validate_target_arguments(spell, ["r.x"], None)
        with pytest.raises(SpellError):
            validate_target_arguments(spell, [], {"x_wu": 0.0, "y_wu": 0.0})
    # single：恰好 1 目标
    validate_target_arguments(single, ["r.x"], None)
    with pytest.raises(SpellError):
        validate_target_arguments(single, [], None)
    with pytest.raises(SpellError):
        validate_target_arguments(single, ["r.x", "r.y"], None)
    # ground：只要 aim_point
    validate_target_arguments(ground, [], {"x_wu": 1.0, "y_wu": 1.0})
    with pytest.raises(SpellError):
        validate_target_arguments(ground, [], None)
    with pytest.raises(SpellError):
        validate_target_arguments(ground, ["r.x"], {"x_wu": 1.0, "y_wu": 1.0})
    # multi：1..min(max_targets, 8)
    multi = decode_spell_definition(_record(
        spell_id="spell.arcane.fixture_multi", target_mode="multi_entity", max_targets=10,
    ))
    validate_target_arguments(multi, [f"r.{i}" for i in range(8)], None)
    with pytest.raises(SpellError):
        validate_target_arguments(multi, [f"r.{i}" for i in range(9)], None)
    with pytest.raises(SpellError):
        validate_target_arguments(multi, [], None)


def test_magic_009_legal_override_only_tightens():
    catalog = build_default_spell_catalog()
    from src.magic import build_default_schools

    schools = build_default_schools()
    strictness = {"permitted": 0, "restricted": 1, "prohibited": 2}
    for spell in catalog.all():
        baseline = schools.get(spell.school_id).default_legal_baseline
        if spell.legal_override is LegalOverride.INHERIT:
            continue
        # override 只能收紧（或持平），不得把基线放宽
        assert strictness[spell.legal_override.value] >= strictness[baseline]
        # 首版唯一 override：hex 收紧为 restricted 且要求同意
        assert spell.spell_id == "spell.spirit.hex_of_weariness"
        assert spell.consent_required
    inherit_count = sum(1 for s in catalog.all() if s.legal_override is LegalOverride.INHERIT)
    assert inherit_count == 11

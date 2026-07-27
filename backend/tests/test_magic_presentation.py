"""
TEST-MAGIC-024..025：魔法 VFX 与音频（DOC-MAGIC-011）

- TEST-MAGIC-024：映射闭合与家族前缀审计；表现失败不影响提交；版本化替换回放
- TEST-MAGIC-025：降级链逐级拔除、诊断一次性、幻象识破标记访问控制
"""

import pytest

from src.magic import (
    FALLBACK_VFX_ID,
    PresentationError,
    PresentationRegistry,
    audit_presentation_closure,
    build_default_presentations,
    build_default_schools,
    build_default_spell_catalog,
    decode_presentation,
    illusion_projection_for_observer,
)

from magic_helpers import command, learn, make_engine


def _record(presentation_id, family, short, **overrides):
    record = {
        "presentation_schema_version": 1,
        "presentation_id": presentation_id,
        "cast_vfx_id": f"{family}.{short}_cast",
        "impact_vfx_id": f"{family}.{short}_impact",
        "cast_audio_id": f"audio.sfx.magic.{short}",
        "loop_vfx_id": None,
        "reduced_motion_icon": "icon.magic.arcane",
    }
    record.update(overrides)
    return record


def test_magic_024_closure_and_family_audit():
    catalog = build_default_spell_catalog()
    schools = build_default_schools()
    registry = build_default_presentations(catalog, schools)
    # REQ-MAGIC-021：12 条法术的表现引用全部解析、前缀零违例
    assert len(registry) == 12
    audit_presentation_closure(catalog, registry)
    for spell in catalog.all():
        resolved = registry.resolve_with_fallback(spell.presentation_id, spell.school_id)
        assert resolved["fallback_level"] == 0
        family = schools.get(spell.school_id).vfx_family
        assert resolved["cast_vfx_id"].startswith(f"{family}.")
        assert resolved["impact_vfx_id"].startswith(f"{family}.")
    # 家族前缀违例在构建期拒绝
    with pytest.raises(PresentationError) as exc:
        registry.register(
            _record("magic.presentation.elemental.bad", "vfx.arcane", "bad"),
            "school.elemental",
        )
    assert exc.value.code == "magic_presentation_family_mismatch"


def test_magic_024_duration_bounds():
    # RULE-MAGIC-059：duration_ms 遵守 100..1500，越界不注册
    for bad in (50, 1600):
        with pytest.raises(PresentationError) as exc:
            decode_presentation(_record(
                "magic.presentation.arcane.x", "vfx.arcane", "x", duration_ms=bad,
            ))
        assert exc.value.code == "magic_presentation_duration_out_of_range"


def test_magic_024_presentation_failure_does_not_affect_commit():
    # REQ-MAGIC-022：表现缺失/降级不影响已提交效果
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight")
    committed = env.engine.commit_spell_cast(command(env, "r.a", "spell.arcane.glowlight"))
    assert committed.spell_id == "spell.arcane.glowlight"
    assert env.mana.get("r.a").mana_current == env.mana.get("r.a").mana_max - 5
    # 表现层对该事件的解析完全失败（资产全部拔除）也只是降级
    schools = build_default_schools()
    registry = PresentationRegistry(schools)
    resolved = registry.resolve_with_fallback(
        "magic.presentation.arcane.glowlight", "school.arcane",
        asset_available=lambda _asset: False,
    )
    assert resolved["fallback_level"] == 2
    assert resolved["cast_vfx_id"] == FALLBACK_VFX_ID
    # 提交记录本身不变
    assert env.engine.committed_cast(committed.command_id) is committed


def test_magic_024_versioned_replacement_replay():
    schools = build_default_schools()
    registry = PresentationRegistry(schools)
    registry.register(
        _record("magic.presentation.arcane.glowlight", "vfx.arcane", "glowlight_v1"),
        "school.arcane",
    )
    # RULE-MAGIC-063：替换走版本化新增；旧 ID 仍可解析（旧存档回放）
    registry.register_versioned(
        _record("magic.presentation.arcane.glowlight.v2", "vfx.arcane", "glowlight_v2"),
        "school.arcane",
        supersedes="magic.presentation.arcane.glowlight",
    )
    replayed = registry.resolve_with_fallback(
        "magic.presentation.arcane.glowlight", "school.arcane"
    )
    assert replayed["fallback_level"] == 0
    assert replayed["presentation_id_resolved"] == "magic.presentation.arcane.glowlight.v2"
    assert replayed["cast_vfx_id"] == "vfx.arcane.glowlight_v2_cast"
    # 版本化新增不允许原地覆盖
    with pytest.raises(PresentationError) as exc:
        registry.register(
            _record("magic.presentation.arcane.glowlight", "vfx.arcane", "glowlight_v3"),
            "school.arcane",
        )
    assert exc.value.code == "magic_presentation_conflict"


def test_magic_025_fallback_chain_step_by_step():
    schools = build_default_schools()
    registry = PresentationRegistry(schools)
    registry.register(
        _record("magic.presentation.arcane.glowlight", "vfx.arcane", "glowlight"),
        "school.arcane",
    )
    # 第 0 级：注册项命中，音频缺失静默跳过
    hit = registry.resolve_with_fallback(
        "magic.presentation.arcane.glowlight", "school.arcane",
        asset_available=lambda asset: not asset.startswith("audio."),
    )
    assert hit["fallback_level"] == 0
    assert hit["cast_audio_id"] is None
    assert hit["cast_vfx_id"] == "vfx.arcane.glowlight_cast"
    # 第 1 级：presentation 未注册 → 学派家族默认
    family = registry.resolve_with_fallback(
        "magic.presentation.arcane.unknown", "school.arcane"
    )
    assert family["fallback_level"] == 1
    assert family["cast_vfx_id"] == "vfx.arcane.family_default"
    assert family["cast_audio_id"] is None
    # 第 2 级：家族默认资产也缺失 → 全局 fallback
    global_fallback = registry.resolve_with_fallback(
        "magic.presentation.arcane.another", "school.arcane",
        asset_available=lambda _asset: False,
    )
    assert global_fallback["fallback_level"] == 2
    assert global_fallback["cast_vfx_id"] == FALLBACK_VFX_ID


def test_magic_025_diagnostic_only_once():
    schools = build_default_schools()
    registry = PresentationRegistry(schools)
    first = registry.resolve_with_fallback("magic.presentation.arcane.missing", "school.arcane")
    second = registry.resolve_with_fallback("magic.presentation.arcane.missing", "school.arcane")
    assert first["diagnostic"] is not None
    assert second["diagnostic"] is None  # 同一 ID 不重复刷屏


def test_magic_025_illusion_marker_access_control():
    # RULE-MAGIC-062：未识破者看不到幻象标记（与真实物体同层渲染）
    naive = illusion_projection_for_observer("ei.1", observer_revealed=False)
    assert "illusion_revealed_marker" not in naive
    assert naive["render_kind"] == "world_object"
    revealed = illusion_projection_for_observer("ei.1", observer_revealed=True)
    assert revealed["illusion_revealed_marker"] is True

"""
TEST-MAGIC-010..012：施法合法性（DOC-MAGIC-005）

- TEST-MAGIC-010：七级校验短路矩阵（顺序、reason code、无状态变化）
- TEST-MAGIC-011：提交幂等重放与失败缓存
- TEST-MAGIC-012：世界合法性 Table（镇区禁令/Encounter/同意/紧急例外）
"""

import pytest

from src.magic import (
    CastingError,
    Legality,
    VerdictClassification,
)

from magic_helpers import command, drain_mana, learn, make_engine


def test_magic_010_stage1_reference_and_purpose():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight", "spell.restoration.minor_mend")
    # 未注册法术 → FORBIDDEN（RULE-MAGIC-027）
    verdict = env.engine.validate_spell_cast(command(env, "r.a", "spell.arcane.fireball"))
    assert verdict.classification is VerdictClassification.FORBIDDEN
    assert verdict.failed_stage == 1
    assert verdict.reason_code == "MAGIC_SPELL_UNKNOWN"
    # 用途伪装：治疗法术声明 combat → 第 1 级退回
    verdict2 = env.engine.validate_spell_cast(
        command(env, "r.a", "spell.restoration.minor_mend", declared_purpose="combat",
                target_refs=("r.b",))
    )
    assert verdict2.failed_stage == 1
    assert verdict2.reason_code == "MAGIC_TARGET_INVALID"
    assert env.engine.revision == 0  # 无状态变化


def test_magic_010_stage2_not_learned():
    env = make_engine()
    env.mana.register_caster("r.a", 0)
    verdict = env.engine.validate_spell_cast(command(env, "r.a", "spell.arcane.glowlight"))
    assert verdict.classification is VerdictClassification.FORBIDDEN
    assert verdict.failed_stage == 2
    assert verdict.reason_code == "MAGIC_SPELL_NOT_LEARNED"


def test_magic_010_stage3_exhaustion_and_mana():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight", "spell.restoration.minor_mend", max_rating=0)
    # 枯竭：<10 进入枯竭后一切施法拒绝（REPLAN）
    drain_mana(env, "r.a", 55)
    verdict = env.engine.validate_spell_cast(command(env, "r.a", "spell.arcane.glowlight"))
    assert verdict.classification is VerdictClassification.REPLAN_REQUIRED
    assert verdict.failed_stage == 3
    assert verdict.reason_code == "MAGIC_CASTER_EXHAUSTED"
    # 未枯竭但不足：mana 10 < cost 12
    env2 = make_engine()
    learn(env2, "r.b", "spell.restoration.minor_mend", max_rating=0)
    drain_mana(env2, "r.b", 50)
    verdict2 = env2.engine.validate_spell_cast(
        command(env2, "r.b", "spell.restoration.minor_mend", declared_purpose="healing",
                target_refs=("r.b",))
    )
    assert verdict2.failed_stage == 3
    assert verdict2.reason_code == "MAGIC_MANA_INSUFFICIENT"


def test_magic_010_stage4_target_and_range():
    targets = {
        "r.near": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}},
        "r.far": {"scene_id": "scene.town", "position": {"x_wu": 200.0, "y_wu": 0.0}},
        "r.away": {"scene_id": "scene.other", "position": {"x_wu": 1.0, "y_wu": 0.0}},
    }
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.restoration.minor_mend")
    # 跨 Scene 目标一律非法
    cross = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.away",),
    ))
    assert cross.failed_stage == 4 and cross.reason_code == "MAGIC_TARGET_INVALID"
    # 欧氏距离超 96wu
    out_of_range = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.far",),
    ))
    assert out_of_range.failed_stage == 4 and out_of_range.reason_code == "MAGIC_RANGE_EXCEEDED"
    # 未知目标引用
    ghost = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.ghost",),
    ))
    assert ghost.failed_stage == 4 and ghost.reason_code == "MAGIC_TARGET_INVALID"


def test_magic_010_stage5_prerequisites():
    ratings = {("r.a", "school.warding"): 40}
    env = make_engine(ratings=ratings)
    learn(env, "r.a", "spell.warding.purify_ground")
    # 学习后技能降级到门槛以下（fixture 直接改表）
    ratings[("r.a", "school.warding")] = 10
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.warding.purify_ground",
        aim_point={"x_wu": 5.0, "y_wu": 0.0},
    ))
    assert verdict.failed_stage == 5
    assert verdict.reason_code == "MAGIC_PREREQUISITE_MISSING"


def test_magic_010_stage6_and_stage7():
    targets = {"r.a": {"scene_id": "scene.town", "position": {"x_wu": 0.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.spirit.hex_of_weariness")
    # restricted 无证据 → MAGIC_CONSENT_MISSING（第 6 级）
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.a",),
    ))
    assert verdict.failed_stage == 6 and verdict.reason_code == "MAGIC_CONSENT_MISSING"
    # 第 7 级：Revision 过期
    stale = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.a",), authorization_event_ids=("evt.auth",),
        expected_revision=env.engine.revision + 1,
    ))
    assert stale.failed_stage == 7 and stale.reason_code == "stale_revision"
    assert stale.classification is VerdictClassification.REPLAN_REQUIRED


def test_magic_010_short_circuit_order():
    # 未注册法术 + Revision 错误：仍按第 1 级报错（顺序固定）
    env = make_engine()
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.arcane.fireball", expected_revision=999,
    ))
    assert verdict.failed_stage == 1
    assert verdict.reason_code == "MAGIC_SPELL_UNKNOWN"


def test_magic_011_commit_idempotent_replay():
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight")
    cmd = command(env, "r.a", "spell.arcane.glowlight", command_id="cmd.replay.1")
    first = env.engine.commit_spell_cast(cmd)
    second = env.engine.commit_spell_cast(cmd)
    assert first is second
    # Mana 只扣一次、Revision 只推进一次
    assert env.mana.get("r.a").mana_current == env.mana.get("r.a").mana_max - 5
    assert env.engine.revision == 1
    # XP 只授一次
    assert env.learning.xp_event_count == 1
    # 失败同样缓存：重放抛同一 reason code
    env2 = make_engine()
    bad = command(env2, "r.a", "spell.arcane.fireball", command_id="cmd.replay.bad")
    with pytest.raises(CastingError) as exc:
        env2.engine.commit_spell_cast(bad)
    assert exc.value.code == "MAGIC_SPELL_UNKNOWN"
    with pytest.raises(CastingError) as exc2:
        env2.engine.commit_spell_cast(bad)
    assert exc2.value.code == "MAGIC_SPELL_UNKNOWN"
    assert env2.engine.revision == 0


def test_magic_011_cooldown_set_after_commit():
    targets = {"r.a": {"scene_id": "scene.town", "position": {"x_wu": 0.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.restoration.minor_mend")
    env.resident_port.set_hp("r.a", 40, 100)
    cmd = command(env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
                  target_refs=("r.a",), game_time=100)
    env.engine.commit_spell_cast(cmd)
    # minor_mend cooldown 30：ready_at = 130
    assert not env.mana.cooldown_ready("r.a", "spell.restoration.minor_mend", 129)
    assert env.mana.cooldown_ready("r.a", "spell.restoration.minor_mend", 130)


def test_magic_012_town_public_attack_prohibited():
    env = make_engine(jurisdiction="town_public")
    learn(env, "r.a", "spell.elemental.kindle_flame")
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.elemental.kindle_flame",
        aim_point={"x_wu": 5.0, "y_wu": 0.0},
    ))
    # RULE-MAGIC-022：镇区公共空间攻击性法术一律拒绝，无提交后受罚路径
    assert verdict.classification is VerdictClassification.FORBIDDEN
    assert verdict.reason_code == "MAGIC_LEGALITY_PROHIBITED"
    assert verdict.failed_stage == 6


def test_magic_012_town_prohibition_not_retroactively_legalized():
    # RULE-MAGIC-024：Overworld prohibited 不因发起战斗而追溯合法化
    env = make_engine(
        jurisdiction="town_public",
        encounters={"r.a": {"enemies": {"r.b"}}},
    )
    learn(env, "r.a", "spell.elemental.kindle_flame")
    verdict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.elemental.kindle_flame",
        aim_point={"x_wu": 5.0, "y_wu": 0.0},
    ))
    assert verdict.reason_code == "MAGIC_LEGALITY_PROHIBITED"
    assert verdict.classification is VerdictClassification.FORBIDDEN


def test_magic_012_encounter_legality_table():
    targets = {
        "r.enemy": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}},
        "r.bystander": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}},
    }
    env = make_engine(
        targets=targets,
        encounters={"r.a": {"enemies": {"r.enemy"}}},
    )
    learn(env, "r.a", "spell.spirit.hex_of_weariness")
    # Encounter 中对参战敌方的攻击性法术合法（携带授权证据 → restricted_authorized）
    lawful = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.enemy",), authorization_event_ids=("evt.consent",),
    ))
    assert lawful.classification is VerdictClassification.VALID
    assert lawful.legality is Legality.RESTRICTED_AUTHORIZED
    # Encounter 中对非敌方施放攻击性法术 → 规则冲突
    conflict = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.bystander",), authorization_event_ids=("evt.consent",),
    ))
    assert conflict.reason_code == "MAGIC_ENCOUNTER_RULE_CONFLICT"
    assert conflict.classification is VerdictClassification.REPLAN_REQUIRED
    # 伤害方向无紧急例外：无证据即便对敌人也拒绝
    no_consent = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.enemy",),
    ))
    assert no_consent.reason_code == "MAGIC_CONSENT_MISSING"


def test_magic_012_emergency_rescue_exception():
    targets = {
        "r.down": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0},
                   "incapacitated": True},
        "r.up": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0},
                 "incapacitated": False},
    }
    env = make_engine(targets=targets, jurisdiction="town_public")
    learn(env, "r.a", "spell.restoration.minor_mend")
    # RULE-MAGIC-025：对无行为能力目标的救助方向紧急例外（无同意也可提交）
    rescue = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.down",),
    ))
    assert rescue.classification is VerdictClassification.VALID
    assert rescue.legality is Legality.PERMITTED
    # 目标有行为能力：仍需同意
    needs_consent = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.up",),
    ))
    assert needs_consent.reason_code == "MAGIC_CONSENT_MISSING"


def test_magic_012_restricted_baseline_requires_evidence():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.spirit.soothe_spirit")
    # Spirit 学派基线 restricted：无证据拒绝，有证据 restricted_authorized
    denied = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.soothe_spirit", declared_purpose="healing",
        target_refs=("r.b",),
    ))
    assert denied.reason_code == "MAGIC_CONSENT_MISSING"
    allowed = env.engine.validate_spell_cast(command(
        env, "r.a", "spell.spirit.soothe_spirit", declared_purpose="healing",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
    ))
    assert allowed.classification is VerdictClassification.VALID
    assert allowed.legality is Legality.RESTRICTED_AUTHORIZED
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.spirit.soothe_spirit", declared_purpose="healing",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
        command_id="cmd.soothe.1",
    ))
    assert committed.legality is Legality.RESTRICTED_AUTHORIZED

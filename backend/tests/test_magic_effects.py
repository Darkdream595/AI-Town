"""
TEST-MAGIC-019..021：魔法环境交互（DOC-MAGIC-009）

- TEST-MAGIC-019：12 handler 注册表闭合与 strict 参数子 Schema
- TEST-MAGIC-020：火/治疗/诅咒/侦测路由集成与两阶段原子性
- TEST-MAGIC-021：持续实例生命周期、锚点上限与真值不变性
"""

import pytest

from src.magic import (
    EFFECT_IDS,
    EFFECT_PARAM_FIELDS,
    EFFECT_PURPOSE_WHITELIST,
    CastingError,
    EffectError,
    EffectInstanceState,
    EffectInstanceStore,
    run_effect_bindings,
)

from magic_helpers import command, learn, make_engine


def test_magic_019_handler_registry_closed():
    # REQ-MAGIC-017：恰好 12 个 handler，参数 Schema 与用途白名单同键集
    assert len(EFFECT_IDS) == 12
    assert len(set(EFFECT_IDS)) == 12
    assert set(EFFECT_PARAM_FIELDS) == set(EFFECT_IDS)
    assert set(EFFECT_PURPOSE_WHITELIST) == set(EFFECT_IDS)
    # RULE-MAGIC-036：治疗类只能 healing；诅咒只能 combat/ritual
    assert EFFECT_PURPOSE_WHITELIST["magic.effect.heal_minor"] == frozenset({"healing"})
    assert EFFECT_PURPOSE_WHITELIST["magic.effect.cure_illness"] == frozenset({"healing"})
    assert EFFECT_PURPOSE_WHITELIST["magic.effect.curse_weariness"] == frozenset({"combat", "ritual"})


def test_magic_019_param_schema_strict():
    env = make_engine()
    learn(env, "r.a", "spell.elemental.kindle_flame")
    env.event_port.register_flammable(5.0, 0.0)
    ctx = env.engine.build_effect_context(
        command(env, "r.a", "spell.elemental.kindle_flame",
                aim_point={"x_wu": 5.0, "y_wu": 0.0}),
        env.catalog.get("spell.elemental.kindle_flame"),
        "evt.ctx",
    )
    # 未知 handler
    with pytest.raises(EffectError) as exc:
        run_effect_bindings(({"effect_id": "magic.effect.fireball", "parameters": {}},), ctx)
    assert exc.value.code == "magic_effect_unknown"
    # 多参数/缺参数都被 strict 子 Schema 拒绝
    with pytest.raises(EffectError) as exc2:
        run_effect_bindings(
            ({"effect_id": "magic.effect.ignite", "parameters": {"ignite_strength": 1, "extra": 1}},), ctx
        )
    assert exc2.value.code == "magic_effect_params_invalid"
    with pytest.raises(EffectError) as exc3:
        run_effect_bindings(({"effect_id": "magic.effect.ignite", "parameters": {}},), ctx)
    assert exc3.value.code == "magic_effect_params_invalid"


def test_magic_020_ignite_routing_and_preconditions():
    env = make_engine()
    learn(env, "r.a", "spell.elemental.kindle_flame", "spell.elemental.douse")
    env.event_port.register_flammable(5.0, 0.0)
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.elemental.kindle_flame", aim_point={"x_wu": 5.0, "y_wu": 0.0},
    ))
    assert committed.effect_results[0]["routed"] == "EVENT"
    assert env.event_port.calls[0][0] == "ignite"
    assert env.event_port.flammable_state({"x_wu": 5.0, "y_wu": 0.0})["active"]
    # 已燃烧火源重复点燃：前置拒绝、无半效果
    with pytest.raises(CastingError) as exc:
        env.engine.commit_spell_cast(command(
            env, "r.a", "spell.elemental.kindle_flame", command_id="cmd.ignite.2",
            aim_point={"x_wu": 5.0, "y_wu": 0.0}, game_time=1,
        ))
    assert exc.value.code == "magic_ignite_occupied"
    assert len([c for c in env.event_port.calls if c[0] == "ignite"]) == 1
    # 熄灭 → 再次点燃可行
    env.engine.commit_spell_cast(command(
        env, "r.a", "spell.elemental.douse", command_id="cmd.douse.1",
        aim_point={"x_wu": 5.0, "y_wu": 0.0}, game_time=2,
    ))
    assert not env.event_port.flammable_state({"x_wu": 5.0, "y_wu": 0.0})["active"]
    # 未注册/潮湿/无火源三种前置
    with pytest.raises(CastingError) as exc2:
        env.engine.commit_spell_cast(command(
            env, "r.a", "spell.elemental.kindle_flame", command_id="cmd.ignite.3",
            aim_point={"x_wu": 90.0, "y_wu": 0.0}, game_time=3,
        ))
    assert exc2.value.code == "magic_ignite_unregistered"
    env.event_port.register_flammable(7.0, 0.0, wet=True)
    with pytest.raises(CastingError) as exc3:
        env.engine.commit_spell_cast(command(
            env, "r.a", "spell.elemental.kindle_flame", command_id="cmd.ignite.4",
            aim_point={"x_wu": 7.0, "y_wu": 0.0}, game_time=4,
        ))
    assert exc3.value.code == "magic_ignite_wet"
    with pytest.raises(CastingError) as exc4:
        env.engine.commit_spell_cast(command(
            env, "r.a", "spell.elemental.douse", command_id="cmd.douse.2",
            aim_point={"x_wu": 7.0, "y_wu": 0.0}, game_time=5,
        ))
    assert exc4.value.code == "magic_extinguish_inactive"


def test_magic_020_heal_formula_and_daily_cap():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.restoration.minor_mend")
    env.resident_port.set_hp("r.b", 0, 100)  # hp_max 100 → 日上限 50
    # heal = 6 + (100 // 25) × 2 = 14；第 1..3 次全量
    expected = [14, 14, 14, 8, 0]
    for index, want in enumerate(expected):
        committed = env.engine.commit_spell_cast(command(
            env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
            target_refs=("r.b",), authorization_event_ids=("evt.consent",),
            command_id=f"cmd.heal.{index}", game_time=index * 60,
        ))
        assert committed.effect_results[0]["hp_delta"] == want
    # REQ-MAGIC-023：日累计恰好封顶 50，超出部分结算为 0
    assert env.ledger.total("r.b", 0) == 50
    assert env.resident_port.hp["r.b"][0] == 50
    # 满血目标整次拒绝（allow_overheal=false）
    env.resident_port.set_hp("r.b", 100, 100)
    with pytest.raises(CastingError) as exc:
        env.engine.commit_spell_cast(command(
            env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
            target_refs=("r.b",), authorization_event_ids=("evt.consent",),
            command_id="cmd.heal.full", game_time=600, game_day=1,
        ))
    assert exc.value.code == "magic_heal_overheal_forbidden"
    # game_day=1  ledger 重置 → hp 50/100 非满血 → 可继续治疗
    env.resident_port.set_hp("r.b", 50, 100)
    committed_next_day = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
        command_id="cmd.heal.day1", game_time=601, game_day=1,
    ))
    assert committed_next_day.effect_results[0]["hp_delta"] == 14


def test_magic_020_curse_is_timeboxed_illness():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.spirit.hex_of_weariness")
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.spirit.hex_of_weariness", declared_purpose="combat",
        target_refs=("r.b",), authorization_event_ids=("evt.consent",),
    ))
    # RULE-MAGIC-047：诅咒登记为带退出条件的病程，无永久诅咒
    assert committed.effect_results[0]["kind"] == "IllnessApplied"
    resident_id, illness_id, duration = env.resident_port.illnesses[0]
    assert illness_id == "illness.arcane_weariness"
    assert 0 < duration <= 1440


def test_magic_020_detect_magic_observation():
    env = make_engine(
        magical_item_detector=lambda _s, _c, _r: [{"fact_kind": "magical_item", "item_hint": "wand"}],
    )
    learn(env, "r.a", "spell.arcane.glowlight", "spell.arcane.detect_magic")
    env.engine.commit_spell_cast(command(env, "r.a", "spell.arcane.glowlight"))
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.arcane.detect_magic", command_id="cmd.detect.1", game_time=1,
    ))
    assert committed.effect_results[0]["routed"] == "MEMORY"
    caster_id, facts, _event = env.memory_port.observations[0]
    assert caster_id == "r.a"
    kinds = {f["fact_kind"] for f in facts}
    # RULE-MAGIC-048：只含结构化事实（持续实例 + 可侦测物品）
    assert kinds == {"world_magic_effect", "magical_item"}


def test_magic_020_two_phase_atomicity():
    # RULE-MAGIC-052：任一绑定前置失败 → 全部不应用
    env = make_engine()
    learn(env, "r.a", "spell.restoration.minor_mend")
    env.resident_port.set_hp("r.b", 40, 100)
    ctx = env.engine.build_effect_context(
        command(env, "r.a", "spell.restoration.minor_mend", declared_purpose="healing",
                target_refs=("r.b",)),
        env.catalog.get("spell.restoration.minor_mend"),
        "evt.atomic",
    )
    bindings = (
        {"effect_id": "magic.effect.heal_minor",
         "parameters": {"heal_base": 6, "skill_scale_per_25_rating": 2}},
        {"effect_id": "magic.effect.ignite", "parameters": {"ignite_strength": 1}},
    )
    with pytest.raises(EffectError):
        run_effect_bindings(bindings, ctx)  # ignite 目标未注册 → 整次拒绝
    assert env.resident_port.hp["r.b"][0] == 40  # heal 未应用
    assert env.resident_port.calls == []


def test_magic_021_instance_lifecycle_and_caps():
    store = EffectInstanceStore()
    # 持续实例必须声明时限；到期严格大于才过期
    instance = store.create(
        "magic.effect.conjure_light", "r.a", "scene.town",
        {"x_wu": 0.0, "y_wu": 0.0}, 32.0, 720, 0, "evt.1",
    )
    assert store.expire_overdue(720) == []
    assert store.expire_overdue(721) == [instance.effect_instance_id]
    assert store.get(instance.effect_instance_id).state is EffectInstanceState.EXPIRED
    # 超时时限包络：普通效果 >1440 拒绝，锚点 >10080 拒绝
    with pytest.raises(EffectError):
        store.create("magic.effect.conjure_light", "r.a", "scene.town", None, 1.0, 1441, 0, "evt.x")
    with pytest.raises(EffectError):
        store.create("magic.effect.place_ley_anchor", "r.a", "scene.town", None, 1.0, 10081, 0, "evt.y")


def test_magic_021_scene_cap_and_anchor_rules():
    store = EffectInstanceStore()
    for index in range(32):
        store.create("magic.effect.conjure_light", "r.a", "scene.town",
                     {"x_wu": float(index * 100), "y_wu": 0.0}, 1.0, 60, 0, f"evt.{index}")
    # Scene 实例上限 32
    with pytest.raises(EffectError) as exc:
        store.create("magic.effect.conjure_light", "r.a", "scene.town",
                     {"x_wu": 9999.0, "y_wu": 0.0}, 1.0, 60, 0, "evt.33")
    assert exc.value.code == "magic_effect_instance_cap"
    # 另一 Scene 不受影响；驱散释放容量
    store.create("magic.effect.conjure_light", "r.a", "scene.other",
                 {"x_wu": 0.0, "y_wu": 0.0}, 1.0, 60, 0, "evt.other")
    first_id = next(iter(store._instances))
    store.dispel(first_id)
    assert store.get(first_id).state is EffectInstanceState.DISPELLED
    with pytest.raises(EffectError) as exc2:
        store.dispel(first_id)
    assert exc2.value.code == "magic_effect_instance_terminal"

    anchors = EffectInstanceStore()
    anchors.create("magic.effect.place_ley_anchor", "r.a", "scene.ley",
                   {"x_wu": 0.0, "y_wu": 0.0}, 100.0, 10080, 0, "evt.a1")
    # 重叠拒绝（半径相交）
    with pytest.raises(EffectError) as exc3:
        anchors.create("magic.effect.place_ley_anchor", "r.b", "scene.ley",
                       {"x_wu": 50.0, "y_wu": 0.0}, 100.0, 10080, 0, "evt.a2")
    assert exc3.value.code == "magic_ley_anchor_overlap"
    anchors.create("magic.effect.place_ley_anchor", "r.b", "scene.ley",
                   {"x_wu": 500.0, "y_wu": 0.0}, 100.0, 10080, 0, "evt.a3")
    # 活动锚点上限 2
    with pytest.raises(EffectError) as exc4:
        anchors.create("magic.effect.place_ley_anchor", "r.c", "scene.ley",
                       {"x_wu": 1000.0, "y_wu": 0.0}, 100.0, 10080, 0, "evt.a4")
    assert exc4.value.code == "magic_ley_anchor_cap"
    # ley 加成不叠加：覆盖区内读取恒为 +100
    assert anchors.ley_anchor_bonus_q1000("scene.ley", {"x_wu": 10.0, "y_wu": 0.0}, 0) == 100
    assert anchors.ley_anchor_bonus_q1000("scene.ley", {"x_wu": 300.0, "y_wu": 0.0}, 0) == 0


def test_magic_021_illusion_truth_unchanged():
    # 幻象/光照是表现层实例，不改世界真值：目标位置与 HP 不受 veil 影响
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    learn(env, "r.a", "spell.illusion.minor_veil")
    env.resident_port.set_hp("r.b", 40, 100)
    before = dict(targets["r.b"])
    committed = env.engine.commit_spell_cast(command(
        env, "r.a", "spell.illusion.minor_veil",
        aim_point={"x_wu": 10.0, "y_wu": 0.0},
        authorization_event_ids=("evt.consent",),  # 幻术基线 restricted：需授权证据
    ))
    assert committed.effect_results[0]["kind"] == "VeilConjured"
    assert targets["r.b"] == before
    assert env.resident_port.hp["r.b"] == [40, 100]
    assert env.resident_port.calls == []
    # 侦测只揭示结构化事实，不含虚构实体
    facts = env.store.detectable_facts("scene.town", {"x_wu": 0.0, "y_wu": 0.0}, 64.0, 0)
    assert facts
    for fact in facts:
        assert set(fact) == {"fact_kind", "effect_id", "radius_wu"}

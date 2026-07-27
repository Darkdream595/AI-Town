"""
TEST-MAGIC-022..023：魔法物品（DOC-MAGIC-010）

- TEST-MAGIC-022：定义审计、充能守恒、tombstone 同步、凭空制造反例
- TEST-MAGIC-023：法器合法性等价、回充长行动、饰物修正不叠加
"""

import pytest

from src.magic import (
    ChargeState,
    MagicItemChargeRegistry,
    MagicItemError,
    MagicItemService,
    audit_magic_item_definitions,
    build_default_magic_items,
    compose_trinket_modifiers,
    decode_magic_item_definition,
)

from magic_helpers import learn, make_engine


def _charged_record(**overrides):
    record = {
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.fixture",
        "magic_item_kind": "charged_spell_item",
        "bound_spell_id": "spell.arcane.glowlight",
        "charges_max": 5,
        "recharge_school_id": "school.arcane",
        "teaches_spell_id": None,
        "passive_modifiers": [],
        "detectable": True,
    }
    record.update(overrides)
    return record


def test_magic_022_definition_decode_branch_matrix():
    # 三分支 strict：充能法器缺充能字段
    with pytest.raises(MagicItemError) as exc:
        decode_magic_item_definition(_charged_record(charges_max=None))
    assert exc.value.code == "magic_item_branch_invalid"
    # 魔法书不得有充能字段
    with pytest.raises(MagicItemError) as exc2:
        decode_magic_item_definition(_charged_record(
            magic_item_kind="spellbook", bound_spell_id=None,
            charges_max=None, recharge_school_id=None,
            teaches_spell_id="spell.arcane.glowlight",
        ) | {"charges_max": 5})
    assert exc2.value.code == "magic_item_branch_invalid"
    # 饰物必须有注册修正键
    with pytest.raises(MagicItemError) as exc3:
        decode_magic_item_definition(_charged_record(
            magic_item_kind="passive_trinket", bound_spell_id=None,
            charges_max=None, recharge_school_id=None, passive_modifiers=[],
        ))
    assert exc3.value.code == "magic_item_branch_invalid"
    with pytest.raises(MagicItemError) as exc4:
        decode_magic_item_definition(_charged_record(
            magic_item_kind="passive_trinket", bound_spell_id=None,
            charges_max=None, recharge_school_id=None,
            passive_modifiers=[{"modifier_key": "fly_speed", "value": 10}],
        ))
    assert exc4.value.code == "magic_item_modifier_unknown"
    # 充能范围 1..20
    for bad in (0, 21):
        with pytest.raises(MagicItemError) as exc5:
            decode_magic_item_definition(_charged_record(charges_max=bad))
        assert exc5.value.code == "magic_item_charges_out_of_range"
    # 未知枚举与多字段
    with pytest.raises(MagicItemError) as exc6:
        decode_magic_item_definition(_charged_record(magic_item_kind="relic"))
    assert exc6.value.code == "magic_item_schema_invalid_enum"
    with pytest.raises(MagicItemError) as exc7:
        decode_magic_item_definition(_charged_record() | {"lore_text": "x"})
    assert exc7.value.code == "magic_item_schema_additional_property"


def test_magic_022_reference_audit_zero_orphan():
    env = make_engine()
    items = build_default_magic_items()
    # 首版六件全部可解析（REQ-MAGIC-019 双向引用审计）
    assert len(items) == 6
    audit_magic_item_definitions(items, env.catalog, env.schools)
    # 注入孤儿引用必检出
    orphan = build_default_magic_items()
    orphan.register(_charged_record(
        magic_definition_id="magic.item.orphan", bound_spell_id="spell.arcane.fireball",
    ))
    with pytest.raises(MagicItemError) as exc:
        audit_magic_item_definitions(orphan, env.catalog, env.schools)
    assert exc.value.code == "magic_item_reference_orphan"
    # 未知 definition 的 Item：fail closed，不猜测效果
    with pytest.raises(MagicItemError) as exc2:
        items.get("magic.item.unknown")
    assert exc2.value.code == "MAGIC_ITEM_DEFINITION_UNKNOWN"


def test_magic_022_charge_conservation_property():
    items = build_default_magic_items()
    charges = MagicItemChargeRegistry(items)
    charges.register_item("item.wand.1", "magic.item.wand_of_glowlight")
    assert charges.charges_of("item.wand.1") == 10
    # 扣减守恒：每次扣 1，同 (item, event) 幂等
    for index in range(10):
        charges.use_charge("item.wand.1", f"evt.use.{index}")
        charges.use_charge("item.wand.1", f"evt.use.{index}")
        assert charges.charges_of("item.wand.1") == 9 - index
    with pytest.raises(MagicItemError) as exc:
        charges.use_charge("item.wand.1", "evt.use.overflow")
    assert exc.value.code == "MAGIC_ITEM_NO_CHARGES"
    # 缺失投影按 0 fail closed
    assert charges.charges_of("item.ghost") == 0
    with pytest.raises(MagicItemError) as exc2:
        charges.use_charge("item.ghost", "evt.ghost")
    assert exc2.value.code == "MAGIC_ITEM_NO_CHARGES"


def test_magic_022_transfer_keeps_charges_and_tombstone_retires():
    items = build_default_magic_items()
    charges = MagicItemChargeRegistry(items)
    charges.register_item("item.charm.1", "magic.item.charm_of_soothing")
    charges.use_charge("item.charm.1", "evt.use.1")
    # RULE-MAGIC-057：Item 转移不重置充能（状态键为 item_id，与持有者无关）
    owners = {"item.charm.1": "r.seller"}
    owners["item.charm.1"] = "r.buyer"  # ECON 侧转移事件
    assert charges.charges_of("item.charm.1") == 4
    # tombstone 同步 retired，不可复活
    charges.retire("item.charm.1")
    assert charges.charges_of("item.charm.1") == 0
    with pytest.raises(MagicItemError) as exc:
        charges.use_charge("item.charm.1", "evt.use.2")
    assert exc.value.code == "magic_item_charge_retired"
    with pytest.raises(MagicItemError) as exc2:
        charges.recharge_one("item.charm.1", "evt.re.1", 100)
    assert exc2.value.code == "magic_item_charge_retired"
    with pytest.raises(MagicItemError) as exc3:
        charges.register_item("item.charm.1", "magic.item.charm_of_soothing")
    assert exc3.value.code == "magic_item_charge_conflict"


def _item_service(env, owners, ratings):
    items = build_default_magic_items()
    charges = MagicItemChargeRegistry(items)
    service = MagicItemService(
        items, charges, env.catalog, env.engine, env.mana,
        owner_of=lambda item_id: owners.get(item_id),
        skill_rating=lambda caster, school: ratings.get((caster, school), 0),
    )
    return items, charges, service


def test_magic_023_charged_item_legality_equivalence():
    targets = {"r.b": {"scene_id": "scene.town", "position": {"x_wu": 10.0, "y_wu": 0.0}}}
    env = make_engine(targets=targets)
    env.mana.register_caster("r.a", 0)
    owners = {"item.charm.1": "r.a"}
    ratings = {}  # 持有者无任何学派技能
    items, charges, service = _item_service(env, owners, ratings)
    charges.register_item("item.charm.1", "magic.item.charm_of_soothing")
    # RULE-MAGIC-054：无同意证据时与本体施法同样 MAGIC_CONSENT_MISSING
    with pytest.raises(Exception) as exc:
        service.use_charged_item(
            "cmd.item.1", "item.charm.1", "r.a", "scene.town", 0, 0, env.engine.revision,
            target_refs=("r.b",),
        )
    assert exc.value.code == "MAGIC_CONSENT_MISSING"
    assert charges.charges_of("item.charm.1") == 5  # 失败不扣充能
    # 携带证据：与本体施法同判定（restricted_authorized），但跳过 Mana 与门槛
    # 法器路径无 authorization 参数位——经 SpellCastCommand 由服务构造时不带证据，
    # 这里验证跳过 Mana/门槛一侧：glowlight 法器无需学习无需 Mana
    owners["item.wand.1"] = "r.a"
    charges.register_item("item.wand.1", "magic.item.wand_of_glowlight")
    mana_before = env.mana.get("r.a").mana_current
    committed = service.use_charged_item(
        "cmd.item.2", "item.wand.1", "r.a", "scene.town", 0, 0, env.engine.revision,
    )
    assert committed.spell_id == "spell.arcane.glowlight"
    assert charges.charges_of("item.wand.1") == 9
    assert env.mana.get("r.a").mana_current == mana_before  # 不消耗 Mana
    assert env.learning.xp_event_count == 0  # 法器施放不授 XP
    # 幂等重放：同 command_id 不重复扣充能
    replay = service.use_charged_item(
        "cmd.item.2", "item.wand.1", "r.a", "scene.town", 0, 0, env.engine.revision,
    )
    assert replay is committed
    assert charges.charges_of("item.wand.1") == 9


def test_magic_023_not_held_and_empty_rejected():
    env = make_engine()
    env.mana.register_caster("r.a", 0)
    owners = {"item.wand.1": "r.someone_else"}
    items, charges, service = _item_service(env, owners, {})
    charges.register_item("item.wand.1", "magic.item.wand_of_glowlight")
    with pytest.raises(MagicItemError) as exc:
        service.use_charged_item(
            "cmd.item.h", "item.wand.1", "r.a", "scene.town", 0, 0, env.engine.revision,
        )
    assert exc.value.code == "MAGIC_ITEM_NOT_HELD"
    # 充能耗尽：法器保留为普通 Item，不可继续施放
    owners["item.wand.1"] = "r.a"
    for index in range(10):
        charges.use_charge("item.wand.1", f"evt.drain.{index}")
    with pytest.raises(MagicItemError) as exc2:
        service.use_charged_item(
            "cmd.item.e", "item.wand.1", "r.a", "scene.town", 0, 0, env.engine.revision,
        )
    assert exc2.value.code == "MAGIC_ITEM_NO_CHARGES"


def test_magic_023_recharge_long_action():
    env = make_engine()
    env.mana.register_caster("r.a", 0)  # mana 60
    owners = {"item.wand.1": "r.a"}
    ratings = {("r.a", "school.arcane"): 30}
    items, charges, service = _item_service(env, owners, ratings)
    charges.register_item("item.wand.1", "magic.item.wand_of_glowlight")
    charges.use_charge("item.wand.1", "evt.use.1")
    charges.use_charge("item.wand.1", "evt.use.2")
    # 技能门槛不足：rating 20 < 30
    low = make_engine()
    low.mana.register_caster("r.b", 0)
    _, low_charges, low_service = _item_service(low, {"item.wand.2": "r.b"}, {("r.b", "school.arcane"): 20})
    low_charges.register_item("item.wand.2", "magic.item.wand_of_glowlight")
    low_charges.use_charge("item.wand.2", "evt.use.x")
    with pytest.raises(MagicItemError) as exc:
        low_service.begin_recharge("cmd.re.low", "item.wand.2", "r.b")
    assert exc.value.code == "MAGIC_RECHARGE_PREREQUISITE_MISSING"
    # 正常回充：每检查点 15 Mana 换 1 点充能，逐点独立提交
    action = service.begin_recharge("cmd.re.1", "item.wand.1", "r.a")
    assert action["action_kind"] == "magic.recharge_item"
    state = service.recharge_checkpoint("cmd.re.1", "evt.re.1", 100)
    assert state == "in_progress"
    assert charges.charges_of("item.wand.1") == 9
    assert env.mana.get("r.a").mana_current == 45
    # 检查点幂等：同 source_event 重复提交不重复生效
    service.recharge_checkpoint("cmd.re.1", "evt.re.1", 100)
    assert charges.charges_of("item.wand.1") == 9
    assert env.mana.get("r.a").mana_current == 45
    # 回充中卖出：检查点重验持有权失败 → interrupted，已充点数留给新持有者
    owners["item.wand.1"] = "r.buyer"
    with pytest.raises(MagicItemError) as exc2:
        service.recharge_checkpoint("cmd.re.1", "evt.re.2", 200)
    assert exc2.value.code == "MAGIC_ITEM_NOT_HELD"
    assert service._recharges["cmd.re.1"]["state"] == "interrupted"
    assert charges.charges_of("item.wand.1") == 9  # 新持有者继承已充点数


def test_magic_023_trinket_modifiers_not_stacking():
    items = build_default_magic_items()
    pendant = items.get("magic.item.starweave_pendant")
    focus = items.get("magic.item.warding_focus")
    # RULE-MAGIC-056：同类饰物不叠加（取最大），不同类并存
    composed = compose_trinket_modifiers([pendant, pendant, focus])
    assert composed == {"starweave_tide_modifier": 100, "detect_radius_bonus": 32}
    # tide 加成夹取到 +100 q1000 上限
    boosted = decode_magic_item_definition({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.greater_pendant",
        "magic_item_kind": "passive_trinket",
        "bound_spell_id": None,
        "charges_max": None,
        "recharge_school_id": None,
        "teaches_spell_id": None,
        "passive_modifiers": [{"modifier_key": "starweave_tide_modifier", "value": 250}],
        "detectable": True,
    })
    assert compose_trinket_modifiers([boosted])["starweave_tide_modifier"] == 100

"""
魔法物品（DOC-MAGIC-010）

- REQ-MAGIC-019：magic_definition_id 解析到唯一定义；ECON 拥有所有权，MAGIC 拥有效果语义
- REQ-MAGIC-020：充能整数 0..charges_max（1..20），同 (item, event) 最多扣一次
- RULE-MAGIC-054：法器施放保留目标/射程/世界合法性检查，跳过 Mana 与技能门槛
- RULE-MAGIC-055：回充是长行动，每点 15 Mana 且对应学派 rating >= 30，无自动回充
- RULE-MAGIC-056：被动饰物只提供注册修正键，同类不叠加
- RULE-MAGIC-057：转移不重置充能；tombstone 同步 retired，不可复活
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .casting import CastingEngine, SpellCastCommand, SpellCastCommitted
from .constants import (
    ALLOWED_TRINKET_MODIFIERS,
    CHARGES_MAX_MAX,
    CHARGES_MAX_MIN,
    RECHARGE_MANA_PER_CHARGE,
    RECHARGE_MIN_SCHOOL_RATING,
    TRINKET_TIDE_BONUS_CAP_Q1000,
    ChargeState,
    MagicItemKind,
)
from .mana import CasterRegistry
from .schools import SchoolRegistry
from .spells import SpellCatalog


class MagicItemError(Exception):
    """魔法物品注册/使用失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


MAGIC_ITEM_DEFINITION_FIELDS = frozenset(
    {
        "magic_schema_version", "magic_definition_id", "magic_item_kind",
        "bound_spell_id", "charges_max", "recharge_school_id",
        "teaches_spell_id", "passive_modifiers", "detectable",
    }
)
_MODIFIER_FIELDS = frozenset({"modifier_key", "value"})


@dataclass(frozen=True)
class MagicItemDefinition:
    """DES-MAGIC-010 的不可变注册条；三分支字段互斥由 decode 保证"""

    magic_definition_id: str
    magic_item_kind: MagicItemKind
    bound_spell_id: Optional[str]
    charges_max: Optional[int]
    recharge_school_id: Optional[str]
    teaches_spell_id: Optional[str]
    passive_modifiers: Tuple[Dict, ...]
    detectable: bool
    magic_schema_version: int = 1


def decode_magic_item_definition(record: Dict) -> MagicItemDefinition:
    """三分支 strict 子 Schema：字段存在性按 magic_item_kind 互斥"""
    extra = set(record) - MAGIC_ITEM_DEFINITION_FIELDS
    if extra:
        raise MagicItemError("magic_item_schema_additional_property", f"extra: {sorted(extra)}")
    missing = {"magic_schema_version", "magic_definition_id", "magic_item_kind", "detectable"} - set(record)
    if missing:
        raise MagicItemError("magic_item_schema_missing_field", f"missing: {sorted(missing)}")
    try:
        kind = MagicItemKind(record["magic_item_kind"])
    except ValueError as exc:
        raise MagicItemError("magic_item_schema_invalid_enum", str(exc)) from exc
    bound = record.get("bound_spell_id")
    charges_max = record.get("charges_max")
    recharge_school = record.get("recharge_school_id")
    teaches = record.get("teaches_spell_id")
    modifiers = tuple(dict(m) for m in (record.get("passive_modifiers") or ()))
    if kind is MagicItemKind.CHARGED_SPELL_ITEM:
        if bound is None or charges_max is None or recharge_school is None:
            raise MagicItemError("magic_item_branch_invalid", "charged requires bound/charges/recharge_school")
        if teaches is not None or modifiers:
            raise MagicItemError("magic_item_branch_invalid", "charged forbids teaches/modifiers")
        if not (CHARGES_MAX_MIN <= charges_max <= CHARGES_MAX_MAX):
            raise MagicItemError("magic_item_charges_out_of_range", str(charges_max))
    elif kind is MagicItemKind.SPELLBOOK:
        if teaches is None:
            raise MagicItemError("magic_item_branch_invalid", "spellbook requires teaches_spell_id")
        if bound is not None or charges_max is not None or recharge_school is not None or modifiers:
            raise MagicItemError("magic_item_branch_invalid", "spellbook forbids charge/bound fields")
    else:  # PASSIVE_TRINKET
        if not modifiers:
            raise MagicItemError("magic_item_branch_invalid", "trinket requires passive_modifiers")
        if bound is not None or charges_max is not None or recharge_school is not None or teaches is not None:
            raise MagicItemError("magic_item_branch_invalid", "trinket forbids bound/teaches fields")
        for modifier in modifiers:
            if set(modifier) != _MODIFIER_FIELDS:
                raise MagicItemError("magic_item_branch_invalid", f"modifier fields: {sorted(modifier)}")
            if modifier["modifier_key"] not in ALLOWED_TRINKET_MODIFIERS:
                raise MagicItemError("magic_item_modifier_unknown", modifier["modifier_key"])
    return MagicItemDefinition(
        magic_definition_id=record["magic_definition_id"],
        magic_item_kind=kind,
        bound_spell_id=bound,
        charges_max=charges_max,
        recharge_school_id=recharge_school,
        teaches_spell_id=teaches,
        passive_modifiers=modifiers,
        detectable=bool(record["detectable"]),
        magic_schema_version=record["magic_schema_version"],
    )


class MagicItemRegistry:
    """magic_definition_id 的唯一解析点；未知 ID fail closed"""

    def __init__(self) -> None:
        self._definitions: Dict[str, MagicItemDefinition] = {}

    def register(self, record: Dict) -> MagicItemDefinition:
        definition = decode_magic_item_definition(record)
        if definition.magic_definition_id in self._definitions:
            raise MagicItemError("magic_item_registry_conflict", definition.magic_definition_id)
        self._definitions[definition.magic_definition_id] = definition
        return definition

    def get(self, magic_definition_id: str) -> MagicItemDefinition:
        definition = self._definitions.get(magic_definition_id)
        if definition is None:
            raise MagicItemError("MAGIC_ITEM_DEFINITION_UNKNOWN", magic_definition_id)
        return definition

    def __len__(self) -> int:
        return len(self._definitions)

    def all(self) -> List[MagicItemDefinition]:
        return list(self._definitions.values())


def audit_magic_item_definitions(
    registry: MagicItemRegistry,
    catalog: SpellCatalog,
    schools: SchoolRegistry,
) -> None:
    """构建期审计：绑定/教授法术与回充学派必须可解析，零孤儿"""
    for definition in registry.all():
        for spell_id in (definition.bound_spell_id, definition.teaches_spell_id):
            if spell_id is not None and spell_id not in catalog:
                raise MagicItemError("magic_item_reference_orphan", spell_id)
        if definition.recharge_school_id is not None:
            schools.get(definition.recharge_school_id)


def build_default_magic_items() -> MagicItemRegistry:
    """首版注册六件：2 充能法器 + 2 魔法书 + 2 被动饰物"""
    registry = MagicItemRegistry()
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.wand_of_glowlight",
        "magic_item_kind": "charged_spell_item",
        "bound_spell_id": "spell.arcane.glowlight",
        "charges_max": 10,
        "recharge_school_id": "school.arcane",
        "teaches_spell_id": None,
        "passive_modifiers": [],
        "detectable": True,
    })
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.charm_of_soothing",
        "magic_item_kind": "charged_spell_item",
        "bound_spell_id": "spell.spirit.soothe_spirit",
        "charges_max": 5,
        "recharge_school_id": "school.spirit",
        "teaches_spell_id": None,
        "passive_modifiers": [],
        "detectable": True,
    })
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.tome_of_minor_mend",
        "magic_item_kind": "spellbook",
        "bound_spell_id": None,
        "charges_max": None,
        "recharge_school_id": None,
        "teaches_spell_id": "spell.restoration.minor_mend",
        "passive_modifiers": [],
        "detectable": True,
    })
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.tome_of_detect_magic",
        "magic_item_kind": "spellbook",
        "bound_spell_id": None,
        "charges_max": None,
        "recharge_school_id": None,
        "teaches_spell_id": "spell.arcane.detect_magic",
        "passive_modifiers": [],
        "detectable": True,
    })
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.starweave_pendant",
        "magic_item_kind": "passive_trinket",
        "bound_spell_id": None,
        "charges_max": None,
        "recharge_school_id": None,
        "teaches_spell_id": None,
        "passive_modifiers": [{"modifier_key": "starweave_tide_modifier", "value": 100}],
        "detectable": True,
    })
    registry.register({
        "magic_schema_version": 1,
        "magic_definition_id": "magic.item.warding_focus",
        "magic_item_kind": "passive_trinket",
        "bound_spell_id": None,
        "charges_max": None,
        "recharge_school_id": None,
        "teaches_spell_id": None,
        "passive_modifiers": [{"modifier_key": "detect_radius_bonus", "value": 32}],
        "detectable": True,
    })
    return registry


def compose_trinket_modifiers(definitions: List[MagicItemDefinition]) -> Dict[str, int]:
    """RULE-MAGIC-056：同类饰物不叠加（取最大）；tide 加成夹取到 +100 q1000"""
    composed: Dict[str, int] = {}
    for definition in definitions:
        if definition.magic_item_kind is not MagicItemKind.PASSIVE_TRINKET:
            continue
        for modifier in definition.passive_modifiers:
            key = modifier["modifier_key"]
            composed[key] = max(composed.get(key, 0), int(modifier["value"]))
    if "starweave_tide_modifier" in composed:
        composed["starweave_tide_modifier"] = min(
            composed["starweave_tide_modifier"], TRINKET_TIDE_BONUS_CAP_Q1000
        )
    return composed


@dataclass
class MagicItemChargeState:
    """DES-MAGIC-010 的 per-item 充能状态；键为 ECON item_id"""

    item_id: str
    magic_definition_id: str
    charges_current: int
    state: ChargeState = ChargeState.ACTIVE
    last_recharge_game_time: Optional[int] = None
    charge_revision: int = 0
    charge_schema_version: int = 1


class MagicItemChargeRegistry:
    """充能状态聚合：幂等扣减、fail closed 读取、tombstone 同步 retired"""

    def __init__(self, item_registry: MagicItemRegistry) -> None:
        self._items = item_registry
        self._states: Dict[str, MagicItemChargeState] = {}
        self._use_events: Dict[Tuple[str, str], int] = {}
        self._recharge_events: set = set()

    def register_item(self, item_id: str, magic_definition_id: str) -> Optional[MagicItemChargeState]:
        """charged 物品建立满充状态；spellbook/trinket 无充能状态"""
        definition = self._items.get(magic_definition_id)
        if definition.magic_item_kind is not MagicItemKind.CHARGED_SPELL_ITEM:
            return None
        if item_id in self._states:
            raise MagicItemError("magic_item_charge_conflict", item_id)
        state = MagicItemChargeState(
            item_id=item_id,
            magic_definition_id=magic_definition_id,
            charges_current=definition.charges_max or 0,
        )
        self._states[item_id] = state
        return state

    def charges_of(self, item_id: str) -> int:
        """充能状态投影缺失时按 0 fail closed，禁止按满充猜测"""
        state = self._states.get(item_id)
        if state is None or state.state is ChargeState.RETIRED:
            return 0
        return state.charges_current

    def use_charge(self, item_id: str, source_event_id: str) -> int:
        """REQ-MAGIC-020：与效果事件同事务；同 (item, event) 最多扣一次"""
        key = (item_id, source_event_id)
        if key in self._use_events:
            return self._use_events[key]
        state = self._states.get(item_id)
        if state is not None and state.state is ChargeState.RETIRED:
            raise MagicItemError("magic_item_charge_retired", item_id)
        if state is None or state.charges_current <= 0:
            raise MagicItemError("MAGIC_ITEM_NO_CHARGES", item_id)
        state.charges_current -= 1
        state.charge_revision += 1
        self._use_events[key] = 1
        return 1

    def recharge_one(self, item_id: str, source_event_id: str, game_time: int) -> int:
        """RULE-MAGIC-055：逐点恢复；各检查点独立提交且幂等"""
        if source_event_id in self._recharge_events:
            return self.charges_of(item_id)
        state = self._states.get(item_id)
        if state is not None and state.state is ChargeState.RETIRED:
            raise MagicItemError("magic_item_charge_retired", item_id)
        if state is None:
            raise MagicItemError("magic_item_charge_unknown", item_id)
        definition = self._items.get(state.magic_definition_id)
        if state.charges_current >= (definition.charges_max or 0):
            raise MagicItemError("magic_item_charges_full", item_id)
        state.charges_current += 1
        state.last_recharge_game_time = game_time
        state.charge_revision += 1
        self._recharge_events.add(source_event_id)
        return state.charges_current

    def retire(self, item_id: str) -> None:
        """RULE-MAGIC-057：ECON tombstone 驱动；retired 是终态"""
        state = self._states.get(item_id)
        if state is None:
            return
        state.state = ChargeState.RETIRED
        state.charge_revision += 1


class MagicItemService:
    """use_object 与 magic.recharge_item 长行动的 MAGIC 侧入口"""

    def __init__(
        self,
        item_registry: MagicItemRegistry,
        charge_registry: MagicItemChargeRegistry,
        catalog: SpellCatalog,
        engine: CastingEngine,
        mana_registry: CasterRegistry,
        owner_of: Callable[[str], Optional[str]],
        skill_rating: Callable[[str, str], int],
    ) -> None:
        self._items = item_registry
        self._charges = charge_registry
        self._catalog = catalog
        self._engine = engine
        self._mana = mana_registry
        self._owner_of = owner_of
        self._skill_rating = skill_rating
        self._recharges: Dict[str, Dict] = {}

    def use_charged_item(
        self,
        command_id: str,
        item_id: str,
        holder_id: str,
        scene_id: str,
        game_time: int,
        game_day: int,
        expected_revision: int,
        target_refs: Tuple[str, ...] = (),
        aim_point: Optional[Dict] = None,
        caster_position: Optional[Dict] = None,
    ) -> SpellCastCommitted:
        """RULE-MAGIC-054：等同施放绑定法术，跳过 Mana/门槛，保留第 4、6、7 级"""
        state = self._charges._states.get(item_id)
        if state is None:
            raise MagicItemError("MAGIC_ITEM_DEFINITION_UNKNOWN", item_id)
        definition = self._items.get(state.magic_definition_id)
        if definition.magic_item_kind is not MagicItemKind.CHARGED_SPELL_ITEM:
            raise MagicItemError("magic_item_kind_not_castable", definition.magic_item_kind.value)
        if self._owner_of(item_id) != holder_id:
            # 提交按最新持有权重验（ECON current ownership）
            raise MagicItemError("MAGIC_ITEM_NOT_HELD", item_id)
        if state.state is ChargeState.RETIRED:
            raise MagicItemError("magic_item_charge_retired", item_id)
        if state.charges_current <= 0:
            raise MagicItemError("MAGIC_ITEM_NO_CHARGES", item_id)
        spell = self._catalog.get(definition.bound_spell_id or "")
        command = SpellCastCommand(
            command_id=command_id,
            world_id="world",
            expected_revision=expected_revision,
            caster_id=holder_id,
            spell_id=spell.spell_id,
            scene_id=scene_id,
            game_time=game_time,
            game_day=game_day,
            target_refs=target_refs,
            aim_point=aim_point,
            declared_purpose="utility",
            caster_position=caster_position or {"x_wu": 0.0, "y_wu": 0.0},
        )
        return self._engine.commit_item_cast(
            command, spell, lambda event_id: self._charges.use_charge(item_id, event_id)
        )

    def begin_recharge(
        self,
        command_id: str,
        item_id: str,
        caster_id: str,
    ) -> Dict:
        """RULE-MAGIC-055：回充是注册长行动；进入时校验持有与技能门槛"""
        if command_id in self._recharges:
            return self._recharges[command_id]
        state = self._charges._states.get(item_id)
        if state is None:
            raise MagicItemError("MAGIC_ITEM_DEFINITION_UNKNOWN", item_id)
        definition = self._items.get(state.magic_definition_id)
        if self._owner_of(item_id) != caster_id:
            raise MagicItemError("MAGIC_ITEM_NOT_HELD", item_id)
        if state.state is ChargeState.RETIRED:
            raise MagicItemError("magic_item_charge_retired", item_id)
        if state.charges_current >= (definition.charges_max or 0):
            raise MagicItemError("magic_item_charges_full", item_id)
        rating = self._skill_rating(caster_id, definition.recharge_school_id or "")
        if rating < RECHARGE_MIN_SCHOOL_RATING:
            raise MagicItemError("MAGIC_RECHARGE_PREREQUISITE_MISSING", f"rating {rating} < 30")
        action = {
            "long_action_id": generate_ulid(),
            "action_kind": "magic.recharge_item",
            "command_id": command_id,
            "item_id": item_id,
            "caster_id": caster_id,
            "charges_restored": 0,
            "state": "in_progress",
        }
        self._recharges[command_id] = action
        return action

    def recharge_checkpoint(
        self,
        command_id: str,
        source_event_id: str,
        game_time: int,
    ) -> str:
        """每检查点：重验持有权与门槛 → 消耗 15 Mana → 恢复 1 点充能"""
        action = self._recharges.get(command_id)
        if action is None or action["state"] != "in_progress":
            raise MagicItemError("magic_recharge_unknown", command_id)
        item_id = action["item_id"]
        caster_id = action["caster_id"]
        state = self._charges._states[item_id]
        definition = self._items.get(state.magic_definition_id)
        try:
            if self._owner_of(item_id) != caster_id:
                # 回充中 Item 被卖出：长行动中断，已充点数留在 Item 上
                raise MagicItemError("MAGIC_ITEM_NOT_HELD", item_id)
            rating = self._skill_rating(caster_id, definition.recharge_school_id or "")
            if rating < RECHARGE_MIN_SCHOOL_RATING:
                raise MagicItemError("MAGIC_RECHARGE_PREREQUISITE_MISSING", f"rating {rating} < 30")
            caster = self._mana.get(caster_id)
            self._mana.consume_mana(
                source_event_id, caster_id, RECHARGE_MANA_PER_CHARGE, caster.state_revision
            )
            self._charges.recharge_one(item_id, source_event_id, game_time)
        except MagicItemError:
            action["state"] = "interrupted"
            raise
        action["charges_restored"] += 1
        if self._charges.charges_of(item_id) >= (definition.charges_max or 0):
            action["state"] = "completed"
        return action["state"]

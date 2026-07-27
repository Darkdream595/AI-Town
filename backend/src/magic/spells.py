"""
法术数据模型（DOC-MAGIC-004）

- REQ-MAGIC-007：strict decoder 拒绝未列字段与未知枚举
- REQ-MAGIC-008：效果只能经注册 effect_bindings，无自由文本效果
- RULE-MAGIC-015/016：target_mode 组合约束与射程语义
- RULE-MAGIC-017：mana_cost/cooldown 范围；ritual 必须声明 work units
- RULE-MAGIC-021：首版 Catalog 恰好 12 条
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .constants import (
    COOLDOWN_MAX_GAME_MINUTES,
    MANA_COST_MAX,
    MANA_COST_MIN,
    STUDY_WORK_UNITS_MIN,
    STUDY_WORK_UNITS_PER_10_MANA,
    CastKind,
    LegalOverride,
    TargetMode,
)
from .schools import SchoolError, assert_no_teleport_semantics


class SpellError(Exception):
    """法术注册/目标校验失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


SPELL_DEFINITION_FIELDS = frozenset(
    {
        "schema_version", "spell_id", "school_id", "display_name_key",
        "cast_kind", "target_mode", "max_targets", "range_wu", "area_radius_wu",
        "mana_cost", "cooldown_game_minutes", "prerequisites", "legal_override",
        "consent_required", "effect_bindings", "presentation_id",
        "required_work_units",
    }
)
PREREQUISITE_FIELDS = frozenset(
    {
        "min_school_skill_rating", "required_ability_ids",
        "required_spell_ids", "required_item_tags",
    }
)
EFFECT_BINDING_FIELDS = frozenset({"effect_id", "parameters"})


@dataclass(frozen=True)
class SpellDefinition:
    """DES-MAGIC-004 的不可变 Catalog 条目"""

    spell_id: str
    school_id: str
    display_name_key: str
    cast_kind: CastKind
    target_mode: TargetMode
    max_targets: int
    range_wu: float
    area_radius_wu: float
    mana_cost: int
    cooldown_game_minutes: int
    prerequisites: Dict
    legal_override: LegalOverride
    consent_required: bool
    effect_bindings: Tuple[Dict, ...]
    presentation_id: str
    required_work_units: Optional[int] = None
    schema_version: int = 1


def _reject_teleport_naming(*texts: str) -> None:
    """Schema 层传送禁令统一以 SpellError 报出（四层反例的 Schema 层）"""
    try:
        assert_no_teleport_semantics(*texts)
    except SchoolError as exc:
        raise SpellError(exc.code, str(exc)) from exc


def decode_spell_definition(record: Dict) -> SpellDefinition:
    """REQ-MAGIC-007：strict decode；RULE-MAGIC-006：传送命名拒绝"""
    extra = set(record) - SPELL_DEFINITION_FIELDS
    if extra:
        raise SpellError("spell_schema_additional_property", f"extra: {sorted(extra)}")
    required = SPELL_DEFINITION_FIELDS - {"required_work_units"}
    missing = required - set(record)
    if missing:
        raise SpellError("spell_schema_missing_field", f"missing: {sorted(missing)}")
    _reject_teleport_naming(record["spell_id"])
    try:
        cast_kind = CastKind(record["cast_kind"])
        target_mode = TargetMode(record["target_mode"])
        legal_override = LegalOverride(record["legal_override"])
    except ValueError as exc:
        raise SpellError("spell_schema_invalid_enum", str(exc)) from exc
    if not (MANA_COST_MIN <= record["mana_cost"] <= MANA_COST_MAX):
        raise SpellError("spell_mana_cost_out_of_range", str(record["mana_cost"]))
    if not (0 <= record["cooldown_game_minutes"] <= COOLDOWN_MAX_GAME_MINUTES):
        raise SpellError("spell_cooldown_out_of_range", str(record["cooldown_game_minutes"]))
    prerequisites = record["prerequisites"]
    if not isinstance(prerequisites, dict) or set(prerequisites) != PREREQUISITE_FIELDS:
        raise SpellError("spell_prerequisite_invalid", f"fields: {sorted(prerequisites)}")
    bindings = record["effect_bindings"]
    if not bindings:
        raise SpellError("spell_effect_binding_missing", record["spell_id"])
    for binding in bindings:
        if set(binding) != EFFECT_BINDING_FIELDS:
            raise SpellError("spell_effect_binding_missing", f"fields: {sorted(binding)}")
        _reject_teleport_naming(binding["effect_id"])
    work_units = record["required_work_units"]
    if cast_kind is CastKind.RITUAL and work_units is None:
        raise SpellError("spell_ritual_work_units_missing", record["spell_id"])
    if cast_kind is CastKind.INSTANT and work_units is not None:
        raise SpellError("spell_instant_work_units_forbidden", record["spell_id"])
    return SpellDefinition(
        spell_id=record["spell_id"],
        school_id=record["school_id"],
        display_name_key=record["display_name_key"],
        cast_kind=cast_kind,
        target_mode=target_mode,
        max_targets=record["max_targets"],
        range_wu=float(record["range_wu"]),
        area_radius_wu=float(record["area_radius_wu"]),
        mana_cost=record["mana_cost"],
        cooldown_game_minutes=record["cooldown_game_minutes"],
        prerequisites=dict(prerequisites),
        legal_override=legal_override,
        consent_required=bool(record["consent_required"]),
        effect_bindings=tuple(dict(b) for b in bindings),
        presentation_id=record["presentation_id"],
        required_work_units=work_units,
        schema_version=record["schema_version"],
    )


class SpellCatalog:
    """不可变 Catalog，按 spell_id O(1) 索引；未知 ID fail closed"""

    def __init__(self) -> None:
        self._spells: Dict[str, SpellDefinition] = {}

    def register(self, record: Dict) -> SpellDefinition:
        spell = decode_spell_definition(record)
        if spell.spell_id in self._spells:
            raise SpellError("spell_registry_conflict", spell.spell_id)
        self._spells[spell.spell_id] = spell
        return spell

    def get(self, spell_id: str) -> SpellDefinition:
        spell = self._spells.get(spell_id)
        if spell is None:
            raise SpellError("MAGIC_SPELL_UNKNOWN", spell_id)
        return spell

    def __contains__(self, spell_id: str) -> bool:
        return spell_id in self._spells

    def __len__(self) -> int:
        return len(self._spells)

    def all(self) -> List[SpellDefinition]:
        return list(self._spells.values())


def validate_target_arguments(
    spell: SpellDefinition,
    target_refs: List[str],
    aim_point: Optional[Dict],
) -> None:
    """RULE-MAGIC-015：target_mode 与提案参数的合法组合"""
    mode = spell.target_mode
    if mode in (TargetMode.SELF, TargetMode.NONE, TargetMode.AREA_AROUND_CASTER):
        if target_refs or aim_point is not None:
            raise SpellError("MAGIC_TARGET_INVALID", f"{mode.value} requires empty targets")
    elif mode is TargetMode.SINGLE_ENTITY:
        if len(target_refs) != 1 or aim_point is not None:
            raise SpellError("MAGIC_TARGET_INVALID", "single_entity requires exactly 1 target")
    elif mode is TargetMode.MULTI_ENTITY:
        limit = min(spell.max_targets, 8)  # cast_spell_parameters maxItems: 8
        if not (1 <= len(target_refs) <= limit) or aim_point is not None:
            raise SpellError("MAGIC_TARGET_INVALID", f"multi_entity requires 1..{limit} targets")
    elif mode is TargetMode.GROUND_POINT:
        if aim_point is None or target_refs:
            raise SpellError("MAGIC_TARGET_INVALID", "ground_point requires aim_point only")


def study_work_units_for(spell: SpellDefinition) -> int:
    """RULE-MAGIC-031：mana_cost 每 10 点 2 work units，最少 4"""
    return max(STUDY_WORK_UNITS_MIN, (spell.mana_cost // 10) * STUDY_WORK_UNITS_PER_10_MANA)


def _spell_record(
    spell_id: str,
    school_id: str,
    cast_kind: str,
    target_mode: str,
    mana_cost: int,
    effect_id: str,
    parameters: Dict,
    *,
    max_targets: int = 1,
    range_wu: float = 96.0,
    area_radius_wu: float = 0.0,
    cooldown: int = 0,
    min_skill: int = 0,
    legal_override: str = "inherit",
    consent_required: bool = False,
    required_work_units: Optional[int] = None,
) -> Dict:
    return {
        "schema_version": 1,
        "spell_id": spell_id,
        "school_id": school_id,
        "display_name_key": f"{spell_id}.name",
        "cast_kind": cast_kind,
        "target_mode": target_mode,
        "max_targets": max_targets,
        "range_wu": range_wu,
        "area_radius_wu": area_radius_wu,
        "mana_cost": mana_cost,
        "cooldown_game_minutes": cooldown,
        "prerequisites": {
            "min_school_skill_rating": min_skill,
            "required_ability_ids": [],
            "required_spell_ids": [],
            "required_item_tags": [],
        },
        "legal_override": legal_override,
        "consent_required": consent_required,
        "effect_bindings": [{"effect_id": effect_id, "parameters": parameters}],
        "presentation_id": f"magic.presentation.{spell_id.split('.', 1)[1]}",
        "required_work_units": required_work_units,
    }


def build_default_spell_catalog() -> SpellCatalog:
    """RULE-MAGIC-021：首版恰好 12 条；ley_anchor/reinforce 为 ritual"""
    catalog = SpellCatalog()
    catalog.register(_spell_record(
        "spell.elemental.kindle_flame", "school.elemental", "instant", "ground_point",
        8, "magic.effect.ignite", {"ignite_strength": 1},
    ))
    catalog.register(_spell_record(
        "spell.elemental.douse", "school.elemental", "instant", "ground_point",
        8, "magic.effect.extinguish", {},
    ))
    catalog.register(_spell_record(
        "spell.restoration.minor_mend", "school.restoration", "instant", "single_entity",
        12, "magic.effect.heal_minor", {"heal_base": 6, "skill_scale_per_25_rating": 2},
        cooldown=30, min_skill=20, consent_required=True,
    ))
    catalog.register(_spell_record(
        "spell.restoration.cleanse_ailment", "school.restoration", "instant", "single_entity",
        20, "magic.effect.cure_illness", {},
        min_skill=30, consent_required=True,
    ))
    catalog.register(_spell_record(
        "spell.warding.purify_ground", "school.warding", "instant", "ground_point",
        30, "magic.effect.purify_anomaly", {"purify_progress": 25},
        min_skill=40,
    ))
    catalog.register(_spell_record(
        "spell.warding.reinforce_structure", "school.warding", "ritual", "single_entity",
        25, "magic.effect.reinforce_structure",
        {"decay_reduction_bps": 5000, "duration_game_minutes": 1440},
        min_skill=35, required_work_units=4,
    ))
    catalog.register(_spell_record(
        "spell.warding.ley_anchor", "school.warding", "ritual", "ground_point",
        40, "magic.effect.place_ley_anchor",
        {"radius_wu": 128.0, "ley_anchor_bonus_q1000": 100, "duration_game_minutes": 10080},
        min_skill=50, required_work_units=6,
    ))
    catalog.register(_spell_record(
        "spell.arcane.detect_magic", "school.arcane", "instant", "area_around_caster",
        10, "magic.effect.detect_magic", {},
        area_radius_wu=64.0,
    ))
    catalog.register(_spell_record(
        "spell.arcane.glowlight", "school.arcane", "instant", "self",
        5, "magic.effect.conjure_light",
        {"light_radius_wu": 32.0, "duration_game_minutes": 720},
    ))
    catalog.register(_spell_record(
        "spell.illusion.minor_veil", "school.illusion", "instant", "ground_point",
        15, "magic.effect.veil_illusion",
        {"veil_radius_wu": 16.0, "duration_game_minutes": 720},
        min_skill=25,
    ))
    catalog.register(_spell_record(
        "spell.spirit.soothe_spirit", "school.spirit", "instant", "single_entity",
        18, "magic.effect.soothe_spirit", {"soothe_strength": 1},
        min_skill=30, consent_required=True,
    ))
    catalog.register(_spell_record(
        "spell.spirit.hex_of_weariness", "school.spirit", "instant", "single_entity",
        35, "magic.effect.curse_weariness", {"duration_game_minutes": 1440},
        cooldown=60, min_skill=45, legal_override="restricted", consent_required=True,
    ))
    return catalog

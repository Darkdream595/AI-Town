"""
魔法学派（DOC-MAGIC-002）

- REQ-MAGIC-003：学派集合固定六个，增删需版本化 Registry 变更
- REQ-MAGIC-004：每个 SpellDefinition 恰好一个 school_id
- RULE-MAGIC-006：首版禁止任何传送语义
- RULE-MAGIC-007：归属冲突仲裁顺序固定，效果描述不决定学派
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .constants import SourceKind


class SchoolError(Exception):
    """学派注册/仲裁失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class SchoolDefinition:
    """DES-MAGIC-002 的不可变注册条"""

    school_id: str
    display_name_zh: str
    scope_tags: frozenset
    default_legal_baseline: str  # permitted / restricted / prohibited
    vfx_family: str
    learning_source_kinds: Tuple[SourceKind, ...]


SCHOOL_IDS = (
    "school.elemental",
    "school.restoration",
    "school.warding",
    "school.illusion",
    "school.spirit",
    "school.arcane",
)


class SchoolRegistry:
    """构建期不可变 Catalog，按 ID O(1) 查找；未知 ID fail closed"""

    def __init__(self) -> None:
        self._schools: Dict[str, SchoolDefinition] = {}

    def register(self, school: SchoolDefinition) -> None:
        if school.school_id in self._schools:
            raise SchoolError("magic_school_registry_conflict", school.school_id)
        self._schools[school.school_id] = school

    def get(self, school_id: str) -> SchoolDefinition:
        school = self._schools.get(school_id)
        if school is None:
            # 运行时遇到未知学派一律 fail closed
            raise SchoolError("FORBIDDEN", f"unknown school {school_id}")
        return school

    def __len__(self) -> int:
        return len(self._schools)


def build_default_schools() -> SchoolRegistry:
    """REQ-MAGIC-003：恰好六个学派，ID 与中文名固定"""
    registry = SchoolRegistry()
    registry.register(SchoolDefinition(
        school_id="school.elemental",
        display_name_zh="元素",
        scope_tags=frozenset({"matter"}),
        default_legal_baseline="permitted",
        vfx_family="vfx.elemental",
        learning_source_kinds=(SourceKind.TEACHER, SourceKind.PRACTICE),
    ))
    registry.register(SchoolDefinition(
        school_id="school.restoration",
        display_name_zh="疗愈",
        scope_tags=frozenset({"creature_state"}),
        default_legal_baseline="permitted",
        vfx_family="vfx.restoration",
        learning_source_kinds=(SourceKind.TEACHER, SourceKind.SPELLBOOK, SourceKind.PRACTICE),
    ))
    registry.register(SchoolDefinition(
        school_id="school.warding",
        display_name_zh="护壁",
        scope_tags=frozenset({"protection"}),
        default_legal_baseline="permitted",
        vfx_family="vfx.warding",
        learning_source_kinds=(SourceKind.TEACHER, SourceKind.SPELLBOOK),
    ))
    registry.register(SchoolDefinition(
        school_id="school.illusion",
        display_name_zh="幻术",
        scope_tags=frozenset({"perception"}),
        default_legal_baseline="restricted",
        vfx_family="vfx.illusion",
        learning_source_kinds=(SourceKind.TEACHER, SourceKind.SPELLBOOK),
    ))
    registry.register(SchoolDefinition(
        school_id="school.spirit",
        display_name_zh="通灵",
        scope_tags=frozenset({"spirit"}),
        default_legal_baseline="restricted",
        vfx_family="vfx.spirit",
        learning_source_kinds=(SourceKind.TEACHER,),
    ))
    registry.register(SchoolDefinition(
        school_id="school.arcane",
        display_name_zh="奥术",
        scope_tags=frozenset({"programmatic"}),
        default_legal_baseline="permitted",
        vfx_family="vfx.arcane",
        learning_source_kinds=(SourceKind.TEACHER, SourceKind.SPELLBOOK, SourceKind.PRACTICE),
    ))
    return registry


#: RULE-MAGIC-007 仲裁输入的效果类别封闭集
class EffectCategory:
    HP_CHANGE = "hp_change"
    FIRE_OR_MATTER = "fire_or_matter"
    PERCEPTION = "perception"
    OTHER = "other"


def arbitrate_school(effect_category: str, declared_school_id: str) -> str:
    """RULE-MAGIC-007：归属冲突仲裁；不允许效果描述决定学派之外的归属"""
    if effect_category == EffectCategory.HP_CHANGE:
        return "school.restoration"
    if effect_category == EffectCategory.FIRE_OR_MATTER:
        return "school.elemental"
    if effect_category == EffectCategory.PERCEPTION:
        return "school.illusion"
    return declared_school_id


def lint_school_scope(school: SchoolDefinition, effect_category: str) -> None:
    """构建期 lint：声明学派的作用域必须覆盖效果类别"""
    expected = arbitrate_school(effect_category, school.school_id)
    if expected != school.school_id:
        raise SchoolError(
            "magic_school_scope_mismatch",
            f"{effect_category} must belong to {expected}, not {school.school_id}",
        )


def assert_no_teleport_semantics(*texts: str) -> None:
    """RULE-MAGIC-006：命名层传送禁令（Schema/Registry 共用的静态检查）"""
    for text in texts:
        normalized = text.lower()
        if "teleport" in normalized or "blink" in normalized:
            raise SchoolError("magic_teleport_forbidden", text)

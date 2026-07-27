"""
魔法 VFX 与音频（DOC-MAGIC-011）

- REQ-MAGIC-021：presentation_id 声明的 vfx 必须属学派 vfx_family 前缀，构建期校验
- REQ-MAGIC-022：表现只驱动已提交事件的 render projection，规则层不读表现状态
- RULE-MAGIC-061：降级链固定 注册项 → 学派家族默认 → vfx.fallback.status_ping
- RULE-MAGIC-062：幻象识破标记只对已识破观察者可见
- RULE-MAGIC-063：已发布 presentation_id 的替换走版本化新增，旧 ID 仍可解析
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

from .schools import SchoolRegistry
from .spells import SpellCatalog


class PresentationError(Exception):
    """表现注册/解析失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


PRESENTATION_FIELDS = frozenset(
    {
        "presentation_schema_version", "presentation_id",
        "cast_vfx_id", "impact_vfx_id", "cast_audio_id",
        "loop_vfx_id", "reduced_motion_icon", "duration_ms",
    }
)

#: RULE-MAGIC-059：单法术 VFX duration_ms 遵守 RENDER 的 100..1500 界限
VFX_DURATION_MS_MIN = 100
VFX_DURATION_MS_MAX = 1500

FALLBACK_VFX_ID = "vfx.fallback.status_ping"


@dataclass(frozen=True)
class MagicPresentation:
    """DES-MAGIC-011 的不可变表现注册项"""

    presentation_id: str
    cast_vfx_id: str
    impact_vfx_id: str
    cast_audio_id: Optional[str]
    loop_vfx_id: Optional[str]
    reduced_motion_icon: str
    duration_ms: int = 600
    presentation_schema_version: int = 1


def decode_presentation(record: Dict) -> MagicPresentation:
    extra = set(record) - PRESENTATION_FIELDS
    if extra:
        raise PresentationError("magic_presentation_additional_property", f"extra: {sorted(extra)}")
    missing = PRESENTATION_FIELDS - {"loop_vfx_id", "duration_ms"} - set(record)
    if missing:
        raise PresentationError("magic_presentation_missing_field", f"missing: {sorted(missing)}")
    duration = int(record.get("duration_ms", 600))
    if not (VFX_DURATION_MS_MIN <= duration <= VFX_DURATION_MS_MAX):
        # RULE-MAGIC-059：超界表现不注册
        raise PresentationError("magic_presentation_duration_out_of_range", str(duration))
    return MagicPresentation(
        presentation_id=record["presentation_id"],
        cast_vfx_id=record["cast_vfx_id"],
        impact_vfx_id=record["impact_vfx_id"],
        cast_audio_id=record.get("cast_audio_id"),
        loop_vfx_id=record.get("loop_vfx_id"),
        reduced_motion_icon=record["reduced_motion_icon"],
        duration_ms=duration,
        presentation_schema_version=record["presentation_schema_version"],
    )


class PresentationRegistry:
    """构建期不可变、按 ID 索引；版本化替换保持旧 ID 可解析"""

    def __init__(self, schools: SchoolRegistry) -> None:
        self._schools = schools
        self._entries: Dict[str, MagicPresentation] = {}
        self._school_by_presentation: Dict[str, str] = {}
        self._superseded: Dict[str, str] = {}  # old_id -> new_id
        self._diagnosed: Set[str] = set()

    def register(self, record: Dict, school_id: str) -> MagicPresentation:
        """REQ-MAGIC-021：vfx 必须落在学派家族前缀内（构建期审计）"""
        entry = decode_presentation(record)
        if entry.presentation_id in self._entries:
            raise PresentationError("magic_presentation_conflict", entry.presentation_id)
        family = self._schools.get(school_id).vfx_family
        for vfx_id in (entry.cast_vfx_id, entry.impact_vfx_id, entry.loop_vfx_id):
            if vfx_id is not None and not vfx_id.startswith(f"{family}."):
                raise PresentationError(
                    "magic_presentation_family_mismatch",
                    f"{vfx_id} not in {family}.*",
                )
        self._entries[entry.presentation_id] = entry
        self._school_by_presentation[entry.presentation_id] = school_id
        return entry

    def register_versioned(self, record: Dict, school_id: str, supersedes: str) -> MagicPresentation:
        """RULE-MAGIC-063：只增不改语义；旧 ID 经版本链解析到新条目"""
        if supersedes not in self._entries:
            raise PresentationError("magic_presentation_unknown", supersedes)
        entry = self.register(record, school_id)
        self._superseded[supersedes] = entry.presentation_id
        return entry

    def get(self, presentation_id: str) -> MagicPresentation:
        entry = self._entries.get(presentation_id)
        if entry is None:
            raise PresentationError("magic_presentation_unknown", presentation_id)
        return entry

    def resolve_with_fallback(
        self,
        presentation_id: str,
        school_id: str,
        asset_available: Optional[Callable[[str], bool]] = None,
    ) -> Dict:
        """RULE-MAGIC-061：注册项 → 家族默认 → 全局 fallback；音频缺失静默跳过

        asset_available 模拟 RENDER 资产缺失；默认全部可用。
        同一 presentation_id 的降级诊断只报一次，不刷屏。
        """
        available = asset_available or (lambda _asset_id: True)
        resolved_id = self._superseded.get(presentation_id, presentation_id)
        entry = self._entries.get(resolved_id)
        diagnostic: Optional[str] = None
        fallback_level = 0
        if entry is not None and available(entry.cast_vfx_id):
            cast_vfx, impact_vfx = entry.cast_vfx_id, entry.impact_vfx_id
            audio = entry.cast_audio_id if available(entry.cast_audio_id or "") else None
        else:
            family = self._schools.get(school_id).vfx_family
            family_default = f"{family}.family_default"
            if presentation_id not in self._diagnosed:
                self._diagnosed.add(presentation_id)
                diagnostic = f"presentation {presentation_id} unresolved; fallback applied"
            if available(family_default):
                fallback_level = 1
                cast_vfx = impact_vfx = family_default
            else:
                fallback_level = 2
                cast_vfx = impact_vfx = FALLBACK_VFX_ID
            audio = None
        return {
            "presentation_id_requested": presentation_id,
            "presentation_id_resolved": resolved_id if entry is not None else None,
            "cast_vfx_id": cast_vfx,
            "impact_vfx_id": impact_vfx,
            "cast_audio_id": audio,  # None 时音频静默跳过
            "fallback_level": fallback_level,
            "diagnostic": diagnostic,
        }

    def __len__(self) -> int:
        return len(self._entries)


def build_default_presentations(
    catalog: SpellCatalog,
    schools: SchoolRegistry,
) -> PresentationRegistry:
    """12 条法术的表现注册；持续效果法术带 loop 表现（RULE-MAGIC-060）"""
    registry = PresentationRegistry(schools)
    for spell in catalog.all():
        family = schools.get(spell.school_id).vfx_family
        short = spell.spell_id.split(".")[-1]
        has_loop = any(
            b["effect_id"] in (
                "magic.effect.place_ley_anchor",
                "magic.effect.conjure_light",
                "magic.effect.veil_illusion",
                "magic.effect.reinforce_structure",
            )
            for b in spell.effect_bindings
        )
        registry.register(
            {
                "presentation_schema_version": 1,
                "presentation_id": spell.presentation_id,
                "cast_vfx_id": f"{family}.{short}_cast",
                "impact_vfx_id": f"{family}.{short}_impact",
                "cast_audio_id": f"audio.sfx.magic.{spell.school_id.split('.')[-1]}_{short}",
                "loop_vfx_id": f"{family}.{short}_loop" if has_loop else None,
                "reduced_motion_icon": f"icon.magic.{spell.school_id.split('.')[-1]}",
            },
            spell.school_id,
        )
    return registry


def audit_presentation_closure(
    catalog: SpellCatalog,
    registry: PresentationRegistry,
) -> None:
    """验收口径：12 条法术的 presentation_id 全部解析成功、前缀零违例"""
    for spell in catalog.all():
        resolved = registry.resolve_with_fallback(spell.presentation_id, spell.school_id)
        if resolved["fallback_level"] != 0:
            raise PresentationError("magic_presentation_unknown", spell.presentation_id)


def illusion_projection_for_observer(effect_instance_id: str, observer_revealed: bool) -> Dict:
    """RULE-MAGIC-062：未识破观察者看不到幻象标记，与真实物体同层渲染"""
    projection: Dict = {
        "effect_instance_id": effect_instance_id,
        "render_kind": "world_object",
    }
    if observer_revealed:
        # 识破后叠加标记；未识破者不泄露
        projection["illusion_revealed_marker"] = True
    return projection

"""
魔法世界观（DOC-MAGIC-001）

- REQ-MAGIC-001：星织潮是唯一环境魔力来源，禁止第二机制来源
- RULE-MAGIC-001：世界观解释不授予绕过 SpellDefinition 的能力
- RULE-MAGIC-004：灰脉灾变等 Canon 历史事实不可被施法改写
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .constants import ALLOWED_MECHANICAL_HOOKS


class CosmologyError(Exception):
    """世界观注册/Canon 校验失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class CosmologyEntry:
    """DES-MAGIC-001 的不可变注册条"""

    cosmology_id: str
    public_summary: str
    belief_variants: Tuple[str, ...]
    mechanical_hooks: Tuple[str, ...]


class CosmologyRegistry:
    """构建期不可变 Catalog；首版恰好三条"""

    def __init__(self) -> None:
        self._entries: Dict[str, CosmologyEntry] = {}

    def register(self, entry: CosmologyEntry) -> None:
        unknown_hooks = set(entry.mechanical_hooks) - ALLOWED_MECHANICAL_HOOKS
        if unknown_hooks:
            # REQ-MAGIC-001：第二机制来源不得入库
            raise CosmologyError(
                "WORLD_CANON_CONFLICT", f"unregistered hooks: {sorted(unknown_hooks)}"
            )
        if entry.cosmology_id in self._entries:
            raise CosmologyError("WORLD_CANON_CONFLICT", f"duplicate {entry.cosmology_id}")
        self._entries[entry.cosmology_id] = entry

    def get(self, cosmology_id: str) -> CosmologyEntry:
        entry = self._entries.get(cosmology_id)
        if entry is None:
            raise CosmologyError("WORLD_CANON_CONFLICT", cosmology_id)
        return entry

    def all_hooks(self) -> frozenset:
        hooks: set = set()
        for entry in self._entries.values():
            hooks.update(entry.mechanical_hooks)
        return frozenset(hooks)


def build_default_cosmology() -> CosmologyRegistry:
    """DOC-MAGIC-001 §5：首版注册三条，随机世界初始化不得改变"""
    registry = CosmologyRegistry()
    registry.register(CosmologyEntry(
        cosmology_id="magic.cosmology.starweave_tide",
        public_summary="星织潮是周期波动的环境魔力场，是全部魔法的世界观基座。",
        belief_variants=("tide_as_breathing", "tide_as_woven_river"),
        mechanical_hooks=("starweave_tide_modifier", "ley_anchor_presence"),
    ))
    registry.register(CosmologyEntry(
        cosmology_id="magic.cosmology.silver_ash_legacy",
        public_summary="银烬坠落与灰脉灾变留下的已登记历史事实与局部污染。",
        belief_variants=("ash_as_warning", "ash_as_grief"),
        mechanical_hooks=(),
    ))
    registry.register(CosmologyEntry(
        cosmology_id="magic.cosmology.spirit_pacts",
        public_summary="灵体交互遵守独立的 Reservation 与同意规则。",
        belief_variants=("spirits_as_ancestors", "spirits_as_echoes"),
        mechanical_hooks=(),
    ))
    return registry

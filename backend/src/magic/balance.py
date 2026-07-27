"""
魔法平衡与测试（DOC-MAGIC-012）

- REQ-MAGIC-023：平衡包络为构建期硬校验
- REQ-MAGIC-024：传送禁令在 Schema/Registry/提案/handler 四层注入全部拒绝
- RULE-MAGIC-065：治疗日上限按 (target, game_day) 分账，双账合并审计
- RULE-MAGIC-066：平衡参数集中在版本化 magic.balance.v1，运行时不可热改
- RULE-MAGIC-068：语料审计任一失败阻断合入
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .constants import (
    CHARGES_MAX_MAX,
    CHARGES_MAX_MIN,
    COOLDOWN_MAX_GAME_MINUTES,
    DAILY_INSTANT_CAST_BUDGET,
    HEAL_DAILY_CAP_BPS,
    MANA_COST_MAX,
    MANA_COST_MIN,
    REGEN_INCREMENT_MAX,
    SCENE_EFFECT_INSTANCE_CAP,
)
from .effects import EFFECT_IDS
from .items import MagicItemRegistry
from .schools import assert_no_teleport_semantics
from .spells import SpellCatalog


class BalanceError(Exception):
    """包络/审计失败；code 为稳定断言名"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class MagicBalanceConfig:
    """RULE-MAGIC-066：版本化平衡参数 Catalog；历史结算不受新参数追溯"""

    config_version: str
    mana_cost_min: int
    mana_cost_max: int
    charges_max_min: int
    charges_max_max: int
    regen_increment_max: int
    heal_daily_cap_bps: int
    daily_instant_cast_budget: int
    scene_effect_instance_cap: int
    cooldown_max_game_minutes: int


#: 首版唯一平衡配置；调整走文档版本变更
BALANCE_V1 = MagicBalanceConfig(
    config_version="magic.balance.v1",
    mana_cost_min=MANA_COST_MIN,
    mana_cost_max=MANA_COST_MAX,
    charges_max_min=CHARGES_MAX_MIN,
    charges_max_max=CHARGES_MAX_MAX,
    regen_increment_max=REGEN_INCREMENT_MAX,
    heal_daily_cap_bps=HEAL_DAILY_CAP_BPS,
    daily_instant_cast_budget=DAILY_INSTANT_CAST_BUDGET,
    scene_effect_instance_cap=SCENE_EFFECT_INSTANCE_CAP,
    cooldown_max_game_minutes=COOLDOWN_MAX_GAME_MINUTES,
)


def audit_catalog_envelope(catalog: SpellCatalog, config: MagicBalanceConfig = BALANCE_V1) -> None:
    """REQ-MAGIC-023：catalog 构建期包络校验；越界即构建失败"""
    for spell in catalog.all():
        if not (config.mana_cost_min <= spell.mana_cost <= config.mana_cost_max):
            raise BalanceError("magic_balance_envelope_violation", f"{spell.spell_id} mana_cost")
        if spell.cooldown_game_minutes > config.cooldown_max_game_minutes:
            raise BalanceError("magic_balance_envelope_violation", f"{spell.spell_id} cooldown")


def audit_item_envelope(registry: MagicItemRegistry, config: MagicBalanceConfig = BALANCE_V1) -> None:
    for definition in registry.all():
        if definition.charges_max is not None and not (
            config.charges_max_min <= definition.charges_max <= config.charges_max_max
        ):
            raise BalanceError(
                "magic_balance_envelope_violation", f"{definition.magic_definition_id} charges_max"
            )


def lint_no_teleport(catalog: SpellCatalog) -> None:
    """REQ-MAGIC-024 Registry 层：全量命名静态检查"""
    for spell in catalog.all():
        assert_no_teleport_semantics(spell.spell_id, spell.presentation_id)
        for binding in spell.effect_bindings:
            assert_no_teleport_semantics(binding["effect_id"])
    assert_no_teleport_semantics(*EFFECT_IDS)


#: REQ-MAGIC-024 handler 层静态证明：每个 handler 调用的 owner 端口方法封闭枚举，
#: 与一切位移能力（set_position/move_entity/teleport）天然不相交
EFFECT_PORT_CALLS: Dict[str, frozenset] = {
    "magic.effect.ignite": frozenset({"flammable_state", "ignite"}),
    "magic.effect.extinguish": frozenset({"flammable_state", "extinguish"}),
    "magic.effect.heal_minor": frozenset({"hp_state", "apply_health_effect"}),
    "magic.effect.cure_illness": frozenset({"cure_illness"}),
    "magic.effect.purify_anomaly": frozenset({"purify_anomaly"}),
    "magic.effect.reinforce_structure": frozenset({"reinforce_structure"}),
    "magic.effect.place_ley_anchor": frozenset({"create"}),
    "magic.effect.detect_magic": frozenset({"detectable_facts", "record_observation"}),
    "magic.effect.conjure_light": frozenset({"create"}),
    "magic.effect.veil_illusion": frozenset({"create"}),
    "magic.effect.soothe_spirit": frozenset({"soothe_spirit"}),
    "magic.effect.curse_weariness": frozenset({"apply_illness"}),
}

DISPLACEMENT_CAPABILITIES = frozenset({"set_position", "move_entity", "teleport", "relocate"})


def audit_handler_no_displacement() -> None:
    """静态证明：无任何 handler 具备位移能力"""
    for effect_id, calls in EFFECT_PORT_CALLS.items():
        overlap = calls & DISPLACEMENT_CAPABILITIES
        if overlap:
            raise BalanceError("magic_handler_displacement_found", f"{effect_id}: {sorted(overlap)}")
    if set(EFFECT_PORT_CALLS) != set(EFFECT_IDS):
        raise BalanceError("magic_handler_table_drift", "port call table must cover all handlers")


#: RULE-MAGIC-064：魔法对经济物质影响的注册通道（其余一律禁止）
ECONOMY_IMPACT_CHANNELS = frozenset(
    {"item_charge_usage", "maintenance_cost_reduction", "potion_demand_substitution"}
)


@dataclass
class MagicSimulationObservation:
    """RULE-MAGIC-067：1/7/30 日模拟的魔法活动抽样（按日聚合）"""

    seed: int
    game_days: int
    instant_casts_per_caster_day: List[Tuple[str, int, int]] = field(default_factory=list)
    mana_spent_total: int = 0
    mana_regenerated_total: int = 0
    heal_per_target_day: List[Tuple[str, int, int]] = field(default_factory=list)
    peak_scene_effect_instances: int = 0
    item_created_by_magic: int = 0
    currency_created_by_magic: int = 0


def check_magic_envelope(
    observation: MagicSimulationObservation,
    hp_max_by_target: Dict[str, int],
    config: MagicBalanceConfig = BALANCE_V1,
) -> List[str]:
    """包络断言；返回违例列表，空列表即通过（零施法世界按无活动通过）"""
    violations: List[str] = []
    for caster_id, game_day, count in observation.instant_casts_per_caster_day:
        if count > config.daily_instant_cast_budget:
            violations.append(f"cast_budget {caster_id} day{game_day}: {count}")
    if observation.peak_scene_effect_instances > config.scene_effect_instance_cap:
        violations.append(f"scene_instances {observation.peak_scene_effect_instances}")
    for target_id, game_day, amount in observation.heal_per_target_day:
        hp_max = hp_max_by_target.get(target_id, 0)
        if amount > hp_max * config.heal_daily_cap_bps // 10000:
            violations.append(f"heal_cap {target_id} day{game_day}: {amount}")
    if observation.mana_spent_total < 0 or observation.mana_regenerated_total < 0:
        violations.append("mana_flow_negative")
    # RULE-MAGIC-064：效果 handler 不得产出 Item 或货币
    if observation.item_created_by_magic > 0:
        violations.append("magic_created_item")
    if observation.currency_created_by_magic > 0:
        violations.append("magic_created_currency")
    return violations


_DOC_ID_RE = re.compile(r"(?m)^doc_id:\s*(DOC-MAGIC-\d{3})$")
_RULE_RE = re.compile(r"`(RULE-MAGIC-\d{3})`")
_JSON_BLOCK_RE = re.compile(r"```json\r?\n(.*?)```", re.S)
# 与 §5.2 相同的拼接写法，避免审计脚本自身的字面量触发误报
_PLACEHOLDER_RE = re.compile(r"(?i)\b(" + "TO" + "DO|T" + "BD|FIX" + "ME" + r")\b")


def audit_magic_corpus(docs_dir: str) -> str:
    """RULE-MAGIC-068：§5.2 语料机械审计；任一失败以首个断言名阻断"""
    root = Path(docs_dir)
    files = sorted(root.glob("*.md"), key=lambda p: p.name)
    if len(files) != 12:
        raise BalanceError("magic_corpus_file_count", str(len(files)))
    raw = [p.read_text(encoding="utf-8") for p in files]
    ids = []
    for text in raw:
        match = _DOC_ID_RE.search(text)
        ids.append(match.group(1) if match else None)
    expected = [f"DOC-MAGIC-{i:03d}" for i in range(1, 13)]
    if ids != expected:
        raise BalanceError("magic_corpus_doc_id_sequence", repr(ids))
    all_text = "\n".join(raw)
    rules = sorted(set(_RULE_RE.findall(all_text)))
    if len(rules) != 68:
        raise BalanceError("magic_corpus_rule_continuity", str(len(rules)))
    if _PLACEHOLDER_RE.search(all_text):
        raise BalanceError("magic_corpus_placeholder", "unfinished marker found")
    for text in raw:
        for block in _JSON_BLOCK_RE.findall(text):
            try:
                json.loads(block)
            except json.JSONDecodeError as exc:
                raise BalanceError("magic_corpus_json_invalid", str(exc)) from exc
    return "MAGIC_CORPUS_OK"

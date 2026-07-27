"""
TEST-MAGIC-026..030：魔法平衡与测试（DOC-MAGIC-012）

- TEST-MAGIC-026：四层传送注入反例（Schema/Registry/提案/handler）
- TEST-MAGIC-027：包络构建期校验矩阵；治疗日上限跨日与双账合并
- TEST-MAGIC-028：经济守恒——效果 handler 不产出 Item/货币
- TEST-MAGIC-029：1/7/30 日模拟抽样包络断言与固定 Seed 复现
- TEST-MAGIC-030：语料审计 MAGIC_CORPUS_OK 与注入损坏逐项报错
"""

import random
import shutil
from pathlib import Path

import pytest

from src.magic import (
    BALANCE_V1,
    DISPLACEMENT_CAPABILITIES,
    ECONOMY_IMPACT_CHANNELS,
    EFFECT_PORT_CALLS,
    EFFECT_IDS,
    BalanceError,
    CastingError,
    EffectError,
    HealDailyLedger,
    MagicBalanceConfig,
    MagicSimulationObservation,
    SpellError,
    VerdictClassification,
    apply_effect,
    audit_catalog_envelope,
    audit_handler_no_displacement,
    audit_item_envelope,
    audit_magic_corpus,
    build_default_magic_items,
    build_default_spell_catalog,
    check_magic_envelope,
    decode_spell_definition,
    lint_no_teleport,
)
from src.magic.spells import SpellDefinition
from src.magic.constants import CastKind, LegalOverride, TargetMode

from magic_helpers import command, learn, make_engine

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "11-magic"


def test_magic_026_four_layer_teleport_counterexamples():
    # 第 1 层 Schema：传送命名拒绝
    record = {
        "schema_version": 1, "spell_id": "spell.arcane.teleport",
        "school_id": "school.arcane", "display_name_key": "x",
        "cast_kind": "instant", "target_mode": "self", "max_targets": 1,
        "range_wu": 0.0, "area_radius_wu": 0.0, "mana_cost": 10,
        "cooldown_game_minutes": 0,
        "prerequisites": {"min_school_skill_rating": 0, "required_ability_ids": [],
                          "required_spell_ids": [], "required_item_tags": []},
        "legal_override": "inherit", "consent_required": False,
        "effect_bindings": [{"effect_id": "magic.effect.detect_magic", "parameters": {}}],
        "presentation_id": "magic.presentation.arcane.teleport",
    }
    with pytest.raises(SpellError) as exc:
        decode_spell_definition(record)
    assert exc.value.code == "magic_teleport_forbidden"
    # 第 2 层 Registry：lint 全量命名检查（注入绕过 decode 的污染条目必检出）
    catalog = build_default_spell_catalog()
    lint_no_teleport(catalog)
    polluted = SpellDefinition(
        spell_id="spell.arcane.teleport", school_id="school.arcane",
        display_name_key="x", cast_kind=CastKind.INSTANT, target_mode=TargetMode.SELF,
        max_targets=1, range_wu=0.0, area_radius_wu=0.0, mana_cost=10,
        cooldown_game_minutes=0,
        prerequisites={"min_school_skill_rating": 0, "required_ability_ids": [],
                       "required_spell_ids": [], "required_item_tags": []},
        legal_override=LegalOverride.INHERIT, consent_required=False,
        effect_bindings=({"effect_id": "magic.effect.detect_magic", "parameters": {}},),
        presentation_id="magic.presentation.arcane.teleport",
    )
    catalog._spells[polluted.spell_id] = polluted
    with pytest.raises(Exception) as exc2:
        lint_no_teleport(catalog)
    assert exc2.value.code == "magic_teleport_forbidden"
    # 第 3 层 提案校验：未注册法术 → FORBIDDEN
    env = make_engine()
    learn(env, "r.a", "spell.arcane.glowlight")
    verdict = env.engine.validate_spell_cast(command(env, "r.a", "spell.arcane.teleport"))
    assert verdict.classification is VerdictClassification.FORBIDDEN
    assert verdict.reason_code == "MAGIC_SPELL_UNKNOWN"
    # 第 4 层 handler：无位移能力的静态证明 + 未知 handler fail closed
    audit_handler_no_displacement()
    assert set(EFFECT_PORT_CALLS) == set(EFFECT_IDS)
    for calls in EFFECT_PORT_CALLS.values():
        assert not (calls & DISPLACEMENT_CAPABILITIES)
    with pytest.raises(EffectError) as exc3:
        apply_effect("magic.effect.teleport", {}, None)
    assert exc3.value.code == "magic_effect_unknown"


def test_magic_027_envelope_build_time_matrix():
    catalog = build_default_spell_catalog()
    audit_catalog_envelope(catalog)
    audit_item_envelope(build_default_magic_items())
    # REQ-MAGIC-023：越界定义构建期失败（mana_cost 上限 60）
    record = {
        "schema_version": 1, "spell_id": "spell.arcane.overcharged",
        "school_id": "school.arcane", "display_name_key": "x",
        "cast_kind": "instant", "target_mode": "self", "max_targets": 1,
        "range_wu": 0.0, "area_radius_wu": 0.0, "mana_cost": 70,
        "cooldown_game_minutes": 0,
        "prerequisites": {"min_school_skill_rating": 0, "required_ability_ids": [],
                          "required_spell_ids": [], "required_item_tags": []},
        "legal_override": "inherit", "consent_required": False,
        "effect_bindings": [{"effect_id": "magic.effect.detect_magic", "parameters": {}}],
        "presentation_id": "magic.presentation.arcane.overcharged",
    }
    with pytest.raises(SpellError):
        decode_spell_definition(record)
    # 配置版本固定且不可热改
    assert BALANCE_V1.config_version == "magic.balance.v1"
    assert BALANCE_V1.regen_increment_max == 9
    assert BALANCE_V1.daily_instant_cast_budget == 8
    changed = MagicBalanceConfig(**{**BALANCE_V1.__dict__, "mana_cost_max": 70})
    assert changed.config_version == BALANCE_V1.config_version  # 同版本不同参数只能靠新文档版本


def test_magic_027_heal_daily_cap_split_ledgers():
    # RULE-MAGIC-065：MAGIC 账按 (target, game_day) 记账；与 COMBAT 账合并审计
    magic_ledger = HealDailyLedger()
    combat_ledger = HealDailyLedger()  # COMBAT 侧同构分账
    hp_max = 100
    cap = HealDailyLedger.cap_for(hp_max)
    assert cap == 50
    magic_ledger.record("r.b", 0, 40)
    magic_ledger.record("r.b", 0, 10)
    assert magic_ledger.total("r.b", 0) == 50 <= cap
    # 跨日边界：按日切重置
    assert magic_ledger.total("r.b", 1) == 0
    # 双账合并：两账各自封顶，合并不超过 HP 恢复不变量
    combat_ledger.record("r.b", 0, 50)
    merged = magic_ledger.total("r.b", 0) + combat_ledger.total("r.b", 0)
    assert merged <= hp_max


def test_magic_028_economy_conservation_channels():
    # RULE-MAGIC-064：恰好三条注册经济影响通道
    assert ECONOMY_IMPACT_CHANNELS == frozenset(
        {"item_charge_usage", "maintenance_cost_reduction", "potion_demand_substitution"}
    )
    # 30 日魔法活动不产出 Item/货币
    observation = MagicSimulationObservation(seed=7, game_days=30)
    observation.instant_casts_per_caster_day = [("r.a", day, 8) for day in range(30)]
    observation.mana_spent_total = 8 * 5 * 30
    observation.mana_regenerated_total = 90 * 30
    observation.peak_scene_effect_instances = 24
    assert check_magic_envelope(observation, {}) == []
    # 注入产出即违例
    dirty = MagicSimulationObservation(seed=7, game_days=30, item_created_by_magic=1)
    assert "magic_created_item" in check_magic_envelope(dirty, {})
    dirty_currency = MagicSimulationObservation(seed=7, game_days=30, currency_created_by_magic=5)
    assert "magic_created_currency" in check_magic_envelope(dirty_currency, {})


def _run_simulation(seed: int, days: int) -> MagicSimulationObservation:
    """RULE-MAGIC-067：固定 Seed 的 1/7/30 日魔法活动抽样"""
    rng = random.Random(seed)
    env = make_engine()
    casters = ["r.a", "r.b", "r.c"]
    for caster in casters:
        learn(env, caster, "spell.arcane.glowlight")
    observation = MagicSimulationObservation(seed=seed, game_days=days)
    peak = 0
    for day in range(days):
        for caster in casters:
            casts = rng.randint(0, 8)  # 预算包络内
            for index in range(casts):
                game_time = day * 1440 + index * 60
                env.engine.commit_spell_cast(command(
                    env, caster, "spell.arcane.glowlight",
                    command_id=f"cmd.{caster}.{day}.{index}", game_time=game_time, game_day=day,
                ))
                observation.mana_spent_total += 5
            observation.instant_casts_per_caster_day.append((caster, day, casts))
        # 每日 10 个恢复 occurrence（resting × tide 1500 → +9）
        for occ in range(10):
            env.mana.settle_mana_regeneration(
                f"occ.{day}.{occ}", casters, {}, starweave_q1000=1500
            )
            observation.mana_regenerated_total += 9 * len(casters)
        env.store.expire_overdue((day + 1) * 1440)
        active = sum(
            1 for i in env.store._instances.values() if i.state.value == "active"
        )
        peak = max(peak, active)
    observation.peak_scene_effect_instances = peak
    return observation


def test_magic_029_simulation_envelope_and_seed_replay():
    for days in (1, 7, 30):
        observation = _run_simulation(seed=42, days=days)
        assert check_magic_envelope(observation, {}) == []
        # 施法频率在预算内、实例存量在 Scene 上限内
        for _caster, _day, count in observation.instant_casts_per_caster_day:
            assert count <= BALANCE_V1.daily_instant_cast_budget
        assert observation.peak_scene_effect_instances <= BALANCE_V1.scene_effect_instance_cap
    # 固定 Seed 复现一致
    first = _run_simulation(seed=42, days=7)
    second = _run_simulation(seed=42, days=7)
    assert first.instant_casts_per_caster_day == second.instant_casts_per_caster_day
    assert first.mana_spent_total == second.mana_spent_total
    assert first.peak_scene_effect_instances == second.peak_scene_effect_instances


def test_magic_030_corpus_audit_ok_on_real_docs():
    assert DOCS_DIR.is_dir()
    assert audit_magic_corpus(str(DOCS_DIR)) == "MAGIC_CORPUS_OK"


def _corpus_copy(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(DOCS_DIR, target)
    return target


def test_magic_030_corpus_injected_corruptions(tmp_path):
    # 缺文件
    broken = _corpus_copy(tmp_path, "missing_file")
    (broken / "12-magic-balance-tests.md").unlink()
    with pytest.raises(BalanceError) as exc:
        audit_magic_corpus(str(broken))
    assert exc.value.code == "magic_corpus_file_count"
    # doc_id 断号
    broken = _corpus_copy(tmp_path, "bad_doc_id")
    path = broken / "01-magic-worldview.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("doc_id: DOC-MAGIC-001", "doc_id: DOC-MAGIC-013"),
        encoding="utf-8",
    )
    with pytest.raises(BalanceError) as exc2:
        audit_magic_corpus(str(broken))
    assert exc2.value.code == "magic_corpus_doc_id_sequence"
    # RULE 断号（全局替换一条规则 ID）
    broken = _corpus_copy(tmp_path, "bad_rule")
    for md in broken.glob("*.md"):
        md.write_text(
            md.read_text(encoding="utf-8").replace("RULE-MAGIC-068", "RULE-MAGIC-06X"),
            encoding="utf-8",
        )
    with pytest.raises(BalanceError) as exc3:
        audit_magic_corpus(str(broken))
    assert exc3.value.code == "magic_corpus_rule_continuity"
    # 未完成标记
    broken = _corpus_copy(tmp_path, "placeholder")
    path = broken / "01-magic-worldview.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nTODO: 待补充\n", encoding="utf-8")
    with pytest.raises(BalanceError) as exc4:
        audit_magic_corpus(str(broken))
    assert exc4.value.code == "magic_corpus_placeholder"
    # 坏 JSON 块
    broken = _corpus_copy(tmp_path, "bad_json")
    path = broken / "05-casting-legality.md"
    text = path.read_text(encoding="utf-8")
    assert "```json\n{" in text
    path.write_text(text.replace("```json\n{", "```json\n{bad", 1), encoding="utf-8")
    with pytest.raises(BalanceError) as exc5:
        audit_magic_corpus(str(broken))
    assert exc5.value.code == "magic_corpus_json_invalid"

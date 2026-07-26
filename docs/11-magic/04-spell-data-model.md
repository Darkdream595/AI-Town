---
doc_id: DOC-MAGIC-004
title: 法术数据模型
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - spell-definition
  - spell-target-model
  - first-version-spell-catalog
depends_on:
  - DOC-FOUNDATION-006
  - DOC-MAGIC-002
  - DOC-MAGIC-003
  - DOC-WORLD-008
requirements:
  - REQ-MAGIC-007
  - REQ-MAGIC-008
last_updated: 2026-07-26
---

# 法术数据模型

## 1. 目的

定义 `SpellDefinition` 的完整 canonical Schema——目标类型、消耗、射程、前置条件、法律声明与注册效果绑定——以及首版法术 Catalog，使每个可施放法术在构建期即可被完整校验，运行时不存在未注册的世界改动路径。

## 2. 非目标

本文件不定义效果 handler 的结算语义（`DOC-MAGIC-009`）、施法校验顺序（`DOC-MAGIC-005`）、学习条件的执行（`DOC-MAGIC-006`）或表现映射（`DOC-MAGIC-011`）。不定义战斗内伤害公式（`DOC-COMBAT-004`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `SpellDefinition` | `spell.*` Stable Catalog 条目，法术的唯一权威定义 |
| Target Mode | 封闭枚举：`self/single_entity/multi_entity/ground_point/area_around_caster/none` |
| Effect Binding | 法术到注册效果 handler（`magic.effect.*`）的参数化引用 |
| Cast Kind | `instant`（单事务提交）或 `ritual`（`DOC-TIME-006` 长行动） |
| 法律声明 | 法术级 `permitted/restricted/prohibited` 覆盖，缺省继承学派基线 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-007` | 每个法术必须以完整 `SpellDefinition` 注册后才可被学习、提案或施放；strict decoder 拒绝未列字段与未知枚举值，构建期校验全部引用可解析。 |
| `REQ-MAGIC-008` | 法术改变世界的唯一途径是 `effect_bindings` 引用的注册 `magic.effect.*` handler；`SpellDefinition` 与运行时都不存在自由文本效果字段，任何叙述文本不进入结算路径。 |
| `RULE-MAGIC-015` | `target_mode` 与提案参数的合法组合：`self/none/area_around_caster` 要求 `target_refs=[]` 且 `aim_point=null`；`single_entity` 要求恰好 1 个 target；`multi_entity` 要求 `1..max_targets` 个；`ground_point` 要求 `aim_point` 非 null 且 target 为空。 |
| `RULE-MAGIC-016` | `range_wu` 为同 Scene 欧氏距离上限；跨 Scene 目标一律非法。`area_around_caster` 的作用半径用 `area_radius_wu` 单独声明，不复用 `range_wu`。 |
| `RULE-MAGIC-017` | `mana_cost` 范围 `5..60`；`cooldown_game_minutes` 范围 `0..1440`；`ritual` 法术必须声明 `required_work_units`，`instant` 法术禁止该字段。 |
| `RULE-MAGIC-018` | 前置条件只允许四类结构化声明：最低 SchoolSkill rating、必需 `ability.*`、必需已学 `spell.*`、必需 Item tag（如法器/材料）；不允许自然语言前置。 |
| `RULE-MAGIC-019` | 法术级法律声明只能收紧不能放宽：学派基线为 `prohibited` 的场景（`RULE-WORLD-034`）不得被法术声明为 `permitted`。 |
| `RULE-MAGIC-020` | `SpellDefinition` 的 `schema_version` 变更走版本化 upcaster；已发布 `spell_id` 不得复用或改变学派归属（`REQ-MAGIC-004`）。 |
| `RULE-MAGIC-021` | 首版法术 Catalog 恰好为 §5.2 列出的 12 条；新增法术必须同时提供 Effect Binding 目标 handler 的注册与测试，缺一构建失败。禁止传送类法术（`RULE-MAGIC-006`）。 |

## 5. 数据与接口

### 5.1 SpellDefinition Schema

`DES-MAGIC-004`：注册 `schema.magic.spell_definition.v1`，strict decoder（`additionalProperties=false`）：

```json
{
  "schema_version": 1,
  "spell_id": "spell.restoration.minor_mend",
  "school_id": "school.restoration",
  "display_name_key": "spell.restoration.minor_mend.name",
  "cast_kind": "instant",
  "target_mode": "single_entity",
  "max_targets": 1,
  "range_wu": 96.0,
  "area_radius_wu": 0.0,
  "mana_cost": 12,
  "cooldown_game_minutes": 30,
  "prerequisites": {
    "min_school_skill_rating": 20,
    "required_ability_ids": [],
    "required_spell_ids": [],
    "required_item_tags": []
  },
  "legal_override": "inherit",
  "consent_required": true,
  "effect_bindings": [
    {
      "effect_id": "magic.effect.heal_minor",
      "parameters": {"heal_base": 6, "skill_scale_per_25_rating": 2}
    }
  ],
  "presentation_id": "magic.presentation.restoration.minor_mend"
}
```

`legal_override` 枚举：`inherit/restricted/prohibited`。`consent_required=true` 表示对他人身体或财产生效前需要当事人同意或紧急救命例外（`RULE-WORLD-033`）。`parameters` 为该 handler 在 `DOC-MAGIC-009` 声明的 strict 参数子 Schema，未知键拒绝。

### 5.2 首版法术 Catalog

| `spell_id` | 学派 | target_mode | mana | 效果 handler |
|---|---|---|---|---|
| `spell.elemental.kindle_flame` | elemental | `ground_point` | 8 | `magic.effect.ignite` |
| `spell.elemental.douse` | elemental | `ground_point` | 8 | `magic.effect.extinguish` |
| `spell.restoration.minor_mend` | restoration | `single_entity` | 12 | `magic.effect.heal_minor` |
| `spell.restoration.cleanse_ailment` | restoration | `single_entity` | 20 | `magic.effect.cure_illness` |
| `spell.warding.purify_ground` | warding | `ground_point` | 30 | `magic.effect.purify_anomaly` |
| `spell.warding.reinforce_structure` | warding | `single_entity` | 25 | `magic.effect.reinforce_structure` |
| `spell.warding.ley_anchor` | warding | `ground_point` | 40 | `magic.effect.place_ley_anchor` |
| `spell.arcane.detect_magic` | arcane | `area_around_caster` | 10 | `magic.effect.detect_magic` |
| `spell.arcane.glowlight` | arcane | `self` | 5 | `magic.effect.conjure_light` |
| `spell.illusion.minor_veil` | illusion | `ground_point` | 15 | `magic.effect.veil_illusion` |
| `spell.spirit.soothe_spirit` | spirit | `single_entity` | 18 | `magic.effect.soothe_spirit` |
| `spell.spirit.hex_of_weariness` | spirit | `single_entity` | 35 | `magic.effect.curse_weariness` |

`spell.warding.ley_anchor`、`spell.warding.reinforce_structure` 为 `ritual`（分别 6/4 work units），其余为 `instant`。`spell.spirit.hex_of_weariness` 声明 `legal_override: "restricted"`；攻击性场景默认判定见 `DOC-MAGIC-005`。

## 6. 正常流程

1. 内容作者提交 `SpellDefinition`；构建期校验 Schema、学派 scope（`RULE-MAGIC-005`）、effect handler 存在性与参数子 Schema。
2. Registry 发布不可变 Catalog 快照，Capability Builder 与学习系统按 `spell_id` 引用。
3. 施法路径按 `target_mode/range_wu/prerequisites` 做前置校验（`DOC-MAGIC-005`）。
4. 提交时逐条执行 `effect_bindings`，每条产生 owner 结算的 DomainEvent（`DOC-MAGIC-009`）。

## 7. 边界情况

- `multi_entity` 目标数超过 `max_targets` 或与 `cast_spell_parameters` 的 `maxItems: 8` 冲突时，以较小者为硬上限。
- `ground_point` 的 `aim_point` 必须位于施法者同 Scene 且经 MAP 判定为有效世界坐标；不要求 standable（可指向火盆、异常区）。
- 一个法术绑定多个效果时按数组顺序结算，任一 handler 前置失败则整次施法拒绝，不允许部分生效。
- `cooldown_game_minutes = 0` 表示无冷却；冷却计时基于 GameTime，暂停期间不流逝（`RULE-FOUNDATION-038`）。

## 8. 错误与降级

注册期错误（未知 `school_id`、未知 `effect_id`、参数越界、字段缺失）一律构建失败，禁止带病发布。运行时遇到 Catalog 中不存在的 `spell_id` 返回 `MAGIC_SPELL_UNKNOWN` 并 fail closed；Catalog 快照加载失败时 MAGIC 拒绝全部施法命令，不猜测定义。

## 9. 安全与性能

`SpellDefinition` 全部字段无 Secret，可整体进入决策上下文摘要。Catalog 为构建期不可变结构，按 `spell_id` O(1) 索引；首版 12 条全量常驻内存。模型与 Client 传入的任何数值字段（伤害、治疗量、消耗）都不被信任——结算参数只来自 Catalog（`RULE-AI-028` 同向约束）。

## 10. 验收标准

- 首版 Catalog 恰好 12 条，全部通过 strict decode 与引用解析。
- 每条法术的 `target_mode` 组合约束在 fixture 上与 `RULE-MAGIC-015` 完全一致。
- 注入自由文本效果字段、未注册 handler 或传送语义的定义在构建期被拒绝。
- `legal_override` 只能收紧的属性在全 Catalog 审计通过。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-007` | `REQ-MAGIC-007`, `RULE-MAGIC-017..018`, `RULE-MAGIC-020` | Schema strict decode、数值范围与版本化 Contract Test |
| `TEST-MAGIC-008` | `REQ-MAGIC-008`, `RULE-MAGIC-021` | Catalog 封闭性审计：12 条法术、全部 effect binding 可解析、自由文本效果注入被拒 |
| `TEST-MAGIC-009` | `RULE-MAGIC-015..016`, `RULE-MAGIC-019` | 六种 target_mode × 参数组合矩阵；法律声明放宽反例 |

## 12. 关联文档

- `DOC-MAGIC-002`：`school_id` 与作用域仲裁
- `DOC-MAGIC-003`：`mana_cost` 的消耗结算
- `DOC-MAGIC-005`：前置与法律校验的执行顺序
- `DOC-MAGIC-009`：`magic.effect.*` handler 注册表
- `DOC-MAGIC-011`：`presentation_id` 的表现映射
- `DOC-AI-004`：`cast_spell_parameters` wire Schema

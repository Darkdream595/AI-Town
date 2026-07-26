---
doc_id: DOC-MAGIC-010
title: 魔法物品
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-definition-registry
  - magic-item-charge-state
depends_on:
  - DOC-ECON-004
  - DOC-ECON-005
  - DOC-MAGIC-003
  - DOC-MAGIC-004
  - DOC-MAGIC-009
requirements:
  - REQ-MAGIC-019
  - REQ-MAGIC-020
last_updated: 2026-07-26
---

# 魔法物品

## 1. 目的

定义 `magic_definition_id` 注册表（`DOC-ECON-004` magical kind 的引用目标）、魔法物品的三种类型（充能法器、魔法书、被动饰物）与充能状态模型，划清"所有权归 Economy、魔法语义归 MAGIC"的双 owner 边界。

## 2. 非目标

本文件不定义 Item 实例、所有权、转移、交易与 Inventory 容量——这些的唯一真值是 `DOC-ECON-004/005/006`（`RULE-MAGIC-008`）；不定义魔法物品的制作配方经济（`DOC-ECON-010`）或掉落来源（`DOC-COMBAT-010`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `MagicItemDefinition` | `magic.item.*` Stable Catalog 条目，`magic_definition_id` 的解析目标 |
| 充能法器 | `charged_spell_item`：绑定单一 `spell_id`、有充能次数的可用 Item |
| 魔法书 | `spellbook`：作为学习来源教授单一 `spell_id` 的 Item |
| 被动饰物 | `passive_trinket`：持有期间提供注册修正的 Item |
| `MagicItemChargeState` | MAGIC 拥有的 per-item 充能状态，键为 ECON `item_id` |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-019` | 每个 `magic_definition_id` 必须解析到唯一 `MagicItemDefinition`；ECON 侧 magical Item 的效果语义只经该注册表解释，ECON 不解释效果、MAGIC 不裁决所有权（对齐 `DOC-ECON-004` §7）。 |
| `REQ-MAGIC-020` | 充能是整数 `0 <= charges_current <= charges_max`（`charges_max` 范围 `1..20`）；充能消耗与效果事件同事务原子结算，相同 `(item_id, source_event_id)` 最多扣减一次。 |
| `RULE-MAGIC-054` | 法器施放走 `use_object` 命令 + 本域校验：效果等同施放绑定法术，但跳过 Mana 消耗与技能门槛、保留目标/射程/世界合法性检查（第 4、6、7 级）；`prohibited` 判定的法术不因装入法器而合法。 |
| `RULE-MAGIC-055` | 充能补充是注册长行动 `magic.recharge_item`：持有者消耗自身 Mana（每充能点 15 Mana）逐点恢复，要求对应学派 SchoolSkill rating >= 30；不存在自动回充或货币直购充能。 |
| `RULE-MAGIC-056` | 被动饰物只能提供注册修正键：`starweave_tide_modifier` 加成（上限 +100 q1000）或侦测半径加成；修正在持有且位于 Inventory 装备位时生效，不叠加同类饰物。 |
| `RULE-MAGIC-057` | Item 转移不重置充能：`MagicItemChargeState` 随 `item_id` 存续；Item `state=consumed/destroyed`（ECON tombstone）时充能状态同步转 `retired`，不可复活。 |
| `RULE-MAGIC-058` | 魔法物品的创造只能来自注册来源：ECON 制作配方、事件奖励或世界初始化，均产生 provenance 事件；法术效果不能凭空制造 Item（`RULE-FOUNDATION-018/019`、`RULE-MAGIC-002`）。 |

## 5. 数据与接口

`DES-MAGIC-010`：`MagicItemDefinition` 与充能状态：

```json
{
  "definition": {
    "magic_schema_version": 1,
    "magic_definition_id": "magic.item.wand_of_glowlight",
    "magic_item_kind": "charged_spell_item",
    "bound_spell_id": "spell.arcane.glowlight",
    "charges_max": 10,
    "recharge_school_id": "school.arcane",
    "passive_modifiers": [],
    "detectable": true
  },
  "charge_state": {
    "charge_schema_version": 1,
    "item_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "magic_definition_id": "magic.item.wand_of_glowlight",
    "charges_current": 7,
    "state": "active",
    "last_recharge_game_time": 4320,
    "charge_revision": 5
  }
}
```

`magic_item_kind` 枚举：`charged_spell_item/spellbook/passive_trinket`。三分支为 strict 子 Schema：`spellbook` 声明 `teaches_spell_id` 且不含充能字段（书不消耗充能）；`passive_trinket` 声明 `passive_modifiers` 且不含 `bound_spell_id`；只有 `charged_spell_item` 拥有充能与回充字段。首版注册六件：`magic.item.wand_of_glowlight`、`magic.item.charm_of_soothing`、`magic.item.tome_of_minor_mend`、`magic.item.tome_of_detect_magic`、`magic.item.starweave_pendant`、`magic.item.warding_focus`。

Port：

```text
resolve_magic_definition(magic_definition_id) -> MagicItemDefinition
use_charged_item(command_id, item_id, target_refs, aim_point) -> SpellCastCommitted | Rejection
begin_recharge(command_id, item_id, caster_id) -> LongAction | Rejection
```

## 6. 正常流程

1. ECON 构建期校验 magical ItemDefinition 的 `magic_definition_id` 可解析（双向引用审计）。
2. 玩家/居民对法器发起 `use_object`；MAGIC 校验充能、目标与合法性后原子扣充能并结算效果。
3. 充能耗尽的法器保留为普通 Item，可交易、可回充。
4. 回充长行动逐检查点消耗 Mana、恢复充能点，各检查点独立提交。

## 7. 边界情况

- 法器在 `use_object` 校验与提交之间被转移：提交按最新 Revision 重验持有权（读取 ECON current ownership），失败拒绝。
- 回充中 Item 被卖出：检查点重验持有权失败，长行动 `interrupted`，已充点数保留在 Item 上归新持有者。
- 被俘/昏迷居民的魔法物品：处置遵循 ECON/COMBAT 掉落与保管规则，MAGIC 不定义没收。
- 魔法书学完不消失：仍是可转卖 Item，可供多人先后学习；同时只能绑定一个学习会话（来源 Reservation）。
- 未知 `magic_definition_id` 的 magical Item（数据漂移）：Item 保留、相关使用动作不可用（对齐 `DOC-ECON-004` §8），不猜测效果。

## 8. 错误与降级

返回 `MAGIC_ITEM_DEFINITION_UNKNOWN`、`MAGIC_ITEM_NO_CHARGES`、`MAGIC_ITEM_NOT_HELD`、`MAGIC_RECHARGE_PREREQUISITE_MISSING` 或复用 `DES-MAGIC-005` reason 集。充能状态投影缺失时按 `charges_current=0` fail closed，禁止按满充猜测。

## 9. 安全与性能

充能扣减只发生在服务器事务；Client/模型不能上报充能数值。`MagicItemChargeState` 按 `item_id` 索引，随 ECON tombstone 事件驱动 `retired`，周期审计对账两侧状态。被动饰物修正进入恢复结算时按持有者位置一次性读取，不逐 Tick 扫描 Inventory。

## 10. 验收标准

- ECON magical Item 与 `MagicItemDefinition` 双向引用审计零孤儿。
- 充能扣减/回充在重放、转移、销毁场景下守恒且幂等。
- 法器施放与本体施法在合法性判定上等价（除 Mana/门槛豁免）。
- 六件首版物品各有端到端 fixture（获得 → 使用/学习 → 回充/转卖）。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-022` | `REQ-MAGIC-019..020`, `RULE-MAGIC-057..058` | 双向引用审计、充能守恒 Property Test、tombstone 同步与凭空制造反例 |
| `TEST-MAGIC-023` | `RULE-MAGIC-054..056` | 法器合法性等价测试、回充长行动中断/持有权重验、饰物修正不叠加 |

## 12. 关联文档

- `DOC-ECON-004`：magical kind 与 `magic_definition_id` 挂钩点
- `DOC-ECON-005/006`：持有、容量与交易真值
- `DOC-MAGIC-003`：回充的 Mana 消耗
- `DOC-MAGIC-006`：魔法书作为学习来源
- `DOC-MAGIC-009`：法器触发的效果结算

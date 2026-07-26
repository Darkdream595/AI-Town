---
doc_id: DOC-ECON-004
title: 物品数据模型
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - item-definition
  - item-instance
  - item-provenance
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
requirements:
  - REQ-ECON-004
last_updated: 2026-07-26
---

# 物品数据模型

## 1. 目的

`REQ-ECON-004`：建立 ItemDefinition、stack batch 与 unique ItemInstance 的唯一权威模型，使种类、来源、数量、所有权、版本和后续魔法/战斗引用均可验证。

## 2. 非目标

本文不定义 Spell 效果、装备战斗数值、渲染 Asset、Inventory 容量、价格或掉落算法；对应 domain 只通过稳定 Item ID 读取 ECON 投影。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| ItemDefinition | Stable Catalog ID 指向的不可变物品模板 |
| Item Kind | `stackable/unique/container/property_deed/magical` 五种主存储形态 |
| ItemInstance | unique、container、property_deed 或 magical 的运行时实体 |
| Stack Batch | 相同 Definition、品质与可合并 provenance key 的整数数量 |
| Provenance | 从合法 source event 到当前 Item/Batch 的追加式来源链 |
| Ownership Location | Item 当前唯一所在的 inventory、container、work reservation 或销毁 sink |

## 4. 规则与不变量

- `RULE-ECON-013`：每个 ItemDefinition 必须声明唯一 `item_definition_id`、kind、整数重量、stack 规则、tags 和 schema version；未知 Definition 禁止创建。
- `RULE-ECON-014`：unique/container/property_deed/magical ItemInstance 同一 Revision 恰好有一个 Ownership Location；不能同时位于两个 Inventory 或“无主但未销毁”。
- `RULE-ECON-015`：stack quantity 为正整数，拆分/合并前后总量与 provenance 数量守恒；quantity=0 的 batch 必须在同事务移除。
- `RULE-ECON-016`：所有创建、制作、采集、交易、掉落、没收、恢复和销毁都追加 provenance edge；不得改写或截断已提交来源链。

## 5. 数据与接口

`DES-ECON-004`：

```json
{
  "schema_version": 1,
  "item_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "item_definition_id": "item.tool.silver_ash_pickaxe",
  "item_kind": "unique",
  "quality_grade": 2,
  "unit_weight_grams": 3200,
  "ownership": {
    "location_kind": "inventory",
    "location_id": "01K1AB2CD3EF4GH5JK6MNP7QRT"
  },
  "provenance_head_event_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "state": "active",
  "created_game_time": 4320,
  "last_revision": 105
}
```

Stack Batch 使用 `batch_id`、`quantity`、`merge_key={definition,quality,condition,provenance_class}`。`state` 为 `active/reserved/consumed/destroyed`；destroyed 只保留审计 tombstone，不再有可转移 ownership。

## 6. 正常流程

1. 注册表在构建期校验 ItemDefinition、Stable ID、kind 分支和整数单位。
2. 合法 source Command 创建 ItemInstance/Batch 与首个 provenance event。
3. Transfer/Craft 先按 Item/Batch ID 建立 Reservation。
4. Transaction 原子改变 Ownership Location 或 stack quantity，并追加 provenance edge。
5. 其他 domain 通过 `get_item_capability_projection(item_id, revision)` 读取最小能力，不直接写 Item。

## 7. 边界情况

- magical 是主 kind 时，Spell/effect 仅以 `magic_definition_id` 引用 MAGIC owner；ECON 不解释效果。
- property_deed 引用 property subject，不等于直接修改 Building owner。
- 两个 stack 只有 merge key 完全一致才可合并；不同来源类别保留独立 batch。
- 容器本身是 unique instance；其内容由 Inventory 规则表示，不能把子物品序列复制进 ItemInstance。
- 腐坏或耐久变化若改变可合并性，必须先拆 batch 或提升 condition key。

## 8. 错误与降级

返回 `item_definition_unknown`、`item_kind_mismatch`、`duplicate_unique_owner`、`invalid_stack_quantity`、`provenance_missing`、`merge_key_mismatch` 或 `stale_revision`。视觉/魔法投影缺失时 Item 保留但相关使用动作不可用，不猜测能力。

## 9. 安全与性能

客户端不能指定可信 provenance、owner 或 quantity delta。Provenance 以 event edge 分页并设置查询深度上限，审计使用迭代游标；ItemDefinition 注册表不可变缓存，运行时按 ownership location 与 Definition 建索引。

## 10. 验收标准

- 五种 Item kind 均可通过严格 Schema 解析且额外字段被拒绝。
- 任一 unique 实例在每个 Revision 恰有一个 owner location。
- stack 拆分、合并、制作消费与销毁满足数量守恒。
- provenance 可从当前记录追溯到注册 source event。
- Magical/Property 引用不让 ECON 改写 MAGIC 或 EVENT 状态。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-013` | 五 kind strict schema 与 Definition registry |
| `TEST-ECON-014` | unique ownership 唯一性 property test |
| `TEST-ECON-015` | stack split/merge/consume 数量守恒 |
| `TEST-ECON-016` | provenance chain、tombstone 与跨域引用边界 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：唯一物品与数量不变量
- `DOC-ECON-005`：Inventory/container 约束
- `DOC-ECON-006`：原子所有权转移
- `DOC-ECON-010`：制作 provenance

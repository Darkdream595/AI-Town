---
doc_id: DOC-RESIDENT-010
title: Inventory 引用与所有权边界
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-inventory-reference
  - resident-economy-boundary
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-001
requirements:
  - REQ-RESIDENT-010
last_updated: 2026-07-26
---

# Inventory 引用与所有权边界

## 1. 目的

`REQ-RESIDENT-010`：规定 Resident 仅保存 ECON-owned `inventory_id`，所有 Item、Currency、容器、容量、重量、所有权、交易与消费均由 ECON 独占，杜绝双重权威和复制物品。

## 2. 非目标

不定义 Item Schema、槽位、重量、价格、货币、装备、掉落或交易事务；Resident 不缓存“便于读取”的数量或余额。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Inventory Reference | Resident 到 ECON Inventory aggregate 的 runtime ID |
| Item Reference | ECON 返回的只读 `item_instance_id` 或 Catalog `item_id` |
| Capability Evidence | ECON 根据 Item/装备生成的只读能力证据 |
| Ownership Transfer | 只可由 ECON Command 完成的原子变更 |

## 4. 数据与接口

`DES-RESIDENT-010`：Resident 内唯一库存字段：

```json
{
  "resident_id":"01K1AB2CD3EF4GH5JK6MNP7QRS",
  "inventory_id":"01K1AB2CD3EF4GH5JK6MNP7QRX"
}
```

允许的只读投影输入：

```json
{
  "inventory_id":"01K1AB2CD3EF4GH5JK6MNP7QRX",
  "source_revision":42,
  "capability_tags":["has.food.basic","has.tool.herbalism"],
  "referenced_item_ids":["item.bread.rye"]
}
```

Resident 不持久化该 projection。创建/更换引用只能使用 ECON owner 返回的 `InventoryBindingResult`。

## 5. 规则与不变量

- `RULE-RESIDENT-053`：Resident Schema 除 `inventory_id` 外不得出现 `items`、`stacks`、`slots`、`weight`、`balance`、`owner_id` 或装备数量字段。
- `RULE-RESIDENT-054`：任何 give/buy/sell/use/craft/loot 行动都调用 ECON Command；Resident 不能修改或补偿 Item。
- `RULE-RESIDENT-055`：`inventory_id` 与 Resident 一对一初始绑定；迁移/修复须 ECON 验证且生成显式事件。
- `RULE-RESIDENT-056`：Capability Evidence 必须携带 `source_revision`，写命令前由 ECON 以最新状态重校验。
- `RULE-RESIDENT-057`：居民 unconscious/captive/转职不自动转移或删除物品；若规则要求转移，由 ECON 产生 Ownership DomainEvent。
- `RULE-RESIDENT-058`：恢复审计发现缺失 Inventory 时停止该 world 写入，不创建空 Inventory 掩盖损失。

## 6. 正常流程

1. Orchestrator 创建 Resident 前请求 ECON 创建空 Inventory。
2. 两个 aggregate 与各自事件在一个 Unit of Work 成功后建立引用。
3. AI/玩家需要物品能力时读取 ECON 的最小只读 projection。
4. 动作提交前 ECON 重校验数量、所有权、权限与 Revision。
5. ECON 提交 Item 变化；Resident 仅消费结果事件以更新 Need/Health 等自身状态。

## 7. 边界情况

- Inventory 已创建而 Resident 创建失败时整个 Unit of Work 回滚。
- 同一 Item 同时交易/使用由 ECON Reservation 决胜，Resident 不缓存获胜结果。
- 被俘时 confiscation 需显式合法 ECON Transaction，不由 lifecycle 隐式发生。
- 读 projection 过期只导致重规划，不把旧 Item 当作存在。

## 8. 错误与降级

返回 `RESIDENT_INVENTORY_REFERENCE_MISSING`、`RESIDENT_INVENTORY_BINDING_CONFLICT`、`RESIDENT_ECON_PROJECTION_STALE`。ECON 不可用时禁止物品相关写操作；基本行为可选择不依赖 Item 的注册 fallback。

## 9. 安全与性能

对 AI 只披露当前行动必要的 Item 摘要，不给 Repository 或隐藏容器。Inventory 查询支持批量 projection，避免居民列表 N+1。

## 10. 验收标准

- Resident 持久 Schema 不包含任何 Item/Currency 权威字段。
- 创建失败不遗留孤儿 Inventory。
- unconscious/captive 不产生隐式所有权变化。
- 过期物品 projection 在提交前被拒绝。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-037` | Resident Schema 禁止 ECON-owned 字段 |
| `TEST-RESIDENT-038` | Resident+Inventory 原子初始化 |
| `TEST-RESIDENT-039` | stale projection 与并发 Item 操作拒绝 |
| `TEST-RESIDENT-040` | defeat/转职无隐式 Ownership Event |

## 12. 关联文档

- `DOC-FOUNDATION-003`：Inventory canonical ownership
- `DOC-FOUNDATION-005`：Item/数量不变量
- `DOC-ECON-004..006`：Item、Inventory、Transaction owner
- `DOC-RESIDENT-011`：初始化 Unit of Work


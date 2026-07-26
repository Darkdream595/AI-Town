---
doc_id: DOC-ECON-005
title: 库存与容器规则
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - inventory
  - container-capacity
  - resource-reservation
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-ECON-004
requirements:
  - REQ-ECON-005
last_updated: 2026-07-26
---

# 库存与容器规则

## 1. 目的

`REQ-ECON-005`：定义 Inventory、Container、格子、重量、类型权限与 Reservation，保证任何移动、装备、交易、制作和恢复都不会产生负数量、超容量、循环容器或重复占用。

## 2. 非目标

本文不拥有 Resident aggregate、Building 存储空间、战斗装备效果或 UI 拖放；Resident 只保存 `inventory_id`，其他 owner 通过 ECON Command 操作。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Inventory | ECON aggregate，具有 owner 引用、slot/weight 限额与访问策略 |
| Slot | 一个 ItemInstance 或一个可合并 Stack Batch 占用的逻辑位置 |
| Container Inventory | `item_kind=container` 实例拥有的子 Inventory |
| Effective Weight | 直接内容加允许深度内子容器内容的整数克数 |
| Resource Reservation | 对 currency、item/batch quantity、slot、station 或 property 的临时排他声明 |

## 4. 规则与不变量

- `RULE-ECON-017`：Inventory 的 `used_slots <= max_slots`、`total_weight_grams <= max_weight_grams`，且 quantity、slots、weight 均不得为负。
- `RULE-ECON-018`：容器嵌套最大深度为 2，禁止自身包含、祖先循环和把容器移动进其后代。
- `RULE-ECON-019`：访问必须满足 `access_policy`；Client/AI 声称 `can_access=true` 无效，私人住宅/容器遵守 WORLD consent 规则。
- `RULE-ECON-020`：Reservation 状态只允许 `active/consumed/released/expired`；active 数量计入可用量扣减，同一资源不得超额预留。

## 5. 数据与接口

`DES-ECON-005`：

```json
{
  "schema_version": 1,
  "inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "owner_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "inventory_kind": "resident",
  "max_slots": 24,
  "max_weight_grams": 30000,
  "used_slots": 7,
  "total_weight_grams": 12540,
  "access_policy_id": "inventory_policy.owner_and_authorized_trade",
  "parent_container_item_id": null,
  "version": 12
}
```

Reservation：

```json
{
  "reservation_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "owner_action_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "resource_kind": "item_quantity",
  "resource_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "quantity": 3,
  "created_game_time": 600,
  "expires_at_game_time": 610,
  "request_revision": 90,
  "state": "active"
}
```

## 6. 正常流程

1. 调用方请求 `preview_transfer(source, target, items, revision)`。
2. ECON 校验权限、可用 quantity、目标 slot/weight、容器深度与 type restriction。
3. 按 `currency_account -> inventory -> item_or_batch -> workplace -> property`，同类按 stable resource key 升序获取 Reservation。
4. Transaction 消费 Reservation 并原子更新 source/target Inventory 与 ownership。
5. 未消费 Reservation 由明确取消或 GameTime 到期释放；GameTime 暂停时不自然过期。

## 7. 边界情况

- Stack 部分转移先 Reservation quantity，再在提交时确定性拆 batch。
- 目标已有可合并 stack 时不新增 slot，但仍检查重量。
- 把空容器放入容器也计容器自重；子内容重量不可隐藏。
- arrival/交易中断时 active Reservation 可恢复，不凭网络断开立即复制释放与消费。
- Inventory owner 被俘、昏迷或 Building 被封锁不转移 ownership，只影响访问 projection。

## 8. 错误与降级

返回 `inventory_access_denied`、`insufficient_quantity`、`slot_limit_exceeded`、`weight_limit_exceeded`、`container_cycle`、`container_depth_exceeded`、`reservation_conflict` 或 `reservation_expired`。UI 投影延迟时只重新拉取，不乐观提交。

## 9. 安全与性能

每次 Command 最多涉及 64 个 item/batch，容器遍历深度固定 2；总重量作为缓存字段但提交时从受影响树增量复核。Reservation 查询按 resource key 索引，恢复时全量检查 active 总和不超过资源量。

## 10. 验收标准

- slot、weight、type restriction、访问与容器深度均有通过/拒绝 fixture。
- stack 部分预留和两个并发买家不会超卖。
- GameTime 暂停、到期、取消、崩溃恢复下 Reservation 状态唯一。
- Resident 只引用 InventoryId，不能直接写 Item quantity。
- 重放后缓存重量/slot 与内容重算完全一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-017` | slot/weight/type 限额与增量缓存重算 |
| `TEST-ECON-018` | 容器循环、深度和子内容重量 |
| `TEST-ECON-019` | 私人访问、玩家/NPC 权限 parity |
| `TEST-ECON-020` | Reservation 并发、暂停、过期与恢复 |

## 12. 关联文档

- `DOC-WORLD-008`：私人容器与同意
- `DOC-ECON-004`：Item 与 ownership
- `DOC-ECON-006`：Reservation 消费与事务
- `DOC-MAP-008`：Door Reservation 是 MAP 自有的独立资源类型

---
doc_id: DOC-ECON-010
title: 制作与资源消耗
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - recipe-definition
  - craft-order
  - deterministic-resource-consumption
depends_on:
  - DOC-FOUNDATION-005
  - DOC-ECON-004
  - DOC-ECON-005
  - DOC-ECON-006
  - DOC-ECON-009
requirements:
  - REQ-ECON-010
last_updated: 2026-07-26
---

# 制作与资源消耗

## 1. 目的

`REQ-ECON-010`：定义 Recipe、制作输入/输出、工具/工位、时长、失败消费与 provenance，使 `craft` 行动可被 AI/玩家提议、由规则确定性结算并在恢复后 exactly-once。

## 2. 非目标

本文不定义 Resident 技能成长、Spell 效果、Building 状态、制作动画或 AI 是否选择 Recipe；只消费其版本化资格/位置投影。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| RecipeDefinition | Stable ID 指向的输入、输出、工具、工位、时长与失败策略 |
| CraftOrder | 一次由 ActionId 发起、可调度和恢复的制作 aggregate |
| Consumable Input | 成功或失败按规则减少的 stack/item |
| Tool Requirement | 必须 Reservation 但正常成功不消费的 Item capability |
| Craft Station | Workplace 内具有 capacity 的制作资源 |
| Yield | 由 Recipe、资格 projection 与 Seed stream 决定的结构化输出 |

## 4. 规则与不变量

- `RULE-ECON-037`：Recipe 必须有 version、正整数 input/output quantity、整数 GameTime duration、Station/Tool 条件和有界 failure policy；AI 不能新增 Recipe 或输出。
- `RULE-ECON-038`：CraftOrder 开始前必须原子预留所有 consumable input、目标 Inventory 容量、工具、worker 与 Station；缺一不可开始。
- `RULE-ECON-039`：成功时输入消费、工具释放、输出创建/ownership、provenance、订单状态与 DomainEvent 同一事务提交。
- `RULE-ECON-040`：失败消费量为 `floor(reserved_quantity × failure_consumption_bps / 10000)`，每项限定 `0..reserved_quantity`；未声明 sink 的差额全部释放。

## 5. 数据与接口

`DES-ECON-010`：

```json
{
  "schema_version": 1,
  "recipe_id": "recipe.smith.iron_pickaxe.v1",
  "recipe_version": 1,
  "inputs": [
    {"item_definition_id": "item.material.iron_ingot", "quantity": 3},
    {"item_definition_id": "item.material.treated_wood", "quantity": 1}
  ],
  "outputs": [
    {"item_definition_id": "item.tool.iron_pickaxe", "quantity": 1}
  ],
  "tool_capability_ids": ["tool_capability.smithing_hammer"],
  "station_capability_id": "station.smithing_anvil",
  "duration_game_minutes": 120,
  "failure_consumption_bps": 2500,
  "required_skill_projection": {"skill_id": "skill.smithing", "minimum_rank": 2}
}
```

CraftOrder 状态为 `drafted/reserved/in_progress/completed/failed/cancelled/recovery_required`，并记录 `action_id`、`recipe_id/version`、Reservation IDs、start/end GameTime、seed stream position 与 last Revision。

## 6. 正常流程

1. AI `ActionProposal` 或 PlayerCommand 选择注册 RecipeId、数量与目标 Inventory。
2. ECON 展开整数物料清单，校验资格、Workplace/Station 与目标容量。
3. 按资源全序建立 Reservation，创建 `reserved` CraftOrder。
4. TIME 调度长动作；ECON 只接收确定的 progress/complete trigger。
5. 完成时基于已记录 Seed stream result 选择已注册 outcome。
6. Transaction 原子消费输入、创建输出、追加 provenance 并转 terminal state。

## 7. 边界情况

- quantity 批次需逐项检查上限，首版单 Order 最多 32 份 Recipe。
- 工具在进行中被其他流程请求时因 Reservation 冲突失败，不能一物多用。
- Building/Station 损坏使 Order 中断；按 Recipe cancellation policy 消费或释放，不自动完成。
- magical output 只引用 MAGIC 提供的 `magic_definition_id`，ECON 不计算效果。
- 崩溃后根据 terminal event 与 Reservation 恢复；不重新抽取 Seed 或再次创建 output。

## 8. 错误与降级

返回 `recipe_unknown`、`recipe_version_mismatch`、`qualification_failed`、`input_missing`、`tool_unavailable`、`station_unavailable`、`output_capacity_missing` 或 `craft_recovery_required`。模型不可用时已开始 Order 可机械完成；不会自动选择新 Recipe。

## 9. 安全与性能

Recipe DAG 在构建期校验无自生产套利环：若循环存在，必须有外部 sink 且由平衡审计批准，否则拒绝 Catalog。展开后 item legs 上限 64。Seed result 与 Recipe version 记录在事件中，重放不执行模型或重新随机。

## 10. 验收标准

- 成功、失败、取消、Station 损坏与崩溃恢复都有明确输入/输出数量。
- 并发 CraftOrder 不重复占用 input、tool 或 Station。
- failure bps 的 0、边界和奇数 quantity 使用 floor 规则一致。
- 输出 provenance 指向 Recipe、输入 provenance heads、worker ActionId 和完成事件。
- 玩家与 AI 使用相同 Recipe/资格/Reservation/结算。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-037` | Recipe strict schema、DAG 与版本 |
| `TEST-ECON-038` | input/tool/station/output capacity 原子 Reservation |
| `TEST-ECON-039` | success/failure/cancel 数量与 provenance |
| `TEST-ECON-040` | crash/Seed replay/exactly-once output |

## 12. 关联文档

- `DOC-ECON-004`：ItemDefinition 与 provenance
- `DOC-ECON-005`：资源与 Station Reservation
- `DOC-ECON-006`：原子提交
- `DOC-ECON-009`：生产链

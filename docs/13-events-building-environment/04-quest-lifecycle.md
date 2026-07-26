---
doc_id: DOC-EVENT-004
title: Quest 生命周期与结构化目标
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - quest-aggregate
  - quest-objective-types
  - quest-deadline-failure
depends_on:
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-TIME-005
  - DOC-TIME-008
  - DOC-EVENT-001
requirements:
  - REQ-EVENT-004
last_updated: 2026-07-26
---

# Quest 生命周期与结构化目标

## 1. 目的

`REQ-EVENT-004`：定义 Quest aggregate、固定状态机、九类结构化 Objective、事件驱动的进度判定、AI 居民独立参与和截止/失败语义，使任务不依赖玩家在场即可推进、完成或失败。

## 2. 非目标

本文不定义 Quest 的奖励数额与价格影响（ECON canonical）、关系数值变化（MEMORY/RESIDENT canonical）、由事件生成 Quest 的策略（`DOC-EVENT-005`）或战斗结算（COMBAT canonical）。本文不提供自由文本任务描述的语义判定。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Quest | 由结构化 Objective、状态、参与者、期限和结果组成的 EVENT aggregate（`DOC-FOUNDATION-004`） |
| Objective | 注册类型 + 参数 + 完成计数的可判定目标项 |
| Objective Matcher | 将已提交 DomainEvent 映射到 Objective 进度的确定性匹配器 |
| Participant | 以角色（`issuer/assignee/beneficiary/target`）登记的实体引用 |
| Deadline | `deadline_game_time`；到期未完成即失败或过期 |
| Offer Window | quest 处于 `offered` 可被接受的 GameTime 区间 |

## 4. 规则与不变量

- `RULE-EVENT-019`：Quest 状态机固定为 `draft → offered → accepted → active → completed | failed | expired | abandoned → archived`，另有 `offered → declined → archived`；每次转换按 `RULE-FOUNDATION-029` 与 DomainEvent 原子提交，且遵循 `RULE-FOUNDATION-013`：Quest 字段不是事实来源。
- `RULE-EVENT-020`：Objective 必须使用注册类型枚举 `reach_location / deliver_item / talk_to / craft_item / protect_target / investigate / win_encounter / repair_structure / maintain_condition`，每类有 strict 参数 Schema；不存在自由文本判定的目标（`REQ-PRODUCT-017`）。
- `RULE-EVENT-021`：Objective 进度只能由 Objective Matcher 消费已提交 DomainEvent 推进；模型文本、前端动画或未提交意图不推进进度；`maintain_condition` 类由周期检查（phase 4）对条件谓词求值。
- `RULE-EVENT-022`：AI 居民经标准 ActionProposal 参与 Quest；玩家不在场时 assignee 按 `Active/Warm/Background` 层照常推进（`DOC-TIME-005`），Quest 可在无玩家参与下完成或失败；不存在"等待玩家"的隐式暂停。
- `RULE-EVENT-023`：Deadline 到期经 TIME Scheduled Event（phase 0 expiry，`RULE-TIME-044`）原子判定：`offered` 过期转 `expired`；`accepted/active` 到期按模板声明转 `failed` 或 `expired`；到期判定与最后一刻完成事件按 Revision 先后裁决，不并发生效。
- `RULE-EVENT-024`：Quest 结果的奖励、赔偿与关系影响只通过 ECON Transaction 与已提交事件传播；Quest aggregate 不直接写余额、Inventory 或关系维度，发放失败不回滚 Quest 终态，而是登记 Aftermath Task（`DOC-EVENT-005`）。

## 5. 数据与接口

`DES-EVENT-004`：Quest aggregate：

```json
{
  "schema_version": 1,
  "quest_id": "01K1AB2CD3EF4GH5JK6MNP7QS1",
  "quest_template_id": "quest.rescue.trapped_miner",
  "origin_world_event_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "state": "active",
  "participants": [
    {"role": "issuer", "entity_id": "resident.mayor.aldric"},
    {"role": "assignee", "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS2"},
    {"role": "target", "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS3"}
  ],
  "objectives": [
    {
      "objective_id": "obj.reach_collapse_site",
      "objective_type": "reach_location",
      "parameters": {"destination_id": "node_semantic.mine.supported_work_face"},
      "required_count": 1,
      "completed_count": 1,
      "state": "completed"
    },
    {
      "objective_id": "obj.rescue_target",
      "objective_type": "protect_target",
      "parameters": {"target_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS3", "until_condition": "target_at_safe_point"},
      "required_count": 1,
      "completed_count": 0,
      "state": "active"
    }
  ],
  "objective_ordering": "sequential",
  "offer_expires_game_time": 22320,
  "deadline_game_time": 23040,
  "failure_policy": "failed",
  "version": 5
}
```

`objective_ordering` 允许 `sequential/parallel`；`sequential` 时后序 Objective 在前序完成前不接收进度。接口：

```text
instantiate_quest(command_id, quest_template_id, participants, origin) -> QuestResult
transition_quest(command_id, quest_id, expected_version, target_state, evidence) -> TransitionResult
apply_domain_event_to_objectives(event_envelope) -> [ObjectiveProgress]
list_open_quests(entity_id | null) -> RevisionStampedProjection
```

## 6. 正常流程

1. 事件善后、居民请求或镇长公告实例化 Quest（模板 + 参与者）。
2. `offered` 状态经对话或公告对 assignee 可见；接受形成 `accepted → active`。
3. Objective Matcher 订阅 DomainEvent 流，按匹配规则推进计数并原子提交进度。
4. 全部 Objective 完成即提交 `active → completed` 并登记奖励发放任务。
5. 终态后进入 `archived`，写入参与者可见的结果摘要供 MEMORY 消费。

## 7. 边界情况

- assignee 在 Quest 进行中昏迷/被俘（`RULE-FOUNDATION-025`）：Quest 不自动失败，Deadline 继续计时；模板可声明 `on_assignee_incapacitated` 为 `hold_open` 或 `reassignable`。
- `deliver_item` 的目标物品在途中被交易/丢失：进度不回退已完成计数，但最终交付校验以 ECON 所有权真值为准。
- `protect_target` 的 target 撤退到安全点后再次遇险：`maintain_condition` 语义在 Deadline 前持续求值，条件破坏时按模板判 `failed`。
- 同一 DomainEvent 匹配多个 Quest 的 Objective：全部推进，各自独立幂等（`(quest_id, objective_id, event_id)` 去重）。
- 玩家与 AI 居民同为候选 assignee：接受先提交者生效，后者收到 `offer_taken`。

## 8. 错误与降级

返回 `quest_template_unknown`、`participant_invalid`、`objective_schema_invalid`、`state_transition_illegal`、`version_stale`、`offer_taken` 或 `deadline_passed`。Matcher 处理失败保留事件游标重试；连续 terminal failure 时冻结该 Quest 进度并发布诊断事件，不阻塞其他 Quest 的事件消费。

## 9. 安全与性能

Quest 参与者只看到自身访问级别允许的描述字段；`investigate` 类 Objective 的线索揭示走 MEMORY 访问控制，不在 Quest 投影中泄漏 Secret（`RULE-FOUNDATION-024`）。Matcher 按 `objective_type + 关键实体 ID` 建订阅索引，避免每事件全表扫描；单世界同时 open Quest 上限 64。

## 10. 验收标准

- 九类 Objective 各有完成与失败 fixture，且判定只依赖已提交事件。
- 玩家完全不在场的 7 游戏日模拟中存在 Quest 被 AI 居民完成与失败的实例。
- Deadline 与完成事件竞争时结果由 Revision 顺序唯一决定。
- 非法状态转换与重复进度注入均被拒绝。
- 奖励发放失败不破坏 Quest 终态且留有 Aftermath Task。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-010` | `RULE-EVENT-019..020` 状态机与九类 Objective Schema |
| `TEST-EVENT-011` | `RULE-EVENT-021..022` 事件驱动进度与无玩家推进 |
| `TEST-EVENT-012` | `RULE-EVENT-023..024` Deadline 裁决与奖励边界 |

## 12. 关联文档

- `DOC-EVENT-001`：WorldEvent 与 Quest 的分离及来源
- `DOC-EVENT-005`：事件生成 Quest 与善后发放
- `DOC-TIME-005`：Active/Warm/Background 推进层
- `DOC-TIME-008`：Deadline expiry phase
- `DOC-AI-005`：居民参与 Quest 的 Action Catalog

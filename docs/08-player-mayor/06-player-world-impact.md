---
doc_id: DOC-PLAYER-006
title: 玩家影响世界的因果与事件边界
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-world-impact
  - player-command-causality
  - player-impact-projection
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-PLAYER-004
  - DOC-ECON-006
requirements:
  - REQ-PLAYER-006
last_updated: 2026-07-26
---

# 玩家影响世界的因果与事件边界

## 1. 目的

`REQ-PLAYER-006`：规定玩家如何通过已验证命令和不可丢 DomainEvent 在社会、经济、政治、空间、冲突与叙事维度影响世界，并保持可追踪因果、守恒和回放一致。

## 2. 非目标

本文不拥有关系计算、市场价格、Building aggregate、战斗结算、Quest/Event 生命周期或 Memory 写入；PLAYER 只定义命令来源、correlation 和玩家可见影响投影。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Causation | 直接导致一个事件的 committed command/event ID |
| Correlation | 一次玩家意图跨多个 Domain 的稳定关联 ID |
| Impact Projection | 从已提交事件派生的玩家可见后果摘要 |
| Direct Mutation | 绕过 owner validator 直接 set balance/relationship/position/state |
| Compensating Command | 产生反向新事件的恢复命令，不删除原历史 |

## 4. 规则与不变量

- `RULE-PLAYER-026`：玩家只能通过 registered PlayerCommand 或受限 MayorCommand 影响世界；普通模式禁止 Direct Mutation。
- `RULE-PLAYER-027`：每个玩家来源 DomainEvent 必须包含 `causation_id=command_id`、稳定 `correlation_id`、actor ResidentId、world Revision 和 GameTime。
- `RULE-PLAYER-028`：金钱、物品、位置、关系、战斗和建筑变化由各 owner 计算并原子提交；PLAYER 不接受 Client/文本声明的结果值。
- `RULE-PLAYER-029`：动画、toast、对话承诺文本和预测不是事实；只有 committed DomainEvent 可驱动持久投影。
- `RULE-PLAYER-030`：撤销使用新命令/补偿事件；不得删除、改写或重新编号原事件。

## 5. 因果 Envelope

```json
{
  "protocol_version": 1,
  "event_id": "01K1EVENT00000000000000001",
  "world_id": "01K1WORLD000000000000000001",
  "revision": 201,
  "type": "economy.transaction_committed",
  "game_time": 3120,
  "causation_id": "01K1COMMAND000000000000006",
  "correlation_id": "01K1CORRELATION00000000001",
  "actor_entity_id": "01K1RESIDENT0000000000001",
  "payload": {
    "transaction_id": "01K1TRANSACTION000000000001"
  },
  "render": {
    "cue": "trade_success"
  }
}
```

PLAYER 只拥有 `actor_entity_id` 的 binding resolution 与初始 correlation；`type/payload` 由 owner Schema 定义。一个 command 可产生多个同 Revision event，但每个写 aggregate 的 owner 和顺序必须确定。

## 6. 影响路径

| 维度 | 玩家命令示例 | Owner 事实 | 禁止的直接结果 |
|---|---|---|---|
| 社会 | talk、give_item、履约/违约 | social interpretation/relationship event | `set_affection=100` |
| 经济 | work、buy、sell、craft | Transaction、ownership、income、stock | `set_balance` |
| 政治 | 合法投票/请愿、Mayor governance | office/law/public budget event | 自称 authority |
| 空间 | move、door、build、repair | MAP position/WorldDiff/EVENT stage | teleport/edit collision |
| 冲突 | start_encounter、combat_action | COMBAT turn/result/health event | 指定命中/胜负 |
| 叙事 | 接受/推进结构化 Quest | EVENT objective transition | 自报“任务完成” |

## 7. 正常流程

1. PLAYER 认证 binding，创建 command/correlation ID。
2. Domain owner 在最新 Revision 验证能力、目标、资源、权限和 Reservation。
3. Unit of Work 原子写 current state、DomainEvent、Outbox 与 idempotency result。
4. 投影器按 Revision 更新公开世界、玩家日志和 UI；MEMORY/AI 只消费其有权观察的事件投影。
5. Client 渲染 event cue；若丢包按 Revision 补增量或 Snapshot。
6. 长期后果由后续 owner event 引用同 correlation 或上游 event causation，形成可审计链。

## 8. 并发与失败恢复

严格资源命令使用 `expected_revision`；可交换的输入也必须在 commit 前按最新状态重校验。Outbox 发送失败不回滚已提交事实，恢复后重发同一 event ID。跨 Domain 编排无法原子完成时使用显式 Saga 状态和 Reservation；失败产生补偿事件，不伪造成功。Impact projection 可重建，损坏时从事件日志重投影。

## 9. 隐私与可见性

公开 Impact Projection 只展示玩家有权知道的结果。“某人对你不满”可来自授权 social projection，但不得显示隐藏 relationship 数值、私人记忆、secret source 或模型 reasoning。Mayor 只能查看公共聚合；Admin audit 不是普通叙事事件，见 `DOC-PLAYER-009`。

## 10. 验收标准

- 六类影响均可从 PlayerCommand 追踪到 owner DomainEvent 和最终投影。
- 守恒、ownership、Collision、权限和战斗数值无法由 Client 指定。
- Outbox 重发、断线补帧和 Snapshot 后不重复后果。
- 失败 Saga 有确定补偿，历史事件不被删除。
- AI/Memory 消费的是受权事件投影，不获得 PLAYER 私有输入或全局 secret。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-021` | 六维 command→event→projection 因果链 |
| `TEST-PLAYER-022` | owner result injection 与 direct mutation 拒绝 |
| `TEST-PLAYER-023` | Outbox 重发、Revision 补帧与投影重建 |
| `TEST-PLAYER-024` | Saga failure、补偿事件与隐私过滤 |

## 12. 关联文档

- `DOC-FOUNDATION-002`：World Writer、Outbox 与 Domain boundary
- `DOC-FOUNDATION-005`：DomainEvent、Revision、守恒与幂等
- `DOC-ECON-006`：原子经济 Transaction
- `DOC-PLAYER-012`：E2E 因果验收 fixtures


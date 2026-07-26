---
doc_id: DOC-DIALOGUE-009
title: 对话的记忆与关系影响
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-event-emission
  - speech-act-social-category
depends_on:
  - DOC-DIALOGUE-005
  - DOC-DIALOGUE-008
  - DOC-MEMORY-002
  - DOC-MEMORY-006
  - DOC-MEMORY-011
requirements:
  - REQ-DIALOGUE-009
last_updated: 2026-07-26
---

# 对话的记忆与关系影响

## 1. 目的

`REQ-DIALOGUE-009`：定义对话如何以已提交事件的形式进入记忆与关系管道——DIALOGUE 提交哪些事件、每个 Speech Act 映射到哪个社交事件类别、玩家言行如何被居民长期记住——同时严守「DIALOGUE 只发事件，MEMORY 拥有写入与 delta 计算」的边界。

## 2. 非目标

本文不定义记忆写入资格与幂等（`DOC-MEMORY-002`）、关系 delta 的 base catalog、缩放与限幅（`DOC-MEMORY-006` 是 canonical owner）、玩家行为记忆策略（`DOC-MEMORY-011`）或 Commitment 履约追踪（MEMORY）。DIALOGUE 不计算任何 delta 数值。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Social Event Category | Speech Act 提交事件携带的社交类别标签，MEMORY base catalog 的查找键 |
| Dialogue Episode | 一次会话结束时提交的汇总事件，供 MEMORY 做 episode 级写入与摘要 |
| Broken Promise Signal | Commitment 违约由 MEMORY 判定后回流的事件，非 DIALOGUE 职责，此处仅作消费说明 |
| Player Influence | 玩家通过累次对话在居民记忆/关系中形成的长期印象，机制归 `DOC-MEMORY-011` |

## 4. 规则与不变量

- `RULE-DIALOGUE-052`：只有已提交 Speech Act 与会话终结事件可进入记忆与关系管道（`RULE-MEMORY-009..010`）；模型草稿、被拒响应、未提交玩家输入与被打断丢弃的迟到结果一律无社会影响。
- `RULE-DIALOGUE-053`：每个已提交 Speech Act 恰好携带一个 Social Event Category，映射由版本化表确定：`comfort → dialogue.comforted`、`apologize → dialogue.apologized`、`warn → dialogue.warned`、`refuse → dialogue.refused`、`promise(带 offer 且确认) → dialogue.promise_made`、`negotiate → dialogue.negotiated`、`greet/inform/ask/request/farewell → dialogue.smalltalk`、`lie → 按其表面类型映射`（说谎的表面行为是什么就映射什么，谎言败露的影响由后续揭穿事件承担）。
- `RULE-DIALOGUE-054`：关系 delta 完全由 MEMORY 以 `(category, 人格 projection, 当前 edge)` 确定性计算（`RULE-MEMORY-044..047`）；DIALOGUE 事件不携带任何目标向量、delta 建议或"好感 +5"字段。
- `RULE-DIALOGUE-055`：会话终结时提交一条 Dialogue Episode 事件：参与者、时长（GameTime）、utterance 数、各类别计数、ended reason；MEMORY 据此做 episode 记忆与低重要度合并，DIALOGUE 不预判重要性。
- `RULE-DIALOGUE-056`：旁听者的社会影响只经 `dialogue.utterance_overheard/v1`（`RULE-DIALOGUE-050`）走 witness/testimony 管道；旁听不触发说话者与旁听者之间的 direct-interaction 类别。
- `RULE-DIALOGUE-057`：玩家与居民对话产生的事件与居民间对话完全同构（同类别、同管道，`DOC-MEMORY-011` 决定玩家侧特化）；不存在"玩家光环"式的额外好感通道。
- `RULE-DIALOGUE-058`：每个 `(conversation_id, utterance_index)` 至多产生一次类别事件、每个 `conversation_id` 至多一条 Episode 事件；重放幂等返回原事件 ID。

## 5. 数据与接口

`DES-DIALOGUE-009`：Speech Act 社交事件与 Episode 事件载荷。

```json
{
  "schema_version": 1,
  "speech_act_event": {
    "event_type": "dialogue.speech_act_committed/v1",
    "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "utterance_index": 6,
    "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "addressed_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRU",
    "social_event_category": "dialogue.comforted",
    "privacy": "public",
    "category_map_version": 1
  },
  "episode_event": {
    "event_type": "dialogue.conversation_episode/v1",
    "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "participant_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRU", "01K1AB2CD3EF4GH5JK6MNP7QRV"],
    "duration_game_minutes": 12,
    "utterance_count": 9,
    "category_counts": {"dialogue.smalltalk": 6, "dialogue.comforted": 2, "dialogue.promise_made": 1},
    "ended_reason": "completed"
  }
}
```

事件不携带 utterance 原文之外 MEMORY 不需要的载荷；原文引用通过 `(conversation_id, utterance_index)` 定位，访问受会话 privacy 与 MEMORY AccessPolicy 约束。

## 6. 正常流程

1. Speech Act 原子提交时（`RULE-DIALOGUE-030`）同事务发出类别事件。
2. MEMORY 消费事件：为在场且满足感知资格的参与者写 episodic/testimony 记忆，为 speaker→addressee 有向边计算并提交关系 delta。
3. 会话终结统一 teardown 时发出 Episode 事件，MEMORY 做汇总写入与合并。
4. 确认后的承诺由 MEMORY 记为 Commitment；届期履约/违约事件回流后，影响下一次对话的 context 与关系。

## 7. 边界情况

- `refuse` 的关系影响不必为负：delta 由 MEMORY 结合人格与关系计算（正直居民拒绝行贿可能提升 respect）；DIALOGUE 不做方向假设。
- 一次会话同一 speaker 连续 5 次 `comfort`：5 条类别事件照发，重复社交行为的边际递减由 MEMORY 的 delta/合并规则处理。
- 会话因 `world_teardown` 终结：Episode 事件仍必须提交（世界关闭前的最后事务），保证无"未结算的社交经历"。
- 玩家骂人后立刻退出：已提交 utterance 的类别事件已生效，退出不撤销社会影响。
- `lie` 被当场识破不存在自动机制：识破只能来自后续事实事件与 belief 冲突（`DOC-MEMORY-010`），DIALOGUE 不发"被识破"事件。

## 8. 错误与降级

- MEMORY 消费失败或延迟：事件在事件流中持久存在，MEMORY 按自身恢复语义补处理；DIALOGUE 不重发也不感知。
- category map 版本不匹配：MEMORY 侧拒收并告警，DIALOGUE 事件保留原 `category_map_version` 供审计；禁止就地改写历史事件。

## 9. 安全与性能

- 事件只携带类别与引用，`private_requested` 会话的原文不进入事件流明文，秘密边界与 `DOC-MEMORY-009` 一致。
- 每 utterance 一条类别事件、每会话一条 Episode，事件量与对话量线性有界。

## 10. 验收标准

- 12 种 Speech Act 类型到类别的映射穷举一致；`lie` 按表面类型映射。
- 关系变化只出现在 MEMORY 提交的 `RelationshipChanged` 中，DIALOGUE 事件零 delta 字段。
- 重放 fixture：类别事件与 Episode 事件均不重复。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-017` | `RULE-DIALOGUE-052..055` 事件资格、类别映射、Episode 汇总 |
| `TEST-DIALOGUE-018` | `RULE-DIALOGUE-056..058` 旁听通道分离、玩家同构、幂等 |

## 12. 关联文档

- `DOC-DIALOGUE-005`（Speech Act 提交）、`DOC-DIALOGUE-008`（旁听事件）
- `DOC-MEMORY-002`（写入资格 canonical）、`DOC-MEMORY-006`（关系 delta canonical）、`DOC-MEMORY-010`（belief 冲突）、`DOC-MEMORY-011`（玩家行为记忆）

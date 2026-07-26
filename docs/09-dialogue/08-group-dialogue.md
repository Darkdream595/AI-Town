---
doc_id: DOC-DIALOGUE-008
title: 群体对话与旁听
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - group-turn-policy
  - dialogue-overhearing
depends_on:
  - DOC-DIALOGUE-001
  - DOC-DIALOGUE-002
  - DOC-DIALOGUE-005
  - DOC-AI-009
  - DOC-MEMORY-002
  - DOC-MEMORY-008
requirements:
  - REQ-DIALOGUE-008
last_updated: 2026-07-26
---

# 群体对话与旁听

## 1. 目的

`REQ-DIALOGUE-008`：定义多参与者会话（3 至 4 人）的轮次分配、点名应答与降员规则，以及非参与者在听力范围内旁听公开对话形成 witness 感知的条件，保证群聊有序、模型请求有界、旁听不成为窃密通道。

## 2. 非目标

本文不定义参与条件几何判定（`DOC-DIALOGUE-002`）、Speech Act 结构（`DOC-DIALOGUE-005`）、witness 记忆写入资格（`DOC-MEMORY-002` 是 canonical owner）或谣言传播（`DOC-MEMORY-008`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Group Conversation | `participant set` 大小 `3..4` 的 Conversation，`kind` 为 `group` |
| Turn Scheduler | 服务器为群聊选择下一位发言居民的确定性调度器 |
| Addressed Reply | utterance 的 `addressed_entity_id` 指向的参与者获得下一轮优先应答权 |
| Overhear Range | 旁听判定距离，`128 wu`（4 tile），需 Line of Sight 成立 |
| Bystander Witness | 旁听者对公开 utterance 形成的感知证据，供 MEMORY 按 witness 规则写入 |

## 4. 规则与不变量

- `RULE-DIALOGUE-045`：首版 `participant set` 上限 `4`（含玩家）；超员的加入请求被拒并返回 `group_full`。每对参与者独立满足 `DOC-DIALOGUE-002` 条件。
- `RULE-DIALOGUE-046`：Turn Scheduler 是唯一发言授权来源：同一时刻至多一位居民持有发言轮次、至多一个在途模型请求；居民发言必须持有当轮 `turn_grant_id`，无轮次的响应即使解码成功也拒收。
- `RULE-DIALOGUE-047`：轮次选择确定性优先级：`Addressed Reply 目标 > 被 request/ask 指向且未答复者 > 最久未发言者`；同级并列按 `participant_id` 字典序。玩家不占调度轮次——`awaiting_player` 期间玩家随时可发言，玩家发言后调度器重新裁决。
- `RULE-DIALOGUE-048`：降员规则：参与者退出/被打断后剩余 `>= 2` 则会话继续并向剩余者 context 注入退出事实；仅剩 1 人按 `participant_exit` 终结。中途加入按 `RULE-DIALOGUE-012` 不回溯历史。
- `RULE-DIALOGUE-049`：旁听条件：非参与者与说话者同 Scene、距离 `<= 128 wu`、Line of Sight 成立、且 utterance 所属会话 `privacy` 为 `public`；三者及 privacy 任一不满足则不产生 Bystander Witness。`private_requested` 会话只可被旁观到"在交谈"这一事实，内容不可旁听。
- `RULE-DIALOGUE-050`：Bystander Witness 是感知证据而非记忆本身：DIALOGUE 只提交 `dialogue.utterance_overheard/v1` 事件（含旁听者、utterance 引用、同 Revision 几何证据，满足 `RULE-MEMORY-011`）；是否写入记忆、可信度与后续谣言化由 MEMORY 决定。
- `RULE-DIALOGUE-051`：旁听不加入 participant set：旁听者无发言权、不出现在参与者 context 的 Speaker Projection 中；居民旁听后想插话必须走正常加入流程并经参与条件校验。

## 5. 数据与接口

`DES-DIALOGUE-008`：轮次授权与旁听事件载荷。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "turn_grant": {
    "turn_grant_id": "01K1AB2CD3EF4GH5JK6MNP7QT5",
    "granted_to": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "granted_for_utterance_index": 6,
    "grant_reason": "addressed_reply",
    "expires_real_ms": 20000
  },
  "overheard_event": {
    "event_type": "dialogue.utterance_overheard/v1",
    "bystander_id": "01K1AB2CD3EF4GH5JK6MNP7QT6",
    "utterance_ref": {"conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS", "utterance_index": 5},
    "observed_revision": 131,
    "distance_wu": 112.0,
    "line_of_sight": true
  }
}
```

`grant_reason` 封闭枚举：`addressed_reply / pending_question / longest_idle`。`expires_real_ms` 是模型响应的 RealTime deadline（对齐 `RULE-AI-052`，暂停不延长）；到期轮次收回并重新调度。

## 6. 正常流程

1. 群聊建立后调度器授予首轮（发起目标优先）。
2. 持轮居民走 `awaiting_model → Speech Act 提交`，其 `addressed_entity_id` 影响下一轮裁决。
3. 每条 utterance 提交时，对 Overhear Range 内满足条件的非参与者逐一提交 overheard 事件。
4. 玩家发言插入后调度器立即重新裁决；会话结束时未消费的 turn grant 一并作废。

## 7. 边界情况

- `addressed_entity_id` 指向已退出的参与者：语义校验失败按 `DOC-DIALOGUE-005` fallback；调度器按次级规则授轮。
- 两名旁听者互相看不见说话者但都在 128 wu 内：各自独立判定 Line of Sight，可能一人成 witness 一人不成。
- 玩家是旁听者：同样按 `RULE-DIALOGUE-049` 判定；公开对话文本对玩家 Client 可渲染为气泡，私密对话只渲染交谈动画不渲染文本。
- 说话者在 utterance 提交与旁听判定之间移动：以提交事务的同 Revision 坐标为准，单次判定。
- 群聊中两居民同时被调度候选（并列 idle 时长）：字典序裁决，可复现。

## 8. 错误与降级

- turn grant 到期且模型未返回：收回轮次、cancel 在途请求、该居民本轮记为跳过；连续两次跳过触发其 fallback 告别退出，避免僵尸参与者拖死群聊。
- 旁听判定的几何查询失败：fail closed 不产生 witness 事件（宁可漏听不可误听）。
- overheard 事件风暴（广场大群聊）：每 utterance 旁听判定上限 `8` 名候选，超出按距离最近截断并记录截断计数。

## 9. 安全与性能

- 群聊模型并发仍受 `DOC-AI-009` 全局并发上限约束，Turn Scheduler 保证每会话至多 1 在途请求，天然限流。
- 旁听内容与参与内容走同一 privacy 闸门，`private_requested` 内容永不进入旁听者事件，秘密不因群聊外溢。
- 旁听判定复杂度每 utterance `O(附近实体数)`，由空间索引提供候选。

## 10. 验收标准

- 4 人群聊 10 轮 fixture：轮次序列确定可复现，无并发双请求。
- 旁听矩阵（距离 127/128/129 wu × LoS × privacy）全组合判定正确。
- 降员到 1 人自动终结；中途加入者读不到历史。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-015` | `RULE-DIALOGUE-045..048` 上限、轮次授权与裁决、降员 |
| `TEST-DIALOGUE-016` | `RULE-DIALOGUE-049..051` 旁听条件、witness 事件、旁听者无权限 |

## 12. 关联文档

- `DOC-DIALOGUE-002`（参与条件）、`DOC-DIALOGUE-005`（点名字段）、`DOC-DIALOGUE-007`（打断降员）
- `DOC-AI-009`（并发上限）、`DOC-MEMORY-002`（witness 写入资格 canonical）、`DOC-MEMORY-008`（谣言化）

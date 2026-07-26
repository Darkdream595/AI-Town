---
doc_id: DOC-DIALOGUE-001
title: 会话生命周期与状态机
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - conversation-state-machine
  - conversation-aggregate-lifecycle
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-006
  - DOC-AI-001
  - DOC-AI-005
  - DOC-TIME-002
  - DOC-PLAYER-005
requirements:
  - REQ-DIALOGUE-001
last_updated: 2026-07-26
---

# 会话生命周期与状态机

## 1. 目的

`REQ-DIALOGUE-001`：定义 Conversation aggregate 的权威状态机、状态迁移命令、幂等与恢复语义，保证服务器权威地管理玩家与居民、居民与居民之间的对话，任何 Client 显示或模型输出都不构成会话事实。

## 2. 非目标

本文不定义距离/视线参与条件（`DOC-DIALOGUE-002`）、上下文构建（`DOC-DIALOGUE-003`）、打断优先级细则（`DOC-DIALOGUE-007`）或群组轮次（`DOC-DIALOGUE-008`）；本文只拥有状态机与生命周期。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Conversation | 一次对话的权威 aggregate，携带 `conversation_id`、参与者、状态与最近 utterance 游标 |
| Utterance | 一次已提交发言，纯文本 payload，属于某个 Conversation 的追加序列 |
| `awaiting_player` | 等待玩家输入的子状态；含玩家参与者的会话在此期间由本域会话 Pause Token 保持世界 0×（`RULE-DIALOGUE-005`） |
| `awaiting_model` | 已发出居民响应模型请求、结果未提交回来的子状态 |
| `interrupted` | 被更高优先级事件挂起、可恢复或终结的状态 |
| Conversation Pause Token | DIALOGUE 以 `owner_domain="dialogue"` 为含玩家参与者的会话申请的恰一枚 blocking Pause Token，与 PLAYER 输入框 token 相互独立 |
| Privacy | 会话私密性封闭枚举 `public / private_requested`，创建时固定，是旁听闸门（`RULE-DIALOGUE-049`）与事件脱敏（`DOC-DIALOGUE-009`）的唯一输入 |
| Ended Reason | 封闭枚举：`completed / participant_left / participant_unavailable / timeout / superseded / admin / world_teardown` |

## 4. 规则与不变量

- `RULE-DIALOGUE-001`：Conversation 状态只允许 `starting → active ⇄ awaiting_player / awaiting_model → interrupted → active / ended`，`ended` 为终态；非法迁移一律 fail closed 并记录 rejected 结果。
- `RULE-DIALOGUE-002`：状态迁移只由服务器在最新 Revision 校验后提交；Client 打开/关闭对话框、模型返回文本、动画完成都不构成迁移事实（与 `RULE-AI-004` 一致）。
- `RULE-DIALOGUE-003`：每次迁移与对应 `dialogue.conversation_state_changed/v1` DomainEvent、幂等结果在同一事务提交；失败 Revision 不增长。
- `RULE-DIALOGUE-004`：同一参与者（玩家或居民）在 Overworld 同时最多处于一个非 `ended` Conversation 的 participant set；新会话请求冲突时按 `DOC-DIALOGUE-007` 的打断优先级裁决。
- `RULE-DIALOGUE-005`：含玩家参与者的 Conversation 在 `starting → active` 提交成功的同一事务内，由 DIALOGUE 以 `owner_domain="dialogue"`、reason `dialogue_input` acquire 恰一枚 blocking Pause Token（`RULE-TIME-009`），`token_id` 记录于投影 `pause_token_id`；该 token 绑定 `active / awaiting_player / awaiting_model` 全部交互态（即 `awaiting_model` 期间世界同样保持 0×，`RULE-TIME-007`）。迁入 `interrupted` 或 `ended` 时由 DIALOGUE 以同一 `token_id` 幂等释放（`RULE-TIME-008`），`interrupted → active` 恢复时以新 `token_id` 重新 acquire。居民间会话（无玩家参与者）不创建任何 Pause Token。
- `RULE-DIALOGUE-006`：Conversation 内的 utterance 序号从 0 连续递增、只追加不改写；重放相同 command 最多产生一条 utterance。
- `RULE-DIALOGUE-078`：token 拓扑与回收：玩家自然语言输入框自身的 `dialogue_input` token 由 PLAYER 域按 `RULE-PLAYER-021` 独立申请与释放，与本域会话 token 是两枚独立 token 的嵌套关系（任一在场即 0×，`RULE-TIME-007`）；DIALOGUE 不释放、不依赖 PLAYER 的 token，会话全程暂停语义仅由本域会话 token 保证。异常退出（断线、进程崩溃）时旧进程不释放 token，由 DIALOGUE 有界恢复流程根据已提交会话终态释放，或随 `world_teardown` 统一 teardown 回收（对齐 `DOC-TIME-002`），禁止按 RealTime 猜测释放。
- `RULE-DIALOGUE-079`：Conversation `privacy` 为创建时固定的封闭枚举 `public / private_requested`，canonical 落库于 `DES-DIALOGUE-001` 投影：居民经 `talk` 发起时由 Commit Adapter 从 `talk_parameters.privacy` 注入（`DOC-AI-005`）；玩家发起（无 `talk_parameters`）默认 `public`。创建后不可变更——既不可中途放宽也不可收紧，改变私密性只能结束并新建会话；`RULE-DIALOGUE-049` 旁听闸门与 `DOC-DIALOGUE-009` 事件脱敏以本字段为唯一输入。

## 5. 数据与接口

`DES-DIALOGUE-001`：Conversation 持久化投影。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "kind": "player_to_resident",
  "privacy": "public",
  "participant_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRX", "01K1AB2CD3EF4GH5JK6MNP7QRV"],
  "initiator_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "state": "awaiting_player",
  "utterance_cursor": 3,
  "created_revision": 120,
  "created_game_time": 5400,
  "last_activity_game_time": 5400,
  "pause_token_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "ended_reason": null
}
```

命令：`dialogue.start_conversation`、`dialogue.submit_player_speech`、`dialogue.commit_utterance`（服务器内部）、`dialogue.interrupt`、`dialogue.resume`、`dialogue.end`。外部命令均携带 Command Envelope（`DOC-FOUNDATION-004`）与 `expected_revision`。`dialogue.start_conversation` 携带 `privacy`：居民发起由 Commit Adapter 从 `talk_parameters.privacy` 注入，玩家发起省略时默认 `public`（`RULE-DIALOGUE-079`）。`pause_token_id` 仅在会话当前持有会话 Pause Token 时非 null，`interrupted / ended` 状态下必须为 null（`RULE-DIALOGUE-005`）。

## 6. 正常流程

1. 发起方提交 `dialogue.start_conversation`，服务器按 `DOC-DIALOGUE-002` 校验参与条件，创建 Conversation（`starting → active`）并落库 `privacy`；含玩家参与者时同事务 acquire 会话 Pause Token（`RULE-DIALOGUE-005`）。
2. 玩家发言走 `dialogue.submit_player_speech`（`PlayerSpeechCommand`），提交 utterance 后进入 `awaiting_model`，向 AI Request Queue 发起居民响应请求（`DOC-AI-009`）。
3. 居民响应经 `DOC-DIALOGUE-005` 响应 Schema 与 Domain validation 后以 `dialogue.commit_utterance` 提交，回到 `awaiting_player` 或 `active`。
4. 任一方正常结束走 `dialogue.end`（reason `completed`），释放 pause token 与注意力资源。

## 7. 边界情况

- 玩家关闭输入框等同提交 `dialogue.end`，不是忽略 pause token。
- `awaiting_model` 期间玩家再次输入：排队为下一条 `PlayerSpeechCommand`，不覆盖在途请求。
- 会话参与者进入 Encounter transition 或离开 Scene：迁移到 `interrupted` 并释放会话 Pause Token（恢复时重新 acquire，`RULE-DIALOGUE-005`），恢复条件不满足则在 deadline 后 `ended`（`participant_unavailable`）。
- 世界关闭/切换：所有非终态 Conversation 以 `world_teardown` 终结并提交事件，不留悬挂 token。

## 8. 错误与降级

- 模型请求超时/取消：按 `RULE-AI-051..053` 处理；Conversation 迁移到 `interrupted` 并可由 Utility fallback（`DOC-AI-011`）生成模板化短句恢复，恢复失败则 `ended`（`timeout`）。
- 过期 Revision 或重复 command：返回 idempotent 原结果或 conflict，不产生第二条 utterance。
- 任何状态校验失败：整次命令失败，不留半迁移状态。

## 9. 安全与性能

- 状态机不接触秘密内容；payload 可见性由 `DOC-DIALOGUE-003` 在上下文构建期过滤。
- 每世界非终态 Conversation 数量有界（参与者数上限决定），无后台轮询；迁移事件驱动。
- pause token 泄漏会破坏 `RULE-TIME-007`，因此所有终结路径必须经过统一 teardown 函数。

## 10. 验收标准

- 状态机所有合法/非法迁移有穷举测试；非法迁移全部 fail closed。
- 断线恢复后 Conversation 从持久化投影重建，pause token 与 utterance 游标一致；恢复流程之外无任何路径可释放他域 token。
- 重复提交同一发言 command 只产生一条 utterance 与一个事件。
- `privacy` 在创建后任何命令都无法变更；居民发起与玩家发起的落库值可分别验证。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-001` | `RULE-DIALOGUE-001..003` 状态机迁移合法性与事件原子提交 |
| `TEST-DIALOGUE-002` | `RULE-DIALOGUE-004..006` 参与者独占、pause token 生命周期、utterance 幂等 |
| `TEST-DIALOGUE-028` | `RULE-DIALOGUE-078..079` 会话 token 与输入框 token 嵌套独立、异常回收、privacy 落库与不可变更 |

## 12. 关联文档

- `DOC-DIALOGUE-002`（参与条件）、`DOC-DIALOGUE-003`（上下文）、`DOC-DIALOGUE-007`（打断）、`DOC-DIALOGUE-008`（旁听闸门消费 privacy）、`DOC-DIALOGUE-012`（测试）
- `DOC-AI-001`、`DOC-AI-005`（`talk_parameters.privacy` 来源）、`DOC-AI-009`（模型请求生命周期）、`DOC-TIME-002`（暂停 token）、`DOC-PLAYER-005`（输入框 token 归属）、`DOC-FOUNDATION-006`（ID/时间基元）

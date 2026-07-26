---
doc_id: DOC-DIALOGUE-007
title: 打断、退出与取消
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-interruption-priority
  - dialogue-cancellation-policy
depends_on:
  - DOC-DIALOGUE-001
  - DOC-DIALOGUE-002
  - DOC-TIME-002
  - DOC-TIME-007
  - DOC-AI-009
requirements:
  - REQ-DIALOGUE-007
last_updated: 2026-07-26
---

# 打断、退出与取消

## 1. 目的

`REQ-DIALOGUE-007`：定义会话被打断的优先级全序、`interrupted` 状态的进入/恢复/终结条件、参与者主动退出语义，以及在途模型请求与意图确认的取消规则，保证更高优先级的世界事件总能夺走注意力且不留悬挂资源。

## 2. 非目标

本文不定义状态机本身（`DOC-DIALOGUE-001`）、Attention Reservation 的创建（`DOC-DIALOGUE-002`）、AI 请求取消机制（`DOC-AI-009` 是 cancel 语义 canonical owner）或并发动作冲突仲裁（`DOC-TIME-007`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Interrupt Source | 触发打断的封闭枚举来源：`world_teardown / combat_encounter / safety_emergency / participant_exit / higher_priority_conversation / condition_lost / timeout` |
| Interrupt Priority | 来源的整数优先级，越大越强，全序见第 5 节 |
| Resume Window | `interrupted` 后允许恢复的窗口，默认 `30 game minutes` |
| Graceful Exit | 经 `farewell`/玩家关闭对话框的正常退出，走 `ended(completed)` 或 `ended(participant_left)` |
| Forced Interrupt | 无告别话语的立即挂起，由高优先级来源触发 |

## 4. 规则与不变量

- `RULE-DIALOGUE-038`：Interrupt Priority 全序固定为 `world_teardown(100) > combat_encounter(80) > safety_emergency(70) > participant_exit(50) = condition_lost(50) > higher_priority_conversation(40) > timeout(20)`；只有优先级严格高于会话当前活动的来源才能触发 Forced Interrupt，相等或更低者排队或被拒。
- `RULE-DIALOGUE-039`：`combat_encounter` 与 `safety_emergency` 打断不等待当前 utterance 或模型响应完成：立即迁移 `interrupted`，对在途模型请求发 cancel（`RULE-AI-051`），迟到结果 discarded，不提交为 utterance。
- `RULE-DIALOGUE-040`：玩家任意时刻可 Graceful Exit；居民退出必须经 Speech Act `end_conversation` 或作为 Forced Interrupt 的当事人。居民不因模型失败而"沉默消失"——失败路径必须走 `DOC-DIALOGUE-005` fallback 告别或 `ended(timeout)`。
- `RULE-DIALOGUE-041`：进入 `interrupted` 时原子完成：挂起会话、取消在途请求、过期未确认的意图 candidate（`RULE-DIALOGUE-023` 的 `expired`）、按参与者去留释放或保留 Attention Reservation、释放 `awaiting_player` 的 pause token。
- `RULE-DIALOGUE-042`：Resume Window 内当且仅当全部剩余参与者仍满足 `DOC-DIALOGUE-002` 参与条件且打断源已解除时可恢复到 `active`；窗口以 GameTime 计量，暂停期间不流逝；超窗按来源映射 ended reason（`combat_encounter/safety_emergency → participant_unavailable`，`timeout → timeout`）。
- `RULE-DIALOGUE-043`：`higher_priority_conversation` 只在新会话请求带有更高 TIME priority class（玩家发起、紧急事件驱动）时成立；居民日常闲聊不能互相抢占。被抢占会话进入 `interrupted` 并遵循同一 Resume Window。
- `RULE-DIALOGUE-044`：所有打断、恢复、终结迁移与 `dialogue.conversation_state_changed/v1` 事件同事务提交并携带 `interrupt_source`；重放同一打断 command 幂等返回原结果。

## 5. 数据与接口

`DES-DIALOGUE-007`：打断命令与裁决记录。

```json
{
  "schema_version": 1,
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QT1",
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "interrupt_source": "combat_encounter",
  "interrupt_priority": 80,
  "source_event_id": "01K1AB2CD3EF4GH5JK6MNP7QT2",
  "affected_participant_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRV"],
  "decision": "granted",
  "resume_deadline_game_time": 5440,
  "cancelled_model_request_ids": ["01K1AB2CD3EF4GH5JK6MNP7QT3"],
  "expired_intent_candidate_ids": []
}
```

`decision` 封闭枚举：`granted / rejected_lower_priority / rejected_terminal_state / duplicate`。接口：`dialogue.interrupt(command) -> InterruptResult`、`dialogue.resume(command_id, conversation_id, expected_revision) -> ResumeResult`。打断命令只能由服务器内部 owner（COMBAT、TIME、DIALOGUE 调度）或玩家 Graceful Exit 网关构造，Client 不能直接注入 `interrupt_source`。

## 6. 正常流程

1. 打断源产生已提交事件（Encounter 开始、危险信号、参与者跨 Scene）。
2. DIALOGUE 按 `RULE-DIALOGUE-038` 裁决，granted 则执行 `RULE-DIALOGUE-041` 的原子挂起。
3. 打断源解除后，任一参与者的恢复触发器（Encounter 结束事件、玩家重新交互）调用 `dialogue.resume`，复验参与条件后回到 `active`。
4. 超窗或复验失败：统一 teardown，终结并释放全部资源。

## 7. 边界情况

- 打断到达时会话已 `ended`：`rejected_terminal_state`，幂等无副作用。
- 两个打断源同 Tick 到达：按优先级取最高者记录为 `interrupt_source`，次高者作为审计附注；恢复条件须两源都解除。
- `awaiting_model` 中玩家 Graceful Exit：先取消在途请求再终结；迟到响应不产生"结束后的幽灵发言"。
- 群组会话部分参与者被抢走（其一进入战斗）：若剩余参与者 `>= 2` 且含发起语境，会话降员继续（`DOC-DIALOGUE-008`），不进入 `interrupted`；仅剩 1 人时按 `participant_exit` 终结。
- 恢复后 utterance 游标不变，上下文重建时打断事实作为一条系统级摘要进入 History Summary，供居民自然接续（"刚才说到哪了"）。

## 8. 错误与降级

- cancel 发送失败（worker 不可达）：会话照常迁移；迟到结果在提交口按 conversation 状态拒收，双保险。
- Reservation 释放失败：进入一致性审计路径，禁止静默泄漏（对齐 `DOC-DIALOGUE-002` 泄漏检查）。
- resume 复验期间条件抖动（刚好走出又走回）：以复验事务的 Revision 快照为准，单次判定。

## 9. 安全与性能

- 打断裁决为纯优先级比较，O(1)；不给低优先级来源任何"等待重试风暴"的路径（rejected 即终局，除非新事件）。
- Client 无法伪造高优先级打断，也无法通过打断跳过 `RULE-DIALOGUE-005` 的 pause token 释放审计。

## 10. 验收标准

- 全部 7 种 Interrupt Source × 会话各状态的裁决矩阵有穷举测试。
- 战斗打断 fixture：模型迟到结果 0 条成为 utterance；恢复后接续摘要存在。
- 任意打断/恢复/终结路径后无悬挂 pause token、Reservation 与模型请求。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-013` | `RULE-DIALOGUE-038..040` 优先级全序、立即打断、退出语义 |
| `TEST-DIALOGUE-014` | `RULE-DIALOGUE-041..044` 原子挂起、Resume Window、抢占限制、幂等 |

## 12. 关联文档

- `DOC-DIALOGUE-001`（状态机）、`DOC-DIALOGUE-002`（参与条件复验）、`DOC-DIALOGUE-008`（群组降员）
- `DOC-TIME-002`（pause token）、`DOC-TIME-007`（并发冲突）、`DOC-AI-009`（请求取消 canonical）、`DOC-COMBAT-001`（Encounter 边界）

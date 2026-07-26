---
doc_id: DOC-TIME-009
title: 游戏关闭暂停与重启
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - closed-game-time-semantics
  - shutdown-quiescence
  - restart-clock-rebase
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-001
  - DOC-TIME-002
  - DOC-TIME-006
  - DOC-TIME-007
  - DOC-TIME-008
requirements:
  - REQ-TIME-009
last_updated: 2026-07-26
---

# 游戏关闭暂停与重启

## 1. 目的

`REQ-TIME-009`：定义正常关闭、意外崩溃、离线期间和重启恢复的时间语义。世界关闭后绝不按现实离线时长推进；重启从最后一致 Revision、GameTime、Clock Phase、Queue、Long Action 和 Reservation 恢复。

## 2. 非目标

本文不定义 SQLite 表、Snapshot 格式、Launcher UI 或备份保留数量；RELEASE owner 持久化 TIME 发布的 checkpoint projection，TIME 不直接执行 SQL。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Quiescence | 停止接受普通写命令、冻结 clock，并等待当前事务到达明确提交边界 |
| Shutdown Checkpoint | 锚定 Revision 的 TIME 恢复投影 |
| Offline Interval | 进程不运行期间的墙钟差；仅可显示，不参与 GameTime |
| Monotonic Rebase | 新进程建立新的 Tick deadline，不沿用旧 monotonic 数值 |
| In-flight AI Record | 关闭时仍未返回的模型请求记录；不代表行动事实 |
| Recovery Barrier | 全量恢复和 invariant 通过前禁止 clock/Tick 写提交 |

## 4. 规则与不变量

- `RULE-TIME-049`：正常关闭顺序必须是 `acquire shutdown pause → stop new ordinary writes → finish/rollback current transaction → persist checkpoint → stop process`。
- `RULE-TIME-050`：Offline Interval 无论长度均使 GameTime delta=0、Clock Phase delta=0、long-action work delta=0、GameTime Reservation expiry delta=0。
- `RULE-TIME-051`：重启必须从 checkpoint + Event Log 重建 Event Queue、Scheduler、Long Action 和 Reservation，并在解除 Recovery Barrier 前运行跨系统 invariant。
- `RULE-TIME-052`：旧进程 in-flight AI response 不可在新进程无条件提交；重启后只能使用已持久记录重放或重新构造请求，并在最新 Revision 校验。
- `RULE-TIME-053`：新进程 Tick Sequence 从 checkpoint 的 next value 继续，但 monotonic deadline 以启动时 `now + 100 ms` 重建，不补离线 Tick。
- `RULE-TIME-054`：恢复失败必须保持 paused/error state，不得重置 GameTime、清空队列或猜测长任务完成。

## 5. 数据与接口

`DES-TIME-009`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/shutdown-checkpoint/v1",
  "type": "object",
  "required": ["schema_version", "world_id", "revision", "game_time", "clock_phase_quanta", "next_tick_sequence", "event_queue_hash", "scheduler_hash", "long_action_hash", "reservation_hash", "shutdown_state"],
  "properties": {
    "schema_version": {"const": 1},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "revision": {"type": "integer", "minimum": 0},
    "game_time": {"type": "integer", "minimum": 0},
    "clock_phase_quanta": {"type": "integer", "minimum": 0, "maximum": 19},
    "next_tick_sequence": {"type": "integer", "minimum": 0},
    "event_queue_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "scheduler_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "long_action_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "reservation_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "shutdown_state": {"const": "checkpointed"}
  },
  "additionalProperties": false
}
```

状态机：

```text
running -> quiescing -> checkpointing -> checkpointed -> stopped
running -- crash --> stopped_ungraceful
checkpointed/stopped_ungraceful -> recovering -> paused_ready -> running
recovering -- audit failure --> recovery_failed
```

接口：

```text
begin_shutdown(command_id) -> QuiescenceBarrier
build_time_checkpoint(revision) -> TimeCheckpointProjection
restore_time_runtime(snapshot, event_tail) -> TimeRecoveryReport
release_startup_pause(command_id) -> ClockControlResult
```

## 6. 正常流程

1. Shutdown coordinator 获取 shutdown Pause Token。
2. Gateway 停止普通写入，World Writer 完成当前事务；未开始命令保留可解释拒绝。
3. TIME 输出 checkpoint projection，RELEASE 同 Revision 持久化并校验 Hash。
4. 重启先建立 Recovery Barrier，重放状态/事件并恢复各 TIME 队列。
5. 比较 Hash、Revision、Seed sequence、Reservation 和 Long Action。
6. audit 通过进入 paused_ready；玩家/启动流程明确释放 startup pause 后才运行。

## 7. 边界情况

- crash 发生在 checkpoint 写入中：RELEASE 选择最后完整 checkpoint + Event tail，TIME 不信任半写文件。
- 已完成模型响应在进程退出前未提交：它不是事实；若有完整 replay record 可重新入验证链，否则按 AI recovery policy 重请求或 fallback。
- 玩家在 4× 时关闭：保存 requested speed=4 和 Clock Phase；重启仍先 paused_ready，不自动补时。
- GameTime Reservation 关闭前已到期但未处理：重启恢复后按原 due order 处理，不能按 offline interval 扩大逾期。
- 系统墙钟回拨、时区变化或夏令时不影响任何恢复字段。

## 8. 错误与降级

Hash、Revision、queue occurrence 或 Reservation 不一致返回 `TIME_RECOVERY_AUDIT_FAILED`。正常 shutdown 超过 RealTime 10 秒时允许 UI 提示强制退出，但强制退出按 crash recovery 处理，不能宣称已安全保存。

## 9. 安全与性能

checkpoint 不含 API Key、Prompt 原文、Secret 或 Chain of Thought。恢复扫描按明确 world 文件和 Event tail，有界且在 Recovery Barrier 下执行。关闭期间拒绝新模型请求和新长任务。

## 10. 验收标准

- 关闭 1 分钟、1 小时、30 天后重启均保持相同 GameTime/Clock Phase。
- 正常退出和五个 crash 注入点均恢复到最后完整 Revision。
- Queue、Long Action、Reservation、Seed sequence 的恢复 Hash 一致。
- 恢复失败保持 paused 且不破坏原文件。
- 重启不会使用旧 monotonic deadline 补做离线 Tick。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-025` | `RULE-TIME-049..050` shutdown order 与 zero offline delta |
| `TEST-TIME-026` | `RULE-TIME-051..053` recovery/rebase |
| `TEST-TIME-027` | `RULE-TIME-054` corruption 不猜测恢复 |

## 12. 关联文档

- `DOC-FOUNDATION-001`：关闭后暂停的产品要求
- `DOC-TIME-002`：shutdown/startup Pause Token
- `DOC-TIME-010`：AI replay 与 Seed sequence
- `DOC-RELEASE-003`：Snapshot/Event Log 持久化
- `DOC-RELEASE-006`：损坏恢复

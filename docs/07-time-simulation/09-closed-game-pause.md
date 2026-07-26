---
doc_id: DOC-TIME-009
title: 游戏关闭暂停与重启
version: 1.0.3
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
- `RULE-TIME-074`：Shutdown Checkpoint 必须保存 requested speed、speed cap、backpressure counters、Clock Control version 与 Pause Ledger Hash；恢复后先加入 recovery/startup blocking token，再按 `DOC-TIME-002` 唯一公式重算 effective speed，禁止直接把 requested speed 当作 effective speed。
- `RULE-TIME-076`：v1、Recovery Evidence 与 v2 必须在 upcast 前/后执行完整 value validation；禁止把 numeric string 强制转换成 number，禁止只检查字段名后宣称 strict validation。

## 5. 数据与接口

`DES-TIME-009`：Legacy v1 是 upcaster 唯一接受的旧输入形状；保留其 strict Schema，禁止把任意旧 JSON 当作 checkpoint：

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

Current strict v2：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/shutdown-checkpoint/v2",
  "type": "object",
  "required": ["schema_version", "world_id", "revision", "game_time", "clock_phase_quanta", "requested_speed_multiplier", "speed_cap_multiplier", "backpressure_overload_windows", "backpressure_healthy_real_ms", "clock_control_version", "pause_ledger_hash", "next_tick_sequence", "event_queue_hash", "scheduler_hash", "long_action_hash", "reservation_hash", "shutdown_state"],
  "properties": {
    "schema_version": {"const": 2},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "revision": {"type": "integer", "minimum": 0},
    "game_time": {"type": "integer", "minimum": 0},
    "clock_phase_quanta": {"type": "integer", "minimum": 0, "maximum": 19},
    "requested_speed_multiplier": {"enum": [0, 0.5, 1, 2, 4]},
    "speed_cap_multiplier": {"enum": [0.5, 1, 2, 4]},
    "backpressure_overload_windows": {"type": "integer", "minimum": 0, "maximum": 6},
    "backpressure_healthy_real_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
    "clock_control_version": {"type": "integer", "minimum": 1},
    "pause_ledger_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
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

完整 v1 input fixture：

```json
{
  "schema_version": 1,
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 820,
  "game_time": 1830,
  "clock_phase_quanta": 6,
  "next_tick_sequence": 40822,
  "event_queue_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "scheduler_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "long_action_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "reservation_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "shutdown_state": "checkpointed"
}
```

对应的完整 canonical Evidence fixture，严格符合 `DOC-TIME-002` 的 `ClockControlRecoveryEvidence/v1`：

```json
{
  "schema_version": 1,
  "evidence_type": "clock_control_recovery",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "checkpoint_revision": 820,
  "requested_speed_multiplier": 4,
  "speed_cap_multiplier": 1,
  "effective_speed_multiplier": 0,
  "active_blocking_token_count": 1,
  "backpressure_overload_windows": 2,
  "backpressure_healthy_real_ms": 0,
  "clock_control_version": 17,
  "pause_ledger_hash": "aef5b1cc44fafa992bac6022d8ba9bf61dbc42a080ea5961f55aabbe263fcbb3"
}
```

重建 Pause Ledger fixture；其 canonical JSON SHA-256 正是 evidence 的 `pause_ledger_hash`：

```json
[
  {
    "token_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "owner_domain": "time",
    "reason": "shutdown",
    "scope": "overworld",
    "acquired_at_game_time": 1830
  }
]
```

精确 expected v2 / strict round-trip fixture：

```json
{
  "schema_version": 2,
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 820,
  "game_time": 1830,
  "clock_phase_quanta": 6,
  "requested_speed_multiplier": 4,
  "speed_cap_multiplier": 1,
  "backpressure_overload_windows": 2,
  "backpressure_healthy_real_ms": 0,
  "clock_control_version": 17,
  "pause_ledger_hash": "aef5b1cc44fafa992bac6022d8ba9bf61dbc42a080ea5961f55aabbe263fcbb3",
  "next_tick_sequence": 40822,
  "event_queue_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "scheduler_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "long_action_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "reservation_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "shutdown_state": "checkpointed"
}
```

`DES-TIME-014`：v1→v2 upcast 是纯函数：

```text
upcast_shutdown_checkpoint_v1(
  strict_v1_checkpoint,
  strict_clock_control_recovery_evidence_v1,
  reconstructed_pause_ledger
) -> strict_v2_checkpoint | RecoveryError
```

算法固定为：

1. 分别按 strict v1 Schema 和 `ClockControlRecoveryEvidence/v1` 校验 required、类型、enum 与 `additionalProperties:false`。
2. 断言 `checkpoint.world_id == evidence.world_id` 且 `checkpoint.revision == evidence.checkpoint_revision`。
3. 从 Event Log 重建该 Revision 的 active Pause Ledger，按 `DOC-TIME-002` 算法重算 hash 与 blocking token count，并与 evidence 比较。
4. 用唯一 speed 公式重算 evidence effective；不一致即拒绝。
5. 复制 v1 的全部 10 个状态字段；把 `schema_version` 改为 2；仅从 evidence 复制 requested、cap、两个 backpressure counter、control version 和 ledger hash。
6. 对输出执行 strict v2 Schema 校验；canonical serialize/deserialize 后逐个比较全部 v2 required 字段。

同一输入重复 upcast 必须产生 byte-identical canonical v2，且不增长 Revision、不追加 DomainEvent。输入已经是 valid v2 时只做 strict validation 后返回 canonical 等价值。

`DES-TIME-015`：三个 validator 是 upcaster 的强制 Port：

```text
validate_shutdown_checkpoint_v1(value)
validate_clock_control_recovery_evidence_v1(value)
validate_shutdown_checkpoint_v2(value)
```

每个 validator 必须实际执行其 Schema 的全部 `required`、`additionalProperties:false`、`type`、integer、`enum`、`minimum/maximum`、`pattern` 与 `const`。验证按 JSON value type 进行：例如字符串 `"1830"` 不得被转换为 integer 1830，`speed_cap_multiplier=3` 不得被夹到合法倍率，短 hash/非法 ULID 不得补齐。任一 constraint failure 统一返回 `TIME_RECOVERY_AUDIT_FAILED`。

`DOC-TIME-012` 第 10.1 节给出无项目依赖、实际可执行的 PowerShell 5.1 reference validator；实现语言可以不同，但合法/非法 fixture 的结果必须逐项一致。

安全失败：

| 条件 | 结果 |
|---|---|
| 无同 Revision Evidence | `TIME_RECOVERY_EVIDENCE_MISSING` |
| Evidence 缺 required 或有额外字段 | `TIME_RECOVERY_AUDIT_FAILED` |
| world/revision、ledger hash/count 或 effective 不一致 | `TIME_RECOVERY_AUDIT_FAILED` |
| v2 输出 strict validation/round-trip 失败 | `TIME_RECOVERY_AUDIT_FAILED` |

任一失败均保持 Recovery Barrier、保持 source v1 bytes 不变、不得写 v2、不得推进 GameTime，也不得以默认 1×、空 ledger 或清零 counter 猜测。

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
upcast_shutdown_checkpoint_v1(checkpoint_v1, evidence_v1, pause_ledger) -> CheckpointV2 | RecoveryError
release_startup_pause(command_id) -> ClockControlResult
```

## 6. 正常流程

1. Shutdown coordinator 获取 shutdown Pause Token。
2. Gateway 停止普通写入，World Writer 完成当前事务；未开始命令保留可解释拒绝。
3. TIME 输出 checkpoint projection，RELEASE 同 Revision 持久化并校验 Hash。
4. 重启先建立 Recovery Barrier，重放状态/事件并恢复各 TIME 队列、Clock Control v2 和 backpressure state。
5. 比较 Hash、Revision、Seed sequence、Reservation、Long Action、requested/cap/control version；验证旧 Pause Ledger Hash 后，原子终结旧 shutdown token 并取得 recovery/startup blocking token，再按唯一公式得到 effective=0。
6. audit 通过进入 paused_ready；玩家/启动流程明确释放 startup pause 后再次按公式合成，而不是直接采用 requested speed。

## 7. 边界情况

- crash 发生在 checkpoint 写入中：RELEASE 选择最后完整 checkpoint + Event tail，TIME 不信任半写文件。
- 已完成模型响应在进程退出前未提交：它不是事实；若有完整 replay record 可重新入验证链，否则按 AI recovery policy 重请求或 fallback。
- 玩家在 requested=4×、backpressure cap=1× 时关闭：v2 保存 requested=4、cap=1、Clock Phase 与 control state；重启先 paused_ready/effective=0，释放 startup token 后 effective=`min(4,1)=1`，不自动恢复 4×。
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
- v2 round-trip 保持 requested=4、cap=1 和 Clock Control version；startup token 前 effective=0、释放后 effective=1。
- 恢复失败保持 paused 且不破坏原文件。
- 重启不会使用旧 monotonic deadline 补做离线 Tick。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-025` | `RULE-TIME-049..050` shutdown order 与 zero offline delta |
| `TEST-TIME-026` | `RULE-TIME-051..053`, `RULE-TIME-074`, `RULE-TIME-076` strict value validation、v2 control round-trip、recovery/rebase |
| `TEST-TIME-027` | `RULE-TIME-054` corruption 不猜测恢复 |

## 12. 关联文档

- `DOC-FOUNDATION-001`：关闭后暂停的产品要求
- `DOC-TIME-002`：shutdown/startup Pause Token
- `DOC-TIME-010`：AI replay 与 Seed sequence
- `DOC-RELEASE-003`：Snapshot/Event Log 持久化
- `DOC-RELEASE-006`：损坏恢复

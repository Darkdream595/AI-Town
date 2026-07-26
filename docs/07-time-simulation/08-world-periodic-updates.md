---
doc_id: DOC-TIME-008
title: 世界周期更新与事件队列
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - authoritative-game-time-event-queue
  - periodic-update-cadence
  - due-event-ordering
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-WORLD-007
  - DOC-TIME-001
  - DOC-TIME-003
  - DOC-TIME-007
requirements:
  - REQ-TIME-008
last_updated: 2026-07-26
---

# 世界周期更新与事件队列

## 1. 目的

`REQ-TIME-008`：定义 GameTime Event Queue 的权威 ownership、到期全序、周期任务目录、重排、catch-up 和幂等，使天气、Needs、经济、日程及到期 Reservation 不依赖逐 Tick 全表扫描。

## 2. 非目标

本文不定义天气、Needs、价格或库存计算。TIME 定义“何时调用”和队列事实；业务 owner 定义 handler 输入、状态变化和 DomainEvent。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Scheduled Event | 在 `due_game_time` 调用注册 handler 的持久记录，不等同 `DomainEvent` |
| Periodic Definition | 带 anchor、interval、handler ID 和 catch-up policy 的 Stable Catalog 项 |
| Due Event | `due_game_time <= current_game_time` 且 state=scheduled 的项 |
| Stable Sequence | 创建时单调分配的 uint64 tie-break |
| Catch-up Policy | `each_occurrence` 或 owner 明确声明可结合的 `aggregate_window` |
| Handler Outcome | `completed/rescheduled/cancelled/retryable_failure/terminal_failure` |

## 4. 规则与不变量

- `RULE-TIME-043`：Scheduled Event 全序为 `(due_game_time, phase, priority_class, owner_domain, stable_sequence, scheduled_event_id)` 升序。
- `RULE-TIME-044`：phase 固定为 `0 expiry/safety`、`1 clock_boundary`、`2 resident/long_action`、`3 environment`、`4 economy/event`、`5 summary/maintenance`。
- `RULE-TIME-045`：周期下一次 due time 必须从原 anchor 递增 interval，禁止从实际晚执行时间漂移。
- `RULE-TIME-046`：默认 cadence 为 Resident Needs 10 游戏分钟、天气评估 30 游戏分钟、经济聚合 60 游戏分钟、日界/Calendar 1440 游戏分钟；handler owner 可在其定义内增加更稀疏任务，不得改变这些 canonical defaults。
- `RULE-TIME-047`：每个 occurrence key `(periodic_definition_id, due_game_time)` 最多完成一次；重放返回原 outcome。
- `RULE-TIME-048`：只有 owner 声明 associative、order-independent 且 conservation-safe 时可 aggregate catch-up；否则逐 occurrence 执行、降速或暂停，禁止跳过。

## 5. 数据与接口

`DES-TIME-008`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/scheduled-event/v1",
  "type": "object",
  "required": ["schema_version", "scheduled_event_id", "handler_id", "owner_domain", "due_game_time", "phase", "priority_class", "stable_sequence", "state", "version"],
  "properties": {
    "schema_version": {"const": 1},
    "scheduled_event_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "handler_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
    "owner_domain": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
    "due_game_time": {"type": "integer", "minimum": 0},
    "phase": {"type": "integer", "minimum": 0, "maximum": 5},
    "priority_class": {"type": "integer", "minimum": 0, "maximum": 5},
    "stable_sequence": {"type": "integer", "minimum": 0},
    "state": {"enum": ["scheduled", "leased", "completed", "cancelled", "retryable_failure", "terminal_failure"]},
    "version": {"type": "integer", "minimum": 1}
  },
  "additionalProperties": false
}
```

默认目录：

| Definition ID | Anchor | Interval | Phase | Consumer |
|---|---:|---:|---:|---|
| `periodic.resident.needs` | 0 | 10 game minutes | 2 | RESIDENT |
| `periodic.environment.weather_evaluation` | 0 | 30 game minutes | 3 | EVENT |
| `periodic.economy.aggregate` | 0 | 60 game minutes | 4 | ECON |
| `periodic.calendar.day_boundary` | 0 | 1440 game minutes | 1 | TIME/WORLD projection |

`anchor=0` 表示 occurrence 对齐到世界纪元的整数倍；初始化/恢复时选择严格大于当前 GameTime 的下一个倍数，当前 GameTime 已完成的 occurrence 由 idempotency record 判断，禁止在 world 创建时额外执行一次 0 时刻更新。

接口：

```text
schedule_event(command_id, event) -> ScheduleResult
cancel_event(command_id, scheduled_event_id, expected_version) -> CancelResult
pop_due_events(current_game_time, batch_limit) -> DueLease
complete_due_event(lease_id, outcome) -> CompletionResult
rebuild_event_queue(snapshot, event_tail) -> QueueRecoveryReport
```

## 6. 正常流程

1. Clock 推进得到 Due Window。
2. Queue 按全序 lease 有界 batch。
3. Orchestrator 调用 handler owner 的纯/事务 Port。
4. handler 状态、DomainEvent、occurrence idempotency result 与 queue outcome 原子提交。
5. periodic item 依据原 anchor 创建下一 occurrence。

## 7. 边界情况

- `4×` 一 Tick 跨多个分钟：按 due time 逐项处理，不按插入容器遍历顺序。
- Pause/关闭期间 GameTime 不变，因此无新的 GameTime event 到期。
- handler retryable failure：保留原 occurrence key，增加 bounded attempt，按 GameTime 重排；不创建逻辑重复 occurrence。
- day boundary 与天气/经济同分钟：先 day boundary，再 environment，再 economy。
- queue overload：每 Tick batch 上限后保留余项并触发 speed fallback；安全 expiry phase 不被低 phase 饥饿。

## 8. 错误与降级

检测到重复 stable sequence、无 handler、due time 逆序或 completed occurrence 再执行时返回 `TIME_EVENT_QUEUE_INVALID`。恢复重建 Hash 不一致时保持 Recovery Barrier；不得从当前 GameTime 重新生成并丢弃历史队列。

## 9. 安全与性能

Queue 使用 `(due_game_time, phase, priority, owner, sequence, id)` 索引。单 Tick 默认最多 lease 128 项；handler payload 最大 16 KiB 且不存 Secret。周期目录在构建期校验 interval 为正整数游戏分钟。

## 10. 验收标准

- 相同 Scheduled Event 集不受插入顺序影响，产生相同执行序列。
- 四个默认 cadence 在 1/7/30 游戏日计数精确且无漂移。
- retry、crash、pause、4× 和 day boundary 组合不重复 occurrence。
- 不安全的 backlog 不被 aggregate 或跳过。
- Snapshot/Event Log 重建 queue 后 Hash 与下一执行项一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-022` | `RULE-TIME-043..045` 全序与 anchor 无漂移 |
| `TEST-TIME-023` | `RULE-TIME-046..047` cadence 与 occurrence idempotency |
| `TEST-TIME-024` | `RULE-TIME-048` catch-up safety 与 overload |

## 12. 关联文档

- `DOC-TIME-003`：Tick Due Window
- `DOC-TIME-007`：Reservation expiry
- `DOC-TIME-011`：batch/queue budget
- `DOC-EVENT-006`：天气 handler owner
- `DOC-ECON-009`：经济 aggregate handler owner

---
doc_id: DOC-TIME-011
title: 模拟性能与负载预算
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - simulation-performance-budget
  - queue-capacity-backpressure
  - high-speed-fallback
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-002
  - DOC-TIME-003
  - DOC-TIME-004
  - DOC-TIME-005
  - DOC-TIME-008
requirements:
  - REQ-TIME-011
last_updated: 2026-07-26
---

# 模拟性能与负载预算

## 1. 目的

`REQ-TIME-011`：定义 Tick latency、每 Tick work batch、队列容量、simulation tier 上限、AI 并发、backpressure 和高倍速回落，使 8–12 名居民在普通玩家机器上长期运行且不牺牲规则正确性。

## 2. 非目标

本文不定义 Phaser shader/asset budget、模型 token 价格或数据库物理调优；只规定 TIME 可观测指标和跨队列负载响应。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Healthy Window | 连续 5 RealTime 秒的 rolling metrics 均低于健康阈值 |
| Overload Window | 连续窗口触发任一降档阈值 |
| Speed Cap | backpressure controller 允许的最高倍率 |
| Due Backlog | 已到期但尚未 lease 的 Scheduled Event 数 |
| Oldest Wait | 队列最旧 item 的 RealTime 等待，不改变其 Game Deadline |
| Hard Safety Stop | 0.5× 仍持续增长时取得 overload Pause Token |

## 4. 规则与不变量

- `RULE-TIME-061`：10 Hz Tick 的 critical section 目标 p95≤25 ms、p99≤50 ms，单 Tick warning threshold=80 ms；不得通过可变 delta 或跳过 invariant 达标。
- `RULE-TIME-062`：每 Tick 默认上限为 due events 128、resident scheduler leases 32、long-action checkpoints 64、tier reconciliation actors 32。
- `RULE-TIME-063`：默认容量为 World Command 512、Resident Scheduler 256、AI pending 64/普通 in-flight 2、Long Action 2048、Scheduled Event 16384；不可丢 Domain Event 不使用 drop policy。
- `RULE-TIME-064`：Active Scene 上限 1、Warm Scene 上限 2；Background 无固定 actor 上限但受 8–12 正式居民与 batch budget。
- `RULE-TIME-065`：连续 3 个 Overload Window 时 speed cap 单级回落 `4→2→1→0.5`；0.5× 下连续 6 个窗口仍增长则申请 overload pause 并提示玩家。
- `RULE-TIME-066`：恢复仅在连续 30 RealTime 秒 Healthy 后单级提高 cap，且不高于 requested speed；不得震荡式每窗口升降。
- `RULE-TIME-067`：降档只能延迟 ambient evaluation、合并可合并 render delta 和减少 batch；不可丢 DomainEvent、跳过安全/守恒/期限或扩大 AI 并发。

## 5. 数据与接口

`DES-TIME-011`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/load-budget-profile/v1",
  "type": "object",
  "required": ["schema_version", "tick_hz", "tick_p95_budget_real_ms", "tick_p99_budget_real_ms", "ordinary_ai_max_in_flight", "active_scene_max", "warm_scene_max"],
  "properties": {
    "schema_version": {"const": 1},
    "tick_hz": {"const": 10},
    "tick_p95_budget_real_ms": {"const": 25},
    "tick_p99_budget_real_ms": {"const": 50},
    "ordinary_ai_max_in_flight": {"const": 2},
    "active_scene_max": {"const": 1},
    "warm_scene_max": {"const": 2}
  },
  "additionalProperties": false
}
```

Overload 条件任一成立：

| 指标 | 阈值 |
|---|---:|
| Tick p99 | >50 real ms |
| Due backlog | >512 |
| World Command Queue | >384 |
| Resident Scheduler | >192 |
| AI pending | >32 |
| Long Action due backlog | >256 |

接口：

```text
sample_load_metrics(monotonic_window) -> LoadMetrics
evaluate_backpressure(metrics, previous_state) -> BackpressureDecision
apply_speed_cap(decision, expected_version) -> ClockControlEvent
get_capacity_status() -> CapacityReport
```

## 6. 正常流程

1. 每 5 RealTime 秒汇总 rolling metrics。
2. healthy 时保持 cap；overload counter 达 3 时降一级。
3. scheduler 停止 ambient prefetch，保留 safety/player/committed obligation。
4. Event Queue 按 phase 和 batch 继续；可安全 aggregate 的 handler 才聚合。
5. 连续健康 30 秒后至多恢复一级。

## 7. 边界情况

- requested speed=1、cap=4 时 effective 仍为 1；恢复 cap 不强迫提速。
- Pause 中 Tick latency 低但 AI pending 未下降：不能据低 latency 宣称 healthy。
- Domain Event outbox 滞后时由 BACKEND snapshot/backpressure 处理；TIME 可降速但不能 drop DomainEvent。
- 突发 200 个同分钟事件：分 batch 且按全序，若 deadline-sensitive 则降速。
- 老旧机器长期无法维持 0.5×：安全暂停并显示瓶颈，不切换非权威 fast-forward。

## 8. 错误与降级

metrics 缺失、负计数或版本冲突时保持更保守 cap 并返回 `TIME_LOAD_METRICS_INVALID`。Backpressure controller 故障时默认 cap=1，不关闭 invariant、审计或恢复逻辑。

## 9. 安全与性能

metrics 只含计数、分位数和 stable queue ID，不含 payload。统计采用固定大小 histogram/ring buffer，不能为监控再次扫描全部世界。容量配置只从版本化后端 profile 读取，不信任 Client。

## 10. 验收标准

- 8、10、12 居民在 1× 下 Tick p95/p99 达标且队列有界。
- 4× 压测会按阈值确定性降到可持续倍率。
- overload/healthy hysteresis 不发生一分钟内反复升降。
- 0.5× 仍失控时安全暂停，世界状态和队列可恢复。
- 故障注入证明没有丢弃 DomainEvent 或跳过 invariant。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-031` | `RULE-TIME-061..064` budgets/capacities |
| `TEST-TIME-032` | `RULE-TIME-065..066` downgrade/restore hysteresis |
| `TEST-TIME-033` | `RULE-TIME-067` no-rule-skipping fault injection |

## 12. 关联文档

- `DOC-TIME-003`：Tick critical section
- `DOC-TIME-004`：Resident/AI queue
- `DOC-TIME-005`：Scene tier limits
- `DOC-TIME-008`：Due backlog
- `DOC-BACKEND-012`：全进程性能与日志测试

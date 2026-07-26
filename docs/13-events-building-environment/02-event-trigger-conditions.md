---
doc_id: DOC-EVENT-002
title: 事件触发条件与叙事压力预算
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - event-trigger-registry
  - event-conflict-rules
  - narrative-pressure-budget
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-008
  - DOC-TIME-010
  - DOC-EVENT-001
requirements:
  - REQ-EVENT-002
last_updated: 2026-07-26
---

# 事件触发条件与叙事压力预算

## 1. 目的

`REQ-EVENT-002`：定义触发器注册格式、确定性评估、severity 分级、Narrative Pressure Budget、重复灾害冷却与并发冲突裁决，使世界事件节奏可控、可复现，且同一时间最多一个重大危机并保留平静日。

## 2. 非目标

本文不定义 WorldEvent 状态机（`DOC-EVENT-001`）、Director 提案流程（`DOC-EVENT-003`）或天气转移矩阵（`DOC-EVENT-006`）。天气与灾害事件作为触发产物遵守本文预算，但其概率参数由 `DOC-EVENT-006` 拥有。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Trigger | Stable Catalog 注册项：条件谓词、目标 EventTemplate、cooldown、priority 与允许来源 |
| Condition Predicate | 在 revision-stamped projection 上求值的受限布尔表达式，无副作用 |
| Severity | `minor/moderate/major/crisis` 四级事件强度 |
| Narrative Pressure Budget | 按 severity 权重记账、限制危机并发/冷却/强度的世界事件资源（`DOC-FOUNDATION-004`） |
| Cooldown Key | `(event_template_id, scene_id)` 的冷却记账键 |
| Calm Window | 无 `moderate` 以上新事件激活的连续 GameTime 区间 |

## 4. 规则与不变量

- `RULE-EVENT-007`：Trigger 必须注册为 Stable Catalog 项；Condition Predicate 只能读取声明的 projection 字段，求值是纯函数：相同 `(revision, trigger_id)` 输入必得相同结果，禁止在谓词内访问网络、墙钟或随机数以外的隐式状态。
- `RULE-EVENT-008`：周期评估由 EVENT 注册的 `periodic.event.trigger_evaluation`（interval 30 game minutes，phase 4）驱动；事件驱动触发订阅已提交 DomainEvent。两类评估均以 `(trigger_id, occurrence_key)` 幂等，重放不产生第二个候选。
- `RULE-EVENT-009`：Narrative Pressure Budget 权重固定为 `minor=1、moderate=2、major=4、crisis=8`，全世界同时 active 权重和上限 12；`crisis` 并发上限 1（同一时间最多一个重大危机）；预算在事件进入 `aftermath` 后经 1440 game minutes 线性返还，保证每 7 游戏日在种子期望下至少出现 1 个完整 Calm Window（≥1440 game minutes）。
- `RULE-EVENT-010`：重复灾害冷却：同一 Cooldown Key 在模板声明的 `cooldown_game_minutes`（灾害类模板下限 4320）内不得再次实例化；`admin` 来源可越过冷却但仍占预算并留审计。
- `RULE-EVENT-011`：冲突裁决确定性：同一评估批次多个候选按 `(severity 降序, trigger_priority 降序, trigger_id 字典序)` 排序逐个申请预算；互斥标签（模板 `exclusion_tags` 交集非空且 Scope 相交）的后序候选直接拒绝；已 active 事件不被新候选隐式取消，只能按 `DOC-EVENT-001` 状态机显式升级或解除。
- `RULE-EVENT-012`：触发概率随机性只来自 `(seed, stream_id, sequence)`（`RULE-FOUNDATION-026`），`stream_id` 固定为 `event.trigger.<trigger 末段>`；存档重载与回放不改变抽样序列。

## 5. 数据与接口

`DES-EVENT-002`：Trigger 注册项：

```json
{
  "schema_version": 1,
  "trigger_id": "event_trigger.forest_fire_after_thunderstorm",
  "event_template_id": "event.disaster.forest_fire",
  "allowed_sources": ["environment"],
  "severity": "major",
  "trigger_priority": 3,
  "condition": {
    "kind": "all_of",
    "clauses": [
      {"kind": "projection_equals", "path": "weather.region.whisper_forest.weather_id", "value": "weather.thunderstorm"},
      {"kind": "projection_at_least", "path": "environment.region.whisper_forest.dryness_0_to_1", "value": 0.7}
    ]
  },
  "activation_chance_0_to_1": 0.25,
  "cooldown_game_minutes": 4320,
  "exclusion_tags": ["regional_disaster.whisper_forest"]
}
```

预算账本随世界持久化：

```json
{
  "schema_version": 1,
  "active_weight": 4,
  "weight_cap": 12,
  "crisis_active_count": 0,
  "cooldowns": [
    {"event_template_id": "event.disaster.forest_fire", "scene_id": "region.whisper_forest", "expires_at_game_time": 17640}
  ],
  "last_calm_window_start_game_time": 8640
}
```

接口：

```text
evaluate_triggers(occurrence_key, revision) -> [CandidateEvent]
try_reserve_pressure(command_id, severity) -> BudgetReservation | BudgetExceeded
release_pressure(world_event_id) -> BudgetReleaseResult
query_budget() -> RevisionStampedBudgetProjection
```

## 6. 正常流程

1. phase 4 周期 handler 以当前 Revision 快照评估全部注册 Trigger。
2. 条件为真的 Trigger 按 `RULE-EVENT-012` 抽样决定是否产生候选。
3. 候选按 `RULE-EVENT-011` 排序，逐个检查冷却、互斥与预算。
4. 通过者调用 `DOC-EVENT-001` `instantiate_event` 原子提交 candidate → scheduled 并占用预算。
5. 事件进入 aftermath 时释放权重并写入冷却记录。

## 7. 边界情况

- 预算恰好剩 2 而候选为 major（权重 4）：拒绝该候选，不允许部分占用。
- crisis 已 active 时第二个 crisis 候选：直接拒绝并记录 `budget_exceeded`，即使总权重未满。
- 高倍速一次 Due Window 覆盖多个评估 occurrence：按 `RULE-TIME-048` 逐 occurrence 执行，不聚合，防止冷却与抽样漂移。
- 触发所依赖 projection 字段缺失（例如新世界尚无 dryness 统计）：该子句求值为 false 并记录一次性登记警告，不抛错。
- Calm Window 统计跨暂停：暂停不推进 GameTime，窗口长度只按 GameTime 计算。

## 8. 错误与降级

返回 `trigger_unknown`、`condition_schema_invalid`、`budget_exceeded`、`cooldown_active`、`exclusion_conflict` 或 `occurrence_replayed`。评估 handler 单次失败按 `RULE-TIME-047` 保留 occurrence key 重试；连续 terminal failure 停用该 Trigger 并发布诊断事件，不停用整个评估管线。

## 9. 安全与性能

Condition Predicate 的 projection 路径白名单在构建期校验，禁止指向私人记忆、Secret 或模型文本（`RULE-FOUNDATION-020/024`）。单次评估上限 256 个 Trigger、每 Trigger 32 个子句；抽样与排序为 O(n log n)。预算账本随 Snapshot 持久化并纳入恢复审计。

## 10. 验收标准

- 相同 Seed 与命令序列重放得到相同的事件时间线。
- 权重注入证明：总权重不可超 12，crisis 并发不可超 1。
- 冷却期内同 Cooldown Key 的候选全部拒绝。
- 30 游戏日模拟中每 7 日至少一个 Calm Window。
- 互斥标签冲突的裁决顺序与文档排序一致且可复现。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-004` | `RULE-EVENT-007..008` 纯函数求值与 occurrence 幂等 |
| `TEST-EVENT-005` | `RULE-EVENT-009..010` 预算上限、crisis 并发、冷却与 Calm Window |
| `TEST-EVENT-006` | `RULE-EVENT-011..012` 确定性裁决与种子化抽样重放 |

## 12. 关联文档

- `DOC-EVENT-001`：候选实例化与状态机
- `DOC-EVENT-003`：Director 提案同样经本预算
- `DOC-EVENT-006`：天气/灾害触发参数 owner
- `DOC-TIME-008`：周期评估 occurrence 与 phase
- `DOC-TIME-010`：Seed stream 纪律

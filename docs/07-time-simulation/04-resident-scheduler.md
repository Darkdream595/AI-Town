---
doc_id: DOC-TIME-004
title: 居民调度器
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - resident-scheduling-policy
  - action-deadline-priority
  - scheduler-fairness
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-006
  - DOC-TIME-001
  - DOC-TIME-003
  - DOC-RESIDENT-001
  - DOC-RESIDENT-009
requirements:
  - REQ-TIME-004
last_updated: 2026-07-26
---

# 居民调度器

## 1. 目的

`REQ-TIME-004`：定义 Resident job 的优先级、deadline、fairness、AI 请求交接和过期结果处理。TIME 只决定“何时获得调度机会”，不决定居民目标、合法 Action 或业务结果。

## 2. 非目标

本文不拥有 Resident 字段、Daily Plan、ActionProposal Schema、Utility AI 选择或职业排班内容。RESIDENT/AI owner 发布只读 projection 与执行 Port，TIME 使用冻结的 Resident Runtime ID 和注册 Action Stable ID。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Scheduler Job | 对一个 actor 和一个已注册 job kind 的有界调度记录 |
| Game Deadline | 必须在某 GameInstant 前开始/重规划的期限 |
| Real Deadline | 模型请求 timeout 等 monotonic RealTime 期限 |
| Priority Class | 从 0 到 5，数值越小越优先 |
| Aging | 等待达到阈值后提高 effective priority，但不越过安全类 |
| Immutable Decision Reference | `{resident_id, observed_revision, observed_game_time, context_hash}` |

## 4. 规则与不变量

- `RULE-TIME-019`：优先级依次为 `0 emergency_safety`、`1 player_blocking`、`2 combat_or_immediate_deadline`、`3 committed_obligation`、`4 routine_need_or_work`、`5 ambient_optional`。
- `RULE-TIME-020`：同一 priority 内按最早 Game Deadline、accepted sequence、resident ID 排序；无 Game Deadline 视为正无穷。
- `RULE-TIME-021`：普通 AI 模型工作默认最多并发 2；scheduler 可以排队、取消或超时，但不能直接调用具体模型 SDK。
- `RULE-TIME-022`：每名 eligible Resident 在连续 10 个游戏分钟内至少获得一次 routine evaluation，除非其处于排他长任务、Encounter、昏迷、合法 pause 或 owner 标记 unavailable。
- `RULE-TIME-023`：AI response 必须携带 immutable decision reference；返回后在最新 Revision/GameTime 重校验，过期不能以原上下文直接提交。
- `RULE-TIME-024`：Deadline miss 产生稳定结果 `replan_required/fallback_required/expired`；不得把未执行 Action 倒填为历史成功。

## 5. 数据与接口

`DES-TIME-004`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/scheduler-job/v1",
  "type": "object",
  "required": ["schema_version", "job_id", "resident_id", "job_kind", "priority_class", "accepted_sequence", "observed_revision", "observed_game_time"],
  "properties": {
    "schema_version": {"const": 1},
    "job_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "job_kind": {"enum": ["daily_plan", "hourly_intent", "immediate_action", "utility_fallback", "routine_evaluation"]},
    "priority_class": {"type": "integer", "minimum": 0, "maximum": 5},
    "accepted_sequence": {"type": "integer", "minimum": 0},
    "observed_revision": {"type": "integer", "minimum": 0},
    "observed_game_time": {"type": "integer", "minimum": 0},
    "deadline_game_time": {"type": ["integer", "null"], "minimum": 0},
    "timeout_real_ms": {"type": ["integer", "null"], "minimum": 1, "maximum": 120000}
  },
  "additionalProperties": false
}
```

接口：

```text
schedule_resident_job(job) -> ScheduleResult
lease_next_job(worker_class, monotonic_now_ms) -> JobLease | none
complete_job(job_id, lease_id, outcome) -> CompletionResult
cancel_actor_jobs(resident_id, reason) -> CancellationSet
```

## 6. 正常流程

1. RESIDENT 或 Orchestrator 发布 eligibility 与 next evaluation deadline。
2. TIME 创建 Scheduler Job 并分配 accepted sequence。
3. worker 按全序 lease job；AI worker 通过 AI Port 获得结果。
4. response 入 World Command Queue，在最新状态重新验证。
5. 成功、拒绝、重规划或 fallback 结果完成 lease，并计算下一次 evaluation。

## 7. 边界情况

- emergency job 到达时不取消已在网络中的普通请求，但不再发新普通 lease，空闲 slot 优先 emergency。
- 同一 Resident 同时出现多个 routine job 时按 `(resident_id, job_kind, target_window)` 幂等合并。
- Pause 中 Game Deadline 不前进，Real Deadline 继续处理模型 timeout；结果只入队，不提交需要推进世界的 Action。
- Resident 转入 Encounter/昏迷时取消不兼容 pending job；其已返回 AI 结果仍需最新状态校验并通常拒绝。
- Aging 最多把 priority 5 提升到 3，不能提升为安全或玩家阻塞类。

## 8. 错误与降级

模型 timeout、限流、非法输出由 AI owner分类；TIME 只接收 `retry_at_real_ms/fallback_required/terminal_failure`。lease 丢失按 RealTime 到期回队且 attempt 有上限；达到上限创建 Utility fallback job，不无限重试。

## 9. 安全与性能

队列不携带未经 ACL 过滤的完整 DecisionContext，只保存引用与 hash。索引键为 `(priority, deadline, sequence, resident_id)`；每 Tick lease 数受 `DOC-TIME-011` budget 限制。普通模型并发 2 是默认硬上限，改变需版本化配置与负载验收。

## 10. 验收标准

- 六级 priority、deadline 和 stable tie-break 在重放时顺序一致。
- 8–12 名居民在无排他状态时均满足 10 游戏分钟 fairness。
- 普通模型并发不超过 2，紧急任务不会被 ambient job 饿死。
- stale response、pause、昏迷和 Encounter 转换均无非法提交。
- timeout 达到上限后进入有界 fallback。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-010` | `RULE-TIME-019..020` priority/deadline stable order |
| `TEST-TIME-011` | `RULE-TIME-021..022` concurrency 与 fairness |
| `TEST-TIME-012` | `RULE-TIME-023..024` stale response 与 deadline miss |

## 12. 关联文档

- `DOC-RESIDENT-001`：Resident identity consumer contract
- `DOC-RESIDENT-009`：日常生活与可调度窗口
- `DOC-AI-009`：AI request queue 下游协作
- `DOC-TIME-006`：排他长任务
- `DOC-TIME-011`：队列容量与负载预算

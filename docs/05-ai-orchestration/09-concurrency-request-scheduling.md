---
doc_id: DOC-AI-009
title: AI 请求并发、优先级与生命周期
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - ai-request-lifecycle
  - model-worker-concurrency
  - retry-cancel-deadline-policy
depends_on:
  - DOC-AI-007
  - DOC-TIME-004
  - DOC-TIME-011
requirements:
  - REQ-AI-009
last_updated: 2026-07-26
---

# AI 请求并发、优先级与生命周期

## 1. 目的

`REQ-AI-009`：定义 AI Request Queue 的全序、普通并发 2、lease、取消、RealTime deadline、有限重试、限流和 stale response 处理。

## 2. 非目标

AI queue 不推进 GameTime、不改变 TIME Scheduler priority、不持有 Domain Reservation，也不在请求完成时直接提交世界。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Pending Request | 已接受但未 lease 的 immutable request |
| In-flight | worker 已开始网络请求 |
| Cancellation Token | actor/世界状态变化发出的 cooperative cancel |
| Real Deadline | monotonic clock 上的最晚完成时间 |
| Attempt | 同一 logical request 的受限 transport 尝试 |

## 4. 数据与接口

`DES-AI-009`：Request state：

```text
created -> queued -> leased -> in_flight -> succeeded
queued/leased/in_flight -> cancelled | expired
in_flight -> retry_wait -> queued
in_flight -> terminal_failed
```

Request record：

```json
{
  "request_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "logical_request_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "job_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "priority_class": 4,
  "accepted_sequence": 201,
  "observed_revision": 84,
  "context_hash": "sha256:8de5c7a8d5f0",
  "deadline_monotonic_ms": 9912345,
  "attempt": 1,
  "max_attempts": 2,
  "state": "queued"
}
```

全序沿用 TIME：`priority_class, deadline_game_time|null-as-infinity, accepted_sequence, resident_id, request_id`。AI 只保存 TIME 提供的 class，不由 Proposal `priority` 覆盖。

## 5. 规则与不变量

- `RULE-AI-049`：普通 provider 请求每世界 `max_in_flight=2`，不能为追赶高倍速扩大；pending 默认上限 64。
- `RULE-AI-050`：TIME priority 0..5 与 deadline/sequence 是唯一队列全序；emergency 停发 ambient，但不破坏网络请求或 Domain Reservation。
- `RULE-AI-051`：actor 失效、job superseded、世界关闭/切换、Encounter transition 或 context dependency 改变时发 cancel；迟到 response 标记 discarded。
- `RULE-AI-052`：deadline 使用 monotonic RealTime，Pause 不延长网络 timeout；Game deadline 由 TIME 另行判断。
- `RULE-AI-053`：仅 connect/provider unavailable/rate limit 可重试；默认 max attempts=2，退避 `250/1000 real ms` 加 deterministic request-hash jitter `0..100 ms`，不得无限重试。
- `RULE-AI-054`：result 必须回到 World Command Queue，在最新 Revision 校验；worker 不能直接调用 commit。

## 6. 正常流程

TIME Scheduler 创建 job；AI 接受 immutable request；按全序 lease，确保 in-flight≤2；adapter 使用 cancellation/deadline；成功送 parser/validator；transient failure 若 deadline 足够则 retry_wait；terminal/耗尽则通知 TIME `fallback_required`。

## 7. 边界情况

取消可能无法中止已发 HTTP；返回仍 discard。rate-limit retry hint 只有在 deadline/bounds 内采用。Pause 期间可完成请求但不提交需要推进世界的 Action。两个结果同时返回按 World Command Queue 的 accepted sequence 和最新 Revision 处理，不按网络先后保证成功。

## 8. 错误与降级

queue full 时 priority 5 先拒绝/合并，0..3 不丢但触发 TIME backpressure；lease crash 到期回队且 attempt+1；无有效 deadline 或负 attempt 为 config invalid；耗尽进入 DOC-AI-011。

## 9. 安全与性能

队列仅保存 Context hash/引用，不保存完整 Context/Prompt。连接池上限与 in-flight 对齐；metrics 包含 queue depth、oldest wait、latency、cancel/discard/retry counts，不含内容。

## 10. 验收标准

- 压测中普通 in-flight 从不超过 2，pending 不超过 64。
- priority/deadline/tie-break 在不同容器迭代顺序下一致。
- cancel、late、pause、retry exhaustion 均无非法提交。
- 4× overload 触发 backpressure 而非扩大并发。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-033` | concurrency=2/pending=64 |
| `TEST-AI-034` | stable priority/deadline ordering |
| `TEST-AI-035` | cancel/late/pause lifecycle |
| `TEST-AI-036` | retry classes/backoff/exhaustion |

## 12. 关联文档

- `DOC-TIME-004`：上游 job priority/fairness
- `DOC-TIME-011`：容量和高倍速回落
- `DOC-AI-011`：fallback required

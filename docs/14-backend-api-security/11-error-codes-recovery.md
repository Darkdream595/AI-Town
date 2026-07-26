---
doc_id: DOC-BACKEND-011
title: 错误码注册表与失败恢复
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - backend-error-code-registry
  - error-response-schema
  - backpressure-and-safe-shutdown
depends_on:
  - DOC-FOUNDATION-005
  - DOC-BACKEND-001
  - DOC-BACKEND-005
requirements:
  - REQ-BACKEND-011
last_updated: 2026-07-26
---

# 错误码注册表与失败恢复

## 1. 目的

`REQ-BACKEND-011`：定义 `BACKEND_*` 错误码的唯一注册表、统一错误对象 Schema、HTTP 与 WS 行为映射、模型/网络/存储三类失败的恢复路径、背压信号与安全关机序列。

## 2. 非目标

本文不定义 Domain 业务 reason code（owner 文档，如 `DOC-ECON-006` §8 的交易失败码）——它们出现在 `failed` 回执的 `details.reason_code` 中且由 owner 登记；不定义 AI 重试与降级决策（`DOC-AI-009` / `DOC-AI-011`）、磁盘损坏分级修复（`DOC-RELEASE-006`）、前端错误 UI 文案。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Error Object | 所有错误响应/帧共用的结构化错误体 |
| Error Category | protocol/auth/limit/conflict/backpressure/upstream/storage/internal/lifecycle |
| Retryable | Client 可用同一请求（含同 `command_id`）安全重试 |
| Read-only Degradation | 存储失败后世界写入暂停、读取与导出仍可用的状态 |
| Overload State | 持续背压下向全部连接广播的降级状态 |
| Graceful Drain | `DOC-BACKEND-001` 定义的安全关机流程，本文细化其对外语义 |

## 4. 规则与不变量

- `RULE-BACKEND-060`：错误码注册表是 wire 上允许出现的 `BACKEND_*` 码的唯一 canonical 列表；新增码必须登记：category、HTTP status、WS 行为（`error 帧` / `error 帧+close`）、retryable、日志级别。未注册码出现在响应中属 `TEST-BACKEND-039` 失败。
- `RULE-BACKEND-061`：错误对象统一 Schema：`{schema_version, code, message, retryable, retry_after_ms, details}`；`message` 面向用户、不含堆栈/路径/Secret/内部配置；`details` 只含 ID、版本号与脱敏 reason code。同一错误在 REST 与 WS 中使用同一对象，仅外层不同。
- `RULE-BACKEND-062`：模型失败（超时、空响应、非法 JSON、限流、网络）不直接成为玩家可见错误：居民行动按 `DOC-AI-009` 受限重试后走 `DOC-AI-011` Utility 降级，世界继续运行；仅玩家显式发起且无降级语义的模型交互（如主动对话）在耗尽后返回 `BACKEND_MODEL_UNAVAILABLE`（retryable=true）。
- `RULE-BACKEND-063`：存储写失败：当前 UoW 回滚、Revision 不变（`RULE-FOUNDATION-023`）、返回 `BACKEND_STORAGE_FAILURE`，该世界进入 Read-only Degradation：拒绝新写命令（同码）、保持读取/WS 推送已提交内容、触发 `DOC-RELEASE-006` 诊断；恢复写入必须经过完整性检查，不自动重试写。
- `RULE-BACKEND-064`：背压逐级：World Command Queue 满 → 单命令 `BACKEND_QUEUE_FULL`（retryable，含 `retry_after_ms`）；持续超过 5000 real ms 或队列滞留 p95 超预算 → 进入 Overload State，广播 `system.overload.changed` 事件（coalescible=false），Client 显示降级提示；解除同样广播。服务器在任何背压层级都不无界缓冲、不丢 DomainEvent。
- `RULE-BACKEND-065`：安全关机序列（细化 `DOC-BACKEND-001` §6.4 对外语义）：进入 Drain 即 (1) 广播 `error(BACKEND_SHUTDOWN)` 预告帧；(2) 新命令一律 `rejected(BACKEND_SHUTDOWN)`；(3) 已入队命令在 10000 real ms 内完成或统一 `failed(BACKEND_SHUTDOWN)` 回执；(4) 取消 AI 在途（`DOC-AI-009` cancel）；(5) flush Outbox 尽力送达后关闭全部连接；(6) checkpoint 并关库。任何一步不产生半事务。

## 5. 数据与接口

`DES-BACKEND-011`：错误对象实例：

```json
{
  "schema_version": 1,
  "code": "BACKEND_QUEUE_FULL",
  "message": "服务器繁忙，请稍后重试。",
  "retryable": true,
  "retry_after_ms": 500,
  "details": {
    "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "queue": "world_command"
  }
}
```

错误码注册表（首版全集）：

| code | category | HTTP | WS 行为 | retryable |
|---|---|---|---|---|
| `BACKEND_BIND_REFUSED` | lifecycle | —（启动日志） | — | false |
| `BACKEND_SCHEMA_INVALID` | protocol | 400 | error 帧 | false |
| `BACKEND_PROTOCOL_MISMATCH` | protocol | 400 | error 帧+close | false |
| `BACKEND_NOT_FOUND` | protocol | 404 | error 帧 | false |
| `BACKEND_BODY_TOO_LARGE` | limit | 413 | error 帧+close | false |
| `BACKEND_RATE_LIMITED` | limit | 429 | error 帧 | true |
| `BACKEND_ORIGIN_REJECTED` | auth | 403 | close | false |
| `BACKEND_CSRF_REJECTED` | auth | 403 | — | false |
| `BACKEND_SESSION_INVALID` | auth | 401 | error 帧+close | true |
| `BACKEND_TICKET_INVALID` | auth | 401 | close | true |
| `BACKEND_FORBIDDEN` | auth | 403 | error 帧 | false |
| `BACKEND_CONFIRMATION_REQUIRED` | auth | 428 | — | false |
| `BACKEND_STALE_REVISION` | conflict | 409 | error 帧 | false |
| `BACKEND_IDEMPOTENCY_CONFLICT` | conflict | 409 | error 帧 | false |
| `BACKEND_CONFLICT_STATE` | conflict | 409 | error 帧 | true |
| `BACKEND_WS_SUPERSEDED` | lifecycle | — | close | false |
| `BACKEND_SNAPSHOT_REQUIRED` | lifecycle | — | error 帧 | true |
| `BACKEND_QUEUE_FULL` | backpressure | 503 | error 帧 | true |
| `BACKEND_OVERLOADED` | backpressure | 503 | error 帧 | true |
| `BACKEND_MODEL_UNAVAILABLE` | upstream | 503 | error 帧 | true |
| `BACKEND_STORAGE_FAILURE` | storage | 503 | error 帧 | false |
| `BACKEND_SHUTDOWN` | lifecycle | 503 | error 帧+close | true |
| `BACKEND_INTERNAL_INVARIANT` | internal | 500 | error 帧+close | false |

`retryable=true` 且携带同 `command_id` 的重试受幂等保护（`DOC-BACKEND-010`）；`false` 表示必须改变请求内容或状态后才可能成功。

## 6. 正常流程

1. 校验位点或用例失败时构造 Error Object，查注册表确定 status 与 WS 行为。
2. REST 以 `{schema_version, error}` envelope 返回；WS 以 `error` 帧发送并按注册表决定是否 close。
3. Client 按 `retryable` 与 `retry_after_ms` 决定重试；命令类重试保持原 `command_id`。
4. category ∈ auth/internal 的错误同步写审计/诊断日志。
5. Overload/Shutdown 状态变化经广播事件同步到全部连接。

## 7. 边界情况

- 错误对象自身序列化失败：写出预构造的常量 `BACKEND_INTERNAL_INVARIANT` 响应，绝不静默空响应。
- 同请求同时命中多个失败：按 `RULE-BACKEND-022` 顺序返回第一个，不聚合多错误（Schema 校验错误可在 `details.reason_code` 给出首个字段路径）。
- Read-only Degradation 期间的存档请求：手动导出允许（只读已提交数据），写槽位拒绝。
- Drain 10 s 上限到期仍有在途 UoW：等待当前单个事务自然结束（串行写者最多一个在途），其余队列命令统一失败回执；超过 30000 real ms 硬上限则进程退出交由恢复序列保证一致性。
- 恢复期（Recovery Barrier）收到命令：`BACKEND_CONFLICT_STATE`（retryable），health 端点暴露进度。

## 8. 错误与降级

本文即错误与降级的 canonical 定义；元级约定：所有降级路径不得违反 `DOC-FOUNDATION-005` 不变量，不得以「自动修复」名义改写状态（`RULE-FOUNDATION-027` 补偿事件模式）。日志记录失败本身不得再抛出到请求路径（logging 失败静默丢弃该条并递增指标）。

## 9. 安全与性能

`message` 文案表与错误码同源管理，避免临时字符串携带内部信息；auth 类错误响应时间做常量化处理（不因失败原因不同产生可测时差）。错误构造路径无内存分配热点，注册表为启动期冻结的只读映射。错误计数按 code 维度进指标（`DOC-BACKEND-012`），审计条目含 `session_id` 与位点但不含请求正文。

## 10. 验收标准

- wire 抓包审计：出现的每个错误码均在注册表且 status/WS 行为一致。
- 模型全故障注入 30 game minutes：世界持续运行、无玩家不可见卡死，仅显式对话返回 `BACKEND_MODEL_UNAVAILABLE`。
- 存储写失败注入：回滚、只读降级、读取可用、恢复需完整性检查四点全验证。
- 队列压满与解除：单命令拒绝、Overload 广播、解除广播时序正确且无 DomainEvent 丢失。
- 关机序列每步注入 kill：重启后无半事务、所有已接受命令回执可取回。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-039` | `RULE-BACKEND-060..061` 注册表完备性与错误对象脱敏 |
| `TEST-BACKEND-040` | `RULE-BACKEND-062..063` 模型与存储失败恢复路径 |
| `TEST-BACKEND-041` | `RULE-BACKEND-064` 背压逐级与 Overload 广播 |
| `TEST-BACKEND-042` | `RULE-BACKEND-065` 安全关机步骤级故障注入 |

## 12. 关联文档

- `DOC-BACKEND-001`：Graceful Drain 进程内步骤
- `DOC-BACKEND-005` / `DOC-BACKEND-010`：回执、幂等与重试安全
- `DOC-AI-009` / `DOC-AI-011`：模型重试与 Utility 降级
- `DOC-TIME-011`：overload 判定阈值与降档链路
- `DOC-RELEASE-006`：存储损坏分级与修复

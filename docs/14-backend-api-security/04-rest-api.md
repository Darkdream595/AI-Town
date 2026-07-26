---
doc_id: DOC-BACKEND-004
title: REST API 目录与规范
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - rest-endpoint-catalog
  - rest-request-response-envelope
  - rest-validation-order
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-006
  - DOC-BACKEND-001
  - DOC-BACKEND-003
requirements:
  - REQ-BACKEND-004
last_updated: 2026-07-26
---

# REST API 目录与规范

## 1. 目的

`REQ-BACKEND-004`：定义全部 REST 端点、统一请求/响应 envelope、每个 Schema 的版本标识、统一验证顺序与副作用约束。REST 承载健康、世界管理、存档、设置、Secret、WebSocket Ticket 与诊断；游戏内实时命令走 WebSocket（`DOC-BACKEND-003`）。

## 2. 非目标

本文不定义 WebSocket 帧（`DOC-BACKEND-003`）、Command/Event payload 语义（`DOC-BACKEND-005..006`）、Session 与速率限制参数（`DOC-BACKEND-008`）、错误对象内部结构（`DOC-BACKEND-011`）、存档与世界文件布局（`DOC-RELEASE-001..006`）。不提供公共互联网 API，不做第三方集成。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Response Envelope | `{schema_version, data}` 或 `{schema_version, error}` 的统一外层 |
| Resource Schema | 每个端点 data/请求 body 的命名版本化结构，如 `WorldSummaryV1` |
| Confirmation Token | 破坏性管理操作要求的服务端一次性确认凭据 |
| Job Resource | 长任务的可轮询资源，含 `state` 与结果引用 |
| Route Class | 用于速率限制与审计归类的端点类别 |

## 4. 规则与不变量

- `RULE-BACKEND-019`：全部 REST 路径位于 `/api/v1/` 前缀；path major 版本与 `protocol_version` major 同步。`/api/`、`/ws/` 前缀下未注册路径返回 404，不做 SPA 回退（衔接 `RULE-BACKEND-002` 同源静态托管）。
- `RULE-BACKEND-020`：REST 只承载管理与查询用例；一切改变世界状态的游戏命令只能经 WebSocket `command` 帧进入 World Command Queue，REST 不提供世界写旁路。
- `RULE-BACKEND-021`：每个请求 body 与响应 data 都是携带 `schema_version` 的命名 Resource Schema；响应一律使用 Response Envelope，不裸返回数组或标量。
- `RULE-BACKEND-022`：统一验证顺序：transport → Origin/Host → 速率限制 → body 大小与 JSON 解析 → Session/CSRF（按 §5 端点表 auth 列执行：`anonymous_bootstrap` 端点跳过本步，`session_required` 只验 Session，`session_and_csrf_required` 两者都验）→ 权限 → `schema_version` 支持性 → payload Schema → 用例前置条件。任一步失败立即返回对应错误码，且不执行任何后续副作用；auth 豁免仅覆盖 Session/CSRF 一步，其余各步对全部端点强制执行。
- `RULE-BACKEND-023`：非 GET 端点必须幂等（PUT/DELETE 天然幂等，POST 携带 `command_id` 幂等键）；删除世界、覆盖存档槽、清除 Key 等破坏性操作还必须携带服务端颁发的一次性 Confirmation Token，缺失或过期返回 `BACKEND_CONFIRMATION_REQUIRED`。
- `RULE-BACKEND-024`：GET 无副作用且可缓存性显式为 `Cache-Control: no-store`；预计超过 1000 real ms 的操作（诊断包生成、世界导出）必须返回 202 与 Job Resource，由 Client 轮询，不长挂 HTTP 连接。

## 5. 数据与接口

`DES-BACKEND-004`：端点目录（auth 列是各端点认证要求的 canonical 依据，取值 `anonymous_bootstrap`（无 Session/CSRF 即可调用，loopback 绑定与 Origin/Host 校验仍强制）、`session_required`（须有效 Session）、`session_and_csrf_required`（Session + `X-AI-Town-Csrf` 头），执行位点与豁免语义见 `DOC-BACKEND-008`；所有 Schema 名称即注册表键，均含 `schema_version`）：

| 方法与路径 | 用途 | 请求 Schema | 响应 data Schema | auth | Route Class |
|---|---|---|---|---|---|
| `GET /api/v1/health` | 进程健康与 Recovery Barrier 状态 | — | `HealthStatusV1` | anonymous_bootstrap | health |
| `GET /api/v1/meta` | 应用版本、`protocol_version`、构建指纹 | — | `AppMetaV1` | anonymous_bootstrap | health |
| `POST /api/v1/session` | 建立/刷新本地 Session Cookie | `SessionRequestV1` | `SessionInfoV1` | anonymous_bootstrap | session |
| `POST /api/v1/ws-tickets` | 颁发单次 WebSocket Ticket | `WsTicketRequestV1` | `WsTicketV1` | session_and_csrf_required | ticket |
| `GET /api/v1/worlds` | 世界列表与元数据 | — | `WorldListV1` | session_required | world-admin |
| `POST /api/v1/worlds` | 创建世界（Seed、模板） | `WorldCreateV1` | `WorldSummaryV1` | session_and_csrf_required | world-admin |
| `GET /api/v1/worlds/{world_id}` | 单世界详情 | — | `WorldDetailV1` | session_required | world-admin |
| `POST /api/v1/worlds/{world_id}/open` | 打开世界（触发恢复序列） | `WorldOpenV1` | `WorldRuntimeStateV1` | session_and_csrf_required | world-admin |
| `POST /api/v1/worlds/{world_id}/close` | 关闭世界（Graceful Drain） | `WorldCloseV1` | `WorldRuntimeStateV1` | session_and_csrf_required | world-admin |
| `DELETE /api/v1/worlds/{world_id}` | 删除世界（需 Confirmation Token） | `WorldDeleteV1` | `WorldDeleteResultV1` | session_and_csrf_required | destructive |
| `GET /api/v1/worlds/{world_id}/saves` | 存档槽列表 | — | `SaveSlotListV1` | session_required | save |
| `POST /api/v1/worlds/{world_id}/saves` | 写手动存档槽（覆盖需 Token） | `SaveWriteV1` | `SaveSlotV1` | session_and_csrf_required | save |
| `POST /api/v1/worlds/{world_id}/saves/{save_id}/load` | 从槽位加载（分支语义见 `DOC-RELEASE-004`） | `SaveLoadV1` | `WorldRuntimeStateV1` | session_and_csrf_required | save |
| `GET /api/v1/settings` | 非敏感设置读取 | — | `SettingsV1` | session_required | settings |
| `PUT /api/v1/settings` | 非敏感设置写入 | `SettingsV1` | `SettingsV1` | session_and_csrf_required | settings |
| `PUT /api/v1/secrets/deepseek-api-key` | 提交/替换 DeepSeek Key | `SecretPutV1` | `SecretStatusV1` | session_and_csrf_required | secret |
| `GET /api/v1/secrets/deepseek-api-key/status` | Key 状态（masked） | — | `SecretStatusV1` | session_required | secret |
| `DELETE /api/v1/secrets/deepseek-api-key` | 删除 Key（需 Confirmation Token） | `SecretDeleteV1` | `SecretStatusV1` | session_and_csrf_required | destructive |
| `POST /api/v1/confirmations` | 颁发破坏性操作 Confirmation Token | `ConfirmationRequestV1` | `ConfirmationTokenV1` | session_and_csrf_required | destructive |
| `POST /api/v1/diagnostics/package` | 生成脱敏诊断包（Job） | `DiagnosticsRequestV1` | `JobResourceV1` | session_and_csrf_required | diagnostics |
| `GET /api/v1/diagnostics/jobs/{job_id}` | 轮询诊断 Job | — | `JobResourceV1` | session_required | diagnostics |
| `GET /api/v1/diagnostics/metrics` | 本地指标快照 | — | `MetricsSnapshotV1` | session_required | diagnostics |

Envelope 与示例（`HealthStatusV1`）：

```json
{
  "schema_version": 1,
  "data": {
    "schema_version": 1,
    "process_state": "ready",
    "recovery_barrier_active": false,
    "open_world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "current_revision": 40821,
    "uptime_ms": 5230000
  }
}
```

`JobResourceV1.state` ∈ `queued/running/succeeded/failed`；成功时含 `result_ref`（本地文件句柄 ID，不含文件系统绝对路径）。

## 6. 正常流程

1. 前端加载后依次调用 `GET /health`、`POST /session`、`GET /worlds`：前两步为 `anonymous_bootstrap`（无 Cookie 状态下合法），`POST /session` 返回 Session 与 CSRF Cookie 后，后续请求按 auth 列全量校验（`RULE-BACKEND-045` 的 bootstrap 豁免）。
2. 玩家选择世界后 `POST /worlds/{id}/open`；成功进入 `ready` 后 `POST /ws-tickets` 并建立 WebSocket。
3. 运行期管理操作（存档、设置、Key、诊断）继续走 REST，与 WebSocket 通道并存。
4. 破坏性操作先 `POST /confirmations` 获取 Token，UI 二次确认后携带 Token 提交。
5. 退出时 `POST /worlds/{id}/close` 触发 Graceful Drain（`DOC-BACKEND-001` §6）。

## 7. 边界情况

- 世界处于 Recovery Barrier：world-admin 只读端点可用，写端点返回 `BACKEND_CONFLICT_STATE`（见 `DOC-BACKEND-011`）；health 始终可用。
- 重复 `POST /worlds`（同 `command_id`）：返回首个创建结果，不产生第二个世界（`RULE-FOUNDATION-022`）。
- 打开一个已打开的世界：幂等返回当前 `WorldRuntimeStateV1`；打开另一世界前必须先 close 当前世界。
- 存档写入与运行中事务并发：存档只能锚定已提交 Revision（`RULE-FOUNDATION-029`），实现见 `DOC-RELEASE-004`。
- Job 完成前进程重启：Job Resource 标记 `failed` 且 `reason_code=process_restarted`，Client 重新发起；Job 不跨进程恢复。

## 8. 错误与降级

全部错误使用 `DOC-BACKEND-011` 的统一错误对象与 HTTP 映射。JSON 解析失败返回 `BACKEND_SCHEMA_INVALID`（400），不回显原始 body；未知 `schema_version` 返回 `BACKEND_PROTOCOL_MISMATCH`（400）。存储层故障时管理端点进入只读降级：GET 类可用，写类统一 `BACKEND_STORAGE_FAILURE`（503）。

## 9. 安全与性能

所有端点继承 `DOC-BACKEND-008` 的 Origin/Host、速率与 body 限制（`anonymous_bootstrap` 端点亦不豁免）；Session/CSRF 按 §5 auth 列执行；`secret`、`destructive` Route Class 使用最严格限额并全量审计。响应不含文件系统绝对路径、堆栈或内部配置；`world_id`、`save_id` 等 ID 可出现。管理端点目标 p95 预算见 `DOC-BACKEND-012`。列表端点分页上限 100 条，防止超大响应。

## 10. 验收标准

- 端点目录与实现路由一一对应，无未登记路由（含 debug 路由）通过 CI 路由清单比对。
- 每个请求/响应 body 均含 `schema_version`，golden 样本校验通过。
- 验证顺序注入测试：每一步失败均无后续副作用（数据库无写、无 Job 创建）。
- 破坏性操作缺 Token、Token 过期/重放均被拒绝且审计。
- 长任务全部走 Job 轮询，无超过 1000 real ms 的同步阻塞响应。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-013` | `RULE-BACKEND-019..020` 路由清单、404 边界与无世界写旁路 |
| `TEST-BACKEND-014` | `RULE-BACKEND-021..022` envelope、版本、验证顺序无副作用与 auth 列逐端点执行一致性 |
| `TEST-BACKEND-015` | `RULE-BACKEND-023` POST 幂等与 Confirmation Token 生命周期 |
| `TEST-BACKEND-016` | `RULE-BACKEND-024` GET 无副作用与 Job 化长任务 |

## 12. 关联文档

- `DOC-BACKEND-003`：Ticket 端点的消费方
- `DOC-BACKEND-007`：Schema 版本化与兼容规则
- `DOC-BACKEND-008`：Session、CSRF、速率与 body 限制
- `DOC-BACKEND-011`：错误对象与 HTTP 映射
- `DOC-RELEASE-004..006`：存档槽、世界管理与恢复的持久化语义

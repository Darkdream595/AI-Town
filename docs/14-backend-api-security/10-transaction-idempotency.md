---
doc_id: DOC-BACKEND-010
title: 事务编排与幂等存储
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - unit-of-work-commit-protocol
  - idempotency-store
  - cross-domain-transaction-orchestration
depends_on:
  - DOC-FOUNDATION-005
  - DOC-BACKEND-002
  - DOC-BACKEND-005
  - DOC-ECON-006
requirements:
  - REQ-BACKEND-010
last_updated: 2026-07-26
---

# 事务编排与幂等存储

## 1. 目的

`REQ-BACKEND-010`：定义所有命令共用的 Unit of Work 提交协议、幂等存储结构与保留策略、跨 Domain 联合写编排、外部效应（模型调用、文件导出）与事务的边界，落实 `RULE-FOUNDATION-022/023/029` 并把 `DOC-ECON-006` 建立的幂等先例推广为后端通用机制。

## 2. 非目标

本文不定义各 Domain 的业务校验与 Reservation 顺序（如 `DOC-ECON-005..006`）、SQLite 连接与 WAL 配置（`DOC-RELEASE-001`）、Command Envelope 协议层幂等检查位点（`DOC-BACKEND-005`）。BACKEND 拥有机制，owner Domain 拥有规则与结果语义。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Unit of Work (UoW) | 一次命令的状态、事件、幂等结果、Reservation 结果的原子提交单元 |
| Idempotency Record | `(world_id, command_id)` 键下的结果引用与 payload hash |
| Canonical Payload Hash | 对 payload 做键排序、无空白序列化后的 SHA-256 |
| Result Ref | 指向 CommandReceipt 物化结果的持久引用 |
| External Effect | 无法纳入数据库事务的副作用（模型请求、文件写出） |
| Retention Window | 幂等记录必须可查询的最小保留范围 |

## 4. 规则与不变量

- `RULE-BACKEND-055`：Idempotency Record 以 `(world_id, command_id)` 唯一，内容含 `payload_hash`、`result_ref`、`committed_revision`、`recorded_at`；记录必须与状态变更、DomainEvent 在同一数据库事务写入（细化 `RULE-BACKEND-010`、落实 `RULE-FOUNDATION-022`）。协议层拒绝（未被接受的命令）不产生记录。
- `RULE-BACKEND-056`：重复命中幂等键时直接返回原 Result Ref 物化的 CommandReceipt，不重新执行任何 Domain 逻辑；`payload_hash` 不一致返回 `BACKEND_IDEMPOTENCY_CONFLICT`，不得以旧成功伪装新请求（与 `RULE-ECON-022` 同语义）。
- `RULE-BACKEND-057`：Retention Window：每世界至少保留 `max(30 game days, 100000 条)` 的幂等记录；裁剪只在 Snapshot 检查点整批执行，且不得早于 Event Log 的重连补发窗口（`catch_up_max_events`），保证断线 Client 凭 `command_id` 取回回执（`RULE-BACKEND-030`）始终可行。
- `RULE-BACKEND-058`：UoW 提交协议：单一 World Writer 串行执行 `BEGIN IMMEDIATE → 写状态 → append 事件 → 写幂等记录 → 消费/释放 Reservation → Commit Check（DOC-FOUNDATION-005）→ COMMIT → Revision +1`；任一步失败整体回滚、Revision 不变（`RULE-FOUNDATION-023`）、不发布任何事件。
- `RULE-BACKEND-059`：External Effect 不进入 UoW：需要外部效应的用例拆为「提交意图事件 → 异步执行（幂等完成）→ 结果以新命令/输入回到 World Command Queue 在最新 Revision 重校验（`RULE-FOUNDATION-007`）」；禁止在事务内 await 外部 I/O，也禁止把多步外部效应伪装成单事务的「先扣后给」。

## 5. 数据与接口

`DES-BACKEND-010`：Idempotency Record：

```json
{
  "schema_version": 1,
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "payload_hash": "sha256:8de5c7a8d5f0b3a1c4e6f8091a2b3c4d5e6f70819a2b3c4d5e6f70819a2b3c4d",
  "result_ref": "receipt/01K1AB2CD3EF4GH5JK6MNP7QRT",
  "result_kind": "committed",
  "committed_revision": 40822,
  "recorded_at": "2026-07-26T08:30:15.250Z"
}
```

`result_kind` ∈ `committed/failed`——两种终局都物化，重复提交失败命令同样返回原失败回执，而不是重新执行。

Orchestrator 接口（对 `api/` 暴露的全部事务能力）：

```text
submit_command(envelope, session_identity) -> queued | rejected(error)
lookup_receipt(world_id, command_id) -> CommandReceipt | not_found
run_uow(command) -> CommandReceipt        # 仅 World Writer 内部
```

跨 Domain 联合写（细化 `DOC-BACKEND-002` §7）：Orchestrator 在同一 UoW 内按 Domain 名称字典序固定顺序调用各 owner Port，Reservation 获取遵循资源全序（`DOC-ECON-005` 先例），Commit Check 覆盖联合写集；不存在跨 UoW 的两阶段提交。

## 6. 正常流程

1. 命令经 `DES-BACKEND-005` 协议检查后入 World Command Queue。
2. World Writer 取出命令，`lookup` 幂等键——命中即返回原回执（该查询只读，不占事务）。
3. 未命中：开启 UoW，按 `RULE-BACKEND-058` 顺序执行 owner Domain 逻辑与提交。
4. COMMIT 成功后 Outbox 发布事件、发送 `command_receipt(committed)`。
5. 需要外部效应的用例按 `RULE-BACKEND-059` 拆分，异步结果回到队列走同一管线。

## 7. 边界情况

- 崩溃于 COMMIT 前：无任何可见变化，无幂等记录；Client 重试同 `command_id` 正常执行（与 `DOC-ECON-006` §7 crash 语义一致）。
- 崩溃于 COMMIT 后、receipt 发送前：恢复后 Client 重试命中幂等记录，取回原回执；Outbox 按已提交事件重发（`RULE-BACKEND-035`）。
- 幂等查询命中但 Result Ref 物化数据缺失：属存储不一致，返回 `BACKEND_INTERNAL_INVARIANT` 并触发 Recovery Barrier 审计，不重新执行命令。
- 同一命令在队列中重复出现（Client 超时重发且首个尚未执行）：第二份在执行时命中首份写入的幂等记录；若首份仍未执行则第二份按到达顺序自然排在其后，执行时命中。
- 世界分支/回档加载（`DOC-RELEASE-004`）：幂等存储随世界数据一起锚定到目标 Revision，分支后的重复 `command_id` 按分支内记录判定。

## 8. 错误与降级

UoW 内 Domain 异常：回滚、返回 `failed` 回执（owner reason code）并物化；连续同类失败按 `DOC-TIME-003` §8 隔离 owner。数据库写失败：回滚并返回 `BACKEND_STORAGE_FAILURE`，该世界进入只读降级（`RULE-BACKEND-063`）。幂等存储裁剪与查询失败视为存储失败，不允许「查不到就当新命令」的降级。

## 9. 安全与性能

Canonical Payload Hash 使用键排序 JSON 序列化，杜绝字段顺序差异造成伪冲突；hash 计算在协议层完成一次并随命令传递，不重复计算。幂等查询走 `(world_id, command_id)` 唯一索引，目标 < 1 ms；Result Ref 物化只存 ID、result、revision、error code，不存 payload 正文。单 UoW 写集上限继承各 owner 限幅（如 `DOC-ECON-006` §9 的 legs 上限）。

## 10. 验收标准

- 每个故障注入点（每条 UoW 步骤后 kill）恢复后满足：无半事务、Revision 与 Event Log 一致、重试返回确定结果。
- 重复命令 1000 次并发压测：恰好一次状态变化，其余全部命中原回执。
- 同 `command_id` 不同 payload 的冲突检测在字段重排、空白差异下不误报、不漏报。
- Retention Window 内任意 `command_id` 可查询回执；裁剪后 Event Log 补发窗口仍完整。
- 跨 Domain 联合写在并发下无死锁（固定顺序）且全成或全败。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-036` | `RULE-BACKEND-055..056` 幂等记录原子性与冲突判定 |
| `TEST-BACKEND-037` | `RULE-BACKEND-057..058` 保留窗口、UoW 步骤级故障注入 |
| `TEST-BACKEND-038` | `RULE-BACKEND-059` 外部效应拆分与最新 Revision 重校验 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：`RULE-FOUNDATION-022/023/029` 上游不变量
- `DOC-BACKEND-002`：UoW 契约与包边界
- `DOC-BACKEND-005`：协议层幂等位点与回执取回
- `DOC-ECON-006`：经济域事务规则先例与 Reservation 顺序
- `DOC-RELEASE-001..004`：数据库布局、Snapshot 检查点与分支语义

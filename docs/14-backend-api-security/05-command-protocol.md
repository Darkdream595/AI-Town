---
doc_id: DOC-BACKEND-005
title: Command Envelope 协议
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - command-envelope-schema
  - command-receipt-contract
  - command-validation-order
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-BACKEND-003
  - DOC-BACKEND-004
requirements:
  - REQ-BACKEND-005
last_updated: 2026-07-26
---

# Command Envelope 协议

## 1. 目的

`REQ-BACKEND-005`：定义所有写命令的统一 Command Envelope、命令类型注册表、服务器权威字段边界、strict/relaxed Revision 语义、命令级验证顺序与 CommandReceipt 回执契约。

## 2. 非目标

本文不定义各命令 payload 的业务字段与合法性（owner Domain 文档，如 `DOC-PLAYER-007..009`、`DOC-ECON-006`）、Event Envelope（`DOC-BACKEND-006`）、幂等存储实现（`DOC-BACKEND-010`）、传输层帧格式（`DOC-BACKEND-003`）。AI ActionProposal 不是 Command——它经 `DOC-AI-004..005` 校验后由服务器内部转化为世界输入，不走本协议的外部入口。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Command Envelope | Client 发起写意图的统一外层结构 |
| Command Registry | `type -> {payload Schema, 角色要求, revision 模式, 队列}` 的注册表 |
| Strict Revision | `expected_revision` 必须精确匹配当前 Revision 的模式 |
| Relaxed Revision | `expected_revision` 为 null，由 Domain 在最新状态校验的模式 |
| CommandReceipt | 每个命令恰好一份的终局回执 |
| Authoritative Field | 只能由服务器补充或计算、Client 不可指定的字段 |

## 4. 规则与不变量

- `RULE-BACKEND-025`：Command Envelope 顶层字段固定为 `protocol_version`、`command_id`、`world_id`、`expected_revision`、`type`、`payload` 六个必填项；顶层出现未注册字段即拒绝 `BACKEND_SCHEMA_INVALID`，不忽略、不透传。
- `RULE-BACKEND-026`：`command_id` 为 Client 生成 ULID，`(world_id, command_id)` 是幂等键（落实 `RULE-FOUNDATION-022`、`RULE-FOUNDATION-034`）；同键重复提交返回原 CommandReceipt；同键不同 canonical payload hash 返回 `BACKEND_IDEMPOTENCY_CONFLICT`。
- `RULE-BACKEND-027`：`type` 必须命中 Command Registry 的 tagged union（前缀 `player.*`、`mayor.*`、`admin.*`、`system.*`）；payload 按注册的 strict Schema 校验：含 `schema_version`、`additionalProperties=false`、全部数值有限、单位后缀符合 `RULE-FOUNDATION-045`。
- `RULE-BACKEND-028`：Authoritative Field（`actor_id`、Session 身份、结算金额、伤害、路径、GameTime、Revision、event ID）由服务器从 Session 与已提交状态补充；payload 内出现伪造权威字段按 `FORBIDDEN` 类拒绝（`BACKEND_FORBIDDEN`）并写审计日志。
- `RULE-BACKEND-029`：Revision 模式由 Command Registry 按 `type` 静态决定，Client 不可协商：交易、战斗、建造、admin 命令为 Strict（不匹配返回 `BACKEND_STALE_REVISION`）；移动、对话发起等为 Relaxed（`expected_revision` 必须显式为 null）。Strict 命令缺失 `expected_revision` 即拒绝。
- `RULE-BACKEND-030`：每个被接受的命令恰好产生一份终局 CommandReceipt（`committed` 或 `failed`），拒绝的命令产生 `rejected` 回执；连接断开不豁免——重连后 Client 可凭 `command_id` 经幂等存储取回原回执（`DOC-BACKEND-010`）。

## 5. 数据与接口

`DES-BACKEND-005`：Command Envelope 实例（`mayor.notice.publish`，payload Schema 由 `DOC-PLAYER-008` 拥有）：

```json
{
  "protocol_version": 1,
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "expected_revision": null,
  "type": "mayor.notice.publish",
  "payload": {
    "schema_version": 1,
    "title": "秋收集市公告",
    "body_text": "本周六在镇广场举办秋收集市。",
    "effective_game_time": 1830
  }
}
```

CommandReceipt：

```json
{
  "schema_version": 1,
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "result": "committed",
  "committed_revision": 40822,
  "event_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRW"],
  "error": null
}
```

`result` ∈ `rejected/committed/failed`；`rejected/failed` 时 `committed_revision` 与 `event_ids` 为 null/空，`error` 为 `DOC-BACKEND-011` 错误对象。

命令级验证顺序（在 `RULE-BACKEND-022` 传输级检查通过之后）：

```text
1. Envelope 顶层 Schema 与 protocol_version
2. type 注册表命中与角色权限（DOC-BACKEND-008 权限执行点）
3. 幂等键查询（命中即返回原回执）
4. payload strict Schema（schema_version 分发）
5. Authoritative Field 伪造检测
6. Revision 模式检查（Strict 精确匹配）
7. 入 World Command Queue；Domain precondition 与 Commit Check 在 World Writer 内执行
```

Command Registry 行示例：

| type | payload Schema | 角色 | Revision 模式 |
|---|---|---|---|
| `player.move.set_target` | `PlayerMoveTargetV1` | player | relaxed |
| `player.dialogue.say` | `PlayerDialogueSayV1` | player | relaxed |
| `mayor.tax.propose` | `MayorTaxProposeV1` | mayor | strict |
| `admin.resource.grant` | `AdminResourceGrantV1` | admin | strict |
| `system.world.pause` | `SystemWorldPauseV1` | player | relaxed |

完整 union 由各 owner 文档定义（`DOC-PLAYER-007..009` 等），本注册表只登记接线信息，不复述 payload 字段。

## 6. 正常流程

1. Client 生成 `command_id`，按当前投影决定 `expected_revision`（Strict 类）并发送 `command` 帧。
2. Gateway 按 §5 顺序完成 1–6 步；通过后回 `accepted` 语义（进入队列，不单独发帧）并入队。
3. World Writer 在最新 Revision 上执行 Domain 校验与 UoW 提交（`DOC-BACKEND-010`）。
4. 提交成功：同一事务写入幂等结果，Outbox 发布事件，随后发送 `command_receipt(committed)`。
5. Client 收到 receipt 与对应事件后更新权威投影；渲染以事件为准，不以本地预测为准。

## 7. 边界情况

- receipt 与事件到达顺序：事件按 Revision 流推送，receipt 单独发送，Client 必须容忍 receipt 先于或晚于对应事件到达（以 `event_ids` 关联）。
- Strict 命令在排队期间 Revision 前进：以 World Writer 执行时刻的比较为准——入队时不预判，执行时不匹配即 `BACKEND_STALE_REVISION`，无部分效果。
- 同一 Session 并发多命令：按到达顺序入队；命令间无隐式依赖，Client 需要顺序语义时应等待前一 receipt。
- 队列满：入队失败返回 `rejected(BACKEND_QUEUE_FULL)`，幂等存储不记录（未接受），Client 可原 `command_id` 重试。
- shutdown 期间到达：`rejected(BACKEND_SHUTDOWN)`；已入队命令按 `RULE-BACKEND-065` 完成或统一失败回执。

## 8. 错误与降级

协议层拒绝（1–6 步）不消耗 Revision、不写幂等存储（幂等冲突除外——该查询本身只读）；Domain 层失败产生 `failed` 回执并携带 owner reason code。错误对象与重试语义见 `DOC-BACKEND-011`。Gateway 不修复、不改写 payload——修复语义只存在于 AI Proposal 管线（`DOC-AI-010`），不适用于玩家命令。

## 9. 安全与性能

权限检查先于 payload 解析深层结构，降低未授权输入的解析面；payload 文本字段（公告、对话）按纯文本处理，长度上限由 owner Schema 定义并受 `RULE-BACKEND-048` 帧上限约束。命令日志记录 `command_id`、`type`、result、reason code 与延迟，不记录 payload 正文（对话与公告文本的日志策略见 `DOC-BACKEND-012` 脱敏表）。

## 10. 验收标准

- 六字段 Envelope 之外的任何顶层字段被拒绝，模糊测试无一透传。
- 幂等重复、payload hash 冲突、Strict 过期、伪造权威字段四类各返回稳定错误且无状态变化。
- 每个被接受命令在正常、断线、崩溃重启三种场景下均恰好一份终局回执可取回。
- Registry 与 owner 文档的 union 清单一致性由 CI 比对通过。
- relaxed 命令显式 null 与 strict 命令精确匹配的矩阵测试全通过。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-017` | `RULE-BACKEND-025..026` Envelope 严格性与幂等键行为 |
| `TEST-BACKEND-018` | `RULE-BACKEND-027..028` Registry 分发与权威字段伪造拒绝 |
| `TEST-BACKEND-019` | `RULE-BACKEND-029` strict/relaxed Revision 矩阵 |
| `TEST-BACKEND-020` | `RULE-BACKEND-030` 回执恰好一次与断线取回 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：幂等、Revision 与提交不变量
- `DOC-BACKEND-006`：命令产生事件的 Envelope
- `DOC-BACKEND-008`：角色与权限执行点
- `DOC-BACKEND-010`：幂等存储与 UoW 提交
- `DOC-PLAYER-007..009`：player/mayor/admin 命令 union 与权限矩阵

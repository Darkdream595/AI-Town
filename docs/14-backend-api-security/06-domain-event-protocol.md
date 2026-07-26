---
doc_id: DOC-BACKEND-006
title: Domain Event 协议
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - event-envelope-schema
  - causation-correlation-semantics
  - render-payload-boundary
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-BACKEND-005
requirements:
  - REQ-BACKEND-006
last_updated: 2026-07-26
---

# Domain Event 协议

## 1. 目的

`REQ-BACKEND-006`：定义 Event Envelope 的完整字段、causation/correlation 因果语义、render payload 的表现边界、事件顺序与去重、可合并 render delta 的分类，落实 `RULE-FOUNDATION-021` 与 `RULE-FOUNDATION-003`。

## 2. 非目标

本文不定义各事件 payload 的业务字段（owner Domain 文档）、Event Log 持久化与裁剪（`DOC-RELEASE-003`）、传输帧与 catch-up（`DOC-BACKEND-003`）、前端如何消费 render 提示（`DOC-RENDER-*`）。事件类型清单由各 owner 登记，本文只拥有 Envelope 与因果结构。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Event Envelope | 已提交 DomainEvent 对外发布的统一外层结构 |
| Causation ID | 直接原因的 ID：command_id、上游 event_id 或 proposal_id |
| Correlation ID | 因果链首的 ID，整条链继承不变 |
| Render Payload | 面向表现层的非权威提示对象，可为 null |
| Coalescible Delta | 可被合并/丢弃的纯表现更新（如逐段位置） |
| Event Registry | `type -> {payload Schema, owner_domain, coalescible}` 注册表 |

## 4. 规则与不变量

- `RULE-BACKEND-031`：Event Envelope 顶层字段固定为 `protocol_version`、`event_id`、`world_id`、`revision`、`type`、`game_time`、`causation_id`、`correlation_id`、`payload`、`render` 十项；除 `render` 可为 null 外全部必填。字段集与 `RULE-FOUNDATION-021` 一致，追加字段需走 `DOC-BACKEND-007` 版本化。
- `RULE-BACKEND-032`：`causation_id` 指向直接原因（外部命令为 `command_id`，衍生事件为上游 `event_id`，AI 行动为 `proposal_id`）；`correlation_id` 为链首 ID 且整链继承。两者由服务器在提交事务内填充，Client 与模型输入中的任何因果声明一律忽略。
- `RULE-BACKEND-033`：`payload` 是 owner Domain 的版本化 Schema（含 `schema_version`）；`render` 只含表现提示（路径点序列、`animation_id`、`duration_ms`、音效与镜头 hint），不含余额、伤害、权限等权威语义；Client 不得从 `render` 推导规则事实（落实 `RULE-FOUNDATION-003`）。
- `RULE-BACKEND-034`：DomainEvent 不可丢弃、不可重排：同一 world 按 `revision` 全序发布与推送；仅 Event Registry 标记 `coalescible=true` 的纯表现 delta 可在 Outbox 合并或丢弃（`RULE-BACKEND-017`），且此类 delta 不得携带任何权威 payload。
- `RULE-BACKEND-035`：事件只能从已提交事务的 Outbox 读出后发布，禁止提交前发布；补发与重试保持 `event_id` 不变，Client 按 `event_id` 幂等去重。同一 `revision` 内多个事件的相对顺序为提交时写入顺序，重放不变。
- `RULE-BACKEND-036`：`payload` 与 `render` 均不得包含未授权 Secret、他人私有 Belief、API Key 或 `reasoning_content`（落实 `RULE-FOUNDATION-024`）；对话正文只进入该对话可见参与者的定向事件流，广播事件只含脱敏摘要 ID。

## 5. 数据与接口

`DES-BACKEND-006`：Event Envelope 实例（economy 交易完成，payload Schema 由 `DOC-ECON-006` 拥有）：

```json
{
  "protocol_version": 1,
  "event_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 40822,
  "type": "economy.transaction.committed",
  "game_time": 1831,
  "causation_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "correlation_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "payload": {
    "schema_version": 1,
    "transaction_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
    "kind": "shop_sale",
    "buyer_account_id": "01K1AB2CD3EF4GH5JK6MNP7QRY",
    "seller_account_id": "01K1AB2CD3EF4GH5JK6MNP7QRZ",
    "total_copper_feather": 110
  },
  "render": {
    "schema_version": 1,
    "animation_id": "anim.shop.checkout",
    "duration_ms": 1200,
    "sound_id": "sfx.coin_clink",
    "focus_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS0"
  }
}
```

Coalescible render delta（无权威 payload）：

```json
{
  "protocol_version": 1,
  "event_id": "01K1AB2CD3EF4GH5JK6MNP7QS1",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 40822,
  "type": "render.position.delta",
  "game_time": 1831,
  "causation_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "correlation_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "payload": {
    "schema_version": 1,
    "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS0",
    "position": {"scene_id": "region.crown_creek_town", "x_wu": 1040.0, "y_wu": 772.5},
    "facing_degrees": 90
  },
  "render": null
}
```

`render.position.delta` 的 `payload` 是权威位置的表现采样：合并时只保留最新一条，Client 权威位置以 Snapshot 与 owner DomainEvent 为准。

Event Registry 行示例：

| type | payload Schema | owner_domain | coalescible |
|---|---|---|---|
| `economy.transaction.committed` | `EconomyTransactionCommittedV1` | economy | false |
| `resident.action.completed` | `ResidentActionCompletedV1` | residents | false |
| `dialogue.line.spoken` | `DialogueLineSpokenV1` | dialogue | false |
| `render.position.delta` | `RenderPositionDeltaV1` | backend | true |
| `world.weather.changed` | `WorldWeatherChangedV1` | events | false |

## 6. 正常流程

1. World Writer 在 UoW 内生成事件并连同状态原子提交（`RULE-FOUNDATION-029`）。
2. Outbox 读取已提交事件，按 Session 订阅范围与可见性过滤（`RULE-BACKEND-036`）。
3. Sender 按 revision 顺序推送；coalescible delta 在缓冲内合并。
4. Client 按 `event_id` 去重后应用 payload 更新权威投影，`render` 只驱动动画与音效。
5. 重连时 catch-up 只补发 `coalescible=false` 的事件，位置由 Snapshot 或最新 delta 收敛。

## 7. 边界情况

- 一个命令产生多个事件：共享 `causation_id=command_id`，各自独立 `event_id`，同 revision 内保持提交顺序。
- 事件驱动事件（交易→通知→关系变化）：每级 `causation_id` 指向上一级 `event_id`，`correlation_id` 保持链首命令/提案 ID。
- 定向对话事件：仅参与者 Session 收到含正文的事件；旁观者收到 `dialogue.overheard.summary` 类脱敏事件（owner 为 DIALOGUE 域），两者 `correlation_id` 相同。
- render 为 null：Client 不播放动画，仅更新数据；payload 为空对象的纯表现事件禁止——无权威内容时必须标记 coalescible。
- 撤销/补偿：以新事件表达（`RULE-FOUNDATION-027`），`causation_id` 指向被补偿事件，Client 不回滚历史应用而是应用新事件。

## 8. 错误与降级

Envelope 组装失败（字段缺失、Registry 未命中）属于 `BACKEND_INTERNAL_INVARIANT`——事务已提交的事件不允许发布失败而丢弃，Outbox 重试直至成功或触发连接级 Snapshot fallback。Client 侧 payload Schema 校验失败时丢弃该帧并请求 Snapshot resync，不猜测字段。

## 9. 安全与性能

可见性过滤在 Outbox 层按 Session 角色与参与者集合执行，过滤逻辑只读已提交状态。Envelope 顶层开销固定，payload 由 owner Schema 限幅；单事件序列化后不得超过 `RULE-BACKEND-048` 帧上限，超限事件必须由 owner 拆分设计而非截断。事件日志只记录 `event_id`、`type`、revision 与字节数，不记录 payload 正文。

## 10. 验收标准

- 全部发布事件通过 Envelope 十字段完整性与 Registry 命中校验。
- 任意因果链上 `correlation_id` 不变、`causation_id` 逐级正确，可从日志重建完整因果树。
- coalescible 合并前后，Client 最终权威投影与服务器逐字段一致。
- 重放、补发、重连场景下 `event_id` 去重后无重复应用。
- 秘密可见性注入测试：未授权 Session 收不到含正文/Secret 的事件。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-021` | `RULE-BACKEND-031..032` Envelope 完整性与因果链构造 |
| `TEST-BACKEND-022` | `RULE-BACKEND-033..034` render 边界、全序与 coalescible 合并 |
| `TEST-BACKEND-023` | `RULE-BACKEND-035` 提交后发布、event_id 稳定与去重 |
| `TEST-BACKEND-024` | `RULE-BACKEND-036` 可见性过滤与 Secret 泄漏注入 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：`RULE-FOUNDATION-021/024/027/029` 上游不变量
- `DOC-BACKEND-003`：推送、ack、catch-up 与 Snapshot fallback
- `DOC-BACKEND-005`：causation 源头 Command Envelope
- `DOC-BACKEND-007`：Envelope 与 payload 的版本化
- `DOC-RELEASE-003`：Event Log 持久化与裁剪窗口

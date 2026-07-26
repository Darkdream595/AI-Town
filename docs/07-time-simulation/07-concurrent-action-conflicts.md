---
doc_id: DOC-TIME-007
title: 并发行动冲突与 Reservation
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - generic-reservation-lifecycle
  - stable-lock-order
  - concurrent-action-conflict-policy
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-008
  - DOC-TIME-004
  - DOC-TIME-006
requirements:
  - REQ-TIME-007
last_updated: 2026-07-26
---

# 并发行动冲突与 Reservation

## 1. 目的

`REQ-TIME-007`：定义通用 Reservation envelope、稳定 lock order、全取或全不取、冲突胜者、到期和恢复策略，防止同一 actor、工作点、门、物品或预算被并发行动重复占用。

## 2. 非目标

本文不拥有物品数量、货币、Door capacity 或建筑土地规则。资源 owner 通过 Port 判断可用性、消费和补偿；TIME 不 import 其 aggregate 或 Repository。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Reservation Envelope | TIME 拥有的通用 owner/resource/quantity/expiry/state 声明 |
| Resource Key | `{lock_rank, owner_domain, resource_type, resource_id, slot}` 的稳定键 |
| Lock Set | 一个行动开始前必须原子获得的全部 Resource Key |
| Stable Lock Order | 全系统对 Lock Set 的唯一排序，避免循环等待 |
| Conflict Winner | 在同一可提交视图中按 scheduler priority 与 accepted sequence 先取得资源的请求 |
| Resource Owner | 定义资源是否可预留、如何消费/释放的 canonical domain |

## 4. 规则与不变量

- `RULE-TIME-037`：Reservation 状态只允许 `requested → held → consumed/released/expired`；恢复不确定时为 `recovery_pending`，终态不可回到 held。
- `RULE-TIME-038`：Lock Set 先完整排序再在一个 Unit of Work 全取或全不取；禁止持有部分 lock 等待另一资源。
- `RULE-TIME-039`：排序键为 `(lock_rank, owner_domain, resource_type, resource_id, slot)` 的逐字段升序；lock rank 固定为 world=0、actor=10、scene/entrance=20、semantic/workstation=30、property=40、inventory/item=50、currency/budget=60、domain-specific=90。
- `RULE-TIME-040`：同一资源冲突按 `(priority_class, accepted_sequence, command_id)` 选胜者；已 held 的 Reservation 不被普通高优先级请求强抢，只能由明确 emergency policy 中断其行动。
- `RULE-TIME-041`：expiry 使用 GameTime；Pause 和关闭期间不失效。AI worker 的 RealTime lease 是不同类型，不能当作资源 Reservation。
- `RULE-TIME-042`：consume 必须与 owner 状态变化及不可丢 DomainEvent 同事务；到期/释放不等同业务成功。

## 5. 数据与接口

`DES-TIME-007`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/reservation/v1",
  "type": "object",
  "required": ["schema_version", "reservation_id", "world_id", "holder_kind", "holder_id", "resource_key", "quantity", "state", "expires_at_game_time", "version"],
  "properties": {
    "schema_version": {"const": 1},
    "reservation_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "holder_kind": {"enum": ["actor", "long_action", "world_event", "command"]},
    "holder_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "resource_key": {
      "type": "object",
      "required": ["lock_rank", "owner_domain", "resource_type", "resource_id", "slot"],
      "properties": {
        "lock_rank": {"enum": [0, 10, 20, 30, 40, 50, 60, 90]},
        "owner_domain": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "resource_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "resource_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "slot": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": false
    },
    "quantity": {"type": "integer", "minimum": 1},
    "state": {"enum": ["requested", "held", "consumed", "released", "expired", "recovery_pending"]},
    "expires_at_game_time": {"type": "integer", "minimum": 0},
    "version": {"type": "integer", "minimum": 1}
  },
  "additionalProperties": false
}
```

接口：

```text
acquire_reservation_set(command_id, sorted_requests, expected_revision) -> ReservationSetResult
consume_reservation_set(set_id, owner_commit_plan) -> ConsumeResult
release_reservation_set(set_id, reason) -> ReleaseResult
expire_due_reservations(due_game_time) -> ExpiryBatch
recover_reservations(snapshot, event_tail) -> RecoveryReport
```

## 6. 正常流程

1. Action owner 解析业务所需资源并生成 resource requests。
2. TIME 验证 lock rank registry、稳定排序和重复 key 合并。
3. Orchestrator 依序调用各 Resource Owner 的 reserve validation。
4. 全部通过后同事务写 held records；任一失败则全量不写。
5. 完成时 owner 原子消费；中断/取消/到期时按 policy 释放。

## 7. 边界情况

- 两名 actor 同 Tick 请求 capacity=1 的 Door：全序较前者 held，后者返回 `conflict_retryable` 并可排队。
- 一个 craft 同时需要 actor、workstation、三种 item：按 rank/ID 全量排序，任一 item 不足则零 Reservation。
- emergency 中断已 held 行动时，先提交 interruption 与 owner compensation，再释放；不能直接偷锁。
- Reservation expiry 与 completion 同 GameTime：accepted sequence 较早的已入队事务先执行；结果以 Revision 为事实顺序。
- crash 后 held 但 action terminal：恢复器依据事件尾唯一 release/consume；证据不足进入 recovery_pending。

## 8. 错误与降级

未排序请求、未知 rank、owner 不一致、重复 key 数量冲突或版本过期返回 `TIME_RESERVATION_INVALID`。检测到 held 资源重复时触发 fatal pause；不得通过任意删除一条记录继续。

## 9. 安全与性能

单行动 Lock Set 上限 64，resource ID 限长。Owner validation 必须是事务内有界查询，不调用网络。冲突日志只记录 key hash、owner 和 reason，不输出容器内容或私人数据。

## 10. 验收标准

- 任意 Lock Set 排列输入都归一为同一稳定顺序。
- 1000 组交叉资源并发 fixture 无 deadlock、无部分持有。
- Door、actor 排他、item、currency/budget 四类冲突保持守恒。
- expiry、pause、shutdown 和 crash recovery 结果确定。
- command 重放最多产生一组 held/consume/release 事实。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-019` | `RULE-TIME-037..039` state machine 与 lock order |
| `TEST-TIME-020` | `RULE-TIME-040..041` conflict/expiry/pause |
| `TEST-TIME-021` | `RULE-TIME-042` consume atomicity 与 recovery |

## 12. 关联文档

- `DOC-FOUNDATION-005`：全局互斥状态与原子提交
- `DOC-MAP-008`：Door/Entrance capacity consumer
- `DOC-TIME-006`：长任务 Reservation 使用
- `DOC-ECON-005..006`：Inventory/Transaction Resource Owner
- `DOC-RELEASE-006`：恢复时 Reservation 审计

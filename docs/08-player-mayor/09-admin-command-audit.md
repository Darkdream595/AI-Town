---
doc_id: DOC-PLAYER-009
title: Sandbox Admin 确认、存档标记与不可抵赖审计
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - sandbox-admin-command
  - admin-confirmation
  - admin-save-taint
  - admin-audit-event
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-PLAYER-001
  - DOC-PLAYER-003
requirements:
  - REQ-PLAYER-009
last_updated: 2026-07-26
---

# Sandbox Admin 确认、存档标记与不可抵赖审计

## 1. 目的

`REQ-PLAYER-009`：为可选 Sandbox Admin 定义独立授权、二次确认、白名单 mutation、永久存档 taint/mark 与不可抵赖审计，使自由体验能力不能伪装成普通玩家或镇长行为。

## 2. 非目标

本文不提供任意 SQL、脚本、文件系统、模型工具调用、事件删除、审计删除或通用“set any field”。Admin 只执行注册、版本化、可验证的有限命令。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Admin Session | 用户显式启用、短期有效、与 Mayor/Resident role 独立的本地能力 |
| Confirmation Challenge | 服务端生成的一次性摘要/hash/nonce，要求用户第二次明确操作 |
| AdminCommand | `admin.*` tagged union，与 PlayerCommand/MayorCommand 不相容 |
| SaveIntegrityMark | 世界已使用 Sandbox Admin 的永久、单调标记 |
| AdminAuditEvent | 独立 append-only 安全事件，记录 attempt/denial/commit 和完整因果摘要 |

## 4. 规则与不变量

- `RULE-PLAYER-041`：Admin Session 必须由 world owner 显式启用，默认 disabled；Mayor office、Player binding、自然语言或 Client mode 不能创建 Admin authority。
- `RULE-PLAYER-042`：每个可能改变世界的 AdminCommand 都必须经过服务端生成的、一次性、短期、payload-bound 二次确认；Client 自报 `confirmed=true` 无效。
- `RULE-PLAYER-043`：首次成功 Admin mutation 必须在同一 commit 原子设置 `save_integrity.admin_modified=true`，以后不得通过 UI、回档、分支或 Admin command 清除。
- `RULE-PLAYER-044`：成功 mutation 必须同时写 owner state、DomainEvent、idempotency result、SaveIntegrityMark 和独立 AdminAuditEvent；audit sink 不可用时 mutation fail closed。
- `RULE-PLAYER-045`：AdminAuditEvent append-only、hash chained、序号单调，普通 Domain rollback/compensation/世界分支不能删除或改写；attempt/denial/expired confirmation 也产生审计事件。
- `RULE-PLAYER-046`：Admin 仍不能改写历史 event、审计、ID/Revision、API Key、文件路径或注册 Catalog；恢复使用新补偿 mutation。

## 5. 数据与接口

### 5.1 确认挑战 Schema

```json
{
  "schema_version": 1,
  "challenge_id": "01K1CHXG000000000000000001",
  "admin_session_id": "01K1ADMN000000000000000001",
  "command_type": "admin.resource.grant",
  "payload_hash": "sha256:4dd6fb3f85d3fe4b4d6a76ba5b1188a748326e8d21c7e4335c55c2dd0325a23a",
  "human_summary": "向玩家居民授予 100 铜羽；此世界将永久标记为已使用 Sandbox Admin。",
  "nonce": "bW9ja19ub25jZV8xMjM0NTY3OA",
  "issued_at_utc": "2026-07-26T09:20:00.000Z",
  "expires_in_ms": 60000,
  "used": false
}
```

时间语义遵循 `RULE-FOUNDATION-035/044`：`issued_at_utc` 是 UTC RFC 3339 持久化墙钟；`expires_in_ms` 是 `RealDurationMs`，服务端自签发时刻起以 monotonic RealTime 计时判定过期，该 deadline 不以墙钟持久化，系统时钟回拨不改变判定结果。

### 5.2 确认后的命令 Schema

```json
{
  "protocol_version": 1,
  "command_id": "01K1CMDX000000000000000009",
  "world_id": "01K1WRDX000000000000000001",
  "expected_revision": 401,
  "type": "admin.resource.grant",
  "payload": {
    "target_resident_id": "01K1RSDT000000000000000001",
    "resource_kind": "currency",
    "definition_id": "currency.copper_feather",
    "quantity": 100,
    "reason_code": "sandbox.player_requested"
  },
  "confirmation": {
    "challenge_id": "01K1CHXG000000000000000001",
    "nonce": "bW9ja19ub25jZV8xMjM0NTY3OA"
  }
}
```

允许 union 首版仅：`admin.resource.grant`、`admin.resident.relocate_safe`、`admin.health.recover`、`admin.event.schedule_registered`、`admin.weather.set_registered`。每型有数量上限、target owner 和 strict Schema。

### 5.3 AdminAuditEvent Schema

```json
{
  "schema_version": 1,
  "audit_sequence": 17,
  "audit_event_id": "01K1ADTE000000000000000001",
  "world_id": "01K1WRDX000000000000000001",
  "admin_session_id": "01K1ADMN000000000000000001",
  "actor_player_identity_id": "01K1DENT000000000000000001",
  "command_id": "01K1CMDX000000000000000009",
  "command_type": "admin.resource.grant",
  "payload_hash": "sha256:4dd6fb3f85d3fe4b4d6a76ba5b1188a748326e8d21c7e4335c55c2dd0325a23a",
  "confirmation_challenge_id": "01K1CHXG000000000000000001",
  "result": "committed",
  "reason_code": "sandbox.player_requested",
  "committed_revision": 402,
  "previous_audit_hash": "sha256:ed9a35abf11742d560997379e1217c7d6a92b535b2889e05004cdd1134368540",
  "audit_hash": "sha256:6d06e208f7ab5575424950ee7cebf0e7c2a83cec367e32e60104d7b69ea8720f",
  "recorded_at_utc": "2026-07-26T09:20:35.000Z"
}
```

`result` 仅 `attempted/denied/expired/committed/failed`。`recorded_at_utc` 为 UTC RFC 3339 持久化墙钟（`RULE-FOUNDATION-044`），禁止以 epoch 毫秒或 monotonic RealTime 持久化。Audit payload 存 hash 和受限摘要，不复制 secret、对话、API Key。

## 6. 正常流程

1. World owner 在设置中显式启用 Admin Session，并看到永久标记警告。
2. Client 选择白名单 operation 和参数；后端先做 schema、session、target 和上限预检。
3. 后端写 `attempted` audit，生成绑定 canonical payload hash 的 challenge。
4. 用户在结构化摘要页再次点击确认；确认必须在同一 Admin modal，不接受自然语言替代。
5. Backend 验证 session、nonce、expiry、unused、payload hash、expected Revision 和 owner constraints。
6. World Writer 原子提交 mutation、owner DomainEvent、idempotency result、`admin_modified` mark 和 `committed` audit；challenge 标 used。
7. UI 常驻显示“Sandbox Admin 已使用”，导出/存档/诊断 metadata 同步标记。

## 7. 边界情况

- command ID 和 challenge 都 exactly-once；challenge 重用、payload 改动、过期或跨 session 返回稳定拒绝并审计。
- commit 前崩溃无 mutation，attempt 保留；commit 后 Client 丢失回执返回原 result。

## 8. 错误与降级

审计 hash chain 断裂、audit sink 只读失败、SaveIntegrityMark 不一致或 orphan mutation evidence 触发 Recovery Barrier，禁止继续 Admin/普通世界写入直到修复。

## 9. 安全与性能

### 9.1 存档与不可抵赖语义

`admin_modified` 是每 world lineage 的单调 OR：Snapshot、手动槽位、自动存档、导出、导入和从旧槽创建的新分支都继承 true。普通玩家不能清除；删除整个世界可删除数据，但导出的审计包必须明确该世界已被删除而非“未修改”。Audit chain 使用本地安装密钥的 HMAC 或签名封装防意外篡改；它提供本地完整性证据，不声称抵抗拥有机器管理员权限的攻击者。

## 10. 验收标准

- 未启用 session、仅有 Mayor role、自然语言或伪造 `confirmed=true` 均不能执行 Admin mutation。
- challenge 对 payload/session/expiry/nonce 一一绑定且只能使用一次。
- 成功 mutation 与 DomainEvent、audit、idempotency、永久 mark 全成或全败。
- 回档、分支、导入导出后 `admin_modified=true` 不回退。
- audit chain 可验证，任何缺口/篡改使系统 fail closed。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-033` | Admin session、白名单和 Mayor/Resident 隔离 |
| `TEST-PLAYER-034` | challenge tamper/replay/expiry/cross-session |
| `TEST-PLAYER-035` | mutation/event/audit/mark 原子故障注入 |
| `TEST-PLAYER-036` | lineage taint、hash chain、篡改 Recovery Barrier |

## 12. 关联文档

- `DOC-FOUNDATION-005`：Revision、DomainEvent、幂等与恢复不变量
- `DOC-FOUNDATION-006`：RealTime/墙钟分离与 RFC 3339 timestamp 标准
- `DOC-PLAYER-006`：普通玩家 DomainEvent 因果
- `DOC-PLAYER-008`：Mayor 不是 Admin
- `DOC-RELEASE-002`：存档 lineage 与 SaveIntegrityMark 持久化

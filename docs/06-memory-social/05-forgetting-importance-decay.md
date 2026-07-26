---
doc_id: DOC-MEMORY-005
title: 重要度、衰减、遗忘与再激活
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-importance
  - memory-decay
  - memory-reactivation
  - memory-tombstone
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-003
  - DOC-MEMORY-004
requirements:
  - REQ-MEMORY-005
last_updated: 2026-07-26
---

# 重要度、衰减、遗忘与再激活

## 1. 目的

`REQ-MEMORY-005`：定义持久 importance、检索 strength 的 GameTime 衰减、冷移阈值、受保护记忆、再激活和 tombstone 行为，使遗忘是可解释的可访问性变化，而不是静默改写或删除历史。

## 2. 非目标

本文不推进 GameTime、不让模型决定“忘掉谁”、不改变客观事实/关系/Commitment 状态，也不物理删除 DomainEvent。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Importance | 创建/明确事件更新后的 `0..1000` 持久值 |
| Retention Class | `routine/normal/significant/core/pinned` |
| Retrieval Strength | 由 importance 与整日 decay factor 计算的派生值 |
| Cold Threshold | strength<250 且非 protected 时可进入 cold |
| Reactivation | 当前合法刺激与 cold metadata 匹配后恢复为 `reactivated` |
| Tombstone | payload 已清除、ID/来源 hash/删除审计永久保留的终止状态 |

## 4. 数据与接口

`DES-MEMORY-005`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/retention-state/v1",
  "type": "object",
  "required": [
    "schema_version",
    "memory_id",
    "retention_class",
    "base_importance_q1000",
    "last_strength_anchor_game_time",
    "state",
    "legal_hold",
    "tombstone"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "memory_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "retention_class": {"enum": ["routine", "normal", "significant", "core", "pinned"]},
    "base_importance_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
    "last_strength_anchor_game_time": {"type": "integer", "minimum": 0},
    "state": {"enum": ["active", "cold", "reactivated", "tombstoned"]},
    "legal_hold": {"type": "boolean"},
    "tombstone": {
      "type": ["object", "null"],
      "required": ["reason", "source_event_id", "payload_hash", "tombstoned_at_revision"],
      "properties": {
        "reason": {"enum": ["invalid_source", "duplicate_record", "authorized_admin_correction", "migration_redaction"]},
        "source_event_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "payload_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "tombstoned_at_revision": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

v1 整日 retention factor：

| `elapsed_game_days` | routine | normal | significant | core | pinned |
|---:|---:|---:|---:|---:|---:|
| 0 | 1000 | 1000 | 1000 | 1000 | 1000 |
| 1–3 | 750 | 900 | 970 | 1000 | 1000 |
| 4–7 | 500 | 750 | 920 | 1000 | 1000 |
| 8–30 | 250 | 500 | 820 | 980 | 1000 |
| 31–90 | 100 | 250 | 700 | 950 | 1000 |
| 91+ | 50 | 100 | 600 | 900 | 1000 |

```text
strength_q1000 =
floor(base_importance_q1000 * retention_factor_q1000 / 1000)
```

Reactivation trigger score 使用 `DOC-MEMORY-003` 的 semantic/participant/emotion 三分量重新按 `500/300/200` 合成；≥700 才可 reactivation。Port：

```text
evaluate_retention(memory_id, current_game_time) -> RetentionDecision
reactivate_cold_memory(memory_id, trigger, acl_decision_id) -> ReactivationResult
request_memory_tombstone(command, expected_record_version) -> TombstoneResult
audit_retention_state(owner_id, revision) -> RetentionAudit
```

## 5. 规则与不变量

- `RULE-MEMORY-034`：所有衰减只使用 GameTime 整日差；Pause、关闭和现实离线时间不产生 decay。
- `RULE-MEMORY-035`：trauma、救命之恩、重大背叛、accepted/未解决 Commitment 自动分类至少 core；pinned/core 不自动 cold/tombstone。
- `RULE-MEMORY-036`：importance 变化必须由已提交事件与 reason rule 触发；单事件绝对 delta≤100，最终 clamp `0..1000`。
- `RULE-MEMORY-037`：strength 是派生值，不写回 base importance；重复 retention evaluation 无状态变化。
- `RULE-MEMORY-038`：cold 仅从默认索引移除；payload/provenance/access policy 保留。
- `RULE-MEMORY-039`：reactivation 先 ACL allow，再 materialize/打分；deny 不能通过“唤起提示”泄露记录存在或内容。
- `RULE-MEMORY-040`：tombstone 不可恢复为 active；更正须创建新 memory，引用 tombstone ID 与新来源。
- `RULE-MEMORY-041`：玩家、Mayor、模型和普通对话均无权任意 tombstone 他人记忆；只有 retention owner 的规则或已授权 Sandbox Admin correction 可请求。

## 6. 正常流程

1. 周期 caller 提供当前 GameTime；MEMORY 分片扫描 due retention metadata。
2. 计算 elapsed days、factor 和 strength；protected/legal hold 跳过。
3. strength<250 的 active 记录进入 cold，并提交 `MemoryMovedToCold`。
4. 新刺激先通过 ACL，在 cold metadata 中按 trigger score 找候选。
5. score≥700 时原子改为 reactivated、记录触发 memory/event ID 和 GameTime。
6. 后续 consolidation 可在稳定期将 reactivated 归 active；tombstone 仅走独立命令。

状态机：

```text
active -> cold
cold -> reactivated
reactivated -> active/cold
active/cold/reactivated -> tombstoned
tombstoned -> terminal
```

## 7. 边界情况

- GameTime 倒退或 trigger 来自未来 Revision：拒绝，不重置 anchor。
- 一次触发匹配多个 cold 记录：按 trigger score desc/importance desc/memory ID asc，最多 reactivation 4 条。
- Commitment fulfilled 后仍按 significant/core 保留社会历史，不因终态立即 cold。
- source Event 后来被补偿：生成更正记忆，不以事实撤销为由 tombstone 原主观经历。
- tombstone 前 payload 已在 cold blob：事务写 tombstone 后，异步安全清除 blob；恢复必须验证 payload 不再可 materialize。

## 8. 错误、降级与恢复

错误码为 `MEMORY_RETENTION_TIME_INVALID`、`MEMORY_REACTIVATION_FORBIDDEN`、`MEMORY_TOMBSTONE_FORBIDDEN`、`MEMORY_TOMBSTONE_PAYLOAD_PRESENT`。恢复发现 state=tombstoned 但 payload 可读时保持 Recovery Barrier 并执行受审计 redaction job。

### 8.1 Version 与 Migration

factor table 与 classification manifest 使用 `memory-retention/v1` hash。新表只作用于新 evaluation，旧事件不重算。旧“deleted”记录迁移为 tombstone 时必须有 source bytes hash、迁移事件和 reason；无法证明原 payload 已清除则迁移失败。

## 9. 安全与性能

retention scan 只读 metadata，按 `(owner,next_evaluation_game_time,memory_id)` 分页，每 batch≤256。reactivation deny 不写 payload hash到普通日志。Tombstone payload 清除是高优先级持久化 job，完成前记录不可被任何读 Port 返回。

## 10. 验收标准

- factor table 所有端点与整数舍入符合 oracle。
- Pause/offline 1 分钟、1 小时、30 天均产生 0 decay。
- core/pinned/Commitment/法定保留不会自动 cold 或 tombstone。
- ACL-denied trigger 不 materialize、不 reactivation、不泄露内容。
- tombstone save/reload/reindex 后 payload 永不可读取且 audit lineage 保留。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-017` | retention table、importance delta 与 protected classes |
| `TEST-MEMORY-018` | GameTime-only decay 与 offline zero delta |
| `TEST-MEMORY-019` | reactivation trigger、ACL 与 stable limits |
| `TEST-MEMORY-020` | tombstone/redaction/reload 与 migration failure |

## 12. 关联文档

- `DOC-MEMORY-003`：trigger 分量和检索输出
- `DOC-MEMORY-004`：cold storage 与 consolidation
- `DOC-MEMORY-009`：reactivation ACL
- `DOC-MEMORY-011`：玩家、Mayor 与删除权限

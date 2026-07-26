---
doc_id: DOC-MEMORY-002
title: 记忆写入资格、幂等与生命周期
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-write-eligibility
  - memory-write-idempotency
  - memory-write-state-machine
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
requirements:
  - REQ-MEMORY-002
last_updated: 2026-07-26
---

# 记忆写入资格、幂等与生命周期

## 1. 目的

`REQ-MEMORY-002`：规定哪些已提交事实、直接观察、证词、推导、承诺和训练结果有资格生成认知记录，并用确定性 write key、状态机和事务事件保证重试、重连、重放不会重复写入。

## 2. 非目标

本文不决定对话内容是否安全、不拥有 DomainEvent、不把模型输出本身视为经历，也不定义遗忘、检索评分或关系 delta。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `MemoryWriteCandidateV1` | Orchestrator 基于已提交来源构造的非权威候选 |
| Direct Observation | owner 在事件发生时位于合法感知范围且通过可见/可听规则的证据 |
| Testimony | 一名 actor 向另一名 actor 传播 claim 的已提交 Speech Act/BeliefTransfer |
| Write Key | 对世界、owner、来源、kind、rule version 的 canonical tuple 计算 SHA-256 |
| Eligibility | `eligible/rejected/deferred`；只有 eligible 可进入 commit |
| Write Lifecycle | `proposed → eligible → committed`，或进入 `rejected/deferred` |

## 4. 数据与接口

`DES-MEMORY-002`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/write-candidate/v1",
  "type": "object",
  "required": [
    "schema_version",
    "candidate_id",
    "world_id",
    "memory_owner_id",
    "memory_kind",
    "source_kind",
    "source_event_ids",
    "source_memory_ids",
    "observed_revision",
    "observed_game_time",
    "observation_evidence",
    "write_rule_version"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "candidate_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "memory_owner_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "memory_kind": {
      "enum": [
        "episodic_memory",
        "semantic_belief",
        "social_impression",
        "commitment",
        "routine_knowledge"
      ]
    },
    "source_kind": {
      "enum": [
        "domain_event",
        "direct_observation",
        "testimony",
        "inference",
        "self_commitment",
        "routine_training"
      ]
    },
    "source_event_ids": {
      "type": "array",
      "maxItems": 16,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
    },
    "source_memory_ids": {
      "type": "array",
      "maxItems": 32,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
    },
    "observed_revision": {"type": "integer", "minimum": 0},
    "observed_game_time": {"type": "integer", "minimum": 0},
    "observation_evidence": {
      "type": ["object", "null"],
      "required": ["observer_id", "scene_id", "sense_modes", "evidence_hash"],
      "properties": {
        "observer_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "scene_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "sense_modes": {
          "type": "array",
          "minItems": 1,
          "maxItems": 3,
          "uniqueItems": true,
          "items": {"enum": ["sight", "hearing", "direct_participation"]}
        },
        "evidence_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
      },
      "additionalProperties": false
    },
    "write_rule_version": {"const": "memory-write/v1"}
  },
  "anyOf": [
    {"required": ["source_event_ids"], "properties": {"source_event_ids": {"minItems": 1}}},
    {"required": ["source_memory_ids"], "properties": {"source_memory_ids": {"minItems": 1}}}
  ],
  "additionalProperties": false
}
```

Write key 的 canonical input 固定为：

```text
world_id
"\n"+memory_owner_id
+"\n"+memory_kind
+"\n"+source_kind
+"\n"+join(sort(source_event_ids),",")
+"\n"+join(sort(source_memory_ids),",")
+"\n"+write_rule_version
```

以 UTF-8 编码后计算 lowercase SHA-256。Port：

```text
evaluate_write_eligibility(candidate, owner_projection) -> EligibilityResult
commit_eligible_memory(command_id, write_key, memory_record) -> MemoryWriteResult
mark_memory_write_deferred(write_key, reason_code, retry_revision) -> DeferredResult
replay_memory_write(world_id, write_key) -> OriginalMemoryWriteResult | none
```

## 5. 规则与不变量

- `RULE-MEMORY-009`：只有已提交 DomainEvent、已提交 direct observation/Speech Act、有效来源记忆、self commitment 或成功 routine training 可成为来源。
- `RULE-MEMORY-010`：`ActionProposal`、模型自然语言、Client 动画、未提交 PlayerCommand、未通过校验的对话文本和原始 `reasoning_content` 永不具备写入资格。
- `RULE-MEMORY-011`：direct observation 必须有事件同 Revision 的感知证据；“在同一区域”不足以证明看见或听见。
- `RULE-MEMORY-012`：每个 `(world_id, write_key)` 最多提交一个结果；相同 key 重放返回原 memory ID 和 event ID。
- `RULE-MEMORY-013`：同一 key 使用不同 canonical candidate hash 时返回 idempotency conflict，不覆盖原记录。
- `RULE-MEMORY-014`：Memory 状态、`MemoryRecorded`、write-key result 与 owner index 在同一事务提交；失败 Revision 不增长。
- `RULE-MEMORY-015`：inference 只能从 owner 可访问的现有记忆派生，必须登记 transform rule，且默认 confidence 不高于全部来源最小值。
- `RULE-MEMORY-016`：写入时即绑定 `AccessPolicy`；无法唯一计算策略时 deferred/rejected，禁止先 public 写入后补权限。

## 6. 正常流程

1. 已提交事件进入 MEMORY subscriber；subscriber 以 `(event_id, observer_id, rule_version)` 形成候选。
2. 校验来源存在、观察证据、owner lifecycle、同 world 和访问策略。
3. 计算 canonical candidate hash 与 write key，查询幂等结果。
4. eligible 候选生成 strict `MemoryRecordV1`，与 `MemoryRecorded` 原子提交。
5. deferred 候选保存无 payload 的原因和重试 Revision；来源补齐后以同 key 重试。

状态机：

```text
proposed -> eligible -> committed
proposed -> rejected
proposed -> deferred -> eligible
deferred -> rejected
committed -> active/cold/reactivated/tombstoned
```

## 7. 边界情况

- 同一公开事件有十名观察者：产生十个不同 owner write key，不共享主观 payload。
- 观察者在事件后进入场景：无 direct observation，可通过后续 testimony 获得 belief。
- Speech Act 事务成功但模型回复未渲染：已提交 speech 仍可写记忆；渲染失败不撤销。
- Commitment 双方对条款理解不同：各自可持有不同主观记录，但共享同一 commitment runtime ID。
- subscriber crash 于状态写后、事件写前：事务回滚；重放以同 write key 只提交一次。

## 8. 错误、降级与恢复

错误码为 `MEMORY_SOURCE_NOT_COMMITTED`、`MEMORY_OBSERVATION_UNPROVEN`、`MEMORY_WRITE_CONFLICT`、`MEMORY_ACCESS_POLICY_UNRESOLVED`、`MEMORY_OWNER_UNAVAILABLE`。订阅器积压可以延迟写入，但不得丢弃 Must 事件；恢复按 Event Log Revision 与 write-key store 重放。

### 8.1 Version 与 Migration

`memory-write/v1` 的 canonical tuple 永不改变。新规则发布新 version；不得用新算法重算旧 write key。迁移只补建缺失索引，必须从原记录和事件证据重算 hash；任何不一致保持 Recovery Barrier。

## 9. 安全与性能

eligibility 阶段只处理 owner 所需字段，禁止把完整 Event payload复制到 deferred queue。每事件观察者上限由合法感知集合决定；批量写按 resident ID 稳定排序。write-key 查询有唯一索引，目标均摊 O(1)。

## 10. 验收标准

- 已提交直接经历、证词、推导、承诺、训练各有正例。
- Proposal、动画、迟到观察者、无 ACL 候选全部无记录副作用。
- 相同 command/write key 重放返回相同 ID；不同 payload 冲突稳定失败。
- 四个事务 fault point 均无半记录、无半事件、Revision 不增长。
- subscriber 从 Snapshot/Event tail 恢复后记录集合与无 crash 对照一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-005` | source eligibility 正反例 |
| `TEST-MEMORY-006` | write-key 固定向量与幂等冲突 |
| `TEST-MEMORY-007` | 观察证据与 owner/access policy |
| `TEST-MEMORY-008` | 事务 fault injection 与 Event tail replay |

## 12. 关联文档

- `DOC-MEMORY-001`：MemoryRecord 与 provenance
- `DOC-MEMORY-008`：testimony 与 BeliefTransfer
- `DOC-MEMORY-009`：写入时 AccessPolicy
- `DOC-FOUNDATION-005`：原子事件与客观/主观分离

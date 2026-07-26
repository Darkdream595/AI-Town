---
doc_id: DOC-MEMORY-001
title: 记忆、信念与社会认知数据模型
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-record-schema
  - memory-provenance
  - cognitive-record-kinds
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-001
  - DOC-RESIDENT-001
requirements:
  - REQ-MEMORY-001
last_updated: 2026-07-26
---

# 记忆、信念与社会认知数据模型

## 1. 目的

`REQ-MEMORY-001`：定义 MEMORY-owned `MemoryRecordV1` 以及 `EpisodicMemory`、`SemanticBelief`、`SocialImpression`、`Commitment`、`RoutineKnowledge` 五种封闭认知类型，保证所有内容均有来源、主体、可见性、版本和可恢复生命周期。

## 2. 非目标

本文不拥有世界客观事实、Resident 身份字段、Prompt construction、ActionProposal、对话状态或 GameTime 推进。Memory 中的文本、信念和印象均不是已提交世界事实，也不能直接修改其他 Domain。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `memory_owner_id` | 持有该主观认知的 Resident runtime ID |
| `subject_refs` | 认知所指向的稳定/runtime entity 引用，不复制实体可变状态 |
| Provenance | 来源事件、观察者、传播链、推导规则与创建 Revision 的可审计证据 |
| `source_kind` | `domain_event/direct_observation/testimony/inference/self_commitment/routine_training` |
| `MemoryState` | `active/cold/reactivated/tombstoned`，其中 tombstoned 永不参与检索 |
| `AccessPolicy` | `DOC-MEMORY-009` 定义的后端可见性策略引用 |
| Payload | 五种认知类型之一的 strict discriminated union |

## 4. 数据与接口

`DES-MEMORY-001`：注册 `schema://ai-town/memory/record/v1`。以下为完整 strict JSON Schema；`payload` 在 tombstoned 时必须为 `null`，其他状态必须匹配且只匹配一种 `$defs`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/record/v1",
  "type": "object",
  "required": [
    "schema_version",
    "memory_id",
    "world_id",
    "memory_owner_id",
    "memory_kind",
    "state",
    "created_at_revision",
    "created_at_game_time",
    "last_reactivated_game_time",
    "importance_q1000",
    "confidence_q1000",
    "subject_refs",
    "semantic_tags",
    "provenance",
    "access_policy_id",
    "payload",
    "record_version"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "memory_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
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
    "state": {"enum": ["active", "cold", "reactivated", "tombstoned"]},
    "created_at_revision": {"type": "integer", "minimum": 0},
    "created_at_game_time": {"type": "integer", "minimum": 0},
    "last_reactivated_game_time": {"type": ["integer", "null"], "minimum": 0},
    "importance_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
    "confidence_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
    "subject_refs": {
      "type": "array",
      "maxItems": 32,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 128}
    },
    "semantic_tags": {
      "type": "array",
      "maxItems": 32,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
    },
    "provenance": {"$ref": "#/$defs/provenance"},
    "access_policy_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "payload": {
      "oneOf": [
        {"$ref": "#/$defs/episodic"},
        {"$ref": "#/$defs/belief"},
        {"$ref": "#/$defs/impression"},
        {"$ref": "#/$defs/commitment"},
        {"$ref": "#/$defs/routine"},
        {"type": "null"}
      ]
    },
    "record_version": {"type": "integer", "minimum": 1}
  },
  "allOf": [
    {
      "if": {"properties": {"state": {"const": "tombstoned"}}},
      "then": {"properties": {"payload": {"type": "null"}}},
      "else": {"properties": {"payload": {"not": {"type": "null"}}}}
    },
    {
      "if": {"properties": {"memory_kind": {"const": "episodic_memory"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/episodic"}}}
    },
    {
      "if": {"properties": {"memory_kind": {"const": "semantic_belief"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/belief"}}}
    },
    {
      "if": {"properties": {"memory_kind": {"const": "social_impression"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/impression"}}}
    },
    {
      "if": {"properties": {"memory_kind": {"const": "commitment"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/commitment"}}}
    },
    {
      "if": {"properties": {"memory_kind": {"const": "routine_knowledge"}}},
      "then": {"properties": {"payload": {"$ref": "#/$defs/routine"}}}
    }
  ],
  "$defs": {
    "provenance": {
      "type": "object",
      "required": [
        "source_kind",
        "source_event_ids",
        "origin_actor_id",
        "direct_observer_id",
        "derived_from_memory_ids",
        "transform_rule_ids",
        "source_revision"
      ],
      "properties": {
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
        "origin_actor_id": {
          "type": ["string", "null"],
          "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"
        },
        "direct_observer_id": {
          "type": ["string", "null"],
          "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"
        },
        "derived_from_memory_ids": {
          "type": "array",
          "maxItems": 64,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        },
        "transform_rule_ids": {
          "type": "array",
          "maxItems": 16,
          "items": {"type": "string", "pattern": "^RULE-MEMORY-[0-9]{3}$"}
        },
        "source_revision": {"type": "integer", "minimum": 0}
      },
      "anyOf": [
        {
          "properties": {
            "source_event_ids": {"minItems": 1}
          }
        },
        {
          "properties": {
            "derived_from_memory_ids": {"minItems": 1}
          }
        }
      ],
      "additionalProperties": false
    },
    "episodic": {
      "type": "object",
      "required": [
        "kind",
        "representation",
        "summary_text",
        "participant_ids",
        "location_ids",
        "emotion_id",
        "emotion_intensity_q1000",
        "source_memory_ids"
      ],
      "properties": {
        "kind": {"const": "episodic_memory"},
        "representation": {"enum": ["direct_episode", "consolidated_summary"]},
        "summary_text": {"type": "string", "minLength": 1, "maxLength": 1024},
        "participant_ids": {
          "type": "array",
          "maxItems": 16,
          "uniqueItems": true,
          "items": {"type": "string", "minLength": 1, "maxLength": 128}
        },
        "location_ids": {
          "type": "array",
          "maxItems": 8,
          "uniqueItems": true,
          "items": {"type": "string", "minLength": 1, "maxLength": 128}
        },
        "emotion_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "emotion_intensity_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
        "source_memory_ids": {
          "type": "array",
          "maxItems": 64,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        }
      },
      "additionalProperties": false
    },
    "belief": {
      "type": "object",
      "required": ["kind", "claim", "evidence_memory_ids", "contradiction_memory_ids"],
      "properties": {
        "kind": {"const": "semantic_belief"},
        "claim": {
          "type": "object",
          "required": ["predicate_id", "subject_ref", "object_value"],
          "properties": {
            "predicate_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
            "subject_ref": {"type": "string", "minLength": 1, "maxLength": 128},
            "object_value": {
              "type": ["string", "number", "integer", "boolean", "null"]
            }
          },
          "additionalProperties": false
        },
        "evidence_memory_ids": {
          "type": "array",
          "maxItems": 32,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        },
        "contradiction_memory_ids": {
          "type": "array",
          "maxItems": 32,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        }
      },
      "additionalProperties": false
    },
    "impression": {
      "type": "object",
      "required": ["kind", "target_resident_id", "trait_id", "valence_q1000", "evidence_memory_ids"],
      "properties": {
        "kind": {"const": "social_impression"},
        "target_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "trait_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
        "valence_q1000": {"type": "integer", "minimum": -1000, "maximum": 1000},
        "evidence_memory_ids": {
          "type": "array",
          "maxItems": 32,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        }
      },
      "additionalProperties": false
    },
    "commitment": {
      "type": "object",
      "required": [
        "kind",
        "commitment_id",
        "promisor_id",
        "beneficiary_ids",
        "terms_id",
        "deadline_game_time",
        "status"
      ],
      "properties": {
        "kind": {"const": "commitment"},
        "commitment_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "promisor_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
        "beneficiary_ids": {
          "type": "array",
          "minItems": 1,
          "maxItems": 16,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
        },
        "terms_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
        "deadline_game_time": {"type": ["integer", "null"], "minimum": 0},
        "status": {"enum": ["proposed", "accepted", "fulfilled", "breached", "released", "expired"]}
      },
      "additionalProperties": false
    },
    "routine": {
      "type": "object",
      "required": ["kind", "procedure_id", "step_action_ids", "proficiency_q1000", "last_success_event_id"],
      "properties": {
        "kind": {"const": "routine_knowledge"},
        "procedure_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
        "step_action_ids": {
          "type": "array",
          "minItems": 1,
          "maxItems": 32,
          "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
        },
        "proficiency_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
        "last_success_event_id": {
          "type": ["string", "null"],
          "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

写/读 Port：

```text
propose_memory_write(MemoryWriteCandidateV1) -> MemoryEligibilityResult
commit_memory_record(EligibleMemoryWriteV1) -> MemoryWriteResult
get_memory_metadata(memory_id, expected_revision) -> MemoryMetadataProjection
materialize_authorized_memory(memory_id, access_decision_id) -> MemoryRecordV1
```

## 5. 规则与不变量

- `RULE-MEMORY-001`：`memory_kind` 与 payload discriminator 必须一致；五种之外的类型一律拒绝。
- `RULE-MEMORY-002`：`memory_id/world_id/memory_owner_id` 创建后不可变；record version 只随成功变更递增。
- `RULE-MEMORY-003`：所有非 tombstone 记录必须有至少一个来源事件、来源记忆或明确的 self/routine source；不得出现无 provenance 认知。
- `RULE-MEMORY-004`：`source_revision <= created_at_revision`，所有来源引用属于同一 world；跨世界内容只能经显式导入产生新来源事件。
- `RULE-MEMORY-005`：`SemanticBelief` 不含 `is_true/objective_truth` 字段；`confidence_q1000` 只表示持有者主观置信度。
- `RULE-MEMORY-006`：Commitment 状态是 MEMORY-owned 社会义务投影，不替代 Quest、Transaction 或法律事实；外部结果只经已提交事件更新。
- `RULE-MEMORY-007`：payload、自由文本和来源内容不得通过 metadata-only 查询泄露；materialize 前必须有 `DOC-MEMORY-009` 的允许决定。
- `RULE-MEMORY-008`：tombstoned 记录的 payload 必须为 null，provenance hash/ID 和 tombstone audit 由后续文档保留。

## 6. 正常流程

1. Orchestrator 将已提交事件、观察范围和 Resident identity 引用映射为 `MemoryWriteCandidateV1`。
2. MEMORY 按 `DOC-MEMORY-002` 判断 eligibility、幂等键和访问策略。
3. 记录在同一事务写入状态、provenance、AccessPolicy 引用与 `MemoryRecorded`。
4. 检索先读不含 payload 的 metadata，执行 ACL 后才 materialize。
5. 下游只消费版本固定的 authorized projection，不能反向写 `MemoryRecordV1`。

## 7. 边界情况

- 同一事件可给多个直接观察者生成不同 EpisodicMemory，但每份都绑定自己的 owner 和观察证据。
- 一个居民可以同时持有互相矛盾的 SemanticBelief，不能由 Repository 自动覆盖。
- Commitment 被履行后保留为终态社会历史；不得转回 accepted。
- 来源事件被业务补偿不删除记忆；产生新观察/更正记忆并降低旧 belief confidence。
- 冷存储只改变 state/索引位置，不改变 payload hash、provenance 或 record version 语义。

## 8. 错误、降级与恢复

错误码为 `MEMORY_SCHEMA_INVALID`、`MEMORY_KIND_MISMATCH`、`MEMORY_PROVENANCE_MISSING`、`MEMORY_CROSS_WORLD_REFERENCE`、`MEMORY_ACCESS_REQUIRED`。任一错误无部分写入。Repository 发现未知 Schema 时保持 Recovery Barrier；不得把未知字段丢弃后继续。

### 8.1 Version 与 Migration

v1→后续版本必须以纯 upcaster 执行：strict 校验旧值、保留 ID/provenance/access policy、显式生成新增字段、strict 校验新值并 canonical round-trip。无法推导 access level、payload kind 或 source revision 时返回 `MEMORY_MIGRATION_AMBIGUOUS`，保持源 bytes 与世界暂停。

## 9. 安全与性能

高基数文本与冷数据不得内嵌 Resident aggregate。单条 payload UTF-8 上限 4 KiB、总记录上限由 `DOC-MEMORY-004` 分层控制。日志只记录 memory ID、kind、policy ID、hash 和 reason code，不记录 Secret 内容。

## 10. 验收标准

- 五种 payload 的正例与 kind mismatch/额外字段/缺 provenance 反例通过 strict validator。
- 客观事实字段无法写入 SemanticBelief。
- metadata-only 查询不含 payload、summary_text、claim object 或 secret participant。
- tombstone round-trip 后 payload 仍为 null，ID/provenance 审计仍可追踪。
- v1 canonical JSON save/reload 后逐字段一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-001` | 五类 strict Schema、discriminator 与 additionalProperties |
| `TEST-MEMORY-002` | provenance/world/revision 不变量 |
| `TEST-MEMORY-003` | metadata/materialize 数据边界 |
| `TEST-MEMORY-004` | v1 round-trip、tombstone 与 migration safe failure |

## 12. 关联文档

- `DOC-MEMORY-002`：写入资格与幂等
- `DOC-MEMORY-009`：AccessPolicy 与 Prompt 前过滤
- `DOC-MEMORY-010`：客观事实与信念分离
- `DOC-RESIDENT-001`：Resident aggregate 引用边界

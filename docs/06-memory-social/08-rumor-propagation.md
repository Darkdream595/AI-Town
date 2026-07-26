---
doc_id: DOC-MEMORY-008
title: 谣言、来源链、失真与 BeliefTransfer
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - belief-transfer
  - rumor-source-chain
  - rumor-distortion
  - rumor-confidence
depends_on:
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-002
  - DOC-MEMORY-006
  - DOC-MEMORY-007
requirements:
  - REQ-MEMORY-008
last_updated: 2026-07-26
---

# 谣言、来源链、失真与 BeliefTransfer

## 1. 目的

`REQ-MEMORY-008`：定义居民之间传播主观 claim 的 `BeliefTransferV1`、来源链、置信度衰减、确定性失真、循环阻断、ACL 与 recipient belief 写入，使居民不会自动知道谣言真假或把传播内容升级为客观事实。

## 2. 非目标

本文不生成对话句子、不拥有 Speech Act、不验证 claim 真值、不修改 WORLD 事实，也不保证每次社会接触都会传播谣言。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Origin Belief | 传播链起点的 SemanticBelief ID 与不可变 claim hash |
| Source Chain | 从 origin holder 到当前 recipient 的有序 hop |
| Distortion Operation | `omit_qualifier/generalize_quantity/shift_time_bucket/change_certainty` |
| Transfer Confidence | 每 hop 后的主观置信度 `0..1000` |
| Chain Fingerprint | origin belief、claim hash、hop actor IDs、rule version 的 SHA-256 |
| Loop | recipient 已出现在 source chain，或 chain fingerprint 已被该 recipient 接收 |

## 4. 数据与接口

`DES-MEMORY-008`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/belief-transfer/v1",
  "type": "object",
  "required": [
    "schema_version",
    "transfer_id",
    "world_id",
    "origin_belief_id",
    "origin_claim_hash",
    "speaker_id",
    "recipient_id",
    "source_chain",
    "claim",
    "distortion_operations",
    "confidence_q1000",
    "access_policy_id",
    "source_event_id",
    "chain_fingerprint"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "transfer_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "origin_belief_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "origin_claim_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "speaker_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "recipient_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_chain": {
      "type": "array",
      "minItems": 1,
      "maxItems": 8,
      "items": {
        "type": "object",
        "required": ["hop_index", "speaker_id", "recipient_id", "source_event_id", "claim_hash_after_hop", "confidence_after_hop_q1000"],
        "properties": {
          "hop_index": {"type": "integer", "minimum": 0, "maximum": 7},
          "speaker_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
          "recipient_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
          "source_event_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
          "claim_hash_after_hop": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
          "confidence_after_hop_q1000": {"type": "integer", "minimum": 0, "maximum": 1000}
        },
        "additionalProperties": false
      }
    },
    "claim": {
      "type": "object",
      "required": ["predicate_id", "subject_ref", "object_value", "qualifier_ids", "time_bucket_id"],
      "properties": {
        "predicate_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
        "subject_ref": {"type": "string", "minLength": 1, "maxLength": 128},
        "object_value": {"type": ["string", "number", "integer", "boolean", "null"]},
        "qualifier_ids": {
          "type": "array",
          "maxItems": 8,
          "uniqueItems": true,
          "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
        },
        "time_bucket_id": {"type": ["string", "null"], "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
      },
      "additionalProperties": false
    },
    "distortion_operations": {
      "type": "array",
      "maxItems": 4,
      "items": {
        "enum": [
          "omit_qualifier",
          "generalize_quantity",
          "shift_time_bucket",
          "change_certainty"
        ]
      }
    },
    "confidence_q1000": {"type": "integer", "minimum": 0, "maximum": 1000},
    "access_policy_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_event_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "chain_fingerprint": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
  },
  "additionalProperties": false
}
```

每 hop confidence：

```text
speaker_factor = clamp((speaker_to_recipient_trust + 100) * 5, 0, 1000)
base_after_trust = floor(previous_confidence * speaker_factor / 1000)
distortion_penalty = 80 * number_of_new_distortion_operations
next_confidence = clamp(base_after_trust - distortion_penalty, 0, previous_confidence)
```

失真选择不使用模型随机：`selector = first_uint32(SHA256(origin_claim_hash + "\n" + join(actor_ids,",") + "\nrumor-distortion/v1"))`，按 Catalog 中允许操作列表取 `selector mod operation_count`；当 claim 不满足操作前置时不失真。Port：

```text
prepare_belief_transfer(speaker_id, recipient_id, belief_id, speech_event_id) -> TransferProposal
validate_transfer_acl(proposal, access_snapshot) -> TransferAccessDecision
commit_belief_transfer(proposal, recipient_write_candidate) -> TransferResult
replay_belief_transfer(transfer_id) -> OriginalTransferResult
```

## 5. 规则与不变量

- `RULE-MEMORY-059`：传播来源只能是 speaker 已持有且当前可访问的 SemanticBelief；不能传播后台客观事实、未授权 memory 或模型临时文本。
- `RULE-MEMORY-060`：source chain 每 hop 连续，前一 recipient 必须等于后一 speaker；hop index 从 0 连续递增。
- `RULE-MEMORY-061`：recipient 已在 chain、chain>8 或 fingerprint 已接收时停止传播，不写重复 belief effect。
- `RULE-MEMORY-062`：confidence 每 hop单调不增；关系 trust 只影响 confidence，不验证真值。
- `RULE-MEMORY-063`：失真必须来自允许操作、记录前后 claim hash，不能改变 subject 为不存在实体或生成越权 Secret。
- `RULE-MEMORY-064`：public/community/faction/relationship 内容只在 `DOC-MEMORY-009` 当前 ACL allow 时传播；personal 不传播；shared_secret 仅精确 participants 且 speaker 仍在 participant set 时传播。
- `RULE-MEMORY-065`：recipient 写入的是带 testimony provenance 的 SemanticBelief，绝不是 DomainEvent/Fact。
- `RULE-MEMORY-066`：Transfer、recipient belief/write-key、source chain 和 `BeliefTransferred` 原子提交。
- `RULE-MEMORY-067`：相同 speech event/origin belief/speaker/recipient/rule version 最多一个 effect。

## 6. 正常流程

1. 已提交 Speech Act 指明 speaker 传播某个已授权 belief。
2. MEMORY 验证 speaker ownership/access、recipient、chain/loop 和 policy。
3. 依据 edge trust 与 deterministic selector 计算 confidence/失真。
4. 构造 `BeliefTransferV1` 和 recipient SemanticBelief candidate。
5. 原子提交 transfer、recipient memory、事件与幂等结果。
6. recipient 后续可能质疑/验证；新观察生成新证据，不回写 origin fact。

## 7. 边界情况

- trust=-100 得到 factor 0，belief 可记录“听说过”但 confidence=0；检索可按阈值排除。
- 无 social edge 时 trust 默认 0，factor=500，不建立关系边。
- chain 达 8 时保留最终记录但标记 `propagation_terminal` 诊断，不再转发。
- shared_secret participant 被移除后，旧 holder 仍记得，但不能继续传播给非参与者。
- speaker 撒谎是其 Speech Act/intent；MEMORY 仍记录 testimony provenance，不自动识别真伪。

## 8. 错误、降级与恢复

错误码为 `MEMORY_RUMOR_SOURCE_FORBIDDEN`、`MEMORY_RUMOR_CHAIN_INVALID`、`MEMORY_RUMOR_LOOP`、`MEMORY_RUMOR_POLICY_DENIED`、`MEMORY_RUMOR_CLAIM_INVALID`。ACL/edge/index unavailable 时拒绝或 deferred，禁止以 public fallback。

### 8.1 Version 与 Migration

`rumor-distortion/v1` 固定 selector、操作顺序和 confidence 公式。旧 chain 缺 hop event/hash 不得补猜；保留旧 belief 为 legacy testimony，但禁止继续传播，直到显式 migration evidence 完整。

## 9. 安全与性能

传播每次只处理一条 belief，chain≤8、qualifier≤8。deny/loop 日志只含 transfer/fingerprint/reason，不含 claim。hash 不替代 ACL：即使只传 hash，也必须先检查 policy。

## 10. 验收标准

- 固定 trust/claim/chain oracle 得到精确 confidence、operation 和 hash。
- loop、8-hop、personal、unauthorized shared_secret 全部停止且无 recipient memory。
- recipient 只获得 SemanticBelief，客观事实 store 无变化。
- crash/replay 最多产生一个 transfer 与一个 recipient effect。
- save/reload 后 source chain、claim hash、confidence 与 fingerprint 一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-029` | chain continuity/loop/max hops |
| `TEST-MEMORY-030` | confidence/distortion fixed oracle |
| `TEST-MEMORY-031` | ACL levels 与 shared_secret propagation |
| `TEST-MEMORY-032` | recipient belief/atomicity/reload |

## 12. 关联文档

- `DOC-MEMORY-001`：SemanticBelief/provenance
- `DOC-MEMORY-006`：trust range
- `DOC-MEMORY-009`：六级 AccessPolicy
- `DOC-MEMORY-010`：belief 不等于 objective fact

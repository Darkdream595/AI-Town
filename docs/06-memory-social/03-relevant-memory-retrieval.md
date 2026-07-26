---
doc_id: DOC-MEMORY-003
title: 相关记忆检索、评分与输出预算
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - deterministic-memory-retrieval
  - memory-retrieval-score
  - authorized-context-output
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-002
requirements:
  - REQ-MEMORY-003
last_updated: 2026-07-26
---

# 相关记忆检索、评分与输出预算

## 1. 目的

`REQ-MEMORY-003`：定义固定 Revision 下从 metadata candidate、ACL 前置过滤、确定性评分、稳定排序到 `AuthorizedMemoryContextV1` 的完整检索链，使相同输入得到相同结果且未授权 Secret 在 Prompt construction 之前已被排除。

## 2. 非目标

本文不构造 Prompt、不调用模型/embedding 服务、不决定 AI 行动，也不让检索分数改写 Memory、关系或世界状态。模型不得提交自选 memory ID 绕过检索。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Retrieval Query | 固定 actor、Revision、GameTime、目标/参与者/概念标签与输出预算 |
| Metadata Candidate | 不含 payload 的索引项，可用于 ACL 与分数计算 |
| Authorized Candidate | `DOC-MEMORY-009` 返回 allow 且 policy/revision 匹配的项 |
| Semantic Match | query concept tags 与记录 semantic tags 的加权 Jaccard，非网络 embedding |
| Commitment Urgency | accepted commitment 与 deadline/参与者的有界特征 |
| Retrieval Oracle | 固定 fixture 的逐项 component、总分、排序与截断结果 |

## 4. 数据与接口

`DES-MEMORY-003`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/retrieval-query/v1",
  "type": "object",
  "required": [
    "schema_version",
    "retrieval_id",
    "world_id",
    "requesting_principal_id",
    "actor_resident_id",
    "observed_revision",
    "observed_game_time",
    "goal_tags",
    "concept_tags",
    "participant_ids",
    "emotion_id",
    "limits"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "retrieval_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "requesting_principal_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "actor_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "observed_revision": {"type": "integer", "minimum": 0},
    "observed_game_time": {"type": "integer", "minimum": 0},
    "goal_tags": {
      "type": "array",
      "maxItems": 16,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
    },
    "concept_tags": {
      "type": "array",
      "maxItems": 32,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
    },
    "participant_ids": {
      "type": "array",
      "maxItems": 16,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 128}
    },
    "emotion_id": {"type": ["string", "null"], "pattern": "^[a-z][a-z0-9_]*$"},
    "limits": {
      "type": "object",
      "required": ["candidate_limit", "record_limit", "commitment_limit", "utf8_byte_limit"],
      "properties": {
        "candidate_limit": {"type": "integer", "minimum": 1, "maximum": 128},
        "record_limit": {"type": "integer", "minimum": 1, "maximum": 16},
        "commitment_limit": {"type": "integer", "minimum": 0, "maximum": 4},
        "utf8_byte_limit": {"type": "integer", "minimum": 1024, "maximum": 12288}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

所有分量为整数 `0..1000`，总权重恰为 1000：

| 分量 | 权重 | 计算 |
|---|---:|---|
| `semantic_match_q1000` | 300 | versioned tag weight 的加权 Jaccard；空并集为 0 |
| `goal_match_q1000` | 180 | goal tags 与 semantic tags 的加权 Jaccard |
| `participant_match_q1000` | 120 | 交集数/查询 participant 数，查询为空则 0 |
| `emotion_match_q1000` | 80 | 相同 emotion=1000，兼容组=500，否则 0 |
| `importance_q1000` | 120 | 记录的持久 importance |
| `commitment_urgency_q1000` | 120 | 非 commitment=0；accepted 且相关时按 deadline table |
| `recency_q1000` | 80 | 按创建/最近 reactivation 到当前的整游戏日查表 |

```text
score_q1000 =
floor((
  semantic*300 + goal*180 + participant*120 + emotion*80 +
  importance*120 + commitment_urgency*120 + recency*80
) / 1000)
```

Recency table：0 日=1000、1=900、2–3=750、4–7=550、8–30=300、31–90=150、91+=50。Commitment urgency：逾期/24 分钟内=1000、1 日内=800、3 日内=500、更远=250、无 deadline=300；只有 status=accepted 才应用。

Port：

```text
retrieve_authorized_memories(query, acl_snapshot) -> AuthorizedMemoryContextV1
explain_retrieval(retrieval_id) -> RetrievalOracleProjection
replay_retrieval(query_hash, index_revision) -> AuthorizedMemoryContextV1
```

输出记录每项只含 `memory_id/kind/authorized_payload/score_q1000/component_scores/source_revision/access_decision_id`，并携带 `observed_revision/index_revision/query_hash/result_hash/truncated`。

## 5. 规则与不变量

- `RULE-MEMORY-017`：candidate scan 只能读取 metadata；必须先 ACL allow，再 materialize payload，再排序输出，禁止先把全量 Secret 加载到 Prompt builder 后过滤。
- `RULE-MEMORY-018`：`tombstoned` 永不候选；`cold` 默认不进入热索引，只可由 `DOC-MEMORY-005` reactivation scan 提升。
- `RULE-MEMORY-019`：所有标签由版本化 Catalog/确定性投影提供；检索 critical path 禁止网络 embedding、模型评分或系统时间。
- `RULE-MEMORY-020`：总分按上述整数公式计算，禁止浮点实现差异；同分依次按 `importance desc/created_at_game_time desc/memory_id asc`。
- `RULE-MEMORY-021`：先保留最多 `commitment_limit` 个相关 accepted Commitment，再从统一排序填满 `record_limit`；重复 memory ID 只出现一次。
- `RULE-MEMORY-022`：逐条以 canonical UTF-8 JSON 计算 byte limit；超出时停止加入，不能截断 JSON、Secret 或 Unicode grapheme。
- `RULE-MEMORY-023`：query/ACL/index 任一 Revision 不一致返回 stale，不在混合 Revision 上拼接上下文。
- `RULE-MEMORY-024`：检索无结果返回空 authorized context；不得回退为最近全量记忆或扩大权限。
- `RULE-MEMORY-025`：Prompt ownership 属于 AI；MEMORY 只生产已经授权、版本固定、预算内的 context projection。

## 6. 正常流程

1. Orchestrator 固定 actor、world Revision、GameTime 和 owner projection。
2. MEMORY 依据 participant/tag/kind index 取最多 128 条 metadata。
3. 对每条在同一 ACL snapshot 执行 `authorize`；deny 不读取 payload。
4. 对 allow 条目计算七个整数分量、总分和稳定排序。
5. 按 commitment/record/byte limit materialize 并输出 result hash。
6. AI-owned Context Builder 只能消费该 projection，不得调用 Memory Repository。

## 7. 边界情况

- byte limit 恰好等于序列化长度时允许；大 1 byte 则拒绝整条。
- 两条完全同分且同创建时间时 ULID 字典序较小者先。
- Secret 的 metadata 可暴露其存在本身时也可能敏感；索引仅返回 opaque memory ID、policy ID 和评分所需数值，不返回 subject/name。
- accepted Commitment 即使分数低于普通记忆，也只能在相关参与者且 ACL allow 时进入保留槽。
- owner 在检索过程中关系变化：access snapshot 过期，整次返回 stale 并重试，不混用结果。

## 8. 错误、降级与恢复

错误码为 `MEMORY_RETRIEVAL_STALE`、`MEMORY_INDEX_CORRUPT`、`MEMORY_ACL_SNAPSHOT_INVALID`、`MEMORY_CONTEXT_BUDGET_INVALID`。索引损坏时可从 canonical records 在 Recovery Barrier 下重建；运行中不得以全表 payload scan 降级。

### 8.1 Version 与 Migration

评分算法 ID 固定为 `memory-retrieval-score/v1`，tag weights 和 emotion compatibility 以 manifest hash 固定。新算法创建新 version；历史 replay 使用原 version。索引迁移必须比较 record count、policy count、metadata hash 与固定 oracle 后才能切换。

## 9. 安全与性能

目标为 12 名居民、每人 10,000 条记录时 p95≤25 ms（不含外部 I/O），candidate≤128、output≤16/12 KiB。ACL deny 数、分数和 hash 可记录；payload、Secret level、claim/text 不进入普通日志。

## 10. 验收标准

- 固定 oracle 的七分量、总分、tie-break、commitment 保留槽与 byte 截断逐项一致。
- 任一 ACL-denied memory 从未调用 materialize。
- 空结果、stale Revision、损坏索引均不会扩大数据范围。
- 相同 query/index/policy hash 重跑 result hash 相同。
- AI Context Builder 静态边界中不存在 Memory Repository import。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-009` | 七分量公式、recency/commitment table |
| `TEST-MEMORY-010` | stable sort、limits 与 UTF-8 byte boundary |
| `TEST-MEMORY-011` | ACL-before-materialize 与 stale snapshot |
| `TEST-MEMORY-012` | index rebuild/replay 与无网络确定性 |

## 12. 关联文档

- `DOC-MEMORY-005`：cold memory reactivation
- `DOC-MEMORY-009`：AccessPolicy 与 AccessDecision
- `DOC-MEMORY-012`：固定检索 fixture/oracle
- `DOC-FOUNDATION-003`：AI projection ownership

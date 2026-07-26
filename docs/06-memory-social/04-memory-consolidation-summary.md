---
doc_id: DOC-MEMORY-004
title: 记忆巩固、摘要与冷热分层
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-consolidation
  - memory-summary-lineage
  - memory-cold-storage
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-002
  - DOC-MEMORY-003
requirements:
  - REQ-MEMORY-004
last_updated: 2026-07-26
---

# 记忆巩固、摘要与冷热分层

## 1. 目的

`REQ-MEMORY-004`：定义重复低重要度认知的确定性聚类、可追溯摘要、冷存储迁移、原记录保留与崩溃恢复，使长期世界的数据规模有界而不伪造来源、删除高价值经历或泄露 Secret。

## 2. 非目标

本文不让模型自由改写历史，不把摘要当客观事实，不改变 Commitment 状态、关系数值或原记录 ACL，也不物理删除 Event Log。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Consolidation Batch | 对一个 owner、kind、policy scope 和时间窗的原子巩固工作 |
| Source Set | 参与摘要的原 memory ID 有序集合 |
| Consolidated Summary | `EpisodicMemory.representation=consolidated_summary` 的新记录 |
| Cold Storage | payload 保留但不在默认热检索索引中的持久层 |
| Lineage Hash | source ID、source record hash、algorithm version 的 canonical SHA-256 |
| Promotion | cold 记录经 reactivation 变为 hot/reactivated 的显式状态变化 |

## 4. 数据与接口

`DES-MEMORY-004`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/consolidation-batch/v1",
  "type": "object",
  "required": [
    "schema_version",
    "batch_id",
    "world_id",
    "memory_owner_id",
    "source_memory_ids",
    "source_record_hashes",
    "source_access_policy_id",
    "window_start_game_time",
    "window_end_game_time",
    "algorithm_version",
    "state",
    "lineage_hash"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "batch_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "memory_owner_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_memory_ids": {
      "type": "array",
      "minItems": 3,
      "maxItems": 64,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
    },
    "source_record_hashes": {
      "type": "array",
      "minItems": 3,
      "maxItems": 64,
      "items": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
    },
    "source_access_policy_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "window_start_game_time": {"type": "integer", "minimum": 0},
    "window_end_game_time": {"type": "integer", "minimum": 0},
    "algorithm_version": {"const": "memory-consolidation/v1"},
    "state": {
      "enum": ["planned", "summarizing", "committing", "completed", "failed", "recovery_required"]
    },
    "lineage_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
  },
  "additionalProperties": false
}
```

v1 可合并条件全部成立：

1. 同 `world_id/memory_owner_id/access_policy_id/memory_kind`。
2. 仅 `episodic_memory` 或非 Commitment 的 `social_impression`；v1 对后者只建冷 cluster，不生成替代 payload。
3. 每条 `importance_q1000 < 600`、state=active、无 legal hold。
4. 至少三个记录，GameTime 窗口不超过 7 日。
5. semantic tag 加权 Jaccard 两两与 cluster medoid 均 ≥700。
6. 不含伤害创伤、救命、重大背叛、accepted Commitment、shared_secret 或明确 pinned tag。

摘要文本 v1 不调用网络模型：按 source `(created_at_game_time,memory_id)` 升序，选择固定 Catalog phrase、公共 subject alias 与次数/时间范围生成，最大 1024 UTF-8 bytes。Port：

```text
plan_consolidation(owner_id, index_revision, due_game_time) -> ConsolidationPlan
execute_consolidation(batch_id, expected_record_versions) -> ConsolidationResult
recover_consolidation(batch_id, record_set, event_tail) -> ConsolidationRecovery
move_payload_to_cold(memory_ids, batch_id) -> ColdStorageResult
```

## 5. 规则与不变量

- `RULE-MEMORY-026`：source set、cluster 和摘要必须完全由固定 record/index Revision 与 `memory-consolidation/v1` 决定，不调用模型。
- `RULE-MEMORY-027`：摘要是新 EpisodicMemory，provenance 包含全部 source ID 与 lineage hash；原记录不被改写为摘要。
- `RULE-MEMORY-028`：摘要 AccessPolicy 必须与全部来源相同；不同 policy 不可合并，禁止选择“最宽”策略。
- `RULE-MEMORY-029`：Commitment、importance≥600、pinned/high-consequence、shared_secret 和 legal-hold 记录永不自动巩固/冷移。
- `RULE-MEMORY-030`：summary commit、source state→cold、索引变更、幂等结果和 `MemoriesConsolidated` 同事务提交。
- `RULE-MEMORY-031`：同一 lineage hash 最多生成一个 summary；重放返回原 summary ID。
- `RULE-MEMORY-032`：source payload 冷移后仍可经 ACL materialize；cold 不等于删除或 tombstone。
- `RULE-MEMORY-033`：summary 不能提高来源最高 confidence/importance，也不能丢失相互矛盾标记。

## 6. 正常流程

1. 周期 caller 请求指定 owner 的 consolidation plan。
2. MEMORY 从 metadata 索引按 policy/kind/tag/window 生成稳定 cluster。
3. 校验所有 source record version、legal hold、ACL 与 lineage hash。
4. 生成 strict consolidated EpisodicMemory；原记录转 cold。
5. 原子提交状态、事件、索引和幂等结果；异步移动 cold payload。
6. cold payload 移动失败只重试 storage job，不撤销已提交 lineage；读取可回退旧物理位置。

状态机：

```text
planned -> summarizing -> committing -> completed
planned/summarizing -> failed
committing -> recovery_required -> completed/failed
```

## 7. 边界情况

- commit 后进程在 cold payload move 前崩溃：恢复依据 event/result 继续幂等搬移，不生成第二摘要。
- source 在 plan 后被 tombstone/改 ACL：version mismatch，batch failed，不部分冷移。
- 64 条以上同类记录按稳定窗口和 ID 分成多个 batch，不能无限扩大事务。
- 两个来源互相矛盾：不生成单一肯定句，summary 标为 `mixed_accounts` tag 并保留二者。
- summary 自身不再与自己的 source summary 循环巩固；lineage graph 必须无环。

## 8. 错误、降级与恢复

错误码为 `MEMORY_CONSOLIDATION_STALE`、`MEMORY_POLICY_MISMATCH`、`MEMORY_LINEAGE_CYCLE`、`MEMORY_COLD_STORAGE_FAILED`。任何证据不唯一时进入 `recovery_required`；不得选择删除 source 或猜测 summary。

### 8.1 Version 与 Migration

运行中 batch 固定 algorithm version。Schema upcast 必须保留 source ID/hash、policy、window 和 lineage hash；无法验证旧 summary lineage 时保留为 cold legacy record，但禁止进入热检索，直到人工/迁移审计通过。

## 9. 安全与性能

每次 batch 最多 64 条、每 owner 每游戏日最多 8 batch；扫描走 metadata/tag/policy 索引。摘要 alias 必须沿用与 source 相同 ACL projection，不能把私人姓名转成公开文本。冷存储压缩/加密由 RELEASE owner 实现，MEMORY 只定义逻辑 contract。

## 10. 验收标准

- 固定 3/64/65 条 fixture 产生确定 batch、summary 和 lineage hash。
- policy 不同、高重要、Commitment、shared_secret、legal hold 均不被自动处理。
- crash 于计划/摘要/事务/cold move 各点，最终最多一个 summary 且 source 可恢复。
- source/summary lineage 无环，save/reload 后 hash 与 state 一致。
- 30 游戏日后热索引规模有界且未物理丢失来源。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-013` | cluster/window/eligibility 固定 oracle |
| `TEST-MEMORY-014` | policy、高价值与 protected exclusion |
| `TEST-MEMORY-015` | lineage、事务与 crash recovery |
| `TEST-MEMORY-016` | cold materialize 与 30 日规模预算 |

## 12. 关联文档

- `DOC-MEMORY-003`：hot/cold 检索边界
- `DOC-MEMORY-005`：importance、decay 与 reactivation
- `DOC-MEMORY-009`：AccessPolicy 不扩权
- `DOC-MEMORY-012`：consolidation fixture

---
doc_id: DOC-MEMORY-012
title: 记忆与社会关系验收测试
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-social-test-matrix
  - memory-fixed-fixtures
  - memory-reload-oracles
  - memory-traceability
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MEMORY-001
  - DOC-MEMORY-002
  - DOC-MEMORY-003
  - DOC-MEMORY-004
  - DOC-MEMORY-005
  - DOC-MEMORY-006
  - DOC-MEMORY-007
  - DOC-MEMORY-008
  - DOC-MEMORY-009
  - DOC-MEMORY-010
  - DOC-MEMORY-011
requirements:
  - REQ-MEMORY-012
last_updated: 2026-07-26
---

# 记忆与社会关系验收测试

## 1. 目的

`REQ-MEMORY-012`：建立可直接自动化的 strict Schema、写入幂等、检索评分、巩固/冷存储、衰减/再激活、五维关系、图谱、谣言、六级 ACL、事实/信念、玩家/Mayor、tombstone 与 save/reload 测试闭环，覆盖 `TEST-MEMORY-001..060`。

## 2. 非目标

本文不调用真实 DeepSeek，不以人工阅读代替机器断言，不测试其他 owner 的业务公式，也不把 Secret fixture 内容写入普通日志或验收 bundle。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Fixed Fixture | 固定 world/resident/Revision/GameTime/record/policy 的输入 |
| Oracle | 精确 expected 状态、分数、事件、hash、materialize call count |
| Secret Canary | 仅存在于受限 payload 的合成 token，用于证明 Prompt 前零泄露 |
| Save/Reload Parity | canonical records、indexes、idempotency、ACL、tombstone 的 hash 相等 |
| Fault Point | write/event/index/blob/checkpoint 的可重复崩溃注入位置 |
| Acceptance Bundle | 脱敏 input/hash/trace/oracle/actual/result |

## 4. 数据与接口

`DES-MEMORY-012`：统一 Scenario Manifest：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/acceptance-scenario/v1",
  "type": "object",
  "required": [
    "schema_version",
    "scenario_id",
    "initial_revision",
    "initial_game_time",
    "principal_id",
    "given_fixture_ids",
    "when_steps",
    "expected_oracle_id"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "scenario_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
    "initial_revision": {"type": "integer", "minimum": 0},
    "initial_game_time": {"type": "integer", "minimum": 0},
    "principal_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "given_fixture_ids": {
      "type": "array",
      "minItems": 1,
      "maxItems": 32,
      "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
    },
    "when_steps": {
      "type": "array",
      "minItems": 1,
      "maxItems": 64,
      "items": {
        "type": "object",
        "required": ["step_id", "operation", "input_fixture_id"],
        "properties": {
          "step_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
          "operation": {
            "enum": [
              "write",
              "retrieve",
              "consolidate",
              "decay",
              "reactivate",
              "relationship_delta",
              "graph_query",
              "belief_transfer",
              "authorize",
              "reconcile_belief",
              "journal_hide",
              "tombstone",
              "save_reload",
              "inject_fault"
            ]
          },
          "input_fixture_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
        },
        "additionalProperties": false
      }
    },
    "expected_oracle_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"}
  },
  "additionalProperties": false
}
```

Harness：

```text
run_memory_scenario(manifest, fake_owner_ports, fake_clock_snapshot) -> AcceptanceBundle
inject_memory_fault(fault_point, occurrence) -> FaultHandle
compare_memory_reloads(before, after) -> ReloadParityReport
scan_secret_canaries(bundle, prompt_input, logs, diagnostics) -> SecretLeakReport
audit_memory_traceability() -> TraceabilityReport
```

### 4.1 固定评分 fixture 与 oracle

Query：GameTime 14400（第 10 日），goal/concept=`trade.medicine`，participant=`resident.b`，emotion=`anxiety`，limit 3。允许的三个 metadata：

| ID | semantic | goal | participant | emotion | importance | commitment | recency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `01K1AB2CD3EF4GH5JK6MNP7QRA` | 1000 | 1000 | 1000 | 1000 | 600 | 0 | 550 |
| `01K1AB2CD3EF4GH5JK6MNP7QRB` | 500 | 1000 | 0 | 0 | 900 | 1000 | 900 |
| `01K1AB2CD3EF4GH5JK6MNP7QRC` | 1000 | 0 | 1000 | 500 | 400 | 0 | 1000 |

精确总分：

```text
A=floor((300000+180000+120000+80000+72000+0+44000)/1000)=796
B=floor((150000+180000+0+0+108000+120000+72000)/1000)=630
C=floor((300000+0+120000+40000+48000+0+80000)/1000)=588
order=A,B,C
```

若 B 为 relevant accepted Commitment 且 `commitment_limit=1`，仍只出现一次；若 A 被 ACL deny，则 materialize call count(A)=0，order=B,C。

### 4.2 六级 ACL fixture/oracle

Principal roles：`owner`、`community_member`、`faction_member`、`explicit_friend(trust=70,intimacy=60)`、`mayor_nonmember`、`shared_participant`、`outsider`。

| Level | owner | community member | faction member | explicit friend | mayor nonmember | shared participant | outsider |
|---|---:|---:|---:|---:|---:|---:|---:|
| `public` | allow | allow | allow | allow | allow | allow | allow |
| `community` | allow | allow | deny | deny | deny | deny | deny |
| `faction` | allow | deny | allow | deny | deny | deny | deny |
| `relationship` | allow | deny | deny | allow | deny | deny | deny |
| `personal` | allow | deny | deny | deny | deny | deny | deny |
| `shared_secret` | allow | deny | deny | deny | deny | allow | deny |

`relationship` friend 若未在 explicit allow list 或任一阈值不足即 deny。所有 deny 的 payload Secret Canary materialize count=0。

### 4.3 关系与谣言 fixture/oracle

Clamp fixture 的 Relationship 初值
`{affection:95,trust:10,fear:-5,respect:0,intimacy:0}`，base/interpretation：

```text
affection: base 20, interpretation 1000 -> limited 20 -> actual 5
trust: base 20, interpretation 750 -> limited 15 -> actual 15
fear: base -20, interpretation 500 -> limited -10 -> actual -10
respect: base 10, interpretation 500 -> limited 5 -> actual 5
intimacy: base 10, interpretation 500 -> limited 5 -> actual 5
```

精确 `actual={affection:5,trust:15,fear:-10,respect:5,intimacy:5}`，
`next={affection:100,trust:25,fear:-15,respect:5,intimacy:5}`，绝对值合计 40。

Total-cap fixture 的初值全为 0，
`pre_applied={affection:20,trust:15,fear:-10,respect:5,intimacy:5}`，绝对值合计 55。
按 `DOC-MEMORY-006` v1 比例缩放与余数顺序，精确
`actual={affection:15,trust:11,fear:-8,respect:3,intimacy:3}`，绝对值合计 40。
重放 source event 后两个 fixture 的向量均不变。

Rumor confidence：previous=800、speaker trust=50 → factor=750、base=600；1 个 distortion penalty=80，next=520。recipient 已在 chain、personal、未授权 shared_secret 均不创建 belief。

### 4.4 Reload fixture/oracle

Reload bundle 固定比较：

```json
{
  "schema_version": 1,
  "required_hashes": [
    "memory_records",
    "access_policies",
    "write_keys",
    "relationship_edges",
    "social_overlays",
    "belief_transfers",
    "consolidation_lineage",
    "retention_states",
    "tombstones",
    "hot_index",
    "cold_index",
    "journal_preferences"
  ],
  "required_counts": {
    "active_memories": 8,
    "cold_memories": 3,
    "reactivated_memories": 1,
    "tombstoned_memories": 1,
    "relationship_edges": 2,
    "belief_transfers": 1
  },
  "secret_canary_occurrences_in_prompt_logs_diagnostics": 0
}
```

## 5. 规则与不变量

- `RULE-MEMORY-097`：`REQ-MEMORY-001..012` 每项至少映射一个 executable Test ID、固定 fixture 与机器 oracle。
- `RULE-MEMORY-098`：Schema 测试执行 required/type/enum/range/pattern/conditional/additionalProperties，不做字符串到数字等强制转换。
- `RULE-MEMORY-099`：安全测试记录 materialize 调用；ACL deny、stale、unknown policy 的调用次数必须为 0。
- `RULE-MEMORY-100`：确定性测试至少运行两次并比较 state hash、event trace、result hash、idempotency keys 和 stable order。
- `RULE-MEMORY-101`：fault injection 覆盖状态写前/后、事件写前、索引写前、cold blob move、tombstone payload clear、checkpoint/reload。
- `RULE-MEMORY-102`：save/reload 必须比较第 4.4 节全部 hash/count；不能只比较记录总数。
- `RULE-MEMORY-103`：1/7/30 游戏日模拟每天执行 ACL canary、关系范围、provenance、graph/retrieval index 与 tombstone audit。
- `RULE-MEMORY-104`：Acceptance Bundle、普通日志、Prompt input 与诊断包的 Secret Canary occurrence 必须为 0。

## 6. 正常流程

1. 加载 3 名 Resident、六级 policies、五种 memory kinds、两条 relationship edge 与固定 facts。
2. 先运行 strict Unit/Property，再运行 owner Fake Port Contract。
3. 执行评分、巩固、衰减、关系、graph、rumor、ACL 与 player/mayor scenarios。
4. 在七类 fault point 崩溃并恢复；重放最后 command/source event。
5. 执行 save/reload，比较全部 canonical/index/idempotency hash。
6. 运行 1/7/30 日模拟、Secret scan 与 traceability，输出脱敏 bundle。

## 7. 边界情况

- strict validator 遇到额外字段、numeric string、未知 level/kind/state 必须拒绝。
- 评分同分必须走完整 tie-break，不接受数据库自然顺序。
- policy 在检索和 materialize 间改变，整次 context stale。
- tombstone 记录在 Snapshot 中仍有旧 blob 引用时恢复失败，不返回 payload。
- Fake owner Port 未登记的调用使 suite fail，不以 stub 默认成功。

## 8. 错误、降级与恢复

Fixture、oracle、hash version、Fake Port、Secret scan 任一失败返回 `MEMORY_ACCEPTANCE_INVALID`。缺实现的跨域依赖使用 strict Fake Port；不得 `skip-as-pass`。恢复证据不唯一时期望结果必须是 Recovery Barrier，而不是“尽力继续”。

### 8.1 Version 与 Migration

Acceptance suite ID 固定 `acceptance.memory.v1`。任何 Schema/公式版本更新必须保留旧 fixture replay，并新增 migration input/expected output/ambiguous safe-failure。旧 bundle 缺 materialize call trace 或 Secret scan 不算新 Gate 证据。

## 9. 安全与性能

fixture 使用合成 Secret Canary，不包含真实玩家/API 数据。Unit+Contract 目标 30 秒；30 日模拟可单独运行但必须保存 Seed、Revision、event count、每日 audit hash。测试输出中的 canary 只报告 count/hash，不打印原文。

## 10. 验收标准

| Scenario ID | 必须断言 |
|---|---|
| `memory.schema.five_kinds` | 五种正例、kind mismatch、额外字段、缺 provenance |
| `memory.write.idempotency` | 相同 key 一次，不同 payload conflict，四 fault point原子 |
| `memory.retrieval.oracle` | A/B/C 分数 796/630/588、stable order/limit |
| `memory.consolidation.recovery` | protected 不处理、lineage唯一、cold move crash可恢复 |
| `memory.retention.offline` | table精确、offline delta=0、ACL reactivation |
| `memory.relationship.vector` | 五维 range/delta/total cap/direction/idempotency |
| `memory.graph.overlay` | personal/faction/community分离、无传递 trust |
| `memory.rumor.chain` | confidence=520、loop/level/chain边界、belief-only |
| `memory.acl.matrix` | 第4.2节全表、deny materialize=0、Mayor无 override |
| `memory.fact.belief` | true/false/unknown/contradicted与事实写边界 |
| `memory.player.mayor` | observer差异、journal hide隔离、治理 unknown |
| `memory.tombstone.reload` | payload零回现、第4.4节全部 hash/count一致 |

以上场景、`TEST-MEMORY-001..060`、1/7/30 日 audit、Secret scan 与 traceability 全部通过，MEMORY domain 才可 accepted。

## 11. 测试追踪

| Test ID | 覆盖 |
|---|---|
| `TEST-MEMORY-046` | `REQ-MEMORY-001..002` strict model/write eligibility |
| `TEST-MEMORY-047` | `REQ-MEMORY-003` retrieval oracle/limits |
| `TEST-MEMORY-048` | `REQ-MEMORY-004..005` consolidation/retention |
| `TEST-MEMORY-049` | `REQ-MEMORY-006..007` relationship/graph |
| `TEST-MEMORY-050` | `REQ-MEMORY-008` rumor chain/confidence |
| `TEST-MEMORY-051` | `REQ-MEMORY-009` ACL/Prompt boundary |
| `TEST-MEMORY-052` | `REQ-MEMORY-010` fact/belief separation |
| `TEST-MEMORY-053` | `REQ-MEMORY-011` player/mayor/journal/tombstone |
| `TEST-MEMORY-054` | state machine reachability 与非法边 |
| `TEST-MEMORY-055` | transaction/source-event idempotency fault matrix |
| `TEST-MEMORY-056` | save/reload/reindex parity |
| `TEST-MEMORY-057` | 1 游戏日 invariant/Secret audit |
| `TEST-MEMORY-058` | 7 游戏日 consolidation/relationship drift audit |
| `TEST-MEMORY-059` | 30 游戏日 scale/index/tombstone audit |
| `TEST-MEMORY-060` | 12/12 Requirement、DOC/link/ID/Schema/ACL traceability |

## 12. 关联文档

- `DOC-MEMORY-001..011`：本 suite 的 canonical 输入
- `DOC-FOUNDATION-005`：主观知识、Secret、事务与恢复不变量
- `DOC-FOUNDATION-007`：全局追踪策略
- `DOC-RESIDENT-012`：Resident owner 的跨域 fixture

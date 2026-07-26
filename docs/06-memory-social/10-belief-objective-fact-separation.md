---
doc_id: DOC-MEMORY-010
title: 客观事实、主观信念与未知状态分离
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - belief-fact-separation
  - subjective-knowledge-boundary
  - belief-reconciliation
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-001
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-002
  - DOC-MEMORY-008
requirements:
  - REQ-MEMORY-010
last_updated: 2026-07-26
---

# 客观事实、主观信念与未知状态分离

## 1. 目的

`REQ-MEMORY-010`：建立 Objective Fact、Direct Observation、SemanticBelief、Unknown 与 Contradiction 的严格边界，定义 belief reconciliation 与 action-time truth validation，使居民可持有错误、过期或相互矛盾的信念，却不能把它们写成世界事实。

## 2. 非目标

本文不拥有各业务 Domain 的事实 Schema、不判定所有自然语言命题真值、不修正模型“常识”，也不允许 MEMORY 查询其他 Domain Repository 或提交其状态。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Objective Fact | Canonical owner 在某 Revision 已提交的状态或 DomainEvent |
| Fact Reference | `{owner_domain,event_id/entity_id,revision,fact_type}` 的不可变引用 |
| Direct Observation | 居民对可感知事实的主观经历证据，不等于拥有全部事实 payload |
| SemanticBelief | 居民认为成立的 structured claim，可真、假、过期或不确定 |
| Unknown | actor 没有足够授权 evidence；不是 false |
| Contradiction Set | predicate/subject 相同但 object/confidence 不兼容的 belief ID 集合 |
| Reconciliation | 基于新已提交观察/证词调整 belief confidence/evidence，而非改写事实 |

## 4. 数据与接口

`DES-MEMORY-010`：MEMORY 只保存 `FactReferenceV1`，不复制 owner state：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/fact-reference/v1",
  "type": "object",
  "required": [
    "schema_version",
    "owner_domain",
    "fact_type",
    "entity_id",
    "event_id",
    "fact_revision",
    "fact_projection_hash"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "owner_domain": {
      "enum": [
        "world",
        "map",
        "resident",
        "economy",
        "magic",
        "combat",
        "event",
        "backend"
      ]
    },
    "fact_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
    "entity_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 128},
    "event_id": {"type": ["string", "null"], "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "fact_revision": {"type": "integer", "minimum": 0},
    "fact_projection_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
  },
  "anyOf": [
    {"required": ["entity_id"], "properties": {"entity_id": {"type": "string"}}},
    {"required": ["event_id"], "properties": {"event_id": {"type": "string"}}}
  ],
  "additionalProperties": false
}
```

Belief Query 结果：

```json
{
  "schema_version": 1,
  "actor_resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "claim_key": "shop.apothecary.is_open",
  "observed_revision": 480,
  "knowledge_state": "believed",
  "belief_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRT"],
  "confidence_q1000": 780,
  "contradiction_ids": [],
  "fact_refs_visible_to_actor": []
}
```

`knowledge_state` 封闭为 `unknown/believed/disbelieved/contradicted`；没有 belief 时为 unknown，不从当前客观状态反推 actor 应该知道。Port：

```text
query_actor_belief(actor_id, structured_claim, revision) -> ActorBeliefProjection
reconcile_belief(source_event_id, actor_id, new_evidence) -> BeliefReconciliationResult
resolve_fact_refs_for_validation(fact_refs, owner_ports, latest_revision) -> FactValidationProjection
audit_belief_fact_boundary(world_id, revision) -> BoundaryAudit
```

Reconciliation v1：

```text
direct observation supporting claim: confidence +200
direct observation contradicting claim: confidence -300 and create/update contradiction
authorized testimony supporting claim: confidence +floor(source_confidence/10), max +100
authorized testimony contradicting claim: confidence -floor(source_confidence/10), max -100
clamp 0..1000; each evidence event applies once
```

达到 0 不删除 belief；标为 disbelieved 并保留 provenance。新的 contradictory object 创建独立 SemanticBelief 并建立 contradiction links。

## 5. 规则与不变量

- `RULE-MEMORY-079`：Objective Fact 只由其 canonical owner 写入；MEMORY 只能持有 Fact Reference/authorized projection。
- `RULE-MEMORY-080`：Memory、Belief、Impression、Rumor、模型文本和 relationship vector 均不得作为 Domain owner 的无校验写入事实。
- `RULE-MEMORY-081`：actor 没有 belief/authorized observation 时状态为 unknown；unknown 不等于 false、denied 或不存在。
- `RULE-MEMORY-082`：SemanticBelief 不含全局 truth flag；调试 truth comparison 是隔离测试 projection，不能进入居民上下文。
- `RULE-MEMORY-083`：同一 predicate/subject 可有多个互相矛盾 belief；Repository 不按 key 覆盖。
- `RULE-MEMORY-084`：reconciliation 只由已提交且 actor 有资格获得的 evidence 触发，按 source event 幂等。
- `RULE-MEMORY-085`：Action 提交时 owner 在最新 Revision 校验真实前置；belief 只解释为什么提出，不使非法行动合法。
- `RULE-MEMORY-086`：Fact projection 的 payload/access 由 owner 决定；MEMORY 不因持有 FactRef 绕过 owner ACL。
- `RULE-MEMORY-087`：事实被补偿/改变后，旧直接经历仍保留；新 evidence 更新 belief，不重写历史经历。

## 6. 正常流程

1. Owner 提交 DomainEvent；Orchestrator 构造 actor 可观察的最小 FactRef/observation evidence。
2. MEMORY 写 EpisodicMemory，并按规则创建/更新 SemanticBelief。
3. 对话/谣言只产生 testimony evidence，不查询全局 truth。
4. 检索返回 actor belief projection，明确 unknown/contradicted。
5. AI/玩家提出 Action 后，业务 owner 在最新 Revision 对真实状态重校验。
6. 失败可产生“发现认知过期”的新观察和 reconciliation。

## 7. 边界情况

- 商店实际关闭但居民相信营业：buy proposal 可生成，ECON 校验拒绝并产生可观察失败；belief 随后更新。
- 居民知道 event 发生但无权知道 payload：只写经过 owner disclosure 的 summary，不持有隐藏 FactRef 内容。
- 两名 witness 对同一 actor 描述相反：recipient 可处于 contradicted，不自动选择 confidence 较高者为事实。
- Fact owner 删除 read model projection：Event Log 事实仍可被引用；无法解析时 FactRef 标 stale，不删除 Memory。
- Mayor 公告是客观“公告已发布”，公告内容中的宣称仍可能只是治理声明，不自动成为真实世界状态。

## 8. 错误、降级与恢复

错误码为 `MEMORY_FACT_OWNER_INVALID`、`MEMORY_FACT_REFERENCE_STALE`、`MEMORY_BELIEF_EVIDENCE_FORBIDDEN`、`MEMORY_BELIEF_BOUNDARY_VIOLATION`。Fact owner unavailable 时可保留既有 belief，但新 action validation由 owner拒绝/暂停，MEMORY 不提供猜测真值。

### 8.1 Version 与 Migration

旧 belief 中若含 `is_true`，迁移必须删除该权威语义并把旧值转为带 migration provenance 的 confidence evidence；不得把 true 写回 Fact。无法确认字段来源时保留 legacy quarantine，禁止进入检索，直到审计。

## 9. 安全与性能

FactRef hash 不能作为访问许可。Boundary audit 静态扫描 Schema/代码禁止 `truth/is_true/objective_state` 出现在 MEMORY-owned belief。belief query 按 `(owner,predicate,subject)` 索引，contradiction set≤16，超限进入 summary但不丢 provenance。

## 10. 验收标准

- false/true/unknown/contradicted 四类 fixture 与实际事实独立。
- 无 belief 的 actor 不因服务器知道事实而获得该事实。
- 谣言只创建 testimony belief，Fact store hash/Revision 不变。
- stale belief 可提出行动但 owner 最新校验拒绝，且无越权副作用。
- migration 后 MEMORY Schema 中不存在权威 truth flag。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-038` | fact/belief Schema 与 owner boundary |
| `TEST-MEMORY-039` | unknown/false/contradicted fixtures |
| `TEST-MEMORY-040` | reconciliation formula/idempotency |
| `TEST-MEMORY-041` | stale belief vs latest owner validation 与 migration |

## 12. 关联文档

- `DOC-MEMORY-001`：SemanticBelief strict model
- `DOC-MEMORY-008`：testimony/rumor provenance
- `DOC-MEMORY-009`：FactRef/payload access
- `DOC-FOUNDATION-005`：客观事实与主观认知不变量

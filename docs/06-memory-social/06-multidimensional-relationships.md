---
doc_id: DOC-MEMORY-006
title: 五维有向关系模型
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - relationship-vector
  - relationship-delta
  - relationship-state-machine
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-RESIDENT-003
  - DOC-MEMORY-001
  - DOC-MEMORY-002
requirements:
  - REQ-MEMORY-006
last_updated: 2026-07-26
---

# 五维有向关系模型

## 1. 目的

`REQ-MEMORY-006`：定义 Resident A 指向 Resident B 的 `affection/trust/fear/respect/intimacy` 五个独立维度、严格范围、事件解释、delta 限幅、幂等和重载规则，使关系变化可追踪且不能被模型、玩家或 Mayor 直接设值。

## 2. 非目标

本文不拥有对话 Speech Act、人格、Faction membership、婚恋标签、AI 行动选择或前端好感度 UI。关系向量不是对另一人的客观评价，也不自动对称。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Relationship Edge | `source_resident_id → target_resident_id` 的有向唯一边 |
| Relationship Vector | 五维整数，各自范围 `-100..100` |
| Interpretation | 基于 source Resident personality、existing impression 与事件角色的 `-1000..1000` 因子 |
| Base Delta | 由版本化 event-to-relationship catalog 定义的每维基础变化 |
| Applied Delta | 解释、限幅、clamp 后实际写入的变化 |
| Evidence Entry | source event、dimension、base/interpretation/applied、rule version 的审计记录 |

## 4. 数据与接口

`DES-MEMORY-006`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/relationship-edge/v1",
  "type": "object",
  "required": [
    "schema_version",
    "edge_id",
    "world_id",
    "source_resident_id",
    "target_resident_id",
    "vector",
    "edge_revision",
    "last_source_event_id",
    "state"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "edge_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "target_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "vector": {
      "type": "object",
      "required": ["affection", "trust", "fear", "respect", "intimacy"],
      "properties": {
        "affection": {"type": "integer", "minimum": -100, "maximum": 100},
        "trust": {"type": "integer", "minimum": -100, "maximum": 100},
        "fear": {"type": "integer", "minimum": -100, "maximum": 100},
        "respect": {"type": "integer", "minimum": -100, "maximum": 100},
        "intimacy": {"type": "integer", "minimum": -100, "maximum": 100}
      },
      "additionalProperties": false
    },
    "edge_revision": {"type": "integer", "minimum": 1},
    "last_source_event_id": {
      "type": ["string", "null"],
      "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"
    },
    "state": {"enum": ["active", "archived"]}
  },
  "additionalProperties": false
}
```

每维先计算临时变化：

```text
interpreted_delta =
truncate_toward_zero(base_delta * interpretation_q1000 / 1000)
limited_delta = clamp(interpreted_delta, -20, 20)
pre_next_value = clamp(current_value + limited_delta, -100, 100)
pre_applied_delta = pre_next_value - current_value
```

`base_delta` 必须为 `-20..20`。若五维 `sum(abs(pre_applied_delta)) <= 40`，
则 `applied_delta=pre_applied_delta`。否则每维先执行
`truncate_toward_zero(pre_applied_delta * 40 / sum_abs)`；尚未分配的绝对单位按
`trust,affection,fear,respect,intimacy` 顺序循环分配，每次给仍未达到
`abs(pre_applied_delta)` 的维度增加一个同符号单位，直到总绝对值为 40。
最终 `next_value=current_value+applied_delta`。因此同一 source event 对同一 edge
的五维 applied delta 绝对值之和永不超过 40。

Port：

```text
interpret_relationship_event(event_ref, source_personality_projection) -> RelationshipDeltaSet
apply_relationship_delta_set(command_id, expected_edge_revision, delta_set) -> RelationshipResult
get_relationship_vector(source_id, target_id, revision) -> RelationshipProjection
archive_relationship_edge(source_id, target_id, reason_event_id) -> ArchiveResult
```

## 5. 规则与不变量

- `RULE-MEMORY-042`：五维必须完整且各自 `-100..100`；缺维、额外维或浮点值拒绝。
- `RULE-MEMORY-043`：edge 有向且非对称；A→B 变化不隐式改变 B→A。
- `RULE-MEMORY-044`：只有已提交事件可触发 delta；模型、Client、Mayor、Admin 文本不得直接提交目标向量。
- `RULE-MEMORY-045`：base catalog、人格 projection、source event 和 current edge 固定后，delta/缩放/舍入完全确定。
- `RULE-MEMORY-046`：相同 `(edge_id,source_event_id,rule_version)` 最多应用一次；新 command ID 重放仍不重复变化。
- `RULE-MEMORY-047`：每事件每维限幅 20、五维合计限幅 40；clamp 后记录 actual applied delta，不伪报 base delta。
- `RULE-MEMORY-048`：relationship 不自动随时间衰减；任何缓和/恶化必须有明确事件，例如长期疏远的周期社会事件。
- `RULE-MEMORY-049`：正式 Resident defeat/captive/转职/迁居不删除关系边；target 不可互动时仅投影 availability。
- `RULE-MEMORY-050`：关系变化与 `RelationshipChanged`、evidence entry、幂等结果在同一事务提交。

## 6. 正常流程

1. MEMORY subscriber 接收已提交交互/帮助/伤害/背叛/履约等事件。
2. 确认 source/target 角色、owner 可知证据与 event catalog base delta。
3. Orchestrator 提供固定 Revision 的 source personality projection；MEMORY 计算 interpretation。
4. 按公式限幅、clamp，生成 evidence set。
5. 原子更新有向 edge、事件与幂等结果；写入相应 SocialImpression 可作为同一 MEMORY Unit of Work 的另一记录。

## 7. 边界情况

- current=95、delta=10 时 next=100、actual=5。
- 同一事件既救助又恐吓可同时增加 trust 和 fear；维度不互相覆盖。
- relationship edge 不存在时从全零向量创建，不使用 ancestry/职业/玩家身份默认偏见。
- source personality projection stale 时整个 delta set 重算或拒绝，不混用旧解释。
- target 离开世界常规活动但 Resident 保留：edge archived 仅影响活跃 graph query，不清除证据。

## 8. 错误、降级与恢复

错误码为 `MEMORY_RELATIONSHIP_VECTOR_INVALID`、`MEMORY_RELATIONSHIP_EVENT_UNSUPPORTED`、`MEMORY_RELATIONSHIP_STALE`、`MEMORY_RELATIONSHIP_DUPLICATE_EFFECT`。Catalog 缺项时只写经历/诊断，不猜测 delta。

### 8.1 Version 与 Migration

`relationship-delta/v1` 固定维度、舍入与缩放顺序。旧四维或单好感度数据不得猜测拆分；只有有证据的 mapping 可 upcast，否则 Recovery Barrier。迁移保留 edge ID、direction、evidence 与 source events。

## 9. 安全与性能

完整关系向量默认只向 source actor 自身决策上下文和受限 UI 投影；其他居民不能读取“后台数值”。索引 `(world,source,target)` 唯一，更新 O(1)，evidence 历史进入 append-only event/summary，不无限内嵌 edge。

## 10. 验收标准

- 五维上下界、舍入、合计限幅和 clamp 固定 oracle 通过。
- A→B 与 B→A 独立；同事件重放最多一次。
- 极端人格不能扩大单维/合计上限或让非法事件生效。
- 模型/玩家/Mayor 直接设向量均被拒且无 Revision 变化。
- save/reload 后向量、edge revision、evidence key 一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-021` | 五维 strict Schema 与 range property |
| `TEST-MEMORY-022` | delta/舍入/缩放/clamp oracle |
| `TEST-MEMORY-023` | direction、event eligibility 与幂等 |
| `TEST-MEMORY-024` | transaction/reload/migration safe failure |

## 12. 关联文档

- `DOC-MEMORY-001`：SocialImpression
- `DOC-MEMORY-007`：Social Graph 与 faction overlay
- `DOC-MEMORY-009`：relationship-level ACL
- `DOC-RESIDENT-003`：人格只读输入

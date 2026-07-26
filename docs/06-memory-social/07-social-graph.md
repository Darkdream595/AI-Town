---
doc_id: DOC-MEMORY-007
title: 社会图谱、群体边与 Faction Overlay
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - social-graph
  - relationship-edge-projection
  - faction-attitude-overlay
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-WORLD-006
  - DOC-RESIDENT-001
  - DOC-MEMORY-006
requirements:
  - REQ-MEMORY-007
last_updated: 2026-07-26
---

# 社会图谱、群体边与 Faction Overlay

## 1. 目的

`REQ-MEMORY-007`：定义由有向 Relationship Edge 形成的社会图、只读邻接投影、community/faction overlay 及稳定查询，使个人关系、群体印象和正式 membership 保持独立，不产生传递式“全知关系”。

## 2. 非目标

本文不拥有 Faction/Community 的客观成员关系、法律身份或组织规则；不执行 graph-based 行动，不把 faction 态度写回个人关系，也不定义 UI 社交网络布局。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Social Graph | 以 Resident runtime ID 为节点、`DOC-MEMORY-006` edge 为有向边的 MEMORY 投影 |
| Personal Edge | source 对 target 的五维主观关系 |
| Faction Overlay | source 对 WORLD-owned faction 引用的五维有界态度，不等于 membership |
| Community Overlay | 对 community scope 的群体印象 |
| Membership Projection | Orchestrator 从 WORLD owner 提供的固定 Revision 只读引用 |
| Neighborhood Query | 经 ACL/目的限制后返回的有界边集合 |

## 4. 数据与接口

`DES-MEMORY-007`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/social-overlay/v1",
  "type": "object",
  "required": [
    "schema_version",
    "overlay_id",
    "world_id",
    "source_resident_id",
    "scope_kind",
    "scope_id",
    "vector",
    "evidence_event_ids",
    "overlay_revision"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "overlay_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "scope_kind": {"enum": ["community", "faction"]},
    "scope_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
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
    "evidence_event_ids": {
      "type": "array",
      "maxItems": 64,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}
    },
    "overlay_revision": {"type": "integer", "minimum": 1}
  },
  "additionalProperties": false
}
```

Neighborhood projection：

```json
{
  "schema_version": 1,
  "source_resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "observed_revision": 430,
  "edges": [
    {
      "target_resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
      "relationship_edge_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
      "relationship_edge_revision": 7
    }
  ],
  "overlay_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRW"],
  "truncated": false
}
```

该 projection 不默认包含向量值；需要向量的自身决策 caller 另以授权 Port 读取。Port：

```text
get_social_neighborhood(source_id, purpose, revision, limit) -> SocialNeighborhoodProjection
get_personal_edge(source_id, target_id, access_decision_id) -> RelationshipProjection
apply_social_overlay_delta(source_event_id, source_id, scope_id, delta_set) -> OverlayResult
resolve_social_context(source_id, target_id, membership_projection) -> SocialContextProjection
```

## 5. 规则与不变量

- `RULE-MEMORY-051`：Social Graph edge 与 `RelationshipEdgeV1` 一一对应；图索引不是第二权威，不可独立写向量。
- `RULE-MEMORY-052`：个人 edge、community overlay、faction overlay 三层分别存储；overlay 不覆盖、平均或初始化个人 edge。
- `RULE-MEMORY-053`：membership 是 WORLD-owned 客观引用；MEMORY 不从态度、谣言、职业或姓氏推断 membership。
- `RULE-MEMORY-054`：A 信任 B 且 B 信任 C 不产生 A 信任 C；路径、共同邻居和中心性只可作为受限检索提示，不写关系。
- `RULE-MEMORY-055`：Neighborhood query 默认只返回 source 自身可知且 purpose 允许的 opaque edge refs，limit `1..32`，稳定顺序为 `edge_revision desc/target_id asc`。
- `RULE-MEMORY-056`：Faction/community overlay 的 delta 使用 `DOC-MEMORY-006` 同一范围、事件资格、限幅、舍入与幂等契约。
- `RULE-MEMORY-057`：target/organization 不活跃不删除边；仅 archive projection，历史和 ACL 保留。
- `RULE-MEMORY-058`：graph rebuild 必须从 canonical edge/overlay records 得到相同 node/edge/hash，不从 Event 文本猜测节点。

## 6. 正常流程

1. Relationship/overlay 事务提交后写 `SocialGraphIndexChanged`。
2. Graph projector 按 Revision 幂等更新邻接索引。
3. caller 提供 source、purpose、固定 Revision 和 membership projection。
4. MEMORY 过滤 source 权限、archive state 和 limit，返回 opaque graph projection。
5. 需要具体向量时逐边执行 access decision；AI/对话只接收 Orchestrator 组装的最小 projection。

## 7. 边界情况

- graph projector 落后：返回 index stale，不混合最新 edge 与旧图。
- Resident 更换 faction：membership projection改变，但旧 faction overlay 与个人边仍保留。
- target 既是私人朋友又是敌对 faction 成员：个人 edge 与 faction overlay同时提供给下游，MEMORY 不决定取舍。
- 空图合法；不得以同职业或同 ancestry 自动建边。
- 多个 community/faction scope 同时适用时按 scope ID asc 返回，不能合并成一个不可追踪分数。

## 8. 错误、降级与恢复

错误码为 `MEMORY_SOCIAL_GRAPH_STALE`、`MEMORY_MEMBERSHIP_PROJECTION_INVALID`、`MEMORY_SOCIAL_SCOPE_UNKNOWN`、`MEMORY_GRAPH_INDEX_CORRUPT`。索引损坏时在 Recovery Barrier 下从 edges/overlays 重建；运行时可返回局部 unavailable，不能扩大邻接可见性。

### 8.1 Version 与 Migration

v1 graph index 无持久业务权威，可丢弃重建；edge/overlay Schema migration 必须保留 direction、scope、vector、evidence 和 revision。旧无方向边无法自动复制成双向关系，必须拒绝或由有证据 migration 分别建立。

## 9. 安全与性能

图遍历不返回 Secret、Memory payload、私人地址或隐藏 membership。索引按 `(world,source,target)` 与 `(world,source,scope_kind,scope_id)`；12 Resident 主图很小，但 API 仍限制 depth=1、edges≤32，禁止任意图查询造成越权推断。

## 10. 验收标准

- 个人/faction/community 三层在相同事件下独立变化。
- 三角关系不自动传播，空图不自动建边。
- stale projector、archive、membership 变化有确定结果。
- rebuild 前后 node/edge/overlay hash 一致。
- 未授权 caller 只能看到允许的 opaque refs，不能读取向量或隐藏 scope。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-025` | graph-edge 一致性与 overlay separation |
| `TEST-MEMORY-026` | no-transitive-trust 与 membership boundary |
| `TEST-MEMORY-027` | query ACL/limit/stable order |
| `TEST-MEMORY-028` | index lag/rebuild/migration |

## 12. 关联文档

- `DOC-MEMORY-006`：五维 edge 与 delta
- `DOC-MEMORY-008`：谣言沿社会连接传播但不自动授权
- `DOC-MEMORY-009`：graph query/access policy
- `DOC-WORLD-006`：Faction 与 community 客观语义

---
doc_id: DOC-MAP-005
title: 可行走区域定义
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - authoritative-walkability
  - standing-legality
  - road-navigation-semantics
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-001
  - DOC-MAP-004
requirements:
  - REQ-MAP-005
last_updated: 2026-07-26
---

# 可行走区域定义

## 1. 目的

`REQ-MAP-005`：把合法站立区定义为结构化闭合集合，并规定 agent profile、道路语义、terrain cost 与动态修饰，作为玩家和 NPC 共同的移动前置条件。

## 2. 非目标

Walkability 不表示“没有 Collision”，不决定路径搜索顺序，不从 Ground Art 识别道路，也不拥有门、危险或角色能力的业务状态。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Walkable Surface | 一个无洞、简单、闭合的允许 Polygon |
| Walkable Set | 同一 Scene 中全部 Walkable Surface 的集合并集 |
| Standing Legality | Agent Disc 完整包含于 Walkable Set，且不与有效 Collision 相交 |
| Agent Profile | `radius_wu`、`clearance_wu`、能力 tag 与代价策略 |
| Terrain Tag | `road.primary`、`road.secondary`、`floor`、`grass`、`rough` 等结构化标签 |
| Navigation Modifier | `blocked` 或确定性 cost multiplier/additive 的动态覆盖 |

## 4. 规则与不变量

- `RULE-MAP-017`：Walkable Surface 使用结构化 Polygon，边界包含在 Walkable Set 中；Ground Art 和 Collision 的缺失/存在都不能隐式创建 Walkability。
- `RULE-MAP-018`：合法站立要求半径为 `radius_wu + clearance_wu` 的闭合 Agent Disc 完整位于 Walkable Set，并通过当前 Collision 检查。
- `RULE-MAP-019`：玩家与 NPC 传入相同 Agent Profile 时必须得到相同合法性和基础路径成本；决策来源不影响规则。
- `RULE-MAP-020`：Road 是 Terrain Tag，不是图片颜色；Road tag 必须附着于 Walkable Surface，且不得绕过 Collision、权限或 `blocked` modifier。

## 5. 数据与接口

`DES-MAP-005`：Walkability manifest 中每个 Polygon 顶点遵守 `DOC-MAP-006` 的方向与量化规则，但 Walkable Surface 不含 holes；障碍统一由 Collision 表达。

```json
{
  "scene_id": "region.crown_creek_town",
  "walkability_version": 1,
  "surfaces": [
    {
      "surface_id": "walkable.crown_creek.central_road",
      "vertices_wu": [[64,1984],[4032,1984],[4032,2112],[64,2112]],
      "terrain_tag": "road.primary",
      "base_cost_q1000": 800,
      "allowed_profile_tags": ["ground"]
    }
  ]
}
```

基础 cost 表：

| Terrain Tag | `base_cost_q1000` |
|---|---:|
| `road.primary` | 800 |
| `road.secondary` | 900 |
| `floor` | 1000 |
| `grass` | 1100 |
| `rough` | 1400 |

默认 humanoid profile 为 `radius_wu = 10`、`clearance_wu = 2`、tags=`["ground"]`。Modifier 结构：

```text
{modifier_id, scene_id, shape, blocked, multiplier_q1000, additive_cost, source_revision}
```

约束为 `250 <= multiplier_q1000 <= 4000`、`0 <= additive_cost <= 100000`。

接口：

```text
is_standable(scene_id, point, profile, navigation_revision) -> PositionLegality
surface_tags_at(scene_id, point) -> ordered<TerrainTag>
rasterize_walkability(scene_id, profile, cell_size_wu) -> WalkableCellMask
```

重叠 Surface 选择最低合法 `base_cost_q1000`；相同 cost 以 `surface_id` 字典序稳定决胜。

## 6. 正常流程

1. 加载并验证 Surface Polygon、Terrain Tag 和 profile 限制。
2. 对重叠 Surface 构建确定性 spatial index。
3. 查询时先检查 Agent Disc 是否完全包含于 Walkable Set。
4. 再检查 Collision 与动态 `blocked` modifier。
5. 返回合法性、命中的 Surface ID、effective cost 和 source revision。
6. Pathfinding 从同一接口栅格化，不维护第二套人工可走标记。

## 7. 边界情况

- 点在 Walkable Surface 边界上属于集合，但 Agent Disc 越出集合时仍非法。
- 两个 Polygon 仅边界接触且缝隙小于 Agent Disc 直径时不能跨越。
- Surface 重叠不叠加基础 cost；动态 modifier 才按 `DOC-MAP-007` 组合。
- `blocked` modifier 只覆盖其 shape；撤销后恢复基础 Surface，不修改历史 manifest。
- 水域可以有视觉道路形状，但无 Walkable Surface 即不可站立。

## 8. 错误与降级

未知 Terrain Tag、非法 cost、非简单 Polygon 或未知 profile tag 使对应 manifest 加载失败。查询 revision 已过期返回 `stale_navigation_revision`，调用方必须重新规划，不得使用旧 mask 推进。

## 9. 安全与性能

每 Scene 最多 4096 个 Surface、每 Polygon 最多 256 顶点；构建 R-tree 与按 profile 缓存的 cell mask。动态 modifier 只使相交 dirty cells 失效，且缓存键包含 navigation revision。

## 10. 验收标准

- Walkability 与 Collision 有独立 manifest、独立测试和独立错误码。
- 边界、狭缝、重叠 Surface 与不同 Agent radius 的结果可重复。
- Road cost 只来自 Terrain Tag，替换 Ground Art 后结果不变。
- 玩家/NPC 相同 profile 的合法点、非法点和 effective cost 完全一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-017` | Walkable boundary-inclusive 与 Agent Disc 完整包含 |
| `TEST-MAP-018` | 狭缝、重叠、不同 radius/clearance 的 property test |
| `TEST-MAP-019` | Terrain Tag cost 与 Ground Art 像素无关 |
| `TEST-MAP-020` | 玩家/NPC profile parity 和 stale revision 拒绝 |

## 12. 关联文档

- `DOC-FOUNDATION-004`：Walkability/Collision 词义分离
- `DOC-FOUNDATION-005`：合法位置不变量
- `DOC-MAP-006`：Collision 与 Polygon 几何
- `DOC-MAP-007`：网格与 A*
- `DOC-MAP-010`：动态 modifier 原子更新

---
doc_id: DOC-MAP-006
title: 碰撞多边形规格
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - collision-polygon-format
  - collision-boundary-semantics
  - swept-movement-collision
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-001
  - DOC-MAP-004
  - DOC-MAP-005
requirements:
  - REQ-MAP-006
last_updated: 2026-07-26
---

# 碰撞多边形规格

## 1. 目的

`REQ-MAP-006`：定义 Collision Polygon 的方向、合法性、边界语义、障碍标签、空间索引与 swept test，阻止穿越房屋、树干、悬崖、水域、废墟和封锁区。

## 2. 非目标

Collision 不定义合法站立面的全集，不等同于 Building Footprint 或 sprite bounds，不从 texture alpha/颜色提取，也不决定 Terrain cost。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Outer Ring | Collision 实体的外边界 |
| Hole Ring | Outer Ring 内明确不阻挡的内孔 |
| Signed Area | `0.5 × Σ(x_i*y_(i+1)-x_(i+1)*y_i)` |
| Boundary-exclusive | 仅接触 Collision 边界不算进入 Collision interior |
| Expanded Obstacle | 按 `agent_radius_wu + clearance_wu` 做 Minkowski 扩张后的障碍 |
| Swept Disc | Agent Disc 从起点到终点运动形成的 capsule |

## 4. 规则与不变量

- `RULE-MAP-021`：在 `+Y` 向下坐标中，Outer Ring 按屏幕视觉顺时针存储且 Signed Area `> 0`；Hole Ring 逆时针且 Signed Area `< 0`。
- `RULE-MAP-022`：Collision Polygon 必须闭合、简单、无自交；不重复存储末顶点，连续顶点距离至少 `1/16 wu`，绝对面积至少 `1 wu²`。
- `RULE-MAP-023`：Collision 采用 boundary-exclusive 分类；移动规划对障碍按 agent radius 与 clearance 扩张，从而允许恰好保持 clearance 的边界接触但禁止进入 interior。
- `RULE-MAP-024`：移动命令必须对整段 Swept Disc 检查，不能只验证终点；任何 Collision 数据均不得从像素、阴影、sprite bounds 或 Ground Art 自动推断。

## 5. 数据与接口

`DES-MAP-006`：Collision shape 首版支持 `polygon`、`circle`、`capsule`、`aabb`，静态地图复杂边界必须规范化为 Polygon。障碍 tag registry：

```text
structure.wall
structure.tree_trunk
terrain.cliff
terrain.water
structure.rubble
door.closed
hazard.hard_block
construction.blocked
```

Road、草地和装饰阴影不得使用 Collision tag。

```json
{
  "collision_id": "collision.crown_creek.wall.west_001",
  "scene_id": "region.crown_creek_town",
  "shape_type": "polygon",
  "outer_ring_wu": [[320,320],[640,320],[640,384],[320,384]],
  "hole_rings_wu": [],
  "obstacle_tag": "structure.wall",
  "source_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "enabled": true,
  "source_revision": 42
}
```

接口：

```text
validate_polygon(polygon) -> PolygonValidationResult
intersects_disc(scene_id, center, radius_wu, revision) -> CollisionHit[]
sweep_disc(scene_id, start, end, radius_wu, clearance_wu, revision) -> SweepResult
expand_for_profile(shape, profile) -> ExpandedShape
```

`SweepResult` 至少含 `clear`、`first_hit_fraction_q1000000`、`collision_id`、`normal_degrees`、`navigation_revision`。

## 6. 正常流程

1. 量化顶点并移除相邻的等值点。
2. 校验方向、面积、自交、Hole 包含与 ring 相交。
3. 按 Bounds 分桶并构建 R-tree。
4. 移动前查询 Swept Disc 的候选 Collision。
5. 对 Expanded Obstacle 做精确 segment/shape test，按最小命中 fraction 决定可推进距离。
6. 提交位置前在最新 revision 再校验一次。

## 7. 边界情况

- Swept Disc 起点已在 Collision interior 时返回 `start_in_collision`，只允许恢复流程迁移到登记的 safe point。
- Hole 必须完全位于 Outer Ring interior 且互不接触；触边 Hole 使 manifest 失败。
- 多个障碍同 fraction 命中时以 `collision_id` 字典序稳定决胜。
- 两个 Collision 重叠按集合并集阻挡，不因重叠形成可走区。
- Scene Bounds 由 `DOC-MAP-001` 单独检查，不伪造成围墙 Polygon。
- Footprint 可大于或小于 Collision，但 placement 同时验证二者各自规则。

## 8. 错误与降级

非法 Polygon、未知 tag、悬空 source entity 或过期 revision 均拒绝加载/查询。运行时索引损坏时暂停相关 Scene 移动并从最新 MapSnapshot 重建；不得切换为像素碰撞。

## 9. 安全与性能

每 Polygon 最多 256 顶点、每个 Shape 最多 32 个 Hole、每 Scene 最多 16384 个 Collision shape。Broad phase 使用 R-tree，narrow phase 仅处理候选；单次 sweep 候选超过 512 时返回 `collision_budget_exceeded` 并拒绝移动。

## 10. 验收标准

- 顺/逆时针、Hole、自交、退化边和面积规则均有确定校验结果。
- 高速移动不能穿过宽度小于单步距离的墙体。
- Agent radius/clearance 增大后可达集合只能不变或缩小。
- Ground Art、sprite 或阴影任意变化不改变 Collision hit。
- 水域、悬崖、墙、树干、废墟和封锁区 fixture 均阻挡玩家与 NPC。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-021` | Ring winding、Signed Area、Hole 与自交 validation |
| `TEST-MAP-022` | boundary-exclusive 接触和 Expanded Obstacle clearance |
| `TEST-MAP-023` | Swept Disc 防 tunneling、稳定 first hit |
| `TEST-MAP-024` | obstacle tag coverage、像素独立、玩家/NPC parity |

## 12. 关联文档

- `DOC-FOUNDATION-006`：Polygon 边界 owner 要求与量化基元
- `DOC-MAP-005`：合法站立区
- `DOC-MAP-007`：Collision 栅格化与 A*
- `DOC-MAP-010`：动态 Collision 更新
- `DOC-MAP-012`：几何与穿墙验收

---
doc_id: DOC-MAP-007
title: 导航网格与寻路
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - navigation-grid
  - astar-pathfinding
  - path-result-contract
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-005
  - DOC-MAP-006
requirements:
  - REQ-MAP-007
last_updated: 2026-07-26
---

# 导航网格与寻路

## 1. 目的

`REQ-MAP-007`：定义由结构化 Walkability/Collision 派生的 `16 wu` 导航网格、确定性 A*、动态成本、路径结果与预算，使玩家和 NPC 使用同一可重放路径服务。

## 2. 非目标

本文不把网格作为地图编辑源，不读取图片，不决定 actor 的目标，也不保证已返回路径在未来 Revision 继续有效。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Navigation Cell | 与 Scene 原点对齐的 `16 × 16 wu` 单元 |
| Traversable Edge | Agent 从相邻 cell center 进行 Swept Disc 检查后合法的边 |
| Directed Edge Terrain | 有向边 `u -> v` 固定采样 destination cell `v` 中心解析出的 Surface/Modifier |
| 8-neighbor A* | 使用四个正交与四个对角邻居的 A* |
| Corner Cutting | 对角移动穿过两个不可通行正交邻居之间的角 |
| Navigation Revision | 生成当前网格/索引的已提交 World Revision |
| Path Budget | 单次查询允许扩展的最大节点数 |
| Minimum Edge Cost | 从同一完整 edge formula、最小 traversable terrain/modifier 和零 additive 计算的 heuristic 下界 |

## 4. 规则与不变量

- `RULE-MAP-025`：Navigation Cell 固定 `16 wu`，cell `(cx,cy)` 中心为 `(cx*16+8, cy*16+8)`；网格只由规则层栅格化。
- `RULE-MAP-026`：A* 使用 8-neighbor；正交 step cost=`1000`，对角=`1414`。每条有向边只按 destination cell 中心的 resolved terrain/modifier/additive 收费；对角边要求两个相邻正交边均可通行，禁止 Corner Cutting。
- `RULE-MAP-027`：查询和结果必须携带 Navigation Revision；提交移动前 revision 不一致即重新规划，不能沿旧路径继续。
- `RULE-MAP-028`：Heuristic 必须使用本文完整 edge formula 的可证明下界且不得包含正 additive；同一 Scene、profile、start、goal、revision 与 modifier 集合必须返回相同 status 和 waypoint 序列，tie-break 固定为较小 `f`、`h`、`cy`、`cx`、node key。

## 5. 数据与接口

`DES-MAP-007`：cell 可通行当且仅当其 center 对 profile 通过 `is_standable`；edge 还必须通过 `sweep_disc`。对有向边 `u -> v`，`terrain_q1000(v)` 使用 `DOC-MAP-005` 在 destination center `v` 解析的确定 Surface；重叠时沿用最低 cost、再按 `surface_id` 决胜。只有 shape 包含 `v` 中心的动态 modifier 参与该边收费。

Modifier 按 `modifier_id` 字典序用整数运算组合：

```text
modifier_q1000 = 1000
for each modifier m:
    modifier_q1000 = ceil_div(modifier_q1000 * m.multiplier_q1000, 1000)
modifier_q1000 = clamp(modifier_q1000, 250, 4000)
additive_cost = clamp(sum(m.additive_cost), 0, 100000)
```

完整 directed edge integer formula：

```text
numerator = step_cost * terrain_q1000(v) * modifier_q1000(v)
scaled_cost = ceil_div(numerator, 1_000_000)
edge_cost(u -> v) = scaled_cost + additive_cost(v)
ceil_div(a,b) = floor((a + b - 1) / b), a >= 0, b > 0
```

`blocked=true` 直接移除 destination cell 及所有入边；所有乘法使用无符号 64-bit checked arithmetic，溢出使查询失败。

Heuristic 在当前 NavigationSnapshot 与 profile 上计算：

```text
min_terrain_q1000 = min(terrain_q1000(v)) over traversable destination cells
min_modifier_q1000 = min(modifier_q1000(v)) over traversable destination cells
min_orth_edge_cost = ceil_div(1000 * min_terrain_q1000 * min_modifier_q1000, 1_000_000) + 0
min_diag_edge_cost = ceil_div(1414 * min_terrain_q1000 * min_modifier_q1000, 1_000_000) + 0
dx = abs(goal.cx - current.cx)
dy = abs(goal.cy - current.cy)
diagonal_steps = min(dx,dy)
straight_steps = max(dx,dy) - diagonal_steps
h = diagonal_steps * min(min_diag_edge_cost, 2 * min_orth_edge_cost)
  + straight_steps * min_orth_edge_cost
```

terrain 与 modifier 的最小值即使来自不同 cell，其乘积也不大于任何真实 edge 的对应乘积；additive 下界固定为零，因此 `h` 不高估剩余成本。空 traversable edge 集直接返回 `unreachable`，不构造 heuristic。

```json
{
  "status": "success",
  "scene_id": "region.crown_creek_town",
  "navigation_revision": 84,
  "profile_id": "agent_profile.humanoid.default",
  "waypoints": [
    {"x_wu": 1024.0, "y_wu": 768.0},
    {"x_wu": 1032.0, "y_wu": 776.0},
    {"x_wu": 1088.0, "y_wu": 832.0}
  ],
  "total_cost": 5128,
  "expanded_nodes": 143
}
```

Status enum：

```text
success | unreachable | invalid_start | invalid_goal |
stale_navigation_revision | budget_exceeded | scene_not_ready
```

接口：

```text
find_path(scene_id, start, goal, profile, expected_revision, max_expanded=100000) -> PathResult
validate_path(path_result, current_revision) -> PathValidationResult
nearest_legal_cell(point, profile, max_chebyshev_cells=2) -> Cell | none
```

起终点 snap 只搜索 Chebyshev 半径 2 cells（`32 wu`），按欧氏距离平方、`cy`、`cx` 排序；超出即 `invalid_start/goal`。Path smoothing 仅在完整 Swept Disc 直线检查通过时删除中间点。

## 6. 正常流程

1. 读取与 `expected_revision` 匹配的不可变 NavigationSnapshot。
2. 验证或有界 snap start/goal。
3. 以稳定 priority queue 执行 A*，扩展时应用当前结构化 cost。
4. 得到 cell path 后执行可选 line-of-sight smoothing。
5. 用精确 Swept Disc 复核全部段，返回 waypoints 与 revision。
6. actor 每到 waypoint 或收到导航变更事件时重新检查 path validity。

## 7. 边界情况

- 起点因恢复错误位于 Collision 时返回 `invalid_start`，只允许 `DOC-MAP-012` 的 safe recovery 处理。
- goal 是被占用 Door approach 时可返回路径至 queue point，不把 Door Collision 临时忽略。
- cost 相同的绕行由 tie-break 固定，不依赖 hash/map iteration order。
- 有向边反向时重新按新的 destination cell 收费；terrain 不同可导致 `cost(u->v) != cost(v->u)`，但合法性仍分别执行 Swept Disc。
- `road.primary=800` 与最小 modifier `250`、零 additive 时，orthogonal edge=`200`，diagonal edge=`283`；heuristic 必须采用相同两个下界。
- Path Budget 耗尽与 `unreachable` 分开，调用方可延迟重试但不能宣称无路。
- Active 使用完整网格；Warm/Background 可使用 Semantic graph 估算，但位置提交仍需在 Active 规则上复核。

## 8. 错误与降级

`budget_exceeded` 时返回空 waypoints 与诊断计数，调度器降低重规划频率或选择安全等待；不能退化为直线穿越。缓存丢失时从规则层重建；Scene 未 ready 时返回 `scene_not_ready`。

## 9. 安全与性能

Region 最大约 `256 × 256` cells，矿洞 `192 × 192`；每查询默认上限 100000 expanded nodes、单 actor 每个 World Tick 最多一次重规划。缓存键包含 Scene、profile、start cell、goal cell、navigation revision；动态变更只失效相交 partition。

## 10. 验收标准

- 直路、对角、窄门、障碍绕行和无路 fixture 的成本与路径确定。
- Directed edge destination sampling、modifier 顺序、ceil rounding 与 additive clamp 有逐值 fixture。
- `road.primary=800 + modifier=250 + additive=0` fixture 中 A* 与零 heuristic Dijkstra 的 total cost/path optimum 相同。
- 所有路径段均通过当前 revision 的 Swept Disc 复核。
- 动态 cost 会改变择路但不绕过 blocked/Collision。
- 玩家与 NPC 相同输入得到 byte-equivalent status、cost 和 waypoints。
- 100 次不同容器迭代顺序运行得到相同路径。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-025` | `16 wu` 栅格、directed destination terrain、8-neighbor cost 与 no-corner-cutting |
| `TEST-MAP-026` | 完整 formula minimum edge cost；road+minimum-modifier 的 A* 与 Dijkstra 等价 |
| `TEST-MAP-027` | modifier 组合、ceil rounding、additive、tie-break、snap 和 smoothing 确定性 |
| `TEST-MAP-028` | stale revision、budget、unreachable 与玩家/NPC parity |

## 12. 关联文档

- `DOC-MAP-005`：Walkability 与 cost source
- `DOC-MAP-006`：Swept Disc 与 Expanded Obstacle
- `DOC-MAP-008`：Door approach/queue point
- `DOC-MAP-010`：NavigationSnapshot 原子更新
- `DOC-MAP-012`：路径验收矩阵

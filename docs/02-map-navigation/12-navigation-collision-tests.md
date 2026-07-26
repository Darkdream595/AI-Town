---
doc_id: DOC-MAP-012
title: 导航与碰撞验收测试
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - map-navigation-acceptance
  - critical-route-audit
  - unreachable-semantic-node-audit
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-001
  - DOC-MAP-002
  - DOC-MAP-003
  - DOC-MAP-004
  - DOC-MAP-005
  - DOC-MAP-006
  - DOC-MAP-007
  - DOC-MAP-008
  - DOC-MAP-009
  - DOC-MAP-010
  - DOC-MAP-011
requirements:
  - REQ-MAP-012
last_updated: 2026-07-26
---

# 导航与碰撞验收测试

## 1. 目的

`REQ-MAP-012`：建立覆盖坐标、五层分离、Walkability、Collision、A*、Door/Interior、区域转场、动态障碍、Camera、不可达节点与玩家/NPC parity 的可重复验收矩阵。

## 2. 非目标

本文不替代各文档的 Unit/Property tests，不验收正式美术品质或业务 owner 状态机，也不以人工游玩代替结构化断言。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Acceptance Map | 固定结构化输入、seed、profile 与期望结果的 Scene fixture |
| Typed Critical Route | 以 `SemanticEndpoint={semantic_node_id,point_role}` 引用具体 node geometry 的 route |
| Required Semantic Node | `reachability_policy=required` 的交互/转场节点 |
| Conditional Node | 只有明确 `availability_condition_id` 成立时要求可达的节点 |
| Parity Run | 用 PlayerCommand 与 NPC ActionProposal 驱动相同 MAP query 的成对测试 |
| Geometry Oracle | 独立于 A* 实现的精确 Polygon/Swept Disc 断言 |

## 4. 规则与不变量

- `RULE-MAP-045`：每个 Required Semantic Node 必须 enabled、解析到具体 WorldPoint 并从所属 Scene 的 Region Anchor 可达；Conditional Node 只按注册 condition 在固定 Revision 求值，unavailable 返回 `not_applicable` 且不调用 Pathfinding，available 则按 Required Node 验证，evaluation error 使 Gate 失败。
- `RULE-MAP-046`：Critical Route 必须用 typed SemanticEndpoint 引用 `DOC-MAP-002` canonical node 和合法 point role；Gate 对所有 applicable、must-remain-open route 返回 concrete `PathResult.success`，每段通过 Geometry Oracle，cost 不超过登记上限。
- `RULE-MAP-047`：Parity Run 只改变决策来源，profile、revision、命令参数和世界状态完全相同；结果 status、position、cost、Collision hit 必须一致。
- `RULE-MAP-048`：验收必须在纯结构化 Ground Art stub 与正常 Ground Art 两次运行；规则结果逐字节一致，证明未从像素推断。

## 5. 数据与接口

`DES-MAP-012`：固定 Acceptance Maps：

| Fixture ID | 内容 | 核心断言 |
|---|---|---|
| `map_fixture.bounds_512` | `512×512`、边界 Surface | 半开 Bounds、Agent Disc 边界 |
| `map_fixture.narrow_passage` | `18/24/32 wu` 三种通道 | radius+clearance 可达阈值 |
| `map_fixture.swept_wall` | `4 wu` 墙、`128 wu` 单步 | 无 tunneling |
| `map_fixture.door_interior` | capacity=1 Door + Interior | 排队、transfer、刷新恢复 |
| `map_fixture.dynamic_build` | 六阶段 Structure 跨道路候选 | 原子 patch、route gate、rollback |
| `map_fixture.region_transitions` | 三 Region + 两组 Exit | 双向转场、arrival conflict |
| `map_fixture.camera_small_scene` | 小于 viewport 的 Interior | 居中与 letterbox |
| `map_fixture.pixel_independence` | 相同规则层、两组随机像素 | 全部规则输出一致 |
| `map_fixture.semantic_node_policy` | Required + unavailable Conditional Node | concrete path / `not_applicable` |
| `map_fixture.astar_minimum_edge` | road `800`、modifier `250`、zero additive | orth `200`、diag `283`、A*=Dijkstra |
| `map_fixture.dependency_closure` | merged/missing/changed dependency blobs | verified / failed / invalidated |

Semantic acceptance runner 必须先解析 `DOC-MAP-002` 的 canonical JSON manifest，按 record `id` 建立只读索引，再解析本节的 machine fixture；禁止从后续 Markdown 表格重建 registry。Availability case 的 `policy_fixture` 只在隔离 fixture copy 上覆盖指定 record，不修改 canonical manifest。

Semantic availability fixture：

| Case | Node policy/state | Condition result | Expected |
|---|---|---|---|
| `semantic_case.required_enabled` | `required`, `enabled=true`, condition `null` | 不求值 | Anchor/Exit 坐标解析，调用 A*，返回 concrete `PathResult.success` |
| `semantic_case.conditional_unavailable` | `conditional`, `enabled=true`, `condition.fixture.closed` | `unavailable` | `not_applicable`，Pathfinding call count=`0` |
| `semantic_case.conditional_available` | `conditional`, `enabled=true`, `condition.fixture.open` | `available` | 解析 endpoint 并要求 concrete path |
| `semantic_case.condition_error` | `conditional`, `enabled=true`, `condition.fixture.error` | `evaluation_error` | Gate failed，不改写为 `not_applicable` |

Exit pair consistency fixture：

| Source Exit | Target Exit | Source approach | Expected Target arrival |
|---|---|---:|---:|
| `semantic_exit.crown_creek.north_forest_gate` | `semantic_exit.twilight_whisper_forest.south_path` | town `(2048,160)` | forest `(2048,3968)` |
| `semantic_exit.twilight_whisper_forest.south_path` | `semantic_exit.crown_creek.north_forest_gate` | forest `(2048,3936)` | town `(2048,128)` |
| `semantic_exit.crown_creek.west_mine_road` | `semantic_exit.silver_ash_mine.east_entry` | town `(160,2048)` | mine `(2944,1536)` |
| `semantic_exit.silver_ash_mine.east_entry` | `semantic_exit.crown_creek.west_mine_road` | mine `(2912,1536)` | town `(128,2048)` |

每行同时断言 `source.target_scene_id == target.scene_id`、`source.target_arrival_point == target.arrival_point`；成功 Transition Event 的 `to` 坐标必须等于表中 Expected Target arrival。

Typed Semantic acceptance fixture：

```json
{
  "fixture_id": "map_fixture.semantic_registry_v1",
  "registry_contract": {
    "source_doc_id": "DOC-MAP-002",
    "semantic_schema_version": 1,
    "expected_nodes": 7,
    "expected_anchors": 3,
    "expected_exits": 4
  },
  "availability_cases": [
    {
      "case_id": "semantic_case.required_enabled",
      "node_id": "semantic_anchor.crown_creek.crown_square",
      "policy_fixture": {
        "enabled": true,
        "reachability_policy": "required",
        "availability_condition_id": null
      },
      "condition_result": null,
      "expected_status": "success",
      "expected_pathfinding_calls": 1
    },
    {
      "case_id": "semantic_case.conditional_unavailable",
      "node_id": "semantic_anchor.twilight_whisper.oathkeeper_camp",
      "policy_fixture": {
        "enabled": true,
        "reachability_policy": "conditional",
        "availability_condition_id": "condition.fixture.closed"
      },
      "condition_result": "unavailable",
      "expected_status": "not_applicable",
      "expected_pathfinding_calls": 0
    },
    {
      "case_id": "semantic_case.conditional_available",
      "node_id": "semantic_anchor.silver_ash.entry_shed",
      "policy_fixture": {
        "enabled": true,
        "reachability_policy": "conditional",
        "availability_condition_id": "condition.fixture.open"
      },
      "condition_result": "available",
      "expected_status": "success",
      "expected_pathfinding_calls": 1
    },
    {
      "case_id": "semantic_case.condition_error",
      "node_id": "semantic_anchor.silver_ash.entry_shed",
      "policy_fixture": {
        "enabled": true,
        "reachability_policy": "conditional",
        "availability_condition_id": "condition.fixture.error"
      },
      "condition_result": "evaluation_error",
      "expected_status": "gate_failed",
      "expected_pathfinding_calls": 0
    }
  ],
  "transition_cases": [
    {
      "source_exit_id": "semantic_exit.crown_creek.north_forest_gate",
      "target_exit_id": "semantic_exit.twilight_whisper_forest.south_path",
      "expected_target_arrival": {"scene_id": "region.twilight_whisper_forest", "x_wu": 2048, "y_wu": 3968}
    },
    {
      "source_exit_id": "semantic_exit.twilight_whisper_forest.south_path",
      "target_exit_id": "semantic_exit.crown_creek.north_forest_gate",
      "expected_target_arrival": {"scene_id": "region.crown_creek_town", "x_wu": 2048, "y_wu": 128}
    },
    {
      "source_exit_id": "semantic_exit.crown_creek.west_mine_road",
      "target_exit_id": "semantic_exit.silver_ash_mine.east_entry",
      "expected_target_arrival": {"scene_id": "region.silver_ash_mine", "x_wu": 2944, "y_wu": 1536}
    },
    {
      "source_exit_id": "semantic_exit.silver_ash_mine.east_entry",
      "target_exit_id": "semantic_exit.crown_creek.west_mine_road",
      "expected_target_arrival": {"scene_id": "region.crown_creek_town", "x_wu": 128, "y_wu": 2048}
    }
  ],
  "critical_routes": [
    {
      "route_id": "critical_route.crown_creek.square_to_forest_gate",
      "scene_id": "region.crown_creek_town",
      "from": {"semantic_node_id": "semantic_anchor.crown_creek.crown_square", "point_role": "point"},
      "to": {"semantic_node_id": "semantic_exit.crown_creek.north_forest_gate", "point_role": "approach_point"},
      "profile_id": "agent_profile.humanoid.default",
      "max_cost": 500000,
      "must_remain_open": true
    },
    {
      "route_id": "critical_route.crown_creek.square_to_mine_road",
      "scene_id": "region.crown_creek_town",
      "from": {"semantic_node_id": "semantic_anchor.crown_creek.crown_square", "point_role": "point"},
      "to": {"semantic_node_id": "semantic_exit.crown_creek.west_mine_road", "point_role": "approach_point"},
      "profile_id": "agent_profile.humanoid.default",
      "max_cost": 500000,
      "must_remain_open": true
    },
    {
      "route_id": "critical_route.twilight_whisper.camp_to_south_path",
      "scene_id": "region.twilight_whisper_forest",
      "from": {"semantic_node_id": "semantic_anchor.twilight_whisper.oathkeeper_camp", "point_role": "point"},
      "to": {"semantic_node_id": "semantic_exit.twilight_whisper_forest.south_path", "point_role": "approach_point"},
      "profile_id": "agent_profile.humanoid.default",
      "max_cost": 500000,
      "must_remain_open": true
    },
    {
      "route_id": "critical_route.silver_ash.shed_to_east_entry",
      "scene_id": "region.silver_ash_mine",
      "from": {"semantic_node_id": "semantic_anchor.silver_ash.entry_shed", "point_role": "point"},
      "to": {"semantic_node_id": "semantic_exit.silver_ash_mine.east_entry", "point_role": "approach_point"},
      "profile_id": "agent_profile.humanoid.default",
      "max_cost": 400000,
      "must_remain_open": true
    }
  ]
}
```

`SemanticEndpoint.semantic_node_id` 必须解析到 canonical record 的 `id`。`point_role` 只允许 `point/approach_point/arrival_point`，且所选字段不得为 null、其 `scene_id` 必须等于 route `scene_id`。四条生产路线统一使用 default humanoid profile，并在无临时 actor 占位的静态规则快照上执行；下表只是上述 JSON 的 derived human view：

| Route ID | From typed endpoint | To typed endpoint | 最大 cost |
|---|---|---|---:|
| `critical_route.crown_creek.square_to_forest_gate` | `semantic_anchor.crown_creek.crown_square#point` | `semantic_exit.crown_creek.north_forest_gate#approach_point` | 500000 |
| `critical_route.crown_creek.square_to_mine_road` | `semantic_anchor.crown_creek.crown_square#point` | `semantic_exit.crown_creek.west_mine_road#approach_point` | 500000 |
| `critical_route.twilight_whisper.camp_to_south_path` | `semantic_anchor.twilight_whisper.oathkeeper_camp#point` | `semantic_exit.twilight_whisper_forest.south_path#approach_point` | 500000 |
| `critical_route.silver_ash.shed_to_east_entry` | `semantic_anchor.silver_ash.entry_shed#point` | `semantic_exit.silver_ash_mine.east_entry#approach_point` | 400000 |

A* minimum-edge fixture 固定 destination terrain=`road.primary/800`、effective modifier=`250`、additive=`0`；按 `DOC-MAP-007` 完整公式得到 orth=`ceil(1000×800×250/1,000,000)=200`、diag=`ceil(1414×800×250/1,000,000)=283`。对同一 grid 分别运行 production A* 与 `h=0` Dijkstra，断言 total optimum cost 相等。

Dependency closure fixture 在同一 merged candidate tree 对 `DOC-FOUNDATION-005/006`、`DOC-WORLD-004/009` 及全部传递依赖验证 `source_commit_sha + blob + content_sha256 + document_status`。并行 worktree 只用于兼容性 review，不计作 integrated；内容 bytes 变化后旧 Map Package 必须从 `verified` 变为 `invalidated`。

审计接口：

```text
audit_semantic_reachability(map_snapshot, profile) -> NodeReachabilityReport
audit_critical_routes(map_snapshot, route_set, profile) -> CriticalRouteReport
audit_exit_pair_coordinates(semantic_registry) -> PairCoordinateReport
audit_dependency_closure(package, merged_candidate_tree) -> DependencyClosureReport
run_player_npc_parity(fixture, revision) -> ParityReport
run_map_acceptance(package) -> MapAcceptanceReport
```

报告必须包含 map package hash、navigation revision、profile、seed、expanded nodes、失败 node/Collision ID 和脱敏 reason code。

## 6. 正常流程

1. Task 17 先在同一 merged candidate tree 运行 dependency commit/blob/content hash closure；未 verified 不进入 corpus-level acceptance。
2. Schema lint 验证五层 manifest、typed SemanticNode、ID、Polygon 与四方向 pair coordinates。
3. Unit/Property tests 覆盖坐标、几何、栅格、完整 directed edge cost 与 determinism。
4. 对十一项 Acceptance Maps 运行 Contract/Integration tests。
5. 在固定 Revision 求值 availability，再对三个 Region 和全部 Interior 运行 Semantic reachability。
6. 对四条 typed Critical Route 运行基线与每个动态状态 patch 后审计。
7. 使用玩家/NPC 两种来源执行相同移动、Door、Interior 和 Region transition。
8. Browser E2E 打开 debug overlays，人工只核对表现与结构报告一致。
9. 保存/恢复 MapSnapshot 后重跑关键报告并比较 hash/结果。

## 7. 边界情况

- Conditional Node 条件为 false 时报告 `not_applicable`，条件缺失则失败，不能算通过。
- Required Node disabled、endpoint point role 为 null、跨 Scene endpoint 或 condition evaluation error 均使 Gate 失败。
- Path Budget 耗尽报告 `inconclusive_budget_exceeded` 并使 Gate 失败，不等同 `unreachable`。
- 动态 actor 暂时占位不使静态 Critical Route 失败，但 Arrival/Queue capacity 测试必须覆盖等待。
- Ground Art stub 可以是纯色或随机噪声，但尺寸与 manifest 必须合法。
- 恢复时 actor 已落入新 Collision 必须保持 Recovery Barrier 并使用登记 safe recovery fixture。

## 8. 错误与降级

依赖未合入同一 tree、commit 不含记录 blob、content hash 变化或依赖 status 不符时 corpus integration 失败/失效。任一 pair coordinate、Must route、Required Node、available Conditional Node、Parity、A*/Dijkstra 或像素独立断言失败时 Map Package 不得批准。测试 runner 异常或预算不足记为 failed/inconclusive，不允许人工改写为 pass；输出 exact fixture、seed、revision 和最小复现。

## 9. 安全与性能

随机 property tests 使用世界 Seed 派生的 `map_test` stream 并记录 sequence。每个 Region 全量 reachability 上限 100000 expanded nodes/route；测试不读取未登记路径、Secret 或用户文件。性能基线：Region A* P95 `<= 50 ms`、动态 Dirty rebuild P95 `<= 100 ms`，在发布基准机单线程规则执行测量。

## 10. 验收标准

- `REQ-MAP-001..012` 均至少被一个 `TEST-MAP-*` 覆盖。
- 十一项 Acceptance Maps 全部通过；Exit pair coordinates 4/4、Critical Route 4/4、applicable Required/Conditional Node 100% 可达。
- unavailable Conditional Node 为 `not_applicable` 且 Pathfinding 调用数为 0；enabled Required Node 返回 concrete path。
- road+minimum-modifier fixture 的 orth/diag 下界为 `200/283`，A* optimum 与 Dijkstra 相等。
- Corpus-level approval 仅在 dependency closure verified 后成立；任何 dependency bytes 变化都会使旧 package invalidated。
- 六种建筑/损坏状态、Door 状态、两组区域 Exit 与至少一个 Interior 全覆盖。
- 玩家/NPC parity mismatch 为 0，像素独立输出差异为 0。
- 保存/恢复前后 Map Package hash、合法位置、关键路径 status/cost 一致。
- Camera、loading fallback 和六种 debug overlay 通过 Browser E2E/Visual QA。

## 11. 测试追踪

| 测试 ID | 覆盖 |
|---|---|
| `TEST-MAP-045` | `REQ-MAP-001..002` 坐标、typed SemanticNode、availability、四方向 pair coordinates |
| `TEST-MAP-046` | `REQ-MAP-003..004` Ground Art、五层、依赖 hash closure 与像素独立 |
| `TEST-MAP-047` | `REQ-MAP-005..006` Walkability、Collision、Swept geometry |
| `TEST-MAP-048` | `REQ-MAP-007` directed edge formula、minimum heuristic、A*/Dijkstra、determinism、预算 |
| `TEST-MAP-049` | `REQ-MAP-008..009` Door、Interior、Region transition、恢复 |
| `TEST-MAP-050` | `REQ-MAP-010` 六状态 patch、Critical Route、rollback |
| `TEST-MAP-051` | `REQ-MAP-011` Camera、loading、fallback、debug overlay |
| `TEST-MAP-052` | `REQ-MAP-012` Required Node、parity、存档 round-trip |

## 12. 关联文档

- `DOC-FOUNDATION-005`：位置合法性与恢复不变量
- `DOC-FOUNDATION-006`：坐标、单位和 Seed 基元
- `DOC-MAP-001..011`：被本矩阵验收的 canonical MAP 规格
- `DOC-WORLD-004`：三个区域的地理语义
- `DOC-WORLD-009`：Ground Art 风格约束

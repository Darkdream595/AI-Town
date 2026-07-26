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
| Critical Route | 在 placement、damage 和 recovery 后仍必须保持可达的 node pair |
| Required Semantic Node | `reachability_policy=required` 的交互/转场节点 |
| Conditional Node | 只有明确 `availability_condition_id` 成立时要求可达的节点 |
| Parity Run | 用 PlayerCommand 与 NPC ActionProposal 驱动相同 MAP query 的成对测试 |
| Geometry Oracle | 独立于 A* 实现的精确 Polygon/Swept Disc 断言 |

## 4. 规则与不变量

- `RULE-MAP-045`：每个已启用 Required Semantic Node 必须从所属 Scene 的 Region Anchor 可达；豁免只允许使用已注册 Conditional Node 条件，不接受自由文本忽略。
- `RULE-MAP-046`：Critical Route Gate 对所有 must-remain-open route 必须返回 `success`，路径每段通过 Geometry Oracle，cost 不超过登记上限。
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

生产基线 Critical Routes：

四条路线统一使用 `agent_profile.humanoid.default`，并在无临时 actor 占位的静态规则快照上执行。

| Route ID | From | To | 最大 cost |
|---|---|---|---:|
| `critical_route.crown_creek.square_to_forest_gate` | `semantic_anchor.crown_creek.crown_square` | `semantic_exit.crown_creek.north_forest_gate` | 500000 |
| `critical_route.crown_creek.square_to_mine_road` | `semantic_anchor.crown_creek.crown_square` | `semantic_exit.crown_creek.west_mine_road` | 500000 |
| `critical_route.twilight_whisper.camp_to_south_path` | `semantic_anchor.twilight_whisper.oathkeeper_camp` | `semantic_exit.twilight_whisper_forest.south_path` | 500000 |
| `critical_route.silver_ash.shed_to_east_entry` | `semantic_anchor.silver_ash.entry_shed` | `semantic_exit.silver_ash_mine.east_entry` | 400000 |

审计接口：

```text
audit_semantic_reachability(map_snapshot, profile) -> NodeReachabilityReport
audit_critical_routes(map_snapshot, route_set, profile) -> CriticalRouteReport
run_player_npc_parity(fixture, revision) -> ParityReport
run_map_acceptance(package) -> MapAcceptanceReport
```

报告必须包含 map package hash、navigation revision、profile、seed、expanded nodes、失败 node/Collision ID 和脱敏 reason code。

## 6. 正常流程

1. Schema lint 验证五层 manifest、ID、Polygon 与 pair。
2. Unit/Property tests 覆盖坐标、几何、栅格、成本与 determinism。
3. 对八个 Acceptance Maps 运行 Contract/Integration tests。
4. 对三个 Region 和全部 Interior 运行 Semantic reachability。
5. 对四条 Critical Route 运行基线与每个动态状态 patch 后审计。
6. 使用玩家/NPC 两种来源执行相同移动、Door、Interior 和 Region transition。
7. Browser E2E 打开 debug overlays，人工只核对表现与结构报告一致。
8. 保存/恢复 MapSnapshot 后重跑关键报告并比较 hash/结果。

## 7. 边界情况

- Conditional Node 条件为 false 时报告 `not_applicable`，条件缺失则失败，不能算通过。
- Path Budget 耗尽报告 `inconclusive_budget_exceeded` 并使 Gate 失败，不等同 `unreachable`。
- 动态 actor 暂时占位不使静态 Critical Route 失败，但 Arrival/Queue capacity 测试必须覆盖等待。
- Ground Art stub 可以是纯色或随机噪声，但尺寸与 manifest 必须合法。
- 恢复时 actor 已落入新 Collision 必须保持 Recovery Barrier 并使用登记 safe recovery fixture。

## 8. 错误与降级

任一 Must route、Required Node、Parity 或像素独立断言失败时 Map Package 不得批准。测试 runner 异常或预算不足记为 failed/inconclusive，不允许人工改写为 pass；输出 exact fixture、seed、revision 和最小复现。

## 9. 安全与性能

随机 property tests 使用世界 Seed 派生的 `map_test` stream 并记录 sequence。每个 Region 全量 reachability 上限 100000 expanded nodes/route；测试不读取未登记路径、Secret 或用户文件。性能基线：Region A* P95 `<= 50 ms`、动态 Dirty rebuild P95 `<= 100 ms`，在发布基准机单线程规则执行测量。

## 10. 验收标准

- `REQ-MAP-001..012` 均至少被一个 `TEST-MAP-*` 覆盖。
- 八个 Acceptance Maps 全部通过，Critical Route 4/4、Required Node 100% 可达。
- 六种建筑/损坏状态、Door 状态、两组区域 Exit 与至少一个 Interior 全覆盖。
- 玩家/NPC parity mismatch 为 0，像素独立输出差异为 0。
- 保存/恢复前后 Map Package hash、合法位置、关键路径 status/cost 一致。
- Camera、loading fallback 和六种 debug overlay 通过 Browser E2E/Visual QA。

## 11. 测试追踪

| 测试 ID | 覆盖 |
|---|---|
| `TEST-MAP-045` | `REQ-MAP-001..002` 坐标、Bounds、Region/Exit topology |
| `TEST-MAP-046` | `REQ-MAP-003..004` Ground Art、五层与像素独立 |
| `TEST-MAP-047` | `REQ-MAP-005..006` Walkability、Collision、Swept geometry |
| `TEST-MAP-048` | `REQ-MAP-007` A* 最优性、成本、determinism、预算 |
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

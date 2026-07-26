---
doc_id: DOC-EVENT-007
title: Building 数据模型
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - building-aggregate
  - building-physical-state-machine
  - building-geometry-binding
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-008
  - DOC-MAP-010
  - DOC-ECON-011
requirements:
  - REQ-EVENT-007
last_updated: 2026-07-26
---

# Building 数据模型

## 1. 目的

`REQ-EVENT-007`：定义 Building aggregate 的身份、模板、物理状态机、施工阶段字段、Footprint/Collision/Entrance/Interior/Semantic 绑定与所有权引用边界，作为放置（`DOC-EVENT-008`）、施工（`DOC-EVENT-009`）、损毁修复（`DOC-EVENT-010`）与地图同步（`DOC-EVENT-011`）的共同数据基础。

## 2. 非目标

本文不定义放置校验、施工推进、损伤公式或 WorldDiff 格式（后续各文档 canonical）。几何对象的 Schema 与校验由 MAP 拥有（`DOC-MAP-004..008/010`）；PropertyDeed 与经济权益由 ECON 拥有（`DOC-ECON-011`）；本文只定义 Building 侧的引用与一致性要求。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Building | EVENT 拥有的动态建筑 aggregate，可建造、损坏、修复与拆除 |
| BuildingTemplate | Stable Catalog 项：外形、几何模板、阶段需求、升级路径与语义节点集 |
| Physical State | 建筑物理状态：`foundation/construction/intact/lightly_damaged/severely_damaged/ruins` |
| Construction Phase | 施工进度维度：`planning/clearing/foundation_work/structure_work/fitting/acceptance`（`DOC-EVENT-009`） |
| Geometry Binding | Building 对 MAP 各层对象 ID 的引用集合 |
| Damage Points | 非负整数损伤累计值，映射 Physical State 阈值（`DOC-EVENT-010`） |

## 4. 规则与不变量

- `RULE-EVENT-037`：每个 Building 有唯一 ULID `building_id` 与单调 `version`；`building_template_id` 必须指向注册 BuildingTemplate（`RULE-FOUNDATION-031..033`），模板决定几何模板、阶段需求与允许语义节点，不存在无模板建筑。
- `RULE-EVENT-038`：Physical State 六态固定且与 Construction Phase 正交受约：`foundation/construction` 仅在施工或重建期间出现且必须携带有效 Construction Phase；`intact/lightly_damaged/severely_damaged/ruins` 时 Construction Phase 为 `null`（升级施工除外，见 `RULE-EVENT-053`）；状态转换只允许 `DOC-EVENT-009/010` 声明的边。
- `RULE-EVENT-039`：Geometry Binding 必须完整：Footprint Polygon、按状态的 Collision 对象、`intact` 及以上可用状态至少一个 Entrance Node、可选 Interior Scene、Navigation Modifier 与 Semantic Nodes；几何真值存于 MAP snapshot，Building 只持对象 ID，两者按 `RULE-MAP-037` 同事务一致。
- `RULE-EVENT-040`：所有权经 ECON PropertyDeed（`subject_kind=building`）表达：EVENT 不写 ownership、余额或 Deed 状态，ECON 不写 Physical State、几何或阶段（`RULE-ECON-044` 的对偶边界）；Building 只保存 `property_subject_version` 供 ECON 校验陈旧引用。
- `RULE-EVENT-041`：每次 Physical State 变化必须在同一 World transaction 内提交：Building 状态、完整目标 geometry 的 NavigationPatch（`RULE-MAP-037/039`）、DomainEvent 与 WorldDiff entry（`DOC-EVENT-011`）；不存在只改字段不改几何的状态变化。
- `RULE-EVENT-042`：Interior Scene 与 Entrance/Door 语义遵循 `DOC-MAP-008`：进入受损建筑的许可由 Physical State 声明（`severely_damaged` 默认禁入、`ruins` 无 Interior）；拆除或转为 `ruins` 前必须完成室内 occupant 的 safe relocation（`RULE-MAP-040`）。

## 5. 数据与接口

`DES-EVENT-007`：Building aggregate：

```json
{
  "schema_version": 1,
  "building_id": "01K1AB2CD3EF4GH5JK6MNP7QS6",
  "building_template_id": "building.residence.timber_cottage",
  "scene_id": "region.crown_creek_town",
  "physical_state": "intact",
  "construction_phase": null,
  "damage_points": 0,
  "damage_threshold_profile_id": "damage.profile.timber_small",
  "geometry_binding": {
    "footprint_object_id": "01K1AB2CD3EF4GH5JK6MNP7QS7",
    "collision_object_ids": ["01K1AB2CD3EF4GH5JK6MNP7QS8"],
    "entrance_node_ids": ["01K1AB2CD3EF4GH5JK6MNP7QS9"],
    "interior_scene_id": "interior.timber_cottage_01",
    "navigation_modifier_ids": [],
    "semantic_node_ids": ["01K1AB2CD3EF4GH5JK6MNP7QSA"]
  },
  "property_subject_version": 3,
  "origin_command_id": "01K1AB2CD3EF4GH5JK6MNP7QSB",
  "version": 12
}
```

BuildingTemplate 关键字段：

```json
{
  "schema_version": 1,
  "building_template_id": "building.residence.timber_cottage",
  "footprint_template_id": "footprint.rect_5x4_tiles",
  "state_geometry": {
    "foundation": "geom.timber_cottage.foundation",
    "construction": "geom.timber_cottage.scaffold",
    "intact": "geom.timber_cottage.intact",
    "lightly_damaged": "geom.timber_cottage.intact",
    "severely_damaged": "geom.timber_cottage.damaged",
    "ruins": "geom.timber_cottage.ruins"
  },
  "interior_template_id": "interior.timber_cottage",
  "upgrade_to_template_ids": ["building.residence.stone_house"],
  "max_occupants": 4
}
```

接口：

```text
get_building(building_id) -> BuildingProjection
list_buildings(scene_id, physical_state | null) -> RevisionStampedProjection
assert_binding_consistency(building_id, map_snapshot_revision) -> ConsistencyReport
```

## 6. 正常流程

1. 放置命令（`DOC-EVENT-008`）通过校验后创建 Building：`physical_state=foundation`、`construction_phase=planning` 之后的推进态。
2. 施工（`DOC-EVENT-009`）推进 Construction Phase，验收提交 `construction → intact`。
3. 运行期损伤（`DOC-EVENT-010`）按 Damage Points 阈值降级状态。
4. 每次状态变化按 `RULE-EVENT-041` 原子提交四件套。
5. ECON 通过 Property Subject 引用建筑参与地契、租赁与赔偿。

## 7. 边界情况

- 模板缺少某状态几何映射（如无 `severely_damaged` 专用外形）：允许复用相邻状态几何 ID，但 Collision 语义仍按状态声明，构建期校验映射表完整。
- `ruins` 状态 Interior Scene 引用保留为历史字段但不可进入；室内物品处置由 `DOC-EVENT-010` 瓦砾/搜刮规则定义。
- Building 被拆除（显式命令）：aggregate 转 `ruins` 后经清理进入 terminal `removed` 投影标记，历史经 WorldDiff 保留，`building_id` 不复用。
- MAP 恢复审计发现 Binding 悬空（引用对象不存在）：保持 Recovery Barrier（`DOC-MAP-010` 语义），不自动重建几何。
- 同一 parcel 上重建：新 Building 新 ULID，旧 `ruins` 清理完成是放置前置条件（`DOC-EVENT-008`）。

## 8. 错误与降级

返回 `building_template_unknown`、`binding_incomplete`、`state_phase_mismatch`、`version_stale`、`occupant_relocation_required` 或 `geometry_inconsistent`。`assert_binding_consistency` 失败时冻结该 Building 的全部状态转换命令并发布诊断事件，直至审计修复流程完成。

## 9. 安全与性能

Building 投影按 `(scene_id, physical_state)` 建索引；单 Scene Building 上限 256。模板与几何模板构建期只读校验。室内 occupant 列表按访问级别过滤后才进入公开投影；镇长可见公共建筑完整状态，私宅内部状态仅对 owner 与治理程序可见（`DOC-ECON-011` 披露规则）。

## 10. 验收标准

- 六个 Physical State 各有 fixture 且几何、事件与状态同 Revision 可见（对应 `TEST-MAP-037` 消费方）。
- 状态/阶段非法组合注入全部拒绝。
- EVENT/ECON 边界：双向越权写入被架构测试拒绝。
- Binding 一致性审计在破坏注入下能检出全部悬空引用。
- 拆除与重建后历史可由 Event Log + WorldDiff 完整重放。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-019` | `RULE-EVENT-037..038` 模板约束与状态/阶段组合 |
| `TEST-EVENT-020` | `RULE-EVENT-039..040` Binding 完整性与所有权边界 |
| `TEST-EVENT-021` | `RULE-EVENT-041..042` 原子四件套与室内/禁入语义 |

## 12. 关联文档

- `DOC-EVENT-008`：放置校验与创建
- `DOC-EVENT-009`：施工阶段与升级
- `DOC-EVENT-010`：损伤阈值与修复
- `DOC-EVENT-011`：WorldDiff entry 结构
- `DOC-MAP-008`：门、入口与室内
- `DOC-ECON-011`：PropertyDeed 与 Property Subject

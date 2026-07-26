---
doc_id: DOC-EVENT-009
title: 施工阶段与升级
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - construction-phase-machine
  - construction-resource-labor
  - building-upgrade-paths
depends_on:
  - DOC-FOUNDATION-005
  - DOC-TIME-006
  - DOC-MAP-010
  - DOC-EVENT-007
  - DOC-EVENT-008
  - DOC-ECON-010
  - DOC-ECON-011
requirements:
  - REQ-EVENT-009
last_updated: 2026-07-26
---

# 施工阶段与升级

## 1. 目的

`REQ-EVENT-009`：定义六个施工阶段的推进条件、材料/劳力/工期结算边界、阶段几何同步、升级路径与施工中断恢复，使建造是可持久、可中断、可审计的长时间过程而非瞬时状态翻转。

## 2. 非目标

本文不定义材料配方与消耗结算细节（`DOC-ECON-010`）、预算与 Encumbrance（`DOC-ECON-011`）、`work` 长时间行动机制（`DOC-TIME-006`）或放置校验（`DOC-EVENT-008`）。劳动技能成长由 RESIDENT 域定义。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Construction Phase | `planning/clearing/foundation_work/structure_work/fitting/acceptance` 六阶段（对应规划、清理、地基、主体、设施、验收） |
| Phase Requirement | 模板对某阶段声明的材料、工种、累计劳动 game minutes 与前置 |
| Work Session | 一次已提交的 `build` 长时间行动片段，贡献劳动进度 |
| Material Delivery | 材料从 Inventory/仓储转入施工现场托管的原子转移 |
| Upgrade Path | 模板声明的 `A → B` 升级关系，复用施工阶段机 |
| Stalled | 施工因资源/劳力/事件中断超过阈值后的显式停滞标记 |

## 4. 规则与不变量

- `RULE-EVENT-049`：Construction Phase 顺序固定且不可跳过：`planning → clearing → foundation_work → structure_work → fitting → acceptance`；每阶段完成条件为该阶段 Phase Requirement 全部满足并原子提交阶段完成 DomainEvent；`acceptance` 完成即提交 `construction → intact`（`DOC-EVENT-007` 状态机）。
- `RULE-EVENT-050`：材料与资金只经 ECON 结算：材料经 Material Delivery 进入现场托管 Inventory（守恒，`RULE-FOUNDATION-018/019`），公共工程支出经 Appropriation/Encumbrance（`RULE-ECON-043`）；EVENT 记录需求满足度但不直接扣款、扣料。
- `RULE-EVENT-051`：劳动进度只由已提交 Work Session 累计：居民经 `build` ActionProposal（`DOC-AI-005`）或玩家命令产生长时间行动（`DOC-TIME-006`），Warm/Background 层按分钟推进；进度单位为 game minutes × 工种效率，模型不直接声明进度数值。
- `RULE-EVENT-052`：改变几何的阶段转换（`clearing` 完成、`foundation_work` 完成进入 foundation 外形、`structure_work` 完成进入 construction 脚手架外形、`acceptance` 完成进入 intact 外形）必须按 `RULE-EVENT-041` 同事务提交 `DOC-MAP-010` NavigationPatch（`RULE-MAP-037/039`）与 WorldDiff；纯进度累计不产生 patch。
- `RULE-EVENT-053`：升级必须使用模板注册 Upgrade Path：升级期间 Building `physical_state=construction` 且携带 Construction Phase，原建筑功能语义节点停用；不存在降级路径，价值折损只经损毁（`DOC-EVENT-010`）或 ECON 估值表达。
- `RULE-EVENT-054`：施工中断可恢复：材料断供、劳力缺失或事件破坏时进度与已交付材料保留；活跃 Reservation 按 TIME 到期释放；连续 4320 game minutes 无有效 Work Session 时标记 `stalled` 并通知 owner；恢复施工从既有进度继续，不重复消耗已结算投入。

## 5. 数据与接口

`DES-EVENT-009`：施工状态与阶段需求：

```json
{
  "schema_version": 1,
  "building_id": "01K1AB2CD3EF4GH5JK6MNP7QS6",
  "construction_phase": "structure_work",
  "phase_progress": {
    "labor_committed_game_minutes": 840,
    "labor_required_game_minutes": 1440,
    "materials": [
      {"item_template_id": "item.material.timber_plank", "delivered": 40, "required": 60},
      {"item_template_id": "item.material.iron_nail", "delivered": 200, "required": 200}
    ]
  },
  "site_inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QSE",
  "stalled": false,
  "last_work_session_game_time": 25890,
  "upgrade_from_building_id": null,
  "version": 21
}
```

BuildingTemplate 的阶段需求（节选）：

```json
{
  "phase_requirements": {
    "planning": {"labor_game_minutes": 120, "professions": ["carpenter"], "materials": []},
    "clearing": {"labor_game_minutes": 240, "professions": ["laborer"], "materials": []},
    "foundation_work": {"labor_game_minutes": 720, "professions": ["mason"], "materials": [{"item_template_id": "item.material.stone_block", "count": 30}]},
    "structure_work": {"labor_game_minutes": 1440, "professions": ["carpenter"], "materials": [{"item_template_id": "item.material.timber_plank", "count": 60}, {"item_template_id": "item.material.iron_nail", "count": 200}]},
    "fitting": {"labor_game_minutes": 720, "professions": ["carpenter", "smith"], "materials": [{"item_template_id": "item.material.furniture_kit", "count": 4}]},
    "acceptance": {"labor_game_minutes": 60, "professions": ["mayor_or_inspector"], "materials": []}
  }
}
```

接口：

```text
deliver_materials(command_id, building_id, expected_version, transfers) -> DeliveryResult
apply_work_session(committed_action_event) -> ProgressResult
complete_phase(command_id, building_id, expected_version) -> PhaseResult
start_upgrade(command_id, building_id, target_template_id, funding) -> UpgradeResult
```

## 6. 正常流程

1. 放置提交后进入 `planning`，owner 确认图样与预算。
2. 各阶段循环：交付材料 → 居民 Work Session 累计劳动 → Phase Requirement 满足后 `complete_phase`。
3. 涉及几何的阶段完成按 `RULE-EVENT-052` 原子提交外形与导航。
4. `acceptance` 由镇长或注册验收人完成，建筑转 `intact` 并激活语义节点。
5. 升级从 `start_upgrade` 重入阶段机（`planning` 起），完成后模板替换为目标模板。

## 7. 边界情况

- 阶段完成命令与最后一个 Work Session 并发：`complete_phase` 以 `expected_version` 校验，进度不足即拒绝，不部分完成。
- 现场托管材料被事件损毁：托管 Inventory 按 ECON 损失事件核减，需求满足度随之回退，已提交阶段不回退。
- 工人在施工中被征召/昏迷：Work Session 中断按 `DOC-TIME-006` 长行动中断语义结算已完成分钟，无惩罚性回退。
- 升级期间建筑遭损毁：升级施工转入 `DOC-EVENT-010` 损伤流程，恢复时从受损状态重估阶段需求，`upgrade_from_building_id` 链保留审计。
- `stalled` 公共工程超过 Appropriation 有效期：Encumbrance 到期释放（`RULE-ECON-043`），复工需新的拨款，进度仍保留。

## 8. 错误与降级

返回 `phase_order_violation`、`requirement_unmet`、`materials_insufficient`、`profession_missing`、`upgrade_path_unknown`、`building_state_invalid`、`version_stale` 或 `site_inventory_conflict`。ECON 不可用时材料交付与支出保持 Reservation 至有界恢复点后原子释放（`DOC-ECON-011` 错误语义），EVENT 不自行推进阶段。

## 9. 安全与性能

进度累计为追加式小事务，与 10 Hz Tick 解耦；`apply_work_session` 按已提交行动事件驱动，无轮询。阶段需求与效率表构建期只读。玩家与 AI 走同一 `deliver_materials/complete_phase` 命令路径，无隐藏加速通道；`admin` 加速必须走 `RULE-FOUNDATION-030` 审计。

## 10. 验收标准

- 六阶段顺序推进 fixture：跳段、越序、进度不足全部拒绝。
- 材料/资金/劳力三类投入均可从事件流对账且守恒。
- 涉及几何的阶段完成与导航同 Revision 可见。
- 升级完整链路（含中途损毁分支）可重放。
- 中断 30 游戏日后复工不重复消耗且 `stalled` 标记/解除事件完整。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-025` | `RULE-EVENT-049..050` 阶段机与 ECON 结算边界 |
| `TEST-EVENT-026` | `RULE-EVENT-051..052` Work Session 进度与几何同步 |
| `TEST-EVENT-027` | `RULE-EVENT-053..054` 升级路径与中断恢复 |

## 12. 关联文档

- `DOC-EVENT-007`：状态/阶段组合约束
- `DOC-EVENT-008`：放置与 parcel 前置
- `DOC-EVENT-010`：施工期损毁分支
- `DOC-MAP-010`：阶段几何的 NavigationPatch 审计
- `DOC-TIME-006`：长时间行动生命周期
- `DOC-ECON-010`：材料与制作消耗
- `DOC-ECON-011`：公共工程预算与六阶段结算

---
doc_id: DOC-RENDER-006
title: 建筑阶段与环境渲染
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - structure-stage-rendering
  - occlusion-and-shadows
  - world-diff-rendering
depends_on:
  - DOC-RENDER-003
  - DOC-MAP-006
requirements:
  - REQ-RENDER-006
last_updated: 2026-07-26
---

# 建筑阶段与环境渲染

## 1. 目的

定义 Building/WorldDiff 的可视阶段、遮挡、阴影和环境对象替换，保持动态建筑与地图规则同步。

## 2. 非目标

不定义建筑放置、预算、损坏数值或 navigation 更新的权威决策。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Structure Stage | `foundation`、`construction`、`complete`、`damaged`、`ruined`、`repairing`。 |
| Occluder | 位于实体前景的屋顶、树冠或悬崖 Sprite。 |
| Ground Shadow | 不参与碰撞的半透明脚下/建筑投影。 |

## 4. 规则与不变量

- `RULE-RENDER-016`：Structure Stage 仅由已提交 Building/WorldDiff event 变更，禁止本地预先改图。
- `RULE-RENDER-017`：建筑阴影位于 ground 之上、实体之下；Occluder 位于实体之上并使用确定性 depth。
- `RULE-RENDER-018`：破损/修复切换必须原子替换所有同一 `building_id` 的 visible pieces，不能留下旧 collision 的视觉暗示。

## 5. 数据与接口

`DES-RENDER-006`：Backend/Orchestrator 将 Event owner 的已提交 Building/WorldDiff 映射为 immutable `StructureRenderProjection`；它含 `building_id`、`stage`、`asset_id`、`footprint_version`、`shadow_asset_id`、`occluder_asset_ids` 与 affected slice IDs。RENDER 不直接读取 Event aggregate。

## 6. 正常流程

1. 收到 WorldDiff，按 `building_id` 查旧 display group。
2. 预载新 stage 所有 asset 后在单帧替换 group。
3. 重建仅受影响 slice 的 depth/occluder，触发环境音状态刷新。

## 7. 边界情况

实体被屋顶遮住时仅降低其上方 Occluder alpha 至 0.45；不隐藏建筑本体，也不改变碰撞或 visibility 规则。

## 8. 错误与降级

新 stage 资源缺失时保留上一确认 stage 并显示 `asset.fallback.structure_notice`，直到完整 Snapshot/Manifest 成功；不能伪造 complete。

## 9. 安全与性能

相同建筑实例的 pieces 批量更新；阴影用预烘焙纹理，禁止每帧动态 blur。

## 10. 验收标准

- `REQ-RENDER-006`：建造、损坏、修复的视觉 stage 与同 Revision 的 map diff 一致，遮挡稳定且无残片。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-006` | WorldDiff 回放、stage 原子替换、屋顶遮挡与截图比较。 |

## 12. 关联文档

- `DOC-RENDER-003`：地图合成
- `DOC-RENDER-010`：区域环境音
- 非 direct owner：Building/WorldDiff owner 经 Backend/Orchestrator render adapter 发布只读 stage projection。

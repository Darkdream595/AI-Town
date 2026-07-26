---
doc_id: DOC-RENDER-003
title: 五层地图合成管线
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - five-layer-map-compositing
  - deterministic-depth-sorting
  - map-slice-rendering
depends_on:
  - DOC-RENDER-001
  - DOC-MAP-001
  - DOC-MAP-003
  - DOC-MAP-006
requirements:
  - REQ-RENDER-003
last_updated: 2026-07-26
---

# 五层地图合成管线

## 1. 目的

将冻结的 Ground Art、Structure、Walkability、Collision、Semantic 五层地图合成为可见画面，同时保持后四层的规则所有权在 MAP。

## 2. 非目标

不生成正式地图图像；正式 map art 仅在后续 image generation 阶段按本规格产出。

## 3. 术语与定义

| 层 | 渲染责任 |
|---|---|
| Ground Art | 可见地表与装饰切片。 |
| Structure | 可见建筑、树冠、悬崖与前景遮挡。 |
| Walkability / Collision | 默认不可见，仅 QA overlay。 |
| Semantic | 默认不可见，仅交互标记与编辑 QA。 |

## 4. 规则与不变量

- `RULE-RENDER-007`：合成固定顺序为 Ground Art → 背景 Structure → entities/VFX → 前景 Structure → UI。
- `RULE-RENDER-008`：动态实体 depth=`floor(y_wu*16)+depth_bias`；同值以 stable `entity_id` 字典序打破平局。
- `RULE-RENDER-009`：Walkability、Collision、Semantic 不参与正常视觉遮挡，且不得由图像像素反推。

## 5. 数据与接口

`DES-RENDER-003`：每个 map slice 使用 `asset_id` 和 versioned transform：

```json
{"scene_id":"region.crown_creek_town","asset_id":"map.crown_creek.ground.slice_00_00","render":{"layer":"ground","origin_x_wu":0,"origin_y_wu":0,"depth_bias":0}}
```

## 6. 正常流程

1. 按相机 viewport 加一圈 slice preload Ground Art 与 Structure。
2. 读取 map contract 放置切片；实体按 `WorldPoint` 插值并执行确定性 depth sort。
3. 建筑/WorldDiff 到达后只替换受影响 slice 和遮挡对象。

## 7. 边界情况

跨 slice 的树冠/房顶必须作为一个 Structure object 带统一锚点；不能在边缘出现双重绘制或错误遮挡。

## 8. 错误与降级

单切片失败以中性 `asset.fallback.checkerboard` 覆盖对应可见区域，保留 QA overlay 与交互；禁止把它当作可行走判断。

## 9. 安全与性能

地图切片 lazy load、可见区外回收；一个 Scene 同时保留最多 3×3 可见切片环，避免全图纹理常驻。

## 10. 验收标准

- `REQ-RENDER-003`：相同 Snapshot 在两次加载中实体遮挡次序一致；五层 QA overlay 与 MAP contract 对齐。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-003` | Deterministic depth、slice 边界、building diff 与 overlay 截图回归。 |

## 12. 关联文档

- `DOC-RENDER-006`：结构与环境
- `DOC-RENDER-012`：性能与 Visual QA

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
| Slice extent | LOD0 每格 `1024×1024 wu`、每层 `1024×1024 px`；LOD1 每格 `2048×2048 wu`、每层 `1024×1024 px`。 |
| Preload ring | 当前 camera world-space visible bounds 所覆盖网格，四边各扩一格。 |

## 4. 规则与不变量

- `RULE-RENDER-007`：合成固定顺序为 Ground Art → 背景 Structure → entities/VFX → 前景 Structure → UI。
- `RULE-RENDER-008`：动态实体 depth=`floor(y_wu*16)+depth_bias`；同值以 stable `entity_id` 字典序打破平局。
- `RULE-RENDER-009`：Walkability、Collision、Semantic 不参与正常视觉遮挡，且不得由图像像素反推。支持 viewport 最大 `3840×2160 px`、camera zoom `0.75..2.0`；预载集合必须按 visible bounds 计算，不能固定为 3×3。

## 5. 数据与接口

`DES-RENDER-003`：每个 map slice 使用 `asset_id`、LOD 与明确 extent/versioned transform：

```json
{"scene_id":"region.crown_creek_town","asset_id":"map.crown_creek.ground.lod0.slice_00_00","render":{"layer":"ground","lod":0,"origin_x_wu":0,"origin_y_wu":0,"width_wu":1024,"height_wu":1024,"pixel_width":1024,"pixel_height":1024,"depth_bias":0}}
```

若 camera visible world bounds 为 `[left_wu,right_wu) × [top_wu,bottom_wu)`，当前 LOD 的 slice extent 为 `slice_width_wu × slice_height_wu`，则：

```text
visible_min_x = floor(left_wu / slice_width_wu)
visible_max_x = floor((right_wu - 1/16) / slice_width_wu)
visible_min_y = floor(top_wu / slice_height_wu)
visible_max_y = floor((bottom_wu - 1/16) / slice_height_wu)
preload_x = [visible_min_x - 1, visible_max_x + 1]
preload_y = [visible_min_y - 1, visible_max_y + 1]
```

visible bounds 由 `viewport_px / camera_zoom` 转成 world units，并与 Scene bounds 相交；负索引或超出 Scene bounds 的格不请求。

## 6. 正常流程

1. 由 viewport、camera zoom 与 Scene bounds 计算 visible slice bounds，再按公式扩一圈 preload Ground Art 与 Structure。
2. 读取 map contract 放置切片；实体按 `WorldPoint` 插值并执行确定性 depth sort。
3. 若 LOD0 的 preload grid 超过 20 个 grid cells 或 Ground Art + Structure 预计 GPU allocation 超过 160 MiB，切到 LOD1 后重新计算；支持范围内 LOD1 仍超预算视为 contract/build failure，不能缩小 preload ring。
4. 建筑/WorldDiff 到达后只替换受影响 slice 和遮挡对象。

## 7. 边界情况

跨 slice 的树冠/房顶必须作为一个 Structure object 带统一锚点；不能在边缘出现双重绘制或错误遮挡。

## 8. 错误与降级

单切片失败以中性 `asset.fallback.checkerboard` 覆盖对应可见区域，保留 QA overlay 与交互；禁止把它当作可行走判断。

## 9. 安全与性能

地图切片 lazy load、可见区外回收。每个 preload grid cell 最多包含一张 Ground Art 与一张 Structure texture；同时驻留最多 20 个 grid cells、地图切片预计 GPU allocation 最多 160 MiB，剩余纹理预算留给 Sprite、UI、VFX 与 fallback。LOD 只改变视觉采样密度，不改变 `WorldPoint`、depth 或 MAP layer。

## 10. 验收标准

- `REQ-RENDER-003`：相同 Snapshot 在两次加载中实体遮挡次序一致；720p/1080p/最高 4K fullscreen 与 zoom 边界均无 slice 空洞，五层 QA overlay 与 MAP contract 对齐。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-003` | Property test 覆盖 viewport/zoom/Scene edge 的 visible+ring 公式、LOD/20-cell/160-MiB budget，以及 deterministic depth、building diff 与 overlay 截图回归。 |

## 12. 关联文档

- `DOC-RENDER-006`：结构与环境
- `DOC-RENDER-012`：性能与 Visual QA

---
doc_id: DOC-MAP-011
title: 相机与地图边界
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - camera-clamping
  - map-loading-readiness
  - navigation-debug-overlays
depends_on:
  - DOC-FOUNDATION-006
  - DOC-MAP-001
  - DOC-MAP-004
  - DOC-MAP-009
  - DOC-MAP-010
requirements:
  - REQ-MAP-011
last_updated: 2026-07-26
---

# 相机与地图边界

## 1. 目的

`REQ-MAP-011`：定义浏览器 Camera 对 Scene Bounds 的 clamp、缩放、Map loading readiness、视觉 fallback 和导航 debug overlays，且不让相机或资源状态改变权威位置。

## 2. 非目标

本文不拥有玩家输入映射、HUD 布局、Fullscreen API 授权或 Phaser Scene 具体类；只提供 MAP 边界与加载投影契约。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Camera Center | Rule Coordinate 中的画面中心 |
| World Viewport | `canvas_px / zoom` 换算出的可见 `wu` 尺寸 |
| Rule Ready | Structure geometry、Walkability、Collision、Semantic 和导航索引均可查询 |
| Visual Ready | Ground Art 与必要 Structure texture 已加载 |
| Degraded Visual Ready | 规则可用但视觉资源使用登记 fallback |
| Debug Overlay | 只读投影的开发检查层，不参与规则 |

## 4. 规则与不变量

- `RULE-MAP-041`：Camera center 只影响渲染，不能 clamp、传送或重写 actor WorldPoint。
- `RULE-MAP-042`：zoom 范围固定 `0.75..2.0`、默认 `1.0`；DPR 和 CSS scaling 不改变 `wu`，clamp 使用 World Viewport 计算。
- `RULE-MAP-043`：Scene 只有 Rule Ready 后才能接受移动/转场；Visual Ready 失败可进入 Degraded Visual Ready，但规则层失败必须阻断操作。
- `RULE-MAP-044`：Debug Overlay 只消费指定 revision 的只读数据并显示 revision；不得写 layer、修改 Collision 或作为生产授权依据。

## 5. 数据与接口

`DES-MAP-011`：令 `view_width_wu = canvas_width_px / zoom`，`half_w = view_width_wu / 2`（高度同理）：

```text
if view_width_wu <= scene_width_wu:
    camera_x = clamp(target_x, half_w, scene_width_wu - half_w)
else:
    camera_x = scene_width_wu / 2
```

Y 轴使用同一公式。clamp 后允许画布外 letterbox，但不拉伸规则坐标。

Map load states：

```text
unloaded -> rule_loading -> rule_ready
rule_ready -> visual_loading -> visual_ready
visual_loading -> degraded_visual_ready
任一规则错误 -> rule_failed
```

```json
{
  "scene_id": "region.crown_creek_town",
  "map_package_version": 1,
  "navigation_revision": 84,
  "rule_state": "ready",
  "visual_state": "degraded",
  "fallback_asset_id": "ground_art.fallback.neutral_grid.v1"
}
```

Debug Overlay 固定通道：

| Overlay | 表现 |
|---|---|
| Walkability | 半透明绿，显示 surface ID/terrain cost |
| Collision | 红色 ring 与 winding arrow |
| Navigation Grid | cell 状态、edge 与 expanded nodes |
| Semantic | node/approach/arrival/queue 与 pair link |
| Dynamic | Dirty Bounds、modifier、source revision |
| Path | waypoint、Swept Disc、PathResult revision |

## 6. 正常流程

1. Scene 转场准备阶段加载并验证规则层。
2. Rule Ready 后 Authority 可提交转场，客户端创建 Camera。
3. 客户端并行加载 Ground Art/Structure texture；失败则显示 fallback。
4. 每帧把 actor target point 经 clamp 公式转成 Camera center。
5. resize、DPR、zoom 变化时重算 World Viewport，不修改 actor position。
6. 开发者开启 overlay 时，从当前 MapSnapshot/PathResult 生成只读绘制命令。

## 7. 边界情况

- viewport 大于 Scene 时 Camera 固定 Scene 中心，两侧 letterbox 对称。
- actor 位于 Scene 边缘时 Camera clamp，actor 可以偏离画面中心但位置不变。
- 浏览器从 `1920×1080` 缩至 `1280×720` 时只改变可见范围和 UI，不重建规则层。
- Visual Tile 晚到时替换 fallback，不触发 navigation revision。
- overlay revision 落后当前 World Revision 时显示 `STALE` 并停止用于当前路径解释。
- Interior 小于 viewport 时同样居中，不创建虚构可走边缘。

## 8. 错误与降级

规则层失败显示不可操作错误并保留 source Scene；Ground Art/texture 失败使用登记 fallback。Camera 参数非法时恢复 zoom `1.0` 和 Scene 中心；不以 actor teleport 纠正画面。

## 9. 安全与性能

Active Scene Ground Art 只保留 Camera 周围 3×3 Logical Tile，未压缩 RGBA 预算 `<= 64 MiB`；规则层查询不等待 GPU。Debug Overlay 默认关闭，开启后每帧绘制顶点上限 20000，超限抽样 cell 但不省略关键路径/Collision hit。

## 10. 验收标准

- 720p、1080p、zoom 两端和 viewport 大于 Scene 的 clamp 结果精确。
- Camera/resize/DPR 变化前后 actor WorldPoint byte-equivalent。
- Rule failure 阻断操作，visual failure 保持规则可操作并显示 fallback。
- 六种 overlay 能显示 ID、revision 和几何边界，且关闭后无规则差异。
- Region 与 Interior 边缘不显示越界可玩区域。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-041` | clamp 公式覆盖四边、四角、小 Scene 与 zoom 极值 |
| `TEST-MAP-042` | resize/DPR/Camera 不改变 actor 或导航状态 |
| `TEST-MAP-043` | rule/visual load matrix 与 fallback |
| `TEST-MAP-044` | debug overlay revision、通道和只读性 |

## 12. 关联文档

- `DOC-MAP-001`：Scene Bounds 与 `wu`
- `DOC-MAP-004`：五层加载顺序
- `DOC-MAP-009`：目标 Scene 预热
- `DOC-MAP-010`：Dirty Bounds overlay
- `DOC-MAP-012`：Camera/Map loading acceptance

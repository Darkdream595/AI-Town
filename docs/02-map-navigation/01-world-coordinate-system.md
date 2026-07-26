---
doc_id: DOC-MAP-001
title: 世界坐标系
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - map-coordinate-types
  - scene-bounds
  - spatial-quantization
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
requirements:
  - REQ-MAP-001
last_updated: 2026-07-26
---

# 世界坐标系

## 1. 目的

`REQ-MAP-001`：为区域、独立室内、Polygon、导航网格和相机定义唯一可实现的坐标契约，使移动、碰撞、存档和渲染对同一点得到一致结果。

## 2. 非目标

本文不定义区域叙事身份、地图画面内容、Pathfinding 算法或跨 Scene 转场；这些分别由 `DOC-WORLD-004`、`DOC-MAP-003`、`DOC-MAP-007` 和 `DOC-MAP-009` 负责。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Scene Bounds | Scene 的半开矩形 `[0,width_wu) × [0,height_wu)` |
| Rule Coordinate | 以 `wu` 表示、参与规则计算的坐标 |
| Design Pixel | 1× 设计稿像素；依据 `RULE-FOUNDATION-040`，`1 design pixel = 1 wu` |
| Quantized Point | 坐标分量量化至 `1/16 wu` 的持久化点 |
| Spatial Epsilon | MAP 几何谓词统一容差 `1/32 wu`，仅用于分类，不改变持久值 |
| Agent Disc | 以位置为圆心、`radius_wu` 为半径的站立占位模型 |
| Scene ID | 固定 Region 使用 Stable Catalog ID；运行时 Interior instance 使用 ULID，并另带 Stable Catalog `scene_template_id` |

## 4. 规则与不变量

- `RULE-MAP-001`：所有 2D Scene 采用左上原点，`+X` 向东/右，`+Y` 向南/下；方向角沿用 `RULE-FOUNDATION-039`，不得建立第二套轴向。
- `RULE-MAP-002`：Scene Bounds 为半开区间；任何可持久位置必须满足 `0 <= x_wu < width_wu` 且 `0 <= y_wu < height_wu`，并满足 `RULE-FOUNDATION-017`。
- `RULE-MAP-003`：协议入口拒绝 NaN、Infinity、负半径和绝对值超过 `1,000,000 wu` 的坐标；提交前先量化到 `1/16 wu`，几何分类使用 `1/32 wu` epsilon。
- `RULE-MAP-004`：不同 `scene_id` 的点不得直接相减、测距或插值；区域、室内和对象 Local frame 之间只能通过版本化 Transform 或 Semantic Exit 转换。

## 5. 数据与接口

`DES-MAP-001`：MAP 提供不可变 value objects 和显式边界检查：

```json
{
  "scene_id": "region.crown_creek_town",
  "bounds": {
    "width_wu": 4096,
    "height_wu": 4096
  },
  "position": {
    "x_wu": 1024.0,
    "y_wu": 768.0
  },
  "agent_radius_wu": 10.0,
  "coordinate_schema_version": 1
}
```

接口：

```text
quantize(point, quantum_wu = 0.0625) -> QuantizedPoint
contains(bounds, point) -> bool
to_world(local_point, transform_version) -> WorldPoint | TransformError
classify_position(scene_id, point, radius_wu, navigation_revision) -> PositionLegality
```

Transform 使用平移、顺时针旋转和统一正比例缩放；首版 Scene frame 的缩放固定为 `1.0`，对象 frame 可旋转但禁止 shear 和非均匀缩放。
Region Scene 的 `scene_id` 例如 `region.crown_creek_town`；动态 Interior 的 `scene_id` 是 26 字符 Runtime ULID，内容类型由 `scene_template_id`（例如 `interior.house.small.floor_0`）表达，禁止把 ULID 拼入 dotted Stable Catalog ID。

## 6. 正常流程

1. 协议层验证数值有限、单位后缀和 `scene_id`。
2. MAP registry 读取 Scene Bounds 与 coordinate schema version。
3. 坐标量化后执行 bounds、Walkability 和 Collision 检查。
4. 合法位置随命令事务提交；渲染端以同一 Rule Coordinate 计算画面坐标。
5. 存档恢复时重新执行位置合法性 audit，成功后才解除 Recovery Barrier。

## 7. 边界情况

- 恰好位于 `x_wu = width_wu` 或 `y_wu = height_wu` 的点在 Scene 外。
- 量化把点推至半开上界时判为越界，不向内静默夹取。
- Agent Disc 即使圆心在 bounds 内，只要圆盘越界仍为非法站立。
- Local frame 版本缺失或已退休时停止转换，不能按相同数值猜测 WorldPoint。
- `RULE-FOUNDATION-039` 未定义的方向语义不参与实现判断；所有几何只使用其明确轴向与角度。

## 8. 错误与降级

未知 Scene 返回 `unknown_scene`；Transform 缺失返回 `transform_version_unavailable`；非法数字返回 `invalid_coordinate`; 量化后越界返回 `out_of_bounds`。所有错误均无位置副作用，客户端可保留最后已提交位置并请求权威 Snapshot。

## 9. 安全与性能

坐标和 Polygon 顶点数在协议边界限幅，防止异常数值放大索引与几何计算。Scene Bounds、Transform 和量化参数按 manifest version 缓存为不可变对象；规则端不读取图片尺寸推导边界。

## 10. 验收标准

- 三个区域和任一室内 Scene 使用相同 `wu`、量化与轴向规则。
- 边界内外、NaN/Infinity、负半径和跨 Scene 测距均得到确定结果。
- 存档坐标 round-trip 后逐分量误差不超过 `1/16 wu`。
- 规则缩放不随浏览器 DPR、Camera zoom 或资源分辨率变化。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-001` | 四条边及四个角的半开 Bounds 分类一致 |
| `TEST-MAP-002` | 有限数、限幅、量化和 epsilon property test |
| `TEST-MAP-003` | LocalPoint 在已知 Transform 下往返误差不超过 `1/16 wu` |
| `TEST-MAP-004` | 跨 Scene 直接测距被拒绝，转场只能使用 Semantic Exit |

## 12. 关联文档

- `DOC-FOUNDATION-005`：位置合法性跨系统不变量
- `DOC-FOUNDATION-006`：全局坐标、方向和单位基元
- `DOC-MAP-005`：Walkability 判定
- `DOC-MAP-006`：Collision 几何谓词
- `DOC-MAP-011`：相机与 Scene Bounds

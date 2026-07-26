---
doc_id: DOC-MAP-004
title: 五层地图结构
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - five-layer-map-contract
  - map-package-manifest
  - layer-authority-boundaries
depends_on:
  - DOC-FOUNDATION-005
  - DOC-MAP-001
  - DOC-MAP-003
requirements:
  - REQ-MAP-004
last_updated: 2026-07-26
---

# 五层地图结构

## 1. 目的

`REQ-MAP-004`：定义 `Ground Art`、`Structure`、`Walkability`、`Collision`、`Semantic` 五层的内容、权威性、加载顺序和版本契约，使视觉变化与规则变化可独立验证。

## 2. 非目标

本文不定义 Building 生命周期、资源许可证、渲染深度排序或各类 Semantic Node 的业务效果；只定义地图包如何引用 owner 提供的数据。

## 3. 术语与定义

| 层 | 内容 | 是否规则权威 |
|---|---|---|
| `Ground Art` | 不变地表 Plate/Tile | 否，仅视觉 |
| `Structure` | 房屋、桥、树、矿石、废墟等实例及表现引用 | 几何引用是，图片不是 |
| `Walkability` | 合法站立面和结构化 terrain/road tags | 是 |
| `Collision` | 阻挡移动/占位的 Polygon 或注册 shape | 是 |
| `Semantic` | Exit、Entrance、门、柜台、床、工作台、矿点、触发区 | 是 |
| Map Package | 一个 Scene 的五层 manifest、版本和内容 hash 集合 | 是 |

## 4. 规则与不变量

- `RULE-MAP-013`：五层必须分别登记、分别 hash；缺少任一规则层时 Scene 不得进入可操作状态。
- `RULE-MAP-014`：规则只读取 Walkability、Collision、Semantic 和 Structure 的结构化几何引用；Ground Art、texture alpha、颜色和阴影永不成为规则输入。
- `RULE-MAP-015`：Structure instance 的业务状态由其 canonical owner 提供，MAP 只消费已提交的 geometry state；Footprint、Collision 与 sprite bounds 可以不同且不得互相推导。
- `RULE-MAP-016`：Map Package 发布必须满足依赖闭包：Semantic 引用存在的 Scene/Structure，Collision 引用存在的 geometry source，所有规则坐标位于 Scene Bounds。

## 5. 数据与接口

`DES-MAP-004`：Map Package manifest：

```json
{
  "scene_id": "region.crown_creek_town",
  "map_package_version": 1,
  "coordinate_schema_version": 1,
  "layers": [
    {"kind": "ground_art", "version": 1, "content_hash": "sha256:7f2e5786c009981756fdc96e7f6996cf385ca1ee245016ed1ffce9daa8c5526a"},
    {"kind": "structure", "version": 1, "content_hash": "sha256:520cdb563bf80b193aab6aad62781a9647c75dbf76748117299c7dac0ae63a87"},
    {"kind": "walkability", "version": 1, "content_hash": "sha256:6118511e03d7a12fc61fcb30d0e9a46a0d440288bba2f891460d3206f4a6c2ab"},
    {"kind": "collision", "version": 1, "content_hash": "sha256:9550e70a7c3619220570a6ed8b82684edbfc045b698027748b43afa2cadd6bae"},
    {"kind": "semantic", "version": 1, "content_hash": "sha256:3784070fe3e7e3de5f0ec08eadfa10acbaa0f543916b1ab2c68f371924ff7db3"}
  ],
  "critical_route_set_id": "critical_routes.crown_creek.v1"
}
```

| 消费者 | 可读层 | 禁止依赖 |
|---|---|---|
| Authority Navigation | Structure geometry、Walkability、Collision、Semantic | Ground Art 像素、render bounds |
| Phaser Renderer | 五层投影与已提交状态 | 自行决定合法位置 |
| AI Context Builder | 已授权 Semantic/route read model | 图片、隐藏碰撞、未发现节点 |
| Construction/Event | placement query、NavigationPatch 接口 | 直接改缓存或图片推断 Polygon |

服务接口：

```text
load_map_package(scene_id, expected_version) -> MapSnapshot | MapLoadError
validate_layer_closure(package) -> LayerValidationResult
project_render_manifest(map_snapshot) -> RenderMapProjection
```

## 6. 正常流程

1. 校验 manifest schema、五个唯一 layer kind 与 hash。
2. 加载坐标和 Scene Bounds。
3. 依次加载 Structure geometry、Walkability、Collision、Semantic。
4. 构建空间索引、导航网格和关键路径结果。
5. 规则快照就绪后发布 `MapSnapshotReady` read model。
6. Ground Art 可并行或延迟加载；缺图时使用视觉 fallback，不改变规则快照。

## 7. 边界情况

- Ground Art version 单独变化时无需重建导航，但仍产生新的 render manifest hash。
- Structure sprite 更换而 geometry hash 不变时只刷新表现。
- Structure geometry 变化必须通过 `DOC-MAP-010` 的原子 NavigationPatch。
- Semantic Node 可以位于 Structure 内部 Scene，但必须引用明确 `scene_id`，不能依赖 sprite 层级。
- 两层文件名相同不构成关联，只有 manifest 中的 kind、version 和 hash 有效。

## 8. 错误与降级

规则层 hash 错误、引用悬空或版本不兼容时隔离 Scene 并保持 Recovery Barrier。Ground Art 缺失或损坏时使用 `ground_art.fallback.neutral_grid.v1`，保留移动能力并显示非规则性诊断提示。

## 9. 安全与性能

每层设置条目数、Polygon 顶点数和解压后大小上限；hash 在解析前验证。服务端不加载大纹理，客户端按 Ground Art Tile 流式读取。MapSnapshot 使用不可变结构，变更采用 copy-on-write dirty partitions。

## 10. 验收标准

- 每个 Scene 恰好登记五种 layer kind，hash 与 version 完整。
- 关闭 Ground Art 后，所有规则测试结果逐项相同。
- 修改图片颜色、alpha 或尺寸不会改变 Walkability/Collision 输出。
- 规则层悬空引用阻止 Scene ready，视觉层缺失仅触发可见 fallback。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-013` | 五层唯一性、顺序无关解析和依赖闭包 |
| `TEST-MAP-014` | Ground Art 任意像素变换不改变导航结果 |
| `TEST-MAP-015` | Structure sprite bounds 与 Footprint/Collision 独立 |
| `TEST-MAP-016` | 规则层失败阻断 ready，视觉层失败正确降级 |

## 12. 关联文档

- `DOC-MAP-003`：Ground Art 生成与验收
- `DOC-MAP-005`：Walkability 数据
- `DOC-MAP-006`：Collision 数据
- `DOC-MAP-010`：动态 layer 更新
- `DOC-MAP-011`：Map loading

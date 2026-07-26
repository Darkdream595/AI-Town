---
doc_id: DOC-MAP-003
title: AI 地图生成规格
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - ground-art-generation-contract
  - generated-map-image-acceptance
  - ground-art-seams
depends_on:
  - DOC-FOUNDATION-006
  - DOC-WORLD-009
  - DOC-MAP-001
  - DOC-MAP-002
requirements:
  - REQ-MAP-003
last_updated: 2026-07-26
---

# AI 地图生成规格

## 1. 目的

`REQ-MAP-003`：定义 Gate G5 后生成 `Ground Art` 的输入、分片、负面约束、接缝与验收，使图像可稳定合成但永不承担通行、碰撞或语义权威。

## 2. 非目标

本文不生成正式图片，不指定特定厂商模型，不从图像提取道路或 Collision，也不生产角色、UI、文字、可拆建筑、Structure sprite 或 Semantic data。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Ground Art Plate | 与一个 Scene Bounds 对齐的纯视觉底图 |
| Logical Tile | Ground Art 的 `1024 × 1024` 目标分片 |
| Bleed | 每边额外 `64 px` 的生成上下文，合成时裁去 |
| Seam Band | 分片边界两侧各 `32 px` 的比较带 |
| Prompt Manifest | 可重放的 prompt、negative prompt、seed、模型与参数记录 |
| Image Acceptance | 不涉及规则推断的视觉、尺寸、内容与接缝检查 |

## 4. 规则与不变量

- `RULE-MAP-009`：Ground Art 只提供外观；Walkability、Collision、Entrance、道路语义和资源点必须来自独立结构化 manifest。
- `RULE-MAP-010`：生成图必须正交 90° 俯视、统一 `1 px = 1 wu` 的 1× 设计比例；禁止 isometric、透视地平线和相机倾斜。
- `RULE-MAP-011`：Ground Art 禁止角色、动物、文字、标签、UI、门扇状态、可拆建筑、桥梁、树木主干、矿石实体和任何会随世界状态改变的对象。
- `RULE-MAP-012`：三个 Region 使用同一 palette catalog version、暖光/冷影逻辑、材质词表与采样参数，并分别使用 `DOC-WORLD-009` 指定的 Region palette family；不得直接模仿特定在世艺术家。

## 5. 数据与接口

`DES-MAP-003`：每个 Region 按 `1024 wu` 网格切分。每个 Logical Tile 生成 `1152 × 1152 px`（中央 `1024` 加四周 `64` Bleed），合成时只取中央区域，因此最终像素尺寸严格等于 Scene Bounds。

```json
{
  "ground_art_id": "ground_art.crown_creek.v1",
  "scene_id": "region.crown_creek_town",
  "canvas_px": {"width": 4096, "height": 4096},
  "logical_tile_px": 1024,
  "bleed_px": 64,
  "palette_catalog_version": "world_palette.v1",
  "palette_family_id": "palette.crown_creek",
  "projection": "orthographic_top_down_90",
  "prompt_manifest_version": 1,
  "navigation_source": false
}
```

正向 prompt 固定包含：中世纪剑与魔法、日式西幻手绘绘本气质、正交俯视、清晰地表材质区、跨区域一致比例、共享暖光/冷影逻辑、对应 Region palette family、地图边缘可延展。负向 prompt 固定包含：人物、动物、文字、标记、UI、isometric、perspective、可拆建筑、桥、树干、矿石实体、强制阴影遮挡道路、签名和水印。

图像与规则的对齐仅通过同尺寸 `scene_id + art_version` manifest；图片不能反向生成规则数据。

## 6. 正常流程

1. 在 G5 后冻结 Scene Bounds、palette version 和结构化层草案。
2. 为每个 Tile 生成 Prompt Manifest 与相邻 Tile 上下文摘要。
3. 使用固定 seed 派生流生成带 Bleed 的 Tile。
4. 执行投影、禁物、尺寸、色板和 Seam Band 检查。
5. 裁去 Bleed，按整数坐标合成 Ground Art Plate。
6. 美术人员审阅画面；MAP 审阅者只确认图像未被当作规则来源。

## 7. 边界情况

- 水面、悬崖和道路可画在 Ground Art，但其通行含义仍由结构化层定义。
- 不可拆的纯地形轮廓可进入底图；任何可能损坏、修复或替换的对象必须在 Structure 层。
- 生成器无法严格输出尺寸时，先等比生成再用高质量重采样到目标 Tile；不得改变 Scene Bounds。
- 接缝修复只能修改像素，不得移动 Polygon、Entrance 或 Semantic Node。
- 画面暗部不得掩盖道路边缘到无法人工审阅，但“看似道路”不自动成为 Road。

## 8. 错误与降级

禁物检测命中、尺寸错误、投影错误或接缝超限时拒绝该 Tile 并用相同 manifest 派生新 seed；最多三次后转人工修绘。某 Tile 缺失时客户端使用登记的中性地表 fallback，规则层仍可加载。

## 9. 安全与性能

Prompt Manifest 不包含 Secret、用户目录或受保护文件内容。生成工具只接收规格化文本与目标 Tile 上下文。运行时按 `1024 px` Tile 流式加载，Ground Art 不进入服务器碰撞内存。

## 10. 验收标准

- 最终 Plate 尺寸逐像素等于对应 Scene Bounds，Tile 无重叠错位。
- 画面满足正交俯视和统一比例；三个 Region 的 palette catalog version 一致，family 分别为 `palette.crown_creek`、`palette.twilight_forest`、`palette.silver_ash`。
- 禁止对象、文字、水印和 UI 检测为零命中，并经人工 spot check。
- Seam Band 的每通道平均绝对差不超过 `12/255`，P95 不超过 `28/255`；超限接缝全部修复。
- manifest 明确 `navigation_source: false`，构建产物不存在像素到 Walkability/Collision 的生成步骤。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-009` | Region Plate、Tile、Bleed 和裁切尺寸精确 |
| `TEST-MAP-010` | Prompt/negative prompt 含全部固定约束且可重放 |
| `TEST-MAP-011` | Seam Band 阈值、投影、palette catalog/family 验收 |
| `TEST-MAP-012` | 构建链无 image-to-navigation 或 pixel-derived collision 输入 |

## 12. 关联文档

- `DOC-WORLD-009`：日式西幻手绘绘本视觉方向
- `DOC-MAP-001`：Scene 尺寸与比例
- `DOC-MAP-004`：Ground Art 与其他四层的分离
- `DOC-MAP-012`：图像与规则分离验收

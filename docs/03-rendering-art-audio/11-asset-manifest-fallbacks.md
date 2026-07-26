---
doc_id: DOC-RENDER-011
title: Asset Manifest 与降级资源
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - asset-manifest
  - asset-licensing-and-hashes
  - fallback-resource-policy
depends_on:
  - DOC-FOUNDATION-006
  - DOC-RENDER-004
  - DOC-RENDER-010
requirements:
  - REQ-RENDER-011
last_updated: 2026-07-26
---

# Asset Manifest 与降级资源

## 1. 目的

定义所有 Texture、Atlas、UI、VFX、Audio 和后续正式地图资源的可审计 Manifest、加载组与确定 fallback。

## 2. 非目标

不在本任务生成正式地图或任意资产；image generation 阶段必须按本 Manifest 的 ID 和分层接口生产。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Asset Manifest | 构建期验证、运行时只读的 asset ID 到文件/metadata 映射。 |
| Required group | Scene Load Gate 必须成功的资源组。 |
| Optional group | 可延迟或失败降级的资源组。 |
| Fallback chain | 指定 asset → type fallback → global fallback 的确定链。 |

## 4. 规则与不变量

- `RULE-RENDER-031`：每个 asset ID 符合 Stable Catalog ID grammar，全局唯一且有 type、hash、license metadata、fallback ID。
- `RULE-RENDER-032`：Required group 不可缺少 fallback；未知或 hash 不匹配资源不得被静默加载。
- `RULE-RENDER-033`：地图资源分列 `ground_art` 与 `structure`；Manifest 不承载 Walkability/Collision/Semantic 规则数据。

## 5. 数据与接口

`DES-RENDER-011`：

```json
{"asset_id":"map.crown_creek.ground.slice_00_00","type":"image","load_group":"region.crown_creek.required","sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","license_id":"license.project_original_001","fallback_asset_id":"asset.fallback.checkerboard"}
```

构建工具以资源实际字节计算 SHA-256；上例仅用于说明字段格式，发布 Manifest 必须写入对应资源的实际 hash。

## 6. 正常流程

1. 构建期解析 Manifest，检查 ID、hash、license、文件、fallback DAG 无环。
2. PreloadScene 先加载 global fallback，再加载当前 required group，optional group 随需加载。
3. Runtime 按失败 type 走 fallback chain，并上报 asset/scene/revision。

## 7. 边界情况

同一 asset 在两个 group 出现必须字节 hash 一致；版本升级时旧存档仅引用 stable ID，不能引用旧文件路径。

## 8. 错误与降级

Manifest 不可解析、必需 fallback 缺失或许可证字段缺失时构建失败；运行时单资源失败使用已登记 fallback，禁止 URL 热链或未登记临时素材。

## 9. 安全与性能

hash 防止打包错位；lazy loading 仅载入当前 Scene 所需组；纹理/音频量由 `DOC-RENDER-012` 预算强制限制。

## 10. 验收标准

- `REQ-RENDER-011`：所有发布 asset 可解析、哈希匹配、许可证可追溯、fallback 无环，且缺失资源仍能完成核心操作。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-011` | Manifest schema/hash/license/fallback DAG lint 与故障注入加载测试。 |

## 12. 关联文档

- `DOC-RENDER-002`：Scene Load Gate
- `DOC-RENDER-012`：预算与 QA

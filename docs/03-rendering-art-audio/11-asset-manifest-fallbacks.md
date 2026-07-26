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
| `AssetManifestEntry` | 一个 asset 的路径、hash、类型、加载组、许可引用和 fallback。 |
| `LicenseRecord` | `license_id` 指向的可机读来源、作者、条款、取得时间与许可证正文证据。 |

## 4. 规则与不变量

- `RULE-RENDER-031`：每个 asset ID 符合 Stable Catalog ID grammar，全局唯一且有 type、规范化相对 path、实际字节 SHA-256、byte length、license ID、fallback ID；每个 license ID 必须解析到唯一、完整且允许发布的 `LicenseRecord`。
- `RULE-RENDER-032`：Required group 不可缺少 fallback；未知或 hash 不匹配资源不得被静默加载。
- `RULE-RENDER-033`：地图资源分列 `ground_art` 与 `structure`；Manifest 不承载 Walkability/Collision/Semantic 规则数据。`path` 只能使用 `/`、相对 release root、不得含空段/`.`/`..`；SHA-256 对打包前该 path 的精确文件字节计算并以 64 位 lowercase hex 存储。

## 5. 数据与接口

`DES-RENDER-011`：Manifest 顶层 `{schema_version:"asset-manifest.v1", assets: AssetManifestEntry[], licenses: LicenseRecord[]}`；以下两类 record 的字段均为 required，禁止 unknown field 以避免拼写被静默忽略。

```json
{
  "asset_id": "map.crown_creek.ground.lod0.slice_00_00",
  "type": "image",
  "path": "assets/map/crown_creek/ground/lod0/slice_00_00.png",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "byte_length": 128744,
  "load_group": "region.crown_creek.required",
  "license_id": "license.project_original_001",
  "fallback_asset_id": "asset.fallback.checkerboard"
}
```

```json
{
  "license_id": "license.project_original_001",
  "source_uri": "project://art/map/crown-creek-ground",
  "author": "AI Town Art Team",
  "terms": "LicenseRef-Proprietary-AI-Town",
  "acquired_at": "2026-07-26T00:00:00.000Z",
  "license_text_path": "licenses/license.project_original_001.txt",
  "license_text_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

构建工具以资源和 license text 的实际字节计算 SHA-256；上例只说明字段格式，release Manifest 必须写入对应 path 的实际 hash/byte length。`terms` 必须是允许清单中的 SPDX ID/Expression 或经法务登记的 `LicenseRef-*`。

## 6. 正常流程

1. 构建期以严格 JSON Schema 解析 Manifest，检查 schema version、unknown field、ID/path 唯一、byte length/hash、license lookup 与 fallback DAG 无环。
2. 对每个 `AssetManifestEntry.path` 和 `LicenseRecord.license_text_path` 读取确切字节，验证路径约束、长度/SHA-256、terms allowlist，并产出 `asset_id -> license_id -> evidence path` 审计表。
3. PreloadScene 先加载 global fallback，再加载当前 required group，optional group 随需加载。
4. Runtime 按失败 type 走 fallback chain，并上报 asset/scene/revision。

## 7. 边界情况

同一 asset 在两个 group 出现必须字节 hash 一致；版本升级时旧存档仅引用 stable ID，不能引用旧文件路径。

## 8. 错误与降级

Manifest 不可解析、必需 fallback 缺失或许可证字段缺失时构建失败；诊断码固定为 `RENDER_MANIFEST_PARSE_FAILED`、`RENDER_ASSET_PATH_INVALID`、`RENDER_ASSET_HASH_MISMATCH`、`RENDER_LICENSE_RECORD_MISSING`、`RENDER_LICENSE_FIELD_MISSING`、`RENDER_LICENSE_TEXT_HASH_MISMATCH`、`RENDER_LICENSE_TERMS_UNAPPROVED`。每条诊断必须包含 manifest path、asset/license ID 和 JSON pointer，但不得输出文件内容。运行时单资源失败使用已登记 fallback，禁止 URL 热链或未登记临时素材。

## 9. 安全与性能

hash 防止打包错位；lazy loading 仅载入当前 Scene 所需组；纹理/音频量由 `DOC-RENDER-012` 预算强制限制。

## 10. 验收标准

- `REQ-RENDER-011`：所有发布 asset 与 license text 的 path/hash 可解析匹配，`asset_id -> license_id -> source/author/terms/acquired_at/evidence` 可机械追溯、fallback 无环，且缺失资源仍能完成核心操作。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-011` | 严格 Manifest/LicenseRecord schema、path traversal、asset/license hash、terms allowlist、诊断码、fallback DAG lint 与故障注入加载测试。 |

## 12. 关联文档

- `DOC-RENDER-002`：Scene Load Gate
- `DOC-RENDER-012`：预算与 QA

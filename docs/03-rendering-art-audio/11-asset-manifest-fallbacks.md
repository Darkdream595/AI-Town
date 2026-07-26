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

- `RULE-RENDER-031`：canonical schema 是本文件第 5 节的 Draft 2020-12 JSON Schema，`$id=https://ai-town.local/schemas/asset-manifest.v1.schema.json`；构建工具必须按 exact `$id` 加载并开启 format assertion，不得用手写 DTO 代替 schema validation。每个 asset ID 符合 Stable Catalog ID grammar，全局唯一且有 type、规范化相对 path、实际字节 SHA-256、byte length、license ID、fallback ID；每个 license ID 必须解析到唯一、完整且允许发布的 `LicenseRecord`。
- `RULE-RENDER-032`：Required group 不可缺少 fallback；未知或 hash 不匹配资源不得被静默加载。
- `RULE-RENDER-033`：地图资源分列 `ground_art` 与 `structure`；Manifest 不承载 Walkability/Collision/Semantic 规则数据。`path` 只能使用 `/`、相对 release root、不得含空段/`.`/`..`；SHA-256 对打包前该 path 的精确文件字节计算并以 64 位 lowercase hex 存储。

## 5. 数据与接口

`DES-RENDER-011`：以下 fenced JSON 是可直接加载的 canonical JSON Schema；Manifest instance 顶层固定为 `{schema_version:"asset-manifest.v1", assets: AssetManifestEntry[], licenses: LicenseRecord[]}`。root、两类 record 均禁止 unknown field。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai-town.local/schemas/asset-manifest.v1.schema.json",
  "title": "AI Town Asset Manifest v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "assets", "licenses"],
  "properties": {
    "schema_version": {
      "const": "asset-manifest.v1"
    },
    "assets": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "$ref": "#/$defs/AssetManifestEntry"
      }
    },
    "licenses": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "$ref": "#/$defs/LicenseRecord"
      }
    }
  },
  "$defs": {
    "StableCatalogId": {
      "type": "string",
      "minLength": 3,
      "maxLength": 160,
      "pattern": "^[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)+$"
    },
    "LicenseId": {
      "type": "string",
      "minLength": 9,
      "maxLength": 160,
      "pattern": "^license\\.[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)*$"
    },
    "RelativePath": {
      "type": "string",
      "minLength": 3,
      "maxLength": 240,
      "pattern": "^(?!/)(?!.*(?:^|/)\\.{1,2}(?:/|$))(?!.*//)[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$"
    },
    "Sha256": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$"
    },
    "AssetManifestEntry": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "asset_id",
        "type",
        "path",
        "sha256",
        "byte_length",
        "load_group",
        "load_policy",
        "license_id",
        "fallback_asset_id"
      ],
      "properties": {
        "asset_id": {
          "$ref": "#/$defs/StableCatalogId"
        },
        "type": {
          "type": "string",
          "enum": ["image", "atlas", "audio", "font", "json", "shader"]
        },
        "path": {
          "$ref": "#/$defs/RelativePath"
        },
        "sha256": {
          "$ref": "#/$defs/Sha256"
        },
        "byte_length": {
          "type": "integer",
          "minimum": 1,
          "maximum": 2147483647
        },
        "load_group": {
          "$ref": "#/$defs/StableCatalogId"
        },
        "load_policy": {
          "type": "string",
          "enum": ["required", "optional"]
        },
        "license_id": {
          "$ref": "#/$defs/LicenseId"
        },
        "fallback_asset_id": {
          "$ref": "#/$defs/StableCatalogId"
        }
      }
    },
    "LicenseRecord": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "license_id",
        "source_uri",
        "author",
        "terms",
        "acquired_at",
        "license_text_path",
        "license_text_sha256"
      ],
      "properties": {
        "license_id": {
          "$ref": "#/$defs/LicenseId"
        },
        "source_uri": {
          "type": "string",
          "format": "uri",
          "pattern": "^(?:https://|project://)",
          "maxLength": 2048
        },
        "author": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200,
          "pattern": "^[^\\u0000-\\u001F\\u007F]+$"
        },
        "terms": {
          "type": "string",
          "minLength": 3,
          "maxLength": 240,
          "pattern": "^(?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9][A-Za-z0-9.+() -]*)$"
        },
        "acquired_at": {
          "type": "string",
          "format": "date-time"
        },
        "license_text_path": {
          "$ref": "#/$defs/RelativePath"
        },
        "license_text_sha256": {
          "$ref": "#/$defs/Sha256"
        }
      }
    }
  }
}
```

JSON Schema 负责结构、类型、格式和单 record 约束；JSON Schema 的 `uniqueItems` 只排除完全相同的 object，不能表达“按字段唯一”或跨数组 foreign key。构建 lint 必须在 schema validation 后执行以下确定性算法：

1. 单次遍历 `licenses` 建立 `license_id -> index`，重复即 `RENDER_LICENSE_ID_DUPLICATE`。
2. 单次遍历 `assets` 分别建立 `asset_id -> index` 与 `path -> asset_id`，重复分别为 `RENDER_ASSET_ID_DUPLICATE`、`RENDER_ASSET_PATH_DUPLICATE`。
3. 每个 `AssetManifestEntry.license_id` 必须在 license map 中恰好命中一次；零次为 `RENDER_LICENSE_RECORD_MISSING`，重复已由步骤 1 阻断。
4. 每个 `fallback_asset_id` 必须在 asset map 命中且不能等于自身；沿 fallback edge 做三色 DFS，缺失/自指为 `RENDER_FALLBACK_REFERENCE_INVALID`，环为 `RENDER_FALLBACK_CYCLE`。
5. `path` 与 `license_text_path` 均相对 release root 解析并再次确认 normalized result 仍位于 root 内；构建工具以实际文件字节计算 byte length/SHA-256。`terms` 还须命中 release SPDX/`LicenseRef-*` allowlist。

## 6. 正常流程

1. 构建期先按 `$id` 加载第 5 节 canonical schema，以 Draft 2020-12 validator + format assertion 解析 Manifest；schema 不可加载或 `$id/schema_version` 不匹配立即失败。
2. 对每个 `AssetManifestEntry.path` 和 `LicenseRecord.license_text_path` 读取确切字节，验证路径约束、长度/SHA-256、terms allowlist，并产出 `asset_id -> license_id -> evidence path` 审计表。
3. 按第 5 节顺序执行 license/asset/path 唯一性、foreign key 与 fallback DAG lint；只有 schema 和 lint 全部通过才生成 runtime manifest。
4. PreloadScene 先加载 global fallback，再加载当前 required group，optional group 随需加载。
5. Runtime 按失败 type 走 fallback chain，并上报 asset/scene/revision。

## 7. 边界情况

同一 asset 在两个 group 出现必须字节 hash 一致；版本升级时旧存档仅引用 stable ID，不能引用旧文件路径。

## 8. 错误与降级

Manifest 不可解析、必需 fallback 缺失或许可证字段缺失时构建失败。诊断映射如下；每条诊断必须包含 manifest path、相关 asset/license ID（可取得时）和 JSON Pointer，不得输出文件内容。

| 阶段/条件 | 诊断码 |
|---|---|
| JSON parse 失败 | `RENDER_MANIFEST_PARSE_FAILED` |
| canonical `$id` 无法加载或 schema version 不匹配 | `RENDER_MANIFEST_SCHEMA_VERSION_UNSUPPORTED` |
| JSON Schema keyword/format assertion 失败 | `RENDER_MANIFEST_SCHEMA_INVALID` |
| asset path 非规范、越过 root 或文件不存在 | `RENDER_ASSET_PATH_INVALID` |
| asset byte length/SHA-256 不匹配 | `RENDER_ASSET_HASH_MISMATCH` |
| `asset_id` 重复 | `RENDER_ASSET_ID_DUPLICATE` |
| asset `path` 重复 | `RENDER_ASSET_PATH_DUPLICATE` |
| `license_id` 重复 | `RENDER_LICENSE_ID_DUPLICATE` |
| asset 引用的 `license_id` 不存在 | `RENDER_LICENSE_RECORD_MISSING` |
| license text path 非规范、越过 root 或文件不存在 | `RENDER_LICENSE_TEXT_PATH_INVALID` |
| license text SHA-256 不匹配 | `RENDER_LICENSE_TEXT_HASH_MISMATCH` |
| terms 不在发布 allowlist | `RENDER_LICENSE_TERMS_UNAPPROVED` |
| fallback 缺失、自指或类型不兼容 | `RENDER_FALLBACK_REFERENCE_INVALID` |
| fallback DAG 出现环 | `RENDER_FALLBACK_CYCLE` |

运行时单资源失败使用已登记 fallback，禁止 URL 热链或未登记临时素材。

## 9. 安全与性能

hash 防止打包错位；lazy loading 仅载入当前 Scene 所需组；纹理/音频量由 `DOC-RENDER-012` 预算强制限制。

## 10. 验收标准

- `REQ-RENDER-011`：Manifest 必须通过本文件 versioned canonical JSON Schema 和 schema 后 lint；所有发布 asset 与 license text 的 path/hash 可解析匹配，`asset_id -> license_id -> source/author/terms/acquired_at/evidence` 可机械追溯、ID/path 唯一、fallback 无环，且缺失资源仍能完成核心操作。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-011` | 加载第 5 节 canonical schema 并验证 valid/invalid fixtures；覆盖 root/definitions/required/type/pattern/enum/additionalProperties、format assertion、ID/path 唯一、license foreign key、path traversal、asset/license hash、terms allowlist、诊断码、fallback DAG 与故障注入加载。 |

## 12. 关联文档

- `DOC-RENDER-002`：Scene Load Gate
- `DOC-RENDER-012`：预算与 QA

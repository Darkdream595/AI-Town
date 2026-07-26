---
doc_id: DOC-RESIDENT-002
title: 身份、族裔与外貌引用
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-identity-schema
  - resident-appearance-reference
depends_on:
  - DOC-WORLD-005
  - DOC-RENDER-004
  - DOC-RESIDENT-001
requirements:
  - REQ-RESIDENT-002
last_updated: 2026-07-26
---

# 身份、族裔与外貌引用

## 1. 目的

`REQ-RESIDENT-002`：定义 Resident 的姓名、族裔、文化、语言和外貌引用，确保四类族裔可自由组合职业、文化与人格，且渲染资源缺失不改变身份事实。

## 2. 非目标

不重新定义 WORLD-owned ancestry/culture 语义，不拥有 RENDER Asset Manifest，也不从族裔推断能力、职业、善恶、语言或权限。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `IdentityProfile` | 居民自报姓名、代词、族裔、文化和语言的持久值对象 |
| `AppearanceProfile` | Resident-owned 外观语义选择，引用 RENDER Asset ID |
| `presentation_tags` | 发型、服装轮廓、辅助器具等非规则标签 |
| `language proficiency` | `0..100` 的习得熟练度，不由 ancestry 自动授予 |

## 4. 数据与接口

`DES-RESIDENT-002`：注册 `schema.resident.identity.v1`；required 字段为
`identity_schema_version/display_name/self_name/pronoun_id/ancestry_id/culture_ids/language_proficiencies/appearance`，
且该完整对象原样嵌入 `ResidentAggregateV1.identity`：

```json
{
  "identity_schema_version": 1,
  "display_name": "艾莉丝",
  "self_name": "艾莉丝",
  "pronoun_id": "pronoun.she",
  "ancestry_id": "ancestry.human",
  "culture_ids": ["culture.crown_creek_local","culture.roadfarer"],
  "language_proficiencies": [
    {"language_id":"language.crown_common","level":100}
  ],
  "appearance": {
    "profile_id":"appearance.resident.apothecary.elise",
    "sprite_asset_id":"sprite.resident.apothecary",
    "portrait_asset_id":"portrait.resident.apothecary",
    "combat_sprite_asset_id":"combat_sprite.resident.apothecary",
    "palette_variant_id":"palette.apothecary.blue_amber",
    "presentation_tags":["hair.braided","clothing.apothecary_apron"]
  }
}
```

外貌投影通过 Orchestrator 映射给 RENDER；RENDER 不读取 Resident aggregate。

## 5. 规则与不变量

- `RULE-RESIDENT-007`：`ancestry_id` 必须是 `ancestry.human|woodkin|stonekin|beastkin` 之一；`culture_ids` 至少一个、去重且最多三个。
- `RULE-RESIDENT-008`：任何 ancestry 都不得隐式修改 Skill、Need、Emotion、职业、关系、法律状态或语言。
- `RULE-RESIDENT-009`：正式居民必须具有 `language.crown_common >= 60`，确保公共服务可用；额外语言按经历登记。
- `RULE-RESIDENT-010`：显示名为 1–32 个 Unicode grapheme，去除控制字符；稳定身份依赖 ID 而非显示名。
- `RULE-RESIDENT-011`：Asset 缺失只触发 RENDER fallback；不得改写 ancestry、appearance profile 或 resident key。

## 6. 正常流程

1. 创建器选择或接收世界 Catalog 中的 ancestry/culture/language。
2. 校验反本质主义组合约束和通用语最低能力。
3. 验证外貌 Asset ID 可解析；允许按 Manifest 使用已登记 fallback。
4. 提交 `ResidentIdentityAssigned`，渲染 projection 在事件后生成。

## 7. 边界情况

- 同名居民通过 `resident_id` 区分，UI 可附职业或头像。
- 混合文化保留有序自我认同，不按 ancestry 重排。
- 兽裔 presentation tag 不得包含宠物化词汇；被拒资源使用中性剪影。
- 成年阶段变化可替换外貌 profile，但 ancestry 与历史事件不变。

## 8. 错误与降级

返回 `RESIDENT_IDENTITY_CATALOG_MISSING`、`RESIDENT_IDENTITY_ESSENTIALISM`、`RESIDENT_NAME_INVALID`、`RESIDENT_LANGUAGE_COVERAGE_MISSING`。Asset 缺失记录 `RESIDENT_APPEARANCE_FALLBACK_USED` 警告但不阻断合法身份。

## 9. 安全与性能

身份不用于模型价值排序或隐含授权。玩家可见投影只含公开自报字段；私人背景由 MEMORY owner 控制。Catalog 在构建期索引，运行时 O(1) 校验。

## 10. 验收标准

- 四 ancestry × 四 culture × 至少两职业组合均合法。
- 切换 Asset/fallback 不改变规则状态。
- 同名、混合文化、多语言均可无歧义持久化。
- 任何 ancestry 均不自动生成 Skill、职业或关系差异。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-005` | ancestry/culture/职业组合 Property Test |
| `TEST-RESIDENT-006` | 名称 grapheme、控制字符与同名 ID Test |
| `TEST-RESIDENT-007` | Asset 缺失 fallback 不改变 identity |
| `TEST-RESIDENT-008` | 语言覆盖与 ancestry 无隐式语言测试 |

## 12. 关联文档

- `DOC-WORLD-005`：族裔与文化 canonical 语义
- `DOC-RENDER-004`：Sprite/Portrait 合约
- `DOC-RESIDENT-011`：初始化组合

---
doc_id: DOC-MAGIC-001
title: 魔法世界观
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-cosmology
  - starweave-tide-rules
  - magic-world-law-implications
depends_on:
  - DOC-FOUNDATION-005
  - DOC-WORLD-003
  - DOC-WORLD-008
requirements:
  - REQ-MAGIC-001
  - REQ-MAGIC-002
last_updated: 2026-07-26
---

# 魔法世界观

## 1. 目的

确立星织潮（环境魔力）作为 AI Town 魔法唯一形而上来源的 canonical 叙事与规则含义，限定魔法在世界中的存在边界、可解释范围与法律地位，使六大学派、Mana、SpellDefinition 与环境交互都有共同的世界观基座。

## 2. 非目标

本文件不定义具体法术数值、Mana 恢复公式、学派技能树、施法合法性算法或 VFX；这些由 `DOC-MAGIC-002..012` 分别定义。本文件也不裁定星织潮终极来源的真假——该问题在世界观内保持不可知。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 星织潮 | 周期波动的环境魔力场；强度以结构化数据存在，不凭叙述改变 |
| 施法者 | 持有有效 `SpellKnowledge` 与 Mana 的 Resident 或玩家镇长 |
| 灵体 | Spirit 学派交互的非居民实体，遵守独立 Reservation 与同意规则 |
| 奥术技艺 | 不依学派直觉、依赖程式与准备的 Arcane 施法方式 |
| 魔法异常 | 灰脉灾变遗留的局部污染区，由 EVENT owner 管理 |
| 世界法则 | 魔法在任何情况下不得违反的跨系统不变量集合 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-001` | 所有魔法内容必须以星织潮为唯一环境魔力来源；禁止引入第二来源（神授、血统特权、异界契约等）作为机制依据。 |
| `REQ-MAGIC-002` | 魔法表现必须服从日式西幻方向（`DOC-WORLD-009`）：克制、可读、情绪化的自然光感，不走高饱和度粒子堆砌。 |
| `RULE-MAGIC-001` | 世界观解释不授予任何角色绕过 `SpellDefinition` 的能力；星织潮只解释 Mana 环境背景与恢复修正，参见 `RULE-WORLD-010`。 |
| `RULE-MAGIC-002` | 魔法不得违反 `DOC-FOUNDATION-005` 全部跨系统不变量：只有 Authority Server 提交状态，魔法不能凭空产生货币、Item、HP 或位置变化。 |
| `RULE-MAGIC-003` | 魔法效果的法律状态分类（`permitted/restricted/prohibited`）的唯一权威是 `DOC-WORLD-008`；本域只消费该矩阵，不重新定义罪名或处罚。 |
| `RULE-MAGIC-004` | 灰脉灾变污染、森林禁忌与矿洞魔晶是已登记历史事实（`history.*`），施法不能改写、净化或撤销这些 Canon 事实。 |

## 5. 数据与接口

`DES-MAGIC-001`：世界观以 `MagicCosmology` 注册表条目发布，供 AI Context、对话与任务生成引用：

| 字段 | 说明 |
|---|---|
| `cosmology_id` | `magic.cosmology.*` Stable Catalog ID |
| `public_summary` | 可向任何角色公开的描述 |
| `belief_variants` | 各族群/组织允许持有的解释差异（Belief，非 Fact） |
| `mechanical_hooks` | 允许挂钩的机制键，仅 `starweave_tide_modifier`、`ley_anchor_presence` 两项 |

首版注册三条：`magic.cosmology.starweave_tide`、`magic.cosmology.silver_ash_legacy`、`magic.cosmology.spirit_pacts`。

## 6. 正常流程

1. 内容作者新增世界观条目时先登记 `cosmology_id` 并声明 `mechanical_hooks`。
2. TIME owner 按 `DOC-TIME-*` 的 Tick 推进星织潮强度（日/季节波动），向 Magic 域发布结构化强度值。
3. Magic 域把强度值作为 Mana 恢复的环境修正输入（`DOC-MAGIC-003`），不产生其他世界变化。
4. AI 生成叙述时只能引用已登记条目与当前 actor 可知的 Belief 变体。

## 7. 边界情况

- 星织潮低谷期：施法仍合法，仅恢复修正降低；不得出现"魔法消失"的全局失效叙述。
- 新世界 Seed 可改变小型传说与装饰性遗迹分布，不得改变三条已注册 cosmology 条目（`RULE-WORLD-012`）。
- 玩家用自由文本描述"自创魔法体系"时，只作为角色 Belief 进入对话，不进入任何机制字段。

## 8. 错误与降级

内容请求引用未登记魔法来源或 Canon 冲突时，Canon 校验返回 `WORLD_CANON_CONFLICT` 并保持原状态（沿用 `DOC-WORLD-011` 治理）。星织潮强度数据缺失时按中性修正 1.0 处理并记录诊断，不暂停世界。

## 9. 安全与性能

`MagicCosmology` 注册表构建为不可变 Catalog，按 ID 索引；不得在每次对话全表扫描。灵体与契约叙述不得映射现实宗教或仇恨符号（沿用 `RULE-WORLD-039` 精神）。模型上下文只注入当前 actor 可访问的摘要。

## 10. 验收标准

- 全部魔法相关文档可追溯到星织潮单一来源，无第二机制来源。
- 任一正文叙述断言能反向解析到已注册 `cosmology_id` 或 `history.*` 事实。
- 随机世界初始化一百次不改变三条注册条目与机械挂钩集合。
- 任何"绕过 SpellDefinition"的提案在 Canon 校验被拒绝。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-001` | `REQ-MAGIC-001`, `RULE-MAGIC-001..002` | Catalog 审计：全部魔法机制引用星织潮挂钩；注入"第二来源"内容被拒绝 |
| `TEST-MAGIC-002` | `REQ-MAGIC-002`, `RULE-MAGIC-003..004` | 法律状态引用审计与 Canon 冲突反例测试 |

## 12. 关联文档

- `DOC-WORLD-003`：星织潮、银烬坠落与灰脉灾变的历史登记
- `DOC-WORLD-008`：魔法法律状态的唯一权威
- `DOC-WORLD-009`：视觉风格方向
- `DOC-MAGIC-002`：六大学派定义
- `DOC-MAGIC-003`：星织潮强度对 Mana 恢复的消费

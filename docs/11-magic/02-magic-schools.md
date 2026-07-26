---
doc_id: DOC-MAGIC-002
title: 魔法学派
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-school-registry
  - school-scope-boundaries
  - cross-school-overlap-rules
depends_on:
  - DOC-FOUNDATION-006
  - DOC-MAGIC-001
requirements:
  - REQ-MAGIC-003
  - REQ-MAGIC-004
last_updated: 2026-07-26
---

# 魔法学派

## 1. 目的

定义 Elemental、Restoration、Warding、Illusion、Spirit、Arcane 六大学派的 canonical 注册表、各自作用域、排他边界与跨学派重叠规则，使每个 Spell 有且只有一个归属学派。

## 2. 非目标

本文件不定义具体法术清单与数值（`DOC-MAGIC-004`）、学习路径（`DOC-MAGIC-006`）或学派视觉效果（`DOC-MAGIC-011`）。不引入第七学派或隐藏学派。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| School | 法术的排他分类维度，决定作用域、学习来源与部分法律默认 |
| `SchoolSkill` | 居民在每个学派的技能值，整数 0–100 |
| 作用域 | 学派允许影响的世界实体类别集合 |
| 归属冲突 | 一个效果可被多个学派描述时按本文件 §4 仲裁 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-003` | 学派集合固定为六个：`school.elemental`、`school.restoration`、`school.warding`、`school.illusion`、`school.spirit`、`school.arcane`；增删学派需要版本化 Registry 变更。 |
| `REQ-MAGIC-004` | 每个 `SpellDefinition` 恰好声明一个 `school_id`；学派是其法律默认值、学习来源与 VFX 家族的决定输入。 |
| `RULE-MAGIC-005` | 学派作用域：Elemental 影响非生命物质与环境；Restoration 影响生命体状态修复；Warding 影响区域/对象的防护与强化；Illusion 影响感知与信息呈现；Spirit 影响灵体交互与诅咒；Arcane 影响通用程式化效果（传送除外，见 `RULE-MAGIC-006`）。 |
| `RULE-MAGIC-006` | 首版禁止任何形式的传送（teleport）法术与效果；Arcane 作用域显式排除位置瞬移。 |
| `RULE-MAGIC-007` | 归属冲突仲裁顺序：直接改变 HP/伤势 → Restoration；制造或扑灭火焰/改变物质状态 → Elemental；改变他人感知内容 → Illusion；其余按注册表声明，不允许效果描述决定学派。 |
| `RULE-MAGIC-008` | 学派不提供跨系统特权：任何学派都不能绕过 Economy Item 真值、TIME 时钟或 `DOC-FOUNDATION-005` 不变量。 |

## 5. 数据与接口

`DES-MAGIC-002`：`SchoolDefinition` 注册表：

| 字段 | 说明 |
|---|---|
| `school_id` | 六个固定 Stable Catalog ID 之一 |
| `display_name_zh` | 中文显示名：元素、疗愈、护壁、幻术、通灵、奥术 |
| `scope_tags` | 允许影响的实体类别：`matter`,`creature_state`,`protection`,`perception`,`spirit`,`programmatic` |
| `default_legal_baseline` | 未单独声明时的法律默认；镇区公共空间攻击性 Elemental/Spirit 依 `RULE-WORLD-034` 为 `prohibited` |
| `vfx_family` | 视觉家族前缀，如 `vfx.elemental.*`，细化见 `DOC-MAGIC-011` |
| `learning_source_kinds` | 允许的学习来源：`teacher`,`book`,`practice`，细化见 `DOC-MAGIC-006` |

## 6. 正常流程

1. 新增法术时作者先选定 `school_id`，Registry linter 校验 scope_tags 与效果类别一致。
2. 施法合法性检查（`DOC-MAGIC-005`）读取学派默认法律基线，再叠加法术级声明。
3. 学习系统按 `learning_source_kinds` 过滤可教授该学派法术的教师与书籍。
4. 渲染域按 `vfx_family` 映射 `DOC-RENDER-008` 的 VFX 注册。

## 7. 边界情况

- 火系治疗效果（如烧灼止血）：按 `RULE-MAGIC-007` 归 Restoration，Elemental 不得声明治疗。
- 防护幻象（让人以为有墙）：感知改变优先，归 Illusion。
- 居民同时学习多个学派：允许，每学派独立 `SchoolSkill`，无组合加成字段。

## 8. 错误与降级

法术声明的学派 scope_tags 与其注册效果类别不匹配时，构建期 lint 失败并拒绝入库；运行时遇到未知 `school_id` 一律 fail closed，施法请求以 `FORBIDDEN` 拒绝。学派显示名缺失时退回 `school_id` 原文显示。

## 9. 安全与性能

`SchoolDefinition` 为构建期不可变 Catalog，按 ID O(1) 查找。法律默认值只作 fallback，不得掩盖法术级 `restricted/prohibited` 声明。学派信息无 Secret，可进入任何角色的决策上下文。

## 10. 验收标准

- Registry 恰好六个学派，ID 与中文名固定。
- 全部首版 Spell 的 `school_id` 解析成功且 scope 一致。
- 传送类提案在 Schema/Registry 两级均被拒绝。
- 归属冲突用例按 `RULE-MAGIC-007` 仲裁结果稳定。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-003` | `REQ-MAGIC-003..004`, `RULE-MAGIC-005..006` | Registry 基数、scope 一致性 lint；传送提案拒绝测试 |
| `TEST-MAGIC-004` | `RULE-MAGIC-007..008` | 归属冲突仲裁 fixture；跨系统特权注入反例 |

## 12. 关联文档

- `DOC-MAGIC-001`：学派的世界观基座
- `DOC-MAGIC-004`：SpellDefinition 的 school_id 字段
- `DOC-MAGIC-005`：法律基线的消费
- `DOC-MAGIC-006`：学习来源
- `DOC-MAGIC-011`：vfx_family 的视觉落地
- `DOC-WORLD-008`：镇区攻击性法术禁令

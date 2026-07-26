---
doc_id: DOC-MAGIC-007
title: 居民自主施法
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - autonomous-casting-policy
  - spell-candidate-projection
depends_on:
  - DOC-MAGIC-005
  - DOC-MAGIC-006
  - DOC-AI-004
  - DOC-AI-005
requirements:
  - REQ-MAGIC-013
  - REQ-MAGIC-014
last_updated: 2026-07-26
---

# 居民自主施法

## 1. 目的

定义 AI 居民自主选择施法的候选构建、提案约束与目击/声誉后果的接入点，使 deepseek-v4-flash 的施法决策被限制在"已学会、当前合法可用、上下文可见"的封闭集合内，且模型永远不结算效果数值。

## 2. 非目标

本文件不定义 `cast_spell` 的 wire Schema（`DOC-AI-004` 拥有 `cast_spell_parameters`）、认知流水线与 Prompt 分层（`DOC-AI-001/003`）、战斗回合内的施法决策（`DOC-COMBAT-007`）或记忆/声誉的存储模型（`DOC-MEMORY-006..008` 拥有）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 法术候选投影 | Capability Builder 为单个居民构建的可施放法术摘要列表 |
| `declared_purpose` | 提案中的意图枚举 `utility/healing/defense/combat/ritual`，用于语义一致性检查 |
| 目击 | 感知范围内其他角色对已提交施法事件形成的观察输入 |
| 施法倾向 | 居民人格/职业对候选排序的提示性影响，不构成合法性 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-013` | 进入 Prompt 的法术候选必须同时满足：`SpellKnowledge=learned`、非枯竭且 `mana_current >= mana_cost`、冷却就绪、当前场景世界合法性预判非 `prohibited`；候选之外的 `spell_id` 提案在校验第 2 级即拒（`REQ-MAGIC-009`）。 |
| `REQ-MAGIC-014` | 模型输出只承载选择：`spell_id/target_refs/aim_point/declared_purpose`；治疗量、伤害、成功率、目击者名单等一切结算事实由服务器产生（对齐 `RULE-AI-028`）。 |
| `RULE-MAGIC-035` | 候选投影是提示优化不是安全边界（对齐 `RULE-AI-030`）：即便候选构建遗漏过滤，提交路径的七级校验仍是唯一授权点。 |
| `RULE-MAGIC-036` | `declared_purpose` 必须与效果类别一致（治疗类效果只能声明 `healing`，诅咒只能声明 `combat/ritual`）；不一致按 `REPLAN_REQUIRED` 退回，防止用途伪装绕过语义审计。 |
| `RULE-MAGIC-037` | Utility AI fallback 永不主动施法（`DOC-AI-011` 禁列 `cast_spell`）；模型不可用时居民只是不施法，不存在降级乱放法术。 |
| `RULE-MAGIC-038` | 目标选择只能引用 `DecisionContext` 中可见实体（`RULE-AI-027`）；对居民未感知的实体施法在语义校验拒绝，禁止全知瞄准。 |
| `RULE-MAGIC-039` | 已提交施法对感知范围内角色产生结构化目击输入：`(caster_id, spell_id, school_id, 法律判定, 目标概要)`，由 MEMORY 按其规则转为 EpisodicMemory/SocialImpression/BeliefTransfer；MAGIC 不直接写声誉数值。 |
| `RULE-MAGIC-040` | 施法频率软约束：非战斗自主施法遵守 per-caster 预算（默认每游戏日 8 次 `instant`），超出后候选投影降权但不非法；预算是行为平衡参数（`DOC-MAGIC-012`），不进入合法性判定。 |

## 5. 数据与接口

`DES-MAGIC-007`：法术候选投影条目（注入 Prompt 的最小摘要）：

```json
{
  "candidate_schema_version": 1,
  "caster_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "context_revision": 105,
  "candidates": [
    {
      "spell_id": "spell.restoration.minor_mend",
      "school_id": "school.restoration",
      "mana_cost": 12,
      "range_wu": 96.0,
      "target_mode": "single_entity",
      "legality_preview": "restricted",
      "consent_required": true,
      "cooldown_ready": true
    }
  ],
  "mana_current": 42,
  "daily_cast_budget_remaining": 5
}
```

`legality_preview` 是候选构建时刻的预判（`RULE-MAGIC-028` 缓存语义），提交时重验。目击输入的事件消费契约：MEMORY 订阅 `SpellCastCommitted` 的感知投影，MAGIC 不导出目标的私有状态（如被治疗者具体 HP）。

## 6. 正常流程

1. 认知流水线（`DOC-AI-001`）构建 `DecisionContext` 时并入法术候选投影。
2. 模型按 Hourly Intent 与当前情境产出 `cast_spell` 提案，strict decode 后进入 `DOC-AI-010` 分级校验。
3. MAGIC 执行七级校验并提交；结果事件回流居民记忆（施法者自身获得成功/失败经历记录）。
4. 感知范围内目击者获得 `RULE-MAGIC-039` 结构化输入；对 `restricted` 施法的目击可触发举报、感激或恐惧等 MEMORY/社交反应。

## 7. 边界情况

- 候选为空（无已学法术或全部冷却/枯竭）：Prompt 不展示 `cast_spell` 能力，模型仍可能幻觉提案，校验兜底拒绝。
- 治疗无同意目标：候选保留但标注 `consent_required`，提案缺授权证据时按 `MAGIC_CONSENT_MISSING` 退回，居民可先经对话取得同意事件。
- 两名居民同 Tick 对同一目标施法：按 Reservation 与提交顺序串行化，后者在最新 Revision 重验。
- 居民目击非法施法尝试：被拒绝的命令无 DomainEvent，不产生目击；只有已提交事实可被记住（`RULE-FOUNDATION-015` 同向）。
- 幻术目击：目击输入携带感知内容而非真相，Illusion 的信息面处理见 `DOC-MAGIC-009` 的 `veil_illusion` handler。

## 8. 错误与降级

候选构建失败时该轮上下文不含施法能力，居民决策退化为其余 18 类 Action，不阻塞认知流水线。模型超时/失败走 `DOC-AI-011` fallback（必不施法）。目击投影发布失败重试，不回滚已提交施法事务——表现与记忆是下游消费者。

## 9. 安全与性能

候选投影每居民上限 16 条（按情境相关性截断），控制 Prompt token（`DOC-AI-008`）。投影不含其他角色的 Mana、SpellKnowledge 或 Secret；居民对他人魔法能力的认知只能来自目击与传闻（`RULE-FOUNDATION-020`）。`daily_cast_budget_remaining` 是服务器计数，模型不可自增。

## 10. 验收标准

- 注入未学/冷却中/枯竭/越权法术的提案 100% 被拒且无状态变化。
- 候选投影与七级校验对同一 Revision 的判定一致率 100%（预判偏差只允许由 Revision 推进解释）。
- 目击输入只源于已提交事件，数量与感知范围断言一致。
- 30 游戏日模拟中居民施法频率分布落在预算包络内（`DOC-MAGIC-012`）。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-015` | `REQ-MAGIC-013..014`, `RULE-MAGIC-035..038` | 候选过滤矩阵、幻觉提案兜底、purpose 一致性与不可见目标反例 |
| `TEST-MAGIC-016` | `RULE-MAGIC-039..040` | 目击事件生成与感知范围断言；施法预算软约束统计测试 |

## 12. 关联文档

- `DOC-AI-004`：`cast_spell_parameters` wire Schema
- `DOC-AI-005`：`cast_spell` 在 Action Catalog 中的行
- `DOC-AI-010/011`：校验分级与不施法 fallback
- `DOC-MAGIC-005`：唯一授权点的七级校验
- `DOC-MEMORY-006..008`：目击到关系/谣言的转化

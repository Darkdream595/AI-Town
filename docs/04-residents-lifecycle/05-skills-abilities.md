---
doc_id: DOC-RESIDENT-005
title: 技能与能力资格
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-skill-ratings
  - resident-ability-eligibility
depends_on:
  - DOC-RESIDENT-001
  - DOC-RESIDENT-003
requirements:
  - REQ-RESIDENT-005
last_updated: 2026-07-26
---

# 技能与能力资格

## 1. 目的

`REQ-RESIDENT-005`：定义居民技能等级、经验累积、能力资格和成长边界，为 ECON/MAGIC/COMBAT 等 owner 提供只读能力证据，但不接管其数值结算。

## 2. 非目标

不定义职业产出、SpellDefinition、战斗公式、工具 Item 或 AI 选行动；`ability_id` 只表示已登记资格，不表示当前合法或必然成功。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Skill | `skill.*` Catalog 项，如 `skill.herbalism` |
| Rating | `0..100` 的整数熟练度 |
| XP | 当前 Rating 内 `0..9999` 的成长进度 |
| Ability | `ability.*` 的资格引用，由显式 unlock 条件获得 |
| Capability Snapshot | 某 Revision 的只读技能/能力投影 |

## 4. 数据与接口

`DES-RESIDENT-005`：注册 `schema.resident.capability_state.v1`；required 字段为
`capability_schema_version/skills/ability_ids/capability_revision`，每个 Skill required
`rating/xp/last_practiced_game_time`。该完整对象原样嵌入
`ResidentAggregateV1.capability_state`：

```json
{
  "capability_schema_version": 1,
  "skills": {
    "skill.herbalism": {"rating":64,"xp":320,"last_practiced_game_time":1810},
    "skill.medicine": {"rating":48,"xp":90,"last_practiced_game_time":1700}
  },
  "ability_ids": ["ability.herbalism.identify_common","ability.medicine.first_aid"],
  "capability_revision": 8
}
```

Port：

```text
get_capability_snapshot(resident_id, revision) -> CapabilitySnapshot
apply_skill_practice(source_event_id, skill_id, difficulty, quality_q1000) -> SkillProgressResult
unlock_ability(source_event_id, ability_id, evidence_ids[]) -> AbilityUnlockResult
```

XP 增量由 Resident Catalog 的确定性表计算：`base_xp[difficulty] * quality_q1000 / 1000`，单事件 `1..200`，向下取整。

## 5. 规则与不变量

- `RULE-RESIDENT-024`：Skill rating 只能为 `0..100`；未知 Skill 不自动创建。
- `RULE-RESIDENT-025`：只有已提交且成功的练习/工作/战斗结果事件可授予 XP；提案、动画和失败尝试不授予。
- `RULE-RESIDENT-026`：相同 `(resident_id, source_event_id, skill_id)` 最多授予一次 XP。
- `RULE-RESIDENT-027`：Ability 解锁必须满足 Catalog 中 `required_skill_ratings` 与证据事件；删除资格须显式规则，不能由暂时受伤隐式删除。
- `RULE-RESIDENT-028`：Skill/Ability 只进入 owner 的前置校验；伤害、施法、制造和经济产出由各自 owner 计算。

## 6. 正常流程

1. 外部 owner 完成动作并提交结果事件。
2. Orchestrator 将允许成长的 `source_event_id`、difficulty 和 quality 传给 Resident。
3. Resident 幂等计算 XP、跨级并检查 unlock 条件。
4. 在同一事务提交 `ResidentSkillProgressed` 与可选 `ResidentAbilityUnlocked`。
5. 下游在最新 Revision 读取 Capability Snapshot。

## 7. 边界情况

- 一次 XP 可跨多个 Rating，但 Rating 100 后不再累积。
- 受伤导致能力当前不可用时由 Health restriction projection 表达，资格仍保留。
- 转职不清空技能或 ability。
- 非法来源事件、未来 Revision 或 owner 不匹配时不授予 XP。

## 8. 错误与降级

返回 `RESIDENT_SKILL_UNKNOWN`、`RESIDENT_PRACTICE_SOURCE_INVALID`、`RESIDENT_ABILITY_PREREQUISITE_MISSING`。Catalog 不可用时不授予成长，保留原能力，不使用模型猜测阈值。

## 9. 安全与性能

Client/模型不能提交 XP 数值或解锁结果。每居民最多 64 个非零 Skill、128 个 Ability；只传相关 Skill 子集给 AI。

## 10. 验收标准

- 成功/失败/重复来源事件的 XP 分别为一次/零/零。
- Rating 0、99、100 与跨级结果确定。
- 能力资格与当前可用性严格分离。
- 下游 owner 无法让 Resident 计算伤害、价格或产出。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-017` | XP 表、舍入、跨级与上限 |
| `TEST-RESIDENT-018` | source event 幂等与非法来源拒绝 |
| `TEST-RESIDENT-019` | Ability prerequisite Contract Test |
| `TEST-RESIDENT-020` | Health restriction 不删除 Ability |

## 12. 关联文档

- `DOC-RESIDENT-006`：职业资格引用
- `DOC-RESIDENT-007`：能力临时限制
- `DOC-ECON-010`：制造结算 owner
- `DOC-COMBAT-004`：战斗公式 owner

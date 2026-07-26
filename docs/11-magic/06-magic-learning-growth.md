---
doc_id: DOC-MAGIC-006
title: 魔法学习与成长
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - spell-knowledge-model
  - magic-learning-progress
  - school-skill-mapping
depends_on:
  - DOC-MAGIC-002
  - DOC-MAGIC-004
  - DOC-RESIDENT-005
  - DOC-TIME-006
  - DOC-ECON-004
requirements:
  - REQ-MAGIC-011
  - REQ-MAGIC-012
last_updated: 2026-07-26
---

# 魔法学习与成长

## 1. 目的

定义 `SpellKnowledge` 状态机、三类学习来源（教师、魔法书、练习）、SchoolSkill 技能门槛与学习进度结算，使"已学会"成为可验证的持久事实，并把魔法成长接入 `DOC-RESIDENT-005` 的既有技能/XP 机制而非另建一套。

## 2. 非目标

本文件不定义 SchoolSkill 的 XP 表与跨级规则（`DOC-RESIDENT-005` 拥有）、魔法书 Item 的所有权与交易（`DOC-ECON-004/006` 拥有，魔法侧定义见 `DOC-MAGIC-010`）、教师职业的排班与收入（`DOC-ECON-002/003`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `SpellKnowledge` | MAGIC 拥有的 per-caster 法术掌握记录：`unknown/studying/learned` |
| 教师 | 职业为法师/治疗者且自身已 `learned` 目标法术的居民 |
| 魔法书 | `magic_definition_id` 类型为 `spellbook` 的 magical Item |
| 学习会话 | `DOC-TIME-006` 长行动，按检查点累积 `study_progress` |
| 技能门槛 | `SpellDefinition.prerequisites.min_school_skill_rating` |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-011` | 六学派 SchoolSkill 是 `DOC-RESIDENT-005` Catalog 中的六个固定 Skill：`skill.magic.elemental/restoration/warding/illusion/spirit/arcane`，rating 语义、XP 结算与幂等完全沿用 Resident 规则；MAGIC 不维护第二套技能数值。 |
| `REQ-MAGIC-012` | `learned` 状态只能由已提交的学习完成事件产生；初始居民配置、教师签发或魔法书使用都必须落到同一状态机，不存在"天生全会"或模型宣称学会的路径。 |
| `RULE-MAGIC-029` | `SpellKnowledge` 状态机：`unknown → studying → learned`，无降级与遗忘；`studying` 必须绑定一个学习来源实例（教师会话、魔法书或练习计划）。 |
| `RULE-MAGIC-030` | 进入 `studying` 的前置：满足技能门槛、学派在该来源的 `learning_source_kinds`（`DES-MAGIC-002`）内、来源可用（教师同意且在场 / 魔法书在自己 Inventory 且未销毁）。 |
| `RULE-MAGIC-031` | 学习会话是排他长行动：`required_work_units` 由 `SpellDefinition` 学习难度表决定（`mana_cost` 每 10 点对应 2 work units，最少 4）；检查点重验来源可用性，来源失效转 `interrupted`。 |
| `RULE-MAGIC-032` | 教师教学需要教师方结构化同意（接受教学委托事件），可收费；费用走 ECON 交易事务，教学完成与否不影响已提交的收费事件。 |
| `RULE-MAGIC-033` | 施法与练习的 XP：每次成功 `SpellCastCommitted` 与每个学习检查点按 `DOC-RESIDENT-005` `apply_skill_practice` 提交对应学派 XP，`source_event_id` 幂等去重；失败施法与被拒提案不产生 XP（`RULE-RESIDENT-025`）。 |
| `RULE-MAGIC-034` | 玩家角色与 AI 居民使用同一状态机、门槛与进度规则；镇长模式与 AdminCommand 不能直接置 `learned`，Admin 修正必须走显式 source event 并审计（`RULE-FOUNDATION-030`）。 |

## 5. 数据与接口

`DES-MAGIC-006`：注册 `schema.magic.spell_knowledge.v1`：

```json
{
  "knowledge_schema_version": 1,
  "caster_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "entries": [
    {
      "spell_id": "spell.restoration.minor_mend",
      "state": "learned",
      "learned_at_game_time": 2880,
      "source_kind": "teacher",
      "source_ref": "01K1AB2CD3EF4GH5JK6MNP7QRT"
    },
    {
      "spell_id": "spell.arcane.detect_magic",
      "state": "studying",
      "study_long_action_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
      "source_kind": "spellbook",
      "source_ref": "01K1AB2CD3EF4GH5JK6MNP7QRW"
    }
  ],
  "knowledge_revision": 9
}
```

`source_kind` 枚举：`teacher/spellbook/practice/initialization`。`initialization` 仅用于世界创建时按居民模板预置的 `learned` 条目，同样携带 source event。

Port：

```text
get_spell_knowledge(caster_id, revision) -> SpellKnowledge
begin_study(command_id, caster_id, spell_id, source) -> StudyStarted | Rejection
complete_study_checkpoint(long_action_id, checkpoint_index) -> CheckpointResult
```

## 6. 正常流程

1. 居民（AI 提案或玩家命令）选择目标法术与来源，`begin_study` 校验 `RULE-MAGIC-030`。
2. TIME 调度学习长行动；每检查点提交进度事件并按 `RULE-MAGIC-033` 授予学派 XP。
3. `completed_work_units` 达到 `required_work_units` 时，完成事务写 `SpellLearned`、置 `learned` 并释放来源 Reservation。
4. Capability Builder 在下一次上下文构建中把新法术纳入候选（`DOC-MAGIC-007`）。

## 7. 边界情况

- 技能门槛在学习中途才达到：允许先学低门槛法术积累 XP；`begin_study` 时不满足门槛直接拒绝，不支持"边学边够"。
- 魔法书在学习中被出售或转移出 Inventory：检查点来源重验失败，会话 `interrupted`，进度保留，重新取得书后可 `resume`。
- 教师中途拒绝继续：同上转 `interrupted`；已付学费不自动退还，退费是独立 ECON 交易。
- 同一法术并发两个学习会话：违反排他长行动约束（`RULE-FOUNDATION-028`），第二个拒绝。
- 居民模板预置法术必须同时预置满足门槛的 SchoolSkill rating，构建期校验。

## 8. 错误与降级

`begin_study` 返回 `MAGIC_STUDY_PREREQUISITE_MISSING`、`MAGIC_STUDY_SOURCE_UNAVAILABLE`、`MAGIC_SPELL_UNKNOWN` 或 `MAGIC_ALREADY_LEARNED`。Resident 技能服务不可用时学习检查点整体失败重试，不跳过 XP 结算单独推进度，保证进度与成长不撕裂。

## 9. 安全与性能

`SpellKnowledge` 无 Secret，但教师收费与私下教学关系属 ECON/MEMORY 各自访问规则。每施法者 entries 上限 64 条。AI 上下文只注入 `learned` 与 `studying` 摘要，不注入全 Catalog 未学法术明细，控制 token 成本（`DOC-AI-008`）。

## 10. 验收标准

- 三类来源各有从 `unknown` 到 `learned` 的端到端用例，事件链完整可重放。
- 未达门槛、来源失效、并发会话、重复学习均被正确拒绝或中断。
- 施法/检查点 XP 与 `DOC-RESIDENT-005` 结算逐事件对账一致，无双记账。
- Admin 直接置 `learned` 的尝试被拒绝，显式修正路径留有审计。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-013` | `REQ-MAGIC-011..012`, `RULE-MAGIC-029..031` | 状态机与三来源端到端 Integration Test；中断/恢复进度保持 |
| `TEST-MAGIC-014` | `RULE-MAGIC-032..034` | 教学同意与收费事务、XP 幂等对账、Admin 绕过反例 |

## 12. 关联文档

- `DOC-RESIDENT-005`：SchoolSkill rating、XP 与 Ability 的唯一权威
- `DOC-MAGIC-004`：技能门槛与学习难度来源字段
- `DOC-MAGIC-010`：魔法书的 `magic_definition_id` 定义
- `DOC-TIME-006`：学习长行动生命周期
- `DOC-ECON-006`：学费交易事务

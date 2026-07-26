---
doc_id: DOC-MAGIC-003
title: Mana 与恢复
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - mana-model
  - mana-regeneration
  - mana-exhaustion
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAGIC-001
  - DOC-RESIDENT-005
  - DOC-TIME-008
requirements:
  - REQ-MAGIC-005
  - REQ-MAGIC-006
last_updated: 2026-07-26
---

# Mana 与恢复

## 1. 目的

定义 Mana 的唯一数据模型、单位、上限公式、周期恢复、环境修正与枯竭状态，使全部施法消耗可验证、可重放，并把星织潮强度（`DOC-MAGIC-001`）落地为确定性的恢复输入。

## 2. 非目标

本文件不定义单个法术的 `mana_cost` 数值（`DOC-MAGIC-004`）、施法校验顺序（`DOC-MAGIC-005`）或战斗内 MP 结算细则（`DOC-COMBAT-004` 消费本模型但拥有战斗公式）。不引入第二种魔力资源（如怒气、信仰值）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Mana | 施法唯一消耗资源，整数点数，中文显示"魔力" |
| `CasterState` | MAGIC 拥有的施法者聚合：Mana、冷却与疲劳标志 |
| 恢复周期 | 每 10 game minutes 一次的确定性 Mana 恢复结算 |
| 星织潮修正 | TIME 推进、按 q1000 定点数发布的环境恢复系数 |
| Mana 枯竭 | `mana_current` 低于枯竭阈值后进入的临时禁施法状态 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-005` | Mana 只以整数点数存储，`0 <= mana_current <= mana_max`；`mana_max = 60 + max(六学派 SchoolSkill rating)`，范围 `60..160`。任何负值、小数或超上限值在提交检查即拒绝。 |
| `REQ-MAGIC-006` | Mana 恢复必须通过 `DOC-TIME-008` Event Queue 的周期任务结算，公式确定性、可由 `(seed, stream_id, sequence)` 之外的纯状态输入重放；禁止逐 Tick 浮点累积。 |
| `RULE-MAGIC-009` | `CasterState` 是 Mana 的唯一真值，owner 为 MAGIC；Resident 聚合、AI、Client 与模型输出不得写入 Mana 数值（沿用 `RULE-FOUNDATION-016`）。 |
| `RULE-MAGIC-010` | 每恢复周期增量为 `regen = floor(base_regen * tide_q1000 / 1000 * activity_mult)`，`base_regen = 3`；`activity_mult`：休息中 2、常规 1、Encounter 内 0。结果与 `mana_max` 取较小值。 |
| `RULE-MAGIC-011` | `tide_q1000` 为星织潮修正与 `ley_anchor_presence` 加成的合成值，量化为 q1000 整数并夹取到 `500..1500`；输入缺失时按 `1000` 处理并记录诊断（对应 `DOC-MAGIC-001` §8）。 |
| `RULE-MAGIC-012` | Mana 枯竭：`mana_current < 10` 时置 `mana_exhausted = true`，期间一切 `cast_spell` 前置校验直接拒绝；`mana_current >= 30` 时解除。阈值为 Catalog 常量，不随法术或角色变化。 |
| `RULE-MAGIC-013` | Mana 消耗只发生在 `SpellCastCommitted` 同一事务内；施法失败、提案被拒或 VFX 播放不扣 Mana。相同 `(caster_id, source_event_id)` 的消耗最多结算一次。 |
| `RULE-MAGIC-014` | Mana 不是货币或 Item：不可交易、转移、存入容器或折算铜羽；魔法物品充能（`DOC-MAGIC-010`）是独立的 Item 侧状态，只能经注册充能流程消耗施法者 Mana。 |

## 5. 数据与接口

`DES-MAGIC-003`：注册 `schema.magic.caster_state.v1`，required 字段为
`caster_schema_version/caster_id/mana_current/mana_max/mana_exhausted/cooldowns/state_revision`：

```json
{
  "caster_schema_version": 1,
  "caster_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "mana_current": 42,
  "mana_max": 124,
  "mana_exhausted": false,
  "cooldowns": [
    {"spell_id": "spell.restoration.minor_mend", "ready_at_game_time": 1860}
  ],
  "state_revision": 17
}
```

周期任务在 `DOC-TIME-008` 目录登记：

| `periodic_definition_id` | phase | interval | owner |
|---|---|---|---|
| `periodic.magic.mana_regeneration` | 2 | 10 game minutes | MAGIC |

Port：

```text
get_caster_state(caster_id, revision) -> CasterState
settle_mana_regeneration(occurrence_key, caster_ids[]) -> ManaRegenResult
consume_mana(source_event_id, caster_id, amount, expected_state_revision) -> ManaConsumeResult
```

## 6. 正常流程

1. TIME 按 anchor 触发 `periodic.magic.mana_regeneration` occurrence。
2. MAGIC 读取当前星织潮修正、施法者所在位置的 `ley_anchor_presence` 与活动状态。
3. 按 `RULE-MAGIC-010..011` 逐施法者计算增量，批量提交 `ManaRegenerated` 事件并递增 `state_revision`。
4. 施法路径（`DOC-MAGIC-005`）在提交事务内调用 `consume_mana`，与效果事件原子成败。
5. 枯竭标志变化作为同事务派生字段更新，供 AI Capability Builder 过滤候选法术。

## 7. 边界情况

- 高倍速或 catch-up：恢复任务满足 `RULE-TIME-048` 的可聚合条件（结合律、与顺序无关、守恒安全），允许按错过的 occurrence 数一次性聚合结算，逐 occurrence 上限仍生效。
- `mana_max` 因 SchoolSkill 提升而增长时，`mana_current` 保持不变，不自动补满。
- SchoolSkill 不会下降（`DOC-RESIDENT-005` 无降级路径），因此不存在 `mana_current > mana_max` 的技能侧成因；任何该形态一律视为数据损坏并触发恢复审计。
- Encounter 内 `activity_mult = 0`：战斗中 Mana 只出不进，战斗内额外恢复手段归 `DOC-COMBAT-004` 定义且仍经 `consume_mana`/结算口径。
- 新居民初始化：`mana_current = mana_max`，无冷却、无枯竭标志。

## 8. 错误与降级

`consume_mana` 返回 `MAGIC_MANA_INSUFFICIENT`、`MAGIC_CASTER_EXHAUSTED`、`MAGIC_CASTER_UNKNOWN` 或 `stale_revision`，均不产生状态变化。恢复任务单个施法者结算失败只跳过该施法者并记录诊断，不阻塞批次；星织潮或天气投影缺失按 `RULE-MAGIC-011` 中性值降级。

## 9. 安全与性能

Mana 数值不含 Secret，可进入任何决策上下文。恢复结算按施法者分片批量执行，单 occurrence 处理上限 64 名施法者，超出部分顺延到同 phase 的后续 lease，不做全表扫描。Client 展示的 Mana 条只消费已提交事件，预测动画不改变真值。

## 10. 验收标准

- 任意 `CasterState` 序列重放后 `mana_current/mana_max/mana_exhausted` 与首次执行逐位一致。
- 注入负值、小数、超上限与重复 `source_event_id` 消耗均被拒绝且 Revision 不增长。
- 枯竭进入/解除阈值行为与 `RULE-MAGIC-012` 完全一致，无中间抖动状态。
- 暂停、倍率 4 与 30 游戏日模拟下恢复总量与逐周期基线一致。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-005` | `REQ-MAGIC-005..006`, `RULE-MAGIC-009..011` | 恢复公式 Table Test（tide 500/1000/1500 × 活动三态）；catch-up 聚合与逐 occurrence 等价性 |
| `TEST-MAGIC-006` | `RULE-MAGIC-012..014` | 枯竭阈值状态机测试；消耗幂等与 Mana 不可交易反例注入 |

## 12. 关联文档

- `DOC-MAGIC-001`：星织潮修正与 `ley_anchor_presence` 挂钩的世界观来源
- `DOC-MAGIC-004`：`mana_cost` 声明
- `DOC-MAGIC-005`：消耗发生的施法事务
- `DOC-MAGIC-010`：魔法物品充能对 Mana 的消耗
- `DOC-TIME-008`：周期任务队列与 catch-up 语义
- `DOC-RESIDENT-005`：SchoolSkill rating 来源

---
doc_id: DOC-COMBAT-002
title: 回合顺序与回合生命周期
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - turn-time-lifecycle
  - initiative-order
  - turn-state-machine
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-010
  - DOC-COMBAT-001
requirements:
  - REQ-COMBAT-002
last_updated: 2026-07-26
---

# 回合顺序与回合生命周期

## 1. 目的

`REQ-COMBAT-002`：定义 Encounter 内 TurnTime 的 round/turn/phase 结构、基于 Agility 的确定性 initiative 排序、单回合状态机与轮转规则，使任意已提交 Encounter 状态在重放时得到完全相同的行动顺序。

## 2. 非目标

不定义合法行动集合与目标规则（`DOC-COMBAT-003`）、属性来源与掷骰公式（`DOC-COMBAT-004`）、结果结算（`DOC-COMBAT-006`）或终结条件语义（`DOC-COMBAT-009`）；不定义 AI 决策的 RealTime deadline 数值以外的调度细节（`DOC-COMBAT-007`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Round | 一轮全体存活 Combatant 各行动至多一次的 TurnTime 单元，`round_index` 从 0 递增 |
| Turn | 单个 Combatant 的一次行动机会，`turn_index` 在 Encounter 内全局单调递增 |
| Phase | 封闭 enum `round_start/actor_turn/round_end`，`RULE-FOUNDATION-037` 的 TurnTime 表达 |
| Initiative | round_start 计算的行动排序键，本文唯一定义 |
| Turn Owner | 当前 `actor_turn` 绑定的 Combatant，仅其可提交 `combat_action` |
| Round Cap | 强制终结前允许的最大 round 数 |

## 4. 规则与不变量

- `RULE-COMBAT-007`：TurnTime 只以 `(round_index, turn_index, phase)` 表达且不与 GameTime 换算；Encounter Active 期间 Overworld 处于 `DOC-COMBAT-001` 的 combat Pause Token 下，GameTime 不推进。
- `RULE-COMBAT-008`：每个 round_start 为每名 `combat_state=active` 的 Combatant 计算 `initiative_q1000 = agility * 1000 + tiebreak_roll`；`tiebreak_roll` 来自 `DOC-TIME-010` stream `combat.initiative`、scope 为 `encounter_id` 的 `draw_bounded_uint32(1000)`，按 `combatant_id` ULID 升序消费 draw sequence。排序为 `initiative_q1000` 降序，仍相等时按 `combatant_id` 升序。
- `RULE-COMBAT-009`：round 内顺序在 round_start 提交后冻结；回合中途的 Agility 变化只影响下一 round。新增召唤 Combatant 在下一 round 才进入排序。
- `RULE-COMBAT-010`：Turn 状态机封闭为 `pending -> awaiting_decision -> decision_received -> resolved` 与 `pending -> skipped`；`skipped` 仅允许原因 `defeated_down/fled/surrendered/control_status`，并必须记录 reason。
- `RULE-COMBAT-011`：同一 `(encounter_id, turn_index)` 至多提交一个已解析 `combat_action`；携带过期 `turn_index` 的提交返回 `COMBAT_TURN_STALE` 且无状态变化。
- `RULE-COMBAT-012`：`round_index` 达到 Round Cap（首版 200）时，本 round_end 强制进入 `DOC-COMBAT-009` 的 `round_cap_forced` 终结流程；不允许无限战斗。

## 5. 数据与接口

`DES-COMBAT-002`：注册 `schema.combat.turn_state.v1`；required 字段为
`turn_schema_version/encounter_id/round_index/turn_index/phase/turn_order/current_combatant_id/turn_status/skip_reason`。
`skip_reason` 仅在 `turn_status=skipped` 时非 null。

```json
{
  "turn_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "round_index": 3,
  "turn_index": 11,
  "phase": "actor_turn",
  "turn_order": [
    {"combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC", "initiative_q1000": 42731},
    {"combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD", "initiative_q1000": 30112}
  ],
  "current_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
  "turn_status": "awaiting_decision",
  "skip_reason": null
}
```

接口：

```text
get_turn_state(encounter_id) -> TurnStateView
advance_turn(command_id, encounter_id, expected_turn_index) -> TurnAdvanceResult
```

`advance_turn` 由服务器 Orchestrator 在上一 Turn 解析事务提交后调用，不暴露给 Client 或模型。

## 6. 正常流程

1. Encounter 进入 `active` 后开始 round 0 的 round_start：结算 round 级状态效果计时（`DOC-COMBAT-005`），计算并提交 initiative 排序。
2. 按排序逐个进入 `actor_turn`：Turn Owner 为玩家则等待 PlayerCommand，为 AI 则触发 `DOC-COMBAT-007` 决策。
3. 决策经 `DOC-COMBAT-003` 合法性校验后，由 `DOC-COMBAT-006` 在单事务解析并提交 `CombatActionResolved`。
4. 同一事务评估 `DOC-COMBAT-009` 终结条件；未终结则 `turn_index + 1` 推进到下一 Combatant。
5. 全部 Combatant 行动或跳过后进入 round_end，随后 `round_index + 1` 回到步骤 1。

## 7. 边界情况

- Turn Owner 在自己回合开始前被击倒（例如 round_start 的持续伤害）：该 Turn 标记 `skipped/defeated_down`，不消耗决策请求。
- 两名 Combatant Agility 与 tiebreak_roll 全相等：按 `combatant_id` 升序，顺序仍确定。
- round 中有 Combatant 逃跑成功：其剩余 Turn 标记 `skipped/fled`，已冻结顺序不重排。
- 崩溃后恢复：Turn 状态机的每次迁移都是已提交事务，加载后从最后提交的 `(round_index, turn_index, phase)` 继续；initiative 不重掷（draw sequence 已消费并提交）。
- Encounter 只剩一方存活但当前 phase 为 round_start：终结条件在任何状态迁移事务中均被评估，不必等到 actor_turn。

## 8. 错误与降级

`COMBAT_TURN_STALE`、`COMBAT_TURN_NOT_OWNER`（非 Turn Owner 提交）、`COMBAT_TURN_PHASE_INVALID`（在非 actor_turn 提交行动）均拒绝且 Revision 不增长。initiative draw 的随机服务不可用时，按 `DOC-TIME-010` 不得改用非确定随机；Encounter 保持当前 phase 暂停并告警，不构造伪随机顺序。

## 9. 安全与性能

排序计算为每 round O(n log n)，n 上限 8（双方各 4）。Client 与模型只读 TurnStateView，不能提交 phase 迁移。turn_order 不携带对方隐藏属性，只含 combatant_id 与 initiative 结果。

## 10. 验收标准

- 相同 Seed、相同参战配置重放 100 次，得到逐字节一致的 turn_order 序列。
- 过期 turn_index、非 Owner 提交、错误 phase 提交全部被拒绝且无状态变化。
- 击倒、逃跑、投降、控制状态四种 skip 原因均正确记录。
- Round Cap 到达时强制终结且不产生第 201 个 round。
- 崩溃恢复后行动顺序与崩溃前已提交状态一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-002` | initiative 确定性、tiebreak 与 draw sequence 消费（`RULE-COMBAT-008..009`） |
| `TEST-COMBAT-003` | Turn 状态机合法迁移、skip 原因与 stale 拒绝（`RULE-COMBAT-010..011`） |
| `TEST-COMBAT-004` | Round Cap 强制终结与恢复后顺序一致（`RULE-COMBAT-007`, `RULE-COMBAT-012`） |

## 12. 关联文档

- `DOC-COMBAT-001`：Encounter aggregate 与 Pause Token
- `DOC-COMBAT-003`：Turn Owner 的合法行动集合
- `DOC-COMBAT-005`：round_start/turn 内状态效果计时
- `DOC-COMBAT-009`：终结条件与 round_cap_forced
- `DOC-TIME-010`：`combat.initiative` 随机流

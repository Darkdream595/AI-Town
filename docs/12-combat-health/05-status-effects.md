---
doc_id: DOC-COMBAT-005
title: 状态效果与叠加规则
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - status-effect-registry
  - status-stacking-rules
  - status-tick-resolution
depends_on:
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-007
  - DOC-COMBAT-002
  - DOC-COMBAT-004
requirements:
  - REQ-COMBAT-005
last_updated: 2026-07-26
---

# 状态效果与叠加规则

## 1. 目的

`REQ-COMBAT-005`：定义 Encounter 内状态效果的注册模型、施加与叠加策略、确定性 tick 顺序、到期清理，以及战斗结束时向 Resident 持久 Injury/Illness 的转换入口，使增益、减益、持续伤害与控制效果全部可审计、可重放。

## 2. 非目标

不定义具体法术如何施加效果（`DOC-MAGIC-004` SpellDefinition 引用本文注册表）、每 tick 数值公式的计算细节（`DOC-COMBAT-004`）、结算落账（`DOC-COMBAT-006`）或持久 Injury/Illness 的语义（`DOC-RESIDENT-007`）。Overworld 的非战斗持续状态不属于本文。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| StatusDefinition | Stable Catalog ID `status.*` 注册的效果模板 |
| Status Instance | Encounter 内施加在单个 Combatant 上的效果实例，ULID 标识 |
| Category | 封闭 enum：`buff/debuff/damage_over_time/heal_over_time/control` |
| Stacking Policy | 封闭 enum：`refresh_duration/stack_intensity/independent_instances/reject_duplicate` |
| Tick | 在被施加者 `actor_turn` 开始时执行的一次效果结算 |
| Persist Mapping | 效果注册的战后转换目标：null 或 `injury.*`/`illness.*` definition |

## 4. 规则与不变量

- `RULE-COMBAT-026`：Status Instance 只能由已解析行动、法术效果或 Encounter 规则在解析事务内施加，必须引用注册 StatusDefinition 与 `source_event_id`；施加判定若有概率，使用 `DOC-COMBAT-004` 的 Roll 规则。
- `RULE-COMBAT-027`：StatusDefinition 必须声明 `category/attribute_deltas/per_tick_formula_ref/duration_turns(1..20)/stacking_policy/max_stacks(1..5)/persist_mapping`；`control` 类必须声明被禁止的 Action Kind 集合。
- `RULE-COMBAT-028`：叠加按注册策略执行：`refresh_duration` 重置剩余回合不增强度；`stack_intensity` 强度层数加一至 `max_stacks`，超出拒绝并保留原实例；`independent_instances` 并存独立实例；`reject_duplicate` 拒绝第二次施加。同一 definition 只允许一种策略。
- `RULE-COMBAT-029`：Tick 在被施加者 Turn 进入 `actor_turn` 时、行动决策之前执行；同一 Combatant 的多个实例按 Status Instance ULID 升序结算。tick 后 `remaining_turns - 1`，减到 0 的实例在同一事务移除并记录 `StatusExpired`。
- `RULE-COMBAT-030`：Attribute 修正是派生投影：有效属性 = `clamp(sheet 基础值 + 全部活跃实例 attribute_deltas 之和, 1, 200)`；实例移除即失效，不回写 CombatantSheet 基础值。
- `RULE-COMBAT-031`：Encounter 终结时所有 Status Instance 结束；`persist_mapping` 非 null 且宿主为 Resident 型 Combatant 的，在 `DOC-COMBAT-006` 结果结算中转换为对应 Injury/Illness 效果提交，其余不留任何 Overworld 残留。

## 5. 数据与接口

`DES-COMBAT-005`：注册 `schema.combat.status_instance.v1`；required 字段为
`status_schema_version/status_instance_id/encounter_id/definition_id/holder_combatant_id/source_event_id/stack_count/remaining_turns/applied_at_turn_index`。

```json
{
  "status_schema_version": 1,
  "status_instance_id": "01K1AB2CD3EF4GH5JK6MNP7QSG",
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "definition_id": "status.burning",
  "holder_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD",
  "source_event_id": "01K1AB2CD3EF4GH5JK6MNP7QSH",
  "stack_count": 2,
  "remaining_turns": 3,
  "applied_at_turn_index": 11
}
```

StatusDefinition 注册示例（构建期数据，非运行时事件）：

```json
{
  "definition_id": "status.burning",
  "category": "damage_over_time",
  "attribute_deltas": {},
  "per_tick_formula_ref": "combat_formula.v1.dot_burning",
  "duration_turns": 3,
  "stacking_policy": "stack_intensity",
  "max_stacks": 3,
  "forbidden_action_kinds": [],
  "persist_mapping": "injury.burn_wound"
}
```

接口：

```text
apply_status(resolution_context, definition_id, holder_combatant_id) -> StatusApplyOutcome
tick_statuses(encounter_id, holder_combatant_id, turn_index) -> StatusTickOutcome[]
```

二者只在 Turn/round 解析事务内由 Orchestrator 调用。

## 6. 正常流程

1. 行动解析产生施加意图，按注册概率掷骰后调用 `apply_status`。
2. 依 Stacking Policy 创建/刷新/加层实例，写入 Encounter aggregate 并发 `StatusApplied`。
3. 宿主的下一次 `actor_turn` 开始时 `tick_statuses` 依序结算每实例的 `per_tick_formula_ref`，HP 变化交 `DOC-COMBAT-006` 同事务应用。
4. `remaining_turns` 归零实例移除；`control` 类活跃期间由 `DOC-COMBAT-003` 在派生阶段过滤被禁 Action Kind。
5. Encounter 终结时统一清理并执行 Persist Mapping 转换。

## 7. 边界情况

- tick 造成宿主 HP 归零：宿主转 `down`，其本次 Turn 按 `DOC-COMBAT-002` 标记 `skipped/defeated_down`。
- `stack_intensity` 达 `max_stacks` 再施加：拒绝加层但刷新 `remaining_turns` 为注册时长（该行为属于策略定义，注册表固定）。
- 控制效果禁止全部主动 Kind：`DOC-COMBAT-002` 直接 skip 该 Turn（`control_status`），不进入决策。
- 净化类行动移除实例：按 category 匹配、实例 ULID 升序移除注册数量，移除即时生效。
- 同一事务施加与到期同时发生（duration 1 的效果在自身 tick 到期）：先结算 tick 再移除，顺序固定。

## 8. 错误与降级

未注册 definition、越界 duration/stacks、非法 category 返回 `COMBAT_STATUS_DEFINITION_INVALID` 并使解析事务回滚。Persist Mapping 指向未注册 Injury/Illness definition 属于构建期错误，注册表校验失败即启动失败，不在运行时降级。

## 9. 安全与性能

单 Combatant 活跃实例上限 16，超限的新施加被拒绝并记录。tick 结算为 O(实例数) 整数运算。状态效果的展示文案来自注册表本地化条目，不含模型生成文本；render projection 只携带 definition_id 与层数。

## 10. 验收标准

- 四种 Stacking Policy 各自的施加序列产生注册所定义的唯一结果。
- tick 顺序、到期移除与控制过滤在固定 fixture 下 100 次重放一致。
- 效果修正后的有效属性始终在 `[1, 200]`，实例移除后立即还原。
- Encounter 终结后无任何战斗状态实例残留；Persist Mapping 正确转换为 Injury/Illness。
- 实例上限与未注册 definition 拒绝生效。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-011` | 注册约束与四种叠加策略（`RULE-COMBAT-026..028`） |
| `TEST-COMBAT-012` | tick 顺序、到期、控制过滤与属性投影（`RULE-COMBAT-029..030`） |
| `TEST-COMBAT-013` | 终结清理与 Persist Mapping 转换（`RULE-COMBAT-031`） |

## 12. 关联文档

- `DOC-COMBAT-002`：tick 所在 phase 与 control skip
- `DOC-COMBAT-003`：`control` 类对合法集合的过滤
- `DOC-COMBAT-004`：`per_tick_formula_ref` 公式与施加掷骰
- `DOC-COMBAT-006`：tick HP 变化与战后转换的结算 owner
- `DOC-RESIDENT-007`：Injury/Illness 持久语义

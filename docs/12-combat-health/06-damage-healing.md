---
doc_id: DOC-COMBAT-006
title: 伤害治疗结算与战后持久化
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - damage-healing-settlement
  - combat-health-effect-handoff
  - post-battle-health-persistence
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-007
  - DOC-MAGIC-003
  - DOC-COMBAT-002
  - DOC-COMBAT-003
  - DOC-COMBAT-004
  - DOC-COMBAT-005
requirements:
  - REQ-COMBAT-006
last_updated: 2026-07-26
---

# 伤害治疗结算与战后持久化

## 1. 目的

`REQ-COMBAT-006`：确立 COMBAT 作为 damage/healing 数值结果的 canonical owner（`RULE-RESIDENT-036` 的对端），定义 Turn 解析事务如何把 `FormulaOutcome` 应用到 CombatantSheet，以及 Encounter 终结时向 RESIDENT/MAGIC 的一次性幂等持久化，保证战斗伤病跨存档持续且永不重复落账。

## 2. 非目标

不定义公式本身（`DOC-COMBAT-004`）、状态效果语义（`DOC-COMBAT-005`）、defeat outcome 选择（`DOC-COMBAT-009`）或结果事务的完整跨域清单（`DOC-COMBAT-011`）；不拥有 Resident 持久 health_state（`DOC-RESIDENT-007`）或 Mana 存量（`DOC-MAGIC-003`）的 Schema。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Turn 解析事务 | 一次 `combat_action` 从校验到 `CombatActionResolved` 提交的单事务 |
| In-Encounter HP/MP | Encounter Active 期间 CombatantSheet 上的权威当前值 |
| Down | `combat_state=down`：In-Encounter HP 为 0，仍可被复苏 |
| Settlement | Encounter 终结事务中对 Resident/MAGIC 的聚合持久化 |
| Injury Threshold Table | 注册的确定性伤情转换表（受创程度 -> `injury.*`） |
| Stabilized 标记 | `assist` 稳定化在 down Combatant 上留下的事实标记 |

## 4. 规则与不变量

- `RULE-COMBAT-032`：Encounter Active 期间，参战者的 HP/MP 当前值以 CombatantSheet 为唯一权威；Resident aggregate 的 health_state 与 Mana 在此期间不被逐回合改写。每次 Turn 解析事务把 `FormulaOutcome` 全量 delta 原子应用并提交 `CombatActionResolved`（含完整数值明细）。
- `RULE-COMBAT-033`：In-Encounter HP 下界 0、上界 `hp_max`，治疗超出上限截断但记录实际 applied delta；MP 下界 0，不足支付即选项非法（`DOC-COMBAT-003`）。HP 减到 0 的 Combatant 同事务转 `combat_state=down`；对 down 目标施放注册复苏效果可使其以效果数值回到 `active`。
- `RULE-COMBAT-034`：Creature/summon 型 Combatant HP 归零可直接进入 `down` 并在终结时死亡/消散移除；Resident 型永不因归零删除，其终局由 `DOC-COMBAT-009` 映射为非永久 defeat outcome（`RULE-FOUNDATION-025`）。
- `RULE-COMBAT-035`：Settlement 在 Encounter 终结事务中恰好执行一次：对每名 Resident 型 Combatant 以 `EncounterResolved` 为 `source_event_id`，提交聚合 `HealthEffectCommand`（终态 HP、Injury 转换）与 MAGIC mana 结算命令；RESIDENT/MAGIC 按各自幂等键去重（`RULE-RESIDENT-039`），重放不二次落账。
- `RULE-COMBAT-036`：Injury 转换完全确定性：按 Injury Threshold Table 依据终态 HP 比例、累计受创类型与 `DOC-COMBAT-005` Persist Mapping 生成 Injury/Illness 效果，不使用终结事务外的掷骰。战后不存在自动满血：未治疗的 HP 与伤病原样持久。
- `RULE-COMBAT-037`：任何 damage/healing 数值只能产生于 `resolve_formula` 输出；模型、Client、事件重放器都不能注入或修改 delta。`CombatActionResolved` 的数值明细与重算结果不一致时视为一致性错误，禁止继续提交后续 Turn。

## 5. 数据与接口

`DES-COMBAT-006`：`CombatActionResolved` payload 注册为 `schema.combat.action_resolved.v1`；required 字段为
`resolved_schema_version/encounter_id/turn_index/actor_combatant_id/option_id/target_outcomes/status_changes/mp_spent/rolls`。

```json
{
  "resolved_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "turn_index": 11,
  "actor_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
  "option_id": "combat_option.attack",
  "target_outcomes": [
    {
      "target_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD",
      "hit": true,
      "critical": false,
      "hp_delta": -7,
      "hp_after": 5,
      "combat_state_after": "active"
    }
  ],
  "status_changes": [],
  "mp_spent": 0,
  "rolls": [{"slot": "hit", "value": 412}, {"slot": "variance", "value": 63}]
}
```

Settlement 聚合结构 `schema.combat.settlement.v1`（终结事务内部构件，required
`settlement_schema_version/encounter_id/resident_settlements`）：

```json
{
  "settlement_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "resident_settlements": [
    {
      "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRR",
      "final_hp": 5,
      "hp_delta_total": -19,
      "mp_delta_total": -4,
      "injury_effects": ["injury.burn_wound"],
      "stabilized": false
    }
  ]
}
```

接口：

```text
apply_formula_outcome(resolution_context, formula_outcome) -> AppliedResolution
build_settlement(encounter_id) -> CombatSettlement
```

## 6. 正常流程

1. `DOC-COMBAT-003` 复验通过的行动进入 Turn 解析事务。
2. `DOC-COMBAT-004` 计算 `FormulaOutcome`；本文将 delta 应用到 CombatantSheet，处理 down/复苏转换与状态施加。
3. `CombatActionResolved` 与状态变化、draw sequence 增长原子提交，前端据此播放 VFX（`DOC-RENDER-008`）。
4. Encounter 终结时 `build_settlement` 从已提交回合明细聚合终态，作为 `DOC-COMBAT-011` 结果事务的一部分提交给 RESIDENT/MAGIC。
5. RESIDENT 应用聚合 Health Effect，HP 为 0 者由其唯一 lifecycle 状态机进入 `defeated + outcome`（`RULE-RESIDENT-035`）。

## 7. 边界情况

- 同一行动多目标且部分目标 down：down 目标不在攻击合法目标集合内，仅注册的复苏/稳定化效果可指向 down 目标。
- 复苏后再次归零：允许，每次转换都有事件记录；terminal 判定只看终结时刻状态。
- Encounter 期间 Resident 的 Overworld health_state 被其他系统修改：Overworld 已暂停且 actor 被 Reservation 锁定（`DOC-COMBAT-001`），不存在该并发；Settlement 提交时仍以 `expected_revision` 复验。
- 崩溃于终结事务前：重启后 Encounter 仍 Active，从已提交 Turn 继续；崩溃于终结事务后：Settlement 已随之提交，幂等键保证重放不重复。
- 玩家 Resident 与 AI Resident 的 Settlement 完全同规则，无特殊豁免。

## 8. 错误与降级

`COMBAT_RESOLUTION_MISMATCH`（明细重算不一致）、`COMBAT_SETTLEMENT_DUPLICATE`（幂等键冲突返回原结果引用）、`COMBAT_SETTLEMENT_REVISION_STALE`。RESIDENT/MAGIC 暂不可用时终结事务整体失败并重试；不允许只落一半的 Settlement（`RULE-FOUNDATION-029`）。

## 9. 安全与性能

Turn 解析为纯内存整数计算加单事务写入，目标 P95 < 50 real ms。`CombatActionResolved` 面向玩家的 render projection 只含克制描述与数值结果，不含公式内部量；对方 Resident 的隐私字段不进入 payload。

## 10. 验收标准

- 每次行动的 HP/MP 变化恰好应用一次，重放事件流可逐字节重建 CombatantSheet 终态。
- down/复苏/再次 down 序列正确且 Resident 永无删除。
- Settlement 幂等：终结事务重放不产生第二次 Health/Mana 变更。
- 战后 HP 与 Injury 跨存档保持，不自动回满。
- 注入篡改数值的明细被检测并阻止后续提交。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-014` | In-Encounter 权威、clamp、down/复苏（`RULE-COMBAT-032..034`） |
| `TEST-COMBAT-015` | Settlement 幂等、聚合正确性与崩溃时机矩阵（`RULE-COMBAT-035`） |
| `TEST-COMBAT-016` | Injury 转换确定性与数值防篡改（`RULE-COMBAT-036..037`） |

## 12. 关联文档

- `DOC-RESIDENT-007`：Health Effect 应用与 `RULE-RESIDENT-036/039`
- `DOC-RESIDENT-008`：HP 为 0 的 lifecycle 转换
- `DOC-COMBAT-009`：终局 outcome 映射
- `DOC-COMBAT-011`：终结事务的完整跨域清单
- `DOC-MAGIC-003`：Mana 结算对端

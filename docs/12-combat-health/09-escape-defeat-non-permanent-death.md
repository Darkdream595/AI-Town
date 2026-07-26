---
doc_id: DOC-COMBAT-009
title: 逃脱、失败与非永久死亡
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - encounter-end-conditions
  - combat-defeat-outcome-mapping
  - combat-rescue-retreat
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-007
  - DOC-RESIDENT-008
  - DOC-COMBAT-001
  - DOC-COMBAT-002
  - DOC-COMBAT-003
  - DOC-COMBAT-006
requirements:
  - REQ-COMBAT-009
last_updated: 2026-07-26
---

# 逃脱、失败与非永久死亡

## 1. 目的

`REQ-COMBAT-009`：定义 Encounter 的封闭终结条件集合，以及每名 Resident 型 Combatant 从战斗终态到 `DOC-RESIDENT-008` 非永久 defeat outcome（`unconscious/severely_injured/retreated/captive`）的确定性映射、稳定化与营救入口，落实"正式居民不可被永久删除"（`RULE-FOUNDATION-025`）在 COMBAT 侧的执行点。

## 2. 非目标

不定义 defeat 状态机与恢复语义（`DOC-RESIDENT-008` canonical）、Health Settlement 机制（`DOC-COMBAT-006`）、终结事务的跨域清单（`DOC-COMBAT-011`）、掉落（`DOC-COMBAT-010`）或战后营救事件的编排（`DOC-EVENT-*` 通过稳定 ID 消费 `EncounterResolved`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| End Condition | 封闭 enum：`side_eliminated/surrender_accepted/negotiated_end/flee_complete/round_cap_forced` |
| Winning Side | 终结条件判定的获胜方，`negotiated_end/round_cap_forced` 可为 null |
| Outcome Mapping | 从 Combatant 终态与战场语境到 defeat outcome 的确定性函数 |
| Stabilized | `assist` 稳定化行动在 down Combatant 上提交的事实标记 |
| Valid Holder | 满足 `RULE-RESIDENT-043`（holder、location、review、退出条件）的俘获方 |
| In-Combat Rescue | 战斗内复苏/稳定化；战后营救属于 EVENT aftermath |

## 4. 规则与不变量

- `RULE-COMBAT-049`：终结条件为封闭集合并在每次状态迁移事务中评估：一方全部 `down/fled/surrendered` 为 `side_eliminated`；投降被 acceptance policy 接受为 `surrender_accepted`；注册谈判条款生效为 `negotiated_end`；一方存活者全部逃跑成功为 `flee_complete`；Round Cap 到达为 `round_cap_forced`。首个满足者生效，同事务进入 `resolving`。
- `RULE-COMBAT-050`：Resident 型 Combatant 的 Outcome Mapping 为确定性优先序，与 `DOC-RESIDENT-008` 第 8 节降级序对齐：
  1. 逃跑成功者 -> `retreated`；
  2. `surrendered` 且对方有 Valid Holder -> `captive`，无 Valid Holder -> `retreated`（就地释放撤离）；
  3. `down` 且本方为 Winning Side 或存在存活本方 active 成员 -> `unconscious`；
  4. `down` 且对方为 Winning Side 且对方有 Valid Holder -> `captive`；
  5. 其余 `down` -> `severely_injured`。
  Stabilized 标记使第 5 支路提升为 `unconscious`。
- `RULE-COMBAT-051`：任何战斗终态都不产生 Resident 的 death/delete；映射输出连同 Settlement 交由 RESIDENT 原子写入 `defeated + outcome`（`RULE-RESIDENT-035/041/042`）。未 down、未投降、未逃跑的幸存 Resident 保持 `active`，不进入 defeat。
- `RULE-COMBAT-052`：`captive` 输出必须在同一结果事务引用 EVENT/WORLD 法律 owner 可接受的 holder 与 location，并满足 review 上限（`RULE-RESIDENT-043`）；无法构造合法 captivity 时映射降级为 `severely_injured`，禁止生成无退出路径的俘虏。
- `RULE-COMBAT-053`：Creature/summon 型 Combatant 允许 `died/dissipated` 终态并从世界移除；该移除是显式 DomainEvent，不适用于任何 Resident（含玩家 Resident）。
- `RULE-COMBAT-054`：`retreated/captive` 的战后位置由结果事务写入：`retreated` 回到触发前合法位置或注册安全点，`captive` 为 holder location；位置必须通过 MAP 合法性校验（`RULE-FOUNDATION-017`），失败则整个结果事务回滚。

## 5. 数据与接口

`DES-COMBAT-009`：`EncounterResolved` payload 注册为 `schema.combat.encounter_resolved.v1`；required 字段为
`resolved_schema_version/encounter_id/end_condition/winning_side/combatant_finals/settlement_ref`。

```json
{
  "resolved_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "end_condition": "side_eliminated",
  "winning_side": "party",
  "combatant_finals": [
    {
      "combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
      "entity_ref": "01K1AB2CD3EF4GH5JK6MNP7QRR",
      "kind": "resident",
      "final_combat_state": "active",
      "defeat_outcome": null,
      "post_location_id": "semantic_node.forest.north_trail"
    },
    {
      "combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD",
      "entity_ref": "creature.bandit.cutpurse",
      "kind": "creature",
      "final_combat_state": "down",
      "defeat_outcome": "died",
      "post_location_id": null
    }
  ],
  "settlement_ref": "01K1AB2CD3EF4GH5JK6MNP7QSK"
}
```

`defeat_outcome` 封闭 enum：Resident 型 `null/unconscious/severely_injured/retreated/captive`；Creature 型 `null/died/dissipated/fled`。接口：

```text
evaluate_end_conditions(encounter_state) -> EndConditionResult
map_defeat_outcomes(encounter_state, end_condition) -> CombatantFinal[]
```

二者为纯函数，输入相同则输出相同。

## 6. 正常流程

1. 状态迁移事务中 `evaluate_end_conditions` 首次返回非 null，Encounter 转 `resolving`。
2. `map_defeat_outcomes` 按 `RULE-COMBAT-050` 优先序为每名 Combatant 计算终局。
3. `captive` 支路构造并校验 captivity 引用；`retreated` 支路解析安全位置。
4. 终局与 `DOC-COMBAT-006` Settlement 一并进入 `DOC-COMBAT-011` 的结果事务，原子提交 `EncounterResolved`。
5. RESIDENT 写入 lifecycle 转换，TIME 排定 review/recovery，EVENT 依据事件生成营救/赎回/善后路径。

## 7. 边界情况

- 全队覆灭（双方仅剩 down）：`round_cap_forced` 之前若双方同 Turn 归零，按 Turn 顺序先满足 `side_eliminated` 的一侧判定；双方同时（同一 tick 结算）全灭时 `winning_side=null`，全部 down Resident 走第 3/5 支路（无存活本方成员则映射 `severely_injured`，Stabilized 提升为 `unconscious`）。
- `round_cap_forced` 双方均有存活：`winning_side=null`，无人进入 defeat，双方按 `retreated` 语义各自脱离位置（active Resident 不写 defeat outcome，仅位置脱离）。
- 玩家 Resident 被俘：与 AI Resident 同规则进入 `captive`，玩家控制切换到 `DOC-RESIDENT-008` 的受限行动集合与营救/谈判路径。
- 对方为纯 Creature 且无阵营 holder：不可能产生合法 captivity，Resident down 一律 `severely_injured` 或（Stabilized）`unconscious`。
- 混合队伍（Resident + summon）：summon 一律消散，不参与 Outcome Mapping。

## 8. 错误与降级

`COMBAT_OUTCOME_MAPPING_INVALID`（映射输出不在封闭 enum）、`COMBAT_CAPTIVITY_INVALID`（holder/review 校验失败且未按规则降级）、`RESIDENT_PERMANENT_DEATH_FORBIDDEN` 透传。终结评估或映射内部错误使 Encounter 保持 `resolving` 并触发一致性暂停，禁止以删除参战者或跳过 Settlement 的方式脱困。

## 9. 安全与性能

Outcome Mapping 为 O(参战者数) 纯函数，无 I/O。俘虏/重伤的玩家可见叙事遵守 `DOC-WORLD-010` 克制表达边界；`EncounterResolved` render projection 不含映射内部支路编号，只含结果描述。

## 10. 验收标准

- 五种 End Condition 各有 fixture 并全部可达；封闭集合外无终结路径。
- Property Test：任意终态组合下 Resident 输出恒为四种非永久 outcome 或 null，永无 death/delete。
- captive 全部携带合法 holder/location/review/退出条件；无法构造时正确降级。
- Creature 死亡移除有显式事件且不影响任何 Resident。
- retreated/captive 战后位置全部通过 MAP 校验。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-023` | 终结条件封闭性、首个满足与同 tick 全灭（`RULE-COMBAT-049`） |
| `TEST-COMBAT-024` | Outcome Mapping 优先序、Stabilized 提升与非永久性 Property Test（`RULE-COMBAT-050..051`, `RULE-COMBAT-053`） |
| `TEST-COMBAT-025` | captivity 合法性、降级与战后位置校验（`RULE-COMBAT-052`, `RULE-COMBAT-054`） |

## 12. 关联文档

- `DOC-RESIDENT-008`：defeat 状态机与恢复 canonical owner
- `DOC-COMBAT-006`：Settlement 与终态 HP
- `DOC-COMBAT-010`：终结后的掉落与后果
- `DOC-COMBAT-011`：结果事务与幂等
- `DOC-WORLD-010`：失败表现的内容边界

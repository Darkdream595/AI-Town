---
doc_id: DOC-COMBAT-003
title: 战斗行动与合法选项
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - combat-action-catalog
  - legal-combat-options
  - surrender-negotiation-escape-rules
depends_on:
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-006
  - DOC-ECON-005
  - DOC-MAGIC-005
  - DOC-COMBAT-001
  - DOC-COMBAT-002
requirements:
  - REQ-COMBAT-003
last_updated: 2026-07-26
---

# 战斗行动与合法选项

## 1. 目的

`REQ-COMBAT-003`：定义 Encounter 内封闭的行动种类集合、服务器派生的 `LegalCombatOption[]` 的唯一 Schema 与派生规则，以及投降、谈判、逃跑三类非暴力出口的合法性语义。玩家与 AI 都只能从同一份合法选项集合中选择。

## 2. 非目标

不定义命中/伤害/逃跑成功率公式（`DOC-COMBAT-004`）、状态效果内容（`DOC-COMBAT-005`）、结算事务（`DOC-COMBAT-006`）、AI 如何选择（`DOC-COMBAT-007`）或选择后的失败结果映射（`DOC-COMBAT-009`）。谈判中的自由文本表达由 `DOC-DIALOGUE-001` 生命周期承载，本文只定义其战斗侧入口与结构化结果。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Action Kind | 封闭 enum：`attack/skill/cast_spell/use_item/defend/switch_position/assist/observe/talk/flee/surrender/pass`，共 12 种 |
| Legal Combat Option | 服务器按当前已提交 Encounter 状态为 Turn Owner 派生的一条可选行动 |
| Option ID | Stable Catalog ID，如 `combat_option.attack`、`combat_option.skill.power_strike` |
| Legal Target Set | 该 Option 允许的目标 `combatant_id` 集合，由服务器枚举 |
| Negotiation Term | 注册的结构化谈判条款，如 `negotiation.stand_down`、`negotiation.offer_payment` |
| Reach 标签 | 允许近战选取后排目标的武器/能力标签（`DOC-COMBAT-001` `RULE-COMBAT-003`） |

## 4. 规则与不变量

- `RULE-COMBAT-013`：`LegalCombatOption[]` 只能由服务器从当前已提交 Revision 的 Encounter 状态派生；玩家输入与模型输出仅能引用其中的 `option_id` 与 Legal Target Set 子集，引用集合外内容返回 `COMBAT_OPTION_ILLEGAL` 且无状态变化。
- `RULE-COMBAT-014`：12 种 Action Kind 为封闭集合；`skill/cast_spell/use_item` 的具体条目分别来自 Resident 已解锁 Ability（`DOC-RESIDENT-005`）、已学会且合法可施法的 Spell（`DOC-MAGIC-005`）与本人 Inventory 中的可用物品（`DOC-ECON-005`），不存在集合外行动。
- `RULE-COMBAT-015`：`combat_state=active` 的 Turn Owner 的合法集合永不为空：`defend` 与 `pass` 无前置条件恒为合法；派生结果为空集是 COMBAT invariant violation，必须触发一致性暂停而不是伪造 attack。
- `RULE-COMBAT-016`：近战 `attack/skill` 的 Legal Target Set 遵循站位规则：存在存活前排时不含对方后排，除非行动携带 Reach 标签；`switch_position` 只能与本方相邻空 slot 或同意交换的本方 Combatant 互换，且消耗整个 Turn。
- `RULE-COMBAT-017`：`surrender` 对 active Combatant 恒为合法；其效果是提交 `SurrenderDeclared` 事实并使本人退出后续攻击目标合法集合以外的主动行动。接受与否由已注册 acceptance policy 在同一事务确定性判定（依据对方 side 的 template/faction 参数），不由模型文本判定。
- `RULE-COMBAT-018`：`talk` 每 Turn 至多一次，只能提出零或一条注册 Negotiation Term；条款的接受判定与后果（如 `negotiated_end`）由注册 policy 的确定性规则执行，自由文本只作纯文本渲染与记忆素材，不产生数值或状态效果。`flee` 是一次基于 `DOC-COMBAT-004` 公式的尝试，失败时消耗 Turn 且本 round 不可重试。

## 5. 数据与接口

`DES-COMBAT-003`：注册 `schema.combat.legal_option.v1`；required 字段为
`option_schema_version/option_id/kind/actor_combatant_id/legal_target_sets/cost/formula_ref/source_definition_id`。
`cost` 的 `mp_cost` 为非负整数，`item_ref` 仅 `use_item` 非 null；`source_definition_id` 指向 Ability/Spell/Item/Term 的注册来源，基础行动为 null。

```json
{
  "option_schema_version": 1,
  "option_id": "combat_option.cast_spell.ember_bolt",
  "kind": "cast_spell",
  "actor_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
  "legal_target_sets": [
    {"set_id": "enemy_single", "combatant_ids": ["01K1AB2CD3EF4GH5JK6MNP7QSD"], "min_targets": 1, "max_targets": 1}
  ],
  "cost": {"mp_cost": 4, "item_ref": null},
  "formula_ref": "combat_formula.v1.magical_single",
  "source_definition_id": "spell.elemental.ember_bolt"
}
```

接口：

```text
list_legal_options(encounter_id, turn_index) -> LegalCombatOption[]
submit_combat_action(command_id, encounter_id, turn_index, action_option_id, target_combatant_ids, negotiation_term_id) -> CombatActionResult
```

`submit_combat_action` 的 wire 参数即 `DOC-AI-004` `combat_action_parameters` 加服务器侧补充的可选 `negotiation_term_id`；玩家 PlayerCommand 与 AI ValidatedIntent 进入同一入口。

## 6. 正常流程

1. Turn 进入 `awaiting_decision` 时，服务器派生并缓存该 `(encounter_id, turn_index)` 的 `LegalCombatOption[]`。
2. 玩家 UI（`DOC-COMBAT-008`）或 AI 决策（`DOC-COMBAT-007`）从集合中选择 `option_id` 与目标。
3. 服务器在最新已提交状态上复验选项仍合法（MP 足够、目标存活、站位未变）。
4. 合法则移交 `DOC-COMBAT-006` 单事务解析；`surrender/talk/flee` 的出口语义结果记入同一事务。
5. 事务提交后按 `DOC-COMBAT-002` 推进 Turn。

## 7. 边界情况

- 派生时目标存活、提交时已被本 round 更早行动击倒：复验失败，返回 `COMBAT_OPTION_ILLEGAL`，Turn 保持 `awaiting_decision` 并以刷新后的集合重新决策。
- MP 不足以支付任何 Spell：`cast_spell` 条目不进入集合，不在提交时才失败。
- `use_item` 引用的物品在 Encounter 前被 Reservation 占用或已消耗：不进入集合；集合内物品在 Turn 解析事务中按 `DOC-ECON-005` 校验并消耗。
- 双方同 round 各自 `surrender`：按 Turn 顺序先提交者先判定；若先者被接受进入终结流程，后者的 Turn 不再发生。
- 控制类状态限制行动：`DOC-COMBAT-005` 的 restriction 在派生阶段过滤 kind，被完全禁止行动的 Combatant 由 `DOC-COMBAT-002` 直接 skip，不产生空集合。

## 8. 错误与降级

错误码：`COMBAT_OPTION_ILLEGAL`、`COMBAT_OPTION_TARGET_INVALID`、`COMBAT_OPTION_COST_UNPAYABLE`、`COMBAT_NEGOTIATION_TERM_UNKNOWN`。模型不可用不影响集合派生（纯服务器计算）；AI 决策降级见 `DOC-COMBAT-007`。派生依赖的 MAGIC/ECON projection 暂不可用时，对应 kind 整类不进入集合并记录诊断，基础行动仍可用。

## 9. 安全与性能

集合派生为 O(候选条目数)，单 Combatant 候选上限 32（与 `DOC-AI-011` 候选上限一致）。Legal Target Set 只含 combatant_id，不泄露对方隐藏数值。自由文本经 `DOC-DIALOGUE-011` 内容边界过滤后按纯文本渲染，不进入任何判定逻辑。

## 10. 验收标准

- 12 种 Action Kind 各有至少一个派生与提交用例；集合外 option_id、非法目标、超额目标全部被拒绝。
- active Combatant 的合法集合在全部 fixture 状态下非空。
- 站位/Reach 目标过滤、switch_position 约束按规则生效。
- surrender/talk/flee 的判定与后果全部来自注册 policy 与公式，模型文本改变不了结果。
- 玩家与 AI 提交同一非法输入得到同一错误码。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-005` | 集合派生、非空不变量与集合外拒绝（`RULE-COMBAT-013..015`） |
| `TEST-COMBAT-006` | 站位/Reach/switch_position 目标合法性（`RULE-COMBAT-016`） |
| `TEST-COMBAT-007` | surrender/talk/flee 出口语义与确定性判定（`RULE-COMBAT-017..018`） |

## 12. 关联文档

- `DOC-COMBAT-004`：`formula_ref` 指向的公式注册表
- `DOC-COMBAT-007`：`LegalCombatOption[]` 的 AI 消费者（含 `DOC-AI-011` Tactical Utility）
- `DOC-COMBAT-008`：玩家 UI 只渲染本集合
- `DOC-COMBAT-009`：surrender/flee 的终结与 outcome 映射
- `DOC-AI-004`：`combat_action_parameters` wire Schema

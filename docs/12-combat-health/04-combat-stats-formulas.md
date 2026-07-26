---
doc_id: DOC-COMBAT-004
title: 战斗属性与确定性公式
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - combatant-stat-model
  - combat-formula-registry
  - combat-random-rolls
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-005
  - DOC-RESIDENT-007
  - DOC-ECON-004
  - DOC-MAGIC-003
  - DOC-TIME-010
  - DOC-COMBAT-001
  - DOC-COMBAT-002
  - DOC-COMBAT-003
requirements:
  - REQ-COMBAT-004
last_updated: 2026-07-26
---

# 战斗属性与确定性公式

## 1. 目的

`REQ-COMBAT-004`：定义 CombatantSheet 的八项属性 `HP/MP/Strength/Defense/Magic/Resistance/Agility/Focus` 的类型、派生来源与上下界，以及命中、暴击、伤害、治疗、逃跑的版本化确定性公式和 Seed 掷骰规则。所有数值为整数，任何结果都能从已提交输入与 draw sequence 重算。

## 2. 非目标

不定义结算事务与 HP 落账（`DOC-COMBAT-006`）、状态效果内容（`DOC-COMBAT-005`）、掉落概率（`DOC-COMBAT-010`）；不定义 Resident 持久属性成长（`DOC-RESIDENT-005`）或 Mana 恢复（`DOC-MAGIC-003`）。数值平衡调参通过发布新 formula version 完成，不在本版本内提供可变配置。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| CombatantSheet | Encounter 创建时派生、Encounter 内权威的战斗属性快照与当前值 |
| Attribute | 六项非资源属性 `strength/defense/magic/resistance/agility/focus`，整数 `1..200` |
| Resource | `hp_current/hp_max`、`mp_current/mp_max`，非负整数 |
| Formula Version | 公式注册表版本，首版固定 `combat_formula.v1` |
| Roll | 来自 `DOC-TIME-010` stream `combat.roll`、scope 为 `encounter_id` 的一次 `draw_bounded_uint32` |
| `power_q1000` | 行动/法术注册的威力系数，千分整数 `100..5000` |

## 4. 规则与不变量

- `RULE-COMBAT-019`：Resident 型 Combatant 的 `hp_current/hp_max` 取自 `DOC-RESIDENT-007` health_state，`mp_current/mp_max` 取自 `DOC-MAGIC-003` mana projection；六项 Attribute 按 `attribute = clamp(race_base + skill_bonus + equipment_bonus, 1, 200)` 派生，其中 race_base 来自 Resident Catalog、skill_bonus 来自已注册 `skill -> attribute` 映射表、equipment_bonus 来自已装备 Item 的注册 modifier（`DOC-ECON-004` tags）。Creature 型直接取注册 template 数值。
- `RULE-COMBAT-020`：所有公式只使用整数运算与向下取整除法；公式集合由 `combat_formula.v1` 注册表唯一定义，未注册的 `formula_ref` 拒绝解析。已开始的 Encounter 固定其创建时的 Formula Version。
- `RULE-COMBAT-021`：命中判定为 `p_hit_permille = clamp(700 + 5 * (attacker.focus - defender.agility), 50, 980)`；掷 `roll_hit = draw_bounded_uint32(1000)`，`roll_hit < p_hit_permille` 为命中。暴击仅在命中后判定：`p_crit_permille = clamp(30 + attacker.focus / 2, 10, 250)`，`roll_crit < p_crit_permille` 时伤害乘 `1500 / 1000`。
- `RULE-COMBAT-022`：物理伤害 `damage = max(1, (attacker.strength * power_q1000 / 1000 - defender.defense / 2) * variance / 1000)`，魔法伤害以 `magic/resistance` 同形替换；治疗 `healing = max(1, caster.magic * power_q1000 / 1000 * variance / 1000)` 且不参与暴击。`variance = 900 + draw_bounded_uint32(201)`，范围 `[900, 1100]`。
- `RULE-COMBAT-023`：逃跑成功率 `p_flee_permille = clamp(400 + 8 * (runner.agility - max(opposing active agility)), 100, 900)`，掷一次 `draw_bounded_uint32(1000)` 判定。`defend` 使本 Combatant 至下一自身 Turn 前受到的最终伤害乘 `500 / 1000`（向下取整，最小 1）。
- `RULE-COMBAT-024`：单次 Turn 解析内的 Roll 消费顺序固定：命中、暴击、variance、行动附带状态效果判定、逃跑，按 formula 注册的 `roll_slots` 声明依次消费；未走到的分支不消费。sequence 只在解析事务提交时递增（`RULE-TIME-057`）。
- `RULE-COMBAT-025`：模型与 Client 永不提供或修改任何属性、概率、掷骰或结果数值（`RULE-AI-028` 的 COMBAT 侧执行点）；携带数值字段的输入在协议边界拒绝。

## 5. 数据与接口

`DES-COMBAT-004`：注册 `schema.combat.combatant_sheet.v1`；required 字段为
`sheet_schema_version/combatant_id/entity_ref/kind/side/formation_slot/combat_state/stats/status_effect_ids/equipment_refs`。
`kind` 封闭 enum：`resident/player_resident/creature/summon`；`combat_state` 封闭 enum：`active/down/fled/surrendered`。

```json
{
  "sheet_schema_version": 1,
  "combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
  "entity_ref": "01K1AB2CD3EF4GH5JK6MNP7QRR",
  "kind": "resident",
  "side": "party",
  "formation_slot": "front_left",
  "combat_state": "active",
  "stats": {
    "hp_current": 24, "hp_max": 30,
    "mp_current": 8, "mp_max": 10,
    "strength": 42, "defense": 35, "magic": 18,
    "resistance": 22, "agility": 39, "focus": 27
  },
  "status_effect_ids": [],
  "equipment_refs": ["01K1AB2CD3EF4GH5JK6MNP7QSF"]
}
```

接口：

```text
derive_combatant_sheet(entity_ref, encounter_id, revision) -> CombatantSheet
resolve_formula(formula_ref, actor_sheet, target_sheets, option_context) -> FormulaOutcome
```

`FormulaOutcome` 携带每一步的 roll 值、中间量与最终 delta，供事件审计与重放比对。

## 6. 正常流程

1. Encounter 创建事务内为每名 Participant 调用 `derive_combatant_sheet`，快照写入 Encounter aggregate。
2. Turn 解析时按选项的 `formula_ref` 取注册公式，依 `RULE-COMBAT-024` 顺序消费 Roll。
3. 产出 `FormulaOutcome`，交 `DOC-COMBAT-006` 在同一事务应用并提交。
4. 事务提交时 draw sequence 递增；回滚不消耗。

## 7. 边界情况

- Attribute 派生越界：clamp 到 `[1, 200]`，不报错；`hp_max=0` 的输入是上游数据错误，拒绝创建 Encounter。
- `defender.defense / 2` 超过攻击基值：`max(1, ...)` 保底 1 点伤害，不出现 0 或负伤害。
- 逃跑判定时对方全部非 active：终结条件先于逃跑发生，`flee` 选项不会出现在集合中。
- 同一 Turn 多目标行动：每个目标独立消费命中/暴击/variance Roll，目标顺序按 `combatant_id` 升序。
- variance 抽样 `draw_bounded_uint32(201)` 的 rejection sampling 消耗多个 raw block：全部计入同一 draw result（`RULE-TIME-058`）。

## 8. 错误与降级

未注册 `formula_ref`、越界 `power_q1000`、缺失 roll_slots 声明返回 `COMBAT_FORMULA_INVALID` 并拒绝解析。随机服务不可用时不得退化为伪随机或均值结算；当前 Turn 保持未解析并触发一致性告警。公式注册表与代码 digest 不一致时启动失败。

## 9. 安全与性能

单 Turn 解析的 Roll 上限 32 次（含 rejection 重抽），超限视为公式注册错误。公式计算纯内存整数运算，无 I/O；CombatantSheet 派生只读取已提交 projection。FormulaOutcome 进入事件时不含对方 Sheet 全量，只含参与计算的输入引用。

## 10. 验收标准

- 固定 Seed 与 fixture Sheet 下，命中/暴击/伤害/治疗/逃跑结果跨 100 次重放逐字节一致。
- 全部公式输出为整数且满足保底与 clamp 边界。
- Roll 消费顺序与 sequence 事务性通过反例注入验证（回滚不消耗）。
- 携带数值的模型/Client 输入在边界被拒绝。
- Python/TypeScript 双实现对同一 fixture 输出一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-008` | Sheet 派生来源、clamp 与 kind 差异（`RULE-COMBAT-019`） |
| `TEST-COMBAT-009` | 五组公式边界值、整数性与双实现一致（`RULE-COMBAT-020..023`） |
| `TEST-COMBAT-010` | Roll 顺序、sequence 事务性与数值输入拒绝（`RULE-COMBAT-024..025`） |

## 12. 关联文档

- `DOC-COMBAT-003`：`formula_ref` 的选项载体
- `DOC-COMBAT-005`：状态效果对 Attribute 的临时修正
- `DOC-COMBAT-006`：`FormulaOutcome` 的结算 owner
- `DOC-TIME-010`：`combat.roll` 随机流与 rejection sampling
- `DOC-ECON-004`：装备 modifier 的 Item 真值

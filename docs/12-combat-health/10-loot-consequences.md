---
doc_id: DOC-COMBAT-010
title: 战利品、装备损耗与社会后果
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - combat-loot-provenance
  - equipment-wear-settlement
  - combat-social-consequence-facts
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-008
  - DOC-ECON-004
  - DOC-ECON-005
  - DOC-ECON-006
  - DOC-TIME-010
  - DOC-COMBAT-006
  - DOC-COMBAT-009
requirements:
  - REQ-COMBAT-010
last_updated: 2026-07-26
---

# 战利品、装备损耗与社会后果

## 1. 目的

`REQ-COMBAT-010`：定义战利品的合法来源、Seed 掷骰与 provenance 记录、装备耐久损耗的确定性结算，以及战斗结果向记忆、关系与法律系统输出的事实边界，保证物品守恒、来源可审计且战斗后果自然进入社会模拟。

## 2. 非目标

不定义 Item Schema 与 provenance 存储（`DOC-ECON-004`）、Inventory 容量（`DOC-ECON-005`）、事务机制（`DOC-ECON-006`）、记忆写入与关系变化规则（`DOC-MEMORY-002/006` 消费本文事实）或犯罪判定（WORLD 法律 owner）。COMBAT 只产出已结算事实。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Loot Table | Stable Catalog ID `loot_table.*` 注册的掉落模板：条目、概率、数量范围 |
| Loot Roll | 结果事务内基于 stream `combat.loot`、scope `encounter_id` 的掉落抽取 |
| Wear | 装备耐久损耗量，千分整数，按使用/受击次数确定性累计 |
| Damaged 状态 | 耐久归零后 Item 的可修复状态，不是删除 |
| Consequence Fact | `EncounterResolved` 及其衍生 DomainEvent 中供 MEMORY/EVENT/WORLD 消费的结构化事实 |
| Victor Assignment | 战利品向获胜方 Inventory 的确定性分配算法 |

## 4. 规则与不变量

- `RULE-COMBAT-055`：战利品只有两个合法来源：终态为 `died/dissipated` 的 Creature 的注册 Loot Table，与 `negotiated_end/surrender_accepted` 中注册谈判条款明确让渡的物品/货币。Resident 的 Inventory 永不因战斗失败被自动掠夺（`RULE-RESIDENT-046`）；合法没收只能由 EVENT/WORLD 法律流程另行执行。
- `RULE-COMBAT-056`：Loot Roll 在结果事务内执行：按 Creature `combatant_id` 升序、表内条目注册顺序依次 `draw_bounded_uint32`，数量在注册范围内同法抽取；物品创建走 ECON 事务并追加 `combat_loot` provenance edge，引用 `encounter_id` 与 `EncounterResolved` event（`RULE-ECON-016`）。掉落货币为整数铜羽 mint 类型事件（`RULE-FOUNDATION-019`）。
- `RULE-COMBAT-057`：Victor Assignment 确定性：`winning_side=party` 时按 Item ULID 升序轮转分配给存活（`active` 终态）成员；无存活成员或 `winning_side=null` 时战利品作为地点容器落在 Encounter 位置，由 ECON 容器规则管理。容量不足的溢出部分同样落入地点容器，不丢弃。
- `RULE-COMBAT-058`：Wear 无掷骰：武器每次 `attack/skill` 使用累计 5 q1000，护甲每次被命中累计 3 q1000，数值来自注册表而非硬编码；逐回合只记账于 Encounter aggregate，结果事务一次性向 ECON 提交每件装备的聚合耐久 delta。耐久归零转 Damaged 状态（不可继续提供 modifier，可修复），永不静默删除。
- `RULE-COMBAT-059`：Consequence Fact 是唯一社会输出通道：参战者与登记见证者的记忆写入、关系变化、谣言传播、法律追责全部由各 owner 消费已提交事件自行结算；COMBAT 不直接修改任何关系值、记忆或法律状态。非法触发源（如无许可决斗、袭击居民）的判定输入随事件携带 `trigger_source` 与参与者事实。

## 5. 数据与接口

`DES-COMBAT-010`：Loot Table 注册 Schema（构建期校验）与结果事务内的掉落记录：

```json
{
  "loot_table_id": "loot_table.bandit.cutpurse",
  "entries": [
    {"item_definition_id": "item.currency.copper_feather", "drop_permille": 1000, "quantity_min": 5, "quantity_max": 20},
    {"item_definition_id": "item.weapon.rusty_dagger", "drop_permille": 250, "quantity_min": 1, "quantity_max": 1}
  ]
}
```

注册 `schema.combat.loot_outcome.v1`；required 字段为
`loot_schema_version/encounter_id/source_event_id/drops/wear_settlements`：

```json
{
  "loot_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "source_event_id": "01K1AB2CD3EF4GH5JK6MNP7QS8",
  "drops": [
    {
      "loot_table_id": "loot_table.bandit.cutpurse",
      "item_definition_id": "item.currency.copper_feather",
      "quantity": 12,
      "assigned_inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QSM"
    }
  ],
  "wear_settlements": [
    {"item_instance_id": "01K1AB2CD3EF4GH5JK6MNP7QSF", "wear_delta_q1000": 15, "became_damaged": false}
  ]
}
```

接口：

```text
roll_loot(encounter_state, end_condition) -> LootOutcome
accumulate_wear(resolution_context) -> WearLedgerDelta
```

`roll_loot` 只在结果事务内调用一次；`accumulate_wear` 在每次 Turn 解析事务内记账。

## 6. 正常流程

1. Turn 解析中按 `RULE-COMBAT-058` 记账 Wear。
2. 终结进入结果事务：`roll_loot` 依序抽取掉落并计算 Victor Assignment。
3. 物品创建、provenance、Inventory 存入、货币 mint、耐久 delta 与 `EncounterResolved` 在 `DOC-COMBAT-011` 的同一事务提交（`RULE-ECON-021` 同级原子性）。
4. MEMORY/EVENT/WORLD 各自消费 Consequence Fact：记忆写入、aftermath 事件、法律流程。
5. Damaged 装备后续通过 `repair` 流程恢复（`DOC-AI-005` `repair` Action 的 owner 链）。

## 7. 边界情况

- 谈判让渡的物品在让渡瞬间已不在对方 Inventory：条款判定失败回退为无让渡，谈判仍可按其余条款生效；不凭空创建物品。
- `drop_permille=1000` 的保底条目仍消费 draw（顺序稳定性优先于微小节省），数量范围为单值时不消费数量 draw 并记录 draw_count=0（`DOC-TIME-010` 边界的同款版本固定优化）。
- 双方全灭：战利品全部落入地点容器；后续拾取走 ECON 常规 ownership 流程。
- 未装备的 Inventory 物品不产生 Wear；战斗中 `use_item` 消耗品按 ECON 消耗规则在 Turn 解析事务内落账，不属于 Wear。
- 玩家 Resident 战败：与 AI Resident 同规则——物品不被自动掠夺，仅谈判让渡或法律没收可转移。

## 8. 错误与降级

未注册 Loot Table、越界 `drop_permille`、负数量返回 `COMBAT_LOOT_TABLE_INVALID`（构建期尽量拦截，运行时兜底拒绝）。ECON 提交失败使整个结果事务回滚重试，不允许"先掉落后补账"。Wear 记账溢出上限（单件单场 500 q1000）按上限截断并记录诊断。

## 9. 安全与性能

Loot Roll 次数上限为表条目数 × Creature 数，fixture 上限 64 次。provenance 与 mint 事件使物品/货币守恒可审计（`RULE-FOUNDATION-018/019`）。Consequence Fact 不含未授权 Secret；见证者集合按感知规则构建，不全网广播。

## 10. 验收标准

- 相同 Seed 与终态重放得到逐字节一致的掉落与分配。
- 全部战利品有 `combat_loot` provenance 且守恒审计通过；Resident 失败者物品无自动转移。
- Wear 聚合结算幂等，归零转 Damaged 且无删除。
- 溢出/全灭场景物品落入地点容器无丢失。
- 记忆/关系/法律变化全部可追溯到已提交 Consequence Fact。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-026` | 掉落来源封闭、Seed 确定性与 provenance（`RULE-COMBAT-055..056`） |
| `TEST-COMBAT-027` | Victor Assignment、溢出与容器回退（`RULE-COMBAT-057`） |
| `TEST-COMBAT-028` | Wear 记账/聚合/Damaged 与社会事实边界（`RULE-COMBAT-058..059`） |

## 12. 关联文档

- `DOC-ECON-004`：Item 真值与 provenance 存储
- `DOC-ECON-006`：原子事务对端
- `DOC-COMBAT-011`：结果事务的提交载体
- `DOC-MEMORY-002`：战斗记忆写入消费者
- `DOC-TIME-010`：`combat.loot` 随机流

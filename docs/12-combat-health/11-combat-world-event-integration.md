---
doc_id: DOC-COMBAT-011
title: 战斗与世界暂停、事件集成
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - encounter-result-transaction
  - encounter-recovery-idempotency
  - combat-world-event-integration
depends_on:
  - DOC-FOUNDATION-005
  - DOC-TIME-002
  - DOC-TIME-007
  - DOC-COMBAT-001
  - DOC-COMBAT-006
  - DOC-COMBAT-009
  - DOC-COMBAT-010
requirements:
  - REQ-COMBAT-011
last_updated: 2026-07-26
---

# 战斗与世界暂停、事件集成

## 1. 目的

`REQ-COMBAT-011`：定义 Encounter 与 Overworld 的完整边界——暂停与恢复的 token 生命周期、终结时唯一的跨域结果事务及其幂等性、崩溃/重载恢复语义，以及战斗作为 WorldEvent/Quest 生态一环的输入输出契约，保证战斗既不重复执行也不半途丢失。

## 2. 非目标

不定义 Pause Token 机制本身（`DOC-TIME-002`）、Reservation 生命周期（`DOC-TIME-007`）、WorldEvent/Quest 生命周期（`DOC-EVENT-*` 通过稳定 ID 消费）、Settlement 内容（`DOC-COMBAT-006`）、outcome 映射（`DOC-COMBAT-009`）或掉落内容（`DOC-COMBAT-010`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Result Transaction | Encounter 从 `resolving` 到 `ended` 的唯一跨域原子事务 |
| Resolve Command | 服务器 Orchestrator 触发 Result Transaction 的内部命令，携带 `command_id` |
| Recovery Resume | 重载后按已提交 `(state, round, turn, phase)` 继续 Encounter 的流程 |
| Aftermath Input | `EncounterResolved` 中供 EVENT 生成善后事件的事实子集 |
| Quest Combat Objective | 结构化任务目标类型"战斗"对 Encounter 结果的引用方式 |
| GameTime 冻结语义 | Encounter Active 期间 GameTime 不推进，战斗只消耗 TurnTime 与 RealTime |

## 4. 规则与不变量

- `RULE-COMBAT-060`：Result Transaction 原子提交且仅提交一次以下写集：`EncounterResolved` 事件、`DOC-COMBAT-006` Settlement、`DOC-COMBAT-009` lifecycle 转换与战后位置、`DOC-COMBAT-010` 掉落/耐久/货币、全部 actor Reservation 释放、combat Pause Token 释放、Encounter `state=ended`。任一子写失败则整体回滚，Revision 不增长（`RULE-FOUNDATION-029`）。
- `RULE-COMBAT-061`：Resolve Command 幂等：重复 `command_id` 返回原 `EncounterResolved` 引用；下游 RESIDENT/ECON/MAGIC 的幂等键使跨域重放同样至多生效一次（`RULE-FOUNDATION-022`）。不存在第二条终结路径——Admin 也只能通过带审计的标准 Resolve 流程终结战斗。
- `RULE-COMBAT-062`：Recovery Resume 只依赖已提交状态：`state=active` 从最后提交的 Turn 继续（draw sequence、initiative、回合明细全部已提交，不重掷）；`state=resolving` 重新执行确定性终结计算并提交同一 Result Transaction；`state=ended` 不再有任何战斗写入。恢复期间 combat Pause Token 依 `DOC-TIME-002` 恢复协调器规则保持，禁止按 RealTime 猜测释放。
- `RULE-COMBAT-063`：GameTime 冻结语义：Encounter Active 期间 `started_at_game_time` 即结束时刻的 game_time，战斗不消耗 GameTime；伤病恢复、captivity review 等后续排程一律以 Result Transaction 提交时的 game_time 为基准。TurnTime 与 GameTime 不换算（`RULE-FOUNDATION-037`）。
- `RULE-COMBAT-064`：事件生态边界：WorldEvent/Quest 只能通过 `DOC-COMBAT-001` 的 Trigger Source 请求战斗、通过 `EncounterResolved` 消费结果；Quest Combat Objective 以 `encounter_id + end_condition + winning_side` 判定达成，EVENT 不读取 Encounter 内部回合状态。`start_encounter` ActionProposal/PlayerCommand 经校验后先提交对应 Trigger Source 事实（如 `aggro_contact`），再走标准创建，二者同事务。

## 5. 数据与接口

`DES-COMBAT-011`：Resolve Command 注册为 `schema.combat.resolve_command.v1`；required 字段为
`resolve_schema_version/command_id/world_id/encounter_id/expected_revision/end_condition`。

```json
{
  "resolve_schema_version": 1,
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QSN",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "expected_revision": 96,
  "end_condition": "side_eliminated"
}
```

Result Transaction 的固定内部顺序（同一 Unit of Work 内的执行序，不是多次提交）：

```text
1. 复验 encounter state=resolving 与 expected_revision
2. Settlement（RESIDENT health / MAGIC mana）
3. defeat lifecycle 转换与战后位置写入
4. 掉落创建、provenance、Inventory 存入、货币 mint、耐久 delta
5. Reservation set 释放（DOC-TIME-007 release）
6. combat Pause Token 释放（DOC-TIME-002 release）
7. EncounterResolved 事件追加、state=ended、Revision +1
```

接口：

```text
resolve_encounter(resolve_command) -> EncounterResolvedRef
recover_encounters(snapshot, event_tail) -> CombatRecoveryReport
```

## 6. 正常流程

1. `DOC-COMBAT-009` 终结评估使 Encounter 进入 `resolving`（该迁移与最后一个 Turn 解析同事务）。
2. Orchestrator 构造 Resolve Command，按固定顺序执行 Result Transaction。
3. 提交后前端收到 `EncounterResolved` 返回 Overworld；最后一个 blocking token 释放后按既有 requested speed/speed cap 恢复（`RULE-TIME-007`）。
4. EVENT 消费 Aftermath Input 生成营救、赎回、追责、修复等善后；Quest 判定 Combat Objective。
5. TIME 以提交时 game_time 排定伤病恢复与 captivity review。

## 7. 边界情况

- 崩溃于 `resolving` 提交后、Result Transaction 前：Recovery Resume 重算终结（纯函数 + 已提交 draw sequence）得到相同结果并提交；期间 Pause Token 与 Reservation 保持，世界不会在战斗未了结时恢复运行。
- Result Transaction 提交后崩溃：重启后 `state=ended`，恢复器只做只读校验；重复 Resolve 返回原引用。
- 触发 Encounter 的 WorldEvent 在战斗期间到期：Overworld 暂停期间 GameTime 冻结，事件不会在战斗中途到期；到期判定在恢复后的下一 Tick 进行。
- 玩家在战斗中请求存档/退出：`shutdown` token 与 `combat` token 叠加（`RULE-TIME-010`），存档落在最后提交的战斗 Revision；重开后 Recovery Resume 回到同一回合。
- 战斗中 backpressure 或其他 owner 申请额外 token：嵌套暂停不影响战斗推进（战斗不依赖 GameTime），释放顺序互不干扰（`RULE-TIME-008`）。

## 8. 错误与降级

`COMBAT_RESOLVE_STATE_INVALID`（非 resolving 状态收到 Resolve）、`COMBAT_RESOLVE_REVISION_STALE`、下游域错误透传并整体回滚。反复失败进入一致性暂停并保留完整 Encounter 状态供审计，禁止用释放 token/锁但不提交结果的方式"解卡"。

## 9. 安全与性能

Result Transaction 是本系统最大跨域写集，目标 P95 < 200 real ms、写集条目上限 128。Resolve Command 只能由服务器 Orchestrator 构造，Gateway 不暴露该命令类型给 Client。Aftermath Input 只含已提交事实与克制描述，不含决策上下文或 Secret。

## 10. 验收标准

- Result Transaction 七步写集全有或全无；反例注入任一步失败时 Revision 不增长、token/锁不泄漏。
- 重复 Resolve、跨域重放均至多生效一次。
- 崩溃时机矩阵（active/resolving/ended × 提交前后）全部恢复到一致状态且不重掷随机。
- 战斗全程 GameTime 不推进；恢复后世界速度回到 requested/cap 合成值。
- WorldEvent 触发、Quest 判定、aftermath 消费均只经稳定 ID 与已提交事件。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-029` | 结果事务原子性、写集顺序与失败回滚（`RULE-COMBAT-060`） |
| `TEST-COMBAT-030` | Resolve 幂等与跨域重放去重（`RULE-COMBAT-061`） |
| `TEST-COMBAT-031` | 崩溃恢复矩阵、token/Reservation 保持与 GameTime 冻结（`RULE-COMBAT-062..063`） |
| `TEST-COMBAT-032` | 事件/任务集成只经 Trigger Source 与 EncounterResolved（`RULE-COMBAT-064`） |

## 12. 关联文档

- `DOC-COMBAT-001`：创建侧的 token/Reservation 获取
- `DOC-TIME-002`：Pause Token 释放与恢复协调
- `DOC-TIME-007`：Reservation release/consume 语义
- `DOC-EVENT-001`：WorldEvent 引擎消费者
- `DOC-RELEASE-003`：Snapshot/Event Log 恢复基础

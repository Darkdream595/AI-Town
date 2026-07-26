---
doc_id: DOC-COMBAT-001
title: 遭遇触发规则
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - encounter-trigger-sources
  - encounter-participant-lock
  - encounter-party-formation
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-007
  - DOC-RESIDENT-008
  - DOC-TIME-002
  - DOC-TIME-007
requirements:
  - REQ-COMBAT-001
last_updated: 2026-07-26
---

# 遭遇触发规则

## 1. 目的

`REQ-COMBAT-001`：定义 Encounter 的唯一创建入口、合法触发源、参与者锁定、四人小队上限与前/后排站位，使战斗开始本身是确定性、可审计、可拒绝的权威事务，而不是客户端或模型的即兴请求。

## 2. 非目标

不定义回合内行动、数值公式、状态效果或失败结果；不定义世界事件如何生成敌对目标（`DOC-EVENT-*`）；不定义 Overworld 移动与碰撞（`DOC-MAP-*`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Encounter | 暂停 Overworld、以 TurnTime 推进的独立战斗 aggregate，COMBAT 唯一拥有 |
| Trigger Source | 触发 Encounter 的已提交事实类型：`ambush_event/aggro_contact/defense_response/arena_duel/scripted_quest` |
| Participant | 被锁定进 Encounter 的 Resident 或注册 Creature 实体引用 |
| Party | 玩家方参战小队，最多 4 名正式成员 |
| Formation Slot | `front_left/front_right/rear_left/rear_right` 四个己方站位 |
| Side | `party/adversary`，首版仅两方，不支持三方混战 |

## 4. 规则与不变量

- `RULE-COMBAT-001`：Encounter 只能由 COMBAT `StartEncounterCommand` 创建，payload 必须引用一个已提交的 Trigger Source event；AI 的 `ActionProposal`、玩家输入和渲染事件都不能直接创建 Encounter（`RULE-FOUNDATION-015`）。
- `RULE-COMBAT-002`：创建事务必须为每个 Participant 通过 `DOC-TIME-007` Reservation 取得 actor 互斥锁；任一锁失败则整个创建回滚，不允许部分参战（`RULE-FOUNDATION-028`）。
- `RULE-COMBAT-003`：Party 正式成员上限 4，占用四个 Formation Slot；空缺 slot 保留为空，不允许 5 人以上或后排超员。`front_*` 承受近战目标的默认优先级，`rear_*` 仅在无存活前排或攻击方拥有 `reach` 标签时可被近战选为目标。
- `RULE-COMBAT-004`：Participant 必须 `lifecycle_state=active`（`DOC-RESIDENT-008`）；`defeated/recovering` 居民不能被拉入新 Encounter。
- `RULE-COMBAT-005`：Encounter 创建成功的同一事务申请 `reason=combat` 的 Pause Token（`DOC-TIME-002`）；Encounter 终结事务幂等释放同一 `token_id`。创建回滚不得残留 token。
- `RULE-COMBAT-006`：同一 actor 同一时刻只能属于一个未终结 Encounter；重复 `command_id` 返回原结果引用（`RULE-FOUNDATION-022`）。

## 5. 数据与接口

`DES-COMBAT-001`：注册 `schema.combat.encounter.v1`；required 字段为
`encounter_schema_version/encounter_id/world_id/trigger_source/trigger_event_id/side_party/side_adversary/formation/started_at_game_time/started_revision/pause_token_id/state`。
`state` 封闭 enum：`forming/active/resolving/ended`。

```json
{
  "encounter_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "trigger_source": "ambush_event",
  "trigger_event_id": "01K1AB2CD3EF4GH5JK6MNP7QSB",
  "side_party": ["01K1AB2CD3EF4GH5JK6MNP7QSC"],
  "side_adversary": ["01K1AB2CD3EF4GH5JK6MNP7QSD"],
  "formation": {"front_left": "01K1AB2CD3EF4GH5JK6MNP7QSC", "front_right": null, "rear_left": null, "rear_right": null},
  "started_at_game_time": 1830,
  "started_revision": 42,
  "pause_token_id": "01K1AB2CD3EF4GH5JK6MNP7QSE",
  "state": "active"
}
```

接口：`start_encounter(command_id, payload, expected_revision) -> EncounterResult`；
`get_encounter(encounter_id) -> EncounterView`（只读 DTO，携带 Revision）。

## 6. 正常流程

1. Orchestrator 收到已提交 Trigger Source event，构造 `StartEncounterCommand`。
2. 校验全部 Participant lifecycle 与合法性，按 `DOC-TIME-007` 稳定锁序获取 actor Reservation。
3. 申请 combat Pause Token，写入 Encounter aggregate 与 `EncounterStarted` DomainEvent。
4. 原子提交，Revision 递增；前端从事件进入战斗 Scene。

## 7. 边界情况

- 触发时目标已处于另一 Encounter：Reservation 失败，创建回滚并返回 `COMBAT_ACTOR_LOCKED`，不排队等待。
- Party 不足 4 人：合法，按实际人数填充 slot；单人队伍允许。
- `arena_duel` 触发源必须引用 EVENT/WORLD 法律 owner 的合法决斗许可；否则拒绝。
- 触发瞬间有 Participant 正被执行 defeat 流程：以当前已提交 Revision 的 lifecycle 为准，不加锁猜测。
- AI/玩家的 `start_encounter` 提案不是直接创建入口：校验通过后先提交对应 Trigger Source 事实（如 `aggro_contact`），再在同一事务执行标准创建（`DOC-COMBAT-011`）。

## 8. 错误与降级

错误码：`COMBAT_TRIGGER_SOURCE_INVALID`、`COMBAT_ACTOR_LOCKED`、`COMBAT_PARTY_OVERFLOW`、`COMBAT_PARTICIPANT_NOT_ACTIVE`、`COMBAT_DUEL_PERMIT_MISSING`。模型不可用不阻止 Encounter 创建——战斗结算全部确定性；NPC 决策走 `DOC-COMBAT-007` 降级。

## 9. 安全与性能

创建命令不接受客户端提供的 Participant 数值快照，只接受实体 ID；服务器按当前 Revision 读取。单世界活跃 Encounter 上限 1（Overworld 已暂停，不存在并发战斗）。Formation 校验为 O(4) 常数。

## 10. 验收标准

- 五种 Trigger Source 均可创建合法 Encounter，非法源被拒绝且无 Pause Token 残留。
- 锁冲突、超员、非 active 参与者分别返回对应错误码且 Revision 不增长。
- 重复 `command_id` 不产生第二个 Encounter。
- 创建与暂停 token 在同一事务原子生效。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-001` | 五种触发源、锁冲突、超员、重复命令与 token 原子性 |

## 12. 关联文档

- `DOC-COMBAT-002`：回合生命周期
- `DOC-COMBAT-009`：失败与释放流程
- `DOC-TIME-002`：combat Pause Token
- `DOC-TIME-007`：actor Reservation
- `DOC-RESIDENT-008`：lifecycle 合法性

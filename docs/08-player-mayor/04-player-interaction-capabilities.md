---
doc_id: DOC-PLAYER-004
title: 玩家交互能力与统一验证
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-interaction-intent
  - player-command-routing
  - interaction-target-selection
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-MAP-008
  - DOC-RESIDENT-007
  - DOC-RESIDENT-010
  - DOC-ECON-006
requirements:
  - REQ-PLAYER-004
last_updated: 2026-07-26
---

# 玩家交互能力与统一验证

## 1. 目的

`REQ-PLAYER-004`：定义 `E`、菜单和上下文操作如何形成不可信 Player Intent，经 PLAYER 路由为 `PlayerCommand`，再调用与 AI ActionProposal 相同的 Domain validator、Reservation 和提交路径。

## 2. 非目标

本文不拥有 talk、work、trade、magic、combat、build 等业务规则，也不允许 PLAYER 创建新的 Action 类型；各 Domain owner 决定合法性和结算。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Player Intent | Client 表达的愿望，尚无规则效力 |
| PlayerCommand | 已认证 actor、带幂等键与 Revision 的结构化命令 |
| Interaction Candidate | 服务端从距离、视线、Scene、状态和权限派生的候选 |
| Domain Validator | 目标 Domain 拥有的同源合法性检查器 |
| Capability Projection | 当前 actor 可尝试的有限操作提示，不保证提交时仍成功 |

## 4. 规则与不变量

- `RULE-PLAYER-016`：Client 只能建议 `target_entity_id/action_id/parameters`；后端从 binding 解析 actor，并重新计算距离、视线、可达性、权限和状态。
- `RULE-PLAYER-017`：相同 canonical action 的 PlayerCommand 与 AI ActionProposal 必须进入同一 Domain validator；不得维护“玩家专用放宽版”。
- `RULE-PLAYER-018`：Capability Projection 是 revision-stamped hint；世界变化后必须在提交点重校验，隐藏按钮不能代替授权。
- `RULE-PLAYER-019`：交互失败不消费物品、货币、体力、冷却或 Revision，也不播放“成功即事实”的动画。
- `RULE-PLAYER-020`：Player intent、Mayor command、Admin mutation 使用不同 envelope/type union，禁止从普通交互路由到后两类。

## 5. 数据与接口

`DES-PLAYER-004`：

```json
{
  "protocol_version": 1,
  "command_id": "01K1COMMAND000000000000004",
  "world_id": "01K1WORLD000000000000000001",
  "expected_revision": 118,
  "type": "player.action",
  "payload": {
    "action_id": "give_item",
    "target_entity_id": "01K1RESIDENT0000000000002",
    "parameters": {
      "item_id": "01K1ITEM00000000000000001",
      "quantity": 1
    }
  }
}
```

`type` 固定为 `player.action`；`action_id` 必须来自注册 Action Catalog；payload 最大 16 KiB，拒绝额外根字段。接口：

```text
query_interaction_candidates(binding_id, expected_revision) -> CapabilityProjection
submit_player_command(session, envelope) -> CommandReceipt
route_canonical_action(actor, action_id, parameters, revision)
  -> DomainValidationResult
```

## 6. 正常流程

1. Client 的 `E` 请求候选，不自行根据 Sprite 像素选择可信目标。
2. Backend 按距离、视线、交互半径、Scene、actor 状态和公开权限排序候选。
3. 单一候选可直接打开确认/对话；多个候选显示可键盘选择列表。
4. Client 发 PlayerCommand；Gateway 验证 session、world、大小、schema、幂等键和 Revision。
5. Orchestrator 把 canonical action 路由到 MAP/RESIDENT/ECON/MAGIC/COMBAT/EVENT owner validator。
6. 成功时 Reservation、状态、DomainEvent、Outbox 与幂等结果原子提交；Client 仅渲染 committed event。

## 7. 能力映射

| 玩家能力 | Canonical action/command | Owner 校验重点 |
|---|---|---|
| 交谈/观察 | `talk/observe` | 距离、视线、状态、语言、知识投影 |
| 工作/制作/采集 | `work/craft/gather` | 技能、岗位、工具、地点、Reservation |
| 买卖/赠与 | `buy/sell/give_item` | Quote、ownership、capacity、资金、税费 |
| 使用对象/物品 | `use_object` | target state、许可、effect registry |
| 施法/战斗 | `cast_spell/start_encounter/combat_action` | 已学习法术、目标、回合、资源、法律 |
| 建造/修理 | `build/repair` | 土地权、许可、材料、MAP/EVENT stage |

## 8. 并发、幂等与失败恢复

`(world_id, command_id)` 相同且 payload hash 相同返回原 receipt；不同 payload 返回 `PLAYER_COMMAND_ID_CONFLICT`。Candidate projection 过期返回 `PLAYER_CAPABILITY_STALE` 并刷新，不静默换目标。Reservation 冲突、目标离开或权限撤销时全体失败。commit 后回执丢失通过 idempotency result 恢复；动画中断不撤销事实。

## 9. 安全与性能

模型文本、DOM `data-*`、Sprite name 与 Client capability list 都不能成为权限来源。交互候选只在当前 Scene 空间索引查询，上限 16，返回最小公开字段。参数使用每 action 的严格 Schema，拒绝 prototype key、HTML、脚本 URL、任意文件路径和未知 action。

## 10. 验收标准

- 玩家与 AI 对同一 action/fixture 得到相同 Domain legality 和数值结果。
- 目标离开、Revision 过期、重复提交和 Reservation 竞争无部分副作用。
- `E` 候选排序可重复，隐藏/伪造按钮不能越权。
- 普通 PlayerCommand 无法构造 Mayor/Admin mutation。
- Client 只在 committed event 后显示结算成功。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-013` | Interaction Candidate 距离/视线/状态排序 |
| `TEST-PLAYER-014` | Player/AI canonical validator parity |
| `TEST-PLAYER-015` | stale、Reservation、幂等与动画中断 |
| `TEST-PLAYER-016` | unknown action、越权 envelope 与恶意参数拒绝 |

## 12. 关联文档

- `DOC-MAP-008`：Door/entrance interaction 条件
- `DOC-ECON-006`：交易、Reservation 与原子提交
- `DOC-PLAYER-005`：自然语言转换为同类 PlayerCommand
- `DOC-PLAYER-007..009`：三类权限边界


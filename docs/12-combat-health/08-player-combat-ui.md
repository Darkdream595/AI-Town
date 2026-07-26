---
doc_id: DOC-COMBAT-008
title: 玩家战斗 UI 与刷新恢复
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - player-combat-ui-contract
  - combat-ui-refresh-recovery
depends_on:
  - DOC-FOUNDATION-006
  - DOC-RENDER-002
  - DOC-RENDER-008
  - DOC-RENDER-009
  - DOC-COMBAT-002
  - DOC-COMBAT-003
requirements:
  - REQ-COMBAT-008
last_updated: 2026-07-26
---

# 玩家战斗 UI 与刷新恢复

## 1. 目的

`REQ-COMBAT-008`：定义玩家在战斗 Scene 中看到什么、能操作什么、操作如何映射为 PlayerCommand，以及浏览器刷新/断线后如何从已提交状态无损恢复到当前回合，保证 UI 永远只是已提交事实的投影，不能制造或预测战斗结果。

## 2. 非目标

不定义 Phaser Scene 装配与资源加载（`DOC-RENDER-002`）、VFX 生命周期（`DOC-RENDER-008`）、羊皮纸视觉规范（`DOC-RENDER-009`）、WebSocket 重连协议细节（`DOC-BACKEND-003`）或合法选项派生（`DOC-COMBAT-003`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| EncounterView | 服务器按玩家视角输出的只读战斗投影，携带 Revision |
| Action Menu | 由当前 `LegalCombatOption[]` 渲染的选项菜单 |
| Target Picker | 在 Legal Target Set 内高亮与选择目标的交互 |
| Combat Log | 已提交 `CombatActionResolved` render projection 的滚动记录 |
| Pending Submission | 已发送、未收到已提交回执的 `combat_action` PlayerCommand |
| Refresh Recovery | 页面重载后由 Revision 对齐重建战斗 UI 的流程 |

## 4. 规则与不变量

- `RULE-COMBAT-044`：Action Menu 只渲染服务器下发的 `LegalCombatOption[]`；UI 不自行推导、隐藏或添加选项，选中项与目标原样组装为 `combat_action` PlayerCommand，走与 AI 相同的校验管线（`RULE-FOUNDATION-015`）。
- `RULE-COMBAT-045`：UI 不做任何结果预测：HP 条、状态图标、Combat Log、VFX 只响应已提交事件的 render projection；本地仅允许选中高亮与菜单展开等无状态交互反馈。
- `RULE-COMBAT-046`：玩家回合无 RealTime 超时——Encounter Active 期间 Overworld 已由 combat Pause Token 暂停，`awaiting_decision` 可无限等待；UI 可显示提示但不得代玩家提交。
- `RULE-COMBAT-047`：每次提交携带 Client 生成的 `command_id` 与当前 `turn_index`；重复点击、重发与刷新后重提交由 `(world_id, command_id)` 幂等键（`RULE-FOUNDATION-022`）与 `COMBAT_TURN_STALE` 双重防护，至多生效一次。
- `RULE-COMBAT-048`：Refresh Recovery 必须完全从服务器已提交状态重建：重连后按 Revision 拉取 EncounterView 与当前 `LegalCombatOption[]`，Pending Submission 以原 `command_id` 查询结局；本地存储不保存战斗状态副本作为真值。

## 5. 数据与接口

`DES-COMBAT-008`：注册 `schema.combat.encounter_view.v1`；required 字段为
`view_schema_version/encounter_id/revision/turn_state/party_sheets/enemy_views/combat_log_tail/awaiting_player`。
`party_sheets` 为本方完整数值，`enemy_views` 复用 `DOC-COMBAT-007` 的 Observed Enemy View 投影（玩家与 AI 的敌情知识边界一致）。

```json
{
  "view_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "revision": 92,
  "turn_state": {"round_index": 3, "turn_index": 12, "phase": "actor_turn", "current_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC"},
  "party_sheets": [{"combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC", "hp_current": 24, "hp_max": 30, "mp_current": 8, "mp_max": 10}],
  "enemy_views": [{"combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD", "hp_bucket": "wounded", "visible_status_ids": [], "formation_slot": "front_left"}],
  "combat_log_tail": [{"turn_index": 11, "render_text": "埃莉丝的火苗术命中了盗匪。"}],
  "awaiting_player": true
}
```

接口：

```text
get_encounter_view(encounter_id) -> EncounterView
get_command_outcome(command_id) -> CommandOutcome
```

UI 布局构件（羊皮纸风格，`DOC-RENDER-009`）：回合顺序条、本方状态栏（整数 HP/MP 条）、Action Menu、Target Picker、Combat Log、逃跑/投降确认对话框。键位沿用总体设计：方向键/鼠标选择、`E`/Enter 确认、Esc 返回上级菜单（世界已暂停，Esc 不再申请额外暂停）。

## 6. 正常流程

1. `EncounterStarted` 事件驱动前端切入战斗 Scene，加载 EncounterView。
2. 轮到玩家 Combatant 时 `awaiting_player=true`，渲染 Action Menu 与 Target Picker。
3. 玩家确认后发送 `combat_action` PlayerCommand，进入 Pending Submission 态（按钮禁用防重复）。
4. 收到 `CombatActionResolved` render projection 后更新数值、日志并触发 VFX。
5. 非玩家回合按事件流播放各 Turn 结果；`EncounterResolved` 后展示结算面板并返回 Overworld Scene。

## 7. 边界情况

- 刷新发生在 Pending Submission 期间：恢复后先以 `command_id` 查询结局——已提交则直接进入下一状态，未提交则重新呈现同一回合菜单。
- 刷新发生在 AI 回合：恢复后从 `combat_log_tail` 与最新 turn_state 续播，不回退、不重演已提交回合。
- 收到 `COMBAT_TURN_STALE`/`COMBAT_OPTION_ILLEGAL`：以服务器刷新后的选项集合重新渲染菜单并给出克制提示，不静默改选。
- 断线期间 Encounter 被系统一致性暂停：EncounterView 携带暂停标记，UI 显示等待状态，禁止提交。
- Reduced Motion 或低性能档：VFX 按 `DOC-RENDER-008` 降级，数值与日志表达不受影响。

## 8. 错误与降级

网络错误只影响展示与提交时机，不产生本地结算。重连采用 `DOC-BACKEND-003` 的 Revision 增量或 Snapshot 路径；EncounterView 拉取失败时保持只读等待界面并指数退避重试。UI 崩溃不影响服务器战斗状态——重新进入页面等价于一次 Refresh Recovery。

## 9. 安全与性能

EncounterView 按玩家会话 ACL 生成，敌方精确数值与他人私有信息不进入 payload；Combat Log 文本为服务器 render 字段，按纯文本渲染（不作为 HTML 执行）。视图更新为事件驱动增量渲染，目标每事件 UI 应用 < 16 real ms，保持 60 FPS。

## 10. 验收标准

- 菜单集合与服务器 `LegalCombatOption[]` 严格一致，无 UI 私造选项。
- 双击/重发/刷新重提交至多生效一次。
- 浏览器 E2E：战斗中刷新后回到同一回合、同一选项集合，日志无缺失无重复。
- 玩家回合等待任意长 RealTime 不产生超时副作用。
- 敌方展示仅含 hp_bucket 级信息，与 AI 决策上下文的知识边界一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-020` | 菜单/目标与合法集合一致、无预测渲染（`RULE-COMBAT-044..045`） |
| `TEST-COMBAT-021` | 幂等提交与 stale 处理（`RULE-COMBAT-046..047`） |
| `TEST-COMBAT-022` | 刷新/断线恢复 E2E 矩阵（`RULE-COMBAT-048`） |

## 12. 关联文档

- `DOC-COMBAT-003`：选项与目标合法性唯一来源
- `DOC-COMBAT-007`：敌情投影的共同知识边界
- `DOC-RENDER-008`：命中/状态 VFX 播放契约
- `DOC-RENDER-009`：羊皮纸 UI 视觉系统
- `DOC-BACKEND-003`：重连与 Revision 对齐

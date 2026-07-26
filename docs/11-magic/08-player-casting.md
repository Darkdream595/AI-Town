---
doc_id: DOC-MAGIC-008
title: 玩家施法
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - player-casting-command
  - player-casting-feedback
depends_on:
  - DOC-MAGIC-005
  - DOC-MAGIC-006
  - DOC-MAGIC-007
  - DOC-FOUNDATION-004
requirements:
  - REQ-MAGIC-015
  - REQ-MAGIC-016
last_updated: 2026-07-26
---

# 玩家施法

## 1. 目的

定义玩家在居民模式下的施法命令、目标选择交互与结构化反馈，保证玩家与 AI 居民经过完全相同的校验流水线，并明确镇长模式与自然语言输入不构成施法特权通道。

## 2. 非目标

本文件不定义玩家模式切换与权限矩阵（`DOC-PLAYER-003/007/008` 拥有）、施法 UI 的视觉规格（`DOC-RENDER-009` 的羊皮纸 UI 体系）、战斗内玩家回合操作（`DOC-COMBAT-008`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `PlayerCastSpellCommand` | 玩家施法的 `PlayerCommand` 子类型，归一化为 `SpellCastCommand` |
| 法术面板 | 只读展示玩家角色 `SpellKnowledge` 与 Mana 状态的 UI 投影 |
| 目标拾取 | 玩家点选实体或地面点形成 `target_refs/aim_point` 的交互 |
| 施法反馈 | 校验/提交结果到玩家可读文案的结构化映射 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-015` | 玩家施法与 AI 施法共用 `DOC-MAGIC-005` 七级校验与同一提交管线；玩家不因操作者身份获得额外射程、消耗减免或合法性豁免，法律判定输入完全一致。 |
| `REQ-MAGIC-016` | 玩家只能施放自己角色 `SpellKnowledge=learned` 的注册法术；法术面板、快捷栏与命令入口都以 `spell_id` 引用 Catalog，客户端不能构造 Catalog 外定义。 |
| `RULE-MAGIC-041` | 镇长模式无身体、无 `CasterState`，不能施法；切回居民模式后使用该居民自身的 Mana 与知识。AdminCommand 不得代放法术或直接注入效果事件（`RULE-FOUNDATION-030`）。 |
| `RULE-MAGIC-042` | 自然语言输入（`DOC-PLAYER-005`）中的施法意图只能解析为对已学 `spell_id` 的选择建议，由玩家确认后发出结构化命令；自由文本本身不触发效果（`REQ-MAGIC-008` 同向）。 |
| `RULE-MAGIC-043` | 目标拾取只能选择客户端已渲染的已提交实体或有效地面点；服务器仍按最新 Revision 重验可见性与射程，客户端预判非法时应即时提示但拦截不是安全边界。 |
| `RULE-MAGIC-044` | 每次拒绝必须向玩家返回封闭 `reason_code`（`DES-MAGIC-005`）映射的中文文案与可行建议（如"目标超出射程 96wu"）；不允许静默失败。 |
| `RULE-MAGIC-045` | 玩家施法与 AI 施法在目击、法律后果、XP 成长（`RULE-MAGIC-033`）上同规则；玩家对居民施放 `consent_required` 法术同样需要同意事件，对话取得的同意由 DIALOGUE 流程落成结构化事件后方可引用。 |

## 5. 数据与接口

`DES-MAGIC-008`：`PlayerCastSpellCommand` payload（Command Envelope 内）：

```json
{
  "player_command_kind": "cast_spell",
  "actor_resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "spell_id": "spell.arcane.glowlight",
  "target_refs": [],
  "aim_point": null,
  "authorization_event_ids": [],
  "client_context": {
    "ui_source": "spell_panel",
    "client_predicted_legal": true
  }
}
```

`client_context` 仅用于遥测与 UX 诊断，不参与校验。法术面板投影复用 `DES-MAGIC-007` 候选结构（含 `legality_preview/cooldown_ready/mana_current`），另附 `studying` 条目的进度百分比用于展示。

## 6. 正常流程

1. 玩家打开法术面板或快捷栏，客户端渲染候选投影与 Mana 条。
2. 选择法术后进入目标拾取；`self/none` 模式直接确认。
3. 客户端发出 `PlayerCastSpellCommand`（携带 `command_id/expected_revision`）。
4. 服务器归一化为 `SpellCastCommand`，执行七级校验并提交。
5. 客户端消费 `SpellCastCommitted` 的 render projection 播放表现（`DOC-MAGIC-011`），或按 `RULE-MAGIC-044` 显示拒绝反馈。

## 7. 边界情况

- 浏览器刷新/断线重连：未提交命令按幂等键安全重发；已提交施法不重复生效（`RULE-FOUNDATION-022`）。
- 玩家在对话暂停（Overworld 暂停输入态）中发起施法：按 `RULE-FOUNDATION-038` 的暂停语义排队或拒绝，不在暂停世界内结算。
- 快捷栏引用的法术进入冷却：按钮置灰并显示 `ready_at_game_time` 倒计时，点击返回结构化提示而非发送必败命令。
- 玩家角色 defeated/昏迷：`can_initiate_actions=false`（`RULE-RESIDENT-038`），施法入口整体不可用。
- 玩家尝试对镇长模式下看到的远处实体施法：切回居民模式后目标不在感知/射程内则正常拒绝，镇长视野不注入居民可见性。

## 8. 错误与降级

命令被拒时客户端保持面板状态并显示原因；`TRANSIENT_OWNER_UNAVAILABLE` 提示稍后重试并允许一键重发（同 `command_id`）。文案缺失时退回显示 `reason_code` 原文，不猜测语义。客户端预测特效在提交失败时立即取消，不留视觉既成事实（`RULE-RENDER-022`）。

## 9. 安全与性能

客户端提交的一切字段视为不可信输入；数值、目标与授权引用全部服务器重验。`authorization_event_ids` 只传 ID。法术面板投影按 `knowledge_revision/state_revision` 增量刷新，不轮询全量 Catalog。单玩家施法命令速率限制 4 次/RealTime 秒，防止连点洪泛。

## 10. 验收标准

- 同一世界状态下，玩家与 AI 居民对同一法术/目标组合得到相同 verdict。
- 镇长模式、AdminCommand 与自由文本三条旁路尝试均无法产生施法效果。
- 全部 `reason_code` 有中文文案映射且拒绝路径可在 UI 复现。
- 断线重连、连点与冷却期操作不产生重复或非法状态变化。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-017` | `REQ-MAGIC-015..016`, `RULE-MAGIC-041..043` | 玩家/AI 同判定等价性测试；镇长/Admin/自由文本旁路反例 |
| `TEST-MAGIC-018` | `RULE-MAGIC-044..045` | 拒绝反馈映射完整性；同意事件引用与幂等重发 Integration Test |

## 12. 关联文档

- `DOC-MAGIC-005`：共用校验流水线
- `DOC-MAGIC-007`：候选投影结构复用
- `DOC-PLAYER-005`：自然语言输入解析边界
- `DOC-PLAYER-007/008`：居民/镇长模式权限
- `DOC-RENDER-009`：施法 UI 的视觉体系归属

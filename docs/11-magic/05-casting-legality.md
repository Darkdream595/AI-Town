---
doc_id: DOC-MAGIC-005
title: 施法合法性
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - casting-validation-pipeline
  - casting-legality-decision
depends_on:
  - DOC-FOUNDATION-005
  - DOC-MAGIC-003
  - DOC-MAGIC-004
  - DOC-WORLD-008
  - DOC-TIME-006
requirements:
  - REQ-MAGIC-009
  - REQ-MAGIC-010
last_updated: 2026-07-26
---

# 施法合法性

## 1. 目的

定义施法命令从接收、分级校验、法律检查到原子提交的唯一流水线，以及每级的判定输入与错误码，使"AI 只能选择已学会且合法可用的法术"（系统设计 §15）成为可执行、可测试的机制而非提示词约定。

## 2. 非目标

本文件不定义罪名分类与处罚——法律矩阵的唯一权威是 `DOC-WORLD-008`（`RULE-MAGIC-003`）；不定义效果结算内容（`DOC-MAGIC-009`）；不定义 Encounter 内回合合法性（`DOC-COMBAT-003` 拥有战斗行动合法集，但战斗内施法仍走本文件的 Mana/目标/注册校验）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `SpellCastCommand` | 由 `ActionProposal` 或 `PlayerCommand` 归一化得到的非权威施法请求 |
| 系统合法性 | 是否满足注册、学会、Mana、目标、射程、前置等机制条件 |
| 世界合法性 | 依 `DOC-WORLD-008` 法律状态与同意规则的世界内判定 |
| `SpellCastCommitted` | 施法成功的原子提交事件，携带全部效果结算结果引用 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-009` | 施法校验固定七级顺序：(1) Schema/引用解析 → (2) `SpellKnowledge` 已学 → (3) 枯竭与 Mana 充足 → (4) 目标模式与射程 → (5) 结构化前置（`RULE-MAGIC-018`）→ (6) 世界合法性 → (7) Reservation 与最新 Revision 提交检查。任一级失败即终止，后续级不执行，无状态变化。 |
| `REQ-MAGIC-010` | 世界合法性判定为确定性函数：输入为 `(spell 法律声明, 学派基线, 场景管辖, 目标同意状态, Encounter 上下文)`，输出 `permitted/restricted_authorized/rejected`；同一输入必须得到同一输出，模型文本不参与判定。 |
| `RULE-MAGIC-022` | `prohibited` 判定的施法请求（如镇区公共空间的攻击性 Elemental/Spirit，`RULE-WORLD-034`）对 AI 与玩家一律拒绝提交，不存在"提交后受罚"路径；世界内犯罪叙事只能来自其他已注册行为，不来自绕过本检查。 |
| `RULE-MAGIC-023` | `restricted` 法术需要结构化授权证据：目标同意事件、职业执照（如治疗者）或紧急救命例外记录（`RULE-WORLD-033`）；授权证据以 event ID 引用，不接受自由文本声明。 |
| `RULE-MAGIC-024` | Encounter 内施法：世界合法性委托给 Encounter 规则（战斗中对参战敌方的攻击性法术合法），但第 1–5 级与第 7 级校验不豁免；Overworld 判定为 `prohibited` 的法术不因发起战斗而追溯合法化。 |
| `RULE-MAGIC-025` | `consent_required` 法术对无行为能力目标（defeated、昏迷）在救助方向（治疗、净化）适用紧急例外并强制记录；伤害方向（诅咒）不存在紧急例外。 |
| `RULE-MAGIC-026` | 施法提交必须携带 `command_id` 与 `expected_revision`，满足 `RULE-FOUNDATION-022` 幂等；`ritual` 法术先经 `DOC-TIME-006` 建立长行动与 Reservation，完成检查点时重验第 3、4、6 级。 |
| `RULE-MAGIC-027` | 校验结果分类固定为 `VALID/REPLAN_REQUIRED/FORBIDDEN/TRANSIENT_OWNER_UNAVAILABLE`，与 `DOC-AI-010` 分级对齐；`FORBIDDEN` 包含未注册法术、未学会与 `prohibited` 判定。 |
| `RULE-MAGIC-028` | 合法性检查缓存只能用于 Prompt 候选过滤；提交时必须在最新 Revision 重新执行全部七级，缓存不作为授权依据。 |

## 5. 数据与接口

`DES-MAGIC-005`：`SpellCastCommand` 归一化结构与判定结果：

```json
{
  "command": {
    "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
    "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "expected_revision": 105,
    "caster_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "spell_id": "spell.restoration.minor_mend",
    "target_refs": ["01K1AB2CD3EF4GH5JK6MNP7QRW"],
    "aim_point": null,
    "declared_purpose": "healing",
    "authorization_event_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRX"]
  },
  "verdict": {
    "classification": "VALID",
    "legality": "restricted_authorized",
    "failed_stage": null,
    "reason_code": null
  }
}
```

`reason_code` 封闭集：`MAGIC_SPELL_UNKNOWN`、`MAGIC_SPELL_NOT_LEARNED`、`MAGIC_CASTER_EXHAUSTED`、`MAGIC_MANA_INSUFFICIENT`、`MAGIC_TARGET_INVALID`、`MAGIC_RANGE_EXCEEDED`、`MAGIC_PREREQUISITE_MISSING`、`MAGIC_CONSENT_MISSING`、`MAGIC_LEGALITY_PROHIBITED`、`MAGIC_ENCOUNTER_RULE_CONFLICT`、`stale_revision`。

Port：

```text
validate_spell_cast(command, decision_context_revision) -> CastVerdict
commit_spell_cast(command) -> SpellCastCommitted | CastRejection
```

## 6. 正常流程

1. Gateway 完成 Envelope 校验，AI 提案经 `DOC-AI-010` 形状校验后归一化为 `SpellCastCommand`。
2. MAGIC 按 `REQ-MAGIC-009` 七级顺序执行；第 6 级调用 `DOC-WORLD-008` `LegalContext` 与场景管辖数据。
3. `instant`：Orchestrator 取得目标/位置 Reservation，同一事务内 `consume_mana`、逐条结算 effect binding、写 `SpellCastCommitted` 并递增 Revision。
4. `ritual`：建立长行动，检查点按 `RULE-MAGIC-026` 重验，完成事务提交效果与事件。
5. 已提交事件的 `render` projection 驱动表现（`DOC-MAGIC-011`），感知与记忆消费见 `DOC-MAGIC-007/008`。

## 7. 边界情况

- 目标在校验与提交之间移出射程或离开 Scene：第 7 级以最新 Revision 重验第 4 级，失败返回 `REPLAN_REQUIRED`，不产生消耗。
- 目标在 ritual 进行中撤回同意：下一检查点第 6 级失败，长行动转 `interrupted`，已消耗 work 不返还（`RULE-TIME-035`）。
- 施法者在提交前进入 Encounter：Overworld 施法命令因 `RULE-FOUNDATION-028` 互斥状态被拒。
- 对自身施放 `consent_required` 法术视为已同意，无需授权证据。
- 同一 `command_id` 重放：返回原 verdict/result 引用，最多一次状态变化。

## 8. 错误与降级

第 6 级依赖的管辖或法律投影不可用时返回 `TRANSIENT_OWNER_UNAVAILABLE`，可重试，禁止降级为"默认允许"。任何级别的内部错误 fail closed 计为拒绝。拒绝结果对 AI 走 `DOC-AI-010` 修复/重规划，对玩家显示结构化原因（`DOC-MAGIC-008`）。

## 9. 安全与性能

第 1–5 级为纯内存校验，目标复杂度 O(targets)；第 6 级使用版本化法律矩阵缓存但按 `RULE-MAGIC-028` 在提交时重验。`authorization_event_ids` 只存 ID，不复制证据内容，防止 Secret 进入命令 payload（`RULE-FOUNDATION-024`）。校验拒绝是常态路径，不产生事件写放大。

## 10. 验收标准

- 七级顺序在全部拒绝 fixture 上可观测且短路正确（后级 side effect 为零）。
- `permitted/restricted/prohibited` 三类法术各有可执行的通过与拒绝用例（对齐 `DOC-WORLD-008` §10）。
- 相同输入的世界合法性判定跨进程、跨重放一致。
- 模型自由文本（`declared_purpose` 之外的任何叙述）无法改变 verdict。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-010` | `REQ-MAGIC-009`, `RULE-MAGIC-026..028` | 七级短路矩阵、幂等重放、缓存-提交重验 Integration Test |
| `TEST-MAGIC-011` | `REQ-MAGIC-010`, `RULE-MAGIC-022..023`, `RULE-MAGIC-025` | 法律判定 Table Test：镇区攻击禁令、授权证据、紧急例外方向性 |
| `TEST-MAGIC-012` | `RULE-MAGIC-024` | Encounter 内外合法集切换与追溯合法化反例 |

## 12. 关联文档

- `DOC-WORLD-008`：法律矩阵与同意规则的唯一权威
- `DOC-MAGIC-003`：Mana 消耗与枯竭前置
- `DOC-MAGIC-004`：目标模式、射程与前置声明
- `DOC-MAGIC-009`：通过校验后的效果结算
- `DOC-AI-010`：AI 侧校验分级与修复
- `DOC-TIME-006`：ritual 长行动生命周期

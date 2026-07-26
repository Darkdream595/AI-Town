---
doc_id: DOC-COMBAT-007
title: NPC 战术决策与模型降级
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - combat-ai-turn-decision
  - combat-decision-context
  - tactical-fallback-trigger
depends_on:
  - DOC-FOUNDATION-005
  - DOC-TIME-010
  - DOC-COMBAT-002
  - DOC-COMBAT-003
  - DOC-AI-004
  - DOC-AI-005
  - DOC-AI-011
requirements:
  - REQ-COMBAT-007
last_updated: 2026-07-26
---

# NPC 战术决策与模型降级

## 1. 目的

`REQ-COMBAT-007`：定义 AI 控制的 Combatant 每回合恰好一次模型决策的请求边界、战斗 DecisionContext 的内容与知识限制、返回校验与修复上限，以及触发 `DOC-AI-011` Tactical Utility fallback 的确定性条件，保证模型只选行动、永不决定数值结果，且模型完全不可用时战斗仍能合法推进到终结。

## 2. 非目标

不定义 Prompt 版本管理（`DOC-AI-003`）、`combat_action_parameters` Schema（`DOC-AI-004`）、并发调度与取消（`DOC-AI-009`）或 Tactical Utility 的评分函数（`DOC-AI-011`）；不覆盖玩家回合（`DOC-COMBAT-008`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Combat Decision Request | 针对一个 `(encounter_id, turn_index)` 的一次模型调用 |
| CombatDecisionContext | 不可变的战斗上下文投影，构建于 Turn 进入 `awaiting_decision` 的已提交 Revision |
| Observed Enemy View | 对敌方的有限观测投影：HP 桶、可见状态效果、站位，不含精确属性 |
| Repair Pass | 对格式可修复输出的至多一次重新校验，不重新调用模型 |
| Decision Deadline | 单次决策的 RealTime 上限，首版 8000 ms |
| Tactical Fallback | 以 `LegalCombatOption[]` 为输入的 `DOC-AI-011` 确定性选择 |

## 4. 规则与不变量

- `RULE-COMBAT-038`：每个 AI Turn 至多发起一次 Combat Decision Request，模型 ID 固定 `deepseek-v4-flash`，prompt 使用注册的 `resident-combat-turn/v1`；同一 `turn_index` 不进行第二次模型调用，格式失败走 Repair Pass 或直接 fallback。
- `RULE-COMBAT-039`：CombatDecisionContext 只包含：本方完整 CombatantSheet、Observed Enemy View、`DOC-COMBAT-003` 的完整 `LegalCombatOption[]`（含 option_id、目标集合、cost）、最近至多 6 个 Turn 的行动摘要、本 Combatant 的 persona/关系摘要。不包含任何公式、概率、敌方精确属性或未授权 Secret（`RULE-FOUNDATION-020`、`RULE-FOUNDATION-024`）。
- `RULE-COMBAT-040`：模型输出必须是 `DOC-AI-004` `combat_action_parameters` 的合法实例且 `encounter_id/turn_index` 与请求一致、`action_option_id` 属于给定集合、目标为对应 Legal Target Set 的合法子集；违反任一条即校验失败。模型输出的其余文本一律丢弃，不进入状态或事件。
- `RULE-COMBAT-041`：fallback 触发条件封闭：模型超时（超过 Decision Deadline）、provider 不可用、Repair Pass 后仍非法、`DOC-AI-009` 判定的取消/丢弃。触发后由 Tactical Fallback 从同一份 `LegalCombatOption[]` 确定性选择，结果与模型结果走完全相同的 `submit_combat_action` 提交管线。
- `RULE-COMBAT-042`：命中、伤害、状态施加、逃跑成败、掉落等一切数值结果由 `DOC-COMBAT-004/006` 结算；模型选择不同选项只改变被结算的行动，不改变任何公式输入之外的东西（`RULE-AI-028` 执行点）。
- `RULE-COMBAT-043`：每次决策（含 fallback）按 `DOC-TIME-010` 写 AI Replay Record（validated output 或 fallback 选择、context hash、结果分类）；历史重放优先读取 recorded validated output，不重新调用模型。

## 5. 数据与接口

`DES-COMBAT-007`：注册 `schema.combat.decision_context.v1`；required 字段为
`context_schema_version/encounter_id/turn_index/actor_combatant_id/observed_revision/ally_sheets/enemy_views/legal_options/recent_turns/persona_summary_ref`。

```json
{
  "context_schema_version": 1,
  "encounter_id": "01K1AB2CD3EF4GH5JK6MNP7QSA",
  "turn_index": 12,
  "actor_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSD",
  "observed_revision": 88,
  "ally_sheets": ["01K1AB2CD3EF4GH5JK6MNP7QSD"],
  "enemy_views": [
    {
      "combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
      "hp_bucket": "wounded",
      "visible_status_ids": ["status.burning"],
      "formation_slot": "front_left"
    }
  ],
  "legal_options": ["combat_option.attack", "combat_option.defend", "combat_option.flee"],
  "recent_turns": [
    {"turn_index": 11, "actor_combatant_id": "01K1AB2CD3EF4GH5JK6MNP7QSC", "option_id": "combat_option.attack", "summary": "命中，目标受创"}
  ],
  "persona_summary_ref": "01K1AB2CD3EF4GH5JK6MNP7QSJ"
}
```

`hp_bucket` 封闭 enum：`unharmed/scratched/wounded/critical/down`。接口：

```text
request_combat_decision(encounter_id, turn_index) -> CombatDecisionOutcome
```

`CombatDecisionOutcome` 分类封闭：`model_decision/fallback_decision`，二者载荷同为合法 `combat_action` 提交参数。

## 6. 正常流程

1. Turn 进入 `awaiting_decision` 且 Owner 为 AI 时，构建 CombatDecisionContext 并冻结。
2. 经 `DOC-AI-009` 调度发起模型请求（战斗优先级高于普通居民请求）。
3. strict decode 成功且 `RULE-COMBAT-040` 全部通过则形成 ValidatedIntent；可修复的格式偏差执行一次 Repair Pass。
4. 任一 fallback 条件触发时改走 Tactical Fallback。
5. 结果提交 `submit_combat_action`，写 Replay Record，Turn 解析继续。

## 7. 边界情况

- 模型在 deadline 内返回但引用了构建后已失效的目标：属于校验失败而非重掷理由——按 `DOC-COMBAT-003` 的复验语义以刷新集合触发 fallback，不再次调用模型。
- Overworld 已暂停，战斗决策没有 GameTime 压力；Decision Deadline 只约束 RealTime，保证玩家不长时间等待。
- 敌我双方均为 AI（防卫响应等触发源）：逐 Turn 同规则执行，仍受单世界活跃 Encounter 上限 1 约束。
- `legal_options` 只有 `defend/pass/surrender` 可用（完全被压制）：模型与 fallback 都只能从中选择，空集合是 `DOC-COMBAT-003` 的 invariant violation。
- Replay Record 的 context hash 不匹配历史重放：返回 mismatch 并停止重放（`RULE-TIME-060`），不拿相似记录替代。

## 8. 错误与降级

模型侧错误不产生玩家可见失败：一切失败路径终止于 Tactical Fallback 的合法提交。Tactical Fallback 自身因候选空而失败时按 `DOC-AI-011` 返回 `fallback_no_legal_candidate` 并触发 COMBAT 一致性暂停。provider 恢复后自下一个 AI Turn 起自动回到模型决策，无需人工干预。

## 9. 安全与性能

CombatDecisionContext 经 `DOC-AI-002` 同一 ACL 管道构建，Secret 与私人记忆按授权过滤；`reasoning_content` 不落盘（`RULE-TIME-060`）。上下文预算目标单请求 ≤ 2000 prompt token；Observed Enemy View 的 HP 桶化同时是知识边界与 token 控制手段。

## 10. 验收标准

- 每个 AI Turn 恰好一次模型调用，重复调用被调度层拒绝。
- 上下文不含公式、敌方精确数值与未授权 Secret 的断言测试通过。
- 四类 fallback 条件各自触发且产物与模型产物走同一提交管线。
- FakeModelProvider 全故障下，fixture 战斗完整推进到合法终结。
- Replay Record 使离线重放复现同一 validated output。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-017` | 单次调用、上下文知识边界与 hp_bucket 投影（`RULE-COMBAT-038..039`） |
| `TEST-COMBAT-018` | 输出校验矩阵与 Repair Pass 上限（`RULE-COMBAT-040`） |
| `TEST-COMBAT-019` | fallback 触发封闭集、同管线提交与 Replay Record（`RULE-COMBAT-041..043`） |

## 12. 关联文档

- `DOC-AI-004`：`combat_action_parameters` wire Schema
- `DOC-AI-009`：调度、取消与优先级
- `DOC-AI-011`：Tactical Utility 评分与安全边界
- `DOC-COMBAT-003`：`LegalCombatOption[]` 唯一来源
- `DOC-TIME-010`：AI Replay Record 契约

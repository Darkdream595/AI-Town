---
doc_id: DOC-DIALOGUE-002
title: 距离、视线与参与条件
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-proximity-conditions
  - dialogue-attention-reservation
depends_on:
  - DOC-FOUNDATION-006
  - DOC-DIALOGUE-001
  - DOC-MAP-001
  - DOC-RESIDENT-001
  - DOC-RESIDENT-002
  - DOC-AI-005
  - DOC-TIME-004
requirements:
  - REQ-DIALOGUE-002
last_updated: 2026-07-26
---

# 距离、视线与参与条件

## 1. 目的

`REQ-DIALOGUE-002`：定义发起与维持对话的几何条件（距离、视线）、共通语言条件、居民可用性与同意条件、参与者集合变更规则和注意力 Reservation，保证对话只发生在规则上可感知且能理解彼此的实体之间；`DOC-AI-005` talk 行校验列（距离、语言、同意、会话状态）中前三项的 DIALOGUE validator 语义由本文拥有。

## 2. 非目标

本文不定义寻路与网格（`DOC-MAP-007`）、居民 Need/情绪数值（`DOC-RESIDENT-004`）、会话状态机（`DOC-DIALOGUE-001`）或群组轮次策略（`DOC-DIALOGUE-008`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Talk Range | 对话发起与维持的最大距离，首版基准 `96 wu`（3 tile，按 `RULE-FOUNDATION-040`） |
| Line of Sight | 两实体位置连线不被遮挡 Polygon 阻断，几何数据由 MAP 提供 |
| Participant Set | Conversation 当前有权发言/接收秘密内容的实体集合 |
| Attention Reservation | 居民在会话期间对其调度注意力的临时排他声明，属于 TIME 资源（`RULE-FOUNDATION-034` 体系中的 Reservation 语义） |
| Availability | 居民可被对话的状态投影：存活、非昏迷、非 Encounter 独占、非长时动作锁定 |
| Shared Language | 双方对同一 `language_id` 均达到理解阈值的共通语言，数据来源为 RESIDENT 的 `language_proficiencies`（`DOC-RESIDENT-002`） |
| Initiation Consent | 发起侧同意语义：Availability 与 Reservation 授予构成进入会话的隐式同意，居民自主拒绝以会话内 Speech Act 表达 |

## 4. 规则与不变量

- `RULE-DIALOGUE-007`：发起对话要求发起方与目标同 Scene、距离 `<= 96 wu` 且 Line of Sight 成立；任一不满足则发起被拒绝并返回具体 reason code，客户端不得预渲染已开始的假象。
- `RULE-DIALOGUE-008`：距离与视线判定在服务器最新 Revision 上以持久化量化坐标（`RULE-FOUNDATION-042`）计算，禁止用 Client 插值坐标。
- `RULE-DIALOGUE-009`：目标 Availability 为 false 时发起失败；可用性投影只读 RESIDENT/TIME 已提交状态，对话域不自行定义居民状态。
- `RULE-DIALOGUE-010`：会话建立时对每位居民参与者创建 Attention Reservation，带 owner、到期 GameTime 与状态；Reservation 失效或被更高优先级抢占时按 `DOC-DIALOGUE-007` 迁移会话。
- `RULE-DIALOGUE-011`：会话维持期间每 World Tick 复算距离/视线；超限先进入宽限期 `10 game minutes`（ utterance 提交时即时复算），宽限期满仍超限则 `interrupted → ended(participant_left)`。
- `RULE-DIALOGUE-012`：participant set 只允许整员加入/退出事件变更；中途加入者不能回溯读取加入前的 utterance 内容，除非内容 access level 允许（`DOC-MEMORY-009`）。
- `RULE-DIALOGUE-076`：发起对话要求双方至少存在一种 Shared Language：对同一 `language_id`，双方 `language_proficiencies` level `>= 60`（阈值随 `RULE-RESIDENT-009` 的公共服务基线）；玩家实体视为具有 `language.crown_common` level `100`。无共通语言则发起被拒并返回 reason `no_shared_language`；会话语言在创建时确定性选定（双方 level 之和最高者，并列按 `language_id` 字典序）并记录，`DOC-AI-005` talk 校验列的「语言」项由本条实现。
- `RULE-DIALOGUE-077`：发起同意语义：目标 Availability 为 true 且 Attention Reservation 授予成功即构成进入会话的隐式同意（自动接受），`DOC-AI-005` talk 校验列的「同意」项由本条实现；居民的自主拒绝不阻塞会话建立，而以首轮 `refuse` / `farewell` Speech Act 表达（`RULE-DIALOGUE-027`）。拒绝时的降级路径：会话经 `dialogue.end`（reason `completed`）正常终结、统一 teardown 释放全部资源，拒绝作为已提交 Speech Fact 进入记忆与关系管道（`DOC-DIALOGUE-009`）；再次发起是新的独立会话请求，仍须完整通过本文全部参与条件校验，不存在跳过校验的重试通道。

## 5. 数据与接口

`DES-DIALOGUE-002`：参与条件校验输入。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "observed_revision": 120,
  "checks": [
    {
      "pair": ["01K1AB2CD3EF4GH5JK6MNP7QRX", "01K1AB2CD3EF4GH5JK6MNP7QRV"],
      "same_scene": true,
      "distance_wu": 64.0,
      "line_of_sight": true,
      "target_availability": true,
      "shared_language_ids": ["language.crown_common"]
    }
  ],
  "selected_language_id": "language.crown_common",
  "attention_reservations": [
    {"reservation_id": "01K1AB2CD3EF4GH5JK6MNP7QRW", "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRV", "expires_game_time": 5460, "state": "granted"}
  ]
}
```

依赖接口：MAP 提供遮挡查询，RESIDENT 提供 Availability 投影与 `language_proficiencies` 投影（`DOC-RESIDENT-002`），TIME 提供 Reservation/调度接口；Dialogue 只消费，不拥有这些真值。

## 6. 正常流程

1. 玩家点击居民或居民 ActionProposal 指向 `talk`：构造 `dialogue.start_conversation`。
2. 服务器在最新 Revision 复算距离/视线/Availability/共通语言，通过后创建 Conversation 与 Attention Reservation（Reservation 授予即隐式同意成立，`RULE-DIALOGUE-077`）。
3. 维持期 Tick 复算；任一方移动超距进入宽限，回到范围内立即清除宽限。
4. 会话结束时统一释放全部 Attention Reservation。

## 7. 边界情况

- 隔着关闭的门对话：视线不成立，发起被拒；开门瞬间 Client 显示的近距不改变判定时点。
- 目标在长时动作（`DOC-TIME-006`）锁定中：Availability false；玩家可等待，系统不自动排队偷跑。
- 距离恰为 `96 wu`：闭区间允许；浮点比较使用 Dialogue 域 epsilon `1/16 wu`。
- 多参与者三角站位：对每对参与者分别判定（含 Shared Language），任一对失败则该参与者不能加入。
- 双方无共通语言（双方对任何同一 `language_id` 都未同时达到阈值）：发起被拒 reason `no_shared_language`，不产生 Conversation 与 Reservation；含玩家的会话因玩家视为掌握 `language.crown_common` 而只受目标语言约束。
- 首轮即被拒绝：会话短暂建立后经 `refuse`/`farewell` 正常终结，Episode 事件照发（`DOC-DIALOGUE-009`），不视为发起校验失败。

## 8. 错误与降级

- MAP 遮挡查询失败：fail closed 视为视线不成立，记录 reason `los_query_failed`。
- Attention Reservation 超时未授予：发起失败，不留半建立会话。
- Tick 复算期间参与者跨 Scene 迁移：立即 `interrupted`，不按宽限期处理。

## 9. 安全与性能

- 距离/视线判定在服务器执行，Client 无法伪造近距。
- Tick 复算只对非终态 Conversation 的参与者对执行，复杂度 `O(Σ k²)`，k 为参与者数（首版 `k <= 4`，见 `DOC-DIALOGUE-008`）。

## 10. 验收标准

- 距离边界（95/96/97 wu）、遮挡开关门、宽限期与跨 Scene 用例全部通过。
- 共通语言矩阵（双方 level 59/60/61 × 有无共同 `language_id` × 玩家参与）判定与会话语言选定确定性通过。
- 拒绝降级路径：首轮 `refuse` 后会话正常终结、资源零泄漏、Speech Fact 进入事件流。
- Reservation 泄漏检查：任意结束路径后不存在悬挂 Attention Reservation。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-003` | `RULE-DIALOGUE-007..009` 发起条件与 reason code |
| `TEST-DIALOGUE-004` | `RULE-DIALOGUE-010..012` Reservation 生命周期、宽限期、中途加入可见性 |
| `TEST-DIALOGUE-027` | `RULE-DIALOGUE-076..077` 共通语言判定与会话语言选定、隐式同意与拒绝降级路径 |

## 12. 关联文档

- `DOC-DIALOGUE-001`（状态机）、`DOC-DIALOGUE-007`（打断）、`DOC-DIALOGUE-008`（群组）、`DOC-DIALOGUE-009`（拒绝的事件影响）
- `DOC-MAP-001`、`DOC-MAP-006`（坐标与遮挡）、`DOC-RESIDENT-001`、`DOC-RESIDENT-002`（语言数据 canonical）、`DOC-AI-005`（talk 校验列）、`DOC-TIME-004`（调度）

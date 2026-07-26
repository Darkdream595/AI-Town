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
  - DOC-TIME-004
requirements:
  - REQ-DIALOGUE-002
last_updated: 2026-07-26
---

# 距离、视线与参与条件

## 1. 目的

`REQ-DIALOGUE-002`：定义发起与维持对话的几何条件（距离、视线）、居民可用性条件、参与者集合变更规则和注意力 Reservation，保证对话只发生在规则上可感知彼此的实体之间。

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

## 4. 规则与不变量

- `RULE-DIALOGUE-007`：发起对话要求发起方与目标同 Scene、距离 `<= 96 wu` 且 Line of Sight 成立；任一不满足则发起被拒绝并返回具体 reason code，客户端不得预渲染已开始的假象。
- `RULE-DIALOGUE-008`：距离与视线判定在服务器最新 Revision 上以持久化量化坐标（`RULE-FOUNDATION-042`）计算，禁止用 Client 插值坐标。
- `RULE-DIALOGUE-009`：目标 Availability 为 false 时发起失败；可用性投影只读 RESIDENT/TIME 已提交状态，对话域不自行定义居民状态。
- `RULE-DIALOGUE-010`：会话建立时对每位居民参与者创建 Attention Reservation，带 owner、到期 GameTime 与状态；Reservation 失效或被更高优先级抢占时按 `DOC-DIALOGUE-007` 迁移会话。
- `RULE-DIALOGUE-011`：会话维持期间每 World Tick 复算距离/视线；超限先进入宽限期 `10 game minutes`（ utterance 提交时即时复算），宽限期满仍超限则 `interrupted → ended(participant_left)`。
- `RULE-DIALOGUE-012`：participant set 只允许整员加入/退出事件变更；中途加入者不能回溯读取加入前的 utterance 内容，除非内容 access level 允许（`DOC-MEMORY-009`）。

## 5. 数据与接口

`DES-DIALOGUE-002`：参与条件校验输入。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "observed_revision": 120,
  "checks": [
    {
      "pair": ["01K1AB2CD3EF4GH5JK6MNP7QRU", "01K1AB2CD3EF4GH5JK6MNP7QRV"],
      "same_scene": true,
      "distance_wu": 64.0,
      "line_of_sight": true,
      "target_availability": true
    }
  ],
  "attention_reservations": [
    {"reservation_id": "01K1AB2CD3EF4GH5JK6MNP7QRW", "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRV", "expires_game_time": 5460, "state": "granted"}
  ]
}
```

依赖接口：MAP 提供遮挡查询，RESIDENT 提供 Availability 投影，TIME 提供 Reservation/调度接口；Dialogue 只消费，不拥有这些真值。

## 6. 正常流程

1. 玩家点击居民或居民 ActionProposal 指向 `talk`：构造 `dialogue.start_conversation`。
2. 服务器在最新 Revision 复算距离/视线/Availability，通过后创建 Conversation 与 Attention Reservation。
3. 维持期 Tick 复算；任一方移动超距进入宽限，回到范围内立即清除宽限。
4. 会话结束时统一释放全部 Attention Reservation。

## 7. 边界情况

- 隔着关闭的门对话：视线不成立，发起被拒；开门瞬间 Client 显示的近距不改变判定时点。
- 目标在长时动作（`DOC-TIME-006`）锁定中：Availability false；玩家可等待，系统不自动排队偷跑。
- 距离恰为 `96 wu`：闭区间允许；浮点比较使用 Dialogue 域 epsilon `1/16 wu`。
- 多参与者三角站位：对每对参与者分别判定，任一对失败则该参与者不能加入。

## 8. 错误与降级

- MAP 遮挡查询失败：fail closed 视为视线不成立，记录 reason `los_query_failed`。
- Attention Reservation 超时未授予：发起失败，不留半建立会话。
- Tick 复算期间参与者跨 Scene 迁移：立即 `interrupted`，不按宽限期处理。

## 9. 安全与性能

- 距离/视线判定在服务器执行，Client 无法伪造近距。
- Tick 复算只对非终态 Conversation 的参与者对执行，复杂度 `O(Σ k²)`，k 为参与者数（首版 `k <= 4`，见 `DOC-DIALOGUE-008`）。

## 10. 验收标准

- 距离边界（95/96/97 wu）、遮挡开关门、宽限期与跨 Scene 用例全部通过。
- Reservation 泄漏检查：任意结束路径后不存在悬挂 Attention Reservation。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-003` | `RULE-DIALOGUE-007..009` 发起条件与 reason code |
| `TEST-DIALOGUE-004` | `RULE-DIALOGUE-010..012` Reservation 生命周期、宽限期、中途加入可见性 |

## 12. 关联文档

- `DOC-DIALOGUE-001`（状态机）、`DOC-DIALOGUE-007`（打断）、`DOC-DIALOGUE-008`（群组）
- `DOC-MAP-001`、`DOC-MAP-006`（坐标与遮挡）、`DOC-RESIDENT-001`、`DOC-TIME-004`（调度）

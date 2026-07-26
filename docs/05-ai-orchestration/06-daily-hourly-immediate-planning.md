---
doc_id: DOC-AI-006
title: Daily Plan、Hourly Intent 与 Immediate Action
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - three-layer-resident-planning
  - plan-staleness-and-abort
depends_on:
  - DOC-AI-001
  - DOC-AI-004
  - DOC-RESIDENT-009
  - DOC-TIME-004
requirements:
  - REQ-AI-006
last_updated: 2026-07-26
---

# Daily Plan、Hourly Intent 与 Immediate Action

## 1. 目的

`REQ-AI-006`：定义日、小时、即时三层 artifact 的 strict contract、版本、有效期、放弃条件、stale 判定和重规划关系。

## 2. 非目标

计划不是日程强制、Reservation、路径或世界事实；TIME 决定调度机会，Domain 决定行动合法与结果。

## 3. 术语与定义

| 层 | 作用 | 默认有效范围 |
|---|---|---|
| Daily Plan | 当日目标、工作/社交/资源/风险权衡 | 当前游戏日，重大变化失效 |
| Hourly Intent | 一个目标及候选 Action sequence | 最多 120 游戏分钟 |
| Immediate Action | DOC-AI-004 单个可验证 Proposal | 直到 deadline/revision 变化 |
| Abort Condition | owner 可计算的稳定 condition ID |
| Stale Fingerprint | plan 依赖的 owner projection versions/hash |

## 4. 数据与接口

`DES-AI-006`：Daily Plan：

```json
{
  "schema_version": 1,
  "plan_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "observed_revision": 84,
  "game_day_index": 2,
  "goals": [
    {"goal_id": "goal.daily.obtain_medicine", "priority": 80, "success_condition_id": "inventory.has_healing_item", "abandon_condition_ids": ["danger_detected"], "target_game_time": 2100}
  ],
  "risk_response_ids": ["response.seek_safety"],
  "dependency_fingerprint": "sha256:93ff3d7c",
  "expires_at_game_time": 2880
}
```

Hourly Intent：

```json
{
  "schema_version": 1,
  "intent_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "parent_plan_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "goal_id": "goal.daily.obtain_medicine",
  "observed_revision": 84,
  "candidate_action_ids": ["move_to", "buy"],
  "expected_start_game_time": 1830,
  "expires_at_game_time": 1950,
  "abort_condition_ids": ["shop_closed", "insufficient_funds", "danger_detected"],
  "dependency_fingerprint": "sha256:7ea5018d"
}
```

Immediate artifact 是 DOC-AI-004 `ActionProposalV1` 加服务器 envelope 和 `parent_intent_id`。Plans 状态：

```text
proposed -> active -> satisfied | abandoned | expired | superseded
active -> stale -> superseded | abandoned
```

## 5. 规则与不变量

- `RULE-AI-031`：上层只约束目标与候选，不预批准下层；每个 Immediate Action 都在最新 Revision 独立校验。
- `RULE-AI-032`：Daily/Hourly artifact 必须携带 observed Revision、expiry、dependency fingerprint 和 version；激活/终止幂等。
- `RULE-AI-033`：安全、critical Need、健康限制、Encounter、目标不可用、deadline miss 或关键 dependency version 变化使相关计划 stale/abort。
- `RULE-AI-034`：stale plan 不继续生成 Immediate Action；先记录 `stale_reason_code` 再 replan，不改写旧计划。
- `RULE-AI-035`：成功只由 committed event 满足 registered condition；模型自述“完成”无效。
- `RULE-AI-036`：候选 sequence 不是宏命令；每步提交后下一步重新观察。

## 6. 正常流程

每日边界或无有效计划时生成 Daily Plan；Scheduler 到 routine/deadline 生成 Hourly Intent；Immediate job 从当前 Intent 选择一项 action；提交事件更新 condition projection；满足则关闭 intent/goal，否则继续或在 abort/stale 时重规划。

## 7. 边界情况

跨午夜长行动固定原 definition version，但 Daily Plan 到期后新计划可继承 active commitment；高倍速不能一次提交整个候选序列；玩家影响目标后只使相关 dependency stale；多个目标并存按 priority、deadline、Need 和 commitment 排序，不允许低价值目标饿死 safety。

## 8. 错误与降级

Daily 生成失败可保留上一计划中仍合法的 commitments，并由 Utility AI 维持安全；Hourly 失败生成 safe immediate candidate；Immediate 失败按 DOC-AI-010/011。任何 replan 有每 actor 冷却，防止循环。

## 9. 安全与性能

每 Resident 最多 active Daily 1、Hourly 1；Daily goals 8、candidate actions 6、abort conditions 8。历史只存结构化摘要和版本，不存 reasoning。fingerprint 按 owner version 构建，不包含 secret payload。

## 10. 验收标准

- 三层状态机、expiry 与 parent 引用可重放。
- stale/abort fixture 不执行后续候选或倒填成功。
- 每个 action 后重新观察，最新 Domain rule 始终生效。
- 模型离线时 safety/Need 可继续且不虚构 Daily success。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-021` | Daily/Hourly schema、state 与 expiry |
| `TEST-AI-022` | dependency stale/abort matrix |
| `TEST-AI-023` | committed condition 才满足 goal |
| `TEST-AI-024` | high-speed/no-macro/replan-loop bounds |

## 12. 关联文档

- `DOC-RESIDENT-009`：routine 只提供候选
- `DOC-TIME-004`：调度、deadline、fairness
- `DOC-AI-011`：无模型 fallback

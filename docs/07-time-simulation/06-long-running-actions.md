---
doc_id: DOC-TIME-006
title: 长时间行动生命周期
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - long-action-lifecycle
  - long-action-progress
  - long-action-interruption-recovery
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-004
  - DOC-TIME-005
  - DOC-RESIDENT-001
requirements:
  - REQ-TIME-006
last_updated: 2026-07-26
---

# 长时间行动生命周期

## 1. 目的

`REQ-TIME-006`：定义 work、craft、gather、build、repair、travel、rest 等跨多个游戏分钟行动的状态机、确定性进度、checkpoint、暂停、中断、取消、完成和崩溃恢复。

## 2. 非目标

本文不定义具体行动的 work amount、产出、技能公式或资源语义；Action owner 提供 `LongActionDefinition`，TIME 负责按其已验证 work contract 调度生命周期。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Required Work | owner 以整数 work units 声明的完成总量 |
| Progress | 已提交 `completed_work_units`，不是动画百分比或墙钟时间 |
| Checkpoint | owner 声明的可原子提交中间点，可有资源消费或结果 |
| Interruption | 外部状态使 running action 暂停并等待 resume/replan |
| Cancellation | actor/owner 主动终止，按 owner compensation policy 结算 |
| Recovery Required | 崩溃后无法从 Event/Reservation 唯一判断下一状态 |

## 4. 规则与不变量

- `RULE-TIME-031`：状态机只允许 `scheduled → reserving → running ↔ paused/interrupted → completing → completed`，以及从非终态进入 `cancelled/failed/recovery_required`。
- `RULE-TIME-032`：`completed_work_units` 单调不减且不得超过 `required_work_units`；进度只由已提交 checkpoint 增加。
- `RULE-TIME-033`：进入 running 前必须持有全部声明的排他 Reservation；完成时 owner 在同一事务消费/释放资源、提交结果与 Completion Event。
- `RULE-TIME-034`：pause 冻结 GameTime 时不增加 work；tier 降级可以改变 batch 粒度，不能改变总 work、rate 公式或 checkpoint 顺序。
- `RULE-TIME-035`：interrupt/cancel 必须记录 reason、actor、game_time、last_checkpoint 和 owner compensation policy ID；不能删除已提交消耗。
- `RULE-TIME-036`：同一 `long_action_id + checkpoint_index` 最多提交一次；恢复重放返回原 checkpoint result。

## 5. 数据与接口

`DES-TIME-006`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/long-action/v1",
  "type": "object",
  "required": ["schema_version", "long_action_id", "actor_id", "action_id", "state", "required_work_units", "completed_work_units", "next_checkpoint_index", "version"],
  "properties": {
    "schema_version": {"const": 1},
    "long_action_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "actor_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "action_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"},
    "state": {"enum": ["scheduled", "reserving", "running", "paused", "interrupted", "completing", "completed", "cancelled", "failed", "recovery_required"]},
    "required_work_units": {"type": "integer", "minimum": 1},
    "completed_work_units": {"type": "integer", "minimum": 0},
    "next_checkpoint_index": {"type": "integer", "minimum": 0},
    "version": {"type": "integer", "minimum": 1},
    "expected_end_game_time": {"type": ["integer", "null"], "minimum": 0}
  },
  "additionalProperties": false
}
```

接口：

```text
schedule_long_action(definition, actor_id, command_id) -> LongAction
advance_long_action(long_action_id, due_game_time, expected_version) -> CheckpointResult
interrupt_long_action(long_action_id, reason, causation_id) -> TransitionResult
resume_long_action(long_action_id, resume_context) -> TransitionResult
recover_long_action(long_action_id, event_tail, reservation_set) -> RecoveryResult
```

## 6. 正常流程

1. owner 校验 Action 与 required work，TIME 创建 scheduled record。
2. 按 `DOC-TIME-007` 获取 Reservation，转为 running。
3. Event Queue 在 GameTime deadline 触发 checkpoint。
4. owner 依据 actor/state/skill projection 计算本 checkpoint 的整数 work delta。
5. 达到总 work 后进入 completing；同一事务结算结果、Reservation 和 DomainEvent，转为 completed。

## 7. 边界情况

- actor Needs/健康恶化：owner 返回 interruption reason，行动停在 last committed checkpoint。
- 路径或工作点失效：释放可释放的空间 Reservation，保留已消耗资源，进入 interrupted/replan。
- completion 事务失败：保持 completing 前状态或幂等重试同 checkpoint，绝不重复产出。
- 玩家关闭游戏：shutdown barrier 先落盘当前状态；离线不增加 work。
- action definition 升级：运行中实例固定 definition version；新版本只作用于新实例，除非有显式 migration。

## 8. 错误与降级

进度越界、未知状态迁移、丢失 Reservation 或 checkpoint hash 不一致返回 `TIME_LONG_ACTION_INVARIANT_FAILED` 并进入 recovery_required。Recovery 无唯一结论时保持 world paused，禁止自动标记 completed 或退还全部资源。

## 9. 安全与性能

每 Tick 处理长任务 checkpoint 有界批量，业务计算不得调用网络。Action parameters 在创建前由 owner Schema 限幅。历史只保留事件/摘要，不在 record 中复制模型 reasoning 或敏感上下文。

## 10. 验收标准

- 状态机所有合法边可达，非法边零副作用。
- progress 在 Active/Warm/Background 和倍率变化下结果一致。
- interrupt、cancel、resume、completion 各自保持资源与事件原子性。
- crash 发生在 checkpoint 前、中、后都能唯一恢复或明确 recovery_required。
- 同一 checkpoint 重放不会重复产出。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-016` | `RULE-TIME-031..032` state/progress property test |
| `TEST-TIME-017` | `RULE-TIME-033..035` Reservation/interruption/compensation |
| `TEST-TIME-018` | `RULE-TIME-036` crash 与 checkpoint idempotency |

## 12. 关联文档

- `DOC-TIME-005`：tier 的 batch 粒度
- `DOC-TIME-007`：Reservation 与并发冲突
- `DOC-TIME-008`：checkpoint deadline queue
- `DOC-RESIDENT-009`：Resident 日常行动来源
- `DOC-ECON-010`：craft 业务 work/资源定义

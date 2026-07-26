---
doc_id: DOC-RESIDENT-009
title: 日常结构、中断与长行动协作
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-routine-preferences
  - resident-interruption-policy
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-004
  - DOC-RESIDENT-006
  - DOC-MAP-008
requirements:
  - REQ-RESIDENT-009
last_updated: 2026-07-26
---

# 日常结构、中断与长行动协作

## 1. 目的

`REQ-RESIDENT-009`：定义居民日常可用窗口、routine 偏好、中断优先级与长行动参与约束；TIME 拥有实际 scheduling、deadline、Reservation 和模拟层级，AI 拥有具体行动决策。

## 2. 非目标

不推进 GameTime、不创建 Daily Plan/ActionProposal、不计算路径、不执行长任务；routine 不是命令，也不保证居民一定按表行动。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Routine Window | 一周日型中的 GameTime 区间及候选活动标签 |
| Interrupt Signal | 已提交危险、critical Need、健康、玩家交互或工作状态变化 |
| Interrupt Class | `emergency/high/normal/low` |
| Long Action Participation | TIME-owned 排他任务的 Resident 侧引用 |
| Abandon Condition | AI/TIME 可验证的退出条件 ID |

## 4. 数据与接口

`DES-RESIDENT-009`：

```json
{
  "routine_schema_version": 1,
  "schedule_profile_id": "schedule.apothecary.standard",
  "windows": [
    {
      "window_id":"routine.apothecary.workday.open_shop",
      "day_type":"workday",
      "start_minute_of_day":480,
      "end_minute_of_day":1020,
      "candidate_activity_tags":["activity.work","activity.trade_service"],
      "preferred_destination_ids":["semantic_node.apothecary.counter"],
      "flexibility_game_minutes":60,
      "interruptibility":"normal"
    }
  ],
  "active_long_action_id": null,
  "routine_revision": 4
}
```

Resident 发布 `RoutineConstraintsProjection`；TIME 根据它调度检查，AI 从 owner 提供的合法候选中选择。

## 5. 规则与不变量

- `RULE-RESIDENT-047`：Routine window 使用 `0..1439` 分钟、`start < end`，同 profile 不得无优先规则地重叠。
- `RULE-RESIDENT-048`：routine 只提供候选 activity/destination；不得直接生成 move/work/rest 等 Action。
- `RULE-RESIDENT-049`：中断优先级固定为 emergency > high > normal > low；Health unconscious 和即时安全威胁为 emergency。
- `RULE-RESIDENT-050`：同一居民同一 GameTime 最多引用一项排他 long action；其 reservation、进度、deadline 与 completion 由 TIME owner。
- `RULE-RESIDENT-051`：长行动中断必须由 TIME owner 记录 `paused/cancelled/completed`，Resident 不能仅清空引用。
- `RULE-RESIDENT-052`：routine/中断/长行动的所有时间以 GameTime 表达；暂停、关闭或 Encounter 期间不得用 RealTime 推进。

## 6. 正常流程

1. TIME 到达 routine check point，读取固定 Revision 的约束投影。
2. Orchestrator 汇总 Need、Health、assignment、MAP 可达性和已提交 interrupt。
3. AI owner决定 Hourly Intent/Immediate Action；失败时 Utility AI 只从安全候选中选择。
4. 长行动由 TIME 获取 Reservation 并返回 runtime ID，Resident 保存参与引用。
5. 中断发生时 TIME 依据优先级暂停/取消任务，再由 AI 重新规划。

## 7. 边界情况

- 跨午夜活动拆为两个 window，避免 `start > end` 歧义。
- 工作地不可达时 routine 不强迫移动，返回 `destination_unreachable` 供重规划。
- 玩家发起普通对话不能中断 emergency 行动；居民可拒绝。
- 重连后从 TIME-owned long action 状态恢复，不重复开始或完成。

## 8. 错误与降级

未知 activity、重叠窗口、过期 long action 引用返回 `RESIDENT_ROUTINE_INVALID`。AI 离线时 Utility AI 依 priority 选择 `seek_safety/rest/eat/wait` 等已注册候选，不编造日程或穿墙路径。

## 9. 安全与性能

Scheduler 按下个 boundary 事件驱动，不逐 Tick 扫描全部 window。投影最多每居民 32 个 window；私人住所目的地只向有权限 actor/自身上下文披露。

## 10. 验收标准

- routine 不直接执行 Action，AI/Utility AI 离线边界清晰。
- critical danger 可安全中断排他长任务且无双 Reservation。
- pause/reload 不推进窗口或重复完成。
- 不可达目的地会重规划而非传送。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-033` | window 边界、重叠与跨午夜拆分 |
| `TEST-RESIDENT-034` | interrupt priority Table Test |
| `TEST-RESIDENT-035` | long action 中断/重连/幂等集成 |
| `TEST-RESIDENT-036` | AI 离线只选择注册安全候选 |

## 12. 关联文档

- `DOC-RESIDENT-004`：Need/Emotion 信号
- `DOC-RESIDENT-006`：assignment 目的地
- `DOC-TIME-004..007`：调度与长行动 canonical owner
- `DOC-AI-006`：三层规划 canonical owner


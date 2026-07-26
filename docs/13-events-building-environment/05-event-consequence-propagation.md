---
doc_id: DOC-EVENT-005
title: 事件后果传播与善后
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - consequence-propagation-ports
  - aftermath-task-model
  - consequence-idempotency
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-EVENT-001
  - DOC-EVENT-004
  - DOC-MAP-010
requirements:
  - REQ-EVENT-005
last_updated: 2026-07-26
---

# 事件后果传播与善后

## 1. 目的

`REQ-EVENT-005`：定义 WorldEvent 对经济、记忆/谣言、导航、居民与 Quest 的后果只能经已提交 DomainEvent 与 owner 端口传播的契约，以及 Aftermath 阶段的伤员处理、营救、赔偿与重建任务模型和逐项幂等。

## 2. 非目标

本文不定义各 owner 域内的具体计算：价格修饰的数值公式（ECON）、记忆重要性评分（MEMORY）、昏迷/重伤流程细节（`DOC-RESIDENT-008`）、NavigationPatch 校验（`DOC-MAP-010`）。本文只定义 EVENT 一侧的传播端口、任务结构与幂等键。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Consequence | WorldEvent 模板中声明的一条结构化影响：目标域、端口、参数与触发阶段 |
| Consequence Port | owner 域暴露、EVENT 调用的 Command/Event 接口 |
| Aftermath Task | 终态后登记的善后项：`casualty_care/rescue/compensation/reconstruction/cleanup/commemoration` |
| Region Modifier | 以稳定 ID 引用、由 owner 解释的区域性修饰声明（价格、产出、危险度） |
| Consequence Key | `(world_event_id, consequence_id)` 幂等键 |

## 4. 规则与不变量

- `RULE-EVENT-025`：一切后果只能由已提交 DomainEvent 触发并经 Consequence Port 执行；WorldEvent 处于 `active` 本身不隐式修改任何他域状态，owner 域也不得轮询 WorldEvent 字段推导副作用（`RULE-EVENT-006` 细化）。
- `RULE-EVENT-026`：Aftermath 阶段必须结构化：致命结果一律转换为昏迷、重伤、被俘或撤退（`RULE-FOUNDATION-025`）并登记 `casualty_care`；受困/被俘者登记 `rescue` 并可实例化 `quest.rescue.*`（`DOC-EVENT-004`）；财产损失登记 `compensation` 走 ECON Appropriation 程序；损毁建筑登记 `reconstruction` 指向 `DOC-EVENT-010`。
- `RULE-EVENT-027`：经济后果只以 Region Modifier 稳定 ID 声明（如 `econ_modifier.timber_shortage`），由 ECON 在其定价/供需模型内解释；EVENT 不直接写价格、余额或库存（`RULE-FOUNDATION-018/019`）。
- `RULE-EVENT-028`：认知后果按事件公开程度分发：`public` 事件进入公共可感知事实；非公开范围只对在场/相关者生成可感知事实，谣言经 `BeliefTransfer` 带来源链传播；后果分发不得把未授权 Secret 注入任何居民上下文（`RULE-FOUNDATION-020/024`）。
- `RULE-EVENT-029`：涉及道路、建筑或环境封锁的后果必须经 `DOC-MAP-010` NavigationPatch 原子提交（`RULE-MAP-037..040`），并按 `DOC-EVENT-011` 追加 WorldDiff；不存在绕过导航校验的地图后果。
- `RULE-EVENT-030`：每条后果以 Consequence Key 幂等：重放、重试与恢复重演最多生效一次；跨域后果失败不回滚已提交的事件终态，失败项保留为待处理 Aftermath Task 直至显式完成或取消。

## 5. 数据与接口

`DES-EVENT-005`：模板内的 Consequence 声明与 Aftermath Task：

```json
{
  "schema_version": 1,
  "consequences": [
    {
      "consequence_id": "cq.close_forest_road",
      "phase": "on_active",
      "target_domain": "map",
      "port": "commit_navigation_patch",
      "parameters": {"patch_template_id": "navpatch.forest_road_blocked"}
    },
    {
      "consequence_id": "cq.timber_shortage",
      "phase": "on_active",
      "target_domain": "economy",
      "port": "apply_region_modifier",
      "parameters": {"modifier_id": "econ_modifier.timber_shortage", "scene_id": "region.whisper_forest", "duration_game_minutes": 4320}
    },
    {
      "consequence_id": "cq.reopen_forest_road",
      "phase": "on_aftermath",
      "target_domain": "map",
      "port": "commit_navigation_patch",
      "parameters": {"patch_template_id": "navpatch.forest_road_reopened"}
    }
  ]
}
```

```json
{
  "schema_version": 1,
  "aftermath_task_id": "01K1AB2CD3EF4GH5JK6MNP7QS4",
  "world_event_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "task_kind": "compensation",
  "subject_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QS5",
  "parameters": {"appropriation_purpose_id": "public_work.fire_compensation", "assessed_copper_feather": 3500},
  "state": "pending",
  "version": 1
}
```

Aftermath Task 状态只允许 `pending/in_progress/completed/cancelled`。接口：

```text
dispatch_consequences(world_event_id, phase, revision) -> [ConsequenceOutcome]
complete_aftermath_task(command_id, aftermath_task_id, expected_version, evidence) -> TaskResult
list_pending_aftermath(world_id) -> RevisionStampedProjection
```

## 6. 正常流程

1. Lifecycle Transition 提交后，引擎按 `phase`（`on_scheduled/on_active/on_escalated/on_terminal/on_aftermath`）分发对应 Consequence。
2. 每条后果检查 Consequence Key 未消费，调用 owner Port 并记录 outcome。
3. 终态转换时按 `RULE-EVENT-026` 生成 Aftermath Task 集。
4. 善后任务由镇长命令、居民行动或生成的 Quest 逐项完成。
5. 全部任务离开 `pending` 后事件可 `aftermath → archived`。

## 7. 边界情况

- 后果目标实体在分发时已不存在（居民已撤离、建筑已拆除）：该条后果记为 `completed_noop`，不阻塞其余后果。
- `on_aftermath` 的反向地图后果（重开道路）必须引用正向 WorldDiff entry 追加逆向变更（`DOC-EVENT-011`），不得直接删除封锁历史。
- 赔偿 Appropriation 未获批准：`compensation` 任务保持 `pending`，事件停留在 `aftermath` 不得 archived；由镇长显式将该任务转为 `cancelled` 才能放行归档。
- 同一居民同时是两起事件的 casualty：两个 `casualty_care` 任务并存，医疗处置由 RESIDENT/COMBAT 域按其排他规则调度（`RULE-FOUNDATION-028`）。
- 崩溃发生在部分后果分发后：恢复依据 Consequence Key 已消费记录续发未消费项，不重复已生效项。

## 8. 错误与降级

Port 调用返回 `owner_unavailable`、`port_rejected`、`consequence_replayed` 或 `parameters_invalid`。`owner_unavailable` 为 transient：按有界退避重试并保持任务 `pending`；`port_rejected` 为 terminal：记录原因码并要求人工/镇长处置，不静默丢弃。谣言分发失败只影响认知层，不重试超过一次。

## 9. 安全与性能

Consequence 声明的 `target_domain/port` 组合在构建期对照 `DOC-FOUNDATION-003` 依赖方向校验，禁止出现反向依赖端口。单事件后果上限 32 条；分发批量执行且每条独立事务，避免一条失败拖垮整批。公开事件摘要可进入 UI 与日志，涉及私人受害者的细节按访问级别过滤。

## 10. 验收标准

- 任一后果均可从触发它的 DomainEvent 追溯（causation 链完整）。
- 森林火灾 fixture：封路、木材短缺修饰、伤员、营救 Quest、赔偿与重开道路全链路可重放。
- 重复分发注入证明 Consequence Key 幂等。
- 事件在存在 `pending` 任务时无法 archived。
- 地图类后果全部经 NavigationPatch，负面注入（直接写 Collision）被架构测试拒绝。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-013` | `RULE-EVENT-025..026` 端口传播与 Aftermath 结构化 |
| `TEST-EVENT-014` | `RULE-EVENT-027..028` Region Modifier 与认知/Secret 边界 |
| `TEST-EVENT-015` | `RULE-EVENT-029..030` 导航后果合规与 Consequence 幂等 |

## 12. 关联文档

- `DOC-EVENT-001`：生命周期阶段与 Aftermath 状态
- `DOC-EVENT-004`：营救/重建 Quest 实例化
- `DOC-EVENT-010`：损毁与修复流程
- `DOC-EVENT-011`：WorldDiff 逆向变更
- `DOC-ECON-011`：赔偿 Appropriation 与公共预算
- `DOC-RESIDENT-008`：非永久死亡与 casualty 处置

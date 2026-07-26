---
doc_id: DOC-MAP-008
title: 门、入口与独立室内
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - door-navigation-contract
  - entrance-approach-arrival
  - interior-transfer
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-002
  - DOC-MAP-005
  - DOC-MAP-006
  - DOC-MAP-007
requirements:
  - REQ-MAP-008
last_updated: 2026-07-26
---

# 门、入口与独立室内

## 1. 目的

`REQ-MAP-008`：定义 Door、Entrance、approach/queue/arrival 点、Reservation 和室内 transfer 的原子契约，使多人形 actor 不重叠、不穿门、不跨 Scene 插值。

## 2. 非目标

本文不拥有建筑归属、钥匙物品、犯罪判定或门的视觉动画；这些 owner 提供已验证的 permission/state，MAP 只执行空间与占位规则。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Approach Point | actor 发起开门/进入命令前必须到达的站立点 |
| Queue Point | Door capacity 满时的有序等待点 |
| Arrival Point | transfer 成功后在目标 Scene 的权威位置 |
| Door Clearance | 从 approach 到门阈值的 Swept Disc 通道 |
| Door Reservation | 对 Door passage capacity 的临时排他 Reservation |
| Interior Transfer | 一次事务内从 Exterior/Interior Scene 切换到 pair Scene |

## 4. 规则与不变量

- `RULE-MAP-029`：Entrance 必须拥有唯一 pair、source approach、target arrival、interaction radius 和 facing；所有点在各自 Scene 合法。
- `RULE-MAP-030`：Door state 仅允许 `open/closed/locked/blocked/destroyed`；`closed/locked/blocked` 的 Collision 必须与状态同 Revision 更新，不能只播放动画。
- `RULE-MAP-031`：Door passage capacity 默认 1；同一 actor 同时最多拥有一个 Door Reservation，同一 Door 不得超过 capacity。
- `RULE-MAP-032`：Interior Transfer 原子验证 approach 距离、permission、Door state、Reservation、目标 MapSnapshot 与 arrival 合法性；任一失败保持 source Scene/position 不变。

## 5. 数据与接口

`DES-MAP-008`：

```json
{
  "entrance_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "entrance_template_id": "semantic_entrance.building.front",
  "pair_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "source_scene_id": "region.crown_creek_town",
  "target_scene_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "approach": {"x_wu": 1200, "y_wu": 1600, "facing_degrees": 270},
  "queue_points": [
    {"x_wu": 1200, "y_wu": 1632},
    {"x_wu": 1200, "y_wu": 1664}
  ],
  "arrival": {"x_wu": 512, "y_wu": 704, "facing_degrees": 270},
  "interaction_radius_wu": 24,
  "door_id": "01K1AB2CD3EF4GH5JK6MNP7QRY",
  "door_template_id": "door.building.front",
  "capacity": 1
}
```

Reservation：

```text
{reservation_id, door_id, actor_id, requested_game_time,
 request_revision, expires_at_game_time, state}
```

`expires_at_game_time = requested_game_time + 1`；排序使用 `requested_game_time`、`request_revision`、`reservation_id`。状态为 `active/consumed/released/expired`。

接口：

```text
reserve_door(actor_id, door_id, expected_revision) -> DoorReservationResult
request_interior_transfer(actor_id, entrance_id, reservation_id, expected_revision) -> TransferResult
release_door(reservation_id, reason) -> ReleaseResult
```

## 6. 正常流程

1. actor Pathfind 到 approach；capacity 已满时 Pathfind 到首个可用 queue point。
2. Authority Server 按稳定顺序授予 Reservation。
3. 若 Door 为 `closed`，actor 先提交注册的 open action；MAP 在新 revision 看到 Collision 移除后继续。
4. transfer 命令在同一事务重新验证全部条件。
5. actor 的 `scene_id`、position、facing 与 transfer DomainEvent 原子提交。
6. Reservation 标为 `consumed`，客户端在已提交事件后切换 Scene 表现。

## 7. 边界情况

- `locked` 必须先由 owner 验证解锁/权限，MAP 不猜测钥匙。
- `destroyed` 是否可通行由已提交 geometry state 决定；状态名本身不自动删除 Collision。
- actor 在 interaction radius 内但 Swept Disc 到门阈值被挡时不能 transfer。
- arrival 被临时 actor 占用时保持 Reservation 并等待至到期；不把两个 actor 放在同一点。
- GameTime 暂停期间 Reservation 不自然到期；明确取消、断开恢复或 safe recovery 可释放。
- 刷新/重连根据 reservation_id 与 actor_id 恢复，不重复授予。

## 8. 错误与降级

返回 `too_far`、`door_closed`、`door_locked`、`door_blocked`、`reservation_conflict`、`target_scene_not_ready`、`arrival_occupied` 或 `stale_revision`。失败不移动 actor；超时/断连释放后，actor 重新排队。

## 9. 安全与性能

权限结果必须来自 Authority Server，不接受客户端传入的 `can_enter=true`。每 Door queue 上限 32；超过返回 `door_queue_full`。Interior MapSnapshot 可按 Entrance 预热，但规则加载失败不允许仅加载画面进入。

## 10. 验收标准

- 每个 Entrance 的 pair、approach、queue、arrival、facing 和 Door 均可解析。
- 两个 actor 同时请求 capacity=1 的 Door 时只授予一个，顺序确定。
- closed/locked/blocked、arrival occupied、刷新与过期流程无位置重复或穿门。
- transfer 前后不存在中间持久状态，失败保持 source position。
- 玩家与 NPC 遵守相同 approach、permission、Reservation 和 transfer 条件。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MAP-029` | Entrance pair 与 approach/arrival 合法性 |
| `TEST-MAP-030` | Door state、Collision 与 Reservation 原子一致 |
| `TEST-MAP-031` | capacity、稳定排队、超时、重连和幂等 transfer |
| `TEST-MAP-032` | 室内进入/离开失败无副作用且玩家/NPC parity |

## 12. 关联文档

- `DOC-MAP-002`：Interior Scene 与 topology
- `DOC-MAP-006`：Door Collision
- `DOC-MAP-007`：approach/queue 寻路
- `DOC-MAP-009`：区域 Exit transfer
- `DOC-MAP-010`：Door geometry 原子更新

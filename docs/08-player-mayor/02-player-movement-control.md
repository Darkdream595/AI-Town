---
doc_id: DOC-PLAYER-002
title: 玩家移动、预测与权威校准
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-movement-intent
  - movement-authority-reconciliation
  - player-navigation-parity
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-005
  - DOC-MAP-006
  - DOC-MAP-007
  - DOC-MAP-008
  - DOC-MAP-009
  - DOC-RENDER-001
requirements:
  - REQ-PLAYER-002
last_updated: 2026-07-26
---

# 玩家移动、预测与权威校准

## 1. 目的

`REQ-PLAYER-002`：定义 WASD/Shift 移动从 Client intent 到后端权威路径、Collision 校验和客户端校准的完整闭环，确保玩家与 AI 居民使用同一 MAP 合法性。

## 2. 非目标

本文不拥有 Walkability、Collision、A*、Door、Scene transition、Animation State Machine 或网络 Envelope；分别由 MAP、RENDER 与 BACKEND 拥有。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Input Frame | Client 在一个采样窗口内压缩后的方向键状态 |
| Player Move Intent | 未被信任的方向、快走请求和序号 |
| Authoritative Move | 通过最新 Revision、体型、速度、Walkability、Collision 与 Occupancy 校验的位移 |
| Prediction | Client 为手感提前显示的可撤销视觉位置 |
| Reconciliation | 以已提交位置和确认序号纠正 Client 预测 |

## 4. 规则与不变量

- `RULE-PLAYER-006`：玩家和 AI 的移动最终都调用 MAP 的相同 `validate_navigation_intent`、体型 clearance、Door/permission、Occupancy 与 transition validator。
- `RULE-PLAYER-007`：Client 方向、坐标、速度、路径、碰撞结果与 `expected_revision` 均不可信；Client 不可提交 teleport 或可信终点。
- `RULE-PLAYER-008`：规则位置只由后端提交的量化 `WorldPoint` 表示；camera、fullscreen、DPR、zoom 和预测 Sprite 均不改变规则坐标。
- `RULE-PLAYER-009`：失焦、modal、模式切换、断线和 Scene 切换必须清空按键 latch；不得保持“幽灵移动”。
- `RULE-PLAYER-010`：预测误差只能由视觉校准消除，不能反向覆盖后端；失败移动不产生位置 DomainEvent。

## 5. 数据与接口

`DES-PLAYER-002`：

```json
{
  "schema_version": 1,
  "command_id": "01K1COMMAND000000000000002",
  "expected_revision": 44,
  "input_sequence": 731,
  "sample_duration_ms": 50,
  "direction": {
    "x": 1,
    "y": 0
  },
  "speed_mode": "walk",
  "client_observed_scene_id": "scene.crowncreek.town"
}
```

约束：`sample_duration_ms` 为 `1..100`；`direction.x/y` 各为 `-1/0/1` 且不能同时为 0；对角线先归一化，不能获得更高速度；`speed_mode` 仅 `walk/fast_walk`。接口：

```text
submit_player_move(binding_id, move_intent) -> CommandReceipt
validate_navigation_intent(actor_projection, movement_request, map_revision)
  -> ApprovedMovement | NavigationRejection
reconcile_player_position(confirmed_input_sequence, authoritative_position, revision)
  -> ClientCorrection
```

## 6. 正常流程

1. 仅在 `resident_active + world_input` context 采样 WASD；Shift 只请求 `fast_walk`。
2. Client 合并重复 keydown，按最多 20 Hz 发送 intent，可在本地沿最近权威向量预测。
3. Backend 从 authenticated binding 解析 actor，不接受 payload 内 actor ID。
4. Domain validator 检查健康/Encounter/长行动、Scene、Walkability、Collision、Occupancy、许可、速度和地图 Revision。
5. 成功时提交量化位置、耐力等 owner 结果与 DomainEvent；RENDER 接收 path segment/animation hint。
6. Client 丢弃 `input_sequence <= confirmed_input_sequence` 的预测输入，并在 100–180 ms 内平滑校准；穿墙风险或 Scene 变化时立即 snap。

## 7. 权威校准状态机

```text
synced -> predicting -> awaiting_ack -> synced
awaiting_ack -> correcting -> synced
any -> input_cleared : blur/modal/mode/disconnect
any -> snapshot_required : revision_gap/scene_mismatch
snapshot_required -> synced : valid snapshot installed
```

同一 `input_sequence` 重复到达只返回原 receipt；低于已确认序号的输入忽略；同序号不同 payload 返回 `PLAYER_INPUT_SEQUENCE_CONFLICT`。Revision gap 不猜测中间碰撞，必须请求 Snapshot。

## 8. 边界情况与失败恢复

- 对角线贴墙：MAP swept-volume/clearance 决定合法段，Client 不自行“滑墙”产生规则结果。
- 快走条件失效：validator 可批准 walk 速度并返回明确 downgrade reason，不能相信 Client 速度。
- Door 在请求途中锁定：以提交时最新状态拒绝或截断到最后合法点。
- 断线重连：清空 pending prediction，从 Snapshot authoritative position 恢复。
- 低 FPS 长 sample：单 intent 上限 100 ms，额外时间不能兑换位移。
- 浏览器自动重复按键：以 pressed-state 采样，不按 keydown 次数累积速度。

## 9. 安全与性能

每玩家移动 intent 限 25/s，超额合并为最新按键状态；拒绝 NaN、Infinity、浮点方向、未知字段和超大序号跳变。MAP 查询使用当前 Scene 索引，不扫描全世界。日志保留 reason code 和序号，不记录每帧 raw key event。

## 10. 验收标准

- 玩家与 NPC 对同一 fixture 的移动、Door、Interior 和 Region transition 判定完全一致。
- 房屋、树木、水域、悬崖、废墟和封锁区不可穿越。
- blur、Tab、modal、断线和 Scene change 后没有 stuck key。
- 乱序、重复、丢包与 Revision gap 最终收敛到权威位置。
- fullscreen/resize/zoom 不改变路径或 WorldPoint。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-005` | WASD/Shift、对角归一化和速率限制 |
| `TEST-PLAYER-006` | PlayerCommand/NPC ActionProposal MAP parity |
| `TEST-PLAYER-007` | collision、动态 Door 与 Scene transition |
| `TEST-PLAYER-008` | prediction、乱序、Snapshot 与 stuck-key recovery |

## 12. 关联文档

- `DOC-MAP-005..009`：站立、碰撞、寻路与转场权威规则
- `DOC-MAP-012`：玩家/NPC parity fixtures
- `DOC-RENDER-001`：Snapshot、camera 与 Revision 渲染契约
- `DOC-PLAYER-011`：输入上下文和按键重绑定


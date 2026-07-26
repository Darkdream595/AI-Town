---
doc_id: DOC-TIME-005
title: Active、Warm 与 Background 模拟层级
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - simulation-tier-semantics
  - simulation-tier-transition
  - tier-equivalence-policy
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-WORLD-004
  - DOC-MAP-007
  - DOC-MAP-009
  - DOC-TIME-003
  - DOC-RESIDENT-001
requirements:
  - REQ-TIME-005
last_updated: 2026-07-26
---

# Active、Warm 与 Background 模拟层级

## 1. 目的

`REQ-TIME-005`：定义三个模拟层级的空间精度、更新频率、允许简化、迁移屏障和结果等价边界，使未在画面中的居民仍遵守同一资源、权限、行动和后果规则。

## 2. 非目标

本文不定义 MAP path cost、Resident Needs 公式、经济产出或 Render Scene 加载。层级只改变执行粒度和调用频率，不改变各 owner 的业务真值。

## 3. 术语与定义

| 层级 | 定义 |
|---|---|
| `Active` | 玩家当前 Scene；使用完整 Walkability、Collision、Occupancy Overlay、逐路径段进度和即时事件 |
| `Warm` | 已加载但非玩家当前 Scene；使用 Semantic Node/Exit 路径、分钟级进度和确定性占位摘要 |
| `Background` | 未加载 Scene 或可摘要长任务；按开始、checkpoint、条件、结束模拟，不维护逐步位置 |
| Tier Barrier | tier 变更前冻结目标 actor 写入、结清到同一 Revision/GameTime 的协调点 |
| Semantic Progress | `{from_node_id,to_node_id,route_id,progress_basis_points}`，不是任意坐标 |
| Promotion Reconciliation | 从低精度状态恢复到 Active 前进行的路径、占位和规则合法性校验 |

## 4. 规则与不变量

- `RULE-TIME-025`：玩家所在 Scene 必须为 Active；其他已加载 Scene 默认 Warm，未加载 Scene 默认 Background。
- `RULE-TIME-026`：tier 不得改变货币、物品、健康、关系、法律、Reservation、deadline 或 Action 成败；业务结果由同一 owner Port 计算。
- `RULE-TIME-027`：Active 可提交连续路径进度；Warm 只提交已登记 Semantic route 的分钟级进度；Background 只提交可证明条件的 checkpoint/完成结果。
- `RULE-TIME-028`：任一 tier 的 actor 都必须有唯一 location representation；同一 Revision 不得同时具有 Active WorldPoint 与 Background task location。
- `RULE-TIME-029`：promotion 到 Active 前必须在最新 MapSnapshot 验证 standing point、Collision、occupancy 和 required route；失败进入 recovery，不得瞬移到最近像素。
- `RULE-TIME-030`：法律、危险、资源守恒与正式居民非永久死亡不允许以 performance tier 为理由降级或跳过。

## 5. 数据与接口

`DES-TIME-005`：

```json
{
  "schema_version": 1,
  "scene_id": "region.twilight_whisper_forest",
  "tier": "warm",
  "effective_at_revision": 1204,
  "effective_at_game_time": 1840,
  "reason": "player_left_scene",
  "actor_projection": {
    "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "representation": "semantic_progress",
    "route_id": "route.fixture.camp_to_south_path",
    "from_node_id": "semantic_anchor.twilight_whisper.oathkeeper_camp",
    "to_node_id": "semantic_exit.twilight_whisper_forest.south_path",
    "progress_basis_points": 3500
  }
}
```

接口：

```text
request_tier_transition(scene_id, target_tier, reason) -> TierTransitionPlan
enter_tier_barrier(scene_id, expected_revision) -> TierBarrier
reconcile_actor_for_promotion(resident_id, map_revision) -> ReconciliationResult
commit_tier_transition(plan, reconciliation_set) -> TierTransitionEvent
```

`progress_basis_points` 范围 `0..10000`；Background action 使用 `long_action_id` 与 `checkpoint_index`，不伪造 WorldPoint。

## 6. 正常流程

1. 玩家转场已提交后，TIME 计算旧/新 Scene tier proposal。
2. Orchestrator 进入 Tier Barrier，等待正在提交的 actor transaction 完成，不等待网络模型。
3. Active→Warm 把路径位置投影到已验证 semantic segment；Warm→Background 将可摘要行动变为 checkpoint。
4. Background/Warm→Active 在最新 MAP 状态做 reconciliation。
5. 同一事务提交 tier、actor representation 和 TierTransition Event。

## 7. 边界情况

- 玩家进入 Interior：Interior Scene 为 Active；父 Region 可保持 Warm 以继续天气/管辖投影，不生成第四 Region。
- actor 正在跨 Region transition：先完成或拒绝转场事务，再做 tier 变更，不能停在两个 Scene。
- Background 路线被灾害封锁：到下一个条件 checkpoint 时中断并重规划，不能按旧 ETA 穿越。
- promotion 目标站立点被占：只使用 MAP 登记 safe point/arrival fallback；无合法点则保持非 Active representation 并阻止 Scene 交互开始。
- Encounter participant 不由 Overworld tier 推进位置或长任务。

## 8. 错误与降级

projection 无法无损生成、map revision 不匹配或 recovery safe point 缺失时返回 `TIME_TIER_RECONCILIATION_REQUIRED`，保持原 tier 与位置。过载时可延迟非玩家 Scene promotion，但不能把玩家已进入 Scene 标为非 Active。

## 9. 安全与性能

Active 默认仅 1 个 Scene；Warm 默认最多 2 个 Scene，更多按最近访问顺序降到 Background。Tier projection 只保留业务所需 ID/进度，不复制 Secret。批量迁移按稳定 Resident ID 分片，每 Tick 受 budget 限制。

## 10. 验收标准

- 三个 tier 的位置表示互斥且可追踪到同一 actor。
- 相同 seed/input 下，tier 切换前后守恒量与业务结果一致。
- Active promotion 不产生 Collision、非法站立或未声明 fallback。
- 灾害、建筑 patch、Encounter 和 Region transition 并发均有确定结果。
- 30 游戏日 Background 模拟不出现免费资源、穿墙或永久删除居民。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-013` | `RULE-TIME-025..028` tier assignment 与 representation exclusivity |
| `TEST-TIME-014` | `RULE-TIME-029` promotion reconciliation |
| `TEST-TIME-015` | `RULE-TIME-026`, `RULE-TIME-030` tier equivalence 与 invariant |

## 12. 关联文档

- `DOC-WORLD-004`：Region/Interior 语义
- `DOC-MAP-009`：Region transition 原子位置
- `DOC-TIME-006`：Background 长任务
- `DOC-TIME-011`：Active/Warm 容量预算
- `DOC-RESIDENT-001`：Resident 位置引用消费者

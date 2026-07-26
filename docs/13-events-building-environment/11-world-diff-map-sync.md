---
doc_id: DOC-EVENT-011
title: WorldDiff 与地图原子同步
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - world-diff-log
  - reverse-diff-semantics
  - map-state-replay
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-004
  - DOC-MAP-010
  - DOC-EVENT-007
requirements:
  - REQ-EVENT-011
last_updated: 2026-07-26
---

# WorldDiff 与地图原子同步

## 1. 目的

`REQ-EVENT-011`：定义 append-only WorldDiff log 的 entry 结构、与业务状态/NavigationPatch/DomainEvent 的原子同步、逆向变更语义与基于重放的地图状态重建，使道路、建筑和环境的长期变化可审计、可恢复且永不改写历史。

## 2. 非目标

本文不定义 NavigationPatch 的几何校验（`DOC-MAP-010`）、Map Package 基线格式（`DOC-MAP-004`）、Event Log 存储引擎（RELEASE）或触发这些变化的业务规则（本域其余文档）。WorldDiff 不是渲染增量协议；前端同步走 Event Envelope 与 Snapshot（BACKEND）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| WorldDiff Log | 每 Scene 一条、按 Revision 追加的持久变更序列（`DOC-FOUNDATION-004` `WorldDiff`） |
| Diff Entry | 一次持久地图变更的完整记录：来源、操作集、revision、game_time |
| Diff Kind | `road/building/environment_blockade/semantic/terrain_object` 五类变更类别 |
| Reverse Entry | 撤销既有 entry 的新追加 entry，携带被撤销 entry 引用 |
| Map Replay | `base Map Package + 按 Revision 顺序应用 WorldDiff` 得到当前规则层状态 |
| Diff Hash | 对重放结果规则层的确定性 SHA-256，用于恢复审计 |

## 4. 规则与不变量

- `RULE-EVENT-061`：WorldDiff Log 只追加（`RULE-FOUNDATION-027` 细化）：entry 一经提交不得修改、删除或重排；每 entry 携带 `revision`（严格递增）、`game_time`、来源 `command_id/world_event_id` 与产生它的 DomainEvent 引用。
- `RULE-EVENT-062`：每次持久地图变更（建筑状态几何、道路修改、环境封锁、语义节点增删、地形对象变化）必须产生恰好一个 Diff Entry，且与业务状态、NavigationPatch（`RULE-MAP-037`）、DomainEvent 同一 World transaction；不经 NavigationPatch 的 Diff Entry 与不产生 Diff Entry 的持久地图变更均为架构违规。
- `RULE-EVENT-063`：恢复与撤销以 Reverse Entry 表达：新 entry 的 `reverses_entry_id` 指向被撤销 entry，操作集为其确定性逆运算（`add↔remove`、`replace` 携带前值）；被撤销 entry 保留在 log 中，链条可多级（撤销之撤销）。
- `RULE-EVENT-064`：Map Replay 是规则层状态的唯一重建方式：`base Map Package(version) + WorldDiff[0..revision]` 的重放结果必须与该 Revision 的 MapSnapshot 一致（Diff Hash 相等）；不一致时保持 Recovery Barrier，禁止以任一方"修正"另一方。
- `RULE-EVENT-065`：Diff Entry 操作集与 NavigationPatch 同构：只含 `structure/walkability/collision/semantic` 规则层的 `add/replace/remove`，不含 Ground Art 像素、渲染参数或实体位置；`replace/remove` 必须内嵌被替换对象的完整前值以保证可逆。
- `RULE-EVENT-066`：Diff 应用是确定性且幂等的 set 运算：同一 entry 在重放中恰好应用一次，重复投递以 `(scene_id, revision)` 去重；entry 之间只按 Revision 全序应用，无并行合并。

## 5. 数据与接口

`DES-EVENT-011`：Diff Entry：

```json
{
  "schema_version": 1,
  "diff_entry_id": "01K1AB2CD3EF4GH5JK6MNP7QSH",
  "scene_id": "region.crown_creek_town",
  "revision": 5121,
  "game_time": 25200,
  "diff_kind": "building",
  "source": {
    "command_id": "01K1AB2CD3EF4GH5JK6MNP7QSC",
    "world_event_id": null,
    "domain_event_id": "01K1AB2CD3EF4GH5JK6MNP7QSJ"
  },
  "subject_id": "01K1AB2CD3EF4GH5JK6MNP7QS6",
  "reverses_entry_id": null,
  "operations": [
    {
      "op": "add",
      "layer": "collision",
      "object_id": "01K1AB2CD3EF4GH5JK6MNP7QS8",
      "object_template_id": "collision.building.foundation",
      "value": {
        "shape_type": "polygon",
        "outer_ring_wu": [[800, 800], [960, 800], [960, 928], [800, 928]],
        "obstacle_tag": "building.foundation"
      }
    }
  ]
}
```

Reverse Entry 示例（重开被洪水封锁的道路）：

```json
{
  "schema_version": 1,
  "diff_entry_id": "01K1AB2CD3EF4GH5JK6MNP7QSK",
  "scene_id": "region.twilight_whisper_forest",
  "revision": 5388,
  "game_time": 28800,
  "diff_kind": "environment_blockade",
  "source": {
    "command_id": null,
    "world_event_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "domain_event_id": "01K1AB2CD3EF4GH5JK6MNP7QS8"
  },
  "subject_id": "01K1AB2CD3EF4GH5JK6MNP7QSM",
  "reverses_entry_id": "01K1AB2CD3EF4GH5JK6MNP7QSN",
  "operations": [
    {"op": "remove", "layer": "collision", "object_id": "01K1AB2CD3EF4GH5JK6MNP7QSM", "object_template_id": "collision.hazard.flood", "value": {"shape_type": "polygon", "outer_ring_wu": [[1200, 640], [1400, 640], [1400, 760], [1200, 760]], "obstacle_tag": "hazard.flood"}}
  ]
}
```

接口：

```text
append_world_diff(transaction_context, entry) -> DiffAppendResult
replay_world_diff(scene_id, base_package_version, up_to_revision) -> ReplayedRuleLayers
compute_diff_hash(replayed_layers) -> sha256
audit_map_consistency(scene_id, revision) -> ConsistencyReport
```

`append_world_diff` 只能在提交 NavigationPatch 的同一事务上下文中调用；不存在独立的 WorldDiff 写入口。

## 6. 正常流程

1. 业务命令（放置、阶段完成、损毁、封路、重开）经 owner 校验与 MAP Candidate 审计。
2. 提交事务内依次写：业务状态、NavigationPatch、DomainEvent、Diff Entry。
3. 提交后按 Revision 发布 NavigationChanged 与事件，前端按协议同步。
4. Snapshot 生成时记录 Scene 当前 Diff Hash。
5. 恢复时 Map Replay 重建规则层并与 Snapshot Hash 比对，一致才解除屏障。

## 7. 边界情况

- 撤销的对象在其后已被其他 entry 修改：Reverse Entry 构造时以当前值校验 `replace` 前值，不匹配则拒绝撤销命令，要求走新的正向变更表达目标状态。
- base Map Package 升版（内容更新）：新版本重新锚定 Diff Log 起点，旧世界继续用旧 base + 全量 log；不做跨 base 版本的 entry 迁移改写。
- 高频门开关不产生 Diff Entry：Door state 属于 MAP 运行状态（`DOC-MAP-008`），只有持久结构变化才进入 WorldDiff。
- 单事务多层操作（建筑降级同时改 Collision 与 Semantic）：同一 entry 的 operations 数组承载，不拆多 entry。
- 极长时间线的重放成本：允许以"经审计的中间 MapSnapshot"作为重放起点，但 log 本身永不截断（截断属 RELEASE 归档策略且必须保持可审计导出）。

## 8. 错误与降级

返回 `diff_outside_transaction`、`revision_not_monotonic`、`reverse_precondition_failed`、`operation_layer_invalid`、`replay_hash_mismatch` 或 `entry_replayed`。`replay_hash_mismatch` 触发 Recovery Barrier 并生成含首个分歧 entry 的诊断报告；在线运行期不做任何自动回滚或补写。

## 9. 安全与性能

Diff Entry 上限沿用 patch 预算（单 entry ≤ 256 operations）；log 按 `(scene_id, revision)` 唯一索引。entry 不含居民隐私与 Secret；`admin` 来源变更经 `RULE-FOUNDATION-030` 标记。重放为纯函数，可在后台线程执行；Diff Hash 计算对规则层对象按 `object_id` 排序后序列化，与插入顺序无关。

## 10. 验收标准

- 任意 fixture 时间线：重放结果 Hash 与各 Revision Snapshot 一致。
- 每个持久地图变更恰有一个 entry，负面注入（旁路写层、独立写 diff）被架构测试拒绝。
- 正向-逆向-再逆向三级链可重放且历史完整。
- `replace` 前值不匹配的撤销被拒绝。
- 30 游戏日模拟后 log 与地图状态审计零分歧。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-031` | `RULE-EVENT-061..062` append-only、单事务四件套与 entry 唯一性 |
| `TEST-EVENT-032` | `RULE-EVENT-063` 逆向链语义与前值校验 |
| `TEST-EVENT-033` | `RULE-EVENT-064..066` 重放一致性、Hash 审计与幂等应用 |

## 12. 关联文档

- `DOC-MAP-004`：base Map Package 与规则层
- `DOC-MAP-010`：NavigationPatch 同事务契约
- `DOC-EVENT-005`：事件后果的正向/逆向地图变更
- `DOC-EVENT-012`：恢复与重放场景测试
- `DOC-FOUNDATION-005`：`RULE-FOUNDATION-027` 追加式历史

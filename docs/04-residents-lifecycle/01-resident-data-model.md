---
doc_id: DOC-RESIDENT-001
title: 居民聚合与数据模型
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-aggregate
  - resident-state-version
  - resident-reference-boundaries
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-MAP-005
requirements:
  - REQ-RESIDENT-001
last_updated: 2026-07-26
---

# 居民聚合与数据模型

## 1. 目的

`REQ-RESIDENT-001`：定义正式居民的唯一聚合根、版本、持久字段、跨域引用和更新入口，使身份、生命周期与持久健康在同一 Revision 下保持一致。

## 2. 非目标

本文件不拥有 Item/Inventory 内容、伤害公式、GameTime 调度、ActionProposal、关系或记忆；这些只保存 owner 发布的 stable/runtime ID 引用。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `Resident` | 以 `resident_id` 为聚合根的正式居民 |
| `resident_key` | 跨世界内容稳定的 Catalog ID，如 `resident.apothecary.elise` |
| `resident_id` | 当前 world 内的 ULID 实例 ID |
| `aggregate_schema_version` | `ResidentAggregateV1` 的持久 Schema 版本，不等于 World Revision |
| `resident_revision` | 最近一次成功修改该 Resident 的 World Revision |
| `ResidentSummaryProjection` | 从完整聚合派生的非持久只读摘要；不能用于 save/reload |
| 外部引用 | owner domain 的 ID；Resident 不复制其可变权威状态 |

## 4. 数据与接口

`DES-RESIDENT-001`：注册 `schema.resident.aggregate.v1`；`ResidentAggregateV1` 是唯一 authoritative stored/wire Schema。`required` 顶层字段恰好为
`aggregate_schema_version/resident_id/resident_key/world_id/resident_revision/identity/personality/needs_state/capability_state/assignment_state/health_state/lifecycle/routine_state/inventory_id/created_at_game_time/updated_at_game_time`。
各内嵌对象必须逐字满足对应 canonical 子 Schema，不允许以 ID 数组或摘要字段替代：

| Aggregate key | Schema ID | Canonical 文档 |
|---|---|---|
| `identity` | `schema.resident.identity.v1` | `DOC-RESIDENT-002` |
| `personality` | `schema.resident.personality.v1` | `DOC-RESIDENT-003` |
| `needs_state` | `schema.resident.needs_state.v1` | `DOC-RESIDENT-004` |
| `capability_state` | `schema.resident.capability_state.v1` | `DOC-RESIDENT-005` |
| `assignment_state` | `schema.resident.assignment_state.v1` | `DOC-RESIDENT-006` |
| `health_state` | `schema.resident.health_state.v1` | `DOC-RESIDENT-007` |
| `lifecycle` | `schema.resident.lifecycle.v1` | `DOC-RESIDENT-008` |
| `routine_state` | `schema.resident.routine_state.v1` | `DOC-RESIDENT-009` |

```json
{
  "aggregate_schema_version": 1,
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "resident_key": "resident.apothecary.elise",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "resident_revision": 42,
  "identity": {
    "identity_schema_version": 1,
    "display_name": "艾莉丝",
    "self_name": "艾莉丝",
    "pronoun_id": "pronoun.she",
    "ancestry_id": "ancestry.human",
    "culture_ids": ["culture.crown_creek_local"],
    "language_proficiencies": [{"language_id":"language.crown_common","level":100}],
    "appearance": {
      "profile_id":"appearance.resident.apothecary.elise",
      "sprite_asset_id":"sprite.resident.apothecary",
      "portrait_asset_id":"portrait.resident.apothecary",
      "combat_sprite_asset_id":"combat_sprite.resident.apothecary",
      "palette_variant_id":"palette.apothecary.blue_amber",
      "presentation_tags":["hair.braided"]
    }
  },
  "personality": {
    "schema_version":1,
    "dimensions":{"sociability":62,"diligence":80,"curiosity":55,"empathy":71,"caution":68,"assertiveness":44},
    "values":[{"value_id":"value.community","weight_q1000":850}],
    "preferences":[{"preference_id":"preference.activity.herbalism","weight_q1000":500}],
    "fears":[],
    "profile_revision":3
  },
  "needs_state": {
    "needs_schema_version":1,
    "values":{
      "hunger":{"value_q1000":420,"last_updated_game_time":1830},
      "fatigue":{"value_q1000":610,"last_updated_game_time":1830},
      "safety":{"value_q1000":90,"last_updated_game_time":1830},
      "social":{"value_q1000":330,"last_updated_game_time":1830},
      "comfort":{"value_q1000":250,"last_updated_game_time":1830}
    },
    "emotion":{"primary":"calm","intensity_q1000":180,"cause_event_ids":[],"updated_at_game_time":1830,"decay_rate_q1000_per_game_hour":80}
  },
  "capability_state": {
    "capability_schema_version":1,
    "skills":{"skill.herbalism":{"rating":64,"xp":320,"last_practiced_game_time":1810}},
    "ability_ids":["ability.herbalism.identify_common"],
    "capability_revision":8
  },
  "assignment_state": {
    "assignment_schema_version":1,
    "profession":{"assignment_id":"01K1AB2CD3EF4GH5JK6MNP7QRV","profession_id":"profession.apothecary","workplace_id":"building.apothecary","state":"active","effective_from_game_time":480,"effective_until_game_time":null},
    "residence":{"assignment_id":"01K1AB2CD3EF4GH5JK6MNP7QRW","building_id":"building.riverside_house_02","interior_scene_id":"interior.riverside_house_02","bed_node_id":"semantic_node.riverside_house_02.bed_a","state":"active"}
  },
  "health_state": {
    "health_schema_version":1,
    "condition":"healthy",
    "hp_current":30,
    "hp_max":30,
    "injuries":[],
    "illnesses":[],
    "restrictions":[],
    "health_revision":11
  },
  "lifecycle": {
    "lifecycle_schema_version":1,
    "age_stage":"adult",
    "age_stage_since_game_time":0,
    "lifecycle_state":"active",
    "defeat":null
  },
  "routine_state": {
    "routine_schema_version":1,
    "schedule_profile_id":"schedule.apothecary.standard",
    "windows":[{
      "window_id":"routine.apothecary.workday.open_shop",
      "day_type":"workday",
      "start_minute_of_day":480,
      "end_minute_of_day":1020,
      "candidate_activity_tags":["activity.work","activity.trade_service"],
      "preferred_destination_ids":["semantic_node.apothecary.counter"],
      "flexibility_game_minutes":60,
      "interruptibility":"normal"
    }],
    "active_long_action_id":null,
    "routine_revision":4
  },
  "inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "created_at_game_time": 0,
  "updated_at_game_time": 1830
}
```

`ResidentSummaryProjectionV1` 仅允许
`schema_version/resident_id/resident_key/resident_revision/display_name/appearance_profile_id/lifecycle_state/health_condition`；
它由 `ResidentAggregateV1` 派生、不可写回、不可作为 Snapshot 或 upcaster 输入。

写 Port：

```text
create_resident(CreateResidentCommand) -> ResidentResult
apply_health_effect(HealthEffectCommand) -> ResidentResult
change_assignment(ChangeResidentAssignmentCommand) -> ResidentResult
update_needs(NeedsUpdateCommand) -> ResidentResult
set_lifecycle_state(LifecycleTransitionCommand) -> ResidentResult
```

读 Port `get_resident_aggregate` 返回 immutable `ResidentAggregateV1`；
`get_resident_summary` 返回 `ResidentSummaryProjectionV1`。二者必须携带 `resident_revision`，但只有前者参与持久化 round-trip。

## 5. 规则与不变量

- `RULE-RESIDENT-001`：`resident_id`、`resident_key` 和 `world_id` 创建后不可变；同一 world 内二者各自唯一。
- `RULE-RESIDENT-002`：正式居民不得物理删除；离开常规可行动状态只能使用 DOC-RESIDENT-008 封闭 lifecycle state 与事件表达。
- `RULE-RESIDENT-003`：每次写命令必须携带 `command_id`、`expected_revision`、`schema_version`，相同 `(world_id, command_id)` 最多生效一次。
- `RULE-RESIDENT-004`：`inventory_id` 仅引用 ECON-owned Inventory；Resident 不缓存物品数量、余额、重量或所有者。
- `RULE-RESIDENT-005`：`assignment_state` 内的 profession/residence ID 与 `routine_state.schedule_profile_id` 是已验证引用；引用失效不得静默创建替代对象。
- `RULE-RESIDENT-006`：任何成功变更与对应 `ResidentCreated`、`ResidentStateChanged` 或专用 DomainEvent 原子提交，失败不增长 Revision。
- `RULE-RESIDENT-072`：`ResidentAggregateV1` 的所有 canonical 子对象均 required，子对象版本必须等于其注册 Schema 版本；摘要 projection 不能反序列化为 aggregate。

## 6. 正常流程

1. 初始化器验证 Catalog、World、Scene 与外部引用。
2. `create_resident` 建立 Resident aggregate；ECON Inventory 和其他 owner 资源由 Orchestrator 在同一 Unit of Work 建立。
3. Resident 检查内部不变量并生成事件。
4. Orchestrator 运行 MAP 站立合法性及跨域引用检查。
5. 状态、事件和幂等结果提交后，读模型与渲染 projection 才更新。

## 7. 边界情况

- 重放相同创建命令返回原 `resident_id` 与结果事件，不创建第二居民。
- 外部 owner 暂不可用时创建整体回滚，不留下半初始化 Resident。
- 旧 Schema 缺失可推导字段时由版本化 upcaster 补齐；不可推导时保持 Recovery Barrier。
- 玩家采用正式居民生命周期时使用同一 aggregate，决策来源不进入 Resident Schema。

## 8. 错误与降级

稳定错误码包括 `RESIDENT_DUPLICATE_KEY`、`RESIDENT_STALE_REVISION`、`RESIDENT_SCHEMA_UNSUPPORTED`、`RESIDENT_REFERENCE_MISSING`、`RESIDENT_INVARIANT_VIOLATION`。错误无部分副作用；恢复期发现孤立引用时保持暂停并输出脱敏 ID。

## 9. 安全与性能

写入只接受 Authority Server 内部 Command，不信任 Client/模型提供的 actor 或属性。Snapshot 不包含 Secret、Memory 文本或模型推理。单 Resident 聚合序列化上限 64 KiB；高基数 Item/Memory 永不内嵌。

## 10. 验收标准

- `ResidentAggregateV1` 逐子 Schema 校验、canonical JSON round-trip 和 save/reload 后逐字相等。
- 删除任一 required 子对象、替换为旧简写字段或把 Summary 当 Aggregate 均被 validator 拒绝。
- 重复命令不重复创建或变更。
- 外部引用失败时 Unit of Work 全回滚。
- 正式 Resident 无 delete/death terminal API。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-001` | 完整 Aggregate 逐子 Schema validator、canonical JSON round-trip 与旧简写反例 |
| `TEST-RESIDENT-002` | 创建/更新/重放的幂等与 Revision Contract Test |
| `TEST-RESIDENT-003` | 外部引用失败注入时无半状态 |
| `TEST-RESIDENT-004` | Repository API 不暴露正式居民物理删除 |

## 12. 关联文档

- `DOC-FOUNDATION-003`：canonical ownership
- `DOC-RESIDENT-010`：Inventory 引用边界
- `DOC-RESIDENT-012`：聚合验收场景

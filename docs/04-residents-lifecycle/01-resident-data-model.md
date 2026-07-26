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
| `state_version` | Resident Schema 版本，不等于 World Revision |
| `resident_revision` | 最近一次成功修改该 Resident 的 World Revision |
| 外部引用 | owner domain 的 ID；Resident 不复制其可变权威状态 |

## 4. 数据与接口

`DES-RESIDENT-001`：Resident wire Schema：

```json
{
  "schema_version": 1,
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "resident_key": "resident.apothecary.elise",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "resident_revision": 42,
  "identity": {
    "display_name": "艾莉丝",
    "ancestry_id": "ancestry.human",
    "culture_ids": ["culture.crown_creek_local"],
    "language_proficiencies": [{"language_id":"language.crown_common","level":100}]
  },
  "appearance_profile_id": "appearance.resident.apothecary.elise",
  "personality_profile": {"schema_version":1,"dimensions":{},"value_ids":[],"preference_ids":[],"fear_ids":[]},
  "needs": {},
  "emotion": {"primary":"calm","intensity_q1000":180,"updated_at_game_time":1830},
  "health": {"state":"healthy","hp_current":30,"hp_max":30,"injury_ids":[],"illness_ids":[]},
  "capabilities": {"skill_ratings":{},"ability_ids":[]},
  "profession_assignment_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "residence_assignment_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "schedule_profile_id": "schedule.apothecary.standard",
  "lifecycle_state": "active",
  "created_at_game_time": 0,
  "updated_at_game_time": 1830
}
```

写 Port：

```text
create_resident(CreateResidentCommand) -> ResidentResult
apply_health_effect(HealthEffectCommand) -> ResidentResult
change_assignment(ChangeResidentAssignmentCommand) -> ResidentResult
update_needs(NeedsUpdateCommand) -> ResidentResult
set_lifecycle_state(LifecycleTransitionCommand) -> ResidentResult
```

读 Port 返回 immutable `ResidentSnapshot`，必须携带 `resident_revision`。

## 5. 规则与不变量

- `RULE-RESIDENT-001`：`resident_id`、`resident_key` 和 `world_id` 创建后不可变；同一 world 内二者各自唯一。
- `RULE-RESIDENT-002`：正式居民不得物理删除；停用使用非 terminal lifecycle state 与事件表达。
- `RULE-RESIDENT-003`：每次写命令必须携带 `command_id`、`expected_revision`、`schema_version`，相同 `(world_id, command_id)` 最多生效一次。
- `RULE-RESIDENT-004`：`inventory_id` 仅引用 ECON-owned Inventory；Resident 不缓存物品数量、余额、重量或所有者。
- `RULE-RESIDENT-005`：`profession_assignment_id`、`residence_assignment_id`、`schedule_profile_id` 分别是已验证引用；引用失效不得静默创建替代对象。
- `RULE-RESIDENT-006`：任何成功变更与对应 `ResidentCreated`、`ResidentStateChanged` 或专用 DomainEvent 原子提交，失败不增长 Revision。

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

- Schema 可往返序列化且所有跨域字段能定位 owner。
- 重复命令不重复创建或变更。
- 外部引用失败时 Unit of Work 全回滚。
- 正式 Resident 无 delete/death terminal API。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-001` | JSON Schema 正反例、stable ID 与 ULID 校验 |
| `TEST-RESIDENT-002` | 创建/更新/重放的幂等与 Revision Contract Test |
| `TEST-RESIDENT-003` | 外部引用失败注入时无半状态 |
| `TEST-RESIDENT-004` | Repository API 不暴露正式居民物理删除 |

## 12. 关联文档

- `DOC-FOUNDATION-003`：canonical ownership
- `DOC-RESIDENT-010`：Inventory 引用边界
- `DOC-RESIDENT-012`：聚合验收场景


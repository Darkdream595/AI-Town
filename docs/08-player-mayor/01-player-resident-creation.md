---
doc_id: DOC-PLAYER-001
title: 玩家居民创建与身份绑定
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-identity
  - player-resident-binding
  - player-resident-creation
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-RESIDENT-002
  - DOC-RESIDENT-011
requirements:
  - REQ-PLAYER-001
last_updated: 2026-07-26
---

# 玩家居民创建与身份绑定

## 1. 目的

`REQ-PLAYER-001`：把本地玩家身份与一个世界内的正式 Resident aggregate 安全绑定，使玩家能作为居民参与世界，同时保持 Resident Schema、生命周期、权限和 8–12 名 AI 核心居民配额的边界。

## 2. 非目标

本文不定义 Resident 子对象、AI personality、账号联网认证或多人身份。RESIDENT 拥有 Resident aggregate 与创建校验；PLAYER 只拥有本地玩家身份、世界绑定与决策来源。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| PlayerIdentity | 安装实例内的本地玩家主体，不等于 Resident |
| PlayerResidentBinding | 在单个 World 中把一个 PlayerIdentity 绑定到一个 ResidentId |
| Decision Source | `human` 或 `ai`；只描述命令来源，不改变 Domain rule |
| Core AI Resident Quota | 首版 8–12 名 AI 核心居民；玩家 Resident 不计入该配额 |
| World Ownership | PlayerIdentity 对本地 World 的管理关系，不自动授予 Mayor/Admin 权限 |

## 4. 规则与不变量

- `RULE-PLAYER-001`：一个 `(world_id, player_identity_id)` 最多有一个 active binding；一个 ResidentId 最多被一个 active PlayerIdentity 控制。
- `RULE-PLAYER-002`：玩家 Resident 必须通过 `DOC-RESIDENT-011` 的同一创建 validator；PLAYER 不得删减 Needs、Health、Inventory 引用、Position 或版本字段。
- `RULE-PLAYER-003`：`decision_source=human` 不授予额外技能、物品、法术、金钱、位置或秘密；玩家与 AI 的差异只在合法 intent 的来源。
- `RULE-PLAYER-004`：玩家 Resident 不计入 8–12 名 AI 核心居民 Must coverage，但计入世界实体、调度负载、经济守恒和存档。
- `RULE-PLAYER-005`：World owner、Mayor office 与 Sandbox Admin 是三个独立授权；创建 World 或玩家 Resident 不自动获得后两者。

## 5. 数据与接口

`DES-PLAYER-001`：binding 使用稳定 ID、严格版本和显式状态：

```json
{
  "schema_version": 1,
  "binding_id": "01K1PLAYER00000000000000001",
  "world_id": "01K1WORLD000000000000000001",
  "player_identity_id": "01K1IDENTITY00000000000001",
  "resident_id": "01K1RESIDENT0000000000001",
  "decision_source": "human",
  "state": "active",
  "created_by_command_id": "01K1COMMAND000000000000001",
  "created_revision": 12,
  "version": 1
}
```

字段约束：`schema_version=1`；所有 ID 为非空稳定 ID；`decision_source` 固定为 `human`；`state` 仅允许 `pending/active/suspended/retired`；`version>=1`。接口：

```text
prepare_player_resident(command_id, world_id, player_identity_id, resident_draft)
  -> PlayerResidentCreationPrepared
commit_player_resident(command_id, preparation_id, expected_revision)
  -> PlayerResidentBindingResult
get_player_authority(world_id, player_identity_id, revision)
  -> PlayerAuthorityProjection
```

`PlayerAuthorityProjection` 只含 `binding_id/resident_id/world_role_ids/mayor_office_id/admin_session_state/revision`，不含私人记忆或凭据。

## 6. 正常流程

1. Launcher 创建或读取本地 PlayerIdentity；Secret 不进入 PlayerIdentity。
2. 玩家选择世界、公开外观和允许的 Resident 起始选项。
3. PLAYER 生成 `ResidentCreationDraft`，交给 RESIDENT Catalog、必填字段和出生点校验。
4. MAP 验证出生 `WorldPoint` 可站立且未被占用；ECON 创建普通起始账户与 Inventory 引用。
5. 单一 World Writer 原子提交 Resident、binding、初始化事件与幂等结果，Revision 只增长 1。
6. Client 从已提交 Snapshot 获得 resident projection；不能把表单草稿直接当作世界实体。

## 7. 并发、幂等与版本

创建幂等键为 `(world_id, command_id)`，payload hash 覆盖 PlayerIdentity、公开选项与 Resident draft。相同 key 相同 payload 返回原 binding；相同 key 不同 payload 返回 `PLAYER_IDEMPOTENCY_PAYLOAD_CONFLICT`。两个窗口并发创建时由 binding/Resident unique index 保证最多一个成功。任何 `expected_revision` 过期均重新展示最新状态，不静默创建第二名玩家。

## 8. 边界情况与恢复

- 初始化中崩溃：Resident、账户、Inventory、Position、binding 与事件全成或全败。
- active binding 的 Resident 昏迷或被俘：binding 保留，能力由状态 validator 限制，不重建角色。
- binding 损坏或指向缺失 Resident：启动进入 Recovery Barrier，禁止自动生成替代 Resident。
- 导入世界的 PlayerIdentity 不存在：binding 保持 suspended，由明确 reclaim 流程重新绑定并审计。
- 删除世界只删除该世界数据，不删除安装级 PlayerIdentity；删除 PlayerIdentity 不级联篡改世界历史。

## 9. 安全与隐私

Client 不能指定可信 role、starting balance、skill level、spawn point 或 `decision_source`。PlayerIdentity 只保存本地显示名和稳定 ID，不存 DeepSeek Key。公开角色创建页不得读取 AI/Memory 私有字段；敏感 reclaim 需要当前本地 world ownership proof。

## 10. 验收标准

- 玩家 Resident 通过完整 RESIDENT validator，且不计入 8–12 AI 核心居民配额。
- 同一玩家/世界不能产生两个 active binding，同一 Resident 不能被两名玩家绑定。
- 创建失败和崩溃无孤儿账户、Inventory、Position 或半成品 Resident。
- World owner、Mayor 与 Admin 三类授权可分别为 false。
- Snapshot 重放后 binding、Resident 和初始化 DomainEvent 一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-001` | 完整玩家 Resident 创建与 AI 配额隔离 |
| `TEST-PLAYER-002` | 双窗口创建、幂等重试与 payload conflict |
| `TEST-PLAYER-003` | 初始化各故障点原子回滚 |
| `TEST-PLAYER-004` | binding 缺失、导入 reclaim 与权限分离 |

## 12. 关联文档

- `DOC-RESIDENT-001`：Resident aggregate canonical Schema
- `DOC-RESIDENT-011`：创建编排与初始化不变量
- `DOC-PLAYER-007`：居民模式能力
- `DOC-PLAYER-009`：Sandbox Admin 独立授权与审计


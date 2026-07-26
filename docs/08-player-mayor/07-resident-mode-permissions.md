---
doc_id: DOC-PLAYER-007
title: 玩家居民模式权限
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - resident-mode-permissions
  - player-capability-authorization
  - resident-mode-denials
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-001
  - DOC-RESIDENT-007
  - DOC-RESIDENT-010
  - DOC-ECON-005
  - DOC-PLAYER-001
requirements:
  - REQ-PLAYER-007
last_updated: 2026-07-26
---

# 玩家居民模式权限

## 1. 目的

`REQ-PLAYER-007`：定义玩家在 Resident Mode 的默认能力、角色/财产/地点授权、最小披露和拒绝规则，使玩家既能完整参与小镇，又不能因人类输入绕过正式居民规则。

## 2. 非目标

本文不定义 Mayor、Sandbox Admin、各职业许可、秘密分类内部实现或 Domain 数值公式。PLAYER 组合 owner 提供的 permission projection，不复制其权威状态。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 有效能力 | 玩家当前可尝试的能力集合，由权限模型交集给出，而非 UI 按钮集合 |
| Permission Projection | 服务端按 Revision 生成的能力提示投影，不是授权本身 |
| world_owner | 只允许世界管理/存档操作的安装级角色 |
| resident | 允许普通世界行动的绑定 Resident 角色 |

### 3.1 权限模型

有效能力为下列交集：

```text
active player-resident binding
∩ resident health/state capability
∩ learned skill/spell and profession role
∩ target/scene/jurisdiction permission
∩ ownership/consent/reservation
∩ current action and legal state
∩ latest world revision
```

`world_owner` 只允许世界管理/存档操作；`resident` 允许普通世界行动；`mayor` 与 `sandbox_admin` 不包含在居民模式 capability 中。

## 4. 规则与不变量

- `RULE-PLAYER-031`：Resident Mode 不允许治理公共预算、改税率、发布强制公告、修改公共工程，也不允许 Admin mutation。
- `RULE-PLAYER-032`：玩家只能使用绑定 Resident 已拥有/获准的物品、金钱、技能、法术、职业、门禁和关系能力。
- `RULE-PLAYER-033`：读取能力遵循最小披露；私人记忆、personal/shared_secret、隐藏关系数值、未观察事件和 AI reasoning 默认不可见。
- `RULE-PLAYER-034`：owner/consent/permission/Reservation 在提交点以最新版本校验；Client token、UI 状态或旧 projection 不构成授权。
- `RULE-PLAYER-035`：拒绝是稳定结果，必须给安全 reason code；不得通过 fallback 把禁止命令改成近似成功。

## 5. 数据与接口

### 5.1 权限投影 Schema

```json
{
  "schema_version": 1,
  "binding_id": "01K1BNDG000000000000000001",
  "resident_id": "01K1RSDT000000000000000001",
  "mode": "resident_active",
  "revision": 240,
  "capability_ids": [
    "resident.move",
    "resident.talk",
    "resident.trade",
    "resident.work"
  ],
  "role_versions": {
    "profession.blacksmith": 2
  },
  "restriction_codes": [],
  "expires_after_revision": 240
}
```

Projection 不包含余额、Inventory 内容、secret、relationship raw values 或 capability 参数。具体命令仍由 owner 查询这些权威值。

### 5.2 能力矩阵

| 操作 | 默认 | 附加条件 |
|---|---:|---|
| 移动、观察、公开交谈 | 允许尝试 | 健康、Scene、Collision、距离、语言 |
| 工作、交易、制作、采集 | 允许尝试 | Contract/许可、ownership、Quote、资源、地点 |
| 赠与、承诺、关系行为 | 允许尝试 | consent、ownership、social interpretation |
| 施法、战斗 | 条件允许 | learned、资源、目标、法律、Encounter/turn |
| 进入建筑/容器 | 条件允许 | Door、property、invitation、role |
| 查看公开统计 | 允许 | public projection |
| 查看私人记忆/秘密 | 默认禁止 | 只有 owner 明确的合法披露事件 |
| 管理公共预算/税率 | 禁止 | 必须切换 Mayor 并重新授权 |
| 直接 set state/mint/teleport | 禁止 | 仅显式 Admin 流程可提议受限 mutation |

## 6. 正常流程

1. Gateway 从 session 和 binding 得到 actor，忽略 Client actor/role。
2. PLAYER 验证 mode 与 capability category。
3. Orchestrator 请求 owner 的 revision-stamped role、health、ownership、consent、scene 与 legal projection。
4. Domain validator 使用最新 aggregate 检查，而非仅信任 projection。
5. 成功按 `DOC-PLAYER-006` 提交事件；拒绝返回 `deny_code + safe_player_message + retryability`。
6. UI 根据新 projection 更新提示，不暴露被拒绝目标的私有原因。

## 7. 边界情况

- Capability cache 最多有效到生成时 Revision；角色、健康、拘押、产权或 Scene 变化立即使相关项失效。
- 重复 permission check 可缓存只读结果，但 commit 仍重校验。

## 8. 错误与降级

- 恢复后从 binding 和 owner aggregates 重建，不从 Client localStorage 恢复 role。
- 权限投影无法生成时 fail closed，但移动到安全位置和存档等基本恢复能力由专用 system command 提供。

## 9. 安全与性能

错误消息区分 `not_permitted` 与可公开原因，不能通过枚举目标探测秘密/私人物品。例如访问 secret 门失败可统一显示“无法进入”，而不是泄露 owner 或内部事件。权限日志保存 actor、capability、resource ID hash、decision、policy version 和 correlation，不保存对话/secret 内容。

## 10. 验收标准

- 玩家与相同状态 AI Resident 的普通 action 权限结果一致。
- 居民模式不能调用 Mayor/Admin command union。
- 旧 role/ownership projection、伪造 Client role 和枚举攻击均失败。
- 私人记忆、隐藏关系和 secret 不出现在 capability/错误/日志中。
- 权限撤销与恢复后没有残留能力。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-025` | resident capability matrix 与 AI parity |
| `TEST-PLAYER-026` | role/ownership/consent stale revocation |
| `TEST-PLAYER-027` | Mayor/Admin union confusion 拒绝 |
| `TEST-PLAYER-028` | secret enumeration、error/log 最小披露 |

## 12. 关联文档

- `DOC-PLAYER-004`：统一 action 路由
- `DOC-PLAYER-008`：Mayor 权限不继承
- `DOC-PLAYER-009`：Admin 独立 session 和确认
- `DOC-MEMORY-009`：秘密与隐私投影 owner contract

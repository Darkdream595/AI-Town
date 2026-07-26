---
doc_id: DOC-MEMORY-009
title: 秘密、隐私、AccessPolicy 与 Prompt 前过滤
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - memory-access-policy
  - secret-access-levels
  - pre-prompt-secret-filter
  - access-decision
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-009
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-006
  - DOC-MEMORY-007
requirements:
  - REQ-MEMORY-009
last_updated: 2026-07-26
---

# 秘密、隐私、AccessPolicy 与 Prompt 前过滤

## 1. 目的

`REQ-MEMORY-009`：定义 `public/community/faction/relationship/personal/shared_secret` 六级访问策略、当前 Revision 授权、最小 materialization 和 `AuthorizedMemoryContextV1` 输出边界，保证未授权秘密在 Prompt construction 之前已被后端排除，而不是依赖提示词要求模型保密。

## 2. 非目标

本文不构造/存储 Prompt、不定义 HTTP Session、Windows API Key secret 或文件加密，也不授予 Mayor/Sandbox Admin 对私人认知的默认读取权。

## 3. 术语与定义

| Access Level | 允许主体 |
|---|---|
| `public` | 当前 world 中所有合法 resident principal |
| `community` | policy 指定 community 的当前成员，外加 owner |
| `faction` | policy 指定 faction 的当前成员，外加 owner |
| `relationship` | owner + 显式 allow list；可选关系阈值必须全部满足 |
| `personal` | 仅 owner |
| `shared_secret` | 仅精确 participant set；owner 必须在 participants 中 |

`Mayor` 是治理身份，不是 privacy override；`Sandbox Admin` 的 forensic inspection 是独立、二次确认、审计且永不进入模型上下文的管理流程。

## 4. 数据与接口

`DES-MEMORY-009`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/access-policy/v1",
  "type": "object",
  "required": [
    "schema_version",
    "access_policy_id",
    "world_id",
    "owner_principal_id",
    "access_level",
    "community_id",
    "faction_id",
    "relationship_rule",
    "participant_ids",
    "explicit_allow_principal_ids",
    "policy_version"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "access_policy_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "owner_principal_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "access_level": {
      "enum": ["public", "community", "faction", "relationship", "personal", "shared_secret"]
    },
    "community_id": {
      "type": ["string", "null"],
      "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"
    },
    "faction_id": {
      "type": ["string", "null"],
      "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$"
    },
    "relationship_rule": {
      "type": ["object", "null"],
      "required": ["minimum_trust", "minimum_intimacy", "require_all"],
      "properties": {
        "minimum_trust": {"type": "integer", "minimum": -100, "maximum": 100},
        "minimum_intimacy": {"type": "integer", "minimum": -100, "maximum": 100},
        "require_all": {"const": true}
      },
      "additionalProperties": false
    },
    "participant_ids": {
      "type": "array",
      "maxItems": 16,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 128}
    },
    "explicit_allow_principal_ids": {
      "type": "array",
      "maxItems": 32,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 128}
    },
    "policy_version": {"type": "integer", "minimum": 1}
  },
  "allOf": [
    {
      "if": {"properties": {"access_level": {"const": "community"}}},
      "then": {"required": ["community_id"], "properties": {"community_id": {"type": "string"}}},
      "else": {"properties": {"community_id": {"type": "null"}}}
    },
    {
      "if": {"properties": {"access_level": {"const": "faction"}}},
      "then": {"required": ["faction_id"], "properties": {"faction_id": {"type": "string"}}},
      "else": {"properties": {"faction_id": {"type": "null"}}}
    },
    {
      "if": {"properties": {"access_level": {"const": "relationship"}}},
      "then": {"required": ["relationship_rule"], "properties": {"relationship_rule": {"type": "object"}}},
      "else": {"properties": {"relationship_rule": {"type": "null"}}}
    },
    {
      "if": {"properties": {"access_level": {"const": "shared_secret"}}},
      "then": {"properties": {"participant_ids": {"minItems": 2}}},
      "else": {"properties": {"participant_ids": {"maxItems": 0}}}
    }
  ],
  "additionalProperties": false
}
```

`AccessDecisionV1` required：

```json
{
  "schema_version": 1,
  "access_decision_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "principal_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "memory_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "policy_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "policy_version": 3,
  "observed_revision": 450,
  "purpose": "resident_decision_context",
  "decision": "allow",
  "reason_code": "owner_access"
}
```

目的 enum：`resident_decision_context/player_journal/dialogue_context/authorized_ui/rumor_transfer/admin_forensic`。Prompt chain：

```text
metadata candidates
-> current principal/membership/relationship snapshot
-> AccessDecision per memory
-> allow-only payload materialization
-> budget/redaction scan
-> AuthorizedMemoryContextV1
-> AI-owned Prompt construction
```

Port：

```text
authorize_memory_access(principal, memory_metadata, purpose, access_snapshot) -> AccessDecisionV1
materialize_allow_set(access_decision_ids) -> AuthorizedMemoryContextV1
scan_authorized_context(context) -> SecretBoundaryScan
inspect_memory_forensic(admin_command, memory_id) -> AuditedForensicResult
```

## 5. 规则与不变量

- `RULE-MEMORY-068`：六个 access level 是封闭 enum；未知值 fail closed，不映射为 public。
- `RULE-MEMORY-069`：policy 在 memory commit 前确定；policy 变化创建新 version 与事件，不能就地放宽旧审计。
- `RULE-MEMORY-070`：membership/relationship/participants 必须来自同一 observed Revision；stale access snapshot 整次拒绝。
- `RULE-MEMORY-071`：AccessDecision allow 之前 Repository/Context Builder 不得读取 payload、claim、summary_text、participants 或 source content。
- `RULE-MEMORY-072`：`personal` 仅 owner；`shared_secret` 仅 participant set，且 owner 必须在 participant set 中；关系高、Mayor、Faction leader 均不产生隐式 override。
- `RULE-MEMORY-073`：`relationship` 若设置 threshold，trust 与 intimacy 必须同时达到，且 principal 在 explicit allow list；只有阈值而无 allow list不授权。
- `RULE-MEMORY-074`：community/faction membership 离开后立即失去新访问权；过去已写入的本人记忆仍按其自己的 policy 存在，不被远程删除。
- `RULE-MEMORY-075`：Mayor 只能读取 public 与其本人作为 resident 合法可见的信息；治理统计必须由 owner 发布聚合数据，不读取 private Memory。
- `RULE-MEMORY-076`：forensic inspection 不得流向 Prompt、普通日志、WebSocket render 或玩家 journal；要求 Sandbox Admin、二次确认、永久 timeline 标记与审计事件。
- `RULE-MEMORY-077`：Secret boundary scan 发现 decision 缺失、policy version 不匹配、deny item 或 forbidden key 时整份 context rejected。
- `RULE-MEMORY-078`：日志/诊断只保留 decision ID、level category、reason code、count/hash；禁止记录 payload 或 shared-secret participant names。

## 6. 正常流程

1. caller 以 authenticated principal、actor、purpose 和 observed Revision 请求检索。
2. Orchestrator 提供 current membership 与 source-owned relationship projection。
3. MEMORY 只对 metadata 执行 level-specific predicate，生成 allow/deny decision。
4. 只 materialize allow set，执行 byte budget 与 forbidden-key scan。
5. 输出 `AuthorizedMemoryContextV1`，包含每项 decision ID 与 policy version。
6. AI Context Builder 验证 context hash/Revision 后构造 Prompt；它无 Repository access。

## 7. 边界情况

- principal 同时是 Mayor、Faction leader 和好友：仍逐 policy 求值，不取最高角色。
- relationship 在检索后下降：提交 AI 行动前不需要再次泄露 payload，但新的 context build 使用最新 policy；旧 request record按受控 hash/replay处理。
- policy 从 public 收紧为 shared_secret：新访问立即按新 version；已发送模型请求不能撤回，必须有最小上下文与请求审计。
- participant set 修改必须所有仍有权限 owner/规则证据满足；不得由任一参与者单方面扩大。
- ACL store 不可用时返回空/denied context，不使用缓存 payload；只可使用未过期且 policy/revision完全匹配的 allow decision cache。

## 8. 错误、降级与恢复

错误码为 `MEMORY_ACCESS_DENIED`、`MEMORY_ACCESS_SNAPSHOT_STALE`、`MEMORY_POLICY_INVALID`、`MEMORY_SECRET_BOUNDARY_FAILED`、`MEMORY_FORENSIC_AUTH_REQUIRED`。任何安全组件失败均 fail closed；世界可继续 Utility AI 基本行动，但不能使用受保护上下文。

### 8.1 Version 与 Migration

v1 policy upcast 必须保留或收紧访问；无法唯一映射旧 privacy label 时迁移为 `personal` 并标记 review，绝不能默认为 public。迁移后对六级 fixture、Mayor、shared_secret 和 stale snapshot 执行完整 oracle。

## 9. 安全与性能

AccessDecision 可按 `(principal,policy_version,relationship_revision,membership_revision,purpose)` 短期缓存，但不缓存 payload。每 context 最多 128 decisions/16 materializations/12 KiB。Secret scan 运行于 Prompt construction 前，且错误不能被 Prompt 指令覆盖。

## 10. 验收标准

- 六级 access matrix 对 owner/member/nonmember/friend/Mayor/participant 逐格符合 oracle。
- deny 项 materialize 调用次数为 0，Prompt 输入 scan 中 deny/unknown 为 0。
- membership/relationship/policy stale 全部 fail closed。
- shared_secret 对高 trust、Mayor、Faction leader 均无隐式泄露。
- forensic 结果不出现在 Prompt、Event render、普通日志或诊断包。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-033` | 六级 strict policy Schema 与 conditional |
| `TEST-MEMORY-034` | access matrix、Mayor 与 shared_secret |
| `TEST-MEMORY-035` | ACL-before-materialize/Prompt 与 boundary scan |
| `TEST-MEMORY-036` | stale/cache/policy change fail closed |
| `TEST-MEMORY-037` | forensic isolation、migration 收紧与诊断脱敏 |

## 12. 关联文档

- `DOC-MEMORY-003`：authorized retrieval
- `DOC-MEMORY-008`：传播 ACL
- `DOC-MEMORY-011`：玩家、Mayor 的认知边界
- `DOC-FOUNDATION-005`：未授权 Secret 不进入 Prompt

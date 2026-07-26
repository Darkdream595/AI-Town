---
doc_id: DOC-MEMORY-011
title: 玩家行为、Mayor 治理记忆与删除边界
version: 1.0.0
status: approved-for-implementation
owner_domain: memory
canonical_for:
  - player-behavior-memory
  - mayor-memory-boundary
  - player-journal-projection
  - memory-deletion-boundary
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-008
  - DOC-RESIDENT-001
  - DOC-MEMORY-001
  - DOC-MEMORY-002
  - DOC-MEMORY-005
  - DOC-MEMORY-006
  - DOC-MEMORY-009
  - DOC-MEMORY-010
requirements:
  - REQ-MEMORY-011
last_updated: 2026-07-26
---

# 玩家行为、Mayor 治理记忆与删除边界

## 1. 目的

`REQ-MEMORY-011`：定义玩家以 Resident 身份参与时如何被观察、记忆、评价和建立 Commitment，Mayor 治理事件如何形成公共/主观认知，以及玩家 journal、隐藏、tombstone、存档重载的权限边界。

## 2. 非目标

本文不拥有玩家输入、Mayor Command、治理预算、对话或 UI；不赋予玩家删除 NPC 记忆、重写关系、读取私人认知或用 Mayor 身份取得全知。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Player Resident | 使用正式 Resident aggregate 与相同世界/社会规则的玩家角色 |
| Player Behavior Memory | NPC 对已提交且其可观察的 Player action/speech/result 的认知 |
| Civic Record | Mayor command 成功后由 owner 发布的公开治理事实引用 |
| Mayor Impression | 居民基于可知 Civic Record 形成的主观 memory/relationship delta |
| Player Journal | 玩家本人 authorized memories/Commitments/Civic Records 的只读 UI projection |
| Journal Hide | 仅 UI 偏好，不删除 canonical memory |
| Correction Tombstone | `DOC-MEMORY-005` 授权流程清除错误/违规 payload，保留审计 lineage |

## 4. 数据与接口

`DES-MEMORY-011`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/memory/player-journal-entry/v1",
  "type": "object",
  "required": [
    "schema_version",
    "entry_id",
    "player_resident_id",
    "source_kind",
    "source_ref_id",
    "access_decision_id",
    "display_summary",
    "journal_state",
    "observed_revision"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "entry_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "player_resident_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "source_kind": {"enum": ["memory", "commitment", "civic_record"]},
    "source_ref_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "access_decision_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "display_summary": {"type": "string", "minLength": 1, "maxLength": 1024},
    "journal_state": {"enum": ["visible", "hidden"]},
    "observed_revision": {"type": "integer", "minimum": 0}
  },
  "additionalProperties": false
}
```

可观察玩家行为目录 v1：

| 结果事件类别 | 可能认知 | 前置 |
|---|---|---|
| 对话/承诺 | episode、belief、Commitment | Speech Act/Commitment 已提交且 actor 在会话 |
| give/trade/work | episode、impression、relationship delta | 交易/工作结果已提交且 observer 合法感知 |
| help/heal/rescue | high-importance episode、trust/affection/respect | owner 结果事件 |
| harm/threat/theft | episode、fear/trust/affection delta | 事件可知且内容许可 |
| Mayor tax/build/notice/festival | Civic Record belief、Mayor impression | governance command 已提交、公开范围明确 |
| rejected/failed action | 仅直接参与者/观察者的失败经历 | 失败有已提交可观察结果；Proposal 不算 |

Port：

```text
project_player_behavior_for_observers(result_event, observer_set) -> MemoryWriteCandidateSet
project_mayor_civic_record(governance_event, disclosure_policy) -> CivicMemoryCandidateSet
get_player_journal(player_id, filter, revision) -> AuthorizedPlayerJournal
set_journal_entry_visibility(player_id, entry_id, visible) -> JournalPreferenceResult
request_correction_tombstone(admin_command, memory_id, evidence_event_id) -> TombstoneResult
```

## 5. 规则与不变量

- `RULE-MEMORY-088`：玩家 Resident 与 AI Resident 的 memory/relationship/ACL 规则相同；差别仅在行动决策来源。
- `RULE-MEMORY-089`：NPC 只记得其直接观察、参与或被合法传播的玩家行为；玩家全局行为日志不会自动进入所有居民记忆。
- `RULE-MEMORY-090`：Mayor command 成功只产生治理事实；每名居民根据其可知范围、人格和经历形成独立 belief/impression/delta。
- `RULE-MEMORY-091`：Mayor 不得读取 personal/shared_secret/relationship memory、直接设关系或删除居民记忆。
- `RULE-MEMORY-092`：Player Journal 逐项使用玩家当前 principal 的 AccessDecision；它不是 MEMORY Repository 管理界面。
- `RULE-MEMORY-093`：Journal hide 只改玩家偏好，不改 MemoryRecord、ACL、关系、AI context 或其他角色 journal。
- `RULE-MEMORY-094`：玩家请求“忘掉我”可成为对话/社会事件，但不执行删除；NPC 是否调整关系/行为仍走已提交规则。
- `RULE-MEMORY-095`：canonical tombstone 仅处理错误来源、重复记录、受授权更正或 migration redaction；不得用于抹去合法负面后果。
- `RULE-MEMORY-096`：save/reload 必须保留 NPC 对玩家的 memory、relationship、Commitment、journal hidden preference、tombstone 与幂等 keys。

## 6. 正常流程

1. 玩家命令经业务 owner 提交结果事件。
2. Orchestrator 根据事件时的 Scene/会话/参与者生成合法 observer set。
3. MEMORY 为每个 observer 独立执行 eligibility、ACL、write key、impression/relationship解释。
4. Mayor 治理结果先形成 owner Civic Record，再按 disclosure scope进入居民认知。
5. 玩家打开 journal 时逐项授权、materialize、生成只读 projection。
6. hide 保存偏好；correction tombstone 走独立 Sandbox Admin 审计并在 reload 验证 payload 清除。

## 7. 边界情况

- 玩家私下送礼：只有双方及合法 observer 记得；其他居民不会因“系统知道”而获得印象。
- Mayor 降税：公开 Civic Record 存在，但未听闻的远方居民保持 unknown。
- 玩家切换 Resident/Mayor mode：identity 不变，过去关系/记忆不重置。
- 玩家 journal entry hidden 后，NPC 仍可合法检索自己的相关记忆。
- 玩家删除 world 是 RELEASE 管理行为；本文件不把它当单条记忆 tombstone，也不承诺跨 world 保留。

## 8. 错误、降级与恢复

错误码为 `MEMORY_PLAYER_OBSERVER_INVALID`、`MEMORY_MAYOR_PRIVACY_OVERRIDE_FORBIDDEN`、`MEMORY_JOURNAL_ACCESS_DENIED`、`MEMORY_CORRECTION_EVIDENCE_REQUIRED`。observer evidence 不完整时不写；Journal不可用不影响世界运行；tombstone 未完成时所有 read fail closed。

### 8.1 Version 与 Migration

Player Journal 是可重建 projection，Schema 升级可重建但必须迁移 hidden preference key。旧版“delete memory”命令只允许迁移为 journal hide；若历史确实清除了 payload，则生成 migration tombstone 和 hash audit，不能伪造原内容。

## 9. 安全与性能

每 result event 的 observer set 上限由空间/会话 owner 给出并去重，MEMORY 不做全居民广播扫描。Journal 每页≤50、只返回 authorized display summary。Mayor statistics 使用聚合/匿名 owner projection，不以逐条 Memory 绕过隐私。

## 10. 验收标准

- 同一玩家事件对 participant/direct observer/nonobserver 产生预期不同 memory set。
- Resident/Mayor mode 切换不清空社会状态。
- Mayor 无法读取或删除 private/shared_secret 记录。
- journal hide 不改变 canonical memory 或 NPC 检索。
- tombstone/reload 后 payload 不回现，合法负面记忆不会被普通玩家命令删除。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-MEMORY-042` | player observer eligibility 与相同社会规则 |
| `TEST-MEMORY-043` | Mayor civic record、unknown 与 privacy boundary |
| `TEST-MEMORY-044` | journal authorization/hide isolation |
| `TEST-MEMORY-045` | correction tombstone、negative consequence 与 reload |

## 12. 关联文档

- `DOC-MEMORY-002`：observer write eligibility
- `DOC-MEMORY-005`：tombstone 终止状态
- `DOC-MEMORY-009`：Mayor/Journal ACL
- `DOC-MEMORY-012`：玩家与恢复固定场景

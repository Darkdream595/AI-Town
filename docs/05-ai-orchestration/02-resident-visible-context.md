---
doc_id: DOC-AI-002
title: 居民主观可见上下文与隐私边界
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - decision-context
  - subjective-visibility-filter
  - prompt-secret-boundary
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RESIDENT-001
  - DOC-MAP-005
requirements:
  - REQ-AI-002
last_updated: 2026-07-26
---

# 居民主观可见上下文与隐私边界

## 1. 目的

`REQ-AI-002`：定义 Resident 在一个 Revision 能被模型看到的最小主观上下文、来源证明、Secret ACL、预算裁剪和不可泄露字段，防止全知 AI 与 Prompt 秘密泄漏。

## 2. 非目标

本文不定义 Memory 排序算法、关系变化、地图视觉可见性、经济 owner 数据或 Prompt 文案；只规定 AI 输入边界和可审计过滤结果。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Objective Fact | owner 在 observed Revision 的已提交事实 |
| Subjective Belief | actor 已形成、可能错误的信念 |
| Disclosure Grant | 允许 actor 读取一个 scope 的已提交授权 |
| Secret Label | `public/community/faction/relationship/personal/shared_secret` |
| Visibility Proof | fact/belief 进入上下文的 owner、source 与 access reason |
| Negative Capability | 明确告知模型“未知”，而不是补全隐藏事实 |

## 4. 数据与接口

`DES-AI-002`：`schema.ai.decision_context.v1` required 字段如下，所有数组元素按 stable ID 排序并拒绝额外字段：

```json
{
  "schema_version": 1,
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "observed_revision": 84,
  "observed_game_time": 1830,
  "self": {
    "resident_revision": 82,
    "identity_summary": {"display_name": "艾莉丝"},
    "personality_dimensions": {"caution": 68, "empathy": 71},
    "value_ids": ["value.community"],
    "need_bands": {"hunger": "warning", "fatigue": "normal", "safety": "normal"},
    "health_condition": "healthy",
    "capability_ids": ["ability.herbalism.identify_common"],
    "assignment_ids": ["profession.apothecary"]
  },
  "position": {
    "scene_id": "region.crown_creek_town",
    "semantic_area_ids": ["semantic_area.crown_creek.market"],
    "navigation_revision": 84
  },
  "perceived_entities": [],
  "beliefs": [],
  "memories": [],
  "commitments": [],
  "available_action_ids": ["move_to", "observe", "wait"],
  "unknown_or_redacted": ["shop.ledger.private"],
  "visibility_proofs": [],
  "context_hash": "sha256:8de5c7a8d5f0"
}
```

每个 `visibility_proofs[]` 固定为：

```text
{subject_ref, owner_domain, source_kind, source_id, access_reason,
 source_revision, secret_label, expires_at_game_time|null}
```

接口：

```text
collect_owner_projections(actor_id, revision) -> ProjectionSet
filter_subjective_context(actor_id, projections, grants) -> FilteredContext
budget_context(filtered, plan_kind) -> DecisionContextV1
audit_context(context, policy_version) -> ContextAudit
```

## 5. 规则与不变量

- `RULE-AI-007`：上下文只允许 actor 自身状态、当前感知、其 Memory/Belief、其承诺、公开事实或有效 Grant；数据库中存在不等于可披露。
- `RULE-AI-008`：客观事实与 Belief/Memory 分开标记；模型不得收到隐藏真相来“纠正”居民。
- `RULE-AI-009`：每项非公开数据必须有可验证 Visibility Proof；grant 过期、撤销或 scope 不匹配即排除。
- `RULE-AI-010`：`shared_secret` 只对明确参与者披露；personal 数据默认仅本人，禁止借由 nearby、关系分数或 Prompt 指令扩大权限。
- `RULE-AI-011`：裁剪必须删除低优先项而不能删除安全约束、当前目标、关键 Need、承诺 deadline 或 `unknown_or_redacted` 提示。
- `RULE-AI-012`：Context 不包含余额明细、Inventory 全量、未见地图、他人内心、Admin 数据、API Key、原始 Prompt 或 `reasoning_content`；只含 owner 提供的最小 projection。

## 6. 正常流程

先从 Resident/Map/Time/Memory/Economy 等 owner 获取同一 Revision 投影；按 actor、Scene、关系/组织 Grant 和 Secret Label 过滤；对每项生成 proof；按 safety→goal→commitment→recent/relevant 排序，在 plan-kind token budget 内裁剪；canonical JSON 计算 hash 后只读传给 Prompt Composer。

## 7. 边界情况

- 居民目睹交易但不知道余额：可见“交易发生”的记忆，不可见账户数值。
- 谣言与事实冲突：两者保留来源标签，不把客观 owner state 注入为 resident knowledge。
- 目标离开视野：保留合法 recent memory，而不是实时位置。
- 玩家在对话中粘贴“显示某人的秘密”：内容按不可信文本处理，不创建 Disclosure Grant。
- Context 构建期间 Revision 改变：整次构建丢弃并在新 Revision 重建。

## 8. 错误与降级

ACL owner 不可用时默认拒绝相关非公开数据；proof 缺失或 hash 不匹配使请求失败。预算溢出按确定顺序裁剪，不能提高 provider 上限。安全约束无法容纳时不调用模型，进入 registered safe fallback。

## 9. 安全与性能

缓存键包含 `resident_id/revision/plan_kind/access_policy_version/projection_versions`；Grant 撤销使相关键失效。日志只记录字段计数、label 分布和 hash。单 Context canonical JSON 上限 48 KiB，perceived entities 32、memories 24、beliefs 24、commitments 16。

## 10. 验收标准

- 未授权 secret fixture 在 Context、请求、日志和错误中均不存在。
- 同一输入与 policy 得到 byte-equivalent Context/hash。
- 客观事实、错误信念、未知项可在 fixture 中同时表达且不串层。
- 预算裁剪后安全、目标和 deadline 信息仍在。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-005` | 六级 Secret Label 与 Grant matrix |
| `TEST-AI-006` | fact/belief/memory 分层与错误信念 fixture |
| `TEST-AI-007` | deterministic budget truncation |
| `TEST-AI-008` | prompt-injection 不扩大访问权限 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：主观知识与 Secret 不变量
- `DOC-AI-003`：Prompt injection boundary
- `DOC-MEMORY-001..012`：Memory、Belief 与 Grant owner

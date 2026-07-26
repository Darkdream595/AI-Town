---
doc_id: DOC-AI-003
title: Prompt 分层、版本与注入防线
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - prompt-layering
  - prompt-version-registry
  - prompt-injection-boundary
depends_on:
  - DOC-AI-002
  - DOC-FOUNDATION-005
requirements:
  - REQ-AI-003
last_updated: 2026-07-26
---

# Prompt 分层、版本与注入防线

## 1. 目的

`REQ-AI-003`：定义 Prompt 的不可变层次、版本 ID、变量白名单、内容隔离和注入防线，使模型只在注册 Action/Schema 内工作，且历史请求可追踪与重放。

## 2. 非目标

本文不保存 Chain of Thought，不授予世界权限，不让 Prompt 替代 Domain validator，也不把玩家/居民文本升级为 system/developer instruction。

## 3. 术语与定义

| 层 | 权威性与内容 |
|---|---|
| `system_contract` | 权威边界、安全、输出仅 JSON、禁止泄露 |
| `developer_task` | plan kind、Action Catalog、Schema、选择准则 |
| `world_rules` | 版本化规则摘要和单位，不含隐藏世界状态 |
| `resident_profile` | 已过滤人格、价值、Needs 与自我身份 |
| `decision_context` | DOC-AI-002 immutable JSON |
| `untrusted_content` | 对话、书信、招牌、记忆原文；始终作为数据 |
| `output_contract` | artifact strict Schema 与停止条件 |

## 4. 数据与接口

`DES-AI-003`：Prompt Registry 首版 ID：

```text
resident-daily-plan/v1
resident-hourly-intent/v1
resident-action/v1
resident-dialogue/v1
resident-combat-turn/v1
event-director/v1
memory-consolidation/v1
```

AI 子系统直接使用前三个及 combat-turn；其余由 owner 文档引用。Registry record：

```json
{
  "prompt_id": "resident-action/v1",
  "artifact_schema_id": "schema.ai.action_proposal.v1",
  "template_sha256": "sha256:8b30d4f31c17",
  "policy_version": 1,
  "allowed_variables": ["decision_context_json", "action_catalog_digest"],
  "model_policy_id": "model_policy.resident_action.v1",
  "status": "active"
}
```

消息装配顺序固定为 `system_contract → developer_task → world_rules → resident_profile → decision_context → output_contract`；`untrusted_content` 只能作为 `decision_context` 内 JSON string，并使用 JSON serializer 转义。

## 5. 规则与不变量

- `RULE-AI-013`：层顺序固定，低层不能覆盖高层；所有变量必须在 Registry 白名单，禁止运行时拼接额外 instruction。
- `RULE-AI-014`：玩家、居民、Memory、Item 文本和网络内容均为 untrusted data；其中“忽略规则”“调用工具”“显示秘密”等只作为故事文本。
- `RULE-AI-015`：Prompt ID 语义不可就地改变；模板、Schema、模型策略或安全规则改变必须发布新 version 或 policy version。
- `RULE-AI-016`：Prompt 不声明模型拥有世界写权限、可信数值结算、任意 Action/target 或秘密访问。
- `RULE-AI-017`：Action Catalog 与 output Schema 由版本化 registry 引用；Prompt 中的摘要 hash 必须匹配 decoder 使用版本。
- `RULE-AI-018`：持久化只记录 Prompt ID、template hash、context hash、policy/model version；不保存完整 Prompt 或 `reasoning_content`。

## 6. 正常流程

Composer 解析 active registry；校验变量集合；使用 canonical JSON 注入 DecisionContext；为 untrusted strings 添加数据标签但不依赖自然语言标签作为安全边界；计算 request hash；ModelProvider 调用后 strict decoder 按 registry Schema 解析；记录版本元数据。

## 7. 边界情况

- 旧存档引用 inactive Prompt：replay 使用记录响应；新请求迁移到明确 successor，不悄悄套新模板。
- 文本包含 JSON closing brace、Markdown fence 或 Unicode 控制符：serializer 正确转义，长度/控制字符 policy 拒绝异常输入。
- Catalog 升级但 Prompt 缓存未失效：hash mismatch 阻止调用。
- 模型返回额外 prose/code fence：strict JSON decoder 拒绝并进入一次 repair。

## 8. 错误与降级

未知 Prompt ID、变量越界、模板 hash 不符、Schema 不兼容或 Context 超限均在 provider 调用前失败。repair 使用专门 `output-repair/v1` 的最小错误列表，不回传秘密值；再次失败进入 fallback。

## 9. 安全与性能

模板随应用只读发布并在启动时 hash 校验；配置不能从世界存档或 Client 覆盖。缓存只保存 template tokenization 和脱敏 request metadata。每个 untrusted string 上限 2048 Unicode scalar，总 untrusted 字符上限 8192。

## 10. 验收标准

- Registry ID、template hash、Schema 与模型策略可唯一解析。
- injection corpus 无法改变 Action enum、访问 hidden field 或产生非 JSON 成功。
- 版本迁移和历史重放不依赖当前模板内容。
- 日志、Event、Memory 和诊断包不含完整 Prompt/Chain of Thought。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-009` | layer order、variable whitelist、hash |
| `TEST-AI-010` | injection/escaping/control-character corpus |
| `TEST-AI-011` | Prompt/Schema/model-policy version compatibility |
| `TEST-AI-012` | no full Prompt/reasoning persistence |

## 12. 关联文档

- `DOC-AI-002`：唯一 Context 输入
- `DOC-AI-004`：ActionProposal strict Schema
- `DOC-AI-007`：model policy routing

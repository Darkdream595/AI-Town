---
doc_id: DOC-AI-007
title: DeepSeek 模型策略与 Thinking 路由
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - deepseek-provider-policy
  - thinking-mode-routing
  - reasoning-content-disposal
depends_on:
  - DOC-AI-003
  - DOC-AI-006
requirements:
  - REQ-AI-007
last_updated: 2026-07-26
---

# DeepSeek 模型策略与 Thinking 路由

## 1. 目的

`REQ-AI-007`：定义 `ModelProvider` 抽象、`deepseek-v4-flash` 配置、显式 Thinking toggle、`reasoning_effort`、JSON Output、响应清理和可测试 failure mapping。

## 2. 非目标

本文不承诺供应商未在总体设计中确认的参数、价格或 SLA，不自动切换其他模型，不依赖 beta strict Tool Calls，不展示/存储原始 Chain of Thought。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Provider Profile | endpoint、model、credential reference 与 transport policy 的版本化配置 |
| Thinking Toggle | 每个请求显式 `on/off`，不继承 SDK/账户默认 |
| JSON Output | provider 受支持的 JSON 模式加本地 strict Schema |
| `reasoning_content` | 供应商可能返回的推理字段；读取后立即丢弃 |
| Normalized Response | 只含 artifact bytes、usage、finish/status 与 provider request ID |

## 4. 数据与接口

`DES-AI-007`：默认 profile 来自已批准总体设计；Base URL/model/credential 均由本地配置装配，文档不把它们解释成不可变官方事实：

```json
{
  "profile_id": "provider.deepseek.v4_flash.v1",
  "provider_kind": "deepseek_compatible",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-flash",
  "credential_ref": "windows_secret.deepseek_api_key",
  "connect_timeout_real_ms": 5000,
  "request_timeout_real_ms": 30000,
  "max_response_bytes": 16384,
  "profile_version": 1
}
```

| Request kind | Thinking | `reasoning_effort` | Prompt ID |
|---|---|---|---|
| ordinary immediate action | explicit `off` | omitted | `resident-action/v1` |
| hourly intent | explicit `off` | omitted | `resident-hourly-intent/v1` |
| daily plan | explicit `on` | `high` | `resident-daily-plan/v1` |
| complex conflict/major event planning | explicit `on` | `high` | owner registered |
| combat turn | explicit `off` | omitted | `resident-combat-turn/v1` |

Provider Port：

```text
generate_json(request: ModelRequestV1, cancellation_token) -> NormalizedModelResponse
probe_profile(profile_id) -> ProviderHealth
classify_provider_error(error) -> ProviderFailure
```

`ModelRequestV1` 必含 `request_id/profile_id/model/prompt_id/messages/json_output_enabled/thinking_enabled/reasoning_effort|null/max_output_tokens/deadline_monotonic_ms/idempotency_key`。

## 5. 规则与不变量

- `RULE-AI-037`：所有请求显式设置 Thinking；普通即时、Hourly 和 combat 为 off，Daily/复杂规划为 on+high。
- `RULE-AI-038`：模型名固定使用配置值 `deepseek-v4-flash`；Domain 不绑定 SDK，改变 profile/model 必须新版本和评测 Gate。
- `RULE-AI-039`：首版以 JSON Output 与本地 strict validator 为正确性边界，不将 beta strict Tool Calls 作为必要条件。
- `RULE-AI-040`：`reasoning_content` 不进入 Normalized Response、日志、Event、Memory、Cache、diagnostic 或 UI；adapter 解析后立即丢弃。
- `RULE-AI-041`：API Key 只从 Secret Provider 在服务器内解析，不进 Client、SQLite、配置文件或请求日志。
- `RULE-AI-042`：provider HTTP success 不是 Proposal success；空、截断、非法 JSON、拒绝、超时、限流分别分类。

## 6. 正常流程

Router 依据 artifact kind 选择 profile/policy；Composer 生成版本化 messages；adapter 显式发送 JSON/Thinking 设置；response parser 在大小限制内提取 artifact 和 usage，丢弃 reasoning；DOC-AI-004 strict decode；metrics 记录非敏感 metadata。

## 7. 边界情况

供应商忽略 JSON mode、返回 Markdown fence 或同时含 text/reasoning 时只尝试提取协议允许的单 JSON object；model/profile 不匹配拒绝启动或请求；profile endpoint 改为用户兼容代理时仍执行同一安全/Schema contract，不宣称其为官方服务。

## 8. 错误与降级

failure enum 为 `connect_timeout/request_timeout/rate_limited/provider_unavailable/empty_response/response_too_large/invalid_json/schema_invalid/content_refused/config_invalid/cancelled`。只有 transport transient 与 rate limit 可按 DOC-AI-009 重试；格式修复最多一次；其余进入 replan/fallback。

## 9. 安全与性能

只允许 `https` endpoint，开发 FakeProvider 除外；禁止重定向到非配置 host。Header、Key、完整 body 默认不记录。Normal adapter 有连接池但每世界普通 in-flight 仍为 2。

## 10. 验收标准

- 五类 request 的 Thinking/reasoning_effort snapshot 与表一致。
- FakeProvider 能模拟所有 failure，真实 DeepSeek 测试必须显式 opt-in。
- reasoning/key/full Prompt 的 sink audit 为零。
- profile/model/Schema 版本可从一次结果追踪。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-025` | routing matrix 与显式 toggle |
| `TEST-AI-026` | JSON Output + strict local validation |
| `TEST-AI-027` | reasoning_content/key sink negative audit |
| `TEST-AI-028` | provider failure classification |

## 12. 关联文档

- `DOC-AI-008..009`：预算与 request lifecycle
- `DOC-FOUNDATION-002`：ModelProvider Port

---
doc_id: DOC-AI-008
title: Token、缓存与成本控制
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - ai-token-budget
  - model-response-cache
  - local-cost-accounting
depends_on:
  - DOC-AI-002
  - DOC-AI-003
  - DOC-AI-007
requirements:
  - REQ-AI-008
last_updated: 2026-07-26
---

# Token、缓存与成本控制

## 1. 目的

`REQ-AI-008`：为各 cognition kind 设定输入/输出预算、确定性裁剪、缓存键、usage 记账与可解释成本显示，避免秘密缓存、重复调用和失控费用。

## 2. 非目标

本文不硬编码未经验证的供应商价格，不从金额推断游戏时间，不以缓存结果绕过 stale/Domain validation，也不缓存 Chain of Thought。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Token Estimate | 请求前 provider tokenizer/保守 estimator 的预算值 |
| Usage Record | provider 返回或本地估算的 input/output/cache token counts |
| Artifact Cache | 相同安全上下文与版本的模型 artifact bytes |
| Price Profile | 用户可更新、带币种/生效日/来源说明的本地展示配置 |
| Cost Estimate | usage × price profile 的展示值，不参与 Domain 规则 |

## 4. 数据与接口

`DES-AI-008` 默认硬预算：

| Kind | max input tokens | max output tokens | cache TTL |
|---|---:|---:|---:|
| immediate action | 3000 | 700 | 5 RealTime min |
| hourly intent | 4500 | 1000 | 10 RealTime min |
| daily plan | 7000 | 1600 | 当前 game day |
| combat turn | 2500 | 600 | 当前 turn only |

缓存键：

```text
sha256(
 profile_id + model + prompt_id + template_sha256 + artifact_schema_id +
 context_hash + action_catalog_digest + thinking_enabled +
 reasoning_effort|null + max_output_tokens + access_policy_version
)
```

Usage：

```json
{
  "request_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "profile_id": "provider.deepseek.v4_flash.v1",
  "input_tokens": 2450,
  "output_tokens": 312,
  "cache_read_tokens": 0,
  "usage_source": "provider_reported",
  "price_profile_id": null,
  "estimated_cost_minor_unit": null
}
```

## 5. 规则与不变量

- `RULE-AI-043`：超出输入预算先按 DOC-AI-002 确定顺序裁剪；安全/目标信息仍无法容纳则不调用模型。
- `RULE-AI-044`：cache hit 仍必须 strict decode、stale check 和最新 Domain validation；不能重放已提交副作用。
- `RULE-AI-045`：缓存键包含全部行为/访问相关版本与 Context hash；Secret Grant/Revision 改变不复用旧 artifact。
- `RULE-AI-046`：缓存值仅含模型 artifact、非敏感 usage 和版本 metadata；不含完整 Prompt、reasoning、Key 或未授权 projection。
- `RULE-AI-047`：价格缺失/过期时显示 token，不显示伪精确金额；Price Profile 改变不重写历史 usage。
- `RULE-AI-048`：预算按 request/actor/world/day 聚合并可告警，但不得因成本限制跳过 emergency local fallback。

## 6. 正常流程

估算 token→裁剪→计算 cache key→命中则返回 immutable artifact copy；未命中时调用 provider→校验响应→写受限 cache→追加 usage；UI 通过脱敏汇总读取 Token、请求数、cache hit 和可选估算成本。

## 7. 边界情况

provider 不返回 usage 时 `usage_source=estimated`；stream 中断不记录成功 cache；同 Context 但新 Prompt/Schema/Grant 不命中；Daily cache 跨 game day 失效；战斗 cache 绑定 encounter/turn，不跨 turn。

## 8. 错误与降级

cache 损坏/Schema hash mismatch 视 miss 并删除该 entry；tokenizer 不可用采用保守字符估计并预留 20%；达到用户 request/token cap 时普通 ambient 延迟，critical 进入 Utility fallback，不无限排队。

## 9. 安全与性能

默认内存 LRU 256 entries/32 MiB，持久 cache 首版关闭；如启用必须 DPAPI 保护并受同样 purge policy。Usage 不含文本。cache lookup 不在 World Tick critical section。

## 10. 验收标准

- 四类预算端点与 deterministic truncation 可重放。
- 任一安全/Prompt/Schema/model/version 改变均 cache miss。
- cache hit 不重复提交 command/event。
- 无 Price Profile 时 UI 明确显示“金额不可用”而非 0。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-029` | token budget/truncation boundaries |
| `TEST-AI-030` | cache-key mutation matrix |
| `TEST-AI-031` | hit 后 stale/domain revalidation |
| `TEST-AI-032` | usage/price missing/estimated display |

## 12. 关联文档

- `DOC-AI-002`：Context 裁剪
- `DOC-AI-007`：model/profile metadata
- `DOC-AI-012`：Token/latency 评测

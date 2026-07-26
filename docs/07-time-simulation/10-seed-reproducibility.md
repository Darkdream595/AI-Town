---
doc_id: DOC-TIME-010
title: Seed 随机流与可重放性
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - deterministic-seed-streams
  - random-draw-sequencing
  - recorded-ai-replay-time-contract
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-003
  - DOC-TIME-009
requirements:
  - REQ-TIME-010
last_updated: 2026-07-26
---

# Seed 随机流与可重放性

## 1. 目的

`REQ-TIME-010`：定义 128-bit world Seed 的命名随机流、sequence 持久化、无偏整数抽样、版本升级和 AI response recorded replay，使规则随机及历史模型结果可在存档、测试和恢复中重现。

## 2. 非目标

本文不决定天气概率、战斗掉落或居民选择权重；业务 owner 申请命名 stream 并解释抽样结果。TIME 不保存或展示模型 Chain of Thought。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| World Seed | 创建后不可变的 16 bytes 值，显示为 32 个 lowercase hex |
| Stream ID | Stable Catalog ID，描述随机用途，例如 `time.weather` |
| Scope ID | world/entity/encounter 的稳定或运行时 ID，用于隔离同一用途 |
| Draw Sequence | 每 `(stream_id,scope_id)` 从 0 递增的 uint64 raw block 序号 |
| Algorithm Version | 随机 derivation 算法版本；旧 timeline 固定原版本 |
| AI Replay Record | 固定模型输入引用、版本、验证输出与结果 hash 的非 Chain-of-Thought 记录 |

## 4. 规则与不变量

- `RULE-TIME-055`：world Seed 创建后不可变；所有规则随机必须显式提供 `stream_id/scope_id/draw_sequence`，禁止使用进程全局 random 或系统时间。
- `RULE-TIME-056`：v1 `stream_key = HMAC-SHA256(world_seed, UTF8("ai-town/v1\0" + stream_id + "\0" + scope_id))`；raw block 为 `HMAC-SHA256(stream_key, UTF8("draw\0") + uint64_be(sequence))`。
- `RULE-TIME-057`：每消费一个 raw block，sequence 在同一结果事务中递增一次；事务回滚不消耗 sequence。
- `RULE-TIME-058`：bounded integer 使用 rejection sampling，禁止直接 modulo bias；拒绝的 raw block仍算已消费并提交在同一 draw result 中。
- `RULE-TIME-059`：不同 stream/scope 的结果不得依赖彼此调用顺序；新增随机功能必须登记新 Stream ID，不复用旧语义。
- `RULE-TIME-060`：历史 AI replay 必须优先使用 recorded validated output，不重新请求模型替代；record 不含 `reasoning_content`、Secret 或原始未过滤 DecisionContext。

## 5. 数据与接口

`DES-TIME-010`：

```json
{
  "schema_version": 1,
  "algorithm_version": "hmac_sha256_v1",
  "world_seed_hex": "0123456789abcdeffedcba9876543210",
  "stream_id": "time.weather",
  "scope_id": "world",
  "next_draw_sequence": 1,
  "last_committed_revision": 1205
}
```

固定 test vector：

```text
seed_hex: 0123456789abcdeffedcba9876543210
stream_id: time.weather
scope_id: world
sequence: 0
stream_key_hex: 67f681f7d39d24580768808d033be6ffd0cd3eb661ddaab200ca184bc1073b5f
raw_block_hex: c7801dd6c40f8ef4f422b58c1360dbe8afeb3a2f53c9428d3061b7fff71885b8
```

AI Replay Record 至少包含：

```json
{
  "schema_version": 1,
  "request_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "observed_revision": 1204,
  "observed_game_time": 1830,
  "context_hash": "b7e5c1dc6f7b8ad55743f72e15f59c680bbf1f27f47c18d7dc725410c3445af7",
  "prompt_id": "resident-action/v1",
  "model_id": "deepseek-v4-flash",
  "request_parameters_hash": "e0ff1ee7597d4ea08152590f49f54768b554471c2317a8346d15defb17cc1234",
  "validated_output": {"action": "wait", "parameters": {}},
  "response_hash": "41d1f7d0383a30c9a43aa29bb8d980d650cc9bca91bcb0e968096dfdea4741f4",
  "outcome": "accepted_for_revalidation"
}
```

接口：

```text
draw_uint32(stream_id, scope_id, expected_sequence) -> RandomDraw
draw_bounded_uint32(stream_id, scope_id, upper_exclusive) -> RandomDrawSet
record_ai_response(replay_record) -> ReplayRecordResult
load_recorded_ai_response(request_id, input_hashes) -> ValidatedOutput | mismatch
```

## 6. 正常流程

1. 业务 owner 声明 Stream ID、scope 和所需分布。
2. TIME 读取已提交 next sequence，派生 raw block。
3. 业务 owner 使用规定转换形成候选结果。
4. 状态变化、Draw Record、sequence 增长和 DomainEvent 原子提交。
5. 测试/恢复按记录 sequence 重算并比较 hash。
6. AI 历史重放读取 validated output，再走最新状态校验或历史 replay validator，不访问网络。

## 7. 边界情况

- bounded range 为 1 时仍可返回 0，不必消费 raw block；该优化必须版本固定并记录 draw_count=0。
- sequence 达 uint64 max 时停止该 stream 并返回 overflow，不回绕。
- Algorithm Version 升级不能改变已有 timeline；新 world 才可默认新版本。
- AI replay 的 context/prompt/model hash 不匹配时返回 mismatch，禁止拿“相似”记录替代。
- 模型响应被拒绝或 fallback 仍保留结果分类，但未提交 Action 不成为世界事实。

## 8. 错误与降级

未知 Stream ID、sequence mismatch、Seed Hash 不符或 replay hash mismatch 返回 `TIME_REPLAY_MISMATCH` 并停止相关写入。随机服务不可用时不能改用非确定随机；可选择确定性安全 Action 或暂停 owner 流程。

## 9. 安全与性能

World Seed 不是授权 Secret，但公开导出需明确提示其可预测性。HMAC key/material 生命周期仅在内存。AI replay 输出经过 Schema/ACL 过滤，禁止存 `reasoning_content`；hash 不能作为原文泄露的替代许可。

## 10. 验收标准

- 固定 test vector 在 Python/TypeScript/PowerShell 实现逐字节一致。
- 跨 stream 调用重排不改变各自输出。
- rollback、crash、Snapshot reload 不多消耗或少消耗 sequence。
- bounded sampling 通过分布与无 modulo bias 测试。
- AI replay 在模型离线时复现同一 validated output 且无网络请求。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-028` | `RULE-TIME-055..057` vector/sequence/transaction |
| `TEST-TIME-029` | `RULE-TIME-058..059` rejection 与 stream independence |
| `TEST-TIME-030` | `RULE-TIME-060` AI replay、hash mismatch 与 CoT 零存储 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：世界 Seed 不变量
- `DOC-TIME-009`：sequence 恢复
- `DOC-AI-003`：Prompt version
- `DOC-AI-004`：validated output Schema
- `DOC-RELEASE-003`：Draw/Replay record 持久化

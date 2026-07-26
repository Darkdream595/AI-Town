---
doc_id: DOC-DIALOGUE-003
title: 对话上下文构建
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-context-assembly
  - utterance-history-window
depends_on:
  - DOC-FOUNDATION-006
  - DOC-DIALOGUE-001
  - DOC-AI-002
  - DOC-AI-003
  - DOC-MEMORY-003
  - DOC-MEMORY-009
requirements:
  - REQ-DIALOGUE-003
last_updated: 2026-07-26
---

# 对话上下文构建

## 1. 目的

`REQ-DIALOGUE-003`：定义居民响应一次对话时后端如何组装 Dialogue Context——会话快照、utterance 历史窗口、检索记忆、关系投影与承诺——并保证秘密过滤在 Prompt 构建之前全部完成，每位居民只见到自己主观有权见到的世界。

## 2. 非目标

本文不定义主观可见性与 Visibility Proof 的通用规则（`DOC-AI-002` 是 canonical owner）、Prompt 分层与模板（`DOC-AI-003`）、记忆检索打分（`DOC-MEMORY-003`）或秘密访问判定（`DOC-MEMORY-009`）。本文只拥有「对话场景下这些输入如何拼装成 DialogueContext」这一层。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Dialogue Context | 为某一位响应居民组装的不可变上下文快照，随模型请求携带 observed Revision |
| Utterance History Window | 送入上下文的最近已提交 utterance 有界序列 |
| History Summary | 超出窗口的更早 utterance 的摘要文本，由服务器生成并标记为摘要 |
| Speaker Projection | 对话对方在响应居民视角下的投影：外观、公开身份、本居民对其的记忆与关系 |
| Redaction Marker | 被过滤内容留下的 `unknown_or_redacted` 占位标记（语义随 `RULE-AI-011`） |

## 4. 规则与不变量

- `RULE-DIALOGUE-013`：Dialogue Context 只能由服务器 Context Builder 在最新已提交 Revision 上组装；Client 文本、模型历史输出与未提交 command 一律不得进入。
- `RULE-DIALOGUE-014`：所有记忆、关系、秘密条目在进入 Dialogue Context 之前必须已有 AccessDecision allow（`RULE-MEMORY-071`、`RULE-MEMORY-077`）；Prompt 构建阶段不做任何补充过滤，收到未判定条目即整份 context rejected。
- `RULE-DIALOGUE-015`：Dialogue Context 对每位响应居民分别构建且互不共享；同一 Conversation 中两名居民的 context 允许且预期不一致（主观世界，`RULE-AI-007..010`）。
- `RULE-DIALOGUE-016`：Utterance History Window 上限 `12` 条已提交 utterance；更早内容只能以 History Summary 形式进入，摘要必须显式标记 `is_summary=true`，不得伪装成原话。
- `RULE-DIALOGUE-017`：对方的内心状态、Need 数值、秘密、Inventory 与余额不进入 Speaker Projection；只允许公开外观、公开身份、以及响应居民自己的 Memory/Belief/关系边投影（与 `RULE-AI-012` 一致）。
- `RULE-DIALOGUE-018`：每次模型请求持久化 `context_hash`、prompt ID（`resident-dialogue/v1`）与 observed Revision；不持久化完整 Prompt 或 `reasoning_content`（`RULE-AI-018`）。

## 5. 数据与接口

`DES-DIALOGUE-003`：`DialogueContextV1` 组装结果（示例为响应居民视角）。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "responder_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "observed_revision": 128,
  "game_time": 5410,
  "utterance_history": [
    {"utterance_index": 2, "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRU", "text": "你最近还去矿上吗？", "is_summary": false},
    {"utterance_index": 3, "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRV", "text": "去得少了，腿伤还没好利索。", "is_summary": false}
  ],
  "history_summary": {"covered_utterances": [0, 1], "text": "双方寒暄并互相问候了家人。", "is_summary": true},
  "speaker_projections": [
    {
      "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRU",
      "public_identity": {"display_name": "旅人", "profession_public": "unknown_or_redacted"},
      "relationship_edge": {"affection": 12, "trust": 8, "fear": 0, "respect": 20, "intimacy": 3},
      "impression_memory_ids": ["01K1AB2CD3EF4GH5JK6MNP7QS1"]
    }
  ],
  "retrieved_memory_ids": ["01K1AB2CD3EF4GH5JK6MNP7QS1", "01K1AB2CD3EF4GH5JK6MNP7QS2"],
  "access_decision_ids": ["01K1AB2CD3EF4GH5JK6MNP7QS3"],
  "commitments": [{"commitment_id": "01K1AB2CD3EF4GH5JK6MNP7QS4", "summary": "答应本周内还铁匠 3 银冠", "deadline_game_time": 12960}],
  "context_hash": "c3d1a58c0f4b7e9a2d6f8b1c4e7a9d2f6b8c1e4a7d9f2b6c8e1a4d7f9b2c6e8a"
}
```

组装接口：`build_dialogue_context(conversation_id, responder_id) -> DialogueContextV1`。输入来源固定为：DIALOGUE 自己的 Conversation 投影，AI 的 Decision Context 管道（`DOC-AI-002`），MEMORY 的检索与访问判定（`DOC-MEMORY-003`、`DOC-MEMORY-009`）。retrieved memory 的 payload 文本在 Prompt 层展开，本投影只携带 ID 与已授权摘要。

## 6. 正常流程

1. Conversation 进入 `awaiting_model`，Context Builder 以最新 Revision 读取 Conversation 投影与 utterance 游标。
2. 向 MEMORY 请求「以本次会话主题与参与者为线索」的检索，得到已通过 AccessDecision 的记忆集合。
3. 组装 utterance 窗口、History Summary、Speaker Projection、关系边与承诺，计算 `context_hash`。
4. 交给 Prompt 层（`resident-dialogue/v1`）渲染模板并入队模型请求（`DOC-AI-009`）。

## 7. 边界情况

- 中途加入的参与者：其 context 的 utterance 窗口从加入事件起算，加入前内容不进入窗口也不进入摘要（`RULE-DIALOGUE-012`）。
- 会话极短（不足 12 条）：无 History Summary，`history_summary` 字段为 null 序列化时省略或显式 null，Schema 两者等价。
- 响应期间世界 Revision 前进：context 不重建；返回结果按 `RULE-AI-054` 在最新 Revision 重新校验。
- 检索结果为空：合法，居民以"不了解"的姿态响应，不得为凑内容注入未授权数据。

## 8. 错误与降级

- MEMORY 检索超时：使用仅含 utterance 窗口与关系边的最小 context 降级组装，并记录 `context_degraded=true`；秘密过滤规则不因降级放宽。
- AccessDecision 缺失或 policy version 不匹配：整份 context rejected（fail closed），会话按 `DOC-DIALOGUE-001` 的模型失败路径处理。
- `context_hash` 与请求快照不一致：请求作废重建，不允许带错误 hash 入队。

## 9. 安全与性能

- 秘密边界在组装期终结：Prompt 层与模型永远接触不到被拒条目，注入文本无法追溯出被过滤内容（配合 `DOC-DIALOGUE-011`）。
- 单次组装的记忆条目上限 `16`、utterance 窗口上限 `12`、总 token 预算受 `DOC-AI-008` 约束；裁剪按 `RULE-AI-011` 只删低优先项。
- context 为不可变快照，组装为一次只读事务，不持锁等待模型。

## 10. 验收标准

- 同一 Conversation 两名居民的 context 在秘密与记忆维度可验证地不同。
- 任意 fixture 中未授权秘密不出现在 context 序列化结果的任何字段（含摘要）。
- 窗口滚动、摘要标记、中途加入截断均有确定性结果。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-005` | `RULE-DIALOGUE-013..015` 服务器组装、预过滤完成性、主观隔离 |
| `TEST-DIALOGUE-006` | `RULE-DIALOGUE-016..018` 窗口/摘要边界、投影最小化、hash 与持久化边界 |

## 12. 关联文档

- `DOC-DIALOGUE-001`（状态机）、`DOC-DIALOGUE-005`（响应 Schema）、`DOC-DIALOGUE-011`（安全边界）
- `DOC-AI-002`（主观可见性 canonical）、`DOC-AI-003`（Prompt 分层）、`DOC-AI-008`（token 预算）
- `DOC-MEMORY-003`（检索）、`DOC-MEMORY-009`（秘密访问）

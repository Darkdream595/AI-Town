---
doc_id: DOC-DIALOGUE-005
title: Speech Act 模型与响应 Schema
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - speech-act-schema
  - dialogue-response-decode
depends_on:
  - DOC-FOUNDATION-006
  - DOC-DIALOGUE-001
  - DOC-DIALOGUE-003
  - DOC-DIALOGUE-004
  - DOC-AI-004
  - DOC-MEMORY-002
requirements:
  - REQ-DIALOGUE-005
last_updated: 2026-07-26
---

# Speech Act 模型与响应 Schema

## 1. 目的

`REQ-DIALOGUE-005`：定义居民对话响应的唯一 strict JSON Schema `SpeechActV1`——包含言语行为类型、话语文本、情绪、承诺提议、协商提议与结束标志——以及从模型原始输出到已提交 utterance 的解码与校验管道。拒绝、说谎、协商与承诺都以显式 Speech Act 类型表达，而不是让模型自由改写世界。

## 2. 非目标

本文不定义 `ActionProposalV1`（`DOC-AI-004`，其 `talk` action 负责"发起对话"这一动作，本文负责"会话内的响应内容"）、意图边界（`DOC-DIALOGUE-004`）、情绪呈现（`DOC-DIALOGUE-006`）或 Commitment 存储（MEMORY）。Schema 通过不等于话语合法或承诺成立。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Speech Act | 一次结构化的言语行为：类型 + 文本 + 附加提议，是居民响应的唯一输出形态 |
| Strict Decode | required、type、enum、maxLength 与 `additionalProperties=false` 全部通过 |
| Deception Intent | `lie` 类型携带的说谎意图标记，仅服务器与说话者自身记忆可见，不进入他人渲染或 context |
| Commitment Offer | Speech Act 内的承诺提议载荷，经 `RULE-DIALOGUE-023` 确认后才成为 Commitment |
| Negotiation Offer | 引用 ECON Quote 的协商载荷，价格结算权始终在 ECON |

## 4. 规则与不变量

- `RULE-DIALOGUE-025`：居民会话响应必须是单个 `SpeechActV1` strict JSON；解码失败按 `DOC-AI-009` 的受限重试与失败路径处理，绝不把自由文本直接当作 utterance 提交。
- `RULE-DIALOGUE-026`：`speech_act_type` 为封闭枚举 `greet / inform / ask / request / promise / refuse / lie / negotiate / comfort / warn / apologize / farewell`；未知类型 fail closed。类型只描述言语行为，不授予任何规则效果。
- `RULE-DIALOGUE-027`：`refuse` 是一等合法结果：居民可基于关系、秘密权限、性格或情绪拒绝回答、拒绝交易或拒绝继续对话，系统不得为“推进剧情”强制居民合作。
- `RULE-DIALOGUE-028`：`lie` 的 Deception Intent 只写入说话者自身记忆 provenance 与服务器审计；渲染文本、其他参与者 context 与 MEMORY 的 testimony 管道均不携带真伪标记（听者自行判断，`RULE-MEMORY-044` 语义下的主观解释）。
- `RULE-DIALOGUE-029`：`commitment_offer` 与 `negotiation_offer` 只能引用 context 中可见的实体与 ECON 已报 Quote；引用不可见实体、伪造价格或超出居民处置权的提议在提交校验时整体拒绝，话语文本可提交但载荷作废并记录 reason。
- `RULE-DIALOGUE-030`：Speech Act 提交是原子事务：utterance 追加、`dialogue.speech_act_committed/v1` DomainEvent、幂等结果同事务落库；提交后才可被渲染、被记忆写入引用（`RULE-MEMORY-009`）。
- `RULE-DIALOGUE-031`：`utterance_text` 上限 `280` 字符、纯文本；解码后服务器强制执行 `DOC-DIALOGUE-010` 渲染策略与 `DOC-DIALOGUE-011` 内容边界，二者失败视为响应失败而非"部分提交"。

## 5. 数据与接口

`DES-DIALOGUE-005`：注册 `$id=schema://ai-town/dialogue/speech-act/v1`，本 code block 是唯一机器提取真源。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/dialogue/speech-act/v1",
  "type": "object",
  "required": ["speech_act_type", "utterance_text", "emotion", "tone", "addressed_entity_id", "commitment_offer", "negotiation_offer", "end_conversation"],
  "properties": {
    "speech_act_type": {"enum": ["greet", "inform", "ask", "request", "promise", "refuse", "lie", "negotiate", "comfort", "warn", "apologize", "farewell"]},
    "utterance_text": {"type": "string", "minLength": 1, "maxLength": 280},
    "emotion": {"enum": ["calm", "joy", "sadness", "anger", "fear", "anxiety", "disgust", "hope"]},
    "tone": {"enum": ["warm", "neutral", "cold", "formal", "playful", "hostile"]},
    "addressed_entity_id": {"oneOf": [{"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"}, {"type": "null"}]},
    "commitment_offer": {
      "oneOf": [
        {
          "type": "object",
          "required": ["summary", "deadline_game_minutes_from_now"],
          "properties": {
            "summary": {"type": "string", "minLength": 1, "maxLength": 120},
            "deadline_game_minutes_from_now": {"type": "integer", "minimum": 30, "maximum": 43200}
          },
          "additionalProperties": false
        },
        {"type": "null"}
      ]
    },
    "negotiation_offer": {
      "oneOf": [
        {
          "type": "object",
          "required": ["quote_id", "stance"],
          "properties": {
            "quote_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
            "stance": {"enum": ["accept", "counter", "decline"]}
          },
          "additionalProperties": false
        },
        {"type": "null"}
      ]
    },
    "end_conversation": {"type": "boolean"}
  },
  "additionalProperties": false
}
```

管道接口：`decode_speech_act(model_artifact) -> SpeechActV1 | DecodeError`，`commit_speech_act(conversation_id, responder_id, speech_act, expected_revision) -> CommitResult`。模型不提供可信 `conversation_id / responder_id / revision`，全部由 Server Envelope 追加（与 `DOC-AI-004` 同构）。`negotiate` 的 counter 价必须由 ECON 生成新 Quote，Speech Act 只引用 `quote_id`，不携带自由价格数字。

## 6. 正常流程

1. `awaiting_model` 下模型返回 artifact，Strict Decode 得到 `SpeechActV1`。
2. 语义校验：类型与载荷一致性（`promise` 才可带 `commitment_offer`、`negotiate` 才可带 `negotiation_offer`）、引用可见性、内容边界。
3. `commit_speech_act` 原子提交，Conversation 按 `DOC-DIALOGUE-001` 迁移（`end_conversation=true` 时走 `dialogue.end`，reason `completed`）。
4. 提交事件驱动渲染（立绘/情绪提示按 `DOC-DIALOGUE-006`）与记忆写入（`DOC-DIALOGUE-009`）。

## 7. 边界情况

- `promise` 无 `commitment_offer`（口头空话）：合法，仅 Speech Fact，无 Commitment Candidate。
- 非 `promise/negotiate` 类型携带对应 offer：语义校验失败，整个响应按解码失败处理（防止“类型伪装”）。
- `lie` 且带 `commitment_offer`：允许——居民可作虚假承诺；Commitment 一经确认仍按真实承诺追踪履约，违约后果由 MEMORY/关系承担。
- `farewell` 且 `end_conversation=false`：合法（客套告别但等待对方回应）；反之 `end_conversation=true` 的任何类型都触发结束流程。
- `addressed_entity_id` 指向非参与者：语义校验失败（群组内点名规则见 `DOC-DIALOGUE-008`）。

## 8. 错误与降级

- Strict Decode 失败、空响应或超时：按 `RULE-AI-051..053` 受限重试；耗尽后由 Utility fallback（`DOC-AI-011`）产出模板化 `farewell` 或 `refuse` 类 Speech Act（固定文案目录，不调模型），保证会话可关闭。
- 语义校验失败：不重试模型（内容层失败），直接走 fallback 路径并记录 reason code。
- 提交时 Revision 冲突：以最新 Revision 重新校验一次引用可见性，仍失败则丢弃并 fallback。

## 9. 安全与性能

- Schema `additionalProperties=false` 使模型无法夹带工具调用、系统字段或越权载荷；一切数值结算字段（价格、数量、伤害）在 Schema 中不存在。
- Deception Intent 的存储与日志遵循 `RULE-MEMORY-078` 式脱敏：只留类型与 reason code，不复制话语内容到普通日志。
- 单次响应解码与校验为 O(1)，无网络依赖（Quote 可见性在 context 组装期已快照）。

## 10. 验收标准

- 12 种类型、全部 oneOf 分支与非法组合的 decode fixture 全通过/全拒绝无歧义。
- 说谎路径：听者 context 与渲染中无真伪标记；说话者记忆 provenance 有标记。
- 越权 offer fixture：话语可提交、载荷作废、零资产变化。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-009` | `RULE-DIALOGUE-025..028` Strict Decode、类型封闭、拒绝与说谎语义 |
| `TEST-DIALOGUE-010` | `RULE-DIALOGUE-029..031` offer 引用校验、原子提交、文本上限与渲染策略衔接 |

## 12. 关联文档

- `DOC-DIALOGUE-003`（context 输入）、`DOC-DIALOGUE-004`（意图边界）、`DOC-DIALOGUE-006`（情绪呈现）、`DOC-DIALOGUE-008`（群组点名）
- `DOC-AI-004`（ActionProposal 与 Server Envelope 模式）、`DOC-AI-011`（fallback）、`DOC-MEMORY-002`（写入资格）、`DOC-ECON-008`（Quote 定价）

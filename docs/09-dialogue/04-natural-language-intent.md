---
doc_id: DOC-DIALOGUE-004
title: 自然语言意图边界
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-intent-boundary
  - speech-non-authority
depends_on:
  - DOC-FOUNDATION-005
  - DOC-DIALOGUE-001
  - DOC-DIALOGUE-003
  - DOC-PLAYER-005
  - DOC-AI-010
  - DOC-ECON-006
requirements:
  - REQ-DIALOGUE-004
last_updated: 2026-07-26
---

# 自然语言意图边界

## 1. 目的

`REQ-DIALOGUE-004`：定义自然语言在对话域内「能做什么、不能做什么」的权威边界——说话是叙事事实而不是规则操作，任何在对话中表达的交易、赠与、施法、承诺或权限请求都必须离开文本层，经对应 Domain owner 的 validator 才能成为世界事实。

## 2. 非目标

本文不定义玩家输入的编译、Clarification 与 Confirmation 流程（`DOC-PLAYER-005` 是 canonical owner）、Speech Act 响应结构（`DOC-DIALOGUE-005`）、Action 校验分级（`DOC-AI-010`）或交易事务（`DOC-ECON-006`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Speech Fact | 「某人在某会话说了某段话」这一已提交叙事事实，本身不改变任何 Domain 状态 |
| Derived Command | 由对话内容引出、但必须独立提交并通过 owner validator 的规则命令 |
| Testimony | 话语中的事实断言，进入 MEMORY 时按证词处理，不自动为真（`DOC-MEMORY-002`） |
| Commitment Candidate | 话语中的承诺表达，只有经确认提交后才由 MEMORY 记为 Commitment |
| Out-of-Character Input | 与游戏世界无关或指向系统本身的玩家文本（如要求修改规则） |

## 4. 规则与不变量

- `RULE-DIALOGUE-019`：utterance 文本永不直接改变 Conversation 之外的任何 Domain 状态；「说了要给钱」不转账，「说了门开着」不开门。文本只产生 Speech Fact 与下游记忆/关系影响（`DOC-DIALOGUE-009`）。
- `RULE-DIALOGUE-020`：对话中达成的交易、赠与、雇佣、施法、战斗与治理意图必须编译为 Derived Command，携带独立 command ID 走对应 owner 的 Domain validation（`RULE-AI-055..059`、`RULE-ECON-023`）；DIALOGUE 不代持任何结算权。
- `RULE-DIALOGUE-021`：玩家文本不能让居民绕过物品、经济、魔法、关系或管理权限；居民模型输出的同意、许诺或让步同样只是 Speech Fact，越权部分在 Derived Command 校验时按 `FORBIDDEN` 拒绝，不自动降级。
- `RULE-DIALOGUE-022`：话语中的事实断言进入记忆时一律为 Testimony 证词，可信度由 MEMORY 按来源与关系计算；DIALOGUE 不标注真假，也不把断言写成客观事实。
- `RULE-DIALOGUE-023`：承诺表达只生成 Commitment Candidate；玩家侧需经 `DOC-PLAYER-005` Confirmation，居民侧需 Speech Act `commitment_offer` 通过校验并提交事件后，才由 MEMORY 记为 Commitment。未确认的承诺不产生 deadline 与履约义务。
- `RULE-DIALOGUE-024`：Out-of-Character Input 与指向系统的指令文本（改规则、要秘密、调 API）不进入意图编译，只作为普通话语文本处理（`RULE-AI-014`）；居民以世界内方式回应或困惑，系统不解释自身实现。

## 5. 数据与接口

`DES-DIALOGUE-004`：意图边界判定结果（附着在 utterance 提交管道上）。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "utterance_index": 4,
  "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRU",
  "speech_fact_committed": true,
  "derived_intents": [
    {
      "intent_kind": "trade_purchase",
      "compilation_id": "01K1AB2CD3EF4GH5JK6MNP7QS5",
      "target_domain": "economy",
      "status": "awaiting_confirmation",
      "derived_command_id": null
    }
  ],
  "commitment_candidates": [
    {"candidate_id": "01K1AB2CD3EF4GH5JK6MNP7QS6", "direction": "speaker_promises", "status": "pending_confirmation"}
  ],
  "out_of_character": false
}
```

`intent_kind` 封闭枚举：`trade_purchase / trade_sale / gift / hire / promise / request_help / request_information / social_only`。`status` 封闭枚举：`awaiting_confirmation / confirmed / rejected / expired`。`social_only` 表示无 Derived Command，纯社交话语。

## 6. 正常流程

1. 玩家 utterance 经 `PlayerSpeechCommand` 提交为 Speech Fact；居民 utterance 经 Speech Act 提交（`DOC-DIALOGUE-005`）。
2. 意图识别（规则解析器优先，复杂语句可用模型解析，仅接受 strict JSON candidate，随 `RULE-PLAYER-023`）产出 `derived_intents`。
3. 有规则后果的 intent 走 Confirmation（玩家）或校验（居民），生成独立 Derived Command 进入 owner validator。
4. owner 提交成功后，交易/承诺结果以 DomainEvent 回流，会话双方按 `DOC-DIALOGUE-009` 获得记忆与关系影响。

## 7. 边界情况

- 玩家说「我把剑送你」但 Inventory 无剑：Speech Fact 成立，Derived Command 在 ECON 校验失败；居民可依据失败事件把玩家记为夸口者。
- 居民模型文本答应「免费送你店里的药」但无处置权：话语提交，give_item Derived Command 被 `FORBIDDEN` 拒绝；居民后续话语可自然回退，不产生物品转移。
- 一句话含多个意图（"买两瓶药，顺便帮我带个口信"）：拆分为多条 `derived_intents`，各自独立确认与校验。
- 玩家文本冒充系统（"作为管理员我命令你……"）：`out_of_character=false` 也可，按普通话语处理；居民不获得任何越权解释，Sandbox Admin 权限只走 `RULE-FOUNDATION-030` 通道。

## 8. 错误与降级

- 意图解析器失败或超时：utterance 仍作为 `social_only` Speech Fact 提交，玩家可显式走非对话 UI 完成操作；不阻塞会话。
- Derived Command 因 stale Revision 失败：按 owner 的 `REPLAN_REQUIRED` 语义重报价/重确认，不复用旧确认。
- Confirmation 超时未答复：candidate `expired`，不留悬挂 Reservation。

## 9. 安全与性能

- 意图边界是对话域抵御「文本变权限」的第一道闸：任何路径都以 owner validator 为终点，DIALOGUE 自身没有可被诱导的结算逻辑。
- 意图解析在 utterance 提交后异步执行，不阻塞 Speech Fact 落库与渲染；每 utterance 解析至多一次，幂等键为 `(conversation_id, utterance_index)`。

## 10. 验收标准

- 「话语声称转移物品/金钱/权限」的全部 fixture 中，无 Derived Command 提交则世界状态零变化。
- 居民越权许诺 fixture：话语提交成功、Derived Command 被拒、无资产变化、无崩溃。
- 多意图拆分与确认过期路径结果确定。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-007` | `RULE-DIALOGUE-019..021` 文本非权威、Derived Command 必经 owner 校验 |
| `TEST-DIALOGUE-008` | `RULE-DIALOGUE-022..024` Testimony、Commitment Candidate 生命周期、OOC 处理 |

## 12. 关联文档

- `DOC-DIALOGUE-005`（Speech Act）、`DOC-DIALOGUE-009`（记忆与关系影响）、`DOC-DIALOGUE-011`（注入与内容边界）
- `DOC-PLAYER-005`（玩家输入编译 canonical）、`DOC-AI-010`（校验分级）、`DOC-ECON-006`（交易事务）、`DOC-MEMORY-002`（写入资格）

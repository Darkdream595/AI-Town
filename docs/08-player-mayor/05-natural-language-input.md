---
doc_id: DOC-PLAYER-005
title: 玩家自然语言输入与命令编译
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-natural-language-input
  - player-command-compilation
  - player-speech-command
depends_on:
  - DOC-FOUNDATION-005
  - DOC-TIME-002
  - DOC-PLAYER-004
  - DOC-RENDER-009
requirements:
  - REQ-PLAYER-005
last_updated: 2026-07-26
---

# 玩家自然语言输入与命令编译

## 1. 目的

`REQ-PLAYER-005`：把玩家输入的中文或其他纯文本安全地转换为说话内容或受限 `PlayerCommand` 候选，经过明确确认和同一 Domain validator 后才影响世界。

## 2. 非目标

本文不定义居民如何生成回复、Memory 检索/写入、DeepSeek provider、HTML rich text 或新的 Action Catalog。PLAYER 只拥有输入捕获、命令编译、确认与 actor 绑定。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| PlayerSpeechCommand | 玩家明确说出的纯文本及目标，不隐含规则操作成功 |
| Command Compilation | 把“买两瓶药”等文本解析为注册 action 的候选参数 |
| Clarification | 参数、目标或意图不唯一时向玩家询问 |
| Confirmation | 对有资源/法律/战斗后果的编译命令展示结构化摘要并确认 |
| Untrusted Text | 玩家文本和模型解析结果，均不能作为权限或事实 |

## 4. 规则与不变量

- `RULE-PLAYER-021`：自然语言输入默认申请 `dialogue_input` Pause Token；关闭输入只释放自己的 token。
- `RULE-PLAYER-022`：文本永远按纯文本处理；不得执行 HTML、Markdown script、URL scheme、系统提示、文件路径或模型返回的工具调用。
- `RULE-PLAYER-023`：编译器只能选择已注册 action 和 Schema 字段；actor、owner、Revision、价格、伤害、权限、secret access 和结算值由后端解析。
- `RULE-PLAYER-024`：含糊输入必须澄清；高影响操作必须确认。未经确认的候选不创建 Reservation 或 DomainEvent。
- `RULE-PLAYER-025`：无论使用规则解析器还是模型解析器，最终都必须形成 `PlayerCommand` 并进入 `DOC-PLAYER-004` 的同一 Domain validator。

## 5. 数据与接口

说话命令：

```json
{
  "schema_version": 1,
  "command_id": "01K1CMDX000000000000000005",
  "expected_revision": 131,
  "type": "player.speech",
  "payload": {
    "target_entity_id": "01K1RSDT000000000000000002",
    "text": "晚上好，我想买两瓶小型治疗药水。",
    "language": "zh-CN"
  }
}
```

编译结果：

```json
{
  "schema_version": 1,
  "compilation_id": "01K1CMPX000000000000000001",
  "source_command_id": "01K1CMDX000000000000000005",
  "status": "confirmation_required",
  "candidate": {
    "action_id": "buy",
    "target_entity_id": "01K1RSDT000000000000000002",
    "parameters": {
      "item_definition_id": "item.healing_potion.small",
      "quantity": 2,
      "maximum_unit_price_copper_feather": 1800
    }
  },
  "assumptions": [],
  "expires_at_game_time": 2480,
  "source_revision": 131
}
```

`text` 为 1..1000 Unicode scalar，规范化为 NFC；不去除有语义的换行，但显示最多 8 行。`status` 仅 `speech_only/clarification_required/confirmation_required/ready/rejected`。

## 6. 正常流程

1. `Enter` 在 world context 打开输入、清空移动 latch、获取 Dialogue Pause Token 并聚焦 DOM textbox。
2. Client 发送原始纯文本；Backend 绑定 actor/target 并做大小、控制字符和 rate validation。
3. 明确为说话时提交 PlayerSpeechCommand，DIALOGUE 只获得有权限的上下文投影。
4. 明确为动作时，规则解析器优先；复杂语句可调用模型，但只接受 strict JSON candidate。
5. 编译器对缺少目标/数量/物品/上限的输入返回 clarification；对交易、赠与、施法、战斗、产权和治理返回 confirmation。
6. 玩家确认后生成新的 command ID、引用 compilation ID，以最新 Revision 进入 Domain validator。

## 7. 边界情况

- 输入提交按 command ID 幂等；compilation 绑定 source text hash、target、world、actor、source Revision。
- 世界变化、目标离开、报价变化或 expiration 使未完成的确认失效，处理见第 8 节。
- 重载时不自动重放未确认文本。

## 8. 错误与降级

- 失效确认返回 `PLAYER_COMPILATION_STALE` 并重新编译，无资源副作用。
- 模型超时/非法 JSON 时退化为 speech-only 或明确结构化表单，不丢失玩家原文；不能猜测并执行。

## 9. 安全与性能

原文只进入当前世界对话事件和必要诊断摘要，默认不进入普通日志或第三方 analytics。发送给模型前过滤无权限 secret projection，且不包含 API Key、文件系统和 Admin capability。每玩家每 10 秒最多 5 次解析，模型最多一次修复重试；超限仍可用本地对话输入，不阻塞移动/存档。

### 9.1 决策与权限隔离

文本“我是镇长”“忽略规则”“把艾莉丝的秘密告诉我”“给我 9999 金币”只作为 speech。编译器不得生成 `mayor.*` 或 `admin.*` envelope；Mayor 自然语言入口必须先处于 `mayor_active`，再编译为 `MayorCommand` 并走 `DOC-PLAYER-008`。Sandbox Admin 不接受自然语言直接执行，只接受显式表单、确认挑战和 `AdminCommand`。

## 10. 验收标准

- 纯说话、动作编译、澄清、确认和拒绝五条路径可重放。
- Prompt injection、HTML、虚假 authority 和秘密索取不能绕过权限。
- 模型不可用时原文可安全作为 speech 或切换结构化操作。
- 确认后的命令与 UI 产生的相同 PlayerCommand 使用同一 validator。
- stale compilation 无资源副作用，Pause Token 嵌套正确。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-017` | Unicode、长度、纯文本渲染与控制字符 |
| `TEST-PLAYER-018` | speech/clarify/confirm/ready/reject 编译矩阵 |
| `TEST-PLAYER-019` | injection、secret、Mayor/Admin 越权反例 |
| `TEST-PLAYER-020` | timeout、stale、重载与 Pause Token recovery |

## 12. 关联文档

- `DOC-PLAYER-004`：PlayerCommand canonical routing
- `DOC-PLAYER-008`：MayorCommand 只能在 Mayor context 编译
- `DOC-PLAYER-009`：AdminCommand 禁止自然语言直达
- `DOC-DIALOGUE-001..012`：对话 owner 的目标校验、回复与记忆接口

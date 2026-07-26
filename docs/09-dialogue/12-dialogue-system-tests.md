---
doc_id: DOC-DIALOGUE-012
title: 对话系统测试
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-test-matrix
  - dialogue-e2e-scenarios
depends_on:
  - DOC-DIALOGUE-001
  - DOC-DIALOGUE-002
  - DOC-DIALOGUE-003
  - DOC-DIALOGUE-004
  - DOC-DIALOGUE-005
  - DOC-DIALOGUE-006
  - DOC-DIALOGUE-007
  - DOC-DIALOGUE-008
  - DOC-DIALOGUE-009
  - DOC-DIALOGUE-010
  - DOC-DIALOGUE-011
requirements:
  - REQ-DIALOGUE-012
last_updated: 2026-07-26
---

# 对话系统测试

## 1. 目的

`REQ-DIALOGUE-012`：给出可直接转为自动化测试的对话域测试矩阵、场景 fixture 格式、故障注入点与浏览器 E2E 场景，覆盖 `TEST-DIALOGUE-001..026`，并以「任何对话路径不得绕过 Domain Validation 或秘密访问控制」为总验收不变量。

## 2. 非目标

不替代 AI/MEMORY/TIME/ECON/PLAYER 的 owner 测试；不调用真实 DeepSeek（模型一律以录制响应或确定性 stub 替身）；不以人工阅读代替必须自动化的不变量、幂等与泄漏检查。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Model Stub | 按 `(prompt_id, context_hash)` 返回预录 `SpeechActV1` 或注入故障的模型替身 |
| Bypass Probe | 试图不经 owner validator 或 AccessDecision 达成状态变化/信息获取的探针用例 |
| Golden Transcript | 固定 Seed 与 stub 下预期的完整 utterance 与事件序列 |
| E2E Scenario | 浏览器驱动的端到端场景：真实前端 + 真实后端 + Model Stub |

## 4. 规则与不变量

- `RULE-DIALOGUE-072`：`REQ-DIALOGUE-001..012` 每条至少映射一个 Test ID（映射见第 11 节）；所有测试固定 Seed、输入 Revision、Model Stub 序列与 Golden Transcript，同输入同结果。
- `RULE-DIALOGUE-073`：Bypass Probe 是发布 Gate：每个版本必须证明——(a) 绕过 owner validator 的状态变化为 0（探针直接调 DIALOGUE 内部口试图转移物品/金钱/权限）；(b) 绕过 AccessDecision 的秘密出现次数为 0（Secret Leakage Oracle 扫描全部 context、Prompt 快照、Speech Act、渲染帧与日志）。
- `RULE-DIALOGUE-074`：故障注入必须覆盖四个边界：模型返回前、Speech Act 提交事务中、pause token 释放前、Reservation 释放前；每处断言无部分提交、无资源泄漏、Revision 不增长（失败时）。
- `RULE-DIALOGUE-075`：E2E 场景在真实浏览器执行（对齐总体设计的 E2E 清单），仅模型层用 stub；E2E 断言 DOM 层面文本以纯文本节点渲染（`RULE-DIALOGUE-059` 的端到端验证）。

## 5. 数据与接口

`DES-DIALOGUE-012`：统一场景 Schema（与 `DOC-RESIDENT-012` harness 同构，扩展对话字段）。

```json
{
  "scenario_id": "dialogue.lifecycle.pause_token_round_trip",
  "seed": 20260726,
  "initial_revision": 200,
  "given": {
    "world_fixture": "fixture.town.two_residents_close",
    "conversation": null,
    "model_stub_responses": [
      {"prompt_id": "resident-dialogue/v1", "sequence": 0, "artifact_kind": "valid_speech_act", "speech_act_type": "greet"}
    ]
  },
  "when": [
    {"command_id": "01K1AB2CD3EF4GH5JK6MNP7QU1", "type": "dialogue.start_conversation", "initiator_id": "01K1AB2CD3EF4GH5JK6MNP7QRU", "target_id": "01K1AB2CD3EF4GH5JK6MNP7QRV", "expected_revision": 200},
    {"command_id": "01K1AB2CD3EF4GH5JK6MNP7QU2", "type": "dialogue.submit_player_speech", "text": "你好！", "expected_revision": 201}
  ],
  "then": {
    "conversation_state": "awaiting_player",
    "utterance_count": 2,
    "pause_token_leaked": false,
    "attention_reservation_leaked": false,
    "secret_leak_hits": 0,
    "bypass_state_changes": 0,
    "golden_event_sequence": ["dialogue.conversation_state_changed/v1", "dialogue.speech_act_committed/v1", "dialogue.speech_act_committed/v1", "dialogue.conversation_state_changed/v1"],
    "final_revision": 204
  }
}
```

Harness 必须支持：`apply_command`、`advance_game_time`、`advance_world_tick`、`inject_model_failure`（超时/非法 JSON/空响应/迟到）、`inject_port_failure`（MAP 遮挡查询、MEMORY 检索、内容分类器）、`save_reload`、`assert_invariants`、`run_secret_leak_oracle`、`run_bypass_probes`。`artifact_kind` 封闭枚举：`valid_speech_act / invalid_json / schema_violation / oversize_text / forbidden_content / late_arrival / empty`。

## 6. 正常流程

1. Unit/Property：状态机穷举、Schema decode、映射表、轮次调度、Sanitized Render。
2. Contract：DIALOGUE 与 TIME（pause token）、AI（请求/取消）、MEMORY（事件消费）、ECON（Derived Command）的 Fake Port 契约测试。
3. Integration：真实后端组合 + Model Stub，跑 Golden Transcript 场景与故障注入。
4. Safety Regression：`DOC-DIALOGUE-011` fixture 全量 + Bypass Probe + Secret Leakage Oracle。
5. E2E：浏览器场景（见第 10 节清单）。
6. 每阶段 save/reload 并重放最后命令，验证恢复一致性。

## 7. 边界情况

- Model Stub 的 `late_arrival`：响应在会话已 `interrupted/ended` 后到达，断言 0 条幽灵 utterance。
- save/reload 发生在 `awaiting_model` 中：恢复后在途请求视为丢失，走超时路径而非重复提交。
- 高倍速（4×）下的群聊场景：轮次与宽限期以 GameTime 计量，断言结果与 1× 完全一致。
- 重复 command ID 不同 payload：idempotency conflict，不执行第二 payload。
- E2E 中玩家在居民响应动画播放中途关闭对话框：后端按 Graceful Exit 收尾，断言无泄漏。

## 8. 错误与降级

- 测试失败输出：scenario ID、Seed、Revision、conversation ID、失败断言与脱敏 invariant ID；不输出 utterance 原文到 CI 日志（含恶意输入语料）。
- Golden Transcript 与实现演进冲突：只能通过升级 fixture 版本显式重录，禁止测试内动态放宽断言。

## 9. 安全与性能

- 安全回归与 Bypass Probe 在 CI 强制执行，失败即阻断（`RULE-DIALOGUE-073`）。
- 性能预算断言：单会话每 utterance 服务器处理（不含模型延迟）P95 `<= 50 real ms`；4 人群聊 + 8 旁听者场景下 Tick 复算不使 World Tick 超出 `DOC-TIME-011` 预算。

## 10. 验收标准

E2E 场景清单（全部必须通过）：

1. `e2e.dialogue.basic`：走近居民 → Enter 打开输入框 → 世界暂停（HUD 时钟停）→ 问候 → 居民立绘/情绪变化 → 告别 → 世界恢复。
2. `e2e.dialogue.trade_intent`：对话中说「买两瓶药」→ Confirmation 弹出 → 确认 → ECON 成交事件 → 物品栏与余额变化；取消路径零变化。
3. `e2e.dialogue.combat_interrupt`：对话中触发 Encounter → 会话挂起、输入框关闭 → 战斗结束 → 重新交谈出现接续摘要。
4. `e2e.dialogue.group_overhear`：三人群聊 + 一名旁听居民 → 轮次有序 → 旁听者事后可转述（testimony 生效）。
5. `e2e.dialogue.injection_probe`：输入 `DOC-DIALOGUE-011` 的 markup/instruction fixture → DOM 无新增元素、无秘密文本、居民世界内回应。
6. `e2e.dialogue.save_reload`：对话进行中刷新页面 → 会话按持久化状态恢复或安全终结，无悬挂暂停。

以及：矩阵全绿、Bypass Probe 双零、泄漏 Oracle 零命中、恢复一致性通过。

## 11. 测试追踪

| 测试 ID | 覆盖 | 所属文档 |
|---|---|---|
| `TEST-DIALOGUE-001..002` | 状态机、token、幂等 | `DOC-DIALOGUE-001` |
| `TEST-DIALOGUE-003..004` | 参与条件、Reservation | `DOC-DIALOGUE-002` |
| `TEST-DIALOGUE-005..006` | context 组装与预过滤 | `DOC-DIALOGUE-003` |
| `TEST-DIALOGUE-007..008` | 意图边界、Testimony/承诺 | `DOC-DIALOGUE-004` |
| `TEST-DIALOGUE-009..010` | Speech Act decode 与提交 | `DOC-DIALOGUE-005` |
| `TEST-DIALOGUE-011..012` | 情绪呈现分离与确定性 | `DOC-DIALOGUE-006` |
| `TEST-DIALOGUE-013..014` | 打断优先级与取消 | `DOC-DIALOGUE-007` |
| `TEST-DIALOGUE-015..016` | 群聊轮次与旁听 | `DOC-DIALOGUE-008` |
| `TEST-DIALOGUE-017..018` | 事件发射与幂等 | `DOC-DIALOGUE-009` |
| `TEST-DIALOGUE-019..020` | 渲染与中文风格 | `DOC-DIALOGUE-010` |
| `TEST-DIALOGUE-021..022` | 注入与内容边界 | `DOC-DIALOGUE-011` |
| `TEST-DIALOGUE-023` | `RULE-DIALOGUE-072`, `RULE-DIALOGUE-074` 矩阵完备与故障注入 | 本文 |
| `TEST-DIALOGUE-024` | `RULE-DIALOGUE-073` Bypass Probe 与泄漏 Oracle 双零 | 本文 |
| `TEST-DIALOGUE-025` | `RULE-DIALOGUE-075` E2E 场景 1..6 | 本文 |
| `TEST-DIALOGUE-026` | 恢复一致性与高倍速等价 | 本文 |

REQ 覆盖映射：`REQ-DIALOGUE-001→TEST-001..002`、`002→003..004`、`003→005..006`、`004→007..008`、`005→009..010`、`006→011..012`、`007→013..014`、`008→015..016`、`009→017..018`、`010→019..020`、`011→021..022`、`012→023..026`（ID 前缀 `TEST-DIALOGUE-` 略写）。

## 12. 关联文档

- `DOC-DIALOGUE-001..011`（被覆盖规格全集）
- `DOC-RESIDENT-012`（harness 同构参照）、`DOC-AI-012`（泄漏评测门）、`DOC-TIME-011`（性能预算）、`DOC-TIME-012`（时间域测试衔接）

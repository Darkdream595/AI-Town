---
doc_id: DOC-DIALOGUE-006
title: 情绪与语气表达
version: 1.0.0
status: approved-for-implementation
owner_domain: dialogue
canonical_for:
  - dialogue-emotion-presentation
  - dialogue-tone-policy
depends_on:
  - DOC-DIALOGUE-005
  - DOC-RESIDENT-003
  - DOC-RESIDENT-004
  - DOC-MEMORY-006
requirements:
  - REQ-DIALOGUE-006
last_updated: 2026-07-26
---

# 情绪与语气表达

## 1. 目的

`REQ-DIALOGUE-006`：定义对话中情绪与语气的表达管道——Speech Act 的 `emotion/tone` 字段如何与居民已提交情绪状态、性格、关系边协同，映射为立绘表情、情绪提示与文风约束——并保证表达层永远不反向改写居民的规则情绪状态。

## 2. 非目标

本文不定义 Emotion 数值模型与衰减（`DOC-RESIDENT-004` 是 canonical owner）、性格维度（`DOC-RESIDENT-003`）、关系维度（`DOC-MEMORY-006`）或立绘美术资产规格（ART 域）。本文只拥有对话呈现层的映射与一致性规则。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Expressed Emotion | Speech Act 携带的 `emotion` 字段：这句话表现出来的情绪，允许与内在状态不同（掩饰） |
| Committed Emotion | RESIDENT 已提交的 `primary + intensity_q1000` 情绪状态，规则真值 |
| Tone | 话语的社交姿态枚举 `warm / neutral / cold / formal / playful / hostile`，与 emotion 正交 |
| Portrait Cue | 渲染层从 Expressed Emotion 派生的立绘表情键 |
| Expression Divergence | Expressed 与 Committed 不一致的程度，用于掩饰的合理性约束 |

## 4. 规则与不变量

- `RULE-DIALOGUE-032`：Expressed Emotion 与 Tone 是呈现层数据：只驱动立绘、情绪提示与文风，永不写回 Committed Emotion；居民情绪变化只能由已提交事件经 RESIDENT 管道发生（`RULE-RESIDENT-019`、`RULE-RESIDENT-021..022`）。
- `RULE-DIALOGUE-033`：`emotion` 枚举与 `DOC-RESIDENT-004` 的八值 Emotion 枚举字面一致（`calm/joy/sadness/anger/fear/anxiety/disgust/hope`）；两处枚举由同一注册表生成，禁止各自维护。
- `RULE-DIALOGUE-034`：允许掩饰：Expressed 可以不等于 Committed（强作镇定、皮笑肉不笑）；但 Committed `intensity_q1000 >= 800`（critical 段）时 Expression Divergence 受限——Prompt 层向模型披露"当前情绪难以掩饰"，且渲染层叠加不可抑制的微表情 Portrait Cue。
- `RULE-DIALOGUE-035`：Tone 选择的输入固定为：性格投影、当下 Committed Emotion、对目标的关系边（`affection/trust/fear/respect/intimacy`）与会话事件；同一输入快照下 Portrait Cue 映射完全确定，渲染不掷随机。
- `RULE-DIALOGUE-036`：情绪提示 UI 只展示 Expressed Emotion 与 Tone 的呈现结果；Committed Emotion 数值、Need 数值与关系分数不向对话 UI 暴露（他人内心不可读，与 `RULE-AI-012` 一致）。
- `RULE-DIALOGUE-037`：玩家 utterance 无 Expressed Emotion 字段；玩家立绘不做情绪推断展示，避免系统替玩家表演内心。

## 5. 数据与接口

`DES-DIALOGUE-006`：呈现映射结果（随 `dialogue.speech_act_committed/v1` 投影给渲染层）。

```json
{
  "schema_version": 1,
  "conversation_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "utterance_index": 5,
  "speaker_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "expressed_emotion": "calm",
  "tone": "formal",
  "portrait_cue": "calm_guarded",
  "leak_cue": "brow_tension",
  "committed_emotion_band": "critical"
}
```

`portrait_cue` 取值来自版本化 Portrait Cue Catalog（`emotion × tone → cue` 的确定性映射表，ART 域实现资产，DIALOGUE 拥有映射键）；`leak_cue` 仅在 `RULE-DIALOGUE-034` 的受限掩饰情形非空。`committed_emotion_band` 只携带 `satisfied/notice/pressing/critical` 段位供渲染微表情强度使用，不携带数值。

## 6. 正常流程

1. Speech Act 提交后，DIALOGUE 读取说话者 Committed Emotion band、性格与关系投影。
2. 按 `RULE-DIALOGUE-034..035` 计算 Expression Divergence 约束与 Portrait Cue。
3. 投影发布给渲染层：立绘切换表情、情绪提示条更新、文本按 Tone 呈现（不改写文本内容）。
4. 情绪的真实变化（被安慰、被激怒）由后续已提交事件走 RESIDENT 管道，再影响下一轮 Prompt。

## 7. 边界情况

- 模型输出 `emotion` 与 context 中情绪严重矛盾（喜讯用 disgust）：Schema 合法即接受——这是表演自由；但 critical band 下的越限掩饰按 `RULE-DIALOGUE-034` 叠加 leak cue。
- 立绘资产缺失某 cue：渲染回退到同 emotion 的 `neutral` tone cue，并记录资产缺失告警；不阻塞会话。
- `comfort` 类 Speech Act 不直接降低对方情绪强度：安慰效果由 MEMORY/RESIDENT 事件管道决定，可能无效。
- 群组会话中旁听者视角：同一 utterance 对所有可见者展示同一 Expressed Emotion（表情是公开可见的），内心仍不可读。

## 8. 错误与降级

- Portrait Cue Catalog 版本不匹配：使用 `neutral` 兜底 cue 并记录告警，禁止渲染层自造映射。
- Committed Emotion 投影读取失败：按 `notice` band 保守处理 Divergence 约束，fail closed 不披露数值。

## 9. 安全与性能

- 呈现映射为纯函数查表，每 utterance 一次，无模型调用。
- 情绪提示不成为侧信道：band 只在 leak cue 计算内使用，UI 不展示 band 本身，防止玩家精确读取居民内心数值。

## 10. 验收标准

- 8 emotion × 6 tone 全组合有确定 Portrait Cue；同输入重放同输出。
- critical band 掩饰 fixture 必产生 leak cue；非 critical 不产生。
- 对话全程 Committed Emotion 仅经 RESIDENT 事件变化，呈现层零写回。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-DIALOGUE-011` | `RULE-DIALOGUE-032..034` 呈现/真值分离、枚举一致、掩饰与 leak cue |
| `TEST-DIALOGUE-012` | `RULE-DIALOGUE-035..037` 映射确定性、内心不可读、玩家不表演 |

## 12. 关联文档

- `DOC-DIALOGUE-005`（emotion/tone 字段来源）、`DOC-DIALOGUE-009`（情绪的事件化影响）
- `DOC-RESIDENT-003`（性格）、`DOC-RESIDENT-004`（Emotion 真值 canonical）、`DOC-MEMORY-006`（关系边）

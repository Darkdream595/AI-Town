---
doc_id: DOC-RESIDENT-004
title: Needs 与情绪状态
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-needs
  - resident-emotion-state
  - need-thresholds
depends_on:
  - DOC-FOUNDATION-006
  - DOC-RESIDENT-001
  - DOC-RESIDENT-003
requirements:
  - REQ-RESIDENT-004
last_updated: 2026-07-26
---

# Needs 与情绪状态

## 1. 目的

`REQ-RESIDENT-004`：定义可确定性推进的 Needs、明确阈值、短期 Emotion 和安全优先信号，使模型离线时居民仍能维持基本生活。

## 2. 非目标

不定义 TIME 的 Tick/事件队列、不选择行动、不定义食物 Item 效果或对话语气；外部 owner 只通过已提交效果调用本域。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Need | `0..1000` 的缺口值，越高越需要处理 |
| Threshold Band | `satisfied/notice/pressing/critical` |
| Emotion | `calm/joy/sadness/anger/fear/anxiety/disgust/hope` 之一 |
| Safety Override Signal | critical Need/Health 供 AI 合法候选排序使用的输入，不直接执行 |

## 4. 数据与接口

`DES-RESIDENT-004`：注册 `schema.resident.needs_state.v1`；required 字段为
`needs_schema_version/values/emotion`；`values` required properties 为
`hunger/fatigue/safety/social/comfort`，每个 Need required
`value_q1000/last_updated_game_time`，Emotion required
`primary/intensity_q1000/cause_event_ids/updated_at_game_time/decay_rate_q1000_per_game_hour`。
该完整对象原样嵌入 `ResidentAggregateV1.needs_state`：

```json
{
  "needs_schema_version": 1,
  "values": {
    "hunger": {"value_q1000": 420, "last_updated_game_time": 1830},
    "fatigue": {"value_q1000": 610, "last_updated_game_time": 1830},
    "safety": {"value_q1000": 90, "last_updated_game_time": 1830},
    "social": {"value_q1000": 330, "last_updated_game_time": 1830},
    "comfort": {"value_q1000": 250, "last_updated_game_time": 1830}
  },
  "emotion": {
    "primary": "anxiety",
    "intensity_q1000": 460,
    "cause_event_ids": ["01K1AB2CD3EF4GH5JK6MNP7QRZ"],
    "updated_at_game_time": 1830,
    "decay_rate_q1000_per_game_hour": 80
  }
}
```

统一阈值：`0..299 satisfied`、`300..599 notice`、`600..799 pressing`、`800..1000 critical`。Catalog 可定义每 Need 的确定性增长率，但不得改变 band 边界。

## 5. 规则与不变量

- `RULE-RESIDENT-018`：Need 值为整数 `0..1000`，推进采用 GameTime 差值；暂停或关闭期间不推进。
- `RULE-RESIDENT-019`：Need 只由已提交 `NeedEffect` 或 TIME 触发的确定性 rate update 改变；模型文本不能直接设值。
- `RULE-RESIDENT-020`：critical hunger/fatigue/safety 生成 `resident_safety_attention_required` 信号，但仍必须通过 AI/Utility AI 与 Action validator。
- `RULE-RESIDENT-021`：Emotion 强度为 `0..1000`；同一时刻只有一个 primary，可保留最多四个 cause event ID。
- `RULE-RESIDENT-022`：Emotion 自然衰减不得抹除 Health、Memory、关系或客观事件；强度降至 0 后 primary 回到 `calm`。
- `RULE-RESIDENT-023`：Need/Emotion 更新命令按 `(resident_id, source_event_id, effect_type)` 幂等。

## 6. 正常流程

1. TIME owner 到期后请求按明确 GameTime 区间推进。
2. Resident 计算 rate delta、量化并跨阈值时生成 `ResidentNeedBandChanged`。
3. Item、休息、治疗等 owner 提交结果后传入 `NeedEffect`。
4. 已提交事件可计算 Emotion impulse，再按 GameTime 衰减。
5. AI projection 只读取最新值、band、cause ID 和安全信号。

## 7. 边界情况

- 一次长任务跨多个阈值时逐个生成有序 band event，但仅一个事务。
- 同一 Revision 多个 effect 先按 `source_event_id` 字典序应用，确保重放一致。
- fatigue=1000 不自动睡眠；若环境危险，合法行动可能是求助或撤离。
- 无法获得食物时 Utility AI 可选择求助/等待，不得凭空减少 hunger。

## 8. 错误与降级

负 GameTime、未来 source event、未知 Need/Emotion 返回 `RESIDENT_NEED_EFFECT_INVALID`。缺少定时更新时恢复审计从最后时间确定性补算到保存时 GameTime，不按现实离线时间补算。

## 9. 安全与性能

Need/Emotion 是游戏状态，不用于医学诊断。按阈值或小时事件驱动，不在每个 10 Hz Tick 写入；每居民每游戏分钟最多一次聚合更新。

## 10. 验收标准

- 阈值端点 299/300/599/600/799/800 结果准确。
- 暂停、关闭、重载后值与事件序列可重复。
- 模型失败时 critical Needs 可由 Utility AI 读取但不能绕过规则。
- 重放同一 effect 不重复改变 Need。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-013` | Need 阈值边界 Table Test |
| `TEST-RESIDENT-014` | pause/reload/long interval deterministic test |
| `TEST-RESIDENT-015` | Effect 幂等与同 Revision 排序 |
| `TEST-RESIDENT-016` | critical signal 不直接执行 Action |

## 12. 关联文档

- `DOC-RESIDENT-003`：稳定人格输入
- `DOC-RESIDENT-007`：健康安全限制
- `DOC-TIME-004`：下游居民调度
- `DOC-AI-011`：Utility AI 消费安全信号

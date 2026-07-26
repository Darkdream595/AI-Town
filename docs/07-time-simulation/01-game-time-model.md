---
doc_id: DOC-TIME-001
title: 游戏时间模型与权威时钟
version: 1.0.1
status: approved-for-implementation
owner_domain: time
canonical_for:
  - authoritative-game-clock
  - real-game-turn-time-separation
  - crown-calendar-conversion
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-WORLD-007
requirements:
  - REQ-TIME-001
last_updated: 2026-07-26
---

# 游戏时间模型与权威时钟

## 1. 目的

`REQ-TIME-001`：定义 `RealTime`、`GameTime`、`TurnTime` 的唯一语义、权威来源、换算边界和王冠历投影。TIME 是 GameTime clock 与 calendar conversion 的 Canonical Owner；其他 domain 只能查询 clock snapshot 或消费时间事件。

## 2. 非目标

本文不定义战斗回合规则、居民日程内容、天气变化公式或前端动画时长。`COMBAT` 拥有 Encounter 内的 Turn 状态，`WORLD` 拥有王冠历目录，TIME 只做确定性换算。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `RealTime` | 进程内 monotonic clock 的持续时间，用于 timeout、latency、Tick cadence 和动画；不由系统墙钟推进 |
| `GameTime` | `GameInstant`，自王冠历纪元起的整数游戏分钟，受 Pause 与倍率控制 |
| `TurnTime` | Encounter 内的 `{encounter_id, round_index, turn_index, phase}`，不与 GameTime 换算 |
| Clock Snapshot | 固定 `world_id/revision` 下的不可变时钟投影 |
| Clock Phase | 0–19 的非日期进度量；每 20 quanta 产生 1 个游戏分钟 |
| Calendar Epoch | 首版固定 `GameInstant=0 → 王冠历 487 年融霜月 1 日 00:00` 的版本化起点 |
| Calendar Projection | 从 GameInstant 与 Calendar Epoch 纯函数换算出的王冠年、月/换岁日、周日与日内时间 |

## 4. 规则与不变量

- `RULE-TIME-001`：只有 World Runtime 内的 TIME clock 可推进 `GameInstant`；Client、AI、系统墙钟和 Render frame 均不可写 GameTime。
- `RULE-TIME-002`：默认 `1 real second = 1 game minute`；倍率只允许 `0×/0.5×/1×/2×/4×`（wire value 为 `0/0.5/1/2/4`），不得插值或接受任意浮点值。
- `RULE-TIME-003`：World Tick 固定目标 10 Hz；每 Tick 在 `0.5×/1×/2×/4×` 分别增加 `1/2/4/8` 个 Clock Phase quanta，20 quanta 才原子增加 1 个 `GameInstant` 分钟。
- `RULE-TIME-004`：`TurnTime` 不自动推进 GameTime；进入 Encounter 后由 Pause Policy 冻结 Overworld clock。
- `RULE-TIME-005`：王冠历每年为 12×30 个常月日加 5 个换岁日；换岁日不属于月份和六日周。
- `RULE-TIME-006`：同一 world 的 GameTime 不得倒退；读取旧存档创建新 timeline 时，新 timeline 可从来源 GameInstant 开始，但必须保留来源引用。
- `RULE-TIME-073`：首版 Calendar Epoch ID 固定为 `calendar_epoch.crown_487_thaw_1`；改变 Epoch 必须创建新版本并迁移，不能通过系统日期或存档读取日改写。

## 5. 数据与接口

`DES-TIME-001`：权威快照 Schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "schema://ai-town/time/clock-snapshot/v2",
  "type": "object",
  "required": ["schema_version", "world_id", "revision", "calendar_epoch_id", "game_time", "clock_phase_quanta", "requested_speed_multiplier", "speed_cap_multiplier", "effective_speed_multiplier", "paused"],
  "properties": {
    "schema_version": {"const": 2},
    "world_id": {"type": "string", "pattern": "^[0-9A-HJKMNP-TV-Z]{26}$"},
    "revision": {"type": "integer", "minimum": 0},
    "calendar_epoch_id": {"const": "calendar_epoch.crown_487_thaw_1"},
    "game_time": {"type": "integer", "minimum": 0},
    "clock_phase_quanta": {"type": "integer", "minimum": 0, "maximum": 19},
    "requested_speed_multiplier": {"enum": [0, 0.5, 1, 2, 4]},
    "speed_cap_multiplier": {"enum": [0.5, 1, 2, 4]},
    "effective_speed_multiplier": {"enum": [0, 0.5, 1, 2, 4]},
    "paused": {"type": "boolean"}
  },
  "additionalProperties": false
}
```

示例：

```json
{
  "schema_version": 2,
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "revision": 820,
  "calendar_epoch_id": "calendar_epoch.crown_487_thaw_1",
  "game_time": 1830,
  "clock_phase_quanta": 6,
  "requested_speed_multiplier": 4,
  "speed_cap_multiplier": 1,
  "effective_speed_multiplier": 1,
  "paused": false
}
```

`effective_speed_multiplier` 与 `paused` 均为 `DOC-TIME-002` 公式的派生值；上述示例没有 Pause Token，但 `requested=4` 仍受 `cap=1` 限制，故 effective 为 1。`paused` 必须等于 `effective_speed_multiplier == 0`，消费者不得从 requested speed 自行推导。

Clock Snapshot v1 没有 `speed_cap_multiplier`，不得以 `requested_speed_multiplier` 代填。v1→v2 只可从同一 Revision 的 ClockControl Event 恢复 cap 并重新合成 effective；证据缺失时拒绝 upcast。

Clock Port：

```text
get_clock_snapshot(world_id) -> ClockSnapshot
advance_clock(world_id, tick_sequence, effective_speed) -> ClockAdvanceResult
project_crown_calendar(game_time) -> CrownCalendarDate
resolve_game_deadline(base_game_time, duration_game_minutes) -> GameInstant
```

`CrownCalendarDate` 使用 tagged union：常月日为 `{kind:"month_day",year,month_id,day,weekday_id,hour,minute}`；换岁日为 `{kind:"yearturn_day",year,yearturn_day,hour,minute}`，后者禁止 `weekday_id`。

## 6. 正常流程

1. World Runtime 以 monotonic deadline 驱动 10 Hz Tick。
2. Pause Controller 计算 effective speed。
3. Clock 按倍率增加 quanta；跨过 20 时提交一个或多个整数 GameTime 分钟。
4. 每个新增分钟将到期范围交给 Event Queue；业务 owner 处理后产生 DomainEvent。
5. 前端从已提交 Clock Event 渲染日期与时间，60 FPS 插值不写回 clock。

## 7. 边界情况

- `4×` 时每 Tick 增加 8 quanta，跨分钟可留下余数，不能四舍五入丢失。
- speed 在 Tick 间切换只影响后续 Tick，已有 Clock Phase 不重算。
- monotonic clock 跳跃或进程挂起时单次最多执行 `DOC-TIME-003` 规定的 catch-up 上限；不把墙钟间隔直接换成 GameTime。
- GameInstant 恰落在第 360 日结束时，下一分钟进入换岁第 1 日；第 365 日结束后年份加一并回到融霜月 1 日。
- 负 duration、未知 calendar ID、非法换岁日或 GameTime overflow 必须拒绝。

## 8. 错误与降级

Clock state 无法解析、倍率非法、tick_sequence 回退或 calendar conversion 失败时返回 `TIME_CLOCK_INVALID` 并暂停该 world；禁止猜测日期继续运行。Render 缺少日期格式化时可显示原始 GameInstant，不影响权威 clock。

## 9. 安全与性能

clock advance 和 calendar conversion 必须是无网络 I/O 的纯确定性核心；全年边界可缓存为不可变表。输入整数设上限，避免恶意超大 deadline 导致循环。墙钟 `recorded_at` 仅供审计，不能参与排序或推进。

## 10. 验收标准

- 五种倍率在固定 Tick 序列下得到精确 GameInstant 与 Clock Phase。
- RealTime、GameTime、TurnTime 的字段、owner 和换算关系无交叉写入。
- 王冠历任意分钟可无损投影并反向解析，含全部换岁边界。
- 60 FPS render 波动不改变 10 Hz clock 结果。
- 存档重载保持 GameInstant 与 Clock Phase 不变。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-001` | `RULE-TIME-001..004` 三时钟隔离与倍率 quanta property test |
| `TEST-TIME-002` | `RULE-TIME-005`, `RULE-TIME-073` 365 日 calendar round-trip 与 Epoch |
| `TEST-TIME-003` | `RULE-TIME-006` timeline/load 不倒退且保留来源 |

## 12. 关联文档

- `DOC-FOUNDATION-006`：三时钟和单位基元
- `DOC-WORLD-007`：王冠历目录
- `DOC-TIME-002`：Pause 与倍率控制
- `DOC-TIME-003`：Tick 推进算法
- `DOC-COMBAT-002`：TurnTime 的下游战斗语义

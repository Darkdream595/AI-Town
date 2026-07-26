---
doc_id: DOC-EVENT-006
title: 天气与自然环境
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - weather-catalog
  - weather-transition-model
  - environment-hazard-escalation
depends_on:
  - DOC-FOUNDATION-006
  - DOC-TIME-008
  - DOC-TIME-010
  - DOC-EVENT-002
  - DOC-MAP-010
  - DOC-RENDER-007
requirements:
  - REQ-EVENT-006
last_updated: 2026-07-26
---

# 天气与自然环境

## 1. 目的

`REQ-EVENT-006`：定义权威天气状态、九项天气 Stable Catalog、种子化 30 游戏分钟评估、注册化的出行/视野/采集/火灾/魔法/经济修饰，以及天气升级为灾害 WorldEvent 与导航封锁的合规路径。

## 2. 非目标

本文不定义光照 band 与天气覆盖的视觉实现（`DOC-RENDER-007` canonical）、天气音频分层（`DOC-RENDER-010`）、法术与环境的相互作用数值（`DOC-MAGIC-009`）或价格公式（ECON）。本文不模拟真实气象，只提供规则可判定的抽象天气。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Weather State | 每个室外 region 的权威 `(weather_id, intensity_0_to_1, since_game_time)` |
| Weather Catalog | 注册的天气类型集合及其允许强度与修饰声明 |
| Transition Matrix | 按季节/区域声明的天气转移概率表，种子化抽样 |
| Environment Stat | 区域环境统计量（`dryness_0_to_1`、`flood_level_0_to_1`），随天气演化 |
| Weather Modifier | 以稳定 ID 声明、由 owner 域解释的天气影响项 |
| Hazard Escalation | 天气条件满足时经 `DOC-EVENT-002` 触发器升级为灾害 WorldEvent |

## 4. 规则与不变量

- `RULE-EVENT-031`：Weather Catalog 固定为 `weather.clear / weather.cloudy / weather.rain.light / weather.rain.heavy / weather.fog / weather.thunderstorm / weather.snow / weather.magical_cold_snap / weather.mana_anomaly`；天气按室外 region 独立持有，室内 Scene 无天气状态，只经门/入口语义感知室外天气。
- `RULE-EVENT-032`：天气评估由 `periodic.environment.weather_evaluation`（interval 30 game minutes，phase 3，`RULE-TIME-046` canonical cadence）驱动；转移抽样只使用 `(seed, "event.weather." + region 末段, sequence)`（`RULE-FOUNDATION-026`），存档重载不改变序列；天气变化作为 DomainEvent 提交。
- `RULE-EVENT-033`：天气影响只以 Weather Modifier 稳定 ID 声明并由 owner 域解释：移动速度与视野（MAP/RESIDENT）、采集与矿洞产出（ECON）、火灾概率与 dryness（EVENT 触发器输入）、魔法环境作用（MAGIC）、区域价格（ECON）；EVENT 不直接写他域数值。
- `RULE-EVENT-034`：灾害（森林火灾、洪水、魔力风暴、寒潮冻害）不是天气本身，而是经 `DOC-EVENT-002` 触发器实例化的 WorldEvent，占用 Narrative Pressure Budget 并受冷却；天气只提供触发条件输入。
- `RULE-EVENT-035`：渲染只消费包含 `weather_id/intensity/revision/game_time` 的 environment projection（`RULE-RENDER-019`）；视觉、粒子与音频不反向定义规则，未注册 `weather_id` 不得进入 projection。
- `RULE-EVENT-036`：天气造成的通行封锁（洪水淹路、雪封山口）必须经 `DOC-MAP-010` NavigationPatch 原子提交并追加 WorldDiff（`DOC-EVENT-011`）；未走 patch 的天气一律只是修饰，不改变 Walkability/Collision。

## 5. 数据与接口

`DES-EVENT-006`：Catalog 条目与权威状态：

```json
{
  "schema_version": 1,
  "weather_id": "weather.rain.heavy",
  "allowed_intensity": [0.4, 1.0],
  "min_duration_game_minutes": 60,
  "modifiers": [
    {"modifier_id": "move_speed.outdoor_penalty", "target_domain": "map", "value_0_to_1": 0.2},
    {"modifier_id": "visibility.range_penalty", "target_domain": "resident", "value_0_to_1": 0.3},
    {"modifier_id": "econ_modifier.outdoor_market_slowdown", "target_domain": "economy", "value_0_to_1": 0.25}
  ],
  "environment_effects": [
    {"stat": "dryness_0_to_1", "delta_per_game_hour": -0.15},
    {"stat": "flood_level_0_to_1", "delta_per_game_hour": 0.1}
  ]
}
```

```json
{
  "schema_version": 1,
  "scene_id": "region.crown_creek_town",
  "weather_id": "weather.rain.heavy",
  "intensity_0_to_1": 0.7,
  "since_game_time": 21630,
  "environment_stats": {"dryness_0_to_1": 0.2, "flood_level_0_to_1": 0.35},
  "version": 88
}
```

Transition Matrix 按 `(region, season)` 注册，行为当前 `weather_id`、列为候选目标，概率行和为 1；`weather.mana_anomaly` 只允许由魔法事件条件行进入，不出现在常规行。接口：

```text
evaluate_weather(occurrence_key, scene_id) -> WeatherTransitionResult
get_environment_projection(scene_id) -> EnvironmentRenderProjection
get_environment_stats(scene_id) -> RevisionStampedStats
```

## 6. 正常流程

1. phase 3 occurrence 到期，逐室外 region 读取当前状态与季节。
2. 按 Transition Matrix 与种子流抽样得到目标天气与强度；不满足 `min_duration_game_minutes` 时保持不变。
3. 变化时原子提交天气 DomainEvent 并更新 Environment Stat。
4. RENDER/AUDIO 消费 projection 切换表现；ECON/MAP/MAGIC 按 Modifier 解释影响。
5. phase 4 触发评估读取新 Environment Stat，必要时实例化灾害 WorldEvent。

## 7. 边界情况

- 高倍速一次 Due Window 含多个天气 occurrence：逐 occurrence 执行（`RULE-TIME-048`），转移链与 1× 相同。
- 灾害 active 期间模板可声明天气锁定（雷暴期间禁转 `weather.clear`）；锁定由模板参数表达，评估时读取 active 事件摘要。
- `weather.magical_cold_snap` 与 `weather.snow` 互斥同 region；矩阵行构建期校验互斥对概率为 0。
- 洪水封路的 NavigationPatch 因 Critical Route Gate 失败（`RULE-MAP-039`）：改为登记 `flood_level` 高值修饰并提交降速 Modifier，绝不绕过 Gate 强行封路；触发器可转而实例化"洪水危机"事件走灾害流程携带 safe relocation。
- 新建室外 region 无历史天气：初始为 `weather.clear`、强度 0，Environment Stat 取模板默认。

## 8. 错误与降级

未知 `weather_id`、矩阵行概率和偏差超过 1e-9、强度越界或 occurrence 重放返回 `weather_config_invalid/occurrence_replayed` 并保持原状态。评估 handler 失败按 `RULE-TIME-047` 重试；连续失败时天气冻结在最后已提交状态并发布诊断事件，渲染端按 `DOC-RENDER-007` 保留上一有效表现。

## 9. 安全与性能

Transition Matrix 与 Catalog 构建期只读；单次评估 O(区域数 × 候选列)，三个室外 region 下可忽略。天气事件 payload 不含实体隐私。`weather.mana_anomaly` 的魔法效果参数由 MAGIC 校验，EVENT 不放大数值范围。

## 10. 验收标准

- 相同 Seed 的 30 游戏日天气序列逐分钟一致。
- 九项天气均有注册 Modifier 与渲染 key，未注册 ID 无法进入 projection。
- 灾害只经触发器与预算产生，天气评估自身不实例化 WorldEvent。
- 封路 fixture 证明 patch 路径与 Gate 失败回退路径都不破坏导航不变量。
- `1×/4×` 与暂停组合下 cadence 计数精确无漂移。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-016` | `RULE-EVENT-031..032` Catalog、按区域状态与种子化重放 |
| `TEST-EVENT-017` | `RULE-EVENT-033..034` Modifier 边界与灾害升级预算 |
| `TEST-EVENT-018` | `RULE-EVENT-035..036` projection 契约与封路合规 |

## 12. 关联文档

- `DOC-EVENT-002`：灾害触发与叙事压力
- `DOC-EVENT-011`：天气类 WorldDiff 与逆向重开
- `DOC-TIME-008`：`periodic.environment.weather_evaluation` 目录项
- `DOC-RENDER-007`：昼夜与天气视觉消费端
- `DOC-MAGIC-009`：魔法与环境相互作用
- `DOC-WORLD-004`：区域 `weather_or_event_hooks` 语义来源

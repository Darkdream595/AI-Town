---
doc_id: DOC-RENDER-007
title: 昼夜与天气视觉系统
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - day-night-lighting
  - weather-overlays
  - reduced-motion-visual-policy
depends_on:
  - DOC-RENDER-003
  - DOC-FOUNDATION-006
requirements:
  - REQ-RENDER-007
last_updated: 2026-07-26
---

# 昼夜与天气视觉系统

## 1. 目的

把权威 GameTime 与 Weather projection 映射成可读的光照、调色、天气覆盖和可访问性降级。

## 2. 非目标

不计算天气概率、季节、作物或伤害；不使用真实墙钟驱动昼夜。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Lighting registry | 版本化、构建期只读的 GameTime minute → band/preset/transition 映射。 |
| Lighting band | `dawn`、`day`、`dusk`、`night` 四段调色配置，由 Client 使用 registry 确定性派生。 |
| Weather overlay | 雨、雪、雾、沙尘等仅表现层颗粒/遮罩。 |
| Reduced Motion | 用户可选模式：去除闪烁、镜头抖动和连续粒子。 |

## 4. 规则与不变量

- `RULE-RENDER-019`：Backend/Orchestrator 只读 environment projection 提供已提交的 `game_time`、`weather_id`、`lighting_registry_id` 与 registry hash；Client 以 `game_minute_of_day = game_time mod 1440` 从该 registry 派生 band，不接受墙钟或本地时间。相同 Revision + registry hash 必得相同 band/tint。
- `RULE-RENDER-020`：天气覆盖永不降低 UI 可读性和角色选择可见性；night 仍保持关键通路可辨认。
- `RULE-RENDER-021`：Reduced Motion 用静态 tint/图标替代相同语义的粒子、闪白与 camera shake。Registry ID 未知、hash 不匹配或外部 payload 携带的 band 与本地派生值不一致时，拒绝该 environment update、保留上一有效 state、发出 `RENDER_LIGHTING_REGISTRY_MISMATCH` 并请求完整 Snapshot；不得混用两个版本。

## 5. 数据与接口

`DES-RENDER-007`：首版固定 registry `lighting.registry.medieval_v1`，Manifest 存储其 JSON 与 SHA-256。分钟区间为左闭右开：night `[0,300)`、dawn `[300,420)`、day `[420,1080)`、dusk `[1080,1200)`、night `[1200,1440)`。每个新 band 的前 60 game minutes 从上一 preset 过渡到当前 preset，使用 `smoothstep(t)=t²(3-2t)`，`t=clamp((minute-start_minute)/60,0,1)`；night 的 1200 边界与跨日 0 边界使用同一 night preset，不重复启动过渡。

```json
{
  "lighting_registry_id": "lighting.registry.medieval_v1",
  "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45",
  "bands": [
    {"band":"night","start_minute":0,"end_minute":300,"preset_id":"lighting.preset.night","transition_minutes":0,"curve":"smoothstep"},
    {"band":"dawn","start_minute":300,"end_minute":420,"preset_id":"lighting.preset.dawn","transition_minutes":60,"curve":"smoothstep"},
    {"band":"day","start_minute":420,"end_minute":1080,"preset_id":"lighting.preset.day","transition_minutes":60,"curve":"smoothstep"},
    {"band":"dusk","start_minute":1080,"end_minute":1200,"preset_id":"lighting.preset.dusk","transition_minutes":60,"curve":"smoothstep"},
    {"band":"night","start_minute":1200,"end_minute":1440,"preset_id":"lighting.preset.night","transition_minutes":60,"curve":"smoothstep"}
  ]
}
```

Input `EnvironmentRenderProjection` 含 `world_id`、`scene_id`、`revision`、`game_time`、`weather_id`、`intensity_0_to_1`、`lighting_registry_id`、`lighting_registry_sha256`；Client 产出的 `EnvironmentVisualState` 才包含 `resolved_lighting_band`、`from_preset_id`、`to_preset_id` 与 `transition_t`。`weather.rain.light` 的 render key 必须在 Manifest 注册。

## 6. 正常流程

1. 校验 projection 的 registry ID/hash，再按已确认 GameTime minute 与 registry 计算 band、preset pair 和 `transition_t`；只按 GameTime 变化，不使用固定 RealTime 400 ms。
2. 天气 event 到达后注册/停止对应 overlay，并向 audio state 发出同一 weather ID。
3. 用户切换 Reduced Motion 后即时替换所有可访问性受控效果。

## 7. 边界情况

scene transfer 中 weather 状态随 Snapshot 水合；不继承旧 Scene 的粒子 emitter。高强度雾只降低远景饱和度，不遮蔽 HUD。

## 8. 错误与降级

未知 `weather_id` 退回 `weather.clear`，未知强度夹紧为 0；记录 contract error 但不停止 WorldScene。

## 9. 安全与性能

覆盖层用共享 emitter 和 viewport 裁剪；Reduced Motion 同时降低 GPU/CPU 预算，不采集健康等私密数据。

## 10. 验收标准

- `REQ-RENDER-007`：versioned registry 的五个分钟区间覆盖 `0..1439` 无重叠/空洞；四个 lighting band、所有注册天气与 Reduced Motion 在 720p/1080p 下均可辨认且同 Revision 可重放。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-007` | Property test 验证 1440 分钟映射、300/420/1080/1200/0 边界、smoothstep 与 registry mismatch；固定 GameTime/Weather 截图及 reduced-motion DOM/Canvas 检查。 |

## 12. 关联文档

- `DOC-RENDER-008`：VFX
- `DOC-RENDER-010`：天气音频
- 非 direct owner：Time/Event 的已提交事实由 Backend/Orchestrator 映射为只读 environment projection。

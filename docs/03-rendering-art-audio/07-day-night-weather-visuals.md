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
  - DOC-EVENT-006
  - DOC-TIME-001
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
| Lighting band | `dawn`、`day`、`dusk`、`night` 四段调色配置。 |
| Weather overlay | 雨、雪、雾、沙尘等仅表现层颗粒/遮罩。 |
| Reduced Motion | 用户可选模式：去除闪烁、镜头抖动和连续粒子。 |

## 4. 规则与不变量

- `RULE-RENDER-019`：光照只使用提交的 `game_time` 与 `weather_id`，重放同一 Revision 必得相同 band。
- `RULE-RENDER-020`：天气覆盖永不降低 UI 可读性和角色选择可见性；night 仍保持关键通路可辨认。
- `RULE-RENDER-021`：Reduced Motion 用静态 tint/图标替代相同语义的粒子、闪白与 camera shake。

## 5. 数据与接口

`DES-RENDER-007`：`EnvironmentVisualState` 含 `game_time`、`lighting_band`、`weather_id`、`intensity_0_to_1`、`reduced_motion`。`weather.rain.light` 的 render key 必须在 Manifest 注册。

## 6. 正常流程

1. 每个已确认 GameTime band 边界平滑过渡 400 ms。
2. 天气 event 到达后注册/停止对应 overlay，并向 audio state 发出同一 weather ID。
3. 用户切换 Reduced Motion 后即时替换所有可访问性受控效果。

## 7. 边界情况

scene transfer 中 weather 状态随 Snapshot 水合；不继承旧 Scene 的粒子 emitter。高强度雾只降低远景饱和度，不遮蔽 HUD。

## 8. 错误与降级

未知 `weather_id` 退回 `weather.clear`，未知强度夹紧为 0；记录 contract error 但不停止 WorldScene。

## 9. 安全与性能

覆盖层用共享 emitter 和 viewport 裁剪；Reduced Motion 同时降低 GPU/CPU 预算，不采集健康等私密数据。

## 10. 验收标准

- `REQ-RENDER-007`：四个 lighting band、所有注册天气与 Reduced Motion 在 720p/1080p 下均可辨认且状态可重放。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-007` | 固定 GameTime/Weather 截图、reduced-motion DOM/Canvas 检查。 |

## 12. 关联文档

- `DOC-RENDER-008`：VFX
- `DOC-RENDER-010`：天气音频

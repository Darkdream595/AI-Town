---
doc_id: DOC-RENDER-010
title: 音乐与环境音频
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - area-soundscapes
  - music-state-mixing
  - audio-licensing
depends_on:
  - DOC-RENDER-002
  - DOC-RENDER-007
  - DOC-WORLD-009
requirements:
  - REQ-RENDER-010
last_updated: 2026-07-26
---

# 音乐与环境音频

## 1. 目的

定义区域 Soundscape、音乐分层、天气/建筑音频状态与许可证追踪，使声音与权威 Scene/环境状态一致。

## 2. 非目标

不生成配乐、不录制语音、不定义战斗/天气规则，也不播放未经登记授权的网络资源。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Soundscape | region/interior 常驻的环境床、局部循环与一次性环境声集合。 |
| Music layer | `base`、`tension`、`combat` 三个可淡入淡出的无缝音乐层。 |
| Audio State | 已确认 scene、weather、time band、encounter 和 mute 设置的组合。 |

## 4. 规则与不变量

- `RULE-RENDER-028`：音频状态只从确认的 Scene/Weather/Encounter projection 派生，Client 不自行推断危险或战斗。
- `RULE-RENDER-029`：区域切换使用 500 ms crossfade；同类 layer 只能有一个活动实例。
- `RULE-RENDER-030`：每个音频 asset 必须通过 `license_id` 解析到 `DOC-RENDER-011` 的 machine-readable `LicenseRecord`，其 source、author、terms、acquired_at、license text path/hash 均非空；asset 自身 path/hash 也必须匹配。不合规资产不可进入 release Manifest。

## 5. 数据与接口

`DES-RENDER-010`：

```json
{"asset_id":"audio.music.crown_creek.base","audio_state_id":"audio_state.crown_creek.day.clear","bus":"music","loop":true,"license_id":"license.project_original_001"}
```

Audio registry 只引用 `asset_id/license_id`；文件 path、SHA-256 与完整 license record 由 Asset Manifest canonical schema 提供，避免音频状态复制授权元数据。

## 6. 正常流程

1. WorldScene 水合后解析 Audio State，lazy load 当前 Soundscape。
2. `base` 常驻，天气修改环境 bus，已确认 encounter 调高 `tension/combat`。
3. Scene Dispose 触发 crossfade、停止 region-local one-shot，并保留全局 UI 提示声。

## 7. 边界情况

浏览器 autoplay 禁止时显示一次“点击启用声音”按钮；静音仍保存 Audio State，用户首次手势后恢复当前正确层而不补播历史 one-shot。

## 8. 错误与降级

单个资源失败时其 bus 静音并记录 asset ID，其他 bus 不受影响；license lookup/hash 失败在 build 阶段使用 `RENDER_LICENSE_*` 诊断码阻断发布。无音乐时保留必要 UI/告警音的视觉等价提示。

## 9. 安全与性能

每 bus 限制 8 个并发实例，距离环境声用音量衰减而非无限实例；许可证元数据随构建产物审计，不含用户数据。

## 10. 验收标准

- `REQ-RENDER-010`：三区域、室内、昼夜、天气和 encounter 状态的交叉淡入正确；所有发布音频均有可追踪许可证。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-010` | Audio State transition、autoplay 恢复、并发上限，以及 audio asset → LicenseRecord → license text path/hash 的完整 license lint。 |

## 12. 关联文档

- `DOC-RENDER-007`：昼夜天气视觉
- `DOC-RENDER-011`：Asset Manifest

---
doc_id: DOC-RENDER-001
title: Phaser 渲染架构
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - phaser-scene-architecture
  - render-event-consumption
  - camera-render-contract
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-006
  - DOC-WORLD-009
requirements:
  - REQ-RENDER-001
last_updated: 2026-07-26
---

# Phaser 渲染架构

## 1. 目的

定义 Phaser 3 / TypeScript Client 的 Scene 边界、相机和已提交事件的表现消费方式；Client 只渲染 Authority Server 已提交的状态。

## 2. 非目标

不定义世界规则、导航、地图图像生成或后端 Repository；不从像素推断 Collision。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `BootScene` | 建立字体、通用占位和配置的短生命周期 Scene。 |
| `PreloadScene` | 按 Asset Manifest 加载当前 Scene 的必需资源。 |
| `WorldScene` | 一个 region 或 interior 的地图、实体和相机容器。 |
| `UIScene` | 常驻、屏幕空间的羊皮纸 HUD 与对话层。 |
| Render Event | 可合并的表现指令，绝不成为规则事实。 |

## 4. 规则与不变量

- `RULE-RENDER-001`：`BootScene -> PreloadScene -> WorldScene + UIScene` 是唯一启动次序；WorldScene 不直接写世界状态。
- `RULE-RENDER-002`：每个 `WorldScene` 仅消费匹配 `scene_id`、已确认 Revision 的 Snapshot/Event；过期事件丢弃。
- `RULE-RENDER-003`：相机使用 `WorldPoint`（1 tile = 32 wu），缩放或 fullscreen 不改变规则坐标。

## 5. 数据与接口

`DES-RENDER-001`：客户端接收只读 `RenderFrameInput`：

```json
{"scene_id":"region.crown_creek_town","revision":42,"render":{"camera_target":{"x_wu":1024,"y_wu":768},"entities":[{"entity_id":"01K1AB2CD3EF4GH5JK6MNP7QRS","asset_id":"sprite.resident.apothecary","animation_id":"anim.resident.walk_south"}]}}
```

## 6. 正常流程

1. `BootScene` 注册 fallback 与显示配置；`PreloadScene` 校验当前 Manifest。
2. `WorldScene` 建立五层容器、相机边界和 entity pool。
3. Snapshot 首次水合，再按 Revision 应用 Render Event。
4. `UIScene` 读取投影状态并在 scene transfer 时保持常驻。

## 7. 边界情况

浏览器恢复、WebSocket 重连或 Snapshot 替换时，销毁旧插值队列并按新 Revision 重建；不得补播旧 VFX。

## 8. 错误与降级

资源或动画缺失时使用 `asset.fallback.checkerboard`、`anim.fallback.idle_south`，同时输出结构化客户端诊断；核心交互继续可用。

## 9. 安全与性能

不渲染 Secret、原始模型推理或未授权私密字段；entity 与 VFX 复用对象池，目标 60 FPS。

## 10. 验收标准

- `REQ-RENDER-001`：Cold start、scene transfer 与重连均只建立一个 UIScene，WorldScene 只消费权威 Revision。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-001` | Playwright 验证启动顺序、scene transfer 与 stale Revision 丢弃。 |

## 12. 关联文档

- `DOC-RENDER-002`：Scene 生命周期
- `DOC-RENDER-003`：五层合成
- `DOC-FOUNDATION-002`：权威数据流

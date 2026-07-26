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
| `UIScene` | 常驻 UI orchestrator；Canvas 装饰与 DOM overlay 通过 bridge 同步，详细边界见 `DOC-RENDER-009`。 |
| `RenderFrameInput` | 某 world/scene 在完整 Revision 上的原子 Snapshot replacement。 |
| `RenderEventEnvelope` | 由 Backend/Orchestrator 从已提交 DomainEvent 映射的只读表现信封。 |
| Applied Revision | Client 已完整应用的最高连续 Revision；不表示 Client 可提交规则事实。 |

## 4. 规则与不变量

- `RULE-RENDER-001`：`BootScene -> PreloadScene -> WorldScene + UIScene` 是唯一启动次序；WorldScene 不直接写世界状态。Resident/Combat/Magic/Event/Time/Player/Dialogue owner 的事件只能由 Backend/Orchestrator 映射为本文件的 immutable render projection。
- `RULE-RENDER-002`：每个 `WorldScene` 只消费 protocol/world/scene 匹配且 Revision 连续的 Snapshot/Event；以 `(world_id,event_id)` 去重，过期、重复或有缺口的输入不得部分应用。
- `RULE-RENDER-003`：entity、camera、VFX target 均使用完整 `WorldPoint`（1 tile = 32 wu）；`scene_id` 必须等于 envelope 的 `scene_id`，缩放或 fullscreen 不改变规则坐标。

## 5. 数据与接口

`DES-RENDER-001`：Snapshot entity projection、camera target 与 event envelope 是 canonical RENDER contract。数字必须有限，坐标按 Foundation 量化到 `1/16 wu`；`facing_degrees` 仅允许 `0/90/180/270`。

完整 Snapshot replacement：

```json
{
  "protocol_version": "render.v1",
  "snapshot_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "snapshot_content_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e26f3ea47c190a9b18aab45",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "scene_id": "region.crown_creek_town",
  "revision": 42,
  "game_time": 1830,
  "camera_target": {
    "scene_id": "region.crown_creek_town",
    "x_wu": 1024.0,
    "y_wu": 768.0
  },
  "entities": [{
    "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "asset_id": "sprite.resident.apothecary",
    "world_point": {
      "scene_id": "region.crown_creek_town",
      "x_wu": 1008.0,
      "y_wu": 752.0
    },
    "facing_degrees": 90,
    "desired_animation_state": {
      "animation_id": "anim.resident.walk_south",
      "state": "walk",
      "loop": true,
      "since_revision": 42
    }
  }]
}
```

增量 `RenderEventEnvelope`：

```json
{
  "protocol_version": "render.v1",
  "event_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "scene_id": "region.crown_creek_town",
  "revision": 43,
  "game_time": 1831,
  "causation_id": "01K1AB2CD3EF4GH5JK6MNP7QRX",
  "correlation_id": "01K1AB2CD3EF4GH5JK6MNP7QRY",
  "transaction_event_index": 0,
  "transaction_event_count": 1,
  "render": {
    "kind": "entity_animation_changed",
    "entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "world_point": {
      "scene_id": "region.crown_creek_town",
      "x_wu": 1016.0,
      "y_wu": 752.0
    },
    "facing_degrees": 90,
    "desired_animation_state": {
      "animation_id": "anim.resident.walk_east",
      "state": "walk",
      "loop": true,
      "since_revision": 43
    }
  }
}
```

`transaction_event_index` 从 0 连续递增且小于 `transaction_event_count`；Client 收齐同一 Revision 的全部 event 后才原子应用并推进 Applied Revision。`event_id` 是 source DomainEvent ID，不允许生成仅限 Client 的替代 ID。
`snapshot_content_sha256` 是排除该字段后，对 RFC 8785 JSON Canonicalization Scheme 字节计算的 lowercase SHA-256，用于识别同 Revision replacement 是否内容一致。

## 6. 正常流程

1. `BootScene` 注册 fallback 与显示配置；`PreloadScene` 校验当前 Manifest。
2. `WorldScene` 建立五层容器、相机边界和 entity pool。
3. 验证 Snapshot 的 protocol/world/scene/坐标；当其 Revision 大于或等于当前 Snapshot Revision 时，单帧原子替换 entity/camera，清空插值与一次性 VFX 队列，并删除所有 `revision <= snapshot.revision` 的待处理 event。
4. event 先校验 `(world_id,scene_id)`，再查 `(world_id,event_id)` dedupe set，然后按 `(revision,transaction_event_index,event_id)` 排序；`revision <= snapshot.revision` 丢弃，下一 Revision 有缺口或 event count 不完整时停止应用并请求新 Snapshot。
5. 同一 Revision 全部 event 应用后推进 Applied Revision；dedupe set 每 world/scene 保留最近 10,000 个 ID 且最长 30 RealTime 分钟，先达到任一上限即 LRU/TTL 淘汰。即使 ID 已淘汰，Snapshot Revision gate 仍禁止历史 VFX 重播。
6. `UIScene` 读取同 Revision 的已授权 UI projection，并在 scene transfer 时保持常驻。

## 7. 边界情况

浏览器恢复或 WebSocket 重连先暂停增量消费并请求 Snapshot；Snapshot 原子替换完成前不显示新 Scene。低于当前 Snapshot Revision 的 replacement 拒绝；同 Revision replacement 仅在 `snapshot_id` 不同且内容 hash 一致时接受幂等重放，hash 不一致视为 contract error。

## 8. 错误与降级

资源或动画缺失时使用 `asset.fallback.checkerboard`、`anim.fallback.idle_south`，同时输出结构化客户端诊断；核心交互继续可用。

## 9. 安全与性能

不渲染 Secret、原始模型推理或未授权私密字段；entity 与 VFX 复用对象池，目标 60 FPS。

## 10. 验收标准

- `REQ-RENDER-001`：Cold start、scene transfer 与重连均只建立一个 UIScene；Snapshot replacement、连续 Revision、同 Revision 多 event、stale discard 与 `(world_id,event_id)` dedupe 可确定重放。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-001` | Contract + Playwright 验证启动顺序、Snapshot 原子替换、完整 WorldPoint/camera schema、同 Revision event 排序、Revision gap 请求重同步、30 分钟/10,000 ID 去重窗口及 stale/VFX 丢弃。 |

## 12. 关联文档

- `DOC-RENDER-002`：Scene 生命周期
- `DOC-RENDER-003`：五层合成
- `DOC-FOUNDATION-002`：权威数据流

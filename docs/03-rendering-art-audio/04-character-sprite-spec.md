---
doc_id: DOC-RENDER-004
title: 角色 Sprite 与肖像规格
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - character-sprite-contract
  - four-direction-walk-cycle
  - portrait-rendering
depends_on:
  - DOC-RENDER-003
  - DOC-RESIDENT-002
requirements:
  - REQ-RENDER-004
last_updated: 2026-07-26
---

# 角色 Sprite 与肖像规格

## 1. 目的

定义居民、玩家和战斗单位的可替换 Sprite/Portrait 合约，使身份外观与规则身份分离。

## 2. 非目标

不定义种族、职业、装备属性或伤害数值；不要求模仿特定在世艺术家风格。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Direction | `north`、`east`、`south`、`west` 四个朝向。 |
| Walk cycle | 每方向恰好 6 帧、循环的移动动画。 |
| Idle frame | 每方向首帧静止图；无独立 idle 资源时使用 walk 第 0 帧。 |
| Portrait | 对话/状态面板用方形半身肖像，不参与地图碰撞。 |

## 4. 规则与不变量

- `RULE-RENDER-010`：地图 Sprite 的每个方向必须有 6 帧；方向只由已确认 facing 转换，禁止由视觉猜测。
- `RULE-RENDER-011`：Sprite anchor 固定为脚底中点，`WorldPoint` 始终对应 anchor；碰撞由 MAP 数据决定。
- `RULE-RENDER-012`：素材名称只用 Stable Catalog ID，例如 `sprite.resident.apothecary`，不得把 locale 文案写入 ID。

## 5. 数据与接口

`DES-RENDER-004`：

```json
{"asset_id":"sprite.resident.apothecary","portrait_asset_id":"portrait.resident.apothecary","frame_size_px":{"width":32,"height":48},"walk_frames_per_direction":6,"directions":["north","east","south","west"]}
```

## 6. 正常流程

1. Resident appearance projection 给出 sprite、portrait 与 palette variant ID。
2. `WorldScene` 注册 texture atlas，按 facing 选择动画 key。
3. `UIScene` 以 portrait ID 渲染对话和镇民卡片，缺失时显示通用剪影。

## 7. 边界情况

长袍、披风等超出脚底的像素只影响 visual bounds；选择框与交互热点仍以服务器实体位置为准。

## 8. 错误与降级

某方向或 portrait 缺失时使用相同实体的 `south` idle；全部缺失时使用 `asset.fallback.resident_silhouette`，保留名字与状态。

## 9. 安全与性能

同一 atlas 的重复居民共享纹理；肖像按面板打开 lazy load；资源许可证、作者、来源和 hash 必须进入 Manifest。

## 10. 验收标准

- `REQ-RENDER-004`：每个可见角色通过四方向、六帧、idle、portrait 和 combat-sprite 完整性检查。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-004` | Asset lint 校验方向/帧数/anchor，Visual QA 截图验证脚底定位。 |

## 12. 关联文档

- `DOC-RENDER-005`：动画状态机
- `DOC-RENDER-011`：资源 Manifest

---
doc_id: DOC-RENDER-008
title: 魔法与战斗 VFX
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - vfx-registration
  - combat-vfx-lifecycle
  - vfx-accessibility
depends_on:
  - DOC-RENDER-005
  - DOC-FOUNDATION-002
requirements:
  - REQ-RENDER-008
last_updated: 2026-07-26
---

# 魔法与战斗 VFX

## 1. 目的

定义已确认 Spell/Combat result 的 VFX 注册、播放和清理合约，使即时反馈不改变回合或伤害事实。

## 2. 非目标

不定义法术数值、命中判定、伤害公式或行动合法性。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `vfx_id` | 注册表稳定 ID，如 `vfx.arcane.spark_burst`。 |
| Attach point | `caster_feet`、`target_center`、`ground_point` 三种投放锚点。 |
| Impact VFX | 已确认命中/治疗/状态结果的视觉反馈。 |

## 4. 规则与不变量

- `RULE-RENDER-022`：VFX 仅由已提交 render event 创建，预测输入不得产生目标命中视觉。
- `RULE-RENDER-023`：每个 VFX 必须声明最大 `duration_ms`（100–1500），结束或 scene Dispose 时释放对象池。
- `RULE-RENDER-024`：闪光、抖动和屏幕遮罩均受 Reduced Motion 控制，改用边框/图标提示。

## 5. 数据与接口

`DES-RENDER-008`：

```json
{"vfx_id":"vfx.arcane.spark_burst","asset_id":"vfx.arcane.spark_atlas","attach_point":"target_center","duration_ms":420,"render":{"blend_mode":"add","z_policy":"above_entities"}}
```

Magic/Combat owner 的已提交结果由 Backend/Orchestrator 映射为上述 render payload；RENDER 不 import Spell、Encounter 或 damage schema。

## 6. 正常流程

1. 解析 event 的 VFX ID、anchor 与 Revision。
2. 从 pool 取得 emitter/sprite，按 z policy 置入 map composite 层。
3. 播放后在 `duration_ms` 回收；同一 event ID 只能播放一次。

## 7. 边界情况

目标离开 Scene、事件乱序或 scene transfer 时立即回收；不能为了完整播放而保留旧 Scene。

## 8. 错误与降级

未知 VFX 退回 `vfx.fallback.status_ping`：目标边框与非闪烁图标；不会吞掉原 event。

## 9. 安全与性能

每 Scene 活跃 VFX 上限 96，超过时先合并同类非关键环境效果，战斗命中与状态效果优先；不含私密 payload 文本。

## 10. 验收标准

- `REQ-RENDER-008`：所有注册 VFX 在重复、断线、转场和 Reduced Motion 下只播放一次且无泄漏。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-008` | Event 去重、pool 回收、96 上限及可访问性截图回归。 |

## 12. 关联文档

- `DOC-RENDER-005`：动画状态机
- `DOC-RENDER-007`：天气视觉
- 非 direct owner：Magic/Combat 仅通过 `DOC-RENDER-001` RenderEvent envelope 提供表现输入。

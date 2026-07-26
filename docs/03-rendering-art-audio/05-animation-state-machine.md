---
doc_id: DOC-RENDER-005
title: 动画状态机与缺失动画降级
version: 1.0.0
status: approved-for-implementation
owner_domain: rendering-art-audio
canonical_for:
  - animation-state-machine
  - animation-mapping
  - missing-animation-fallback
depends_on:
  - DOC-RENDER-004
  - DOC-COMBAT-003
  - DOC-MAGIC-004
requirements:
  - REQ-RENDER-005
last_updated: 2026-07-26
---

# 动画状态机与缺失动画降级

## 1. 目的

将权威 render projection 映射为可预测动画，避免 Client 用动画完成与否推断战斗或施法结果。

## 2. 非目标

不定义 Action/Spell 合法性或战斗结算；动画绝不回写 server。

## 3. 术语与定义

| 状态 | 含义 |
|---|---|
| `idle` | 原地静止，保留最后确认 direction。 |
| `walk` | 按 render delta 插值移动。 |
| `cast` / `attack` | 表现一次已确认 action 的短暂非循环动画。 |
| `hurt` / `downed` | 已确认受击或非永久失败表现。 |

## 4. 规则与不变量

- `RULE-RENDER-013`：优先级为 `downed > hurt > attack/cast > walk > idle`，同优先级以最新 Revision 覆盖。
- `RULE-RENDER-014`：`attack/cast/hurt` 最大表现 900 ms，结束必回当前权威 locomotion 状态。
- `RULE-RENDER-015`：缺失特殊动画不得阻塞 input、事件消费或下一状态。

## 5. 数据与接口

`DES-RENDER-005`：Animation Mapping key 是 `animation_id`，例如 `anim.resident.cast_east`，value 包含 atlas frame range、fps、loop 与 fallback key；映射在构建期唯一。

## 6. 正常流程

1. 将每个 render event 归并为实体的最新 desired state。
2. 依据优先级切换 Phaser animation；walk 使用目标位置插值。
3. 非循环动作完成后读取最新 projection，而非假定状态。

## 7. 边界情况

同 Revision 同时有移动和受击时播放 hurt，但位置仍平滑收敛；新 Revision 的 downed 立即中断其他动画。

## 8. 错误与降级

找不到 `animation_id` 时按 `idle_north`、`idle_east`、`idle_south`、`idle_west` 中与当前朝向对应者，再按 `anim.fallback.idle_south`；只记录一次每 asset/scene 的诊断以免刷屏。

## 9. 安全与性能

每实体最多一个 active tween 与一个 animation；对象回收时停止 tween，防止离区对象继续更新。

## 10. 验收标准

- `REQ-RENDER-005`：所有注册动作在中断、乱序和缺失 mapping 下仍在 900 ms 内回到权威可见状态。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RENDER-005` | 状态优先级、900 ms 回退、乱序 Revision 和 fallback unit test。 |

## 12. 关联文档

- `DOC-RENDER-004`：角色素材
- `DOC-RENDER-008`：战斗与魔法 VFX

---
doc_id: DOC-RESIDENT-007
title: 健康、受伤、疾病与昏迷
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-persistent-health
  - injury-illness-lifecycle
  - unconscious-state
depends_on:
  - DOC-FOUNDATION-005
  - DOC-WORLD-010
  - DOC-RESIDENT-004
  - DOC-RESIDENT-005
requirements:
  - REQ-RESIDENT-007
last_updated: 2026-07-26
---

# 健康、受伤、疾病与昏迷

## 1. 目的

`REQ-RESIDENT-007`：定义居民持久 Health、Injury、Illness、Unconscious 状态、限制与恢复；COMBAT 拥有 damage/healing 数值结果，Resident 只验证并应用已提交效果。

## 2. 非目标

不定义命中、伤害、治疗量、Status Effect 或法术；不允许模型直接设置 HP/疾病，不以医学现实作为诊断输出。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Health State | `healthy/impaired/unconscious/recovering`；`captive` 属于 DOC-RESIDENT-008 的 lifecycle state，不是健康诊断 |
| Injury | `injury.*` 定义的持久伤情实例 |
| Illness | `illness.*` 定义的病程实例 |
| Health Effect | COMBAT/MAGIC/EVENT 等 owner 已结算的 delta/状态命令 |
| Restriction | 对 capability 的明确禁用/倍率投影，不直接选择行动 |

## 4. 数据与接口

`DES-RESIDENT-007`：

```json
{
  "health_schema_version": 1,
  "state": "impaired",
  "hp_current": 12,
  "hp_max": 30,
  "injuries": [{
    "injury_id":"01K1AB2CD3EF4GH5JK6MNP7QRC",
    "definition_id":"injury.sprained_ankle",
    "severity_q1000":420,
    "source_event_id":"01K1AB2CD3EF4GH5JK6MNP7QRD",
    "recovery_progress_q1000":100
  }],
  "illnesses": [],
  "restrictions": [{"capability_tag":"movement.fast","mode":"forbidden"}],
  "unconscious_reason": null,
  "health_revision": 11
}
```

`HealthEffectCommand` 必含 `source_event_id`、`effect_definition_id`、结算 owner、已结算 `hp_delta`/状态、`expected_revision`。

## 5. 规则与不变量

- `RULE-RESIDENT-035`：`0 <= hp_current <= hp_max` 且 `hp_max >= 1`；正式居民 HP 到 0 必须进入 `unconscious` 或 DOC-RESIDENT-008 的其他非永久后果。
- `RULE-RESIDENT-036`：damage/healing 数值只接受 COMBAT/MAGIC/EVENT owner 已结算效果；Resident 不重算、不接受 AI/Client 数值。
- `RULE-RESIDENT-037`：Injury/Illness 实例必须有 definition、source event、severity、恢复进度和明确退出条件。
- `RULE-RESIDENT-038`：unconscious 居民不能发起 move/work/talk/cast/start_encounter；允许被治疗、转运、营救和时间恢复。
- `RULE-RESIDENT-039`：相同 `(resident_id, source_event_id, effect_definition_id)` 最多应用一次。
- `RULE-RESIDENT-040`：Health restriction 只影响当前可用性，不删除 Skill、Ability、身份、Inventory 引用、Memory 或关系。

## 6. 正常流程

1. COMBAT/MAGIC/EVENT owner 结算并提交来源结果。
2. Orchestrator 传入不可变 Health Effect。
3. Resident 校验 owner、source Revision、幂等键、范围和生命周期。
4. 应用 HP、Injury/Illness、restriction；必要时进入 unconscious。
5. 生成 `ResidentHealthChanged`，TIME 排定恢复检查，AI 收到合法能力投影。

## 7. 边界情况

- 同事务多种 effect 按 `source_event_id + effect_definition_id` 排序。
- Healing 超过上限截到 `hp_max`，但仍记录实际 applied delta。
- Illness 恢复中再次暴露可增加 severity；不得生成重复实例，除非 Catalog 允许多株。
- Unconscious 时 arrival 位置仍须 MAP 合法；转运失败不改变位置。

## 8. 错误与降级

返回 `RESIDENT_HEALTH_SOURCE_FORBIDDEN`、`RESIDENT_HEALTH_EFFECT_DUPLICATE`、`RESIDENT_HEALTH_RANGE_INVALID`、`RESIDENT_RECOVERY_CONDITION_MISSING`。未知 effect 不猜测；保持状态并请求 owner 重放/修复。

## 9. 安全与性能

玩家可见文本使用克制内容标签，不暴露模型推理或私人病史。每居民 Injury+Illness 活跃实例上限 32；长期历史保存在事件日志，不内嵌聚合。

## 10. 验收标准

- combat damage 在 Resident 仅应用一次且数值不重算。
- HP=0 永不产生 death/delete。
- unconscious 合法/非法命令矩阵准确。
- 恢复后 Skill/Ability/身份保持不变。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-025` | HP 上下界、overheal 与 effect 幂等 |
| `TEST-RESIDENT-026` | COMBAT-owned damage 边界 Contract Test |
| `TEST-RESIDENT-027` | unconscious 命令能力矩阵 |
| `TEST-RESIDENT-028` | Injury/Illness 恢复与持久数据保留 |

## 12. 关联文档

- `DOC-WORLD-010`：内容与后果边界
- `DOC-RESIDENT-008`：非永久失败状态机
- `DOC-COMBAT-006`：damage/healing canonical owner

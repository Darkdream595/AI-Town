---
doc_id: DOC-RESIDENT-008
title: 年龄阶段与非永久死亡
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-age-stage
  - non-permanent-defeat-lifecycle
  - captivity-reference
depends_on:
  - DOC-FOUNDATION-005
  - DOC-WORLD-010
  - DOC-RESIDENT-007
requirements:
  - REQ-RESIDENT-008
last_updated: 2026-07-26
---

# 年龄阶段与非永久死亡

## 1. 目的

`REQ-RESIDENT-008`：定义首版年龄阶段和正式居民非永久失败状态机，保证战斗、灾害、疾病与剧情均不能永久删除正式 Resident，并为恢复设置非零成本和可达退出路径。

## 2. 非目标

首版不模拟出生、未成年人、自然老死或后代；不定义战斗失败选择算法、赎金、医疗价格或监狱规则。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Age Stage | 首版仅 `adult`、`mature`、`elder` |
| Defeat State | `unconscious/severely_injured/retreated/captive` |
| Captivity Reference | EVENT/WORLD 法律 owner 的持有方、地点、复核与退出条件引用 |
| Recovery Cost | GameTime、资源、限制、许可、关系修复或风险至少一项 |
| `active` | 可参与常规生活的生命周期状态 |

## 4. 数据与接口

`DES-RESIDENT-008`：

```json
{
  "age_stage":"adult",
  "age_stage_since_game_time":0,
  "lifecycle_state":"captive",
  "defeat":{
    "defeat_id":"01K1AB2CD3EF4GH5JK6MNP7QRE",
    "state":"captive",
    "source_event_id":"01K1AB2CD3EF4GH5JK6MNP7QRF",
    "started_at_game_time":1900,
    "holder_entity_id":"faction.ashen_band",
    "location_id":"semantic_node.forest.bandit_camp",
    "review_at_game_time":2260,
    "exit_condition_ids":["condition.rescued","condition.negotiated_release","condition.escaped"],
    "minimum_cost_tags":["risk"]
  }
}
```

状态机：

```text
active/recovering
  -> unconscious | severely_injured | retreated | captive
  -> recovering
  -> active
```

不存在 `dead/deleted/permadeath` 状态或转移。

## 5. 规则与不变量

- `RULE-RESIDENT-041`：正式 Resident aggregate 永不物理删除、永不进入 death terminal、永不以同名替代角色复位。
- `RULE-RESIDENT-042`：每个 defeat 必有 source event、起始 GameTime、至少一个退出条件与至少一个非零 cost tag。
- `RULE-RESIDENT-043`：captivity 必有 holder、location、`review_at_game_time` 和退出条件；review 最迟为开始后 1440 游戏分钟。
- `RULE-RESIDENT-044`：恢复只能经已提交治疗、营救、撤退完成、释放或适应事件推进；不能因加载/重启自动满状态。
- `RULE-RESIDENT-045`：Age Stage 只由版本化 World/Resident 规则与 GameTime 事件改变，不从现实时间推进；首版无死亡终点。
- `RULE-RESIDENT-046`：Defeat 不清空 Inventory、Skill、Memory、关系、职业历史或承诺；外部 owner 单独处理合法转移/暂停。

## 6. 正常流程

1. COMBAT/EVENT 结算致命或失败结果，提供合法 defeat outcome ID。
2. Resident 根据当前位置、结果与规则校验目标状态。
3. 原子写入 defeat、Health/lifecycle 限制及 `ResidentDefeated`。
4. TIME 排定 review/recovery，事件系统产生治疗、营救或协商路径。
5. 满足退出条件并付出记录成本后转 `recovering`，最终回 `active`。

## 7. 边界情况

- 全队失败可为不同居民选择不同合法 outcome。
- Holder 被移除或 location 不可达时，review 触发安全 relocation/释放流程，不删除 Resident。
- 无治疗资源时生成求助与长期限制，不能永久锁死。
- 旧事件含 `dead` 枚举时 Migration 必须停止并要求显式 upcast 到可审计 defeat state。

## 8. 错误与降级

遇到 death/delete、零成本恢复、无退出条件 captivity 返回 `RESIDENT_PERMANENT_DEATH_FORBIDDEN`。模型不可用时采用确定性优先序：有安全盟友则 unconscious；可撤离则 retreated；敌方有效且有 review 则 captive；否则 severely_injured。

## 9. 安全与性能

表现遵守 `DOC-WORLD-010` restrained 内容边界。状态机枚举封闭，恢复审计全量检查，不允许 Admin 绕过正式 Resident 不变量。

## 10. 验收标准

- 任意致命输入都映射到四个非永久 outcome 之一。
- 保存/重载、模型离线、全队失败均保留同一 Resident ID。
- captivity 具有 review 与可达退出路径。
- 恢复至少消耗一项有事件证据的成本。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-029` | 致命值 Property Test 无 dead/delete |
| `TEST-RESIDENT-030` | 四 outcome 状态机可达性与不可达非法边 |
| `TEST-RESIDENT-031` | captivity review/holder失效/不可达恢复 |
| `TEST-RESIDENT-032` | reload 与离线模型保持 ID 和非零成本 |

## 12. 关联文档

- `DOC-WORLD-010`：非永久失败语义
- `DOC-RESIDENT-007`：Health 状态
- `DOC-COMBAT-009`：战斗 outcome owner
- `DOC-EVENT-005`：Aftermath 与营救


---
doc_id: DOC-MAGIC-009
title: 魔法环境交互
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-effect-handler-registry
  - magic-environment-interfaces
  - world-magic-effect-instances
depends_on:
  - DOC-MAGIC-004
  - DOC-RESIDENT-007
  - DOC-MAP-010
  - DOC-WORLD-008
  - DOC-FOUNDATION-005
requirements:
  - REQ-MAGIC-017
  - REQ-MAGIC-018
last_updated: 2026-07-26
---

# 魔法环境交互

## 1. 目的

定义 `magic.effect.*` handler 注册表——火、治疗、净化、侦测、光照、强化、锚点、幻象、诅咒——的结算契约、目标 owner 路由与持续效果实例模型，落实关键不变量：所有法术效果必须注册制，任何自由文本效果都不能改动世界。

## 2. 非目标

本文件不定义被路由 owner 的内部规则（火灾蔓延归 EVENT、HP 应用归 RESIDENT、建筑状态归 EVENT、导航更新归 MAP）；不定义战斗内伤害数值（`DOC-COMBAT-004/006`）；不定义表现（`DOC-MAGIC-011`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Effect Handler | `magic.effect.*` 注册的确定性结算函数，输入为 Catalog 参数与世界状态 |
| Owner 路由 | handler 结算后向目标 domain owner 发出的结构化命令/事件 |
| `WorldMagicEffectInstance` | MAGIC 拥有的持续性效果实例（光照、锚点、幻象、诅咒等） |
| 即时效果 | 结算即终结、无持续实例的效果（治疗、点火、侦测） |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-017` | Effect Handler 集合是封闭注册表：首版恰好 12 个 handler（§5.1）；每个 handler 声明 strict 参数子 Schema、目标 owner、产出事件类型与撤销语义，未注册 `effect_id` 在构建期与运行时双重拒绝。 |
| `REQ-MAGIC-018` | Handler 只能通过目标 owner 的公开命令接口改动世界（治疗走 `HealthEffectCommand`、点火走 EVENT 火源命令、导航影响走 MAP Navigation Modifier）；禁止 handler 直接写他域存储或绕过 `DOC-FOUNDATION-005` 不变量。 |
| `RULE-MAGIC-046` | 火焰接口：`ignite` 只能点燃 EVENT 注册的可燃点（炉灶、火盆、篝火位、可燃物）；`extinguish` 只作用于活动火源。野火蔓延、损毁与灾害升级完全归 EVENT，MAGIC 不结算蔓延。 |
| `RULE-MAGIC-047` | 治疗与净化接口：`heal_minor/cure_illness/curse_weariness` 以 MAGIC 结算数值、经 `RULE-RESIDENT-036` 的 owner 通道应用；诅咒登记为 `illness.arcane_weariness` 病程实例，必须声明明确退出条件（时限或 `cure_illness` 解除），无永久诅咒。 |
| `RULE-MAGIC-048` | 侦测接口：`detect_magic` 只揭示半径内已标记 `detectable` 的结构化事实（活动效果实例、magical Item 存在、异常区边界），产出 MEMORY 观察输入；不揭示 Secret、所有权明细或未标记事实（`RULE-FOUNDATION-024`）。 |
| `RULE-MAGIC-049` | 光照与幻象是感知/表现层效果：`conjure_light` 影响夜间感知半径与 render，`veil_illusion` 只改变观察者感知内容并可被 `detect_magic` 识破；二者不得改变 Walkability、Collision、火源或任何 owner 真值（`RULE-WORLD-034` 的伪造禁令同时适用）。 |
| `RULE-MAGIC-050` | 强化与锚点接口：`reinforce_structure` 向 EVENT 提交建筑维护命令（降低衰减/损伤系数，时限内有效）；`place_ley_anchor` 创建持久 `WorldMagicEffectInstance` 提升半径内 `ley_anchor_presence`（`RULE-MAGIC-011`），放置点需土地权限且每 Scene 上限 2 个活动锚点。 |
| `RULE-MAGIC-051` | 每个 `WorldMagicEffectInstance` 必须声明 `duration_game_minutes`（锚点上限 10080，其余上限 1440）与到期清理事件，由 `DOC-TIME-008` 到期队列驱动；不存在无限期效果实例。 |
| `RULE-MAGIC-052` | Handler 结算与 `SpellCastCommitted` 同一事务原子成败；路由 owner 前置失败（火点被占用、目标已满血且定义禁止过量）时整次施法拒绝，不产生半效果。 |
| `RULE-MAGIC-053` | 灵体接口：`soothe_spirit` 只作用于 EVENT 管理的灵体实体并遵守其同意/Reservation 规则（`DOC-MAGIC-001` 术语），效果为结构化安抚状态，不能命令灵体执行任意行为。 |

## 5. 数据与接口

### 5.1 Handler 注册表

`DES-MAGIC-009`：

| `effect_id` | 类别 | 目标 owner | 产出 |
|---|---|---|---|
| `magic.effect.ignite` | 即时 | EVENT | `FireSourceIgnited` |
| `magic.effect.extinguish` | 即时 | EVENT | `FireSourceExtinguished` |
| `magic.effect.heal_minor` | 即时 | RESIDENT | `HealthEffectCommand`（正向 hp_delta） |
| `magic.effect.cure_illness` | 即时 | RESIDENT | 病程/诅咒实例移除 |
| `magic.effect.purify_anomaly` | 即时 | EVENT | 异常区净化进度事件 |
| `magic.effect.reinforce_structure` | 持续（EVENT 侧） | EVENT | 建筑维护系数命令 |
| `magic.effect.place_ley_anchor` | 持续实例 | MAGIC（+MAP 只读标记） | `WorldMagicEffectInstance` |
| `magic.effect.detect_magic` | 即时 | MEMORY | 结构化观察输入 |
| `magic.effect.conjure_light` | 持续实例 | MAGIC | 光照实例（感知+render） |
| `magic.effect.veil_illusion` | 持续实例 | MAGIC | 幻象实例（仅感知面） |
| `magic.effect.soothe_spirit` | 即时 | EVENT | 灵体安抚状态事件 |
| `magic.effect.curse_weariness` | 持续（RESIDENT 侧） | RESIDENT | `illness.arcane_weariness` 实例 |

### 5.2 持续效果实例

注册 `schema.magic.world_effect_instance.v1`：

```json
{
  "effect_schema_version": 1,
  "effect_instance_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "effect_id": "magic.effect.place_ley_anchor",
  "caster_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "position": {"scene_id": "region.crown_creek_town", "x_wu": 512.0, "y_wu": 640.0},
  "radius_wu": 128.0,
  "detectable": true,
  "expires_at_game_time": 12960,
  "source_event_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "state": "active",
  "instance_revision": 3
}
```

`state` 枚举：`active/expired/dispelled`。净化类效果可将他人实例转为 `dispelled`，同样经命令管线提交。

## 6. 正常流程

1. 施法通过七级校验后，事务内按 `effect_bindings` 顺序调用 handler。
2. Handler 用 Catalog 参数 + 施法者 SchoolSkill rating 确定性结算数值（如 `heal = heal_base + floor(rating/25) * skill_scale_per_25_rating`）。
3. 路由 owner 在同事务校验并应用（或创建 `WorldMagicEffectInstance`），产出各自 DomainEvent。
4. TIME 到期队列在 `expires_at_game_time` 触发清理，提交 `MagicEffectExpired` 并撤销派生修正。

## 7. 边界情况

- 治疗目标已满血：`heal_minor` 声明 `allow_overheal=false`，第 6 步前置失败拒绝整次施法，提示改选目标。
- 点火目标处于雨天：EVENT 可燃点状态含天气修正，湿透状态下 `ignite` 前置失败——天气影响经结构化状态传导，不是 handler 自由裁量。
- 锚点重叠：新锚点半径与既有活动锚点相交时拒绝放置，`ley_anchor_presence` 不叠加。
- 幻象与导航：NPC 因幻象产生的错误 Belief 可能改变其路径选择，但 MAP 的 Walkability/Collision 真值不变；碰撞判定永远以真值为准。
- 施法者离线/离场：持续实例不依赖施法者在场，按自身时限存续。

## 8. 错误与降级

未知 `effect_id` 或参数 strict decode 失败在注册期阻断；运行时路由 owner 返回的拒绝原因原样并入 `CastRejection`。到期清理失败进入重试队列，实例保持 `active` 但超期实例不再提供修正（读取侧按 `expires_at_game_time` 判定），保证降级安全。

## 9. 安全与性能

Handler 为纯函数 + owner 命令，禁止网络调用与跨世界读取。每 Scene 活动 `WorldMagicEffectInstance` 上限 32，超限拒绝新实例。侦测结果按目击者视角过滤后进入 MEMORY，不产生全知投影。效果实例索引按 `(scene_id, state)` 构建，恢复审计重建修正 overlay 而非信任缓存。

## 10. 验收标准

- 12 个 handler 与 `DOC-MAGIC-004` §5.2 的 effect 引用集合完全闭合，无孤儿与缺失。
- 每类环境接口（火/治疗/净化/侦测/光照/强化/锚点/幻象/诅咒）各有至少一个端到端 fixture：施法 → owner 事件 → 状态断言。
- 幻象/光照运行期间 MAP 真值逐字段不变。
- 全部持续实例到期后世界修正回到基线，无残留。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-019` | `REQ-MAGIC-017..018`, `RULE-MAGIC-052` | 注册表闭合审计；handler 直写他域存储的静态检查反例；原子性注入测试 |
| `TEST-MAGIC-020` | `RULE-MAGIC-046..048`, `RULE-MAGIC-053` | 火/治疗/诅咒/侦测/灵体路由 Integration Test 与 Secret 泄漏断言 |
| `TEST-MAGIC-021` | `RULE-MAGIC-049..051` | 幻象/光照真值不变性 Property Test；锚点权限、上限与到期清理 |

## 12. 关联文档

- `DOC-MAGIC-004`：effect binding 的声明侧
- `DOC-MAGIC-003`：`ley_anchor_presence` 对恢复的作用
- `DOC-RESIDENT-007`：Health Effect 应用通道
- `DOC-MAP-010`：动态修正与真值层边界
- `DOC-TIME-008`：到期清理队列
- `DOC-EVENT-006`：天气对可燃状态的传导

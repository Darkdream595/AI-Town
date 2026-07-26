---
doc_id: DOC-AI-005
title: 首版 Action Catalog 与 Domain 所有权
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - action-catalog-v1
  - action-validation-owner-map
depends_on:
  - DOC-AI-004
  - DOC-MAP-007
  - DOC-TIME-006
  - DOC-ECON-006
requirements:
  - REQ-AI-005
last_updated: 2026-07-26
---

# 首版 Action Catalog 与 Domain 所有权

## 1. 目的

`REQ-AI-005`：登记总体设计首版清单中的 19 个 Action 的参数 Schema 唯一引用、必要上下文、canonical validator、Reservation、提交结果和可渲染事件。

## 2. 非目标

Catalog 不是模型 tool execution；AI 不能新增 action、改变 owner 公式或绕过权限。参数字段唯一真源为 DOC-AI-004 `$defs`，本文不另建同名 Schema。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Action ID | Proposal wire enum，如 `move_to` |
| Parameters Ref | `schema.ai.action_proposal.v1#/$defs/<action>_parameters` |
| Semantic Validator | AI 边界的跨字段/引用可见性检查 |
| Domain Validator | 最新状态上决定动作是否可授权的 owner |
| Commit Adapter | 把 ValidatedIntent 转为 owner Command 的服务器组件 |

## 4. Catalog

`DES-AI-005`：

| Action | Parameters `$defs` | 必要顶层引用 | Canonical owner / 关键校验 | 典型 committed event |
|---|---|---|---|---|
| `move_to` | `move_to_parameters` | destination 按 kind | MAP：standable、path、navigation revision | `ActorMovementStarted` |
| `talk` | `talk_parameters` | target required | DIALOGUE：距离、语言、同意、会话状态 | `ConversationStarted` |
| `work` | `work_parameters` | destination/target optional | ECON+TIME：Contract、shift、地点、capacity | `WorkSessionStarted` |
| `rest` | `rest_parameters` | destination required | RESIDENT+TIME+MAP：健康、节点、长行动 | `RestStarted` |
| `eat` | `eat_parameters` | target null | ECON+RESIDENT：ownership、edible effect | `ItemConsumed` |
| `buy` | `buy_parameters` | seller+destination required | ECON：Quote、余额、Inventory、原子交易 | `TransactionCommitted` |
| `sell` | `sell_parameters` | buyer+destination required | ECON：ownership、Quote、买方余额 | `TransactionCommitted` |
| `give_item` | `give_item_parameters` | recipient required | ECON+SOCIAL：ownership、capacity、consent | `ItemTransferred` |
| `use_object` | `use_object_parameters` | object required | object owner+MAP：交互、距离、permission | owner-specific event |
| `craft` | `craft_parameters` | station destination required | ECON+TIME：Recipe、inputs、tool/station | `CraftOrderStarted` |
| `gather` | `gather_parameters` | resource target required | EVENT/ECON+TIME：node state、capacity、yield contract | `GatherActionStarted` |
| `explore` | `explore_parameters` | area destination required | MAP+EVENT：已知边界、可达、安全限制 | `ExplorationStarted` |
| `cast_spell` | `cast_spell_parameters` | varies by Spell | MAGIC：registered Spell、targets、mana、permission | `SpellCastCommitted` |
| `start_encounter` | `start_encounter_parameters` | primary target required | COMBAT+WORLD：合法原因、参与者、non-lethal rules | `EncounterStarted` |
| `combat_action` | `combat_action_parameters` | target optional by option | COMBAT：turn、legal option、targets | `CombatActionResolved` |
| `build` | `build_parameters` | parcel destination required | EVENT+WORLD+ECON+MAP：rights、permit、resources、footprint | `ConstructionPlanned` |
| `repair` | `repair_parameters` | structure required | EVENT+ECON+MAP：damage、materials、access | `RepairStarted` |
| `wait` | `wait_parameters` | target/destination null | TIME：duration、exclusive state、deadline | `WaitStarted` |
| `observe` | `observe_parameters` | subject required | MAP+MEMORY：感知、距离、visibility | `ObservationCompleted` |

所有 event 名是 consumer contract 的语义名；最终 payload 与 version 由 owner 文档定义。Renderer 只消费提交 Event Envelope 的 `render` projection。

### 4.1 跨字段语义表

| Action | 必须条件 |
|---|---|
| `move_to` | semantic node：`destination_id!=null, world_point absent/null`；world point：相反 |
| `talk/buy/sell/give_item/start_encounter` | `target_entity_id!=null` 且 actor 可见该引用 |
| `work/rest/buy/sell/craft/explore/build` | `destination_id!=null` |
| `eat/wait` | `target_entity_id=null, destination_id=null` |
| `combat_action` | 当前 actor/turn 必须由 Encounter projection 绑定，模型字段不得替代 |
| `cast_spell` | target/aim 组合由 SpellDefinition 决定，空 target 仅在 Spell 允许时合法 |

## 5. 规则与不变量

- `RULE-AI-025`：Action enum、`$defs`、Catalog 行与 fixture 集合必须精确相等，各 19 项。
- `RULE-AI-026`：每项 action 只有一个 Parameters Ref；其他文档只能引用，禁止复制/扩展 wire 字段。
- `RULE-AI-027`：AI semantic validation 只验证形状、可见引用与跨字段；Domain owner 在最新 Revision 做最终授权。
- `RULE-AI-028`：模型不得提供可信路径、damage、hit、price legs、yield、building footprint、permission 或 owner。
- `RULE-AI-029`：有副作用 action 使用 command ID、expected Revision、Reservation 与原子 DomainEvent；重放最多生效一次。
- `RULE-AI-030`：Catalog capability 由服务器按 actor 构建；Prompt 不展示当前 actor 不可能使用的 action，但隐藏不构成安全控制。

## 6. 正常流程

Capability Builder 合并 owner 发布的 action eligibility；Prompt 只得到候选 ID 与最小参数帮助；Proposal strict decode 后解析 stable/runtime references；Domain validator 生成 `authorized command plan`；TIME 按稳定 lock order Reservation；World Runtime 原子提交并发布 owner events。

## 7. 边界情况

目标可见但已改变、Quote 未取得、Door 关闭、Recipe/Spell 版本变更、玩家抢先占用资源都必须最新校验。可到达语义目标不等于可交互；模型要求“攻击”不能映射到任意 `use_object`；未知 action 不做相似名称猜测。

## 8. 错误与降级

Catalog/Schema digest 不符时启动失败。缺少 owner projection 时 action 不进入候选；返回后若 owner 不可用则 replan/fallback。禁止将 forbidden action 自动降格成另一有副作用 action。

## 9. 安全与性能

Catalog 为只读版本化 registry。能力投影按 actor/revision 缓存且不包含 secret reason；单次候选最多 20。验证器不调用外网，模型提供文本只能进入显式 string 字段。

## 10. 验收标准

- 19 行 Catalog 与 DOC-AI-004 discriminator 集合完全一致。
- 每项均能解析 owner、参数 ref、跨字段规则与 committed event class。
- 负例证明模型数值/权限/路径不被信任。
- 玩家与 AI 进入同一 owner validation/commit pipeline。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-017` | action/schema/catalog/fixture set equality |
| `TEST-AI-018` | cross-field semantic table |
| `TEST-AI-019` | 19 action owner Contract Tests |
| `TEST-AI-020` | Proposal 与 PlayerCommand rule parity |

## 12. 关联文档

- `DOC-AI-004`：唯一参数 Schema
- `DOC-AI-010`：校验 outcome
- `DOC-TIME-007`：Reservation

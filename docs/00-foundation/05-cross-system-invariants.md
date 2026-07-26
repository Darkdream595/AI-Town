---
doc_id: DOC-FOUNDATION-005
title: 跨系统不变量
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - cross-system-invariants
  - invariant-enforcement-policy
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
requirements:
  - REQ-PRODUCT-003
  - REQ-PRODUCT-004
  - REQ-PRODUCT-008
  - REQ-PRODUCT-009
  - REQ-PRODUCT-016
  - REQ-PRODUCT-018
  - REQ-PRODUCT-019
last_updated: 2026-07-26
---

# 跨系统不变量

## 1. 目的

定义任何正常流程、降级、恢复、管理命令或高倍速模拟都不得破坏的全局事实，并指定 owner、执行点和可验证结果。

## 2. 非目标

本文件不规定 domain 内部所有业务约束；只收录跨越两个以上 domain 或决定系统可信性的不可违反项。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Invariant | 在每次成功事务边界与恢复完成点必须成立的谓词 |
| Precondition | 命令提交前必须满足，否则无状态变化 |
| Commit Check | 与状态写入处于同一事务的最终校验 |
| Recovery Audit | Snapshot/Event 重放后、解除 Recovery Barrier 前的全量校验 |
| Conservation | 在显式 source/sink 事件之外，总量不得凭空改变 |

## 4. 规则与不变量

| ID | 不变量 | Canonical owner / 强制点 |
|---|---|---|
| `RULE-FOUNDATION-016` | 只有 Authority Server 的 World Runtime 可提交世界状态；AI、Client 和 render 不能提交。 | `BACKEND` / command pipeline |
| `RULE-FOUNDATION-017` | 每个可移动实体的位置必须位于所属 Scene 的 Walkability 内，且不与有效 Collision 相交。 | `MAP` / move、spawn、transfer、recovery |
| `RULE-FOUNDATION-018` | 每个 unique Item 同一 Revision 只能有一个 owner；stack 数量和 Inventory 占用不得为负。 | `ECON` / transaction commit |
| `RULE-FOUNDATION-019` | Currency 使用整数铜羽；除有类型的 mint/burn/tax/fee 事件外，事务前后守恒。 | `ECON` / transaction commit |
| `RULE-FOUNDATION-020` | 客观事实、Belief 与 Memory 分离；居民决策上下文只能包含其可访问、可推导或已获知内容。 | `MEMORY` + `AI` / context build |
| `RULE-FOUNDATION-021` | 每个 DomainEvent 必须有 event_id、world_id、Revision、game_time、causation_id、correlation_id 和唯一类型。 | `BACKEND` / event append |
| `RULE-FOUNDATION-022` | 相同 `command_id` 在同一 world 最多产生一次状态变化；重复请求返回原结果引用。 | `BACKEND` / idempotency store |
| `RULE-FOUNDATION-023` | 每世界 Revision 从 0 开始，仅在成功写事务后严格递增 1；回滚、拒绝和纯读不增长。 | `BACKEND` + `RELEASE` / commit |
| `RULE-FOUNDATION-024` | 未授权 Secret 不得进入 Prompt、模型请求、Event render、日志、Snapshot 导出或诊断包。 | `MEMORY` + `BACKEND` + `RELEASE` |
| `RULE-FOUNDATION-025` | 正式 Resident 不得永久删除或进入 death terminal state；致命结果转换为昏迷、重伤、撤退或被俘。 | `RESIDENT` + `COMBAT` |
| `RULE-FOUNDATION-026` | 世界 Seed 创建后不可变；规则随机只来自 `(seed, stream_id, sequence)`，存档重载不改变序列。 | `TIME` + `RELEASE` |
| `RULE-FOUNDATION-027` | DomainEvent Log 只追加；恢复和撤销通过新事件表达，不删除或改写历史事件。 | `RELEASE` / repository |
| `RULE-FOUNDATION-028` | 同一 actor 同一 GameTime 不能占用互斥状态，例如同时参与两个 Encounter 或两项排他长任务。 | `TIME` + owner Reservation |
| `RULE-FOUNDATION-029` | 状态写入与其不可丢 DomainEvent 必须原子提交，Snapshot 只能锚定完整 Revision。 | `BACKEND` + `RELEASE` |
| `RULE-FOUNDATION-030` | 所有破坏性 `AdminCommand` 必须通过 Sandbox Admin 权限、二次确认、审计，并永久标记该 timeline。 | `PLAYER` + `BACKEND` |

## 5. 数据与接口

`DES-FOUNDATION-005`：每个 invariant 实现一个纯函数 `check(state_or_transaction_view) -> InvariantResult`，返回 `invariant_id`、`passed`、`entity_ids`、`revision` 和脱敏 `reason_code`。Commit Check 失败必须导致事务回滚；Recovery Audit 失败必须保持世界暂停。

| 检查级别 | 执行范围 |
|---|---|
| Command precondition | 当前命令涉及 aggregate |
| Transaction commit | 本次写集与受影响索引 |
| Periodic audit | 分片扫描全世界，发现错误后停止相关 owner 写入 |
| Recovery audit | 全量关键 invariant |
| Simulation test | 1/7/30 日持续抽样与结束全量检查 |

## 6. 正常流程

1. Gateway 完成 Envelope 与权限校验。
2. Owner 加载所需 aggregate 并检查 precondition。
3. Orchestrator 获取必要 Reservation，执行确定性变更。
4. 事务内生成 DomainEvent 并运行受影响 invariant。
5. 全部通过后写状态、事件、idempotency result 并递增 Revision。
6. 异步投影和前端只消费已提交事件。

## 7. 边界情况

- 建筑改变道路：同一事务验证新 Collision、关键通路和 WorldDiff。
- 交易同时含税：买方扣款、卖方收款、公共预算、Item ownership 与费用事件作为一个原子写集。
- 战斗断线：actor Reservation 保持到确定恢复/超时流程，不允许加入第二场战斗。
- Snapshot 生成期间有新事务：Snapshot 固定起始 Revision，之后事件保留在 Event Log。
- Admin 恢复资源：仍必须使用显式 source event，不能绕过守恒和审计。

## 8. 错误与降级

Invariant violation 不允许自动“修好并继续”。在线提交立即回滚并记录脱敏诊断；恢复时复制原文件、保持暂停并提供可审计修复流程。Utility AI、低画质、Snapshot fallback 和高倍速回落均不能跳过本文件规则。

## 9. 安全与性能

Commit Check 必须按写集增量执行并有确定上界；全量检查放在恢复或后台分片。诊断中的 entity ID 可保留，Secret 与用户输入内容必须移除。Invariant 检查代码不得调用网络或读取非本世界文件。

## 10. 验收标准

- 十五项 invariant 均有唯一 ID、owner、提交或恢复强制点。
- 对每项进行反例注入时，事务回滚且 Revision 不增长。
- 30 游戏日模拟结束时所有 invariant 通过。
- Snapshot/Event 重放后结果与崩溃前已提交 Revision 一致。
- 模型、Admin、Client 与故障降级不能绕过 invariant。

## 11. 测试追踪

| 测试 ID | 覆盖 invariant |
|---|---|
| `TEST-FOUNDATION-020` | `RULE-FOUNDATION-016..017` |
| `TEST-FOUNDATION-021` | `RULE-FOUNDATION-018..019` |
| `TEST-FOUNDATION-022` | `RULE-FOUNDATION-020`, `RULE-FOUNDATION-024` |
| `TEST-FOUNDATION-023` | `RULE-FOUNDATION-021..023`, `RULE-FOUNDATION-029` |
| `TEST-FOUNDATION-024` | `RULE-FOUNDATION-025..026` |
| `TEST-FOUNDATION-025` | `RULE-FOUNDATION-027..028`, `RULE-FOUNDATION-030` |

## 12. 关联文档

- `DOC-FOUNDATION-002`：不变量所在提交与恢复流程
- `DOC-FOUNDATION-003`：每项不变量的 canonical owner
- `DOC-FOUNDATION-006`：Revision、Seed、ID、时间和坐标格式
- `DOC-FOUNDATION-007`：需求、设计和测试覆盖

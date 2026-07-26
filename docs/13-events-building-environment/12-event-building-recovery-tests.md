---
doc_id: DOC-EVENT-012
title: 事件与建筑恢复及场景测试
version: 1.0.0
status: approved-for-implementation
owner_domain: event
canonical_for:
  - event-building-recovery-contract
  - duplicate-event-prevention
  - event-building-scenario-tests
depends_on:
  - DOC-FOUNDATION-005
  - DOC-TIME-010
  - DOC-EVENT-001
  - DOC-EVENT-009
  - DOC-EVENT-011
requirements:
  - REQ-EVENT-012
last_updated: 2026-07-26
---

# 事件与建筑恢复及场景测试

## 1. 目的

`REQ-EVENT-012`：定义 EVENT 域的中断恢复契约、重复事件防止的三层幂等、种子化场景 fixture 与 1/7/30 游戏日模拟验收，并汇总 `TEST-EVENT-001..040` 与 `RULE-EVENT-001..072` 的覆盖矩阵。

## 2. 非目标

本文不定义 Snapshot/Event Log 存储与恢复引擎（RELEASE canonical）、TIME 队列重建（`DOC-TIME-008`）或各前置文档已 canonical 的业务规则；本文只定义 EVENT 侧的恢复审计断言、防重语义与测试组织。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Recovery Convergence | 崩溃恢复后 EVENT aggregate 与最近已提交 Revision 完全一致的性质 |
| Duplicate Prevention Layers | occurrence key、command idempotency、语义窗口去重三层防重 |
| Scenario Fixture | 注册的确定性测试世界：Seed、初始状态、命令脚本与预期时间线 |
| Oracle | 只基于已提交事件与状态的断言函数，不读渲染或模型文本 |
| Simulation Gate | 1/7/30 游戏日长跑测试的通过阈值集合 |

## 4. 规则与不变量

- `RULE-EVENT-067`：Recovery Convergence：施工、事件、Quest、天气、瓦砾处于任意中间状态时崩溃，恢复重放后 aggregate 状态、TIME 队列注册项与 pending Aftermath Task 必须与崩溃前最近提交 Revision 完全一致；EVENT 恢复审计包含 Building Binding 一致性（`RULE-EVENT-039`）与每 Scene Diff Hash（`RULE-EVENT-064`），失败保持 Recovery Barrier。
- `RULE-EVENT-068`：重复事件防止三层缺一不可：周期评估与到期处理按 occurrence key（`RULE-TIME-047`）、外部命令按 `(world_id, command_id)`（`RULE-FOUNDATION-022`）、Director/触发候选按语义窗口去重——同 `(event_template_id, scope)` 在模板 `dedup_window_game_minutes` 内已有非 archived 实例时拒绝新实例。
- `RULE-EVENT-069`：Scenario Fixture 必须注册且确定性：固定 Seed、固定命令脚本（含模型响应用 FakeProvider 固定工件）、预期事件时间线以 `(revision, event_type)` 序列表达；同一 fixture 重复执行产生逐 Revision 相同结果（`RULE-FOUNDATION-026`）。
- `RULE-EVENT-070`：Oracle 只读已提交状态与 Event Log：禁止以渲染帧、模型自由文本或内存瞬态作为断言依据；涉及模型的场景一律使用 FakeProvider 固定响应，真实 DeepSeek 测试显式 opt-in（与 `DOC-AI-012` 同策略）。
- `RULE-EVENT-071`：Simulation Gate：1/7/30 游戏日长跑必须持续断言叙事压力权重上限、crisis 并发 ≤1、冷却零违规、每 7 日 Calm Window ≥1、建筑四件套原子性抽样与结束时全量 invariant（`DOC-FOUNDATION-005` 全集）通过。
- `RULE-EVENT-072`：任何 EVENT 测试不得以 Sandbox Admin 绕过被测规则：`admin` 只允许用于构造前置状态，且注入步骤在 fixture 中显式标记并纳入断言基线（`RULE-FOUNDATION-030`）。

## 5. 数据与接口

`DES-EVENT-012`：Scenario Fixture 注册项：

```json
{
  "schema_version": 1,
  "fixture_id": "fixture.event.forest_fire_full_chain",
  "seed_hex": "8f3a1c2b9d4e5f60718293a4b5c6d7e8",
  "base_world_template_id": "world_template.crown_creek_default",
  "fake_model_artifacts": ["fake.director.harvest_festival", "fake.resident.build_accept"],
  "admin_setup_command_ids": ["01K1AB2CD3EF4GH5JK6MNP7QSP"],
  "expected_timeline": [
    {"revision": 120, "event_type": "world_event.instantiated"},
    {"revision": 188, "event_type": "world_event.activated"},
    {"revision": 305, "event_type": "navigation.patch_committed"},
    {"revision": 512, "event_type": "world_event.aftermath_entered"}
  ],
  "oracles": ["oracle.budget_never_exceeded", "oracle.diff_hash_consistent", "oracle.no_duplicate_world_event"]
}
```

接口：

```text
run_scenario(fixture_id) -> ScenarioReport
run_recovery_probe(fixture_id, crash_at_revision) -> RecoveryReport
run_simulation_gate(days: 1|7|30, seed_hex) -> SimulationGateReport
```

`run_recovery_probe` 在指定 Revision 注入进程终止，随后执行标准恢复并运行全部 Oracle 与恢复审计。

## 6. 正常流程

1. CI 按注册表执行全部 Scenario Fixture 与恢复探针。
2. 每个 fixture 报告实际时间线与预期时间线的逐项对比。
3. 恢复探针在关键中间态（施工各阶段、事件各状态、Diff 追加前后）各至少一个切点。
4. 长跑 Gate 每夜执行 7 日、发布前执行 30 日。
5. 覆盖矩阵审计确认每条 `RULE-EVENT-*` 至少被一个测试引用。

## 7. 边界情况

- 崩溃点恰在事务提交与队列 outcome 写入之间：依赖 `RULE-FOUNDATION-029` 原子性，恢复后二者要么都在要么都不在，探针必须覆盖该切点。
- 恢复后 TIME 队列存在已 due 的积压 occurrence：按 `RULE-TIME-048` 逐项补执行，防重层保证不产生第二个事件实例。
- FakeProvider 工件与最新 Schema 版本不匹配：fixture 构建期校验失败，禁止运行期跳过 Schema 校验。
- 30 日长跑中随机命中 `budget_exceeded` 等预期拒绝：预期拒绝不是失败，Gate 只统计不变量违规与非预期错误码。
- 探针在 Recovery Barrier 场景（人为破坏 Diff Hash）：预期结果是保持暂停且产生诊断，自动"恢复成功"反而判失败。

## 8. 错误与降级

Scenario 失败报告首个分歧 `(revision, expected, actual)`；恢复探针失败报告审计项与实体 ID（脱敏，`RULE-FOUNDATION-024`）。测试基础设施自身故障（fixture 加载失败、FakeProvider 缺失）标记为 infrastructure error，不计入规则回归统计，但阻塞发布 Gate。

## 9. 安全与性能

Fixture 与 FakeProvider 工件不含真实 API Key 或用户数据。单 Scenario 目标运行时间 ≤ 60 real seconds；30 日长跑以 Background 层加速执行并允许并行分片，但每分片内 Revision 序列严格串行。矩阵审计脚本随仓库版本化，可在 CI 与本地一致执行。

## 10. 验收标准

- 全部注册 fixture 通过且时间线逐项一致。
- 每类中间态至少一个恢复探针通过 Recovery Convergence。
- 三层防重的每层单独禁用时对应探针必须失败（验证测试有效性）。
- 1/7/30 日 Gate 全绿且 Calm Window/预算/冷却统计达标。
- 覆盖矩阵零缺口：`RULE-EVENT-001..072` 全部被引用。

## 11. 测试追踪

场景与恢复测试：

| 测试 ID | 断言 |
|---|---|
| `TEST-EVENT-034` | `RULE-EVENT-067` 施工/事件/Quest 中间态崩溃的 Recovery Convergence |
| `TEST-EVENT-035` | `RULE-EVENT-068` 三层防重与逐层失效探针 |
| `TEST-EVENT-036` | `RULE-EVENT-069..070` fixture 确定性与 Oracle 纪律 |
| `TEST-EVENT-037` | `RULE-EVENT-071` 1/7/30 日 Simulation Gate |
| `TEST-EVENT-038` | `RULE-EVENT-072` admin 使用边界与标记审计 |
| `TEST-EVENT-039` | 森林火灾全链场景：触发→封路→损毁→营救 Quest→赔偿→重开→archived |
| `TEST-EVENT-040` | 建造全链场景：放置→六阶段→升级→受损→修复→WorldDiff 重放一致 |

覆盖矩阵：

| 规则区间 | 定义文档 | 覆盖测试 |
|---|---|---|
| `RULE-EVENT-001..006` | `DOC-EVENT-001` | `TEST-EVENT-001..003`, `TEST-EVENT-039` |
| `RULE-EVENT-007..012` | `DOC-EVENT-002` | `TEST-EVENT-004..006`, `TEST-EVENT-037` |
| `RULE-EVENT-013..018` | `DOC-EVENT-003` | `TEST-EVENT-007..009`, `TEST-EVENT-035` |
| `RULE-EVENT-019..024` | `DOC-EVENT-004` | `TEST-EVENT-010..012`, `TEST-EVENT-039` |
| `RULE-EVENT-025..030` | `DOC-EVENT-005` | `TEST-EVENT-013..015`, `TEST-EVENT-039` |
| `RULE-EVENT-031..036` | `DOC-EVENT-006` | `TEST-EVENT-016..018`, `TEST-EVENT-037` |
| `RULE-EVENT-037..042` | `DOC-EVENT-007` | `TEST-EVENT-019..021`, `TEST-EVENT-040` |
| `RULE-EVENT-043..048` | `DOC-EVENT-008` | `TEST-EVENT-022..024`, `TEST-EVENT-040` |
| `RULE-EVENT-049..054` | `DOC-EVENT-009` | `TEST-EVENT-025..027`, `TEST-EVENT-034`, `TEST-EVENT-040` |
| `RULE-EVENT-055..060` | `DOC-EVENT-010` | `TEST-EVENT-028..030`, `TEST-EVENT-040` |
| `RULE-EVENT-061..066` | `DOC-EVENT-011` | `TEST-EVENT-031..033`, `TEST-EVENT-040` |
| `RULE-EVENT-067..072` | `DOC-EVENT-012` | `TEST-EVENT-034..038` |

## 12. 关联文档

- `DOC-EVENT-001..011`：被覆盖的全部 EVENT 规则
- `DOC-FOUNDATION-005`：恢复审计与 invariant 全集
- `DOC-TIME-008`：队列重建与 occurrence 幂等
- `DOC-TIME-010`：Seed 复现纪律
- `DOC-AI-012`：FakeProvider 与模型测试策略

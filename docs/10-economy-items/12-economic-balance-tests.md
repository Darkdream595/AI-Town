---
doc_id: DOC-ECON-012
title: 经济守恒、平衡与恢复测试
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - economy-acceptance-suite
  - conservation-audit
  - economy-recovery-tests
depends_on:
  - DOC-FOUNDATION-005
  - DOC-ECON-001
  - DOC-ECON-002
  - DOC-ECON-003
  - DOC-ECON-004
  - DOC-ECON-005
  - DOC-ECON-006
  - DOC-ECON-007
  - DOC-ECON-008
  - DOC-ECON-009
  - DOC-ECON-010
  - DOC-ECON-011
requirements:
  - REQ-ECON-012
last_updated: 2026-07-26
---

# 经济守恒、平衡与恢复测试

## 1. 目的

`REQ-ECON-012`：给出可自动执行的 Contract、Property、Integration、Simulation 与 Recovery 验收，覆盖货币/物品守恒、并发、价格边界、高倍速、短缺、工资、制作、产权和公共预算。

## 2. 非目标

本文不以“看起来合理”的单次游玩替代统计与不变量断言，不调用真实 DeepSeek 决定测试结果，也不要求首版经济达到现实宏观精度。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Conservation Snapshot | 在 Revision 边界统计账户、Item、batch 与 active Reservation 的测试投影 |
| Source/Sink Allowlist | 允许改变总量的注册事件类型与预期 delta |
| Crash Boundary | Unit of Work 中每个可注入中断点 |
| Speed Equivalence | 相同 Seed、Command/Event 序列和 GameTime 终点在不同倍率下状态 hash 相同 |
| Balance Envelope | 30 日模拟中允许的库存、价格、欠薪和短缺有界范围 |

## 4. 规则与不变量

- `RULE-ECON-045`：每个成功 Transaction 后必须立即检查 currency sum、unique ownership、stack quantity、Inventory capacity 与 Reservation consumed/released 一致性。
- `RULE-ECON-046`：恢复解除 Recovery Barrier 前必须全量验证 Ledger 重算余额、Item ownership index、Inventory cache、active Reservation 与 terminal Transaction。
- `RULE-ECON-047`：`0.5×/1×/2×/4×` 在相同 GameTime 终点必须产生相同经济 state hash；`0×` 不滚动窗口、不计工时、不使 Reservation 自然过期。
- `RULE-ECON-048`：1/7/30 日模拟不得出现负余额/库存、重复 unique、无界 Quote、永久 active Reservation、无限 production cycle 或无来源 Item/Currency。

## 5. 数据与接口

`DES-ECON-012`：最小 machine-readable acceptance fixture：

```json
{
  "fixture_version": 1,
  "world_seed_hex": "000102030405060708090a0b0c0d0e0f",
  "residents": 10,
  "initial_currency_copper_feather": 50000,
  "initial_unique_item_ids": 12,
  "simulation_end_game_times": [1440, 10080, 43200],
  "speed_multipliers": [0.5, 1, 2, 4],
  "crash_boundaries": [
    "after_reservations",
    "after_state_writes_before_events",
    "after_events_before_idempotency",
    "after_database_commit_before_outbox"
  ],
  "required_assertions": [
    "currency_conserved_except_allowlisted_sources_sinks",
    "unique_owner_count_equals_one",
    "stack_and_inventory_non_negative",
    "transaction_exactly_once",
    "speed_state_hash_equal",
    "recovery_barrier_audit_passed"
  ]
}
```

建议实现入口：

```powershell
python -m pytest tests/economy -q
python -m app.tools.run_simulation --fixture economy_baseline_v1 --game-days 1,7,30 --speeds 0.5,1,2,4
python -m app.tools.audit_economy --world-fixture economy_baseline_v1 --format json
```

## 6. 正常流程

1. 使用 FakeModelProvider 和固定 Seed 创建 10 Resident、三个 Region 生产链与初始账本。
2. 执行工资、Shop sale、税费、赠与、Craft、退款、产权转移和公共工程场景。
3. 每次提交运行增量 invariant；每个模拟终点运行全量 Conservation Snapshot。
4. 对每个 Crash Boundary 复制测试数据库、注入中断、恢复并重放。
5. 比较不同速度 state hash、Ledger/Event projection 与 source/sink delta。
6. 输出 JSON 报告，任一 assertion false 即进程 exit non-zero。

## 7. 边界情况

- 并发夹具同时购买最后一个 unique、最后一份 stack 和消费同一余额。
- 工资结算与 Shop purchase 同时竞争 worker 账户余额。
- GameTime 在 Reservation 过期前一分钟暂停，恢复后只按 GameTime 到期。
- Shortage 在 bucket 边界产生/恢复，价格必须留在 floor/ceiling。
- Crash 后重发 command、Outbox 与 Craft completion，结果必须 exactly-once。

## 8. 错误与降级

测试工具发现不变量失败时保留最小失败 Seed、Command 序列、Revision、entity IDs 与脱敏 reason code，并 exit 1；不能自动修复后继续计为通过。性能预算超时与断言失败分开报告，真实模型不可用不影响确定性 suite。

## 9. 安全与性能

测试限定明确 fixture 和 ECON 数据，不扫描无关目录。每 1000 次 Transaction 做一次全量 audit，其余增量；30 日模拟记录 p50/p95/p99 提交延迟、最大 active Reservation、账本增长与 state hash，诊断不含 Secret/Prompt。

## 10. 验收标准

- 48 个 `TEST-ECON-001..048` 均能映射到本 suite 的 fixture/runner。
- source/sink allowlist 之外货币与 Item 总量 delta 为 0。
- 全部 Crash Boundary 恢复到旧 Revision 或完整新 Revision，不存在半事务。
- 四种非零倍率 state hash 相同，`0×` 观察期 state hash 不变。
- 30 日内价格、库存、欠薪、Shortage、Reservation 与数据增长均落入 fixture 的有界 envelope。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-045` | 每事务守恒、不变量与反例注入 |
| `TEST-ECON-046` | Snapshot/Event/ledger/index/cache/Reservation 恢复 audit |
| `TEST-ECON-047` | `0×..4×` speed equivalence 与暂停 |
| `TEST-ECON-048` | 1/7/30 日 balance envelope、性能与增长上限 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：全局不变量与 Recovery Audit
- `DOC-ECON-001..011`：本套件覆盖的 canonical 经济规格
- `DOC-BACKEND-010`：跨域事务与幂等下游实现
- `DOC-RELEASE-011`：项目级测试策略

---
doc_id: DOC-RESIDENT-012
title: 居民系统验收与恢复测试
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-test-matrix
  - resident-executable-scenarios
depends_on:
  - DOC-RESIDENT-001
  - DOC-RESIDENT-002
  - DOC-RESIDENT-003
  - DOC-RESIDENT-004
  - DOC-RESIDENT-005
  - DOC-RESIDENT-006
  - DOC-RESIDENT-007
  - DOC-RESIDENT-008
  - DOC-RESIDENT-009
  - DOC-RESIDENT-010
  - DOC-RESIDENT-011
requirements:
  - REQ-RESIDENT-012
last_updated: 2026-07-26
---

# 居民系统验收与恢复测试

## 1. 目的

`REQ-RESIDENT-012`：给出可直接转为自动化测试的 Resident 矩阵、fixture 格式、故障注入、状态机与 1/7/30 日验收，覆盖 `TEST-RESIDENT-001..052`。

## 2. 非目标

不替代 ECON/COMBAT/TIME/AI 的 owner 测试，不调用真实 DeepSeek，不以人工阅读代替必须自动化的不变量与幂等检查。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Fixture | 固定 world/seed/revision/resident 输入 |
| Scenario | Given/When/Then 的可执行命令与断言 |
| Failure Injection | 在 owner Port、事务或恢复点注入确定性错误 |
| Golden Event Sequence | 明确 type、causation、顺序的预期事件列表 |

## 4. 数据与接口

`DES-RESIDENT-012`：统一场景 Schema：

```json
{
  "scenario_id":"resident.health.damage_idempotency",
  "initial_revision":42,
  "given":{
    "resident_id":"01K1AB2CD3EF4GH5JK6MNP7QRS",
    "hp_current":30,
    "lifecycle_state":"active"
  },
  "when":[
    {
      "command_id":"01K1AB2CD3EF4GH5JK6MNP7QTA",
      "type":"apply_health_effect",
      "source_owner":"combat",
      "source_event_id":"01K1AB2CD3EF4GH5JK6MNP7QTB",
      "effect_definition_id":"effect.damage.physical",
      "hp_delta":-40,
      "expected_revision":42
    },
    {
      "command_id":"01K1AB2CD3EF4GH5JK6MNP7QTC",
      "type":"apply_health_effect",
      "source_owner":"combat",
      "source_event_id":"01K1AB2CD3EF4GH5JK6MNP7QTB",
      "effect_definition_id":"effect.damage.physical",
      "hp_delta":-40,
      "expected_revision":43
    }
  ],
  "then":{
    "hp_current":0,
    "lifecycle_state":"unconscious",
    "resident_exists":true,
    "effect_application_count":1,
    "forbidden_states":["dead","deleted"],
    "final_revision":43
  }
}
```

Harness 必须支持 `apply_command`、`query_owner_projection`、`inject_failure`、`save_reload`、`advance_game_time` 和 `assert_invariants`。

## 5. 规则与不变量

- `RULE-RESIDENT-066`：所有 `REQ-RESIDENT-001..012` 至少映射一个 Test ID；所有测试固定 Seed、输入 Revision 与预期事件。
- `RULE-RESIDENT-067`：故障场景必须断言状态、事件、幂等记录和 Revision 均无部分提交。
- `RULE-RESIDENT-068`：owner-boundary 测试使用 Fake Port，断言 Resident 不计算 Item、damage、schedule 或 AI 决策。
- `RULE-RESIDENT-069`：恢复测试必须比较保存前后 Resident Snapshot canonical JSON 与 source event application keys。
- `RULE-RESIDENT-070`：Simulation 每游戏日检查正式居民存在、位置合法、active exclusive task 至多一个、HP/Need 范围和引用完整。
- `RULE-RESIDENT-071`：测试失败必须输出 scenario ID、Seed、Revision、resident ID 和脱敏 invariant ID。

## 6. 正常流程

1. 加载最小 8 名与默认 10 名 roster fixture。
2. 执行 Unit/Property/Contract；再执行跨 MAP/ECON/COMBAT/TIME Integration。
3. 在命令前、状态写后、事件写前、幂等写前注入失败。
4. 每个阶段保存/重载并重放最后命令。
5. 运行 1/7/30 游戏日模拟与每日 invariant audit。
6. 生成机器可读通过率和 Requirement coverage。

## 7. 边界情况

- 重复 `command_id` 与不同 command payload 必须返回 idempotency conflict，而非执行第二 payload。
- 同一 source effect 用新 command ID 重放仍只应用一次。
- stale Revision 的 AI/玩家意图不得改变 Resident。
- 30 日内全部服务者受伤时允许服务中断，但 roster 和恢复路径必须存在。

## 8. 错误与降级

Fixture Schema 错误、未知 Test ID、真实模型调用、非固定 Seed 或断言缺失都使测试套件失败。依赖 domain 尚未实现时使用严格 Fake Port；不得把测试标记为通过而跳过断言。

## 9. 安全与性能

Fixture 不含 API Key、Secret、Prompt 或用户文本。Unit+Contract 目标 30 秒内完成；30 日 Simulation 可单独执行但必须记录 Seed 与事件数。

## 10. 验收标准

| 场景 ID | Given / When | 必须断言 |
|---|---|---|
| `resident.bootstrap.rollback` | 第 5 名 Inventory 创建失败 | 0 个新 Resident、0 个孤儿 Inventory、Revision 不变 |
| `resident.personality.no_authority` | 极端 personality + 非法 Action | Action 仍非法、无状态事件 |
| `resident.need.threshold` | hunger 799 推进至 800 | 仅一次 critical band event |
| `resident.long_action.interrupt` | 工作中发生 emergency | TIME 先暂停任务，再允许重规划，无双 Reservation |
| `resident.health.damage_idempotency` | 致命 damage effect 重放 | 仅应用一次、unconscious、Resident 保留 |
| `resident.captivity.review` | holder 失效且到 review | 安全退出流程存在、无 delete |
| `resident.inventory.authority` | stale Item projection 申请 use | ECON 拒绝，Resident 不补物品 |
| `resident.save_reload` | 保存、重载、重复最后命令 | canonical Snapshot 和幂等结果一致 |

全部 `TEST-RESIDENT-001..052` 通过、Requirement coverage 12/12、Critical invariant failure 为 0 才可批准。

## 11. 测试追踪

| Test ID | 覆盖 |
|---|---|
| `TEST-RESIDENT-001..008` | Aggregate、Identity、Schema、外貌 |
| `TEST-RESIDENT-009..016` | Personality、Needs、Emotion |
| `TEST-RESIDENT-017..024` | Skills、Ability、Profession、Residence |
| `TEST-RESIDENT-025..032` | Health、Injury、Illness、非永久失败 |
| `TEST-RESIDENT-033..040` | Routine、Interrupt、Long Action、Inventory boundary |
| `TEST-RESIDENT-041..044` | Roster、service coverage、bootstrap |
| `TEST-RESIDENT-045` | 所有 Requirement/Test 引用与 DOC link 可解析 |
| `TEST-RESIDENT-046` | Resident 状态机无 death/delete terminal 且合法状态可达 |
| `TEST-RESIDENT-047` | owner-boundary 静态与 Contract 检查 |
| `TEST-RESIDENT-048` | transaction failure injection 全部无部分提交 |
| `TEST-RESIDENT-049` | save/reload/replay canonical JSON 相等 |
| `TEST-RESIDENT-050` | 1 游戏日 Simulation invariants |
| `TEST-RESIDENT-051` | 7 游戏日 Simulation invariants 与 service continuity |
| `TEST-RESIDENT-052` | 30 游戏日 Simulation invariants、队列与状态规模有界 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：跨系统不变量
- `DOC-MAP-012`：位置/通行测试
- `DOC-ECON-012`：物品与经济测试
- `DOC-COMBAT-012`：伤害和 outcome 测试
- `DOC-TIME-012`：调度、恢复和 Simulation 测试


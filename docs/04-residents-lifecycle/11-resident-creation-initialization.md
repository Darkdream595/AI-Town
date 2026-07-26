---
doc_id: DOC-RESIDENT-011
title: 居民创建、初始化与服务覆盖
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-initialization
  - core-resident-count
  - resident-service-coverage
depends_on:
  - DOC-FOUNDATION-001
  - DOC-WORLD-004
  - DOC-WORLD-005
  - DOC-RESIDENT-001
  - DOC-RESIDENT-010
requirements:
  - REQ-RESIDENT-011
last_updated: 2026-07-26
---

# 居民创建、初始化与服务覆盖

## 1. 目的

`REQ-RESIDENT-011`：定义新世界 8–12 名正式居民的确定性初始化、stable identity、多样性、关键服务覆盖、跨域原子创建与失败恢复。

## 2. 非目标

不要求每名居民只承担一个职业，不以 ancestry 分配职业，不创建 Item/建筑/工作地权威数据，也不在首版运行时随机生成新正式居民。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Resident Roster Template | 版本化的 8–12 名稳定居民配置 |
| Service Capability | 维持小镇可玩性的能力标签，而非硬编码职业 |
| Service Coverage | 所有 Must capability 至少由一名 active/可恢复居民覆盖 |
| Service Evidence | 可由 owner Port 验证的 Skill、Ability 或 active profession assignment |
| Bootstrap Transaction | 初始化 World、Resident 和 owner 引用的阶段化原子流程 |
| Roster Version | 创建后存档保留的模板版本 |

## 4. 数据与接口

`DES-RESIDENT-011`：首版 Must service capability：

| Capability ID | 最少覆盖 | 允许来源示例 |
|---|---:|---|
| `service.food_supply` | 1 | 酒馆、采集、商人 |
| `service.basic_healing` | 1 | 治疗者、药剂师 |
| `service.public_safety` | 1 | 镇卫、冒险者 |
| `service.tool_repair` | 1 | 铁匠、木匠 |
| `service.raw_materials` | 2 | 矿工、采集者 |
| `service.trade_access` | 1 | 商人、酒馆、药剂师 |
| `service.magic_assistance` | 1 | 法师、治疗者 |
| `service.build_repair` | 1 | 木匠、铁匠 |

注册 `schema.resident.roster.v1`。required 字段为
`roster_id/roster_version/resident_count/resident_keys/required_service_capabilities/service_coverage_assignments`。
每个 coverage assignment required
`capability_id/resident_key/evidence_owner/evidence_kind/evidence_id/evidence_minimum/initial_availability/requires_active_assignment_id`。
默认 10 人正例 fixture：

```json
{
  "roster_id":"roster.crown_creek.v1",
  "roster_version":1,
  "resident_count":10,
  "resident_keys":[
    "resident.apothecary.elise",
    "resident.guard.rowan",
    "resident.innkeeper.mira",
    "resident.blacksmith.toren",
    "resident.miner.borin",
    "resident.gatherer.sylva",
    "resident.mage.cassian",
    "resident.carpenter.liora",
    "resident.merchant.nadia",
    "resident.adventurer.fen"
  ],
  "required_service_capabilities":{
    "service.food_supply":1,
    "service.basic_healing":1,
    "service.public_safety":1,
    "service.tool_repair":1,
    "service.raw_materials":2,
    "service.trade_access":1,
    "service.magic_assistance":1,
    "service.build_repair":1
  },
  "service_coverage_assignments":[
    {"capability_id":"service.food_supply","resident_key":"resident.innkeeper.mira","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.cooking.community_meal","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.basic_healing","resident_key":"resident.apothecary.elise","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.medicine.first_aid","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.public_safety","resident_key":"resident.guard.rowan","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.guard.public_patrol","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.tool_repair","resident_key":"resident.blacksmith.toren","evidence_owner":"resident","evidence_kind":"skill_rating","evidence_id":"skill.smithing","evidence_minimum":40,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.raw_materials","resident_key":"resident.miner.borin","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.mining.extract_common_ore","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.raw_materials","resident_key":"resident.gatherer.sylva","evidence_owner":"resident","evidence_kind":"skill_rating","evidence_id":"skill.gathering","evidence_minimum":30,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.trade_access","resident_key":"resident.merchant.nadia","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.trade.retail_service","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.magic_assistance","resident_key":"resident.mage.cassian","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.magic.safe_assistance","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.build_repair","resident_key":"resident.carpenter.liora","evidence_owner":"resident","evidence_kind":"skill_rating","evidence_id":"skill.carpentry","evidence_minimum":40,"initial_availability":"available","requires_active_assignment_id":null}
  ]
}
```

`evidence_kind` 封闭为 `skill_rating/ability/profession_assignment`：

- `skill_rating/ability` 由 `get_capability_snapshot(resident_id, revision)` 验证；
- `profession_assignment` 由 ECON `get_profession_assignment_projection(assignment_id, revision)` 验证，且
  `requires_active_assignment_id` 必须等于被验证 assignment；
- `initial_availability` 封闭为 `available/temporarily_unavailable`，只有 `available` 计入 bootstrap Must coverage。

审计函数：

```text
validate_service_coverage(roster, resident_capability_port, economy_assignment_port, revision)
  -> {passed, providers_by_capability, missing_capabilities, rejected_assignments}
```

## 5. 规则与不变量

- `RULE-RESIDENT-059`：新世界正式居民数必须为 `8..12`，`resident_key` 唯一，初始化重放保持相同 key-to-runtime-ID 映射。
- `RULE-RESIDENT-060`：八类 Must service capability 必须由 `service_coverage_assignments` 全部满足；同一居民可覆盖多项，但 `raw_materials` 的 provider set 必须包含两个不同 `resident_key`。
- `RULE-RESIDENT-061`：Roster 至少包含三类 ancestry、三个 culture，且每个 ancestry 均不得与单一 profession 一一绑定。
- `RULE-RESIDENT-062`：每名居民必须通过 identity、personality、Needs、Health、Capability、profession/residence 引用、Inventory 引用、routine 校验。
- `RULE-RESIDENT-063`：Bootstrap 阶段失败必须整体回滚或保持 Recovery Barrier；不得以缺失字段/孤立引用启动世界。
- `RULE-RESIDENT-064`：Roster 由 world Seed 与 `roster_version` 选择已登记 variant；规则随机流固定，重试不改变结果。
- `RULE-RESIDENT-065`：服务提供者 defeat/suspended 时服务可暂时中断并形成事件压力，但不得删除 Resident 或偷偷生成替代者。
- `RULE-RESIDENT-073`：每个 coverage assignment 的 resident 必须存在于 `resident_keys`，evidence 必须由声明 owner Port 在固定 Revision 验证；仅名称、职业文案或模型推断不构成 evidence。

## 6. 正常流程

1. 选择 `roster_id/version`，用命名 Seed stream 解析允许的 presentation variant。
2. 静态审计 count、stable key、多样性与 coverage assignment 结构。
3. 通过 Capability/ECON owner Port 验证 evidence，输出 `providers_by_capability`、不足项与拒绝原因；不足即阻断。
4. 预验证 Scene spawn、Entrance/residence、workplace、Catalog 与权限。
5. 分阶段构造 ECON Inventory、Resident aggregate、assignment 与初始 routine。
6. 运行全量 Resident/MAP/ECON invariant 后一次性解除 Bootstrap Barrier。
7. 生成 `ResidentRosterInitialized`，记录 roster/version/seed stream sequence 与 coverage audit hash。

## 7. 边界情况

- 10 名默认 roster 中一人同时为法师和治疗者允许，但基本治疗与魔法服务不能因同一临时状态永久锁死。
- Spawn point 被动态占用时使用模板中有序 fallback spawn，不随机传送。
- 初始化崩溃后按 idempotency key 继续或回滚，不能产生重复 Inventory/Resident。
- 玩家角色不计入 8–12 名 AI 正式居民的 Must coverage。
- assignment 指向 roster 外 resident、evidence 缺失/不足、provider unavailable 时均不计数，并输出 rejected assignment。

最小 8 人反例 fixture 本身仍逐字段满足 `schema.resident.roster.v1`，但故意让
`raw_materials` 两条 assignment 指向同一居民、缺少 `build_repair` assignment，
并提供不足 Skill evidence：

```json
{
  "roster_id":"roster.crown_creek.invalid_minimum_eight",
  "roster_version":1,
  "resident_count":8,
  "resident_keys":[
    "resident.apothecary.elise",
    "resident.guard.rowan",
    "resident.innkeeper.mira",
    "resident.blacksmith.toren",
    "resident.miner.borin",
    "resident.gatherer.sylva",
    "resident.mage.cassian",
    "resident.carpenter.liora"
  ],
  "required_service_capabilities":{
    "service.food_supply":1,
    "service.basic_healing":1,
    "service.public_safety":1,
    "service.tool_repair":1,
    "service.raw_materials":2,
    "service.trade_access":1,
    "service.magic_assistance":1,
    "service.build_repair":1
  },
  "service_coverage_assignments":[
    {"capability_id":"service.food_supply","resident_key":"resident.innkeeper.mira","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.cooking.community_meal","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.basic_healing","resident_key":"resident.apothecary.elise","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.medicine.first_aid","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.public_safety","resident_key":"resident.guard.rowan","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.guard.public_patrol","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.tool_repair","resident_key":"resident.blacksmith.toren","evidence_owner":"resident","evidence_kind":"skill_rating","evidence_id":"skill.smithing","evidence_minimum":40,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.raw_materials","resident_key":"resident.miner.borin","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.mining.extract_common_ore","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.raw_materials","resident_key":"resident.miner.borin","evidence_owner":"resident","evidence_kind":"skill_rating","evidence_id":"skill.mining","evidence_minimum":30,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.trade_access","resident_key":"resident.apothecary.elise","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.trade.retail_service","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null},
    {"capability_id":"service.magic_assistance","resident_key":"resident.mage.cassian","evidence_owner":"resident","evidence_kind":"ability","evidence_id":"ability.magic.safe_assistance","evidence_minimum":null,"initial_availability":"available","requires_active_assignment_id":null}
  ]
}
```

Fake Capability Port 为 `resident.miner.borin/skill.mining` 返回 rating 20。
预期 `passed=false`、`missing_capabilities=["service.raw_materials","service.build_repair"]`，
rejected reasons 包含 `provider_distinctness_failed/evidence_minimum_not_met`。

12 人正例在默认 10 人 fixture 上只可追加两个具有合法 evidence 的 Resident；
增加人数不得降低任何 Must provider set，且新增未覆盖 capability 不会自动成为 Must。

## 8. 错误与降级

返回 `RESIDENT_ROSTER_COUNT_INVALID`、`RESIDENT_SERVICE_COVERAGE_MISSING`、`RESIDENT_ROSTER_DIVERSITY_INVALID`、`RESIDENT_BOOTSTRAP_REFERENCE_FAILED`。缺少 Must 服务时禁止开始该 world，不用模型临时补设定。

## 9. 安全与性能

模板仅引用明确 Catalog，不接受任意文件路径或模型生成 ID。12 名 roster 全量验证目标 200 ms（不含 I/O/资源预热）；检查结果按 roster hash 缓存。

## 10. 验收标准

- 8、10、12 名合法 roster 通过，7/13 名拒绝。
- 每项 Must service capability 的 `providers_by_capability` 非空且证据可由 owner Port 重放验证；
  `raw_materials` 恰有至少两个不同 resident。
- 相同 Seed/version 多次初始化得到相同映射。
- 任一 owner 失败不留下半创建状态。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-041` | count、stable key 与 diversity Property Test |
| `TEST-RESIDENT-042` | 8/10/12 人正例与缺 provider、外部 resident、低 Skill、不可用、raw_materials 单 provider 反例 |
| `TEST-RESIDENT-043` | Seed/version 重放确定性 |
| `TEST-RESIDENT-044` | Bootstrap failure injection 与孤儿扫描 |

## 12. 关联文档

- `DOC-WORLD-005`：身份多样性
- `DOC-MAP-012`：spawn/standing 验收
- `DOC-RESIDENT-012`：系统场景
- `DOC-ECON-002`：职业/服务定义 owner

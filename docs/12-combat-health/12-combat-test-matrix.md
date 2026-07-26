---
doc_id: DOC-COMBAT-012
title: 战斗测试矩阵
version: 1.0.0
status: approved-for-implementation
owner_domain: combat
canonical_for:
  - combat-test-matrix
  - combat-fixture-registry
depends_on:
  - DOC-FOUNDATION-007
  - DOC-TIME-010
  - DOC-COMBAT-001
  - DOC-COMBAT-002
  - DOC-COMBAT-003
  - DOC-COMBAT-004
  - DOC-COMBAT-005
  - DOC-COMBAT-006
  - DOC-COMBAT-007
  - DOC-COMBAT-008
  - DOC-COMBAT-009
  - DOC-COMBAT-010
  - DOC-COMBAT-011
requirements:
  - REQ-COMBAT-012
last_updated: 2026-07-26
---

# 战斗测试矩阵

## 1. 目的

`REQ-COMBAT-012`：登记战斗域的标准 fixture、测试判定 oracle 与完整测试矩阵，保证 `RULE-COMBAT-001..066` 每条规则至少被一个测试覆盖，且核心不变量（模型不决定数值、正式居民非永久死亡、战斗不重复执行）有跨层验证。

## 2. 非目标

不重复定义各文档已声明的规则语义；不定义测试框架选型、CI 编排或非战斗域测试（`DOC-RELEASE-011` 统筹全项目测试策略）。矩阵行引用规则用稳定 ID，不复述规则内容。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Combat Fixture | 注册的确定性战斗初始配置：Seed、参战 Sheet、Loot Table、公式版本 |
| Golden Replay | 固定 fixture + 固定命令序列产生的基准事件流，比较逐字节一致 |
| Oracle | 判定测试通过与否的确定性谓词或基准数据 |
| FakeModelProvider | 按输入 hash 返回固定响应并可模拟超时/非法输出的测试 provider |
| Crash Point Matrix | 在事务提交前/后注入崩溃的恢复测试组合 |
| 覆盖审计 | 校验每条 RULE-COMBAT 出现在至少一行矩阵中的机械检查 |

## 4. 规则与不变量

- `RULE-COMBAT-065`：`RULE-COMBAT-001..066` 每条必须出现在本文第 5.3 节矩阵的至少一行；新增规则未登记矩阵行时，战斗域文档审计失败。
- `RULE-COMBAT-066`：战斗测试默认使用 FakeModelProvider 与固定 Seed；真实 `deepseek-v4-flash` 联网测试必须显式启用并只作为补充层，不作为矩阵行的通过依据。

## 5. 数据与接口

### 5.1 Fixture registry

`DES-COMBAT-012`：fixture 以 Stable Catalog ID 注册，核心 fixture 如下：

| Fixture ID | 内容 |
|---|---|
| `fixture.combat.duel_2v2` | 2 Resident 对 2 Creature，覆盖命中/伤害/状态/掉落主链路 |
| `fixture.combat.full_party_4v4` | 满编前后排，覆盖站位、Reach、switch_position 与 initiative |
| `fixture.combat.nonviolent_exit` | 投降/谈判/逃跑三出口与 acceptance policy 分支 |
| `fixture.combat.wipeout` | 全队 down、同 tick 全灭与 outcome 映射降级支路 |
| `fixture.combat.model_offline` | FakeModelProvider 全故障，全程 Tactical Fallback |
| `fixture.combat.round_cap` | 双方无法互伤，驱动 `round_cap_forced` |

`fixture.combat.duel_2v2` 的种子与断言锚点：

```json
{
  "fixture_id": "fixture.combat.duel_2v2",
  "world_seed_hex": "0123456789abcdeffedcba9876543210",
  "formula_version": "combat_formula.v1",
  "encounter_trigger": "ambush_event",
  "party": [
    {"entity_ref": "resident.apothecary.elise", "strength": 42, "defense": 35, "magic": 18, "resistance": 22, "agility": 39, "focus": 27, "hp_max": 30, "mp_max": 10}
  ],
  "adversary": [
    {"entity_ref": "creature.bandit.cutpurse", "strength": 30, "defense": 20, "magic": 5, "resistance": 10, "agility": 33, "focus": 20, "hp_max": 22, "mp_max": 0, "loot_table_id": "loot_table.bandit.cutpurse"}
  ]
}
```

### 5.2 Oracles

| Oracle | 判定 |
|---|---|
| Golden Replay | 事件流字节级 diff 为空 |
| 守恒审计 | 物品/货币事务前后守恒（含 mint/burn 显式项） |
| 非永久性 Property | 任意随机行动序列下 Resident 终局 ∈ 四种非永久 outcome |
| 双实现一致 | Python/TypeScript 公式与 Seed 派生结果一致 |
| 泄漏审计 | token/Reservation/状态实例在 ended 后归零 |

### 5.3 测试矩阵

| 测试 ID | 层级 | 覆盖规则 |
|---|---|---|
| `TEST-COMBAT-001` | Unit/Contract | `RULE-COMBAT-001..006` |
| `TEST-COMBAT-002` | Unit | `RULE-COMBAT-008..009` |
| `TEST-COMBAT-003` | Unit | `RULE-COMBAT-010..011` |
| `TEST-COMBAT-004` | Integration | `RULE-COMBAT-007`, `RULE-COMBAT-012` |
| `TEST-COMBAT-005` | Unit | `RULE-COMBAT-013..015` |
| `TEST-COMBAT-006` | Unit | `RULE-COMBAT-016` |
| `TEST-COMBAT-007` | Integration | `RULE-COMBAT-017..018` |
| `TEST-COMBAT-008` | Unit | `RULE-COMBAT-019` |
| `TEST-COMBAT-009` | Property | `RULE-COMBAT-020..023` |
| `TEST-COMBAT-010` | Unit/Contract | `RULE-COMBAT-024..025` |
| `TEST-COMBAT-011` | Unit | `RULE-COMBAT-026..028` |
| `TEST-COMBAT-012` | Unit | `RULE-COMBAT-029..030` |
| `TEST-COMBAT-013` | Integration | `RULE-COMBAT-031` |
| `TEST-COMBAT-014` | Unit | `RULE-COMBAT-032..034` |
| `TEST-COMBAT-015` | Integration | `RULE-COMBAT-035` |
| `TEST-COMBAT-016` | Property/Contract | `RULE-COMBAT-036..037` |
| `TEST-COMBAT-017` | Contract | `RULE-COMBAT-038..039` |
| `TEST-COMBAT-018` | Unit | `RULE-COMBAT-040` |
| `TEST-COMBAT-019` | Integration | `RULE-COMBAT-041..043` |
| `TEST-COMBAT-020` | Unit/E2E | `RULE-COMBAT-044..045` |
| `TEST-COMBAT-021` | Integration | `RULE-COMBAT-046..047` |
| `TEST-COMBAT-022` | Browser E2E | `RULE-COMBAT-048` |
| `TEST-COMBAT-023` | Unit | `RULE-COMBAT-049` |
| `TEST-COMBAT-024` | Property | `RULE-COMBAT-050..051`, `RULE-COMBAT-053` |
| `TEST-COMBAT-025` | Integration | `RULE-COMBAT-052`, `RULE-COMBAT-054` |
| `TEST-COMBAT-026` | Unit | `RULE-COMBAT-055..056` |
| `TEST-COMBAT-027` | Unit | `RULE-COMBAT-057` |
| `TEST-COMBAT-028` | Integration/Contract | `RULE-COMBAT-058..059` |
| `TEST-COMBAT-029` | Integration | `RULE-COMBAT-060` |
| `TEST-COMBAT-030` | Integration | `RULE-COMBAT-061` |
| `TEST-COMBAT-031` | Crash Point Matrix | `RULE-COMBAT-062..063` |
| `TEST-COMBAT-032` | Contract | `RULE-COMBAT-064` |
| `TEST-COMBAT-033` | Golden Replay | 全 fixture 事件流字节一致（跨规则回归锚） |
| `TEST-COMBAT-034` | Simulation | `fixture.combat.model_offline` 全程降级完整终结（`RULE-COMBAT-041`, `RULE-COMBAT-066`） |
| `TEST-COMBAT-035` | Simulation | 30 游戏日模拟：无 Resident 永久删除、无重复战斗结算、无 token/锁泄漏（`RULE-COMBAT-051`, `RULE-COMBAT-060..061`） |
| `TEST-COMBAT-036` | Audit | 规则覆盖审计与 fixture/oracle 注册完整性（`RULE-COMBAT-065..066`） |

## 6. 正常流程

1. 构建期注册 fixture 与 oracle，校验引用的 Stable Catalog ID 全部存在。
2. Unit/Property/Contract 层在每次提交运行；Integration 与 Crash Point Matrix 在合并前运行。
3. Golden Replay 基准随 formula/schema version 一起版本化，变更需显式重录并审查 diff。
4. Simulation 与 Browser E2E 在发布 Gate 运行（`DOC-RELEASE-011` 编排）。
5. `TEST-COMBAT-036` 的覆盖审计在文档与代码 CI 双侧执行。

## 7. 边界情况

- 公式版本升级：旧 Golden Replay 以旧 formula version 继续通过（旧 timeline 固定版本），新版本录制新基准，二者并存。
- fixture 中的 Creature template 变更：fixture 引用注册 ID，template 语义变更必须发布新 ID，旧 fixture 不漂移。
- 真实模型补充测试失败：不阻塞矩阵判定，但记录为模型行为回归告警。
- 浏览器 E2E 环境无显卡加速：按 `DOC-RENDER-012` 低画质档运行，断言不依赖像素级渲染。
- 矩阵行与规则重编号：规则 ID 定义后不复用（`RULE-FOUNDATION-031`），矩阵只增行不改历史语义。

## 8. 错误与降级

覆盖审计失败、fixture 引用悬空、Golden Replay diff 非空均为构建失败，不允许跳过。测试基础设施不可用时相应 Gate 保持未通过状态，禁止以人工声明替代机械判定（`DOC-FOUNDATION-007` 追踪原则）。

## 9. 安全与性能

fixture 与 Golden Replay 不含真实 API Key、用户数据或未脱敏 Prompt；FakeModelProvider 响应库随 fixture 版本化。全量 Unit+Property 层目标 < 60 real s；Crash Point Matrix 与 Simulation 允许更长预算但设上限 30 real min。

## 10. 验收标准

- 矩阵覆盖 `RULE-COMBAT-001..066` 全部规则，覆盖审计通过。
- 六个核心 fixture 全部可加载且 Golden Replay 基准存在。
- 模型离线、崩溃恢复、30 日模拟三类跨层测试通过。
- 双实现一致性与守恒/泄漏 oracle 全绿。
- 默认测试零真实网络调用。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-COMBAT-033` | Golden Replay 字节一致 |
| `TEST-COMBAT-034` | 模型全故障下战斗完整合法终结 |
| `TEST-COMBAT-035` | 30 游戏日模拟核心不变量保持 |
| `TEST-COMBAT-036` | 规则覆盖审计与注册完整性（`RULE-COMBAT-065..066`） |

## 12. 关联文档

- `DOC-FOUNDATION-007`：REQ/DES/RULE/TEST 追踪原则
- `DOC-RELEASE-011`：项目级测试策略与 Gate 编排
- `DOC-TIME-010`：Seed 确定性与 AI Replay 基础
- `DOC-COMBAT-001..011`：被覆盖规则的定义文档

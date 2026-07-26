---
doc_id: DOC-RELEASE-011
title: 项目级测试策略
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - project-test-layers
  - fake-model-default-policy
  - long-simulation-gates
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-007
  - DOC-RELEASE-003
  - DOC-RELEASE-006
  - DOC-AI-012
  - DOC-ECON-012
  - DOC-TIME-012
requirements:
  - REQ-PRODUCT-010
  - REQ-RELEASE-011
last_updated: 2026-07-26
---

# 项目级测试策略

## 1. 目的

`REQ-RELEASE-011`：定义项目统一的八层测试层级（Unit → Property → Contract → Integration → Simulation → Browser E2E → Visual QA → Packaged Release）、各层触发点与准入准出、FakeModelProvider 默认与真实 DeepSeek 显式开关、1/7/30 游戏日长模拟的量化门槛，以及缺陷与 flaky 处理纪律，作为所有 domain 测试文档之上的编排层。

## 2. 非目标

本文件不重述各 domain 的具体测试用例（`TEST-<DOMAIN>-NNN` 归各 owner 文档）；不定义 AI 评估的 fixture/oracle 细节（`DOC-AI-012` canonical）；不定义经济守恒审计内容（`DOC-ECON-012`）；不定义 G9 现场执行清单（`DOC-RELEASE-012`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Test Layer | 八层之一，具有固定的范围、环境与触发点 |
| Per-commit Suite | 每次提交必须全绿的层集合（Unit/Property/Contract） |
| Nightly Suite | 每日执行的层集合（+ Integration、1 游戏日 Simulation、Browser E2E） |
| Release Candidate Suite | 发布候选必须全绿的全部八层 |
| `AI_TOWN_REAL_MODEL` | 唯一允许启用真实 DeepSeek 的测试开关（本文件 canonical） |
| Quarantine List | 被隔离的 flaky 用例清单，发布前必须清零 |

## 4. 规则与不变量

- `RULE-RELEASE-079`：八层层级、范围与触发点按第 5.1 节表固定；发布候选必须八层全绿——任何一层缺失、跳过或标记 skip 即 Release Candidate Suite 不通过，G9 不得开始（`DOC-RELEASE-012`）。
- `RULE-RELEASE-080`：所有自动化测试默认使用 `FakeModelProvider`（行为契约由 `RULE-AI-067` canonical 定义：按 input hash 固定响应，可注入 timeout、empty、invalid JSON、forbidden、rate limit、late result）；真实 DeepSeek 只在显式设置 `AI_TOWN_REAL_MODEL=1` 的手动冒烟套件中使用，该套件不在 CI 必经路径，其结果不作为回归判定依据。
- `RULE-RELEASE-081`：AI 行为评估门（`DOC-AI-012`：legality、forbidden、secret leakage、latency/token、重复行为、人格一致性、降级次数）整体纳入 Release Candidate Suite 且 release-blocking；secret canary 或 forbidden commit 任一出现即整套失败（遵循 `RULE-AI-069`），不得以均值抵消。
- `RULE-RELEASE-082`：Simulation 层执行 1、7、30 游戏日三档（对应 `TEST-AI-050..052` 与 `TEST-TIME-031` 一类长测），运行于 FakeModelProvider + 固定 Seed；30 游戏日档必须逐项满足第 5.2 节量化门槛（内存、队列、经济守恒、居民卡死、关系漂移、任务膨胀、存档增长），任一超限即失败。
- `RULE-RELEASE-083`：Simulation 与 Recovery 组合必须覆盖固定 crash 注入点集合（事务提交前后、Snapshot 写入中、迁移 Step 间、branch-on-load 步骤间、关闭序列各阶段），恢复后按 `DOC-RELEASE-006` 的 Recovery Chain 断言 Revision 与状态哈希一致（配合 `TEST-TIME-025..027`、`TEST-RELEASE-021`）。
- `RULE-RELEASE-084`：Browser E2E 在真实 Chromium 内核浏览器执行第 5.3 节 14 项场景；断言以后端权威状态 + DOM 双源为准，禁止仅截图比对判定逻辑正确性；Visual QA 层才使用截图基线（阈值比对 + 人工复核记录）。
- `RULE-RELEASE-085`：失败处理纪律：禁止自动重试掩盖失败（重试仅允许用于诊断收集，结果仍记失败）；flaky 用例进入 Quarantine List 并附 issue 追踪，发布前清零；无测试覆盖的 Must Requirement 视为 `DOC-FOUNDATION-007` 追踪审计失败。

## 5. 数据与接口

### 5.1 八层定义

`DES-RELEASE-022`：

| 层 | 范围 | 模型 | 触发 |
|---|---|---|---|
| Unit | 纯函数与单模块逻辑 | 无 | Per-commit |
| Property | 不变量随机化验证（守恒、幂等、坐标等） | 无 | Per-commit |
| Contract | Schema/协议/仓储 Port 契约（REST、Event、Proposal） | FakeModelProvider | Per-commit |
| Integration | 多 domain 组合流程（交易、战斗、建造、存档） | FakeModelProvider | Nightly |
| Simulation | 1/7/30 游戏日整世界运行 + crash 注入 | FakeModelProvider | 1 日 Nightly；7/30 日 Release Candidate |
| Browser E2E | 真实浏览器全链路场景 | FakeModelProvider | Nightly（子集）/ Release Candidate（全量） |
| Visual QA | 截图基线 + 人工复核清单 | FakeModelProvider | Release Candidate |
| Packaged Release | 发布包冒烟 + G9 现场验收 | FakeModelProvider / 真实 Key 单例冒烟 | Release Candidate |

### 5.2 30 游戏日 Simulation 门槛

`DES-RELEASE-023`：机器可读阈值（runner 直接消费）：

```json
{
  "simulation_gate_version": 1,
  "profile": "sim_30_game_days",
  "seed_policy": "fixed_seed_fixed_fixture",
  "thresholds": {
    "process_rss_max_mib": 2048,
    "queue_depth_bounded": {"ai_requests": 64, "websocket_outbox": 1024, "long_actions": 256},
    "economy_conservation_violations": 0,
    "resident_stuck_max_game_hours": 6,
    "relationship_drift_abs_max": 40,
    "active_quests_max": 24,
    "world_storage_growth_max_mib": 512,
    "invariant_violations": 0,
    "unrecovered_crash_injections": 0
  },
  "checks": [
    {"check_id": "sim30.memory", "metric": "process_rss_max_mib", "source": "runtime_sampler"},
    {"check_id": "sim30.queues", "metric": "queue_depth_bounded", "source": "runtime_sampler"},
    {"check_id": "sim30.economy", "metric": "economy_conservation_violations", "source": "TEST-ECON-045, TEST-ECON-048"},
    {"check_id": "sim30.stuck", "metric": "resident_stuck_max_game_hours", "source": "scheduler_progress_audit"},
    {"check_id": "sim30.drift", "metric": "relationship_drift_abs_max", "source": "memory_social_audit"},
    {"check_id": "sim30.quests", "metric": "active_quests_max", "source": "event_director_audit"},
    {"check_id": "sim30.storage", "metric": "world_storage_growth_max_mib", "source": "release_storage_audit"},
    {"check_id": "sim30.invariants", "metric": "invariant_violations", "source": "DOC-FOUNDATION-005 recovery/periodic audit"},
    {"check_id": "sim30.crash", "metric": "unrecovered_crash_injections", "source": "TEST-RELEASE-021"}
  ]
}
```

`relationship_drift_abs_max` 指无交互事件支撑的关系值净漂移绝对上限（口径由 `DOC-MEMORY-*` owner 定义，本处只定门槛消费方式）。

### 5.3 Browser E2E 场景清单

固定 14 项：启动进入、创建世界、角色移动、碰撞阻挡、对话交流、进入室内、地图切换、镇长模式、建筑建造、回合战斗、手动存档、刷新恢复、全屏提示与切换、保存退出。每项绑定至少一个 `TEST-<DOMAIN>-NNN`（映射在 `DOC-FOUNDATION-007` 追踪矩阵）。

## 6. 正常流程

1. 开发者提交：Per-commit Suite（Unit/Property/Contract）全绿方可合入。
2. 每夜：Nightly Suite 运行 Integration、1 游戏日 Simulation、E2E 子集；失败次日优先修复。
3. 发布候选：全量八层 + 7/30 游戏日 + AI 评估门 + Visual QA + 发布包冒烟。
4. 全绿后进入 `DOC-RELEASE-012` 的 G9 现场验收。
5. 结果与追踪矩阵（`DOC-FOUNDATION-007`）同步更新，缺覆盖项阻塞发布。

## 7. 边界情况

- FakeModelProvider fixture 与最新 Prompt 版本漂移：Contract 层含 fixture 版本一致性断言（`RULE-AI-068` 语义），漂移即失败而非静默使用旧 fixture。
- 30 游戏日运行时长过长：允许提高 Tick 处理速率的 headless 加速模式，但必须保持与实时模式相同的事件序（Seed 固定、确定性调度），加速模式与实时模式 1 游戏日结果哈希一致才可用于长测。
- 真实 DeepSeek 冒烟遇限流：记录并跳过非关键断言，只保留连通性与 Schema 兼容断言；不因外部服务波动阻塞发布判定（真实模型可用性不是首版验收项，`REQ-PRODUCT-007` 保证降级可玩）。
- Visual QA 基线因美术更新失效：基线更新需美术 owner 复核签字记录，不允许测试工程师单方刷新基线。
- Windows 中文/空格路径用例：在 Packaged Release 层与 `TEST-RELEASE-029/033` 覆盖，CI 矩阵至少含一个中文用户名 runner。

## 8. 错误与降级

任何层失败：Release Candidate 状态回退，修复后重跑该层及其下游层（下游结果依赖上游环境）。测试基础设施故障（runner 宕机）与用例失败严格区分记录，前者可重跑、后者必须归因。不存在「有条件通过」「豁免发布」流程——需要放宽门槛时必须先修订本文件并走文档变更。

## 9. 安全与性能

- 全部测试环境使用 Secret Canary 而非真实 Key；`AI_TOWN_REAL_MODEL=1` 的冒烟机器上 Key 仍走 Credential Store（`DOC-RELEASE-007`），日志与产物过 Secret Scanner。
- CI 产物（日志、截图、录像）保留 30 天并过脱敏扫描后归档。
- Per-commit Suite 目标 ≤ 10 分钟；Nightly ≤ 4 小时；30 游戏日长测 ≤ 12 小时（headless 加速）。
- 测试数据库全部使用临时目录，禁止触碰真实 `%LOCALAPPDATA%\AI-Town`。

## 10. 验收标准

- 八层各自有可执行入口与机器可读结果（junit/json），层与触发点关系与 5.1 表一致。
- 强制注入一条 forbidden 提案与一枚 secret canary，AI 评估门与扫描器分别拦截且整套判失败。
- 30 游戏日长测报告覆盖 5.2 全部 9 项 check，无一缺失。
- Quarantine List 在发布候选时为空；追踪矩阵无「Must 无测试」项。
- 同一 Seed 的两次 1 游戏日 Simulation 结果状态哈希一致（确定性前提成立）。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-041` | `RULE-RELEASE-079..080` 层级完整性与模型默认策略 |
| `TEST-RELEASE-042` | `RULE-RELEASE-081..082` AI 评估门与 30 日量化门槛 |
| `TEST-RELEASE-043` | `RULE-RELEASE-083..084` crash 注入矩阵与 E2E 双源断言 |
| `TEST-RELEASE-044` | `RULE-RELEASE-085` 失败纪律、Quarantine 与覆盖审计 |

## 12. 关联文档

- `DOC-AI-012`：FakeModelProvider、评估 fixture 与门槛（canonical）
- `DOC-ECON-012`：经济守恒与恢复测试（sim30.economy 数据源）
- `DOC-TIME-012`：时间/调度测试与确定性验证
- `DOC-RELEASE-006`：crash 注入的恢复断言
- `DOC-RELEASE-012`：Packaged Release 层的现场清单
- `DOC-FOUNDATION-007`：需求—测试追踪矩阵

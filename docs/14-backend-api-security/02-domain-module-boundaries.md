---
doc_id: DOC-BACKEND-002
title: Domain 模块边界与依赖方向
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - backend-module-dependency-direction
  - domain-port-contract
  - application-orchestrator-uow
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
requirements:
  - REQ-BACKEND-002
last_updated: 2026-07-26
---

# Domain 模块边界与依赖方向

## 1. 目的

`REQ-BACKEND-002`：定义后端代码模块的允许依赖方向、Domain Port 契约、Application Orchestrator 的 Unit of Work 编排，以及可执行的依赖审计规则。落实 `RULE-FOUNDATION-004`（Domain 不得依赖 Phaser、SQLite SQL、具体模型 SDK）。

## 2. 非目标

本文不定义各 Domain 的业务规则与公式（各 domain canonical 文档），不定义数据库表结构（`DOC-RELEASE-001`），不定义前端模块。本文只约束后端 Python 包的可见性与调用方向。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Domain Module | `world/`、`residents/`、`economy/` 等纯规则包，只依赖 foundation 基元 |
| Domain Port | Domain 对外暴露的抽象接口（Repository、ModelProvider、Clock 等） |
| Application Orchestrator | 编排用例、事务与队列的薄层，不拥有 Domain 规则 |
| Adapter | 实现 Port 的基础设施层（SQLite repository、DeepSeek provider、ASGI 入口） |
| Unit of Work (UoW) | 一次命令的状态、事件、Reservation 结果的原子提交单元 |

## 4. 规则与不变量

- `RULE-BACKEND-007`：依赖方向只允许 `api/ -> orchestrator -> domain ports -> domain`，`bootstrap/` 可装配一切；Domain 包之间只允许通过对方公开 Port/DTO 交互，禁止 import 对方内部模块。
- `RULE-BACKEND-008`：Domain 包禁止 import：`fastapi`、`uvicorn`、`sqlite3` 及任何 SQL 构造器、DeepSeek/HTTP SDK、`phaser` 相关任何内容、`security/` 与 `diagnostics/` 的具体实现。
- `RULE-BACKEND-009`：`security/` 是唯一允许接触 Secret 明文句柄的包；其他包只能收到 opaque credential reference（见 `DOC-BACKEND-009`）。
- `RULE-BACKEND-010`：一次命令的状态变更、不可丢 DomainEvent、幂等结果与 Reservation 结果必须在同一 UoW 提交（落实 `RULE-FOUNDATION-006`、`RULE-FOUNDATION-029`）；Orchestrator 不允许跨 UoW 半提交。
- `RULE-BACKEND-011`：Domain 规则必须为纯确定性计算：输入为 aggregate 视图 + 命令参数 + Seed stream，输出为新状态与事件；禁止在 Domain 内读墙钟、随机数全局源或环境变量（时钟与随机由 `DOC-TIME-*` 的 Port 注入）。

## 5. 数据与接口

`DES-BACKEND-002`：包结构与允许依赖矩阵（行可依赖列）：

| 包 \ 可依赖 | foundation | domain 自身 | 其他 domain Port | orchestrator | persistence | security | ai | api | bootstrap |
|---|---|---|---|---|---|---|---|---|---|
| foundation 基元 | — | 否 | 否 | 否 | 否 | 否 | 否 | 否 | 否 |
| domain/* | 是 | 是 | 仅 Port/DTO | 否 | 否 | 否 | 否 | 否 | 否 |
| orchestrator | 是 | 经 Port | 经 Port | — | 仅 Port | 仅 Port | 经 Port | 否 | 否 |
| persistence/ | 是 | 否 | 否 | 否 | — | 否 | 否 | 否 | 否 |
| security/ | 是 | 否 | 否 | 否 | 否 | — | 否 | 否 | 否 |
| ai/ | 是 | 经 Port | 经 Port | 否 | 否 | 仅凭据引用 | — | 否 | 否 |
| api/ | 是 | 否 | 否 | 是 | 否 | 是 | 否 | — | 否 |
| diagnostics/ | 是 | 否 | 否 | 否 | 否 | 否 | 否 | 否 | 否 |
| bootstrap/ | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 | — |

UoW 契约：

```text
with unit_of_work(world_id) as uow:
    result = domain_port.apply(command, aggregate_view, seed_stream)
    uow.stage_state(result.state)
    uow.stage_events(result.events)          # 满足 RULE-FOUNDATION-021 全字段
    uow.stage_idempotency(command_id, result_ref)
    uow.stage_reservations(reservation_outcomes)
    uow.run_commit_checks(affected_invariants)  # DOC-FOUNDATION-005
    revision = uow.commit()                   # 原子；任一失败全部回滚
```

Domain Port 形态示例：`EconomyRepository.load_inventory(owner_id) -> InventoryView`、`ModelProvider.complete(request, credential_ref) -> ModelArtifact`。Port 只暴露 DTO，不暴露 ORM 行或 SDK 对象。

## 6. 正常流程

1. `bootstrap` 构建全部 Adapter 并注入 Orchestrator 与各 Domain。
2. 命令到达后 Orchestrator 开启 UoW，经 Port 调用 owner Domain。
3. Commit Check 通过后单点 commit；Outbox 从已提交事件读取并发布。
4. 依赖审计作为 CI 静态检查运行（import graph 白名单比对），违规即构建失败。

## 7. 边界情况

- 跨 Domain 读取（如 AI context 需要 economy 报价）：只允许读 Read Model 投影或经对方只读 Port；禁止跨包直读内部状态。
- 两个 Domain 需要一致的联合写入：由 Orchestrator 在同一 UoW 内按固定顺序调用双方 Port，commit checks 覆盖联合写集。
- 新 Domain 加入：必须先在 `DOC-FOUNDATION-003` 登记边界，再扩展本文依赖矩阵，禁止先写代码后补登记。

## 8. 错误与降级

依赖审计失败即构建失败，不存在运行时绕过。运行期发现 Domain 尝试越层调用（理论上被审计阻止）按 `BACKEND_INTERNAL_INVARIANT` 处理：当前 UoW 回滚、暂停相关 owner 写入并告警。

## 9. 安全与性能

模块边界是 Secret 与注入防护的第一道防线：Domain 无网络与文件 I/O 能力，天然无法外泄 Secret 或执行外部输入。Port 接口保持窄接口（每 Port ≤ 12 方法），DTO 不可变，避免跨层传递可变大对象造成拷贝开销。

## 10. 验收标准

- import 静态审计覆盖全部后端包，违反 `RULE-BACKEND-008` 的引用为零。
- 每个 Domain Port 有独立 fake 实现，Domain 测试不启动 ASGI、SQLite 或网络。
- UoW 故障注入证明状态、事件、幂等结果与 Reservation 原子提交/回滚。
- Domain 测试证明规则函数对相同输入产生相同输出（含 Seed stream）。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-005` | `RULE-BACKEND-007..008` 依赖矩阵静态审计 |
| `TEST-BACKEND-006` | `RULE-BACKEND-010` UoW 原子性故障注入 |
| `TEST-BACKEND-007` | `RULE-BACKEND-011` Domain 确定性（相同输入相同输出） |
| `TEST-BACKEND-008` | `RULE-BACKEND-009` 非 security 包无 Secret 句柄访问路径 |

## 12. 关联文档

- `DOC-FOUNDATION-002`：模块责任表与队列
- `DOC-FOUNDATION-003`：Domain 边界与 owner
- `DOC-FOUNDATION-005`：提交原子性与不变量检查
- `DOC-BACKEND-009`：Secret 句柄边界
- `DOC-BACKEND-010`：事务与幂等细化

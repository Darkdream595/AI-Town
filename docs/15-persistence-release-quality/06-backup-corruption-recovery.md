---
doc_id: DOC-RELEASE-006
title: 备份、损坏分诊与恢复
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - backup-retention-policy
  - corruption-triage-ladder
  - disk-full-behavior
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RELEASE-001
  - DOC-RELEASE-002
  - DOC-RELEASE-003
  - DOC-RELEASE-004
  - DOC-TIME-009
requirements:
  - REQ-PRODUCT-008
  - REQ-RELEASE-006
last_updated: 2026-07-26
---

# 备份、损坏分诊与恢复

## 1. 目的

`REQ-RELEASE-006`：定义备份种类与保留策略、启动恢复链的固定检查顺序、损坏分诊阶梯（从 WAL 自愈到备份还原再到不可恢复声明）以及磁盘满 / IO 错误时的行为，保证任何修复动作前原始文件先被复制，任何降级都不静默丢失已提交 Revision。

## 2. 非目标

本文件不定义 Snapshot/重放算法（`DOC-RELEASE-003`）、迁移失败还原的触发（`DOC-RELEASE-002`）、TIME 恢复审计的内部断言（`DOC-TIME-009`）与诊断包内容（`DOC-RELEASE-010`）；本文件只拥有它们之间的编排顺序与备份文件策略。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Pre-repair Copy | 任何修复动作前对全部相关文件的只读复制件 |
| Recovery Chain | 打开世界时固定顺序执行的 8 步检查 |
| Triage Ladder | 损坏后按数据损失从小到大排列的恢复层级 L1–L6 |
| Lossless Level | 不丢失任何已提交 Revision 的层级（L1、L2） |
| Lossy Level | 会回退到更早锚点的层级（L3–L5），需玩家确认 |
| RecoveryReport | 一次恢复尝试的结构化结果记录 |

## 4. 规则与不变量

- `RULE-RELEASE-040`：任何修复或还原动作开始前，必须把相关原始文件（数据库、`-wal`、`-shm`、Snapshot）完整复制到 `backups\corrupt-<utc>\` 并校验字节数与 SHA-256；复制失败则修复不得开始。corrupt 复制永不被自动清理。
- `RULE-RELEASE-041`：Recovery Chain 固定 8 步顺序：(1) 文件存在与打开、PRAGMA 校验 → (2) `PRAGMA integrity_check` / `foreign_key_check` → (3) Schema 迁移（`DOC-RELEASE-002`）→ (4) Snapshot 哈希校验 → (5) Event Log 连续性校验 → (6) Reservation/长任务重建（`DOC-TIME-009`）→ (7) in-flight AI 请求处置（`RULE-TIME-052`）→ (8) 核心不变量 Recovery Audit（`DOC-FOUNDATION-005`）。任一步失败即停在该步进入分诊，不跳步。
- `RULE-RELEASE-042`：磁盘空间预检：Snapshot 生成、迁移、导出、导入、手动存档、branch-on-load 开始前要求可用空间 ≥ 估算需求的 2 倍；不足则拒绝该操作并明确提示，普通写事务不受预检约束。
- `RULE-RELEASE-043`：遇到 `SQLITE_FULL` 或 IO 错误：当前事务回滚、Revision 不增长、世界立即暂停并进入 `paused_disk_full` / `paused_io_error` 状态；系统绝不自动删除任何用户数据（存档、备份、世界）换取空间；日志轮转停写新日志（`DOC-RELEASE-010`），世界数据写入优先级最高。
- `RULE-RELEASE-044`：Triage Ladder 依序尝试且每级写审计记录：L1 SQLite WAL 自恢复重开 → L2 最新有效 Snapshot + Event tail 重建（无损）→ L3 更早自动恢复点 → L4 手动槽位 → L5 Pre-migration/corrupt 备份还原 → L6 不可恢复声明。L3 及以下会丢失锚点之后的进度，必须向玩家列出候选锚点（含 game_time 与时间戳）并获得显式选择，禁止自动执行。
- `RULE-RELEASE-045`：Lossy Level 的执行走 branch-on-load 语义（`RULE-RELEASE-028`）：损坏的 Timeline 文件保留在 corrupt 复制中，新 Timeline 从所选锚点分支，历史证据不销毁。
- `RULE-RELEASE-046`：Pre-migration 备份每世界保留最近 3 份，更旧的在新备份校验通过后删除；备份文件名固定 `pre-migration-v{from}-v{to}-{utc}.sqlite3`，corrupt 目录名固定 `corrupt-{utc}`，均只含 ASCII。
- `RULE-RELEASE-047`：恢复成功的唯一判定：Recovery Chain 8 步全部通过且 `world_meta.revision` 与 Event Log tip 一致；否则 Recovery Barrier 不解除，世界不进入模拟。L6 声明必须列出已尝试层级、每级失败原因码与全部可用文件清单，并引导生成诊断包。

## 5. 数据与接口

### 5.1 分诊决策表

`DES-RELEASE-012`：

| 级别 | 前置条件 | 数据损失 | 玩家确认 |
|---|---|---|---|
| L1 | 数据库可打开，WAL 存在 | 无 | 不需要 |
| L2 | 有效 Snapshot + 连续 Event tail | 无 | 不需要 |
| L3 | 存在更早自动恢复点（≤ 5 个） | 锚点之后进度 | 需要，选锚点 |
| L4 | 存在手动槽位（≤ 3 个） | 锚点之后进度 | 需要，选槽位 |
| L5 | 存在 Pre-migration/corrupt 备份 | 备份点之后进度 | 需要 |
| L6 | 以上全部失败 | 世界不可用 | 声明并保留文件 |

RecoveryReport（写入 `diagnostics\` 并被 `DOC-RELEASE-010` 引用）：

```json
{
  "report_format_version": 1,
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "started_at": "2026-07-26T11:00:00.000Z",
  "chain_results": [
    {"step": 1, "name": "open_and_pragma", "passed": true},
    {"step": 2, "name": "integrity_check", "passed": false, "reason_code": "RELEASE_DB_INTEGRITY_FAILED"}
  ],
  "triage_attempts": [
    {"level": "L1", "passed": false, "reason_code": "RELEASE_WAL_RECOVER_FAILED"},
    {"level": "L2", "passed": true, "anchor_revision": 44000}
  ],
  "outcome": "recovered",
  "final_revision": 44000,
  "pre_repair_copy": "backups\\corrupt-20260726T110000Z"
}
```

### 5.2 接口

`DES-RELEASE-013`：

```text
run_recovery_chain(world_id) -> RecoveryReport
estimate_required_space(operation) -> ByteEstimate
preflight_disk_check(operation) -> Ok | InsufficientSpace
triage(world_id, failed_step) -> TriagePlan          # 只列候选，不执行
apply_triage_level(command_id, level, anchor) -> RecoveryReport
declare_unrecoverable(world_id) -> RecoveryReport    # outcome = "unrecoverable"
```

## 6. 正常流程

1. 打开世界时顺序执行 Recovery Chain；全部通过则直接进入 paused_ready，本文件不再介入。
2. 某步失败：立即生成 Pre-repair Copy，构建 TriagePlan。
3. 无损层级（L1/L2）自动执行并重跑 Recovery Chain。
4. 无损层级失败：UI 列出 L3/L4 候选锚点，玩家选择后按 branch-on-load 执行并重跑 Recovery Chain。
5. 成功后写 RecoveryReport（outcome=recovered），世界进入 paused_ready，由玩家继续。

## 7. 边界情况

- `-wal` 文件被杀毒软件删除：L1 直接失败但主库通常一致；L2 以 Snapshot + Event tail 验证后无损恢复，丢失的仅是未 checkpoint 的 WAL 事务（这些 Revision 未达持久边界，不属于「已提交且已确认」损失范围，报告中明确列出末尾 Revision 差值）。
- 崩溃发生在恢复过程中：Pre-repair Copy 幂等（同一 utc 目录已存在且校验通过则复用）；分诊从审计记录续跑。
- 磁盘满导致连 Pre-repair Copy 都无法建立：分诊冻结在「等待磁盘空间」状态，提示玩家清理其他文件；绝不跳过复制直接修复。
- 玩家在 L3 确认界面关闭进程：无任何修复执行，下次打开重新进入分诊，候选不变。
- `app.sqlite3` 本身损坏：同一 Triage 思路但层级只有 L1 → registry 重建（扫描 `worlds\` 目录重新登记，世界数据不动）→ L6；重建后各世界首次打开时走各自 Recovery Chain。
- 外部程序锁定数据库（`DOC-RELEASE-001` 边界）：不是损坏；busy 超时报错并保持暂停，提示关闭占用程序后重试。

## 8. 错误与降级

分诊每级失败都记录 reason_code 并进入下一候选级；跨级跳跃只允许「向更保守方向」（例如玩家直接选择 L4）。恢复期间世界严格保持暂停；任何层级都不得以关闭外键、忽略 integrity_check 结果或截断 Event Log 的方式「修好」。L6 之后世界在列表中标记 `needs_attention`，可被导出（原样字节）供外部分析，但不可打开。

## 9. 安全与性能

- Pre-repair Copy 与 RecoveryReport 不含 Secret；reason_code 为注册枚举，不携带自由文本用户内容。
- 恢复链与分诊只读取本世界目录与 `app.sqlite3`，不扫描用户其他文件。
- L2 重建时间目标 ≤ 30 s（首版规模：2000 Revision tail）；预检估算误差目标 ≤ 20%。
- corrupt 复制按世界隔离目录存放，避免多次损坏互相覆盖。

## 10. 验收标准

- 在 Recovery Chain 8 步各注入一种失败，系统停在正确步骤、生成 Pre-repair Copy 且原文件字节不变。
- 覆盖 L1–L5 每级的成功路径：恢复后 Recovery Chain 全绿且最终 Revision 与所选锚点一致。
- 磁盘满注入：事务回滚、世界 `paused_disk_full`、无任何用户文件被删除；释放空间后可恢复运行。
- L3/L4 从不自动执行；无玩家确认时世界保持暂停任意长时间。
- L6 场景保留全部原始文件与 corrupt 复制，报告列出全部尝试记录。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-021` | `RULE-RELEASE-040..041` Pre-repair Copy 与 8 步恢复链顺序 |
| `TEST-RELEASE-022` | `RULE-RELEASE-042..043` 空间预检与磁盘满行为 |
| `TEST-RELEASE-023` | `RULE-RELEASE-044..045` 分诊阶梯、玩家确认与分支化恢复 |
| `TEST-RELEASE-024` | `RULE-RELEASE-046..047` 备份保留、成功判定与 L6 声明 |

## 12. 关联文档

- `DOC-RELEASE-002`：迁移备份的生成时机
- `DOC-RELEASE-003`：Snapshot/Event tail 重建（L2 的执行体）
- `DOC-RELEASE-004`：L3/L4 锚点来源与 branch-on-load
- `DOC-RELEASE-010`：诊断包引用 RecoveryReport
- `DOC-TIME-009`：Recovery Barrier 与 TIME 侧审计
- `DOC-FOUNDATION-005`：Recovery Audit 的 invariant 集

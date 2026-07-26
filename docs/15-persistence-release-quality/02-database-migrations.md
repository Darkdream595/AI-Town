---
doc_id: DOC-RELEASE-002
title: 数据库 Schema 版本与迁移
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - database-schema-versioning
  - migration-execution-policy
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RELEASE-001
  - DOC-RELEASE-006
requirements:
  - REQ-PRODUCT-008
  - REQ-PRODUCT-010
  - REQ-RELEASE-002
last_updated: 2026-07-26
---

# 数据库 Schema 版本与迁移

## 1. 目的

`REQ-RELEASE-002`：定义 `app.sqlite3` 与每世界 `world.sqlite3` 的 schema 版本标识、只前向的分步 Migration 执行流程、迁移前强制备份、事务边界与完整性检查，保证任何版本升级失败都保留可用的原数据库并停止世界模拟，而不是产出半迁移状态。

## 2. 非目标

本文件不定义各 domain 状态表的列级内容（由各 owner 文档定义，迁移脚本只是其版本间桥接）；不定义备份保留策略与损坏恢复阶梯（`DOC-RELEASE-006`）；不定义 API 协议层 `protocol_version` 的兼容策略（`DOC-BACKEND-007`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `schema_version` | 数据库整体结构的单调整数版本，存于 `world_meta` / `app.sqlite3` 的版本表 |
| MigrationStep | 从版本 N 到 N+1 的注册迁移单元，含 SQL 与可选确定性 Python 变换 |
| Migration Chain | 从当前版本到目标版本的有序 MigrationStep 序列 |
| Pre-migration Backup | 迁移开始前对整库的 checkpoint 后复制件 |
| Supported Range | 当前发布包可打开的 `schema_version` 闭区间 `[min_supported, current]` |
| Post-migration Audit | 全部 Step 完成后的结构与数据完整性检查 |

## 4. 规则与不变量

- `RULE-RELEASE-009`：每个数据库有且只有一个 `schema_version`（单调整数，从 1 开始）；发布包声明 Supported Range，`schema_version > current` 的数据库必须拒绝打开且不写入任何字节，提示玩家使用更新版本。
- `RULE-RELEASE-010`：Migration 只前向。同一 `from_version → to_version` 路径由注册 MigrationStep 序列唯一确定；禁止运行期拼接动态 SQL、禁止跳版本捷径、禁止降级迁移——回退唯一手段是恢复 Pre-migration Backup。
- `RULE-RELEASE-011`：任何 MigrationStep 执行前，必须先对目标数据库执行 `PRAGMA wal_checkpoint(TRUNCATE)`，再复制整库为 Pre-migration Backup 并核对 SHA-256；备份失败则迁移不得开始。
- `RULE-RELEASE-012`：每个 MigrationStep 在独立 `BEGIN IMMEDIATE` 事务中执行，并在同一事务内把 `schema_version` 更新为该 Step 的 `to_version`；进程中断后重启时从持久化的 `schema_version` 与 `schema_migrations` 记录继续，不重复执行已完成 Step。
- `RULE-RELEASE-013`：Migration Chain 完成后必须通过 Post-migration Audit：`PRAGMA integrity_check` 返回 `ok`、`PRAGMA foreign_key_check` 返回空集、各 domain 注册的数据审计查询全部通过；任一失败即恢复 Pre-migration Backup 并保持该世界停止模拟。
- `RULE-RELEASE-014`：迁移不得改写、删除或重排 `event_log` 历史行（`RULE-FOUNDATION-027`）；允许的事件类操作仅限：追加 `MigrationCompleted` DomainEvent、重建投影表与索引、为旧事件登记 upcaster（读取时转换，原始 bytes 不变）。
- `RULE-RELEASE-015`：迁移期间该世界不进入模拟：GameTime 不推进（`RULE-FOUNDATION-038`）、不接受普通写 Command、不发起模型请求；`app.sqlite3` 的迁移必须在打开任何世界之前完成。
- `RULE-RELEASE-016`：MigrationStep 中的 Python 变换必须是确定性纯函数：输入只有本库数据与 Step 常量，禁止网络、随机数、系统时间与读取库外文件。

## 5. 数据与接口

### 5.1 版本记录表

`DES-RELEASE-003`：两个数据库使用相同的迁移记录结构（`app.sqlite3` 以 `app_meta` 表承载 `schema_version`，`world.sqlite3` 用 `world_meta.schema_version`）：

```sql
CREATE TABLE schema_migrations (
  to_version    INTEGER PRIMARY KEY,     -- 完成后到达的版本
  step_id       TEXT NOT NULL,           -- 注册的 MigrationStep 稳定 ID
  applied_at    TEXT NOT NULL,           -- UTC RFC 3339
  duration_ms   INTEGER NOT NULL,
  backup_file   TEXT NOT NULL,           -- 相对 backups\ 的文件名
  backup_sha256 TEXT NOT NULL
);
```

### 5.2 MigrationStep 注册清单

发布包内置只读注册清单（构建期生成，运行期不可修改）。示例：

```json
{
  "manifest_version": 1,
  "database": "world",
  "min_supported": 1,
  "current": 3,
  "steps": [
    {
      "step_id": "release.migration.world.v1_to_v2",
      "from_version": 1,
      "to_version": 2,
      "summary": "为 event_log 增加 correlation_id 索引并重建 idempotency_keys 唯一约束",
      "sql": ["CREATE INDEX idx_event_log_correlation ON event_log(correlation_id)"],
      "python_transform": null,
      "audit_queries": ["SELECT COUNT(*) FROM pragma_index_info('idx_event_log_correlation')"]
    },
    {
      "step_id": "release.migration.world.v2_to_v3",
      "from_version": 2,
      "to_version": 3,
      "summary": "world_meta 增加 parent_timeline_id 与 branch_source_revision 列",
      "sql": [
        "ALTER TABLE world_meta ADD COLUMN parent_timeline_id TEXT",
        "ALTER TABLE world_meta ADD COLUMN branch_source_revision INTEGER"
      ],
      "python_transform": null,
      "audit_queries": ["SELECT COUNT(*) FROM world_meta WHERE branch_source_revision IS NOT NULL AND parent_timeline_id IS NULL"]
    }
  ]
}
```

### 5.3 迁移执行接口

`DES-RELEASE-004`：迁移由 RELEASE 的 MigrationRunner 独占执行，Domain 模块不感知：

```text
plan_migration(database_path, manifest) -> MigrationPlan | RefuseToOpen
run_migration(plan) -> MigrationReport            # 逐 Step，含备份与审计
verify_post_migration(database_path) -> AuditReport
```

`MigrationReport` 含每个 Step 的 `step_id`、耗时、备份文件与 SHA-256、审计结果，供 `DOC-RELEASE-010` 诊断包摘要引用。

## 6. 正常流程

1. 后端启动，读取 `app.sqlite3` 版本；低于 current 则按本文件流程迁移 `app.sqlite3`。
2. 打开世界时读取 `world_meta.schema_version`，计算 Migration Chain；为空则直接进入恢复链（`DOC-RELEASE-006`）。
3. checkpoint 并生成 Pre-migration Backup，写入 `backups\pre-migration-v{from}-v{to}-{utc}.sqlite3`。
4. 逐 Step 在独立事务中执行 SQL 与确定性变换，同事务更新 `schema_version` 并写 `schema_migrations` 行。
5. 全链完成后执行 Post-migration Audit，追加 `MigrationCompleted` DomainEvent。
6. 迁移成功后继续正常打开流程（Snapshot 加载与 Event 重放，`DOC-RELEASE-003`）。

## 7. 边界情况

- 迁移中途断电：重启后 `schema_version` 停在最后完成的 Step；MigrationRunner 从下一 Step 继续，不重放已完成 Step；半写的未提交事务由 SQLite 回滚。
- `schema_migrations` 与 `schema_version` 不一致（例如手工改库）：视为损坏，转入 `DOC-RELEASE-006` 分诊，不猜测继续。
- 玩家从很旧版本直接升级：Migration Chain 跨多个版本逐步执行，每步独立备份记录；磁盘空间预检按最大单库 2 倍估算（`RULE-RELEASE-042`）。
- 导入的世界（`DOC-RELEASE-005`）版本低于 `min_supported`：拒绝导入并说明所需的中间版本，不尝试跳版本迁移。
- 中文/空格路径下的备份复制：与 `RULE-RELEASE-001` 相同的 Unicode 全路径处理，备份文件名只含 ASCII 与数字。

## 8. 错误与降级

任何 Step 失败（SQL 错误、审计失败、校验和不符、磁盘满）：当前事务回滚，MigrationRunner 停止后续 Step，恢复流程提示玩家从 Pre-migration Backup 还原（`DOC-RELEASE-006` 执行还原）。该世界保持停止模拟；其他世界与 `app.sqlite3` 不受影响。迁移失败不允许以「跳过该 Step」或「忽略审计」的方式降级。

## 9. 安全与性能

- MigrationStep 清单在构建期固化并进入发布包 manifest 校验（`DOC-RELEASE-009`），运行期篡改会导致包完整性校验失败。
- 迁移 SQL 不含用户输入拼接；`python_transform` 在无网络权限的进程内执行。
- 单 Step 目标耗时 ≤ 30 s（首版数据规模）；超过 10 s 的迁移必须向 UI 报告进度状态，防止玩家误判卡死强杀进程。
- 备份复制使用流式拷贝，内存占用 O(1)。

## 10. 验收标准

- 对 v1 数据库执行全链迁移后，Post-migration Audit 通过且 `schema_migrations` 行数等于 Step 数。
- 在每个 Step 边界注入进程终止，重启后迁移可继续完成，最终库与一次性完成的库逐表 dump 一致。
- 篡改任一 Step 的 SQL 使其失败时，原数据库文件字节不变（与 Pre-migration Backup 一致），世界不进入模拟。
- `schema_version` 高于 current 的数据库打开被拒绝，文件 mtime 与内容不变。
- 迁移全过程 `event_log` 既有行的 `event_id`、`revision`、payload 字节完全不变。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-005` | `RULE-RELEASE-009..010` 版本区间、拒绝打开与唯一迁移路径 |
| `TEST-RELEASE-006` | `RULE-RELEASE-011..012` 备份前置、逐 Step 事务与断点续迁 |
| `TEST-RELEASE-007` | `RULE-RELEASE-013`, `RULE-RELEASE-016` 完整性审计、失败还原与确定性变换 |
| `TEST-RELEASE-008` | `RULE-RELEASE-014..015` Event Log 不可变与迁移期暂停 |

## 12. 关联文档

- `DOC-RELEASE-001`：数据库布局与 PRAGMA 策略
- `DOC-RELEASE-006`：备份还原与损坏分诊
- `DOC-RELEASE-009`：发布包 manifest 与迁移清单固化
- `DOC-BACKEND-007`：协议层 Schema 版本（与本文件的存储版本相互独立）
- `DOC-FOUNDATION-005`：`RULE-FOUNDATION-027` 事件历史不可改写

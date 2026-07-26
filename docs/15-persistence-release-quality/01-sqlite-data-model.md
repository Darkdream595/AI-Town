---
doc_id: DOC-RELEASE-001
title: SQLite 数据模型与存储布局
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - sqlite-storage-layout
  - wal-connection-policy
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-BACKEND-001
requirements:
  - REQ-PRODUCT-008
  - REQ-PRODUCT-014
  - REQ-PRODUCT-015
  - REQ-PRODUCT-019
  - REQ-RELEASE-001
last_updated: 2026-07-26
---

# SQLite 数据模型与存储布局

## 1. 目的

`REQ-RELEASE-001`：定义程序文件与用户数据的分离、全局 `app.sqlite3` 与每世界 `world.sqlite3` 的职责、规范化当前状态 Schema 的归属原则，以及 WAL、外键、单写入等连接级策略，保证所有持久化写入可恢复、可校验、原子提交。

## 2. 非目标

本文件不定义各 domain 业务表的列级 Schema（由 `DOC-MAP-*`、`DOC-RESIDENT-*`、`DOC-ECON-*` 等 owner 文档定义）；不定义 Migration 流程（`DOC-RELEASE-002`）、Snapshot 与 Event Log 细节（`DOC-RELEASE-003`）和存档槽位（`DOC-RELEASE-004`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `app.sqlite3` | 全局应用数据库：世界注册表、非敏感设置、发布包版本戳 |
| `world.sqlite3` | 单个世界的数据库：规范化当前状态、Domain Event Log、Snapshot 元数据 |
| User Data Root | `%LOCALAPPDATA%\AI-Town`，所有用户数据的唯一根目录 |
| Write Connection | 每数据库唯一写连接，经单写入队列串行化 |
| Read Connection | 只读查询连接池，服务投影与 API 查询 |
| `WAL` | Write-Ahead Logging 日志模式，配套 `-wal`/`-shm` 文件 |

## 4. 规则与不变量

- `RULE-RELEASE-001`：程序安装目录只读；一切运行期可变数据写入 `%LOCALAPPDATA%\AI-Town`，路径必须为 Unicode 全路径，支持中文与空格目录名。
- `RULE-RELEASE-002`：每个世界一个独立 `worlds\<world_id>\world.sqlite3`；跨世界 JOIN、跨世界外键和共享表一律禁止。
- `RULE-RELEASE-003`：所有数据库打开时必须设置 `PRAGMA journal_mode=WAL`、`PRAGMA foreign_keys=ON`、`PRAGMA busy_timeout=5000`、`PRAGMA synchronous=NORMAL`。
- `RULE-RELEASE-004`：每数据库进程内只有一个 Write Connection；所有写事务经单写入队列提交，读操作使用独立只读连接，不得升级为写。
- `RULE-RELEASE-005`：状态写入与其不可丢 DomainEvent 在同一事务内原子提交（`RULE-FOUNDATION-029`）；禁止单独提交状态或单独提交事件。
- `RULE-RELEASE-006`：任何 Secret（含 DeepSeek API Key）不得出现在任何 SQLite 表、索引、WAL 或备份文件中（落实 `REQ-PRODUCT-019`、`RULE-FOUNDATION-024`）。
- `RULE-RELEASE-007`：干净退出时对每个数据库执行 `PRAGMA wal_checkpoint(TRUNCATE)`；崩溃后不强制 checkpoint，由恢复流程处理（`DOC-RELEASE-006`）。
- `RULE-RELEASE-008`：每世界 Revision 语义遵循 `RULE-FOUNDATION-023`，持久化于世界元数据表 `world_meta(revision)`，任何回滚不得递减。

## 5. 数据与接口

### 5.1 目录布局

```text
%LOCALAPPDATA%\AI-Town\
├─ app.sqlite3                 # 全局：world_registry、app_settings、release_stamp
├─ worlds\
│  └─ <world_id>\              # ULID 目录名，避免中文路径拼接歧义
│     ├─ world.sqlite3         # 当前活动 Timeline
│     ├─ world.sqlite3-wal
│     ├─ world.sqlite3-shm
│     ├─ timelines\            # branch-on-load 归档的旧 Timeline（DOC-RELEASE-004）
│     ├─ snapshots\
│     ├─ saves\
│     └─ backups\
├─ trash\                      # 可恢复删除的世界（DOC-RELEASE-005）
├─ secrets\                    # 仅 DPAPI 密文文件（DOC-RELEASE-007），无明文
├─ runtime\                    # instance.json 等进程运行期状态（DOC-RELEASE-008）
├─ logs\
└─ diagnostics\
```

### 5.2 `app.sqlite3` 核心表

`DES-RELEASE-001`：

```sql
CREATE TABLE world_registry (
  world_id        TEXT PRIMARY KEY,        -- ULID
  display_name    TEXT NOT NULL,
  seed_hex        TEXT NOT NULL,           -- 128-bit Seed，创建后不可变
  schema_version  INTEGER NOT NULL,
  created_at      TEXT NOT NULL,           -- UTC RFC 3339
  last_opened_at  TEXT,
  deleted_at      TEXT                     -- 软删除标记，见 DOC-RELEASE-005
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE release_stamp (package_version TEXT NOT NULL, build_id TEXT NOT NULL);
```

`app_settings` 只允许非敏感键（见 `DOC-RELEASE-007` 的键白名单）。

### 5.3 `world.sqlite3` 表族

| 表族 | owner | 说明 |
|---|---|---|
| `world_meta` | RELEASE | world_id、timeline_id、parent_timeline_id、branch_source_revision、revision、game_time、schema_version |
| 各 domain 状态表 | 各 domain | 规范化当前状态；列级定义见 owner 文档 |
| `event_log` | RELEASE | 追加式 Domain Event Log（`DOC-RELEASE-003`） |
| `snapshot_meta` | RELEASE | Snapshot 锚点 Revision 与文件引用（`DOC-RELEASE-003`） |
| `idempotency_keys` | BACKEND | `(command_id)` 幂等结果（`RULE-FOUNDATION-022`） |

### 5.4 仓储接口

`DES-RELEASE-002`：Domain 模块不直接执行 SQL（`DOC-FOUNDATION-002`），统一经由 `Repository`：`begin_write() / commit(events, state_writes) / rollback()` 与 `query_readonly(sql, params)`。仓储在 `commit` 内完成 Commit Check 失败回滚（`RULE-FOUNDATION-005` 流程）。

## 6. 正常流程

1. Launcher 启动后端，后端打开 `app.sqlite3`（不存在则按当前 schema 创建）。
2. 打开世界时校验 `world_registry` 记录、运行 Migration（`DOC-RELEASE-002`）、加载 Snapshot 并重放 Event Log（`DOC-RELEASE-003`）。
3. 运行期所有写经单写入队列，事务内写状态 + 事件 + 幂等结果并递增 Revision。
4. 干净退出时暂停 Tick、完成在途事务、`wal_checkpoint(TRUNCATE)`、关闭连接。

## 7. 边界情况

- 中文/空格用户名导致 `%LOCALAPPDATA%` 含非 ASCII 字符：所有路径以 `pathlib` Unicode 处理，禁止字节拼接；打包验收覆盖该场景（`DOC-RELEASE-012`）。
- `world.sqlite3-wal` 体积增长：写队列空闲时执行 `PASSIVE` checkpoint；超过 64 MiB 触发主动 checkpoint。
- 世界目录存在但 `world_registry` 无记录（孤立目录）：启动扫描列出为「未注册世界」，不自动挂载，由玩家确认导入。
- 数据库文件被外部程序占用：`busy_timeout` 后失败，按 `DOC-RELEASE-006` 报错并保持世界暂停，不重试覆盖。

## 8. 错误与降级

数据库打开失败、`PRAGMA` 校验失败或磁盘错误时，世界不进入模拟；后端以只读方式向玩家报告诊断入口（`DOC-RELEASE-010`）。任何写事务异常必须整体回滚，Revision 不增长。SQLite 不可用时系统不可降级为纯内存运行——那是未定义行为，必须停止。

## 9. 安全与性能

- Secret 禁入 SQLite（`RULE-RELEASE-006`）；诊断导出前按 `DOC-RELEASE-010` 扫描。
- 所有 SQL 使用参数绑定；Domain 不得拼接用户输入进 SQL。
- 只读连接设 `query_only=ON`；大查询分页并有行数上限，防止阻塞写队列。
- 索引仅由 owner 文档声明；禁止运行期 `CREATE INDEX` 即兴优化。

## 10. 验收标准

- 新机器首启后目录布局与本文件 5.1 完全一致，含中文路径用户。
- 任意崩溃点后恢复，已提交 Revision 的状态与事件完整（配合 `TEST-FOUNDATION-005`）。
- 全库扫描（含 WAL）不存在 Secret 字段与值。
- 干净退出后 `-wal` 文件长度为 0。
- 单写入压力下无 `database is locked` 导致的玩家可见失败。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-001` | `RULE-RELEASE-001..004` 布局、PRAGMA、单写入与只读连接 |
| `TEST-RELEASE-002` | `RULE-RELEASE-005`, `RULE-RELEASE-008` 原子提交与 Revision |
| `TEST-RELEASE-003` | `RULE-RELEASE-006` Secret 禁入扫描 |
| `TEST-RELEASE-004` | `RULE-RELEASE-007` checkpoint 与崩溃恢复交接 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：原子提交、Revision、Secret 不变量
- `DOC-FOUNDATION-006`：ULID、UTC timestamp、Revision 基元
- `DOC-RELEASE-002`：Schema 版本与迁移
- `DOC-RELEASE-003`：Snapshot 与 Event Log
- `DOC-RELEASE-005`：多世界注册与删除
- `DOC-RELEASE-007`：Secret 的真实存放位置

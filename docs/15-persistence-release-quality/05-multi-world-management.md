---
doc_id: DOC-RELEASE-005
title: 多世界管理与导入导出
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - world-registry-lifecycle
  - world-export-import
  - recoverable-world-deletion
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RELEASE-001
  - DOC-RELEASE-002
  - DOC-RELEASE-004
requirements:
  - REQ-PRODUCT-014
  - REQ-PRODUCT-015
  - REQ-RELEASE-005
last_updated: 2026-07-26
---

# 多世界管理与导入导出

## 1. 目的

`REQ-RELEASE-005`：定义 `world_registry` 承载的世界生命周期（创建、打开、关闭、重命名、删除、还原）、单次仅一个世界在线的运行约束、世界导出/导入包格式，以及默认可恢复的删除流程，使多世界数据彼此隔离且任何删除都有 30 天反悔窗口。

## 2. 非目标

本文件不定义世界内内容生成（`DOC-WORLD-*`）；不定义单世界内部的存档槽位（`DOC-RELEASE-004`）；不定义 REST 端点协议形状（`DOC-BACKEND-004`）；不定义备份文件保留（`DOC-RELEASE-006`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| World Lifecycle State | `active` / `closed` / `trashed` / `needs_attention` 四态 |
| Open World | 当前唯一被模拟与写入的世界；同一时刻至多一个 |
| Export Package | 单世界的自包含 `.aitown-world.zip` 归档 |
| Recoverable Deletion | 目录整体移入 `trash\` 并标记 `deleted_at` 的软删除 |
| Purge | 到期或玩家确认后的物理删除，不可逆 |
| Orphan Directory | `worlds\` 下存在但 `world_registry` 无对应记录的目录 |

## 4. 规则与不变量

- `RULE-RELEASE-032`：同一时刻至多一个世界处于 open 状态（全局单模拟、每库单写者的自然结果）；打开新世界前必须完成当前世界的干净关闭或其恢复流程；并发打开请求按 `command_id` 幂等串行化，后到者收到明确拒绝。
- `RULE-RELEASE-033`：世界创建必须由 CSPRNG 生成 world ULID 与 128-bit Seed（`DOC-FOUNDATION-006` 流程），并在同一事务写入 `world_registry`、创建目录骨架与初始 `world.sqlite3`；任一步失败整体回退且不留半创建目录。
- `RULE-RELEASE-034`：删除默认可恢复：写 `deleted_at`、目录整体原子移动到 `trash\<world_id>\`，保留 30 天；30 天内可整体还原；Purge 仅两种途径——玩家在 UI 对该世界二次确认，或启动清理任务对超期条目执行并写审计日志。
- `RULE-RELEASE-035`：导出必须在世界 closed 且 `wal_checkpoint(TRUNCATE)` 完成后进行；Export Package 只含 manifest、数据库（活动与归档 Timeline）、`snapshots\`、`saves\`；禁止包含 `logs\`、`diagnostics\`、`backups\`、任何 Secret 与绝对路径。
- `RULE-RELEASE-036`：导入前必须校验 manifest schema、逐文件 SHA-256 与 `schema_version ≤ current`；低于 `min_supported` 拒绝导入；`world_id` 与本机冲突时分配新 ULID 并在 registry 记录 `origin_world_id`；任何校验失败不落地任何文件。
- `RULE-RELEASE-037`：`display_name` 是仅用于显示的 Unicode 自由文本（含中文、空格、emoji）；文件系统路径永远只用 `world_id`（承接 `RULE-RELEASE-001` 的中文/空格路径安全），重命名只改 registry 行。
- `RULE-RELEASE-038`：启动一致性扫描：Orphan Directory 与悬空 registry 记录（有记录无目录）标记为 `needs_attention`，只读列出并等待玩家决定导入、还原或清除；系统不自动删除、不自动挂载。
- `RULE-RELEASE-039`：创建、删除、还原、Purge、导入、导出都是审计化 Command；删除与 Purge 需 UI 二次确认；全部操作经 REST（`DOC-BACKEND-004`），WebSocket 不承载世界管理。

## 5. 数据与接口

### 5.1 生命周期状态机

`DES-RELEASE-010`：

```text
(created) -> closed -> active -> closed
closed -> trashed -> closed          # 还原
trashed -> (purged)                  # 二次确认或 30 天到期
closed/scan -> needs_attention -> closed | trashed
```

`world_registry` 列定义见 `DOC-RELEASE-001` 5.2；`deleted_at` 非空即 `trashed`。

### 5.2 Export Package 格式

`DES-RELEASE-011`：`<display_name 清洗为 ASCII>-<world_id>.aitown-world.zip`，内部布局：

```text
manifest.json
world.sqlite3
timelines/<timeline_id>.sqlite3
snapshots/...
saves/...
```

`manifest.json`：

```json
{
  "package_format_version": 1,
  "package_kind": "aitown-world-export",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "origin_world_id": null,
  "display_name": "王冠溪 存档一",
  "seed_hex": "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
  "schema_version": 3,
  "app_package_version": "1.0.0",
  "exported_at": "2026-07-26T10:00:00.000Z",
  "files": [
    {"path": "world.sqlite3", "sha256": "1111111111111111111111111111111111111111111111111111111111111111", "size_bytes": 52428800}
  ]
}
```

### 5.3 接口

```text
create_world(command_id, display_name) -> WorldRegistryRow
open_world(command_id, world_id) -> OpenResult          # 触发迁移 + 恢复链
close_world(command_id) -> CloseResult                  # DOC-TIME-009 干净关闭
rename_world(command_id, world_id, display_name) -> WorldRegistryRow
delete_world(command_id, world_id, confirm) -> TrashResult
restore_world(command_id, world_id) -> WorldRegistryRow
purge_world(command_id, world_id, confirm) -> PurgeResult
export_world(command_id, world_id, target_path) -> ExportReport
import_world(command_id, source_path) -> ImportReport
```

## 6. 正常流程

1. 首启创建 `app.sqlite3`，世界列表为空；玩家创建世界 A、B。
2. 打开 A：registry 校验 → 迁移（`DOC-RELEASE-002`）→ Snapshot/事件恢复（`DOC-RELEASE-003`）→ 运行。
3. 切换到 B：先对 A 执行干净关闭（含关闭 Snapshot），registry 更新 `last_opened_at`，再打开 B。
4. 删除 A：二次确认 → 目录移入 `trash\` → 列表显示可还原倒计时。
5. 导出 B：关闭 → checkpoint → 打包 → 校验 manifest → 写入玩家选择的目标路径。
6. 在另一台机器导入该包：校验 → 解压到 `worlds\<world_id>\` → registry 登记 → 首次打开时按需迁移。

## 7. 边界情况

- 导入包的 `world_id` 已存在于本机（含 `trash\` 内）：分配新 ULID，目录与 registry 用新 ID，manifest 的原 ID 记入 `origin_world_id`；两个世界互不影响。
- 目标导出路径位于含中文与空格的目录（如玩家桌面）：Unicode 全路径处理；zip 内部路径全部为 ASCII 相对路径。
- 删除当前 open 世界：先执行干净关闭，再进入删除流程；关闭失败则删除中止。
- `trash\` 中世界与在用世界同名 `display_name`：允许，列表以 `world_id` 短后缀消歧显示。
- 移动 `trash\` 目录跨卷失败（玩家自定义符号链接）：回退为复制+校验+删除源的三步原子序列，中断时以校验结果判定归属，不出现两处半份数据。
- 导入超大包磁盘不足：预检失败（`RULE-RELEASE-042`），不开始解压。

## 8. 错误与降级

导出/导入是全有或全无操作：任何一步失败清理本次产生的临时文件并报告原因码，registry 不留半登记行。还原失败（目录被外部占用）保持 `trashed` 状态与倒计时冻结，提示玩家关闭占用程序。不提供「强制打开损坏世界」的降级入口——损坏一律走 `DOC-RELEASE-006` 分诊。

## 9. 安全与性能

- Export Package 生成前运行 Secret 扫描（与 `DOC-RELEASE-010` 同一扫描器）：manifest、数据库与文件名中出现 key 形态即中止导出。
- 导入解压前校验 zip 条目路径：拒绝绝对路径、`..`、盘符与保留设备名（zip-slip 防护）。
- 目标路径由玩家通过受控文件对话框选择；前端不能指定任意服务端路径（承接本地安全原则）。
- 导出/导入为流式处理，峰值内存 ≤ 256 MiB；进度按字节推送 UI。

## 10. 验收标准

- 创建 3 个世界后 registry、目录、Seed 一一对应；同时打开第二个世界的请求被明确拒绝。
- 删除→还原后世界可正常打开且状态哈希与删除前一致；删除→30 天模拟到期→启动清理后目录与 registry 行消失且有审计日志。
- 导出→异机导入→打开后，规范化状态哈希与导出前一致；`logs\`、`backups\`、Secret 均不在包内。
- 冲突 `world_id` 导入产生新 ID 且 `origin_world_id` 正确。
- 中文显示名 + 中文/空格导出路径全流程通过。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-017` | `RULE-RELEASE-032..033` 单开约束与原子创建 |
| `TEST-RELEASE-018` | `RULE-RELEASE-034`, `RULE-RELEASE-038` 可恢复删除、Purge 与一致性扫描 |
| `TEST-RELEASE-019` | `RULE-RELEASE-035..036` 导出内容边界、导入校验与冲突改 ID |
| `TEST-RELEASE-020` | `RULE-RELEASE-037`, `RULE-RELEASE-039` 显示名/路径分离、审计与二次确认 |

## 12. 关联文档

- `DOC-RELEASE-001`：目录布局与 `world_registry` Schema
- `DOC-RELEASE-002`：导入后按需迁移
- `DOC-RELEASE-004`：世界内存档（随导出包整体迁移）
- `DOC-RELEASE-006`：损坏世界的分诊与还原
- `DOC-RELEASE-010`：共享的 Secret 扫描器
- `DOC-BACKEND-004`：世界管理 REST 端点

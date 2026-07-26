---
doc_id: DOC-RELEASE-004
title: 自动恢复点与手动存档槽位
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - auto-recovery-points
  - manual-save-slots
  - branch-on-load-policy
depends_on:
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-RELEASE-001
  - DOC-RELEASE-003
  - DOC-TIME-009
requirements:
  - REQ-PRODUCT-008
  - REQ-PRODUCT-014
  - REQ-RELEASE-004
last_updated: 2026-07-26
---

# 自动恢复点与手动存档槽位

## 1. 目的

`REQ-RELEASE-004`：定义每世界恰好 5 个自动恢复点与恰好 3 个手动槽位的创建、覆盖与引用规则，以及读取旧存档时默认创建新 Timeline Branch 的 branch-on-load 流程，保证玩家回读历史不破坏既有时间线、Seed 与 Revision 语义。

## 2. 非目标

本文件不定义 Snapshot 物理格式与重放算法（`DOC-RELEASE-003`）；不定义世界级导出/导入与删除（`DOC-RELEASE-005`）；不定义关闭时刻的时间语义（`DOC-TIME-009`）；不定义存档 REST 端点形状（`DOC-BACKEND-004`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| SaveRecord | 一条存档记录：引用（timeline_id, anchor_revision, snapshot_id），不复制可变状态 |
| Auto Recovery Point | 系统自动创建的 SaveRecord，每世界 FIFO 保留恰好 5 个 |
| Manual Slot | 玩家显式占用的槽位 `slot_1`/`slot_2`/`slot_3`，每世界恰好 3 个 |
| branch-on-load | 读取非 tip 存档时创建新 Timeline 并归档原 Timeline 的流程 |
| Resume | 读取当前 Timeline tip 对应的最新自动恢复点，不创建分支 |
| Save Trash | 被覆盖 SaveRecord 的暂存区，保留 7 天可撤销 |

## 4. 规则与不变量

- `RULE-RELEASE-025`：每世界自动恢复点数量恰好为 5：第 6 个创建时按创建时间 FIFO 淘汰最旧；手动槽位数量恰好为 3；两个数量是产品常量，不提供配置项改变。
- `RULE-RELEASE-026`：自动恢复点创建触发固定为：干净关闭时必建；运行中每 10 game minutes 或每 500 个 Revision（先到者）建一次。创建复用 `DOC-RELEASE-003` 的 Snapshot 任务并在写队列内串行。
- `RULE-RELEASE-027`：SaveRecord 只引用哈希校验通过的 Snapshot 与该 Timeline 的连续事件前缀；被任何 SaveRecord（含 Save Trash 内）引用的 Snapshot 与事件不得被保留策略删除（配合 `RULE-RELEASE-022`）。
- `RULE-RELEASE-028`：读取 tip 存档为 Resume，不创建分支；读取任何 `anchor_revision < tip` 的存档默认 branch-on-load：生成新 `timeline_id`（ULID），在新 `world_meta` 记录 `parent_timeline_id` 与 `branch_source_revision`，原 Timeline 数据库整体移入 `timelines\` 只读归档。
- `RULE-RELEASE-029`：分支后新 Timeline 的 Revision 从 `branch_source_revision` 继续严格递增，不归零；世界 Seed 不变（`RULE-FOUNDATION-026`），随机流 sequence 从锚点时刻的持久值恢复，保证「存档重载不改变 Seed 序列」。
- `RULE-RELEASE-030`：覆盖非空手动槽位与读取会触发分支的存档，均需 UI 二次确认；被覆盖的 SaveRecord 移入 Save Trash 保留 7 天，期内可一键还原到原槽位。
- `RULE-RELEASE-031`：存档创建、读取、覆盖、还原都是携带 `command_id` 的审计化 Command（`RULE-FOUNDATION-022` 幂等）；读档失败时当前 Timeline 保持原状态并暂停，绝不半切换。

## 5. 数据与接口

### 5.1 SaveRecord 存储

`DES-RELEASE-008`：SaveRecord 存于 `world.sqlite3`（活动 Timeline 与归档 Timeline 各自持有自己创建的记录），文件副本目录为 `saves\`：

```sql
CREATE TABLE save_records (
  save_id         TEXT PRIMARY KEY,       -- ULID
  kind            TEXT NOT NULL CHECK (kind IN ('auto','manual')),
  slot            TEXT CHECK (slot IN ('slot_1','slot_2','slot_3')),  -- 仅 manual 非空
  timeline_id     TEXT NOT NULL,
  anchor_revision INTEGER NOT NULL,
  snapshot_id     TEXT NOT NULL REFERENCES snapshot_meta(snapshot_id),
  game_time       INTEGER NOT NULL,
  display_label   TEXT NOT NULL,          -- 玩家可见描述，如游戏日与地点摘要
  created_at      TEXT NOT NULL,
  trashed_at      TEXT                    -- 进入 Save Trash 的时间，NULL 表示在用
);
```

对玩家展示的存档摘要（REST 响应内容，形状归 `DOC-BACKEND-004`）示例：

```json
{
  "save_id": "01K1AB2CD3EF4GH5JK6MNP7QT2",
  "kind": "manual",
  "slot": "slot_2",
  "anchor_revision": 41230,
  "game_time": 11930,
  "display_label": "第 9 游戏日 清晨 · 王冠溪镇广场",
  "created_at": "2026-07-26T09:15:30.000Z",
  "will_branch_on_load": true
}
```

### 5.2 接口

`DES-RELEASE-009`：

```text
create_manual_save(command_id, slot, display_label) -> SaveRecord
create_auto_recovery_point(trigger) -> SaveRecord          # 系统内部
load_save(command_id, save_id, confirm_branch) -> LoadResult
restore_trashed_save(command_id, save_id) -> SaveRecord
list_saves(world_id) -> SaveRecord[]                       # 含归档 Timeline 的记录
```

branch-on-load 算法（原子步骤，任一步失败即整体回退且原 Timeline 不变）：

1. 暂停世界并完成写队列（`DOC-TIME-009` Quiescence）。
2. 将当前 `world.sqlite3`（含 `-wal` checkpoint 后）移动为 `timelines\<old_timeline_id>.sqlite3` 并置只读属性。
3. 以引用 Snapshot + 事件前缀（`revision <= anchor_revision`）构建新的 `world.sqlite3`：写入状态、复制事件前缀、写新 `world_meta`（新 `timeline_id`、`parent_timeline_id`、`branch_source_revision`）。
4. 运行 Recovery Audit（`DOC-RELEASE-003` 第 6 节流程）后进入 paused_ready。

## 6. 正常流程

1. 运行中按 `RULE-RELEASE-026` 周期创建自动恢复点，FIFO 维持 5 个。
2. 玩家在网页 UI 请求手动存档到 `slot_3`：写队列内建 Snapshot、写 SaveRecord、返回摘要。
3. 玩家选择读取 `slot_2`（历史锚点）：UI 明示「将创建新时间线分支」，玩家确认后执行 branch-on-load。
4. 新 Timeline 进入 paused_ready，玩家点击继续后世界运行；旧 Timeline 归档可再次被读取（再次分支）。
5. 玩家覆盖 `slot_2`：旧记录入 Save Trash，7 天后由启动清理任务物理释放其独占引用。

## 7. 边界情况

- 世界刚创建、Revision < 500 且未到 10 game minutes：允许自动恢复点少于 5 个；「恰好 5 个」指保留上限与稳态数量，不要求冷启动即刻凑满。
- branch-on-load 第 2/3 步之间崩溃：启动扫描发现 `world.sqlite3` 缺失但归档与 SaveRecord 存在，自动重试第 3 步（幂等，来源数据只读）；重试失败进入 `DOC-RELEASE-006` 分诊。
- 读取归档 Timeline 上的存档：来源为 `timelines\<id>.sqlite3`，流程相同；归档文件缺失则该 SaveRecord 标记 broken，不允许读取。
- 自动恢复点触发时磁盘空间预检失败（`RULE-RELEASE-042`）：跳过本次创建并计数告警，连续 3 次失败暂停世界提示清理磁盘，不静默丢失恢复能力。
- Save Trash 中记录引用的 Snapshot 同时被在用记录引用：7 天到期只删 SaveRecord 行，不删共享 Snapshot。

## 8. 错误与降级

存档创建失败（Snapshot 失败、磁盘满）不影响已提交世界状态，向 UI 报告并保留上一恢复点。读档/分支失败保持当前 Timeline 原状态暂停，给出失败原因码与分诊入口。不存在「部分读档」或「就地回滚当前 Timeline」的降级路径——历史回读只能以分支表达（保护 `RULE-FOUNDATION-027`）。

## 9. 安全与性能

- SaveRecord 与摘要不含 Secret 与居民私有记忆原文；`display_label` 由服务端生成，玩家自定义标签经长度与字符过滤。
- 自动恢复点创建在写队列内的单次占用目标 ≤ 2 s（首版规模），超时向 TIME backpressure 报告。
- branch-on-load 端到端目标 ≤ 15 s；进度状态推送 UI。
- 归档 Timeline 文件设只读属性并在打开时校验，防止外部程序误写。

## 10. 验收标准

- 连续运行 2 游戏小时后自动恢复点数量恰为 5 且锚点按 FIFO 更替；手动槽位始终恰为 3 个位置。
- 读取历史存档后：新 `timeline_id` 生成、`parent_timeline_id`/`branch_source_revision` 正确、原 Timeline 文件只读归档且字节不变。
- 分支后 Seed 与随机流序列与锚点时刻一致（配合 `TEST-TIME-028..030`）；Revision 从锚点继续且不回退。
- 覆盖槽位后 7 天内可还原；还原后内容与被覆盖前逐字段一致。
- 全部存档操作重复提交同一 `command_id` 只生效一次。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-013` | `RULE-RELEASE-025..026` 数量恒定、FIFO 与触发点 |
| `TEST-RELEASE-014` | `RULE-RELEASE-027` 引用保护与保留策略交互 |
| `TEST-RELEASE-015` | `RULE-RELEASE-028..029` branch-on-load、Revision 延续与 Seed 不变 |
| `TEST-RELEASE-016` | `RULE-RELEASE-030..031` 二次确认、Save Trash、幂等与失败原状保持 |

## 12. 关联文档

- `DOC-RELEASE-003`：Snapshot 生成与重放
- `DOC-RELEASE-005`：世界级导出（含全部存档）与删除
- `DOC-RELEASE-006`：读档失败分诊
- `DOC-TIME-009`：Quiescence 与恢复屏障
- `DOC-FOUNDATION-004`：Timeline Branch 术语定义
- `DOC-BACKEND-004`：存档 REST 端点

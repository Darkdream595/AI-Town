---
doc_id: DOC-RELEASE-003
title: Snapshot 与 Event Log 持久化
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - domain-event-log-persistence
  - snapshot-format-policy
  - replay-recovery-contract
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-RELEASE-001
  - DOC-TIME-009
  - DOC-TIME-010
requirements:
  - REQ-PRODUCT-008
  - REQ-PRODUCT-018
  - REQ-RELEASE-003
last_updated: 2026-07-26
---

# Snapshot 与 Event Log 持久化

## 1. 目的

`REQ-RELEASE-003`：定义追加式 `event_log` 的物理 Schema 与不可变约束、Snapshot 的生成触发、文件格式、原子写入与保留策略，以及「最新有效 Snapshot + Event tail 确定性重放」的恢复契约，使每个已提交 Revision 在任意崩溃点后都可精确重建。

## 2. 非目标

本文件不定义 DomainEvent 的业务类型目录与 payload 语义（各 domain owner 与 `DOC-BACKEND-006`）；不定义关闭/恢复的时间语义（`DOC-TIME-009`）；不定义存档槽位对 Snapshot 的引用（`DOC-RELEASE-004`）；不定义损坏时的分诊顺序（`DOC-RELEASE-006`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Event tail | 某 Snapshot 锚点 Revision 之后、直到 tip 的连续事件序列 |
| Snapshot Anchor | Snapshot 锚定的完整 Revision（`RULE-FOUNDATION-029`） |
| Canonical JSON | 键排序、UTF-8、无多余空白的确定性序列化，用于哈希 |
| Replay | 从 Snapshot 状态起按 Revision 升序重新应用 Event tail 的纯函数过程 |
| AI Replay Record | 已验证模型输出的持久记录，重放时替代重新请求（`RULE-TIME-060`） |
| Tip | 该 Timeline 当前最大已提交 Revision |

## 4. 规则与不变量

- `RULE-RELEASE-017`：`event_log` 只允许 `INSERT`；数据库内建 trigger 拒绝 `UPDATE` 与 `DELETE`，撤销与修复一律以新事件表达（本规则是 `RULE-FOUNDATION-027` 的存储层落实）。
- `RULE-RELEASE-018`：`event_log.revision` 在同一 Timeline 内从 1 开始严格连续无空洞；事件行与对应状态写入同一事务提交（承接 `RULE-RELEASE-005`），恢复时发现空洞即判定损坏。
- `RULE-RELEASE-019`：每行必须携带 `RULE-FOUNDATION-021` 规定的完整 Envelope 字段；`payload_json` 与 `render_json` 为可解析 JSON 文本，禁止私有二进制格式，禁止包含 Secret、API Key 与 `reasoning_content`。
- `RULE-RELEASE-020`：Snapshot 只能锚定完整已提交 Revision；生成期间的新事务照常提交进 `event_log`，不阻塞也不混入本次 Snapshot（`DOC-FOUNDATION-005` 第 7 节语义）。
- `RULE-RELEASE-021`：Snapshot 文件写入必须 write-temp → fsync → 原子 rename；`snapshot_meta` 在文件落盘后同事务记录其 SHA-256；哈希校验失败的 Snapshot 视为不存在。
- `RULE-RELEASE-022`：Snapshot 触发点固定为：干净关闭时必建（`DOC-TIME-009` 序列内）、运行中每累计 2000 个 Revision 建一次；每 Timeline 至少保留最近 2 个校验通过的 Snapshot，删除旧 Snapshot 前必须确认存在更新的有效 Snapshot 且无任何 SaveRecord 引用（`DOC-RELEASE-004`）。
- `RULE-RELEASE-023`：Replay 是确定性纯函数：只消费 Snapshot 状态与 Event tail，不调用模型、不联网、不取系统时间与进程随机数；历史 AI 结果使用 AI Replay Record；两次 Replay 相同输入必须产生逐字节相同的规范化状态哈希。
- `RULE-RELEASE-024`：旧版本事件在读取时经注册 upcaster 转换为当前形状，原始行字节不变；upcaster 必须对输入输出执行 strict validation（与 `DOC-TIME-009` 的 upcast 纪律一致）。

## 5. 数据与接口

### 5.1 `event_log` 物理 Schema

`DES-RELEASE-005`：

```sql
CREATE TABLE event_log (
  revision       INTEGER PRIMARY KEY,     -- 严格连续，从 1 开始
  event_id       TEXT NOT NULL UNIQUE,    -- ULID
  world_id       TEXT NOT NULL,
  event_type     TEXT NOT NULL,           -- 注册的稳定事件类型 ID
  event_schema_version INTEGER NOT NULL,
  game_time      INTEGER NOT NULL,        -- 自世界纪元的游戏分钟
  causation_id   TEXT,
  correlation_id TEXT,
  payload_json   TEXT NOT NULL,
  render_json    TEXT,
  created_at     TEXT NOT NULL            -- UTC RFC 3339
);
CREATE TRIGGER event_log_no_update BEFORE UPDATE ON event_log
BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END;
CREATE TRIGGER event_log_no_delete BEFORE DELETE ON event_log
BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END;
```

### 5.2 Snapshot 文件与元数据

`DES-RELEASE-006`：Snapshot 文件为 zstd 压缩的 Canonical JSON，存于 `snapshots\<anchor_revision>-<snapshot_id>.snap.zst`。逻辑内容：

```json
{
  "snapshot_format_version": 1,
  "snapshot_id": "01K1AB2CD3EF4GH5JK6MNP7QT0",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "timeline_id": "01K1AB2CD3EF4GH5JK6MNP7QT1",
  "anchor_revision": 46000,
  "game_time": 12480,
  "schema_version": 3,
  "state_tables": {
    "world_meta": [],
    "resident_state": [],
    "inventory_state": [],
    "building_state": []
  },
  "domain_projections": {
    "time_checkpoint": {},
    "seed_stream_sequences": []
  },
  "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

`state_tables` 覆盖全部规范化状态表的完整行集（表清单由构建期从各 owner Schema 注册表生成，缺表即校验失败）；`domain_projections` 包含 TIME 的 Shutdown Checkpoint 投影与 Seed stream sequence 持久值（`DOC-TIME-009`、`DOC-TIME-010`）。`content_sha256` 是除该字段本身外全文 Canonical JSON 的 SHA-256。

```sql
CREATE TABLE snapshot_meta (
  snapshot_id     TEXT PRIMARY KEY,       -- ULID
  anchor_revision INTEGER NOT NULL UNIQUE,
  file_name       TEXT NOT NULL,
  file_sha256     TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  trigger         TEXT NOT NULL CHECK (trigger IN ('clean_shutdown','revision_interval','manual_save','auto_save'))
);
```

### 5.3 接口

`DES-RELEASE-007`：

```text
append_events(transaction, events) -> void            # 仅供 Repository commit 内部调用
build_snapshot(trigger) -> SnapshotMeta               # 在写队列内取一致读视图
load_latest_valid_snapshot(max_revision) -> Snapshot | None
replay(snapshot, event_tail) -> WorldState            # 确定性纯函数
verify_event_continuity(from_revision, to_revision) -> ContinuityReport
```

## 6. 正常流程

1. 运行期每次写事务由 Repository 同事务写状态、`event_log` 行与幂等结果（`DOC-RELEASE-001` 流程）。
2. Revision 计数到达触发阈值时，写队列插入 Snapshot 任务：取一致读视图、导出状态表、写临时文件、fsync、rename、记录 `snapshot_meta`。
3. 打开世界时选取 `anchor_revision` 最大且哈希校验通过的 Snapshot，加载状态。
4. 按 Revision 升序重放 Event tail 到 tip；AI 相关事件用 Replay Record 还原，不重新请求模型。
5. 重放完成后运行 Recovery Audit（`RULE-TIME-051`、`DOC-FOUNDATION-005`），通过后解除 Recovery Barrier。

## 7. 边界情况

- Snapshot 写入中途崩溃：只留下临时文件，无 `snapshot_meta` 行；启动时清理孤立临时文件，恢复使用上一个有效 Snapshot。
- `snapshot_meta` 有行但文件缺失或哈希不符：该 Snapshot 视为不存在，回退更早 Snapshot；若全部无效则从 Revision 1 全量重放（首版数据规模可接受，超时进入 `DOC-RELEASE-006` 分诊）。
- Event tail 中出现未注册 `event_type` 或 upcaster 校验失败：停止重放，保持 Recovery Barrier，转入 `DOC-RELEASE-006`，不跳过该事件。
- 高倍速运行下 2000 Revision 间隔触发频繁：Snapshot 任务在写队列中与普通事务串行，单次超过 5 s 时向 TIME 报告 backpressure，由 `DOC-TIME-011` 的倍率回落机制处理，不丢弃 Snapshot。
- branch-on-load 后的新 Timeline：Event tail 前缀从来源 Timeline 复制（`DOC-RELEASE-004`），连续性校验以复制后的本库为准。

## 8. 错误与降级

事件追加失败即整个写事务失败（回滚、Revision 不增长）。Snapshot 生成失败不影响世界继续运行，但连续 3 次失败后强制暂停世界并提示（防止 tail 无限增长且无新恢复点）。重放或连续性校验失败一律保持暂停并进入分诊；禁止「跳过坏事件继续」的降级。

## 9. 安全与性能

- Snapshot 与 `event_log` 内容禁止 Secret、`reasoning_content`、未过滤 Prompt 原文（`RULE-FOUNDATION-024`）；诊断导出前再次扫描（`DOC-RELEASE-010`）。
- 30 游戏日模拟下 `world.sqlite3` + `snapshots\` 总增长必须 ≤ 512 MiB（`DOC-RELEASE-011` 门槛）。
- Snapshot 导出使用分表流式读取，峰值内存 ≤ 256 MiB。
- 重放吞吐目标 ≥ 5000 events/s（FakeModelProvider 环境），保证 2000 Revision 的 tail 重放 ≤ 1 s。

## 10. 验收标准

- 对 `event_log` 执行 `UPDATE`/`DELETE` 被 trigger 拒绝。
- 任意崩溃注入点恢复后，重放态哈希与崩溃前 tip 的规范化状态哈希一致。
- 同一 Snapshot + tail 重放两次产生逐字节相同状态哈希；重放全程零模型调用、零网络调用。
- 干净关闭必产生新 Snapshot；每 Timeline 有效 Snapshot 数 ≥ 2（Revision 足够时）。
- 删除保留策略绝不删除被 SaveRecord 引用的 Snapshot。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-009` | `RULE-RELEASE-017..019` append-only、连续性与 Envelope 完备 |
| `TEST-RELEASE-010` | `RULE-RELEASE-020..021` 锚点语义与原子写入 |
| `TEST-RELEASE-011` | `RULE-RELEASE-022` 触发、保留与引用保护 |
| `TEST-RELEASE-012` | `RULE-RELEASE-023..024` 确定性重放、AI Replay Record 与 upcaster |

## 12. 关联文档

- `DOC-RELEASE-001`：单写入队列与原子事务
- `DOC-RELEASE-004`：SaveRecord 对 Snapshot/事件前缀的引用
- `DOC-RELEASE-006`：重放失败后的分诊
- `DOC-TIME-009`：Shutdown Checkpoint 投影与恢复屏障
- `DOC-TIME-010`：Seed stream sequence 与 AI replay 契约
- `DOC-BACKEND-006`：DomainEvent 协议字段定义

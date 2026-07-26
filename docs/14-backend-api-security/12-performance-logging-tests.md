---
doc_id: DOC-BACKEND-012
title: 性能预算、结构化日志与安全测试
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - backend-performance-budget
  - structured-logging-and-redaction-table
  - security-fixtures-and-load-tests
depends_on:
  - DOC-BACKEND-001
  - DOC-BACKEND-008
  - DOC-BACKEND-009
  - DOC-BACKEND-011
  - DOC-TIME-011
requirements:
  - REQ-BACKEND-012
last_updated: 2026-07-26
---

# 性能预算、结构化日志与安全测试

## 1. 目的

`REQ-BACKEND-012`：定义后端本地指标体系、结构化日志格式与轮转、敏感字段日志策略主表、REST/WS 性能预算、安全 fixture 清单与负载测试矩阵，为 `DOC-BACKEND-001..011` 的规则提供统一可观测性与验证基础设施。

## 2. 非目标

本文不定义 Tick 内部预算（`DOC-TIME-011`）、AI 行为评估（`DOC-AI-012`）、全项目测试分层与发布 Gate（`DOC-RELEASE-011..012`）、诊断包的打包与导出流程（`DOC-RELEASE-010`）。本文的脱敏主表是日志与指标的判定来源，诊断包复用该表。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Structured Log Line | 单行 JSON 的日志记录，字段固定、无自由插值 |
| Log Policy | 字段级记录策略：`allowed/id-only/masked/never` |
| Metrics Snapshot | `GET /api/v1/diagnostics/metrics` 返回的版本化指标快照 |
| Security Fixture | 可重复执行的攻击面回归用例集 |
| Load Profile | 负载测试的世界规模、速度与时长组合 |
| Budget Breach | 指标超出预算并触发 overload 上报的事件 |

## 4. 规则与不变量

- `RULE-BACKEND-066`：日志为 JSON lines：固定字段 `timestamp`（UTC RFC 3339）、`level`（`debug/info/warning/error`）、`logger`、`event_code`、`world_id`（可空）、`ids`（ULID 映射）、`reason_code`（可空）、`duration_ms`（可空）；正文性内容禁止插值进 message 字段——只允许注册过 Log Policy 的字段。轮转：单文件 10 MiB、保留 5 个，全部位于用户数据目录 `logs/`。
- `RULE-BACKEND-067`：§5 敏感字段主表是全部日志、指标、错误 details、审计输出的统一 Log Policy 来源；任何新增字段必须先在主表归类才可记录，未归类字段默认 `never`。`never` 类字段由 `DOC-BACKEND-009` 的 Redaction Filter 兜底擦除。
- `RULE-BACKEND-068`：指标为进程内 registry，经 `MetricsSnapshotV1`（含 `schema_version`）暴露；指标只含数值与低基数标签（`world_id`、queue 名、error code、route class），禁止内容型标签（文本、prompt、路径）。核心指标清单见 §5，缺一即验收失败。
- `RULE-BACKEND-069`：性能预算（本机基准环境，25 居民世界）：REST 管理端点 p95 < 50 ms；`command` 帧从接收到 `command_receipt` p95 < 150 ms（不含模型等待）；事件从 COMMIT 到帧写出 p95 < 50 ms；WS 心跳往返 p95 < 20 ms；进程稳态内存 < 1.5 GiB。连续 3 个采样窗口超预算即 Budget Breach，上报 `DOC-TIME-011` 降档链路。
- `RULE-BACKEND-070`：安全 fixture 与负载测试进 CI/发布 Gate：§5 fixture 清单全绿才可发布；负载 Load Profile 至少覆盖 `25 居民 × 4× 速 × 30 game days`，结束时断言零 DomainEvent 丢失、零幂等违规、零 invariant violation、零 `never` 字段泄漏。

## 5. 数据与接口

`DES-BACKEND-012`：日志行示例：

```json
{
  "timestamp": "2026-07-26T08:30:15.250Z",
  "level": "info",
  "logger": "backend.command",
  "event_code": "command_committed",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "ids": {
    "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
    "session_id": "01K1AB2CD3EF4GH5JK6MNP7QS2"
  },
  "reason_code": null,
  "duration_ms": 12
}
```

敏感字段日志策略主表（master；`DOC-BACKEND-009` §5 为 Secret 子集的细化）：

| 字段/内容 | Log Policy | 说明 |
|---|---|---|
| DeepSeek API Key 明文、`Authorization` 头 | never | Redaction 兜底 |
| Session Cookie 值、Session Secret | never | 记 `session_id` 代替 |
| CSRF Token 值 | never | 拒绝事件记位点即可 |
| WS Ticket 值 | never | 记 SHA-256 前 12 hex 指纹 |
| Confirmation Token 值 | never | 记 `challenge_id` |
| 玩家/居民对话正文、公告正文 | never | 记 `event_id` 与长度 |
| 模型 prompt/completion 正文 | never | AI 域缓存键策略见 `DOC-AI-008` |
| `reasoning_content` | never | 任何输出目标均禁止（`DOC-AI-007`） |
| 居民 Secret/私有 Belief 内容 | never | 记所属 aggregate ID |
| 文件系统绝对路径（用户目录） | masked | 记录相对用户数据根的相对路径 |
| Origin/Host 值 | masked | 只记 allowlist 命中与否及端口 |
| ULID（world/command/event/session 等） | id-only | 允许 |
| Masked Suffix、Key Fingerprint | allowed | `DOC-BACKEND-009` |
| 金额汇总、数量、Revision、GameTime | allowed | 数值型 |
| error code、reason_code、duration | allowed | 低基数 |

核心指标清单（`MetricsSnapshotV1` 必含）：

| 指标 | 类型 | 标签 |
|---|---|---|
| `tick_critical_section_ms` p50/p95/p99 | summary | world_id |
| `queue_depth` / `queue_oldest_wait_ms` | gauge | queue |
| `command_latency_ms` p95 | summary | — |
| `event_fanout_latency_ms` p95 | summary | — |
| `ws_sessions` / `ws_state` | gauge | state |
| `error_count` | counter | code |
| `model_request_latency_ms` p95 / `model_request_count` | summary/counter | result |
| `idempotency_hit_count` | counter | — |
| `budget_breach_count` | counter | budget |
| `process_memory_bytes` / `db_size_bytes` | gauge | — |

Security Fixture 清单（全部可重复、离线执行）：

| fixture | 覆盖 |
|---|---|
| 伪造/缺失 Origin、跨源 preflight | `RULE-BACKEND-043..044` |
| 缺失/错误 CSRF 头 | `RULE-BACKEND-045` |
| Ticket 重放、过期、跨 Session | `RULE-BACKEND-012` |
| 静态路径穿越与符号链接 | `DOC-BACKEND-001` §9 |
| 超大 body/帧、深嵌套 JSON | `RULE-BACKEND-048` |
| 各 Route Class 限速触顶 | `RULE-BACKEND-047` |
| 越权命令（observer 发 mayor/admin） | `RULE-BACKEND-046` |
| 权威字段伪造 payload | `RULE-BACKEND-028` |
| 注入测试 Key 后全目标泄漏扫描 | `RULE-BACKEND-051/053` |
| 未注册错误码/未归类日志字段扫描 | `RULE-BACKEND-060/067` |

## 6. 正常流程

1. 进程启动装配 logger、指标 registry 与 Redaction Filter（顺序在 Secret Provider 之后，保证指纹已注册）。
2. 运行期各模块以 `event_code` 结构化打点；指标由中间件与队列消费者自动采集。
3. 采样窗口（10 s）计算分位数并评估预算；Budget Breach 记事件并上报降档。
4. CI 每次构建运行 Security Fixture 与短负载（1 game day）；发布 Gate 运行完整 Load Profile。
5. 诊断包（`DOC-RELEASE-010`）从日志与 Metrics Snapshot 组装，按主表二次过滤。

## 7. 边界情况

- 日志目录不可写：进程可继续运行（日志降级为内存环形缓冲 1000 条），health 标注 `logging_degraded`；指标不受影响。
- 高倍速下打点洪峰：debug 级别在 4× 速自动抑制，info 以上不抑制；指标聚合不丢样本。
- 指标端点在 Recovery Barrier 期间：可用，仅含进程级指标，世界级指标标记 unavailable。
- 负载测试中的模型调用：一律使用 FakeModelProvider（`DOC-RELEASE-011`），真实 DeepSeek 不进入 CI 与负载路径。
- 时钟回拨：`timestamp` 可能回退但 `duration_ms` 基于 monotonic（`RULE-FOUNDATION-035`），分位数计算不受墙钟影响。

## 8. 错误与降级

日志写失败静默丢弃该条并递增 `log_write_failure` 计数（不得回抛请求路径，呼应 `DOC-BACKEND-011` §8）；指标采集异常隔离到单指标，不影响请求处理。Fixture 失败即构建/发布失败，无手工豁免通道；预算回归允许在 Gate 报告中标注环境噪声后复测一次，两次均超即失败。

## 9. 安全与性能

日志与指标自身开销纳入预算：结构化打点单次 < 50 µs，采集中间件对 REST p95 影响 < 2 ms。日志文件权限仅限当前用户；日志不进入世界存档与导出。主表变更属于安全评审事项，需要 owner_domain backend 的文档更新（本文件版本递增）。

## 10. 验收标准

- 随机抽样 1000 条生产日志：全部字段可对应主表策略，零 `never` 命中。
- Metrics Snapshot 含核心清单全部指标且 `schema_version` 有效。
- 基准环境下四项延迟预算与内存预算全部满足；超预算路径正确触发 Budget Breach。
- Security Fixture 清单十项全绿且每项失败注入版本能被检出（fixture 自验证）。
- 完整 Load Profile 结束断言四个「零」全部成立。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-043` | `RULE-BACKEND-066..067` 日志结构、轮转与主表零泄漏 |
| `TEST-BACKEND-044` | `RULE-BACKEND-068..069` 指标完备性与预算/Breach 行为 |
| `TEST-BACKEND-045` | `RULE-BACKEND-070` Security Fixture 全集与自验证 |
| `TEST-BACKEND-046` | `RULE-BACKEND-070` Load Profile 四零断言 |

## 12. 关联文档

- `DOC-BACKEND-001`：队列与进程指标来源
- `DOC-BACKEND-009`：Redaction Filter 与 Secret 子表
- `DOC-BACKEND-011`：错误码维度与失败恢复
- `DOC-TIME-011`：Tick 预算与降档链路
- `DOC-RELEASE-010..012`：诊断包、测试分层与发布 Gate

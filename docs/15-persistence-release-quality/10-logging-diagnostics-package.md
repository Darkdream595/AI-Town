---
doc_id: DOC-RELEASE-010
title: 日志与脱敏诊断包
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - local-logging-policy
  - log-redaction-scanner
  - diagnostics-package
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RELEASE-001
  - DOC-RELEASE-006
  - DOC-RELEASE-007
requirements:
  - REQ-PRODUCT-016
  - REQ-PRODUCT-019
  - REQ-RELEASE-010
last_updated: 2026-07-26
---

# 日志与脱敏诊断包

## 1. 目的

`REQ-RELEASE-010`：定义本地结构化日志的格式、轮转与内容禁区，共享脱敏扫描器（Secret Scanner）的判定规则，以及玩家显式触发的诊断包内容白名单与打包前扫描流程，保证默认零遥测上传、任何出口介质不含 API Key、Credential、原始 Chain of Thought、未脱敏 Prompt 或无关用户文件。

## 2. 非目标

本文件不定义模型请求的业务日志字段语义（`DOC-AI-008` 的 usage 记录）、后端性能指标（`DOC-BACKEND-012`）、RecoveryReport 内容（`DOC-RELEASE-006`）；不设计任何远程遥测协议——首版不存在该功能，故「上传通道设计」整体不适用。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Log Line | 一行 JSON（JSON Lines 格式）的结构化日志记录 |
| Emission-time Redaction | 在写日志的调用点按注册字段 Schema 过滤，而非事后清洗 |
| Secret Scanner | 对出口介质（诊断包、导出包）统一执行的敏感内容扫描器 |
| Secret Canary | 测试环境注入的已知假凭据，用于验证扫描器有效性 |
| Diagnostics Package | 玩家显式触发生成的 `diagnostics\aitown-diag-<utc>.zip` |
| Content Hashing | 用 `sha256:<hex>+len` 替代自由文本原文的脱敏手段 |

## 4. 规则与不变量

- `RULE-RELEASE-071`：日志仅写入本地 `logs\`；首版不存在任何自动网络上传、崩溃自动上报或统计遥测通道；诊断包只能由玩家显式生成并自行决定是否外传。
- `RULE-RELEASE-072`：Log Line 为注册 Schema 的结构化 JSON；`message` 字段是注册消息模板 ID + 参数，禁止把 Prompt 原文、模型输出原文、居民对话原文、玩家自由输入、`reasoning_content`、Secret 写入任何日志字段（`REQ-PRODUCT-016`、`RULE-FOUNDATION-024` 的日志侧落实）；需要留痕的文本内容使用 Content Hashing。
- `RULE-RELEASE-073`：模型请求日志只记录：request_id、prompt 模板 ID 与版本、input hash、token 计数、latency、结局码、重试次数；请求/响应原文只进入受控 AI Replay Record（`DOC-RELEASE-003`），不进普通日志。
- `RULE-RELEASE-074`：轮转策略固定：按日分文件 `app-YYYYMMDD.log`，单文件到 10 MiB 滚动 `.1..n` 后缀；保留 14 天且 `logs\` 总量 ≤ 200 MiB，超限先删最旧；磁盘满时停写日志（丢日志可接受），世界数据写入优先（配合 `RULE-RELEASE-043`）。
- `RULE-RELEASE-075`：Secret Scanner 判定规则集固定并版本化：(a) key 形态正则（`sk-` 前缀、32+ 位十六进制/Base64 连续串）；(b) 凭据关键词邻接值（`api_key`、`authorization`、`token`、`password` 等后随非掩码值）；(c) Secret Canary 精确匹配；(d) 用户目录越界路径（`%LOCALAPPDATA%\AI-Town` 与包目录之外的绝对路径）。扫描器由诊断包、世界导出（`RULE-RELEASE-035`）、打包流水线（`RULE-RELEASE-068`）共用。
- `RULE-RELEASE-076`：Diagnostics Package 内容白名单固定为第 5.2 节清单；白名单外文件一律不进包；打包前对全部候选内容执行 Secret Scanner，任一命中即中止打包并报告命中类别与位置，绝不产出「部分脱敏」的包。
- `RULE-RELEASE-077`：诊断包不含任何 `world.sqlite3`、Timeline 归档、Snapshot、存档与导出包；数据库信息仅以摘要出现（schema_version、integrity 结果、表行数、文件大小）；需要世界数据协查时引导玩家单独使用世界导出（其自身也过扫描）。
- `RULE-RELEASE-078`：日志与诊断中 ULID 与注册稳定 ID 可保留明文；游戏内自由文本（对话、标签、显示名）默认 Content Hashing；`display_name` 例外允许明文（玩家自己命名的世界名，属可见元数据）。

## 5. 数据与接口

### 5.1 Log Line Schema

`DES-RELEASE-020`：

```json
{
  "ts": "2026-07-26T14:00:00.123Z",
  "level": "INFO",
  "logger": "release.recovery",
  "template_id": "release.recovery.triage_level_passed",
  "params": {"world_id": "01K1AB2CD3EF4GH5JK6MNP7QRS", "level": "L2", "anchor_revision": 44000},
  "request_id": null,
  "revision": 44000
}
```

`level` 枚举 `DEBUG/INFO/WARNING/ERROR`；`params` 值只允许：注册 ID、数字、布尔、UTC 时间戳、reason_code 枚举、Content Hashing 结果。发布包默认级别 `INFO`，`DEBUG` 仅开发构建。

### 5.2 Diagnostics Package 白名单

`DES-RELEASE-021`：

```text
aitown-diag-<utc>.zip
├─ manifest.json                 # 生成时间、package_version、build_id、扫描器版本与结果
├─ system.json                   # OS 版本、locale、CPU/内存概况、磁盘剩余、显卡型号
├─ package.json                  # release-manifest 摘要与完整性复算结果
├─ settings.json                 # app_settings 全量（白名单键天然非敏感）+ Key Masked Status
├─ worlds-summary.json           # 每世界：schema_version、大小、revision、存档数、integrity 摘要
├─ recovery\*.json               # RecoveryReport（DOC-RELEASE-006，本身已脱敏）
└─ logs\                         # 最近 7 天、经 Emission-time Redaction 的日志文件
```

manifest 示例：

```json
{
  "diag_format_version": 1,
  "generated_at": "2026-07-26T14:05:00.000Z",
  "package_version": "1.0.0",
  "build_id": "43d1e4a",
  "scanner_ruleset_version": 1,
  "scan_result": "clean",
  "included": ["system.json", "package.json", "settings.json", "worlds-summary.json", "recovery/", "logs/"]
}
```

### 5.3 接口

```text
log(template_id, params) -> void                      # Schema 校验失败即开发期报错
build_diagnostics_package(command_id) -> DiagResult   # 托盘/网页触发
scan_for_secrets(paths | bytes) -> ScanReport         # 共享扫描器
```

## 6. 正常流程

1. 运行期各模块经注册模板写结构化日志，轮转任务每日与超限时执行。
2. 玩家遇到问题，从托盘「打开诊断文件夹」或网页设置页点「生成诊断包」。
3. 后端收集白名单内容 → 运行 Secret Scanner → 全净则打 zip 到 `diagnostics\` 并打开文件夹。
4. 玩家自行把 zip 提供给协助者；系统不上传。

## 7. 边界情况

- 玩家把 Key 误粘贴到世界名或对话框：`display_name` 入包前同样过扫描器（规则 a/b 命中即中止并提示改名）；对话文本本身已 Content Hashing，不外泄。
- 日志目录被玩家删除：下次写入自动重建；诊断包生成时日志缺失记为 `logs: absent`，不失败。
- 扫描器命中但玩家坚持要包：不提供强制通道；提示具体命中位置由玩家清理后重试（例如清除含 Key 的世界名）。
- 时钟回拨导致日志文件名日期重复：追加写入同名文件，轮转按大小兜底；Log Line 内 `ts` 单调性不作保证（诊断按 `revision` 与 request_id 关联）。
- 超大 RecoveryReport（反复恢复尝试）：单文件 ≤ 5 MiB，超限截断 `chain_results` 中间条目并标记 `truncated: true`。
- 生成诊断包时磁盘不足：空间预检（`RULE-RELEASE-042`）拒绝并提示。

## 8. 错误与降级

日志写入失败绝不反向影响游戏事务（fire-and-forget + 有界缓冲，溢出丢弃并计数）。诊断包生成失败给出原因码；扫描器自身异常视为「不干净」，宁可不出包。不存在绕过扫描器的诊断出口。

## 9. 安全与性能

- Emission-time Redaction 是第一道防线，Secret Scanner 是出口防线；两道独立实现，测试分别注入 Canary 验证（`RULE-AI-069` 的评估套件同样消费 Canary）。
- 日志写入异步批量刷盘，单条开销目标 ≤ 50 µs；轮转在后台线程执行。
- 诊断包生成端到端目标 ≤ 30 s；zip 体积目标 ≤ 50 MiB。
- 扫描器对 200 MiB 语料的扫描目标 ≤ 20 s；规则集更新必须同步更新 `scanner_ruleset_version`。

## 10. 验收标准

- 在日志、诊断包、世界导出、发布包四类出口注入 Secret Canary，扫描器全部拦截。
- 正常游玩 1 游戏日后的全部日志：无 Prompt/对话/输入原文，无 Key 形态串，`reasoning_content` 零出现。
- 诊断包内容与白名单逐项一致，无数据库文件；manifest 的 `scan_result` 为 `clean`。
- 轮转边界：写满 10 MiB 滚动、14 天/200 MiB 保留生效；磁盘满时世界写入不受日志影响。
- 首版代码库内不存在任何遥测上传调用点（静态断言：无出站非 DeepSeek 域名的 HTTP 客户端调用）。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-037` | `RULE-RELEASE-071..073` 零遥测、结构化禁区与模型日志边界 |
| `TEST-RELEASE-038` | `RULE-RELEASE-074` 轮转、保留与磁盘满行为 |
| `TEST-RELEASE-039` | `RULE-RELEASE-075..076` 扫描器规则集与打包中止 |
| `TEST-RELEASE-040` | `RULE-RELEASE-077..078` 内容白名单、数据库排除与 Hashing 例外 |

## 12. 关联文档

- `DOC-RELEASE-006`：RecoveryReport 的生成与内容
- `DOC-RELEASE-007`：Masked Status 与 Secret 存储
- `DOC-RELEASE-005`：世界导出共用扫描器
- `DOC-RELEASE-009`：打包流水线共用扫描器
- `DOC-AI-008`：token/usage 记录的业务语义
- `DOC-FOUNDATION-005`：`RULE-FOUNDATION-024` Secret 边界

---
doc_id: DOC-RELEASE-007
title: 配置与 Secret 管理
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - non-sensitive-configuration
  - windows-secret-storage
  - user-data-path-policy
depends_on:
  - DOC-FOUNDATION-005
  - DOC-RELEASE-001
  - DOC-BACKEND-008
  - DOC-BACKEND-009
requirements:
  - REQ-PRODUCT-015
  - REQ-PRODUCT-019
  - REQ-RELEASE-007
last_updated: 2026-07-26
---

# 配置与 Secret 管理

## 1. 目的

`REQ-RELEASE-007`：定义非敏感配置的唯一存放位置（`app_settings` 键白名单）、DeepSeek API Key 等 Secret 在 Windows 上的唯一持久化位置（Credential Manager 主、按用户 DPAPI 备）、SecretProvider Port 的内存生命周期，以及用户数据路径不可被改写的约束，确保 Key 绝不进入 SQLite、文件配置、日志、浏览器存储或诊断包。

## 2. 非目标

本文件不定义 Key 的提交/校验 REST 端点与传输安全（`DOC-BACKEND-009` canonical）；不定义 Session/权限模型（`DOC-BACKEND-008`）；不定义模型请求如何使用 Key（`DOC-AI-007`）；不定义日志脱敏扫描实现（`DOC-RELEASE-010`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Non-sensitive Setting | 泄露不造成安全损失的配置项，存 `app_settings` |
| Secret | API Key、Session Secret、WebSocket Ticket、shutdown_token 等凭据类值 |
| Credential Store | Windows Credential Manager 的 Generic Credential（用户级） |
| DPAPI Fallback | `CryptProtectData`（user scope）密文文件，仅当 Credential Store 不可用 |
| SecretProvider | 后端唯一读取 Secret 的 Port，向调用方提供内存句柄 |
| Masked Status | 只含是否已配置与末 4 位的展示形态，如 `sk-****abcd` |

## 4. 规则与不变量

- `RULE-RELEASE-048`：`app_settings` 只接受注册白名单键；写入未知键、值 JSON 不可解析或不满足该键 Schema 的请求一律拒绝；白名单变更是文档变更（修订本文件），不是运行期配置。
- `RULE-RELEASE-049`：任何 Secret 不得写入 SQLite（含 WAL/备份/导出包）、json/ini/bat/txt 文件、日志、浏览器 localStorage/sessionStorage/IndexedDB/Cookie 持久层、诊断包（本规则汇聚 `RULE-RELEASE-006`、`RULE-FOUNDATION-024`、`REQ-PRODUCT-019` 在存储侧的落实；协议侧由 `DOC-BACKEND-009` 拥有）。
- `RULE-RELEASE-050`：DeepSeek API Key 的唯一持久位置：Credential Store 条目 `AI-Town/deepseek-api-key`；Credential Store API 不可用时使用 DPAPI Fallback 文件 `secrets\deepseek.dpapi`。两者互斥主备：写入成功一处后必须删除另一处旧值；读取顺序固定为先 Credential Store 后 Fallback。
- `RULE-RELEASE-051`：Key 明文只存在于后端进程内存，经 SecretProvider 提供；REST 永不回传明文，只回 Masked Status；前端输入框提交后立即清空，不做本地暂存。
- `RULE-RELEASE-052`：Session Secret 与 WebSocket Ticket 每次进程启动由 CSPRNG 生成，只驻留内存，不持久化；`runtime\instance.json` 中的 shutdown_token 是唯一允许落盘的进程级凭据，随进程退出删除（`DOC-RELEASE-008`）。
- `RULE-RELEASE-053`：配置解析优先级固定且封闭：内置默认值 < `app_settings`。发布包安装目录内不存在配置来源（目录只读，`RULE-RELEASE-001`）；不提供环境变量与命令行覆盖通道——唯一例外是测试 harness 的 `AI_TOWN_REAL_MODEL` 开关（`DOC-RELEASE-011` canonical），它不进入玩家发布路径。
- `RULE-RELEASE-054`：用户数据根路径固定为 `%LOCALAPPDATA%\AI-Town`，由后端进程解析；前端、REST 参数与任何配置项都不能改写数据库或存档路径（落实「禁止前端指定数据库路径」）。

## 5. 数据与接口

### 5.1 `app_settings` 键白名单

`DES-RELEASE-014`：首版全部合法键（值均为 JSON）：

| 键 | 类型与约束 | 默认值 |
|---|---|---|
| `ui.fullscreen_hint_shown` | boolean | `false` |
| `ui.last_world_id` | string(ULID) 或 null | `null` |
| `ui.tray_notify_on_autosave` | boolean | `false` |
| `simulation.default_speed` | enum `0.5/1/2/4` | `1` |
| `ai.base_url` | string(https URL，同 `DOC-AI-007` 配置档) | `"https://api.deepseek.com"` |
| `ai.model` | string，唯一合法值 `"deepseek-v4-flash"` | `"deepseek-v4-flash"` |
| `ai.request_concurrency_limit` | integer 1..2（上限来自 `DOC-AI-009`） | `2` |
| `diagnostics.include_recovery_reports` | boolean | `true` |

存量示例行：

```json
{
  "key": "simulation.default_speed",
  "value_json": "1"
}
```

### 5.2 SecretProvider Port

`DES-RELEASE-015`：

```text
set_deepseek_key(command_id, plaintext) -> MaskedStatus     # 写 Credential Store / Fallback
get_deepseek_key() -> SecretHandle | NotConfigured          # 仅后端内部
clear_deepseek_key(command_id) -> Ok
get_masked_status() -> MaskedStatus                         # REST 可见
```

Key 生命周期状态机：

```text
not_configured -> configured            # set 成功（含替换旧值）
configured -> not_configured            # clear（Credential Store 与 Fallback 同时清除）
configured -> invalid_reported          # 模型 401/403 后标记，仍保留存储值等待玩家处理
```

`SecretHandle` 是进程内不可序列化对象：禁止实现 `__str__`/`repr` 输出明文、禁止进入异常消息与日志字段；跨 Port 传递只传句柄。

## 6. 正常流程

1. 首启：`app_settings` 写入全部默认键；Key 状态 `not_configured`，AI 功能提示待配置（世界可用 Utility AI 运行，`REQ-PRODUCT-007`）。
2. 玩家在设置页输入 Key：经同源 Session 提交（`DOC-BACKEND-009`），后端写 Credential Store，返回 Masked Status。
3. 后端启动模型请求时经 SecretProvider 取句柄注入 HTTP 客户端 Authorization 头。
4. 玩家修改 `simulation.default_speed`：白名单校验 → `app_settings` 单行 UPSERT → 立即生效。
5. 玩家清除 Key：两处存储同时删除，状态回 `not_configured`。

## 7. 边界情况

- 中文用户名下的 Credential Store 与 `%LOCALAPPDATA%` 路径：条目名固定 ASCII，路径按 Unicode 处理；打包验收覆盖（`DOC-RELEASE-012`）。
- Windows 用户更换密码导致 DPAPI 解密失败（漫游场景）：读取失败按 `not_configured` 处理并提示重新输入，不崩溃、不删除密文文件。
- Credential Store 写入成功但删除旧 Fallback 失败：记录告警并在每次启动重试删除；读取顺序保证使用新值。
- 从旧机器整体复制 `%LOCALAPPDATA%\AI-Town`：`secrets\deepseek.dpapi` 在新机器不可解密（DPAPI 绑定用户），行为同上；`app_settings` 正常生效。
- 玩家手工向 `app_settings` 表插入未知键（外部编辑）：启动校验发现后忽略并告警，不因此拒绝启动；写路径仍拒绝未知键。
- `ai.base_url` 被改为非 https 或非法 URL：写入拒绝；存量非法值按内置默认回退并告警。

## 8. 错误与降级

Credential Store 与 DPAPI 双双不可用（极端受损系统）：Key 不可持久化，提供「仅本次会话」内存模式并明确告知重启后需重输，绝不落盘明文。`app_settings` 读失败按内置默认运行并告警。任何配置错误都不阻止世界以 Utility AI 模式运行。

## 9. 安全与性能

- Key 校验错误（401/403）的日志只记录状态码与 request_id，不记录任何 Key 片段。
- Masked Status 只含末 4 位；长度不足 8 的输入直接拒绝（格式校验归 `DOC-BACKEND-009`）。
- 配置读取全部走内存缓存，`app_settings` 变更时失效重载；不在 Tick 热路径查库。
- 内存中的 Key 缓冲在 clear/替换后主动清零（尽力而为；Python 层配合一次性句柄使用模式）。

## 10. 验收标准

- 配置 Key 后全盘扫描 `%LOCALAPPDATA%\AI-Town`（含 SQLite、WAL、日志、导出包）与浏览器存储，无 Key 明文或可逆形态。
- Credential Store 正常与被禁用两种环境下 Key 均可配置、使用、清除；清除后两处存储均为空。
- REST 任何响应不含明文 Key，仅 Masked Status。
- 白名单外键与非法值写入被拒绝且有明确错误码。
- 卸载（删除包目录）后 Key 仍安全隔离在用户凭据区，删除用户数据目录不影响 Credential Store 条目的独立清除入口。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-025` | `RULE-RELEASE-048`, `RULE-RELEASE-053` 白名单、Schema 校验与封闭优先级 |
| `TEST-RELEASE-026` | `RULE-RELEASE-049..050` 全介质 Secret 禁入与主备存储互斥 |
| `TEST-RELEASE-027` | `RULE-RELEASE-051..052` 内存句柄、Masked Status 与非持久化凭据 |
| `TEST-RELEASE-028` | `RULE-RELEASE-054` 路径不可改写 |

## 12. 关联文档

- `DOC-BACKEND-009`：Key 提交端点、格式校验与传输安全（canonical）
- `DOC-BACKEND-008`：Session 与本地权限
- `DOC-AI-007`：模型配置档对 `ai.base_url`/`ai.model` 的消费
- `DOC-RELEASE-001`：`app_settings` 表与只读安装目录
- `DOC-RELEASE-008`：`instance.json` 与 shutdown_token 生命周期
- `DOC-RELEASE-010`：脱敏扫描对本文件规则的验证

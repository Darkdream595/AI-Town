---
doc_id: DOC-BACKEND-009
title: DeepSeek Key 保护
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - deepseek-key-storage
  - credential-reference-boundary
  - secret-redaction-policy
depends_on:
  - DOC-FOUNDATION-005
  - DOC-BACKEND-002
  - DOC-BACKEND-008
  - DOC-AI-007
requirements:
  - REQ-BACKEND-009
last_updated: 2026-07-26
---

# DeepSeek Key 保护

## 1. 目的

`REQ-BACKEND-009`：定义 DeepSeek API Key 的提交通道、Windows Credential Manager / DPAPI 存储、opaque credential reference 边界、内存持有纪律、日志与错误脱敏，落实 `RULE-FOUNDATION-024` 与 `DOC-FOUNDATION-002` 模块表中 `security/` 的职责（禁止原始 Key 进入 SQLite）。

## 2. 非目标

本文不定义模型请求参数与 endpoint 配置（`DOC-AI-007`，模型 `deepseek-v4-flash`、Base URL `https://api.deepseek.com`）、非敏感配置存储（`DOC-RELEASE-007`）、诊断包脱敏流水线（`DOC-RELEASE-010`，本文提供其 Secret 判定来源）。不支持多 Key 轮换池或云端密钥托管。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| API Key 明文 | 用户从 DeepSeek 平台获取的原始密钥字符串 |
| Credential Ref | `security/` 颁发的 opaque 引用 ID，可流通、不可解出明文 |
| Secret Store | Windows Credential Manager 条目或 DPAPI 加密文件 |
| Masked Suffix | 仅用于 UI/日志展示的 Key 末 4 字符 |
| Redaction Filter | 对全部日志/错误/诊断输出执行的 Secret 擦除层 |
| Key Fingerprint | Key 的 SHA-256 前 12 hex 字符，用于注册 Redaction 与变更审计 |

## 4. 规则与不变量

- `RULE-BACKEND-049`：Key 只能经 `PUT /api/v1/secrets/deepseek-api-key`（同源 Session + CSRF，`secret` Route Class 限速）提交，请求体仅 `{schema_version, api_key}`；任何响应、事件、Snapshot、投影都不回显明文，状态查询只返回 `configured`、Masked Suffix 与最近验证结果。
- `RULE-BACKEND-050`：存储首选 Windows Credential Manager Generic Credential（`TargetName=AI-Town/deepseek-api-key`，per-user）；Credential Manager 不可用时降级为 DPAPI（`CryptProtectData`，`CRYPTPROTECT_UI_FORBIDDEN`，per-user scope）加密文件 `%LOCALAPPDATA%\AI-Town\secrets\deepseek.bin`。两者之外不存在第三种持久化形式，尤其禁止明文文件与环境变量持久化。
- `RULE-BACKEND-051`：Key 明文不得进入：SQLite（app 与 world 库）、任何配置文件、日志、结构化事件、浏览器 localStorage/sessionStorage/IndexedDB、URL/query、崩溃转储上报、Snapshot、导出存档、诊断包。CI 与运行时各有一道检查（静态扫描 + Redaction Filter）。
- `RULE-BACKEND-052`：`security/` 之外只流通 Credential Ref（落实 `RULE-BACKEND-009` 的包边界）；仅 ModelProvider adapter 在发起 HTTPS 请求的瞬间将 ref 解析为 `Authorization` 头。明文持有时间以单次请求为界，不写入可复用缓存、不拼接进可长期存活的对象；请求结束即释放引用（Python 运行时下以最小可达性为目标）。
- `RULE-BACKEND-053`：Redaction Filter 对所有日志、错误 message/details、诊断输出执行两类擦除：已注册 Key Fingerprint 对应值的精确匹配、`sk-[A-Za-z0-9]{8,}` 模式匹配，命中替换为 `[REDACTED]`。上游 401/403/429 只记录 HTTP status 与 reason code，禁止记录请求头与请求体。
- `RULE-BACKEND-054`：Key 生命周期操作（set/verify/delete）全部写审计日志（操作、Masked Suffix、结果、RealTime）；delete 立即移除 Secret Store 条目并使全部在存 Credential Ref 失效；verify 使用最小请求验证连通性，目标为 `DOC-AI-007` 配置的 Base URL `https://api.deepseek.com` 与模型 `deepseek-v4-flash`。

## 5. 数据与接口

`DES-BACKEND-009`：`SecretStatusV1`：

```json
{
  "schema_version": 1,
  "secret_kind": "deepseek_api_key",
  "configured": true,
  "storage_backend": "windows_credential_manager",
  "masked_suffix": "4f2a",
  "last_verified_at": "2026-07-26T08:30:15.250Z",
  "last_verify_result": "ok"
}
```

`storage_backend` ∈ `windows_credential_manager/dpapi_file`；`last_verify_result` ∈ `ok/unauthorized/network_error/not_verified`。

`security/` 包接口（其余包可见的全部能力）：

```text
set_secret(kind, plaintext) -> SecretStatus          # 仅 api/ 的 secret 路由可调用
get_credential_ref(kind) -> CredentialRef | not_configured
resolve_for_request(credential_ref) -> AuthHeaderHandle   # 仅 ModelProvider adapter
delete_secret(kind) -> SecretStatus
register_redaction(fingerprint)                       # set 时自动调用
```

`AuthHeaderHandle` 是一次性对象：注入单个 HTTP 请求后即不可再用。

本文敏感字段日志策略（全项显式，master 表见 `DOC-BACKEND-012`）：

| 字段 | 日志策略 |
|---|---|
| `api_key` 明文 | never——任何级别、任何目标都不允许 |
| `Authorization` 头 | never |
| `credential_ref` | id-only（本身 opaque，可记录） |
| `masked_suffix` | allowed |
| Key Fingerprint | allowed（审计用） |
| verify 请求/响应体 | never；只记录 status 与 reason code |
| Secret Store 文件路径 | allowed（不含内容） |

## 6. 正常流程

1. 用户在设置页粘贴 Key，前端仅在内存持有并立即 PUT 提交，不落浏览器任何存储。
2. `api/` 路由经 `RULE-BACKEND-022` 全部防线后调用 `set_secret`：写 Secret Store、注册 Redaction、生成新 Credential Ref、审计。
3. 后端立即执行 verify 并返回 `SecretStatusV1`；UI 显示 Masked Suffix 与验证结果。
4. AI 请求路径：worker 从 `get_credential_ref` 取 ref，adapter 在发送瞬间 `resolve_for_request` 注入头（并发与取消语义见 `DOC-AI-009`）。
5. 用户删除 Key：Confirmation Token（`RULE-BACKEND-023`）→ `delete_secret` → 在途请求按取消处理，后续模型调用走 Utility 降级（`DOC-AI-011`）。

## 7. 边界情况

- Credential Manager 写入成功但读取失败（策略/损坏）：状态报 `configured=false` 且 `storage_backend` 标注失败原因 reason code，提示重新提交；不尝试从日志或内存「找回」。
- DPAPI 文件被其他 Windows 用户读取：DPAPI per-user scope 使其无法解密；本产品不防御同一 Windows 用户下的其他进程（威胁模型边界，与 `DOC-PLAYER-009` §9 一致）。
- 用户粘贴带空白/换行的 Key：提交前 trim；trim 后为空即 `BACKEND_SCHEMA_INVALID`，不存空 Key。
- 进程崩溃于 set 中途：Secret Store 写入是单条目原子操作；verify 未完成时状态为 `not_verified`，下次启动可重新 verify，无半配置状态。
- 更换 Key：新值覆盖同一条目，旧 Fingerprint 保留在 Redaction 注册表直到进程重启，防止旧 Key 出现在滞后日志中。

## 8. 错误与降级

Secret Store 双后端均不可用时：Key 功能整体禁用（`BACKEND_STORAGE_FAILURE`），世界模拟继续以 Utility AI 运行（`DOC-AI-011`），UI 明确提示。verify 失败不阻止保存——网络问题下允许「已保存未验证」状态，但 unauthorized 结果会在状态中明示。任何脱敏失败路径 fail closed：Redaction Filter 异常时丢弃该条日志而非明文写出。

## 9. 安全与性能

`security/` 包无网络能力（`RULE-BACKEND-008` 依赖矩阵），resolve 只发生在 adapter 进程内调用；Key 不经过 WebSocket 通道。Redaction Filter 为 O(已注册指纹数 + 单模式扫描)，注册指纹 ≤ 8 条，对日志吞吐影响可忽略。Secret 相关端点全部计入审计且限速 5/min（`RULE-BACKEND-047`）。

## 10. 验收标准

- 全链路扫描（SQLite 文件、日志、配置、诊断包、浏览器存储、崩溃输出）在注入已知测试 Key 后零命中明文。
- Credential Manager 与 DPAPI 两后端各自完成 set/get/verify/delete 往返。
- 非 `security/` 包获取明文的静态审计路径数为零（`TEST-BACKEND-008` 的细化）。
- 上游 401/429 故障注入后日志只含 status 与 reason code。
- 删除 Key 后在途请求取消、后续请求走降级、Secret Store 无残留条目。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-032` | `RULE-BACKEND-049..050` 提交通道与双后端存储往返 |
| `TEST-BACKEND-033` | `RULE-BACKEND-051` 全目标明文零泄漏扫描 |
| `TEST-BACKEND-034` | `RULE-BACKEND-052..053` ref 边界、单请求持有与 Redaction |
| `TEST-BACKEND-035` | `RULE-BACKEND-054` 生命周期审计、删除失效与 verify 语义 |

## 12. 关联文档

- `DOC-AI-007`：模型 profile 与请求参数（Key 的消费方）
- `DOC-AI-009` / `DOC-AI-011`：在途取消与无 Key 降级
- `DOC-BACKEND-002`：`security/` 包依赖边界
- `DOC-BACKEND-008`：提交通道复用的本地防线
- `DOC-RELEASE-007` / `DOC-RELEASE-010`：非敏感配置与诊断包脱敏

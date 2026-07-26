---
doc_id: DOC-BACKEND-007
title: 协议兼容与 Schema 版本化
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - protocol-version-layers
  - schema-compatibility-policy
  - wire-schema-registry
depends_on:
  - DOC-FOUNDATION-006
  - DOC-BACKEND-005
  - DOC-BACKEND-006
requirements:
  - REQ-BACKEND-007
last_updated: 2026-07-26
---

# 协议兼容与 Schema 版本化

## 1. 目的

`REQ-BACKEND-007`：定义三层版本体系（`protocol_version`、payload `schema_version`、REST path major）、兼容变更白名单、Client/Server 同包发布下的版本失配处理、持久化数据的 upcaster 迁移与 wire Schema 注册表，保证每个 API Schema 都有版本且演进可审计。

## 2. 非目标

本文不定义具体 Schema 的字段内容（各 owner 文档）、SQLite 表结构迁移（`DOC-RELEASE-002`）、存档文件格式（`DOC-RELEASE-003..004`）。本文拥有 wire 与持久化 Envelope/payload 的版本策略，不拥有数据库 DDL 迁移工具链。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| `protocol_version` | Envelope/帧层整数版本，Client 与 Server 必须一致 |
| `schema_version` | 单个 payload/Resource Schema 的整数版本 |
| Compatible Change | 同版本内允许的向后兼容变更 |
| Breaking Change | 必须 bump 版本的不兼容变更 |
| Upcaster | 将旧版本持久化数据无损升级为当前版本的纯函数 |
| Schema Registry | 所有 wire Schema 的 name/version/owner/状态登记表 |
| Golden Sample | 每个 Schema 版本冻结的示例 JSON，用于 CI 兼容 diff |

## 4. 规则与不变量

- `RULE-BACKEND-037`：版本分三层且各自独立递增：`protocol_version`（uint，全部 Command/Event Envelope 与 WS 帧）、每个 payload/Resource Schema 的 `schema_version`（uint，从 1 起）、REST path major（`/api/v1`）。任何出现在 wire 上的 JSON 对象必须能通过其外层定位到明确的 `(schema 名, schema_version)`。
- `RULE-BACKEND-038`：Compatible Change 白名单：新增 optional 字段（必须定义缺省语义）、为显式标注 open enum 的字段新增取值、新增 frame/command/event/端点类型。Breaking Change：删除或重命名字段、改变类型/单位/语义、optional 变必填、closed enum 增删值、改变字段间约束。Breaking 必须 bump 对应 `schema_version` 或 `protocol_version`，禁止复用旧字段名承载新语义（呼应 `RULE-FOUNDATION-031` 的不复用原则）。
- `RULE-BACKEND-039`：Client 与 Server 同包发布、同源托管，运行时不做多版本协商：`hello` 帧与 `GET /api/v1/meta` 暴露 `protocol_version`，不一致（典型原因是浏览器缓存旧 bundle）时服务器返回 `BACKEND_PROTOCOL_MISMATCH`，Client 必须强制刷新重载静态资源后重试；服务器不为旧 Client 保留旧行为。
- `RULE-BACKEND-040`：持久化的 Event/Snapshot 携带写入时 `schema_version`；加载时经注册的 Upcaster 链逐版升级为当前版本。Upcaster 必须是纯函数、可单测、无信息丢失；无法无损升级时停止加载该 world 并报告（落实 `DOC-FOUNDATION-006` §8），禁止猜测缺失字段。
- `RULE-BACKEND-041`：Schema Registry 是全部 wire Schema 的唯一登记处：`name`、`version`、`owner_doc_id`、`status`（`active/deprecated/frozen`）与 Golden Sample。CI 对 Golden Sample 做结构 diff：未 bump 版本的 Breaking Change、未登记 Schema 上线、`frozen` Schema 被修改均导致构建失败。

## 5. 数据与接口

`DES-BACKEND-007`：Registry 条目：

```json
{
  "schema_version": 1,
  "name": "EconomyTransactionCommittedV1",
  "payload_schema_version": 1,
  "owner_doc_id": "DOC-ECON-006",
  "status": "active",
  "kind": "event_payload",
  "golden_sample_path": "schemas/golden/economy_transaction_committed_v1.json",
  "introduced_protocol_version": 1
}
```

`kind` ∈ `command_payload/event_payload/rest_resource/ws_frame/persisted_record`。

Upcaster 接口：

```text
upcast(name, from_version, json_object) -> json_object   # 纯函数，单版本步进
upcast_chain(name, from_version, to_version, json_object) -> json_object
registry.lookup(name, version) -> SchemaEntry | not_registered
```

版本失配处理矩阵：

| 场景 | 判定点 | 行为 |
|---|---|---|
| WS hello `client_protocol_version` 不等于服务器值 | 握手 | `BACKEND_PROTOCOL_MISMATCH`，Client 强制刷新 |
| REST body `schema_version` 高于服务器已知 | 请求验证 | 400 `BACKEND_PROTOCOL_MISMATCH`（不猜测未来字段） |
| REST body `schema_version` 低于当前且仍 `active` | 请求验证 | 按该版本 Schema 校验后 upcast 进入用例 |
| 持久化事件版本低于当前 | world 加载/重放 | Upcaster 链升级 |
| 持久化版本高于当前（降级安装） | world 加载 | 拒绝加载该 world，提示版本不足 |

## 6. 正常流程

1. Owner 文档定义/修改 Schema，同步更新 Registry 条目与 Golden Sample。
2. CI 兼容 diff：比对新旧 Golden Sample，验证变更落在白名单内或版本已 bump。
3. 发布时 Client 与 Server 一并打包，`protocol_version` 单点常量注入双端。
4. 运行期按 §5 矩阵处理失配；持久化读取路径统一走 `upcast_chain`。
5. 废弃 Schema 先标 `deprecated`（服务器仍接受），下一个 `protocol_version` bump 时移除并标 `frozen` 留档。

## 7. 边界情况

- 同一发布内多个 Schema 各自 bump：互不影响，`protocol_version` 只在 Envelope/帧层结构变化时才 bump。
- Upcaster 链缺一环（如 v1→v3 缺 v2→v3）：Registry 校验在构建期失败，不进入运行时。
- open enum 收到未知值：标注 open enum 的字段按注册的 fallback 语义处理（如 `unknown` 归类）；closed enum 未知值即 Schema 校验失败。
- 强制刷新后仍失配：说明静态资源与进程不同包（部署损坏），Client 显示明确错误页，不循环刷新（最多重试 2 次）。
- 事件在旧版本写入、新版本重放并再持久化：Event Log 保留原始版本原文（`RULE-FOUNDATION-027` 只追加），升级只发生在读取路径，不改写历史。

## 8. 错误与降级

版本失配错误统一 `BACKEND_PROTOCOL_MISMATCH`，details 含 `expected` 与 `received` 版本号（数字，无敏感内容）。Upcaster 抛错按 world 加载失败处理：该 world 保持关闭、其余功能可用，交 `DOC-RELEASE-006` 的损坏分级流程；不允许跳过个别事件继续重放。

## 9. 安全与性能

版本号只使用整数，解析前先做数值有限性检查，防止超大版本触发 upcast 链遍历滥用（链长上限 16）。Registry 与 Golden Sample 打包为只读资源；运行时 Schema 校验器按 `(name, version)` 缓存编译结果。失配错误不回显 Client 提交的 body。

## 10. 验收标准

- wire 上任意 JSON 对象均可定位到 Registry 条目与版本，抽样审计零遗漏。
- 白名单内变更不 bump 版本可通过 CI；任一 Breaking 变更未 bump 被 CI 拦截（含删字段、改类型、closed enum 变更三类回归样例）。
- 旧版本持久化世界经 upcast 后加载成功且状态 Hash 与升级前语义一致；高版本世界被拒绝加载。
- 缓存旧 bundle 的 Client 在一次强制刷新内恢复正常。
- `frozen` Schema 的任何改动导致构建失败。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-025` | `RULE-BACKEND-037..038` 版本分层与兼容白名单 CI diff |
| `TEST-BACKEND-026` | `RULE-BACKEND-039` 失配矩阵与强制刷新收敛 |
| `TEST-BACKEND-027` | `RULE-BACKEND-040..041` Upcaster 链无损性与 Registry 完整性 |

## 12. 关联文档

- `DOC-FOUNDATION-006`：基元格式与 §8 旧 Schema 转换原则
- `DOC-BACKEND-005..006`：被版本化的 Command/Event Envelope
- `DOC-BACKEND-004`：REST Resource Schema 与 path major
- `DOC-RELEASE-002..003`：数据库迁移与 Event Log 持久化

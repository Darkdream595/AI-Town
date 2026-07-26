---
doc_id: DOC-BACKEND-001
title: FastAPI 服务架构
version: 1.0.0
status: approved-for-implementation
owner_domain: backend
canonical_for:
  - fastapi-process-topology
  - static-hosting-and-bind-policy
  - async-queue-isolation
depends_on:
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-003
requirements:
  - REQ-BACKEND-001
last_updated: 2026-07-26
---

# FastAPI 服务架构

## 1. 目的

`REQ-BACKEND-001`：定义 Windows 10/11 本地单进程 FastAPI Authority Server 的进程拓扑、静态资源托管、绑定策略、异步队列隔离、启动与关闭顺序。本文落实 `DOC-FOUNDATION-002` 的权威架构，是后端进程层面的 canonical 细化。

## 2. 非目标

本文不定义具体 REST 路由（`DOC-BACKEND-004`）、WebSocket 帧语义（`DOC-BACKEND-003`）、Domain 模块内部规则（各 domain 文档）、SQLite Schema 与 Migration（`DOC-RELEASE-001..003`）、启动器与打包（`DOC-RELEASE-008..009`）。不支持远程访问、多机部署或多客户端协作。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Authority Server Process | 本机唯一 Python 进程，承载 FastAPI、World Runtime 与持久化 |
| ASGI Server | uvicorn 单 worker 实例，只服务 loopback |
| Static Bundle | 构建期生成的 Phaser 3 前端静态文件，由同一端口同源提供 |
| World Writer | 每世界唯一串行提交者，消费 World Command Queue |
| Outbound Sender | 每 WebSocket Session 独立的有界出站协程 |
| Graceful Drain | 停止接收新输入、完成在途事务并落盘的安全关闭 |

## 4. 规则与不变量

- `RULE-BACKEND-001`：ASGI Server 只绑定 `127.0.0.1`，监听单一可配置端口（默认 8765）；绑定 `0.0.0.0` 或非 loopback 地址时启动必须拒绝。
- `RULE-BACKEND-002`：前端 Static Bundle 与 REST/WebSocket 由同一端口同源提供；不允许跨端口 API 调用，从协议上消除 CORS preflight 需求。
- `RULE-BACKEND-003`：单进程单 ASGI worker；不允许以多 worker 水平扩展。世界写入扩展只能通过 `RULE-FOUNDATION-005` 的队列隔离实现。
- `RULE-BACKEND-004`：AI Request、Long Action、Persistence、WebSocket Outbox 四类异步队列与 World Command Queue 彼此隔离，任一队列积压不得阻塞 `DOC-TIME-003` 的 10 Hz World Tick 提交。
- `RULE-BACKEND-005`：World Tick critical section 内不得 await 网络、模型、日志刷盘、Snapshot 或 WebSocket 发送（落实 `RULE-TIME-015`）；出站事件先入 Outbox 内存队列。
- `RULE-BACKEND-006`：每个队列有固定容量上限与明确满溢策略：World Command Queue 满时对新命令返回 `BACKEND_QUEUE_FULL`；其余队列满时按各 owner 降级策略丢弃可合并项，不可丢 DomainEvent 永不丢弃。

## 5. 数据与接口

`DES-BACKEND-001`：进程内部件与启动顺序：

```text
bootstrap/config load (含 Secret Provider 装配, DOC-BACKEND-009)
-> persistence open + migration + integrity (DOC-RELEASE-001..003)
-> snapshot read + event log replay + reservation/AI 核对
-> core invariant recovery audit (DOC-FOUNDATION-005)
-> revision projection rebuild
-> lift Recovery Barrier
-> ASGI bind 127.0.0.1:port, 开始接收 REST/WebSocket
-> scheduler / AI workers / outbox senders 启动
```

ASGI 应用分层（自外向内）：

```text
HTTP/WebSocket transport
-> Origin/Host 检查 (DOC-BACKEND-008)
-> body size / rate limit middleware
-> Session 解析与权限 (DOC-BACKEND-008)
-> 路由层 (DOC-BACKEND-004) / WebSocket 端点 (DOC-BACKEND-003)
-> Command/Event Envelope 协议适配 (DOC-BACKEND-005..006)
-> Application Orchestrator -> World Runtime
```

关键配置项（`bootstrap` 只读装配，运行时不可变）：

| 配置 | 默认 | 约束 |
|---|---|---|
| `bind_host` | `127.0.0.1` | 必须是 loopback 字面量 |
| `bind_port` | 8765 | 1024–65535，占用时尝试顺延最多 8 个端口 |
| `static_dir` | 打包内 `client/` | 只读，禁止路径穿越（见 §9） |
| `max_body_bytes` | 65536 | 超过返回 `BACKEND_BODY_TOO_LARGE` |
| `world_command_queue_capacity` | 256 | 每世界 |
| `ws_outbox_capacity` | 512 | 每 Session |

## 6. 正常流程

1. 启动器（`DOC-RELEASE-008`）拉起进程并传入配置与数据目录。
2. `bootstrap` 按 §5 顺序装配；任一恢复步骤失败则进程保持 Recovery Barrier、只暴露健康与诊断端点。
3. 正常运行：REST/WS 入口完成协议与安全检查后入队命令；World Writer 串行消费；已提交事件经 Outbox 推送到 Session。
4. 关闭：收到 SIGINT/SIGTERM 或启动器关闭请求后进入 Graceful Drain——停止接受新命令、完成在途事务、取消 AI 在途请求（按 `DOC-AI-009` 的取消语义）、落盘持久化队列、关闭数据库、退出。

## 7. 边界情况

- 默认端口被占用：在 8765–8772 内顺延并写入启动日志；全部占用则退出并给出明确错误，不静默绑定非 loopback。
- 关闭时 World Command Queue 仍有积压：已接受命令必须完成或明确以 `BACKEND_SHUTDOWN` 失败回执，不允许无声丢弃。
- 浏览器直接访问 API 路径之外的 URL：回退到 `index.html`（前端路由），但 `/api/`、`/ws/` 前缀下不存在路径一律 404，不做 SPA 回退。
- 进程崩溃后重启：走 §5 恢复序列；未完成 Reservation 与 AI Request 按 `DOC-FOUNDATION-002` §6.3 核对。

## 8. 错误与降级

- 静态资源缺失或损坏：API 仍可服务，根路径返回明确错误页；不伪造前端版本。
- 某异步队列持续满溢：记录 overload 指标并触发 `DOC-TIME-011` 降档链路；World Tick 与提交路径不受影响。
- Graceful Drain 超过 10 秒：强制取消剩余在途工作，已提交状态不回滚；未提交事务全部回滚。

## 9. 安全与性能

- 静态文件服务必须拒绝 `..` 路径穿越、跟随符号链接与目录列举；只服务 `static_dir` 内白名单扩展名。
- 响应默认带 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`Content-Security-Policy: default-src 'self'`。
- World Tick 预算独立于模型网络延迟；出站合并仅在 Outbox 层做，不改变事件顺序。所有队列指标供 `DOC-BACKEND-012` 采集。

## 10. 验收标准

- 绑定非 loopback 地址时启动失败且日志给出 `BACKEND_BIND_REFUSED`。
- 同源访问前端与 API 全程无 CORS preflight。
- 故障注入下四类异步队列互不造成 World Tick 级联阻塞。
- Graceful Drain 后 Event Log 与状态在同一提交边界，无半事务。
- 架构测试证明不存在第二条世界写入路径。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-BACKEND-001` | `RULE-BACKEND-001..003` bind/worker/同源策略 |
| `TEST-BACKEND-002` | `RULE-BACKEND-004..006` 队列隔离、容量与满溢回执 |
| `TEST-BACKEND-003` | 启动恢复顺序与 Recovery Barrier |
| `TEST-BACKEND-004` | Graceful Drain 原子性与 `BACKEND_SHUTDOWN` 回执 |

## 12. 关联文档

- `DOC-FOUNDATION-002`：权威架构、队列与恢复基线
- `DOC-FOUNDATION-005`：提交原子性与幂等不变量
- `DOC-TIME-003` / `DOC-TIME-011`：Tick cadence、I/O 隔离与降档
- `DOC-BACKEND-003..004`：WebSocket 与 REST 入口细化
- `DOC-BACKEND-012`：指标、日志与负载测试

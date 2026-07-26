---
doc_id: DOC-RELEASE-008
title: Windows 双击启动器
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - launcher-lifecycle
  - single-instance-policy
  - health-polling-protocol
  - tray-and-stop-flow
depends_on:
  - DOC-FOUNDATION-001
  - DOC-RELEASE-001
  - DOC-RELEASE-007
  - DOC-RELEASE-009
  - DOC-TIME-009
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-002
  - REQ-RELEASE-008
last_updated: 2026-07-26
---

# Windows 双击启动器

## 1. 目的

`REQ-RELEASE-008`：定义 `启动AI小镇.bat` 双击后的完整启动链——Batch 委派、单实例互斥、127.0.0.1 随机端口绑定、健康轮询、默认浏览器打开、系统托盘常驻——以及 `停止AI小镇.bat` 备用停止路径，使普通玩家在无 Python/Node 环境、含中文与空格的安装路径下可靠启动与安全退出。

## 2. 非目标

本文件不定义发布包目录与打包方式（`DOC-RELEASE-009`）；不定义后端 REST/WS 协议（`DOC-BACKEND-*`）；不定义关闭时的世界暂停语义（`DOC-TIME-009`）；不定义全屏交互细节（`DOC-PLAYER-010`）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Batch Entry | `启动AI小镇.bat`，只做定位与委派的入口脚本 |
| Launcher Process | `runtime\backend\AI-Town.exe`（windowed，无控制台窗口），承载托盘与后端 |
| Singleton Mutex | 命名互斥体 `Local\AITown.Launcher.Singleton`（每用户会话一个实例） |
| instance.json | `%LOCALAPPDATA%\AI-Town\runtime\instance.json`，运行实例的端口/pid 记录 |
| Health Endpoint | `GET /api/health`，Launcher 与停止脚本共同依赖的就绪探针 |
| shutdown_token | 每次启动 CSPRNG 生成的一次性停止凭据，仅存 instance.json |

## 4. 规则与不变量

- `RULE-RELEASE-055`：Batch Entry 只做三件事：`chcp 65001` 设定代码页、以 `"%~dp0"` 定位包根、引号包裹全路径委派 `start "" "%~dp0runtime\backend\AI-Town.exe"`。不解析参数、不写注册表、不请求管理员权限；必须在含中文、空格与括号的安装路径下工作。
- `RULE-RELEASE-056`：单实例：Launcher 启动即尝试持有 Singleton Mutex；已被持有时不启动第二个后端，而是读取 instance.json 并用默认浏览器打开现有实例 URL 后退出（二次双击 = 重新打开游戏页面）。
- `RULE-RELEASE-057`：端口选择：后端绑定 `127.0.0.1:0` 由 OS 分配临时端口；禁止固定端口与 `0.0.0.0` 绑定；端口、pid、started_at、package_version、shutdown_token 原子写入 instance.json（write-temp + rename）。
- `RULE-RELEASE-058`：健康轮询协议：Launcher 每 500 ms 请求 `/api/health`，总超时 60 s；仅当响应 `status="ready"` 才打开浏览器；`status="error"` 或超时进入错误提示（托盘气泡 + 打开日志目录入口），不打开浏览器、不无限重试。
- `RULE-RELEASE-059`：托盘图标在后端就绪后出现并常驻，菜单固定四项：打开游戏 / 保存并退出 / 打开诊断文件夹 / 关于（版本号）。「保存并退出」执行 `DOC-TIME-009` 正常关闭序列（Quiescence → checkpoint → 关库），完成后删除 instance.json 并退出进程。
- `RULE-RELEASE-060`：`停止AI小镇.bat` 为托盘不可用时的备用：读取 instance.json，`POST /api/shutdown`（携带 shutdown_token）；15 s 内收到进程退出确认则删除 instance.json；否则打印指引（任务管理器结束 `AI-Town.exe` 会按崩溃恢复处理），脚本自身绝不 `taskkill /f` 强杀，避免绕过安全保存。
- `RULE-RELEASE-061`：陈旧实例检测：启动时 instance.json 存在但其 pid 不存活或 Health Endpoint 不可达，视为上次崩溃残留——删除该文件、正常启动，世界打开走崩溃恢复链（`DOC-RELEASE-006`）。
- `RULE-RELEASE-062`：浏览器策略：仅调用系统默认浏览器打开 `http://127.0.0.1:<port>/`；不安装浏览器、不改浏览器设置、不模拟按键触发全屏（`REQ-PRODUCT-002` 由页面内提示与按钮满足）。

## 5. 数据与接口

### 5.1 instance.json

`DES-RELEASE-016`：文件位于每用户可写目录，NTFS 默认 ACL 即为本用户私有：

```json
{
  "instance_format_version": 1,
  "pid": 18244,
  "port": 54321,
  "url": "http://127.0.0.1:54321/",
  "package_version": "1.0.0",
  "started_at": "2026-07-26T12:00:00.000Z",
  "shutdown_token": "d41f1a0a5f2e4b8c9a7d6e5f4c3b2a10"
}
```

`/api/health` 响应（端点归 `DOC-BACKEND-004`，字段契约在此固定）：

```json
{
  "status": "ready",
  "package_version": "1.0.0",
  "build_id": "43d1e4a",
  "open_world_id": null,
  "uptime_ms": 4200
}
```

`status` 枚举：`starting`（服务已监听但恢复链未完成）/ `ready` / `error`。

### 5.2 Launcher 状态机

`DES-RELEASE-017`：

```text
launched -> mutex_acquired -> backend_starting -> polling
polling -> ready -> browser_opened -> tray_resident
polling -- timeout/error --> failed (托盘错误提示 + 日志入口)
tray_resident -> shutting_down -> exited          # 保存并退出 / 停止脚本
launched -- mutex_busy --> focus_existing -> exited
```

`POST /api/shutdown`：仅接受回环来源且 `shutdown_token` 匹配；触发与托盘「保存并退出」同一序列；重复调用幂等（已在关闭中则返回进行中状态）。

## 6. 正常流程

1. 玩家双击 `启动AI小镇.bat` → Batch 委派 Launcher Process。
2. Launcher 取得 Mutex，启动内嵌 FastAPI 后端（同进程），绑定随机端口，写 instance.json。
3. 健康轮询至 `ready`（首启含 `app.sqlite3` 创建/迁移，属 `starting` 阶段）。
4. 打开默认浏览器进入游戏页；托盘图标出现。
5. 玩家游玩后从托盘或网页选择「保存并退出」：干净关闭、删除 instance.json、进程退出。

## 7. 边界情况

- 安装路径为 `C:\游戏 测试\AI 小镇(正式)\`：`%~dp0` 与引号策略保证委派成功；`chcp 65001` 保证 Batch 内中文输出不乱码；打包验收覆盖（`DOC-RELEASE-012`）。
- 端口被占用：不可能持续发生——绑定 `:0` 由 OS 分配；绑定失败（如安全软件拦截回环）重试 3 次后进入 failed 并提示防火墙指引。
- 双实例竞态（两次极快双击）：Mutex 原子裁决；败者等待 instance.json 出现（最多 10 s）后打开 URL，仍无则提示稍后重试。
- 浏览器打开失败（无默认浏览器关联）：托盘气泡显示 URL 并提供「复制地址」，后端照常运行。
- 玩家直接关闭浏览器标签页：世界按会话断开策略暂停（`DOC-TIME-002`），托盘仍常驻，可重新「打开游戏」。
- Windows 注销/关机广播：Launcher 响应 `WM_QUERYENDSESSION`/console control 事件，执行快速正常关闭（10 s 预算，超时按崩溃恢复兜底）。
- 停止脚本在后端已死时运行：连接失败 → 直接清理陈旧 instance.json 并提示已无运行实例。

## 8. 错误与降级

启动链失败点（Mutex、绑定、健康超时、浏览器）各自给出玩家可读提示与日志路径，Launcher 保持可重试的干净退出，不留半启动进程。托盘崩溃不影响后端：停止脚本与网页内退出仍可用。任何失败路径都不删除用户数据。

## 9. 安全与性能

- 后端仅绑定 `127.0.0.1`；`/api/shutdown` 额外要求 shutdown_token，防止本机其他页面盲发停止请求（同源与 Session 防护归 `DOC-BACKEND-008`）。
- instance.json 不含任何 API Key/Session Secret；shutdown_token 单次启动有效，进程退出即作废并删除文件。
- 双击到 `ready` 目标：冷启动 ≤ 60 s、二次启动 ≤ 20 s（`DOC-RELEASE-012` 验收阈值）；健康轮询网络开销可忽略。
- Launcher 不加载游戏资源，常驻内存目标 ≤ 后端进程整体预算内（`DOC-TIME-011`）。

## 10. 验收标准

- 中文 + 空格 + 括号安装路径、中文用户名环境下双击启动成功并自动打开浏览器。
- 运行中二次双击不产生第二个后端进程，浏览器打开现有实例。
- 托盘「保存并退出」后：世界干净关闭（`-wal` 长度 0）、instance.json 删除、进程退出。
- 托盘被杀后 `停止AI小镇.bat` 可安全停止；后端已死时脚本正确清理残留。
- 崩溃残留场景下再次双击可正常启动并进入恢复链。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-029` | `RULE-RELEASE-055..057` Batch 委派、单实例与随机端口 |
| `TEST-RELEASE-030` | `RULE-RELEASE-058`, `RULE-RELEASE-062` 健康轮询与浏览器策略 |
| `TEST-RELEASE-031` | `RULE-RELEASE-059..060` 托盘退出与备用停止脚本 |
| `TEST-RELEASE-032` | `RULE-RELEASE-061` 陈旧实例清理与崩溃恢复衔接 |

## 12. 关联文档

- `DOC-RELEASE-009`：`AI-Town.exe` 的打包形态与包布局
- `DOC-RELEASE-006`：崩溃残留后的恢复链
- `DOC-RELEASE-007`：shutdown_token 的凭据归类
- `DOC-TIME-009`：保存并退出的关闭序列
- `DOC-BACKEND-004`：`/api/health`、`/api/shutdown` 端点注册
- `DOC-BACKEND-008`：回环绑定与同源防护

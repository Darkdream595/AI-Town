---
doc_id: DOC-RELEASE-012
title: 发布验收清单与质量门 G9
version: 1.0.0
status: approved-for-implementation
owner_domain: release
canonical_for:
  - g9-release-gate
  - packaged-acceptance-checklist
depends_on:
  - DOC-FOUNDATION-001
  - DOC-RELEASE-008
  - DOC-RELEASE-009
  - DOC-RELEASE-010
  - DOC-RELEASE-011
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-010
  - REQ-RELEASE-012
last_updated: 2026-07-26
---

# 发布验收清单与质量门 G9

## 1. 目的

`REQ-RELEASE-012`：定义质量门 G9「Windows 发布包通过真实双击验收」的精确、可执行清单：环境矩阵、逐项 check、证据要求、通过判定与结果归档格式。G9 是发布前最后一道门，前置条件是 `DOC-RELEASE-011` 的 Release Candidate Suite 全绿。

## 2. 非目标

本文件不定义测试层级与自动化套件（`DOC-RELEASE-011`）；不定义包构建（`DOC-RELEASE-009`）；不定义 G0–G8 其他阶段门（`DOC-FOUNDATION-001` 与规格的 Gate 表）；不承诺代码签名与商店分发（首版范围外）。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| G9 | 阶段门：发布包在真实干净 Windows 环境通过双击验收 |
| Clean Machine | 无 Python、Node.js、Git、IDE 且 PATH 无开发工具的 Windows 实例 |
| Environment Matrix | G9 必须覆盖的操作系统 × 用户名 × 安装路径组合 |
| Check | 清单中一条原子验收项，含操作、期望与证据 |
| Evidence | 截图、终端输出、导出文件或日志片段，随结果归档 |
| Acceptance Record | `release-acceptance-<package_version>.json` 结果文件 |

## 4. 规则与不变量

- `RULE-RELEASE-086`：G9 必须在至少两台 Clean Machine 上真实执行：Windows 10 22H2 x64 与 Windows 11 x64 各一（物理机或全新快照虚拟机均可）；执行前自动断言机器干净（PATH 与注册表无 Python/Node/Git），不干净的机器结果无效。
- `RULE-RELEASE-087`：Environment Matrix 必须完整覆盖第 5.1 节组合，其中强制包含：中文用户名账户、含中文与空格的安装路径（如 `C:\游戏 测试\AI 小镇\`）、桌面路径；全部组合通过 G9 才通过。
- `RULE-RELEASE-088`：每条 Check 必须记录 `check_id`、执行人、机器标识、结果（`pass`/`fail`）与 Evidence 引用；结果只有 pass/fail 两态——任何 fail 或未执行项都使 G9 不通过，且按 Gate 纪律不得宣称后续阶段完成。
- `RULE-RELEASE-089`：启动性能阈值：双击到 `/api/health` 返回 `ready`，冷启动（本机首次）≤ 60 s、二次启动 ≤ 20 s；超时即 fail（阈值与 `DOC-RELEASE-008` 一致）。
- `RULE-RELEASE-090`：版本一致性三方比对为强制 Check：`release-manifest.json`、运行中 `/api/health`、构建源 commit 三者的 `package_version` 与 `build_id` 完全一致，且 manifest 逐文件哈希复算通过；任一不符即 fail（防发布包非最新代码）。
- `RULE-RELEASE-091`：会话后安全扫描为强制 Check：在配置过真实格式 Canary Key 并游玩后，对 `%LOCALAPPDATA%\AI-Town` 全部文件、包目录、浏览器本地存储执行 Secret Scanner（`DOC-RELEASE-010`），发现 Key 形态内容即 fail；同时抽查日志确认无 Prompt/对话原文。
- `RULE-RELEASE-092`：Acceptance Record 随发布产物归档入库（与包 zip 同处保存）；重跑 G9 生成新 Record 并保留旧 Record 与重跑原因，不覆盖历史。

## 5. 数据与接口

### 5.1 Environment Matrix

`DES-RELEASE-024`：最少 5 个组合，全部必须执行：

| 组合 ID | OS | 用户名 | 安装路径 |
|---|---|---|---|
| ENV-1 | Windows 10 22H2 | ASCII | `C:\Games\AI-Town\` |
| ENV-2 | Windows 10 22H2 | 中文（如 `李测试`） | `C:\游戏 测试\AI 小镇\` |
| ENV-3 | Windows 11 | ASCII | `%USERPROFILE%\Desktop\AI-Town\` |
| ENV-4 | Windows 11 | 中文 | 含中文+空格+括号路径（如 `D:\我的 游戏(新)\AI-Town\`） |
| ENV-5 | Windows 11 | 中文 | ENV-4 同机：二次启动、停止脚本与卸载场景 |

### 5.2 G9 Check 清单

机器可读清单（现场工具直接消费；`manual` 表示人工操作+证据，`auto` 表示脚本断言）：

```json
{
  "checklist_version": 1,
  "gate": "G9",
  "requires": ["release-candidate-suite-green"],
  "checks": [
    {"check_id": "G9-CHK-001", "mode": "auto", "title": "机器干净性断言：PATH 与注册表无 Python/Node/Git"},
    {"check_id": "G9-CHK-002", "mode": "auto", "title": "release-manifest 逐文件哈希复算通过"},
    {"check_id": "G9-CHK-003", "mode": "manual", "title": "解压到矩阵指定路径，双击 启动AI小镇.bat"},
    {"check_id": "G9-CHK-004", "mode": "auto", "title": "冷启动 <= 60 s 达 ready，浏览器自动打开游戏页"},
    {"check_id": "G9-CHK-005", "mode": "auto", "title": "版本三方比对：manifest = /api/health = 构建源 commit"},
    {"check_id": "G9-CHK-006", "mode": "manual", "title": "首次进入出现 F11 与界面全屏按钮提示，切换全屏成功"},
    {"check_id": "G9-CHK-007", "mode": "manual", "title": "创建新世界并进入：移动、碰撞、对话、进入室内、地图切换各执行一次"},
    {"check_id": "G9-CHK-008", "mode": "manual", "title": "切换镇长模式执行一项治理操作；返回居民模式"},
    {"check_id": "G9-CHK-009", "mode": "manual", "title": "触发一场回合战斗并正常结束"},
    {"check_id": "G9-CHK-010", "mode": "manual", "title": "手动存档到 slot_1；刷新浏览器后世界恢复一致"},
    {"check_id": "G9-CHK-011", "mode": "auto", "title": "配置 Canary Key 后游玩 10 分钟，会话后 Secret 扫描全净"},
    {"check_id": "G9-CHK-012", "mode": "manual", "title": "运行中二次双击：不出现第二实例，浏览器聚焦现有页面"},
    {"check_id": "G9-CHK-013", "mode": "manual", "title": "托盘 保存并退出：进程退出、-wal 为 0、再次启动从存档恢复"},
    {"check_id": "G9-CHK-014", "mode": "manual", "title": "杀掉托盘后用 停止AI小镇.bat 安全停止"},
    {"check_id": "G9-CHK-015", "mode": "auto", "title": "licenses 目录存在且 THIRD-PARTY-NOTICES 覆盖依赖清单"},
    {"check_id": "G9-CHK-016", "mode": "manual", "title": "README-开始游戏.txt 记事本打开中文正常"},
    {"check_id": "G9-CHK-017", "mode": "auto", "title": "断网环境下启动与游玩可用（Utility AI 降级），无未处理异常"},
    {"check_id": "G9-CHK-018", "mode": "manual", "title": "删除包目录（卸载）后用户数据仍在 %LOCALAPPDATA%\\AI-Town；重新解压新包后世界可继续"}
  ]
}
```

### 5.3 Acceptance Record

```json
{
  "record_format_version": 1,
  "gate": "G9",
  "package_version": "1.0.0",
  "build_id": "43d1e4a",
  "executed_at": "2026-07-26T16:00:00.000Z",
  "environments": [
    {
      "env_id": "ENV-2",
      "os": "Windows 10 22H2",
      "machine_fingerprint": "vm-snapshot-cn-user-01",
      "operator": "release-qa",
      "results": [
        {"check_id": "G9-CHK-001", "result": "pass", "evidence": "evidence/env2/chk001-path.txt"},
        {"check_id": "G9-CHK-004", "result": "pass", "evidence": "evidence/env2/chk004-timing.json"}
      ]
    }
  ],
  "outcome": "pass",
  "rerun_of": null,
  "rerun_reason": null
}
```

`outcome` 仅当全部环境 × 全部 check 为 pass 时为 `pass`。

## 6. 正常流程

1. Release Candidate Suite 全绿（`DOC-RELEASE-011`），取得候选包 zip 与构建 commit。
2. 准备 Environment Matrix 的干净快照，分发同一 zip。
3. 每个环境按清单顺序执行 auto + manual check，随做随录证据。
4. 汇总生成 Acceptance Record；outcome=pass 则 G9 通过，包定稿归档。
5. outcome=fail：按 fail 项归因（包、文档或环境），修复后从受影响层重跑（可能回退到 Release Candidate Suite），重新执行 G9 全量。

## 7. 边界情况

- 仅个别环境 fail（如仅中文路径失败）：G9 整体 fail；不允许「除中文路径外通过」的部分通过结论。
- SmartScreen 拦截提示：按 README 指引通过属预期（`DOC-RELEASE-009` 边界），需截图存证；若「仍要运行」后无法启动才是 fail。
- 快照复用污染（上轮测试残留 `%LOCALAPPDATA%\AI-Town`）：G9-CHK-001 扩展断言用户数据目录不存在；污染机器结果作废，回滚快照重跑。
- manual check 执行中环境断电等外因中断：该环境全部 check 作废重跑，已收集证据保留标注。
- Canary Key 与真实 Key：G9 全程使用真实格式的 Canary（`sk-` 前缀假值）；连通真实 DeepSeek 不在 G9 范围（`DOC-RELEASE-011` 冒烟处理），G9-CHK-017 反向验证断网可玩。
- 30 天后补测同一包：Record 追加 rerun 记录；包 zip 哈希必须与归档一致，否则视为新候选走全流程。

## 8. 错误与降级

G9 没有降级通过路径：清单不可裁剪、阈值不可现场放宽；变更清单或阈值必须先修订本文件（文档变更流程），再对新版本清单执行完整 G9。工具故障导致 auto check 无法执行时，不允许以人工目测替代 auto 断言——修复工具后重跑。

## 9. 安全与性能

- 验收机器与证据存储不接触真实 API Key；证据文件归档前过 Secret Scanner（`DOC-RELEASE-010`）。
- Evidence 中的截图不含操作者个人信息区域（任务栏账户名允许，属测试账户）。
- 启动计时用 G9 工具的 monotonic 时钟测量（`RULE-FOUNDATION-035`），不用人工掐表。
- 单环境全清单目标执行时长 ≤ 90 分钟，保证一天内完成全矩阵。

## 10. 验收标准

- 本清单 18 项 check × 5 环境全部执行且 pass，Acceptance Record 的 `outcome` 为 `pass`。
- Record 与证据完整归档，可追溯到包 zip 哈希与构建 commit。
- 对照总体验收条款：双击启动、全屏游玩、安全退出、断网可玩、Key 不落地五项均有对应 pass 证据。
- 任一 check 人为改为 fail 时，汇总工具输出 `outcome:"fail"` 且列出未通过项（工具自检）。
- G9 通过后发布物（zip + manifest + Record）三件套完整。

## 11. 测试追踪

| 测试 ID | 覆盖规则 |
|---|---|
| `TEST-RELEASE-045` | `RULE-RELEASE-086..087` 干净机器断言与环境矩阵覆盖 |
| `TEST-RELEASE-046` | `RULE-RELEASE-088..089` check 记录完备性与启动阈值判定 |
| `TEST-RELEASE-047` | `RULE-RELEASE-090..091` 版本三方比对与会话后安全扫描 |
| `TEST-RELEASE-048` | `RULE-RELEASE-092` Acceptance Record 归档与重跑追溯 |

## 12. 关联文档

- `DOC-RELEASE-008`：启动链行为与计时阈值来源
- `DOC-RELEASE-009`：包布局、manifest 与 SmartScreen 边界
- `DOC-RELEASE-010`：Secret Scanner 与证据脱敏
- `DOC-RELEASE-011`：G9 的前置 Release Candidate Suite
- `DOC-FOUNDATION-001`：产品成功标准与 Gate 纪律

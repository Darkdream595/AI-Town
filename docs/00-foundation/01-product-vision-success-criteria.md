---
doc_id: DOC-FOUNDATION-001
title: 产品愿景与成功标准
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - product-vision
  - first-version-scope
  - product-success-criteria
depends_on: []
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-002
  - REQ-PRODUCT-003
  - REQ-PRODUCT-004
  - REQ-PRODUCT-005
  - REQ-PRODUCT-006
  - REQ-PRODUCT-007
  - REQ-PRODUCT-008
  - REQ-PRODUCT-009
  - REQ-PRODUCT-010
  - REQ-PRODUCT-011
  - REQ-PRODUCT-012
  - REQ-PRODUCT-013
  - REQ-PRODUCT-014
  - REQ-PRODUCT-015
  - REQ-PRODUCT-016
  - REQ-PRODUCT-017
  - REQ-PRODUCT-018
  - REQ-PRODUCT-019
  - REQ-PRODUCT-020
last_updated: 2026-07-26
---

# 产品愿景与成功标准

## 1. 目的

本文件定义 AI 小镇首版的玩家承诺、范围边界和可量化完成标准，是所有子系统需求取舍的最高产品依据。

**玩家承诺：** 玩家进入一个持续、可恢复且遵守同一套规则的中世纪剑与魔法小镇；8–12 名 AI 居民会基于自身所知、关系和处境自主行动，玩家既能作为居民生活，也能以受约束的镇长身份治理，任何 AI 文本都不能越过世界规则。

## 2. 非目标

首版明确不包含局域网或公网多人、手机适配、云存档、语音输入、正式居民永久死亡、AI 创建新的可执行 Action 类型、每局重生成整张地图、Mod SDK、Steam 或应用商店发布、公网后端、自动切换模型供应商，以及展示或持久化原始 Chain of Thought。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 首版 | 通过本文件十项完成标准、可交付给 Windows 10/11 单机玩家的版本 |
| 居民模式 | 玩家以居民身份受碰撞、经济、战斗、权限和社会规则约束的模式 |
| 镇长模式 | 玩家以治理身份操作公共预算、建筑、道路、公告、节日与灾害的模式 |
| `Sandbox Admin` | 可选调试身份；所有破坏性命令二次确认、审计并永久标记存档 |
| 正式居民 | 首版 8–12 名拥有持久身份、关系、记忆与生命周期的核心 AI 居民 |
| 可操作 | DeepSeek 不可用时，玩家仍可移动、交互、保存，居民由 Utility AI 维持安全与基本生活 |
| 完成 | 同时满足 `REQ-PRODUCT-001..020` 且通过本文件第 10 节全部验收 |

## 4. 规则与不变量

### 4.1 首版 Must Requirements

| ID | 必须满足的产品需求 |
|---|---|
| `REQ-PRODUCT-001` | Windows 10/11 玩家双击 `启动AI小镇.bat` 后，本地服务自动启动并打开浏览器，不要求安装 Python 或 Node.js。 |
| `REQ-PRODUCT-002` | 首次进入必须明确提示 `F11` 与界面全屏按钮；Fullscreen API 必须由用户点击触发。 |
| `REQ-PRODUCT-003` | 玩家与 AI 居民只能处于合法站立区，不能穿越房屋、树木、悬崖、水域、废墟或封锁区。 |
| `REQ-PRODUCT-004` | AI 居民自主提出目标、对象、Action、参数和表达；后端验证并提交，模型不得直接修改世界。 |
| `REQ-PRODUCT-005` | 居民模式支持移动、交谈、工作、交易、施法、战斗、建立关系和影响事件。 |
| `REQ-PRODUCT-006` | 镇长模式支持受权限、规则与预算约束的治理，不能读取私人记忆、强制感情或指定战斗胜负。 |
| `REQ-PRODUCT-007` | DeepSeek 超时、限流、空响应、非法 JSON、Schema 错误或不可用时，世界必须有界重试并降级到本地 Utility AI。 |
| `REQ-PRODUCT-008` | 世界关闭后暂停；重启后从一致的 Snapshot、Event Log 和当前状态恢复，不按离线现实时间推进。 |
| `REQ-PRODUCT-009` | 正式居民首版不永久死亡；HP 归零转入昏迷、重伤、撤退或被俘等可持续后果。 |
| `REQ-PRODUCT-010` | 发布前必须通过 Unit、Property、Contract、Integration、Simulation、Browser E2E、Visual QA 与 Packaged Release 验收。 |
| `REQ-PRODUCT-011` | 新世界包含 8–12 名正式居民，并覆盖维持首版经济、治疗、安全与生产所需的角色能力。 |
| `REQ-PRODUCT-012` | 可玩空间仅包含王冠溪镇、暮语森林、银烬矿洞及其独立室内场景，区域通过成对 Semantic Exit 连接。 |
| `REQ-PRODUCT-013` | 首版包含五层地图、动态建筑及其建造、损坏、修复与同步导航更新。 |
| `REQ-PRODUCT-014` | 支持多世界、五个自动恢复点、每世界三个手动槽位，以及读取旧槽位时创建新时间线分支。 |
| `REQ-PRODUCT-015` | 首版是仅绑定 `127.0.0.1` 的单机 Client–Server 产品，不提供局域网、公网或云服务。 |
| `REQ-PRODUCT-016` | 原始 `reasoning_content`/Chain of Thought 不展示、不写入居民记忆、不进入普通日志或诊断包。 |
| `REQ-PRODUCT-017` | AI、玩家和 AI Event Director 只能选择注册的 Action、Spell、Quest Objective 与 Event Template。 |
| `REQ-PRODUCT-018` | 规则随机数由世界 Seed 派生；模型响应以输入、版本与输出记录重放，不以重新请求代替历史事实。 |
| `REQ-PRODUCT-019` | DeepSeek API Key 仅存于 Windows Credential Manager 或按用户保护的 DPAPI 数据中，不进入 SQLite、文件配置、日志或浏览器存储。 |
| `REQ-PRODUCT-020` | 在游戏代码与正式美术生产前，188 份文档必须完成、通过一致性与可实现性审计，并经一次性 Gate G5 验收。 |

`RULE-FOUNDATION-001`：子系统不得弱化上述 Must Requirement；若实现约束冲突，应在 canonical owner 修订并同步 traceability，不得建立竞争定义。

## 5. 数据与接口

产品范围由 `ProductBaseline` 只读配置表达：

```json
{
  "baseline_version": "1.0.0",
  "platforms": ["windows-10", "windows-11"],
  "core_resident_min": 8,
  "core_resident_max": 12,
  "regions": ["crown-creek-town", "twilight-whisper-forest", "silver-ash-mine"],
  "auto_recovery_points": 5,
  "manual_slots_per_world": 3,
  "model": "deepseek-v4-flash",
  "model_base_url": "https://api.deepseek.com"
}
```

`DES-FOUNDATION-001`：构建、存档、世界初始化和验收工具必须读取同一版本的 `ProductBaseline`；运行时不得通过前端参数扩大范围。

## 6. 正常流程

1. Launcher 启动本地权威服务器并打开同源 Phaser 3 客户端。
2. 玩家创建或读取世界，服务器恢复 Revision、Seed、GameTime 和居民状态。
3. 玩家在居民/镇长模式间切换，所有命令进入统一验证与事件提交链。
4. AI 调度器构建主观上下文，DeepSeek 返回 `ActionProposal`，后端重新校验后提交。
5. 服务正常退出时完成保存与一致性检查，世界停止推进。

## 7. 边界情况

- 端口占用时 Launcher 选择随机可用端口，但仍只绑定 loopback。
- 浏览器拒绝 Fullscreen API 时保持窗口模式，核心玩法不得被阻断。
- 模型队列过载时降低游戏倍率并优先玩家对话、战斗和危险动作。
- 磁盘空间不足时停止新的破坏性提交，保留最近一致状态并给出可恢复错误。
- 正式居民遭遇致命数值时转换为非永久结局，不删除 Resident aggregate。

## 8. 错误与降级

模型失败按 `REPAIRABLE`、`REPLAN_REQUIRED`、`FORBIDDEN` 分类；只允许白名单字段修正和有限重试。渲染资源缺失时使用已登记 fallback。恢复失败时先复制原数据库，再停止该世界模拟并提供诊断，不得静默重建或丢弃事件。

## 9. 安全与性能

本地不等于可信：必须验证 Host、Origin、Session、WebSocket Ticket、输入大小与速率。默认 World Tick 为 10 Hz、前端目标 60 FPS、普通居民模型请求最多并发 2 个；性能降级不能牺牲权威校验、秘密过滤或持久化一致性。

## 10. 验收标准

以下十项全部通过才可宣称首版完成：

1. 新 Windows 10/11 环境在中文与空格路径中双击启动、全屏提示、保存并安全退出。
2. 三个区域、独立室内和五层地图通过真实碰撞及关键通路测试。
3. 8–12 名正式居民可自主生活，玩家与 AI 使用同一世界规则。
4. 每个 AI 意图均留下提案、批准、拒绝或降级记录，非法 Action 无状态副作用。
5. 居民模式和镇长模式的完整能力、权限及预算边界通过 E2E。
6. 经济、物品、魔法、战斗、建筑、任务和天气可跨存档持续。
7. 1、7、30 游戏日模拟无核心不变量破坏、无无限队列增长。
8. DeepSeek 故障矩阵下世界仍可操作，且无无限重试。
9. API Key、未授权秘密与原始 Chain of Thought 在数据库、日志、浏览器存储和诊断包扫描中均为零泄露。
10. 188 份文档通过全量 ID、链接、Schema、默认值与可实现性审计，并完成 Gate G5。

## 11. 测试追踪

| 测试 ID | 覆盖需求 | 层级 |
|---|---|---|
| `TEST-FOUNDATION-001` | `REQ-PRODUCT-001..002`, `REQ-PRODUCT-015` | Packaged Release / Browser E2E |
| `TEST-FOUNDATION-002` | `REQ-PRODUCT-003`, `REQ-PRODUCT-012..013` | Property / Browser E2E |
| `TEST-FOUNDATION-003` | `REQ-PRODUCT-004`, `REQ-PRODUCT-007`, `REQ-PRODUCT-017` | Contract / Integration |
| `TEST-FOUNDATION-004` | `REQ-PRODUCT-005..006`, `REQ-PRODUCT-011` | Browser E2E / Simulation |
| `TEST-FOUNDATION-005` | `REQ-PRODUCT-008..009`, `REQ-PRODUCT-014`, `REQ-PRODUCT-018` | Recovery / Property |
| `TEST-FOUNDATION-006` | `REQ-PRODUCT-010`, `REQ-PRODUCT-020` | Corpus / Release Gate |
| `TEST-FOUNDATION-007` | `REQ-PRODUCT-016`, `REQ-PRODUCT-019` | Security |

## 12. 关联文档

- `DOC-FOUNDATION-002`：总体架构与权威数据流
- `DOC-FOUNDATION-005`：跨系统不可违反项
- `DOC-FOUNDATION-007`：需求—设计—测试追踪矩阵
- `DOC-FOUNDATION-008`：完整文档索引与阅读顺序

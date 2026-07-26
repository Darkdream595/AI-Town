---
doc_id: DOC-FOUNDATION-004
title: 全局术语表
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - shared-technical-vocabulary
  - chinese-display-terms
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
requirements:
  - REQ-PRODUCT-003
  - REQ-PRODUCT-004
  - REQ-PRODUCT-008
  - REQ-PRODUCT-017
last_updated: 2026-07-26
---

# 全局术语表

## 1. 目的

为文档、代码、协议、测试和中文 UI 建立统一词义。English technical identifier 在 Schema/代码中保持原样，中文列仅用于说明或玩家可见文案。

## 2. 非目标

本文件不枚举各 domain 的全部字段、状态和错误码；domain 专用术语由 owner 文档定义，但不得改变这里的共享词义。

## 3. 术语与定义

### 3.1 命令、提案与事件

| English identifier | 中文显示/说明 | Canonical definition |
|---|---|---|
| `ActionProposal` | 行动提案 | AI 对一个注册 Action 的非权威结构化选择；经最新世界状态校验和提交后才生效 |
| `PlayerCommand` | 玩家命令 | 玩家输入形成的结构化非权威请求，必须经过同一 Domain 规则 |
| `PlayerSpeechCommand` | 玩家发言命令 | 纯文本及会话上下文引用，不拥有关系或交易副作用 |
| `AdminCommand` | 管理命令 | `Sandbox Admin` 的独立命令类型，要求权限、二次确认、审计和存档标记 |
| `DomainEvent` | 领域事件 | 已提交的原子客观事实，不可丢弃、可重放，携带 causation/correlation |
| `WorldEvent` | 世界事件 | 跨时间持续、有生命周期和影响范围的世界态事件 |
| `Quest` | 任务 | 由结构化 Objective、状态、参与者、期限和结果组成的目标集合 |
| `WorldDiff` | 世界差异 | 对道路、建筑或环境的追加式持久变更；恢复以反向事件追加，不删除历史 |
| `Command Envelope` | 命令信封 | 包含 protocol、command、world、expected Revision、type 与 payload 的协议外壳 |
| `Event Envelope` | 事件信封 | 包含 protocol、event、world、Revision、GameTime、因果、payload 与 render 的协议外壳 |

### 3.2 一致性与持久化

| English identifier | 中文显示/说明 | Canonical definition |
|---|---|---|
| `Revision` | 世界修订号 | 每世界从 0 开始、每次成功写事务严格递增的 unsigned 64-bit 整数 |
| `Reservation` | 资源预留 | 有 owner、资源、数量、到期 GameTime 与状态的临时排他声明；不是最终所有权 |
| `Snapshot` | 快照 | 锚定明确 Revision 的完整可恢复投影，不能替代其后的 Event Log |
| `Event Log` | 事件日志 | 按 Revision 追加、不可就地改写的 DomainEvent 序列 |
| `Idempotency` | 幂等性 | 相同 Command ID 重复提交最多产生一次状态变化和一组事件 |
| `Causation ID` | 原因 ID | 直接导致当前事件的 Command/Event ID |
| `Correlation ID` | 关联 ID | 贯穿一个业务流程的追踪 ID |
| `Seed` | 世界种子 | 创建世界后不可变的 128-bit 值，用于派生命名随机流 |
| `Timeline Branch` | 时间线分支 | 从旧存档读取时创建的新 world timeline，保留来源 Revision 引用 |

### 3.3 空间、地图与表现

| English identifier | 中文显示/说明 | Canonical definition |
|---|---|---|
| `World Coordinate` | 世界坐标 | 区域内以 world unit 表示的右手二维坐标，原点左上，+X 向右，+Y 向下 |
| `Local Coordinate` | 局部坐标 | Interior/对象局部空间坐标，必须通过显式 Transform 转换为所属 Scene 坐标 |
| `Semantic Node` | 语义节点 | 带稳定 ID、类型、站立点、交互方向和权限条件的规则位置 |
| `Semantic Exit` | 语义出口 | 成对连接区域/室内、定义 approach 与 arrival node 的特殊 Semantic Node |
| `Walkability` | 可行走性 | 结构化合法站立区域及动态修饰，不从图片像素推断 |
| `Collision` | 碰撞 | 阻止移动或占位的结构化 Polygon/shape 与边界规则 |
| `Footprint Polygon` | 占地多边形 | Structure/Building 占用土地的闭合 Polygon，与 Collision 可不同 |
| `Navigation Modifier` | 导航修饰 | 对可达性或路径成本的确定性动态改变 |
| `Ground Art` | 地表美术层 | 无角色、UI、文字和可拆建筑的非权威视觉底图 |
| `Render Event` | 渲染事件 | Event Envelope 中可合并的表现指令；不承载唯一规则事实 |

### 3.4 居民、认知与社会

| English identifier | 中文显示/说明 | Canonical definition |
|---|---|---|
| `Resident` | 居民 | 有稳定身份、生命周期、状态和规则能力的 aggregate |
| `DecisionContext` | 决策上下文 | 在某 Revision/GameTime 对 actor 可见信息的不可变、权限过滤快照 |
| `Daily Plan` | 每日计划 | 日级目标与候选活动，不是资源或位置的保证 |
| `Hourly Intent` | 小时意图 | 当前目标、候选序列、预计时间与放弃条件 |
| `Immediate Action` | 即时行动 | 一次注册 Action 的可验证提案 |
| `EpisodicMemory` | 情景记忆 | 居民对特定经历的主观记录 |
| `SemanticBelief` | 语义信念 | 居民认为成立的抽象事实，可错误且不等于客观状态 |
| `SocialImpression` | 社会印象 | 居民对他人的主观评价证据 |
| `Commitment` | 承诺 | 有参与者、内容、期限和履行状态的社会义务 |
| `BeliefTransfer` | 信念传播 | 带来源链、可信度与失真的谣言传递 |
| `Secret Access Level` | 秘密访问级别 | `public/community/faction/relationship/personal/shared_secret` 的后端访问分类 |

### 3.5 时间、模拟与玩法

| English identifier | 中文显示/说明 | Canonical definition |
|---|---|---|
| `RealTime` | 现实时间 | 单调时钟的持续时长，用于超时、性能与动画，不推进世界日期 |
| `GameTime` | 游戏时间 | 世界内 UTC-free calendar instant，受暂停和倍率控制 |
| `TurnTime` | 回合时间 | Encounter 内离散回合/阶段序号，不与 RealTime 换算 |
| `World Tick` | 世界 Tick | 默认 10 Hz 的权威提交机会，不代表所有周期业务都逐 Tick 执行 |
| `Active` | 活跃模拟 | 玩家所在区域，完整路径与碰撞 |
| `Warm` | 温区模拟 | 其他加载区域，语义路径与分钟级推进 |
| `Background` | 后台模拟 | 未加载区域/长任务，按开始、结束和条件推进 |
| `Utility AI` | 效用 AI | 模型失败时执行注册、确定性、安全动作的本地降级器 |
| `Narrative Pressure Budget` | 叙事压力预算 | 限制危机并发、冷却和强度的世界事件资源 |
| `Encounter` | 遭遇/战斗 | 暂停 Overworld、以 TurnTime 推进的独立战斗状态 |

## 4. 规则与不变量

- `RULE-FOUNDATION-012`：标识符采用本文件 English spelling；中文文案可本地化但不得改变 Schema 名称。
- `RULE-FOUNDATION-013`：`DomainEvent`、`WorldEvent`、`Quest` 三者不可互换；前者是事实，后两者是可持续 aggregate。
- `RULE-FOUNDATION-014`：`Walkability` 表示可站立，`Collision` 表示阻挡；二者必须分别验证，不能互为反义简化。
- `RULE-FOUNDATION-015`：`ActionProposal` 与 `PlayerCommand` 仅表示请求，不表示成功。

## 5. 数据与接口

`DES-FOUNDATION-004`：共享 Schema 字段名必须使用 `snake_case`，JSON enum value 使用 lowercase `snake_case`，TypeScript/Python 内部类型可按各自惯例映射但 wire format 不变。术语注册项至少包含 `term_id`、English identifier、中文说明、owner_domain、schema_version。

## 6. 正常流程

新增共享术语时，提出者先查询本表，确定 Canonical Owner 和唯一 spelling；owner 在其文档定义完整 Schema；本表只登记跨域语义；消费者引用 DOC/Rule ID，不复制另一套定义。

## 7. 边界情况

- UI 可将 `Revision` 显示为“同步版本”，协议仍使用 `revision`。
- “事件”若只表示一次事实，必须命名 `DomainEvent`；有生命周期才可命名 `WorldEvent`。
- `Reservation` 到期不代表交易成功；owner 必须明确释放或消费。
- 室内 `Local Coordinate` 不得仅凭数值与室外 World Coordinate 比较。

## 8. 错误与降级

协议遇到未知 enum 或 term version 时拒绝写命令并返回版本错误；读取旧事件时由版本化 upcaster 转换。显示层缺少中文翻译时可显示 English identifier，但不得猜测替代字段。

## 9. 安全与性能

术语本身不携带 Secret；日志记录 ID 而非完整敏感 payload。词表加载应构建不可变索引并按版本缓存，不能在每个 Tick 扫描 Markdown。

## 10. 验收标准

- 所有要求的共享 identifier 均有唯一、无歧义定义。
- Schema 与示例中的拼写能映射到本表。
- 中文 UI 术语与 English wire identifier 分离。
- 跨域审计不存在把 Proposal、Command 或动画当作已提交事实的表述。

## 11. 测试追踪

| 测试 ID | 覆盖规则 | 断言 |
|---|---|---|
| `TEST-FOUNDATION-017` | `RULE-FOUNDATION-012..013` | 共享 identifier 与事件类型 lint |
| `TEST-FOUNDATION-018` | `RULE-FOUNDATION-014` | Walkability/Collision schema 分离 |
| `TEST-FOUNDATION-019` | `RULE-FOUNDATION-015` | 未提交 Proposal/Command 无状态副作用 |

## 12. 关联文档

- `DOC-FOUNDATION-003`：术语 owner domain
- `DOC-FOUNDATION-005`：术语对应的跨系统不变量
- `DOC-FOUNDATION-006`：ID、时间、坐标和单位的精确定义

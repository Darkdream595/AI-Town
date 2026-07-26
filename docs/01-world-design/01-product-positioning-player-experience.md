---
doc_id: DOC-WORLD-001
title: 产品定位与玩家体验
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - world-product-positioning
  - player-experience-pillars
  - narrative-experience-boundaries
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
requirements:
  - REQ-WORLD-001
  - REQ-WORLD-002
  - REQ-WORLD-003
last_updated: 2026-07-26
---

# 产品定位与玩家体验

## 1. 目的

定义 AI 小镇的世界层产品定位、核心玩家体验与内容取舍标准，使居民、对话、事件、地图和美术实现共同服务于“一个会继续生活、会记住选择、但不围着玩家旋转的小镇”。

## 2. 非目标

本文件不定义输入按键、战斗公式、经济价格、AI Prompt、地图 Polygon 或 UI 布局；这些由对应 canonical owner 负责。本作不是高速刷装、无约束上帝模拟、恋爱角色收集、无限生成沙盒，也不以连续灾难或残酷处决制造刺激。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 活世界体验 | 8–12 名正式居民在玩家不介入时仍按 Needs、承诺、工作和处境行动 |
| 居民视角 | 玩家作为世界内角色，使用与 AI 居民相同的碰撞、经济、魔法、战斗和社会规则 |
| 有限治理 | 镇长可配置公共资源和制度，但不能读取私人记忆、强制感情或指定胜负 |
| 温暖表层 | 日常劳动、饮食、节庆、互助和自然景观形成的可亲近生活层 |
| 暗流层 | 资源匮乏、旧战争遗留、危险探索、派系冲突和可持续失败后果 |
| 可归因后果 | 能追溯到已提交事件、参与者认知和规则结算的世界变化 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-001` | 首版必须同时提供居民生活、自然语言社交、三地区探索、受约束治理和可持续后果五类体验。 |
| `REQ-WORLD-002` | 世界叙事必须允许居民拒绝玩家、独立解决问题、失败或改变立场，不把玩家设为所有事件的必然中心。 |
| `REQ-WORLD-003` | 温暖日常与黑暗风险必须并存；任何失败不得通过无成本复位抹除正式居民的长期后果。 |
| `RULE-WORLD-001` | 玩家和 AI 居民遵守同一客观世界规则，差异仅在决策来源与玩家拥有的合法治理身份。 |
| `RULE-WORLD-002` | 每个重要叙事结果必须由 `DomainEvent`、`WorldEvent`、关系/记忆解释或结构化制度状态支持，文本本身不构成事实。 |
| `RULE-WORLD-003` | 内容优先级依次为可理解因果、居民自主性、长期可恢复性、氛围表现；氛围不能覆盖规则反馈。 |
| `RULE-WORLD-004` | 镇长模式是世界内职务，不是无审计作弊界面；超出职权的操作只能进入独立 `Sandbox Admin` 流程。 |

## 5. 数据与接口

`DES-WORLD-001`：向下游发布只读 `PlayerExperienceProfile`，字段固定为：

| 字段 | 类型 | 约束 |
|---|---|---|
| `experience_pillars` | stable ID list | `living_world`, `grounded_agency`, `meaningful_relationships`, `constrained_governance`, `lasting_consequences` |
| `tone_layers` | enum list | `warm_daily_life`, `mystery`, `danger`, `aftermath`, 至少保留一个日常层 |
| `player_centrality` | enum | 固定 `participant_not_chosen_one` |
| `consequence_horizon` | enum | `immediate`, `daily`, `seasonal` |
| `prohibited_promises` | stable ID list | 不得出现永久安全、全知镇长、强制友谊、AI 任意改写规则 |

该 Profile 是内容审查输入，不拥有 PLAYER、MEMORY、EVENT 或 COMBAT 状态。

## 6. 正常流程

1. 玩家以普通居民身份进入王冠溪镇，先通过可见日程、劳动和公共空间理解当前生活状态。
2. 探索或交谈暴露一个有来源的需求、秘密线索、资源问题或关系矛盾。
3. 玩家选择帮助、协商、交易、调查、回避或依法治理；居民可接受、拒绝或另寻方案。
4. 后端按 owner 规则提交结果，居民形成各自主观记忆，世界设施、关系或事件进入可观察的新状态。
5. 次日或后续季节以排班、价格、对话语气、公共公告、伤病或环境变化反馈后果。
6. 平静期让玩家恢复资源、修复关系并观察居民自行生活，避免危机成为唯一内容。

## 7. 边界情况

- 玩家长期不介入时，居民仍可通过注册 Action 推进日常和部分事件，事件也可失败或转入 `Aftermath`。
- 玩家同时具有私人关系与镇长职权时，公共决定必须走制度权限，不能把私交直接转换为强制命令。
- 模型生成“命定英雄”“所有人无条件信任玩家”等文本时，只按角色言论处理，不改变 Canon 或关系。
- 玩家反复伤害后道歉时，道歉可成为新事件，但不自动消除恐惧、债务、法律责任或承诺违约。

## 8. 错误与降级

DeepSeek 不可用时，Utility AI 只维持安全、饮食、休息、工作和撤离等注册行动；现有关系、法律、事件和后果继续有效。内容资产缺失时可使用中性 fallback 文案，但不得新增 lore。出现相互冲突的叙事输出时，以 `DOC-WORLD-011` 的 Canon 优先级裁决并拒绝提交冲突事实。

## 9. 安全与性能

玩家输入与模型文本按纯文本处理，不能借角色扮演绕过权限或内容边界。体验评估使用事件 ID 和聚合指标，不记录原始 Chain of Thought 或未授权秘密。平静期也采用计划与事件调度，禁止为制造“活着”而每 Tick 生成模型文本。

## 10. 验收标准

- 固定场景中可观察到居民在无玩家命令时完成至少一项日常目标。
- 同一冲突同时提供居民行动、社交回应、探索线索或合法治理中的至少两条解决路径。
- 镇长尝试读取私人记忆或强制关系时被拒绝，世界状态无副作用。
- 正式居民失败后至少保留一种有成本且可恢复的长期状态。
- 连续七个游戏日包含明确平静时段，重大危机不持续无间断占用体验。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-001` | `REQ-WORLD-001`, `RULE-WORLD-001` | Browser E2E 覆盖五类体验，并验证同类行动由相同 owner 规则结算 |
| `TEST-WORLD-002` | `REQ-WORLD-002`, `RULE-WORLD-002` | Simulation 中玩家不介入，居民仍推进且所有结果可追到已提交事件 |
| `TEST-WORLD-003` | `REQ-WORLD-003`, `RULE-WORLD-003..004` | 七日体验审计包含日常、风险、Aftermath 与受拒绝的越权治理 |

## 12. 关联文档

- `DOC-WORLD-002`：把体验支柱落实为核心玩法循环
- `DOC-WORLD-010`：黑暗内容与长期后果边界
- `DOC-WORLD-011`：Canon 冲突裁决
- `DOC-PLAYER-001..012`：玩家身份、输入和治理权限的下游细化
- `DOC-EVENT-001..012`：事件生命周期与叙事压力的下游细化

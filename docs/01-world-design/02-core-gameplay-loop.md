---
doc_id: DOC-WORLD-002
title: 核心玩法循环
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - core-gameplay-loop
  - exploration-conversation-relationship-event-loop
  - world-feedback-cadence
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-004
  - DOC-WORLD-001
requirements:
  - REQ-WORLD-004
  - REQ-WORLD-005
  - REQ-WORLD-006
last_updated: 2026-07-26
---

# 核心玩法循环

## 1. 目的

定义可实现、可重复且支持居民自主性的“观察与探索 → 交谈与理解 → 行动与协作 → 关系与世界反馈 → 新机会”循环，并说明居民模式和镇长模式如何共享同一世界状态。

## 2. 非目标

本文件不定义 Action Catalog Schema、Quest 状态机、对话轮次、价格公式、战斗回合或时间调度算法；它只规定体验级循环和跨域交接条件。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 观察入口 | 环境变化、居民行为、公告、传闻或直接请求形成的可感知机会 |
| 主观线索 | 某角色相信或转述的信息，不保证等同客观事实 |
| 介入 | 玩家通过注册 Action、`PlayerSpeechCommand` 或合法治理 Command 影响局势 |
| 反馈窗口 | 行动后立即、当日结束或后续日期中呈现结果的时间点 |
| 恢复段 | 危机或高投入行动后用于治疗、补给、修复和关系处理的低压力阶段 |
| 模式切换 | `Tab` 仅改变可用命令集合与 UI 视角，不创建第二份世界状态 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-004` | 每个可持续玩法循环必须至少经过探索、交流、行动、反馈四阶段，且允许从任一反馈形成新入口。 |
| `REQ-WORLD-005` | 关键问题必须允许玩家不接受 Quest 也能调查、协商、交易、援助、撤离或保持旁观中的合理选项。 |
| `REQ-WORLD-006` | 循环必须支持即时、日级和季节级反馈，并为受伤、被俘、债务或关系破裂提供恢复路径。 |
| `RULE-WORLD-005` | Quest 是结构化承诺与目标的可选载体，不是所有世界互动的前置条件。 |
| `RULE-WORLD-006` | 主观线索进入玩家日志时必须保留来源与已知可信度，不能自动升级为客观 Canon。 |
| `RULE-WORLD-007` | 居民/镇长模式切换不暂停或重置世界后果；只有明确的管理输入流程按 Foundation 规则暂停 Overworld。 |
| `RULE-WORLD-008` | 任何循环阶段都不得要求 AI 创建未注册 Action、Spell、Quest Objective 或 Event Template。 |

## 5. 数据与接口

`DES-WORLD-002`：世界层发布 `GameplayOpportunity` 语义合约，供 EVENT、DIALOGUE、PLAYER 和 AI owner 映射，不作为运行时第二权威：

| 字段 | 说明 |
|---|---|
| `opportunity_id` | Stable Catalog ID 或运行时 ULID |
| `source_type` | `environment`, `resident`, `notice`, `rumor`, `aftermath` |
| `source_entity_id` | 信息来源；未知来源必须显式为 `unknown_source` |
| `knowledge_status` | `observed_fact`, `reported_belief`, `inference` |
| `available_approach_tags` | `explore`, `talk`, `trade`, `assist`, `govern`, `wait` 的非穷举提示 |
| `feedback_horizons` | `immediate`, `end_of_day`, `later_date` |
| `expires_at_game_time` | 可为空；有期限时使用 GameTime 整数分钟 |

实际行动合法性由各 owner 在最新 Revision 重新校验。

## 6. 正常流程

1. **观察与探索**：玩家在三个区域、独立室内、公告或居民日程中发现机会。
2. **交谈与理解**：玩家询问相关居民；响应受距离、语言、关系、秘密权限和居民所知限制。
3. **选择立场**：玩家可承诺帮助、交换资源、调查证据、依法治理、拒绝或暂缓。
4. **执行行动**：玩家与居民分别提交 `PlayerCommand` 或 `ActionProposal`，由 owner 校验资源、路径、权限和 Revision。
5. **即时反馈**：动作、对话、伤害、交易或环境结果以已提交 Event 呈现。
6. **日级反馈**：排班、库存、关系、承诺和公共舆论在当日或次日反映变化。
7. **长期反馈**：节庆、派系张力、建筑、疾病、债务和地区安全在后续日期改变新的机会。
8. **恢复或再投入**：玩家补给、治疗、修复关系，也可转向另一条居民自主推进的线索。

## 7. 边界情况

- 机会过期时，已完成的客观行动仍保留；未完成 Quest 进入 owner 定义的 Failed/Expired，不回滚历史。
- 玩家掌握真相但居民不知情时，居民不会据此行动，除非通过可观察事件或有效交流获知。
- 玩家切换镇长模式处理同一问题时，治理命令仍受预算、证据、管辖权和冲突回避约束。
- 居民先于玩家解决机会时，玩家看到结果与 Aftermath，而不是等待玩家触发。
- 路径暂不可达时，可转为等待、请求协助或重新规划，不能瞬移完成。

## 8. 错误与降级

模型故障时，已有机会不丢失；Utility AI 只选择安全且已注册的维生、撤离、工作和等待动作。某一反馈视图缺失时，后端权威状态保持不变，并在重新连接后按 Revision 补发。无法确认线索来源时必须标为 inference 或 reported belief，禁止补写“真相”。

## 9. 安全与性能

机会摘要只包含玩家或 actor 有权限读取的信息。模型队列压力不能阻塞 World Tick；非紧急对话与机会摘要可延迟，危险撤离和已承诺 deadline 优先。循环指标记录 stable ID、阶段和耗时，不记录敏感对话全文。

## 10. 验收标准

- 一条森林资源短缺场景可从观察推进到至少两种合法介入，并在次日产生不同反馈。
- 玩家拒绝接受 Quest 后，仍可自由交易、探索或旁观，世界继续推进。
- 居民抢先解决、机会过期、路径阻断和模型不可用四种情况下均有确定状态。
- 模式切换前后的 Revision、居民关系、Inventory 和事件状态一致。
- 失败后可找到至少一条付出时间、资源、声誉或协商成本的恢复路径。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-004` | `REQ-WORLD-004`, `RULE-WORLD-005` | E2E 完整走通四阶段且不以接受 Quest 为必要条件 |
| `TEST-WORLD-005` | `REQ-WORLD-005`, `RULE-WORLD-006..008` | 同一机会验证多路径、来源标记和注册内容约束 |
| `TEST-WORLD-006` | `REQ-WORLD-006`, `RULE-WORLD-007` | Simulation 验证三种反馈周期、恢复成本与模式切换连续性 |

## 12. 关联文档

- `DOC-WORLD-001`：体验支柱与玩家中心性边界
- `DOC-WORLD-004`：循环发生的三个区域
- `DOC-WORLD-008`：治理、调查和社会行为的合法边界
- `DOC-DIALOGUE-001..012`：对话流程的下游实现
- `DOC-EVENT-001..012`：机会、Quest 与 WorldEvent 的下游实现

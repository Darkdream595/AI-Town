---
doc_id: DOC-WORLD-012
title: 世界设计验收
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - world-design-acceptance
  - world-domain-traceability
  - lore-acceptance-scenarios
depends_on:
  - DOC-FOUNDATION-007
  - DOC-WORLD-001
  - DOC-WORLD-002
  - DOC-WORLD-003
  - DOC-WORLD-004
  - DOC-WORLD-005
  - DOC-WORLD-006
  - DOC-WORLD-007
  - DOC-WORLD-008
  - DOC-WORLD-009
  - DOC-WORLD-010
  - DOC-WORLD-011
requirements:
  - REQ-WORLD-040
  - REQ-WORLD-041
  - REQ-WORLD-042
  - REQ-WORLD-043
last_updated: 2026-07-26
---

# 世界设计验收

## 1. 目的

定义 `DOC-WORLD-001..012` 的结构、内容、一致性、可实现性与追踪验收，使 MAP、RENDER、RESIDENT、AI、MEMORY、TIME、PLAYER、DIALOGUE、ECON、MAGIC、COMBAT、EVENT、BACKEND 和 RELEASE 能消费同一套 approved 世界约束。

## 2. 非目标

本文件不宣称 188 份 corpus 已完成，不替代下游 domain 测试、浏览器 Visual QA 或发布验收，也不修改 Foundation 索引状态。WORLD 文档通过只表示当前 domain 内容可进入后续文档生产。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 结构验收 | 文件数、路径、YAML、十二节、围栏和 whitespace 满足 corpus 规则 |
| 内容验收 | 产品、lore、区域、文化、组织、历法、法律、风格和边界均具体且已定稿 |
| 一致性验收 | 稳定 ID、术语、日期、地区数量、权限和默认值无冲突 |
| 可实现性验收 | 每个 Must 有明确数据、流程、边界、错误和可重复测试 |
| Lore Scenario | 组合多个文档约束、以输入—步骤—断言验证世界语义的审计场景 |
| Red Flag | 临时开发文本、未知 ID、范围扩张、永久居民死亡、直接模仿或 owner 竞争 |
| WORLD Gate | WORLD 12 份文档全部通过本文件检查的 domain 级门槛，不等于 G3/G4/G5 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-040` | `docs/01-world-design` 必须恰好包含索引指定的 12 个文件，每份 YAML 和十二节结构完整。 |
| `REQ-WORLD-041` | 世界验收必须覆盖三地区、多族群聚落、组织权限、Calendar、法律、视觉、暗黑边界与 Canon 组合场景。 |
| `REQ-WORLD-042` | `REQ-WORLD-001..043` 每项必须有 canonical DOC、至少一个 `DES-WORLD-*`/`RULE-WORLD-*` 支撑和 `TEST-WORLD-*` 覆盖。 |
| `REQ-WORLD-043` | WORLD Gate 必须实现零重复定义 ID、零悬空 WORLD 引用、零临时开发文本和零范围外可玩 Region。 |
| `RULE-WORLD-053` | 机器审计与人工 Scenario 审查必须同时通过，不能互相替代。 |
| `RULE-WORLD-054` | 测试失败时 WORLD Gate 保持失败，修正文档后必须重新运行完整审计。 |
| `RULE-WORLD-055` | 验收只读取 Foundation、System Design 与 `docs/01-world-design` 明确路径，不扩大扫描受保护目录。 |
| `RULE-WORLD-056` | 下游发现 WORLD 约束不可实现时必须回到 WORLD owner 修订并更新追踪，不建立竞争 workaround。 |

## 5. 数据与接口

`DES-WORLD-012`：每个 `WorldAcceptanceCase` 包含：

| 字段 | 约束 |
|---|---|
| `case_id` | Stable Catalog ID，namespace 为 `acceptance.world` |
| `source_doc_ids` | 至少一个 `DOC-WORLD-*` |
| `requirement_ids` | 非空，全部为已定义 `REQ-WORLD-*` |
| `preconditions` | 明确世界年、Region、角色知识和 Revision |
| `steps` | 可由审计、Contract、Simulation 或 E2E 重复执行 |
| `assertions` | 同时包含成功与禁止副作用 |
| `evidence` | 命令输出、事件 ID、截图或审计报告引用 |
| `result` | `passed` 或 `failed`，不允许 `unknown` 通过 Gate |

## 6. 正常流程

1. 按依赖顺序读取 Foundation 与 WORLD 12 份文档。
2. 运行文件路径、YAML key/order/value、十二节、围栏和 whitespace 审计。
3. 提取 DOC/REQ/DES/RULE/TEST ID，检查 prefix、定义唯一性、引用和覆盖。
4. 检查 Canon 命名、王冠历 487 年、三个 Region、组织与法律层级的默认值一致。
5. 执行第 10 节 Lore Scenario，记录输入、步骤、断言和证据。
6. 检查下游接口都有唯一 owner，且 WORLD 未越权定义数值/Schema 实现。
7. 任何失败先修正文档，再从步骤 2 重跑；全部通过才标记 WORLD Gate passed。

## 7. 边界情况

- Markdown 中提到禁止事项不等于实现该事项；red-flag 审计必须结合 `禁止/拒绝/不得` 语境复核。
- 同一 Test 支撑多个 Requirement 时必须逐项列边，不能用范围行掩盖缺口。
- 下游文档尚未存在时，关联 `DOC-<DOMAIN>-001..012` 可作为 Foundation 已保留范围引用，不算悬空。
- deliberate ambiguity 只在 `DOC-WORLD-011` 标记并保留多解释，不算内容缺口。
- 工具不可用时可替换为确定性 PowerShell 审计，但不得省略检查项。

## 8. 错误与降级

审计脚本错误、编码失败或输出截断时，结果视为失败并以更小范围重新运行，不能从部分输出推断通过。发现重复 ID、YAML 错序、围栏不平衡、范围扩张或 Canon 冲突时，阻止提交。视觉 Scenario 暂无正式资产时只可验收 Brief 的可测试性，不能宣称最终 Visual QA 通过。

## 9. 安全与性能

审计命令只列举明确 corpus 路径，不递归仓库根目录。报告不包含 Secret、Prompt 原文或用户文件。ID、YAML 和结构检查应为线性时间；Scenario 采用固定 Seed 和 `FakeModelProvider`，真实模型不作为 WORLD Gate 前置。

## 10. 验收标准

以下 Lore Scenario 全部满足才通过：

1. **普通清晨**：正式居民在镇区独立工作、交谈和补给，玩家不是必然触发点。
2. **三地区往返**：镇区分别连接森林与矿洞，无森林—矿洞直达和新增 Region。
3. **盟誓争议**：采集收益与再生边界产生可协商双方，事实、Belief 和法律分层。
4. **矿洞失败**：正式居民遭致命数值后进入重伤或被俘，保留身份并付出恢复成本。
5. **镇长越权**：读取私人记忆、没收财产和强制关系均被拒绝且无副作用。
6. **多重身份**：不同 ancestry/culture/faith 组合不自动改变职业、善恶、语言或法律责任。
7. **节庆危机**：固定 Festival 因灾害延期，原计划和新日期均有事件记录。
8. **禁术与急救**：危险法术被拒绝；紧急治疗记录同意例外但不泄露 Secret。
9. **模型离线**：Utility AI 维持安全生活，不发明 lore、Action 或法律结果。
10. **生成冲突**：关于王冠历、地区数、永久死亡或特定作品模仿的冲突内容被拒绝。
11. **七日余波**：重大危机后存在治疗、修复、赔偿或关系处理，并包含平静时段。
12. **存档一致性**：重载不改变 Seed、当前 Canon Catalog、GameTime、历史事件或后果状态。

## 11. 测试追踪

| 测试 ID | 覆盖范围 | 断言 |
|---|---|---|
| `TEST-WORLD-040` | `REQ-WORLD-040`, `RULE-WORLD-053..055` | 12 文件、YAML、十二节、围栏、whitespace 全通过 |
| `TEST-WORLD-041` | `REQ-WORLD-001..013`, `REQ-WORLD-041` | 玩家体验、循环、历史与三地区 Scenario 通过 |
| `TEST-WORLD-042` | `REQ-WORLD-014..027`, `REQ-WORLD-041` | 身份、组织、Calendar 与法律 Scenario 通过 |
| `TEST-WORLD-043` | `REQ-WORLD-028..035`, `REQ-WORLD-041` | 视觉 Brief、内容边界、非永久后果 Scenario 通过 |
| `TEST-WORLD-044` | `REQ-WORLD-036..039`, `REQ-WORLD-043` | Canon、命名、生成内容与变更流程审计通过 |
| `TEST-WORLD-045` | `REQ-WORLD-042`, `RULE-WORLD-056` | 43/43 Requirement 均有 DOC/Design/Rule/Test 边 |
| `TEST-WORLD-046` | `REQ-WORLD-043` | WORLD ID 唯一、引用解析、临时文本与范围扫描零失败 |

按 canonical document 汇总：`DOC-WORLD-001..011` 分别定义 `REQ-WORLD-001..039`，本文件定义 `REQ-WORLD-040..043`；详细测试边由各文档第 11 节与本节共同组成。

## 12. 关联文档

- `DOC-FOUNDATION-007`：全局 traceability policy 与 WORLD ID range
- `DOC-FOUNDATION-008`：12 个 WORLD 文件的路径基线
- `DOC-WORLD-001..011`：本 Gate 的内容输入
- `DOC-MAP-001..012`：首个直接消费 WORLD Region 合约的下游 domain
- `DOC-RELEASE-011..012`：全 corpus 测试和最终发布验收

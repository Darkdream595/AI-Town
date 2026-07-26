---
doc_id: DOC-WORLD-011
title: Canon 与内容一致性
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - world-canon-governance
  - lore-precedence
  - world-naming-registry
  - generated-content-consistency
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-007
  - DOC-WORLD-001
  - DOC-WORLD-003
  - DOC-WORLD-004
  - DOC-WORLD-005
  - DOC-WORLD-006
  - DOC-WORLD-007
  - DOC-WORLD-008
  - DOC-WORLD-009
  - DOC-WORLD-010
requirements:
  - REQ-WORLD-036
  - REQ-WORLD-037
  - REQ-WORLD-038
  - REQ-WORLD-039
last_updated: 2026-07-26
---

# Canon 与内容一致性

## 1. 目的

定义世界 Canon 的权威优先级、命名注册、客观事实/争议信念分离、生成内容校验和变更流程，确保下游 14 个 domain 使用同一 lore、地区、法律和内容边界。

## 2. 非目标

本文件不取代 Foundation 的全局 Canonical Owner、ID grammar 或跨域不变量，不把所有运行时事件预写成静态 lore，也不要求居民拥有全知视角。模型生成的对话、传闻和装饰细节不是 Canon 变更机制。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Canon | 由唯一 owner 在 approved 文档/Catalog 中定义的稳定世界事实与约束 |
| Canon Entry | 带 stable ID、owner、版本、状态和允许变体的机器可读条目 |
| Runtime Objective Fact | 在特定 world/timeline 由已提交 `DomainEvent` 形成的事实 |
| Deliberate Ambiguity | Canon 明确保留多种解释、尚无客观结论的主题 |
| Generated Detail | 不改变规则、历史、地区或身份边界的局部描述 |
| Naming Registry | 中文显示名、English stable ID 和允许简称的一一映射 |
| Canon Conflict | 内容同时断言两个不可兼容事实，或由非 owner 改写 canonical topic |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-036` | 世界内容必须遵循 Foundation > WORLD canonical document/Catalog > runtime committed fact > in-world record/Belief > generated expression 的优先级。 |
| `REQ-WORLD-037` | 所有地区、政体、组织、族裔、文化、月份、节庆和历史事件必须使用 Naming Registry 的 stable ID。 |
| `REQ-WORLD-038` | 模型与内容工具只能生成允许变体或角色主观表达，不能新增 Canon、第四可玩 Region、未登记核心历史或法律豁免。 |
| `REQ-WORLD-039` | Canon 变更必须由 WORLD owner 评估依赖、分配/保留 stable ID、提升版本并更新追踪与迁移说明。 |
| `RULE-WORLD-047` | 下游文档可细化实现，不能为同一 canonical topic 建立竞争定义或不同默认值。 |
| `RULE-WORLD-048` | Runtime Objective Fact 可以改变某个 world 的建筑、关系和事件结果，但不能改变跨 world 的 Canon Catalog。 |
| `RULE-WORLD-049` | Belief、Memory、传闻、宗教解释和宣传必须携带来源/主体，不能写入 objective Canon 字段。 |
| `RULE-WORLD-050` | Stable ID 语义发布后不复用；弃用项保留 `retired` 记录和替代 ID。 |
| `RULE-WORLD-051` | 未知 ID、禁止项、日期矛盾和命名冲突在内容进入 Prompt/事件/资产 Manifest 前拒绝。 |
| `RULE-WORLD-052` | 正文和 Catalog 不允许开发待办标记、临时命名或无 owner 的悬案。 |

## 5. 数据与接口

`DES-WORLD-011`：`CanonEntry` 包含 `canon_id`, `topic`, `value`, `source_doc_id`, `owner_domain`, `version`, `status`, `allowed_variation`, `forbidden_claims`。`status` 仅可为 `canonical`, `deliberately_ambiguous`, `retired`。

核心 Naming Registry：

| 中文显示名 | Stable ID | 允许简称 |
|---|---|---|
| 王冠溪镇 | `region.crown_creek_town` | 镇区、王冠溪 |
| 暮语森林 | `region.twilight_whisper_forest` | 暮语林 |
| 银烬矿洞 | `region.silver_ash_mine` | 银烬矿 |
| 洛文王国 | `polity.rowen_kingdom` | 王国（上下文唯一时） |
| 王冠历 | `calendar.crown` | 无 |
| 星织潮 | `phenomenon.starweave_tide` | 星织 |
| 灰脉灾变 | `history.greyvein_disaster` | 灰脉事故（非礼仪语境） |
| 重开宪章 | `charter.crown_creek_reopening` | 宪章 |

其他条目从 DOC-WORLD-004..010 的 Catalog 生成，不复制第二份可写值。

## 6. 正常流程

1. 内容作者/工具用 canonical topic 查询 Naming Registry 与 owner 文档。
2. 组装内容时只引用 stable ID，并标明是 Canon、Runtime Fact、Belief 还是 Generated Detail。
3. Canon linter 检查 ID、日期、地区数量、法律、非永久死亡、内容强度和禁止模仿。
4. 运行时上下文构造器再按角色知识与 Secret ACL 过滤。
5. 模型输出经 Schema、Canon 和 owner 规则校验；合法表达可提交，冲突表达只作为明确的角色错误 Belief 或直接拒绝。
6. 需要改变 Canon 时走 owner 变更评审、影响分析、版本升级、追踪和迁移，不在运行时隐式学习。

## 7. 边界情况

- 角色撒谎说存在第四个入口时，可作为带来源的 false Belief；不得创建 Region 或出口。
- 新世界 Seed 可改变装饰性名字、非关键家庭细节和传闻路径，但不得改变 Naming Registry 核心条目。
- Runtime 中建筑被毁不会把其 Catalog Definition 标记删除，只改变该 timeline 的 Building 状态。
- 两份旧内容使用不同简称时，upcaster 映射到唯一 stable ID；无法无损映射则停止加载。
- deliberate ambiguity 得到确证前，任何一方解释都不能被 Prompt 摘要为唯一真相。

## 8. 错误与降级

Canon 冲突返回 `WORLD_CANON_CONFLICT`，包含冲突 topic、source ID 和脱敏 reason code，不自动选模型最新文本。Registry 不可用时停止新生成内容并使用已缓存 approved 版本；不能以自由文本降级。旧内容迁移失败时保留原文件并阻止该内容包加载。

## 9. 安全与性能

Canon Registry 构建为版本化不可变索引，按 stable ID O(1) 查询。错误报告不包含私人 Secret 或完整 Prompt。内容检查限定已登记 corpus、Catalog 和资产 Manifest 路径，禁止扩大到受保护或无关目录。

## 10. 验收标准

- 核心 Naming Registry 无重复中文主名、Stable ID 或竞争 owner。
- 生成内容对地区数、当前年份、法律、身份和非永久死亡的冲突均被拒绝。
- 同一事件的 objective fact、居民 Belief 与对话表达可分层保存且互不覆盖。
- Seed 变体和旧内容 upcast 不改变核心 Canon。
- Canon 变更样例能生成完整影响列表、版本、迁移与测试更新。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-036` | `REQ-WORLD-036`, `RULE-WORLD-047..049` | 多层事实优先级与 owner 竞争检测 |
| `TEST-WORLD-037` | `REQ-WORLD-037`, `RULE-WORLD-050` | Naming Registry 唯一性与 retired ID 测试 |
| `TEST-WORLD-038` | `REQ-WORLD-038`, `RULE-WORLD-051..052` | 生成内容 red-team 与临时开发文本 lint |
| `TEST-WORLD-039` | `REQ-WORLD-039` | Canon change dry-run 检查版本、影响、迁移与追踪 |

## 12. 关联文档

- `DOC-FOUNDATION-003`：Canonical Owner 与依赖方向
- `DOC-FOUNDATION-007`：Requirement/Design/Test 全局追踪
- `DOC-WORLD-003`：历史 Canon 与 deliberate ambiguity
- `DOC-WORLD-004`：三个可玩 Region Catalog
- `DOC-WORLD-012`：世界文档全量验收与追踪

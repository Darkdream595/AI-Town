---
doc_id: DOC-WORLD-003
title: 世界起源与历史
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - world-origin
  - historical-eras
  - current-world-year
  - crown-creek-settlement-rationale
depends_on:
  - DOC-FOUNDATION-001
  - DOC-WORLD-001
requirements:
  - REQ-WORLD-007
  - REQ-WORLD-008
  - REQ-WORLD-009
last_updated: 2026-07-26
---

# 世界起源与历史

## 1. 目的

确立世界起源、历史年代、当前年份及王冠溪镇成为多族群魔法边境聚落的原因，为地理、文化、组织、宗教、事件和居民背景提供唯一历史骨架。

## 2. 非目标

本文件不证明创世传说在形而上意义上的真假，不定义具体法术机制、王国全部疆域、完整君主谱系或三个区域之外的可玩空间。不同群体可以保留解释差异，但不得改写已登记的历史事实。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 星织潮 | 可被观测、周期波动的环境魔力现象；其终极来源未知 |
| 银烬坠落 | 纪元前 312 年发生的天体碎片坠落及地下魔晶形成事件 |
| 溪林盟誓 | 王冠历 9 年由王国拓殖者与暮语森林守林社群缔结的土地与取用条约 |
| 灰脉灾变 | 王冠历 461 年银烬矿洞深层坍塌与魔力污染事故 |
| 重开宪章 | 王冠历 479 年允许王冠溪镇自治管理、接纳迁入者并有限重开矿业的王室文书 |
| 当前年代 | 王冠历 487 年，重开宪章实施第九年 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-007` | 所有首版世界内容必须以王冠历 487 年为当前年份，并使用本文件历史年代。 |
| `REQ-WORLD-008` | 王冠溪镇的多族群共居必须由交通、资源、灾后迁入、盟誓义务和自治宪章共同解释。 |
| `REQ-WORLD-009` | 起源与历史必须留下可调查的不确定性，但客观登记事件、日期和现存文书不得由模型临时改写。 |
| `RULE-WORLD-009` | 银烬坠落、溪林盟誓、灰脉灾变和重开宪章是 objective historical fact；对动机、神意和责任的说法可以是 Belief。 |
| `RULE-WORLD-010` | 星织潮解释环境魔力的普遍存在，不授予任何角色绕过 `SpellDefinition` 的能力。 |
| `RULE-WORLD-011` | 灰脉灾变的伤亡与失踪制造创伤和派系分歧，但不得把正式居民写入既定永久死亡结局。 |
| `RULE-WORLD-012` | 新生成背景必须落入既有年代与迁徙渠道；不得新增改变世界格局的未登记帝国、神战或第四可玩区域。 |

## 5. 数据与接口

`DES-WORLD-003`：历史登记表使用 `HistoricalRecord`：

| 字段 | 说明 |
|---|---|
| `record_id` | 已注册的 `history.*` Stable Catalog ID，不允许仅在示例中出现 |
| `start_game_year` / `end_game_year` | 王冠历整数年；纪元前使用负数 |
| `fact_summary` | 可对玩家公开的客观摘要 |
| `evidence_ids` | 宪章、遗迹、矿务记录等 stable ID |
| `interpretation_tags` | 允许存在争议的解释主题 |
| `knowledge_access` | `public`, `community`, `faction` 等访问级别 |
| `affected_region_ids` | 只能引用已登记地区或更广泛非可玩背景地名 |

Approved Historical Fact Catalog 固定为：

| `record_id` | 年份/区间 | objective fact | 主要证据 |
|---|---:|---|---|
| `history.starweave_first_observations` | 纪元前 900 年以前 | 多个族群已记录星织潮与季节、矿物、灵体反应相关 | 跨文化季候记录与遗迹刻痕 |
| `history.silver_ash_fall` | 纪元前 312 年 | 天体碎片坠入河谷，随后形成银灰矿脉与异常植被 | `evidence.site.silver_ash_crater` |
| `history.crown_northroad_established` | 王冠历 1–88 年 | 洛文王国建立北境道路、河关与持续行政联系 | `evidence.archive.northroad_ledger` |
| `history.creek_forest_oath` | 王冠历 9 年 | 王国拓殖者与暮语森林守林社群签署土地与取用盟誓 | `evidence.document.creek_forest_oath_copy` |
| `history.trade_flourishing` | 王冠历 89–418 年 | 河运、矿业、草药和手工业推动聚落扩大 | `evidence.archive.crown_creek_trade_rolls` |
| `history.border_war_disruption` | 王冠历 419–478 年 | 边境战争持续扰动商路并推动难民迁入 | `evidence.archive.refugee_and_toll_rolls` |
| `history.greyvein_disaster` | 王冠历 461 年 | 银烬矿洞深层坍塌并发生魔力污染，矿洞随后封闭 | `evidence.archive.greyvein_mine_roll` |
| `history.reopening_charter` | 王冠历 479 年 | 王室授予有限自治、跨族群定居与有条件复矿权 | `evidence.document.reopening_charter_seal` |
| `history.mine_safety_reopening` | 王冠历 479–487 年 | 矿洞只在支护、许可和封锁分区下逐步恢复作业 | `evidence.archive.silver_ash_safety_inspections` |

上述九项是本版本全部 approved historical facts。年代摘要只能引用这些 `record_id`；新事实必须先新增 `HistoricalRecord` 并经 `DOC-WORLD-011` Registry/linter 审核，不能留在叙述正文中成为无 ID 事实。

历史事实进入 `DecisionContext` 前仍按角色知识与 Secret ACL 过滤。

## 6. 正常流程

| 年代 Stable ID | 中文名 | 时间 | 引用的 Approved Historical Fact | 当前遗产 |
|---|---|---:|---|---|
| `history.era.starweave_awakening` | 星织初醒 | 纪元前 900 年以前 | `history.starweave_first_observations` | 多种起源解释并存 |
| `history.era.silver_ash` | 银烬时代 | 纪元前 312–1 年 | `history.silver_ash_fall` | 矿洞、魔晶、森林禁忌的物质基础 |
| `history.era.crown_expansion` | 王冠开拓 | 王冠历 1–88 年 | `history.crown_northroad_established`, `history.creek_forest_oath` | 镇区管辖权与森林取用边界 |
| `history.era.trade_flourishing` | 商路繁盛 | 王冠历 89–418 年 | `history.trade_flourishing` | 行会、混合语言与多族群街区形成 |
| `history.era.ember_unrest` | 余烬动荡 | 王冠历 419–478 年 | `history.border_war_disruption`, `history.greyvein_disaster` | 难民迁入、失业、旧债与责任争议 |
| `history.era.reconstruction` | 重建年代 | 王冠历 479–至今 | `history.reopening_charter`, `history.mine_safety_reopening` | 当前的机会、紧张和治理负担 |

王冠溪镇存在的现实原因是河渡与旧王道交汇、森林提供可再生资源、矿洞提供稀缺矿石与魔晶、宪章允许跨族群定居，且溪林盟誓要求镇方共同维护边界和灾害响应。

## 7. 边界情况

- 居民可以错误记忆灰脉灾变责任方，但 Objective Fact Read Model 仍保留档案状态。
- 新世界 Seed 可改变非 canonical 的小型家族细节、传闻传播和装饰性遗迹分布，不能改变年份与关键事件。
- 玩家发现新证据时，可改变 `known/contested/corroborated` 状态，不直接覆写既有事件。
- “纪元前”日期只用于文档和 lore 排序；运行时 GameTime 仍使用 Foundation 定义的整数分钟。

## 8. 错误与降级

若内容请求引用未登记关键战争、王室或创世事实，Canon 校验返回 `WORLD_CANON_CONFLICT` 并保留原状态。缺少史料资产时显示“记录缺页”的既定表现，不自动生成事实。时间换算失败时拒绝加载该条历史内容，不把 RealTime 或 UTC 当作王冠历。

## 9. 安全与性能

历史登记构建为按 `record_id` 和年份索引的不可变 Catalog，不在每次对话扫描全文。派系秘密仍受 ACL 保护；历史争议不得用现实民族、宗教或仇恨符号进行一一映射。模型只接收当前 actor 可知的摘要和证据引用。

## 10. 验收标准

- 所有首版日期可换算并明确落在王冠历 487 年的相对时间。
- 三个区域、九项 Approved Historical Fact 和六个年代 Stable ID 能形成无矛盾因果链。
- 至少三个群体对灰脉灾变拥有不同解释，但共享同一事故日期与封矿事实。
- 随机世界初始化一百次均不改变关键事件、当前年份或区域数量。
- 未登记的“第四大陆入口”或改变格局的神战提案被 Canon 校验拒绝。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-007` | `REQ-WORLD-007`, `RULE-WORLD-009` | Catalog 测试核对九个 `history.*` fact ID、六个 `history.era.*` ID、日期和当前年；任何正文历史断言都必须反向解析到一个 Approved Historical Fact |
| `TEST-WORLD-008` | `REQ-WORLD-008`, `RULE-WORLD-010..011` | Lore 审计证明聚落成因完整且不产生越权魔法/永久死亡 |
| `TEST-WORLD-009` | `REQ-WORLD-009`, `RULE-WORLD-012` | Seed property test 保持 Canon，冲突生成内容被拒绝 |

## 12. 关联文档

- `DOC-WORLD-004`：关键历史在三个区域的地理落点
- `DOC-WORLD-005`：迁徙与多族群文化
- `DOC-WORLD-006`：宪章、机构和派系利益
- `DOC-WORLD-007`：王冠历与起源解释
- `DOC-WORLD-011`：历史事实、争议和 Canon 治理

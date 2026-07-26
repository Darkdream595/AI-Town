---
doc_id: DOC-WORLD-007
title: 宗教、历法与节庆
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - crown-calendar
  - faith-traditions
  - canonical-festivals
depends_on:
  - DOC-FOUNDATION-006
  - DOC-WORLD-003
  - DOC-WORLD-005
  - DOC-WORLD-006
requirements:
  - REQ-WORLD-021
  - REQ-WORLD-022
  - REQ-WORLD-023
last_updated: 2026-07-26
---

# 宗教、历法与节庆

## 1. 目的

定义王冠历的可计算结构、首版信仰传统和固定节庆，使 TIME、EVENT、DIALOGUE、RENDER 与镇长治理能够使用同一日期、礼仪语义和信仰边界。

## 2. 非目标

本文件不定义 GameTime Tick 算法、天气概率、神术数值、节庆 EventTemplate Schema 或角色信仰字段。它不裁定神灵是否客观存在，也不允许宗教身份替代已登记 `SpellDefinition`、法律许可或医疗同意。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 王冠历 | 现行民用历法；当前为 487 年 |
| 常月 | 每年十二个月，每月三十日 |
| 换岁五日 | 十二月后、下一年前的五个周外日，总年长 365 日 |
| 六日周 | 河日、炉日、市日、林日、灯日、息日的连续公共节奏 |
| 七灯传统 | 以炉火、道路、慈护、记忆、技艺、守望、黎明七种象征实践共同体责任 |
| 溪林盟誓传统 | 以地方灵性、取用承诺、再生记录与见证仪式维系人地关系 |
| 信仰解释 | 角色或团体对事件意义的 Belief，不自动成为 objective fact |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-021` | Calendar Catalog 必须定义 12×30 个常月日加 5 个换岁日，当前日期年份固定为王冠历 487 年。 |
| `REQ-WORLD-022` | 七灯传统与溪林盟誓传统必须可共存、可兼信或不信，不赋予强制宗教身份。 |
| `REQ-WORLD-023` | 五个 canonical festival 必须拥有固定日期、公共活动、准备需求和在危机下的延期/缩减规则。 |
| `RULE-WORLD-027` | 换岁五日不属于任何月份或六日周；日期格式必须显式区分 `month_day` 与 `yearturn_day`。 |
| `RULE-WORLD-028` | 信仰叙述不能证明某角色获得法术、赦免法律责任或拥有客观全知。 |
| `RULE-WORLD-029` | 节庆参与自愿；镇长可配置预算、公共设施和安全方案，但不能强制礼拜。 |
| `RULE-WORLD-030` | 节庆因灾害缩减或延期时，原计划、决定和新日期都以事件记录，不静默改日历。 |

## 5. 数据与接口

`DES-WORLD-007`：Calendar Catalog 如下；TIME owner 负责从 `GameInstant` 做确定性换算。

| 序号 | Stable ID | 中文月名 | 季节 |
|---:|---|---|---|
| 1 | `month.thaw` | 融霜月 | 春 |
| 2 | `month.bud` | 新芽月 | 春 |
| 3 | `month.highwater` | 溪涨月 | 春 |
| 4 | `month.longsun` | 长阳月 | 夏 |
| 5 | `month.beesong` | 蜂歌月 | 夏 |
| 6 | `month.thundergrain` | 雷穗月 | 夏 |
| 7 | `month.goldleaf` | 金叶月 | 秋 |
| 8 | `month.greyharvest` | 灰收月 | 秋 |
| 9 | `month.hearth` | 炉火月 | 秋 |
| 10 | `month.firstsnow` | 初雪月 | 冬 |
| 11 | `month.longnight` | 长夜月 | 冬 |
| 12 | `month.ember` | 余烬月 | 冬 |

换岁五日依次为归账、守灯、续誓、同桌、迎曦。六日周 Stable ID 依次为 `weekday.river`, `weekday.forge`, `weekday.market`, `weekday.grove`, `weekday.lantern`, `weekday.rest`。

## 6. 正常流程

| Festival ID | 日期 | 核心活动 | 准备/资源 |
|---|---|---|---|
| `festival.river_opening_market` | 融霜月 6 日 | 清理河桥、开春集市、商路登记 | 守卫值勤、摊位许可、食物 |
| `festival.oath_renewal` | 长阳月 1 日 | 镇方与守誓会公开复核采集边界 | 路标、档案、见证人 |
| `festival.silver_ash_vigil` | 灰收月 15 日 | 为灰脉灾变守灯、读取已确认姓名 | 灯油、安静时段、互助募捐 |
| `festival.hearth_return` | 炉火月 1 日 | 收成共享、修具、冬季互助排班 | 食材、燃料、工具 |
| `festival.yearturn_table` | 换岁第 4 日 | 跨组织同桌、公开感谢与新年承诺 | 公共预算、座席、无障碍餐食 |

日常礼仪由居民自愿执行；重大 Festival 由 EVENT owner 建立准备、Active、Aftermath 状态，镇务议会只处理公共部分。

## 7. 边界情况

- 节庆与重大危机重叠时优先安全，可缩减、延期或转为救助活动，但不可删除历史计划。
- 不同信仰对同一节庆可赋予不同意义；公共公告采用中性目的说明。
- 居民可以拒绝参加守灯夜、改变信仰或同时遵循两种传统，不产生默认关系惩罚。
- 读取旧存档时 Calendar 版本必须保持原有年/月/日，不以现实日期推进。
- 换岁日上的 deadline 必须使用 `yearturn_day`，不能伪装为第十三月。

## 8. 错误与降级

非法月份、31 日、换岁第 6 日或周字段出现在换岁日时，Calendar 校验拒绝写入。节庆资产或模型文本缺失时，保留日期、活动节点和资源事务，使用中性公告降级。宗教文本试图授予未登记法术或法律豁免时返回 `WORLD_FAITH_AUTHORITY_CONFLICT`。

## 9. 安全与性能

Calendar 换算必须是纯函数并缓存年度边界；不得每 Tick 扫描文档。信仰字段属于个人信息，只向有权上下文披露必要摘要。节庆人群规模和音画效果由性能 owner 降级，但事务、参与自愿和安全路径不变。

## 10. 验收标准

- 任意王冠历 487 年日期可在 GameInstant 与 365 日历结构间无损往返。
- 十二个月、五个换岁日、六日周和五个 Festival ID 均唯一。
- 两种信仰、兼信与无信仰角色都能参加公共节庆或选择退出。
- Festival 冲突、延期、资源不足和模型不可用均产生确定状态。
- 信仰叙述不能绕过 Spell、法律或 Secret 权限。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-021` | `REQ-WORLD-021`, `RULE-WORLD-027` | Calendar Property Test 覆盖全年边界与换岁日 |
| `TEST-WORLD-022` | `REQ-WORLD-022`, `RULE-WORLD-028..029` | 角色组合与权限 Scenario Test |
| `TEST-WORLD-023` | `REQ-WORLD-023`, `RULE-WORLD-030` | Festival Catalog/生命周期 Contract Test |

## 12. 关联文档

- `DOC-WORLD-003`：王冠历 487 年与历史事件
- `DOC-WORLD-006`：信仰团体和镇务机构
- `DOC-WORLD-008`：宗教自由、公共秩序与节庆许可
- `DOC-TIME-001`：GameTime 与 Calendar 换算的下游实现
- `DOC-EVENT-001..012`：Festival 生命周期、预算和环境影响

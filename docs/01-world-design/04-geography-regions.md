---
doc_id: DOC-WORLD-004
title: 地理与区域
version: 1.0.0
status: approved-for-implementation
owner_domain: world
canonical_for:
  - playable-region-identities
  - world-geography
  - region-resource-roles
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-006
  - DOC-WORLD-003
requirements:
  - REQ-WORLD-010
  - REQ-WORLD-011
  - REQ-WORLD-012
  - REQ-WORLD-013
last_updated: 2026-07-26
---

# 地理与区域

## 1. 目的

定义首版仅有的三个可玩 Region——王冠溪镇、暮语森林、银烬矿洞——的身份、尺度、资源角色、危险层次与叙事用途，为 MAP、RENDER、ECON、EVENT 和居民日程提供稳定语义。

## 2. 非目标

本文件不定义精确 Walkability、Collision Polygon、导航网格、摄像机边界或美术像素；这些由 MAP 与 RENDER owner 负责。王国首都、远方村庄、古战场和海外地名只能作为非可玩背景，不能获得 Region Scene、Semantic Exit 或首版可达路径。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Region | 拥有独立 `scene_id`、World Coordinate 与模拟状态的室外可玩空间 |
| Interior Scene | 依附某一 Region、通过成对 Semantic Exit 进入的独立局部场景，不计为第四 Region |
| 地区身份 | 该 Region 的视觉、资源、社会用途、危险与声音组合 |
| 关键通路 | 初始化、建造和灾害状态下都必须保留的到达安全点、出口和公共服务路径 |
| 安全核心 | 默认无随机敌对 Encounter、适合日常活动的语义范围 |
| 风险边缘 | 可触发天气、野兽、坍塌或魔力异常的已登记范围 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-WORLD-010` | 首版可玩 Region 必须且只能是 `region.crown_creek_town`、`region.twilight_whisper_forest`、`region.silver_ash_mine`。 |
| `REQ-WORLD-011` | 三个 Region 必须形成“镇区服务与生产—森林可再生资源—矿洞有限资源与危险”的互补链。 |
| `REQ-WORLD-012` | Region 转场只能通过 MAP owner 定义的成对 Semantic Exit，目标必须具有合法 arrival point。 |
| `REQ-WORLD-013` | 每个 Region 必须同时定义安全核心、风险边缘、公共/工作语义节点和天气或事件钩子。 |
| `RULE-WORLD-013` | 王冠溪镇是唯一 Hub；暮语森林与银烬矿洞分别只与镇区直接连接，首版无森林—矿洞直达通路。 |
| `RULE-WORLD-014` | 独立室内属于父 Region；室内 Scene 不得被宣传、统计或初始化为新增可玩 Region。 |
| `RULE-WORLD-015` | 可拆建筑不得画入 `Ground Art`，其占地、Collision、入口和导航变化由结构化层表达。 |
| `RULE-WORLD-016` | 地区 lore 只声明身份与语义，不从视觉颜色、阴影或装饰推断规则通行性。 |
| `RULE-WORLD-017` | 银烬矿洞深层封锁线之外只作为不可达背景；首版不能通过隐藏出口扩展可玩范围。 |

## 5. 数据与接口

`DES-WORLD-004`：发布三条只读 `RegionIdentity`：

| Stable ID | 基准尺寸 | 角色 | 安全核心 | 风险边缘 |
|---|---:|---|---|---|
| `region.crown_creek_town` | `4096 × 4096 wu` | 居住、治理、交易、制作与社交 Hub | 王冠广场、溪桥街、公共井、诊疗屋周边 | 河岸涨水带、旧墙缺口、夜间仓区 |
| `region.twilight_whisper_forest` | `4096 × 4096 wu` | 草药、木材、食材、灵性遗迹与调查 | 守誓营地、南径休息点 | 雾谷、风倒木带、盟誓禁采圈外沿 |
| `region.silver_ash_mine` | `3072 × 3072 wu` | 矿石、魔晶、石料、工业风险与灾变证据 | 入矿棚、第一升降台、已支护主巷 | 渗水支巷、魔晶脉、深层封锁门前 |

固定直接转场对为镇区北林门 ↔ 森林南径、镇区西矿道 ↔ 矿洞东侧入矿棚；具体 node ID、坐标与 Transform 由 MAP owner 发布。

## 6. 正常流程

1. 玩家在王冠溪镇获取服务、线索、许可和补给。
2. 经北林门进入暮语森林，采集可再生资源、履行盟誓义务或调查环境异常。
3. 返回镇区加工、交易、治疗或交流信息。
4. 经西矿道进入银烬矿洞，在安全分区工作，并根据装备、许可和事件状态接近风险边缘。
5. 资源、伤病、见闻和事件结果回流镇区，改变库存、关系、公共决策与后续探索。

三个 Region 的环境节奏分别为镇区的钟声与人声、森林的风叶与远鸟、矿洞的滴水与支架回响；音频实现归 RENDER。

## 7. 边界情况

- 出口目标因建筑或灾害不可站立时，转场必须拒绝或路由到同一 Region 内已登记的备用 arrival node，不能落在 Collision。
- 洪水、风倒木或坍塌可暂时提高路径成本或封锁支路，但不能同时切断所有关键通路。
- 玩家位于 Interior Scene 时，其父 Region 仍用于天气、管辖与 Warm/Active 归属；坐标不能直接比较。
- 深层矿门开启事件只能改变已登记矿洞 Scene 内的可达范围，不创建新 Region。
- 背景商队抵达可以通过镇区入口事件表达，不要求实现其出发地。

## 8. 错误与降级

未知 Region ID、未配对出口、无合法 arrival point 或错误尺寸版本导致内容加载失败，不猜测替代位置。地图视觉资产缺失时可使用登记的 fallback，但 RegionIdentity 与结构化通行规则不变。天气效果不可用时保留规则状态并降级表现。

## 9. 安全与性能

Region Catalog 在构建期验证恰好三条、ID 唯一、尺寸有限。Active/Warm/Background 性能策略由 TIME owner 决定，不能因降级跳过地区法律、资源守恒或 Collision。地图生成输入不得包含角色、文字、标签、UI 或可拆建筑。

## 10. 验收标准

- Catalog 恰好解析出三个可玩 Region，名称、Stable ID 和尺寸与本文件一致。
- 镇区可分别到达森林和矿洞，且不存在森林到矿洞的直接 Semantic Exit。
- 每个 Region 至少有一个安全核心、一个风险边缘、一个工作节点类别和一个事件钩子。
- 所有 Interior Scene 具有父 Region 与成对出口，统计仍为三个 Region。
- 动态建筑、灾害和备用入口组合下关键通路均可验证。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-WORLD-010` | `REQ-WORLD-010`, `RULE-WORLD-013..014` | Catalog/拓扑测试恰好三 Region，Interior 不计数 |
| `TEST-WORLD-011` | `REQ-WORLD-011`, `RULE-WORLD-015..016` | 资源链与五层地图责任审计 |
| `TEST-WORLD-012` | `REQ-WORLD-012`, `RULE-WORLD-017` | Semantic Exit Contract Test，无直达或隐藏第四区 |
| `TEST-WORLD-013` | `REQ-WORLD-013` | 三地区语义覆盖和关键通路 Property Test |

## 12. 关联文档

- `DOC-WORLD-003`：地区形成的历史原因
- `DOC-WORLD-008`：三个地区中的管辖与行为边界
- `DOC-MAP-001..012`：坐标、拓扑、出口、Collision 和导航的下游 canonical 设计
- `DOC-RENDER-001..012`：地区视觉与音频实现
- `DOC-EVENT-006`：天气与环境事件的下游实现

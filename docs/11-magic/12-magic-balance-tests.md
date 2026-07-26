---
doc_id: DOC-MAGIC-012
title: 魔法平衡与测试
version: 1.0.0
status: approved-for-implementation
owner_domain: magic
canonical_for:
  - magic-balance-envelopes
  - magic-test-matrix
depends_on:
  - DOC-MAGIC-003
  - DOC-MAGIC-004
  - DOC-MAGIC-005
  - DOC-MAGIC-009
  - DOC-FOUNDATION-007
requirements:
  - REQ-MAGIC-023
  - REQ-MAGIC-024
last_updated: 2026-07-26
---

# 魔法平衡与测试

## 1. 目的

定义魔法系统的平衡包络（消耗/恢复/治疗/经济影响的数值边界）、强制性反例测试（以非法传送为代表）与跨域集成测试矩阵，并提供 `docs/11-magic` 语料的机械审计口径，使"注册制、无自由文本改动世界"可被持续验证。

## 2. 非目标

本文件不修改任何前序文档的规则，只固化验证口径与数值包络；不定义战斗平衡（`DOC-COMBAT-012`）或经济平衡（`DOC-ECON-012`），仅约束魔法对二者的输入边界。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| 平衡包络 | 首版数值必须落入的闭区间集合，越界即构建期失败 |
| 反例测试 | 断言"被禁止的事必然被拒绝"的注入测试 |
| 集成 fixture | 跨 MAGIC 与至少一个他域 owner 的端到端脚本化场景 |
| 语料审计 | 对本目录 12 份文档结构与 ID 连续性的可执行检查 |

## 4. 规则与不变量

| ID | 规则 |
|---|---|
| `REQ-MAGIC-023` | 平衡包络为构建期硬校验：`mana_cost 5..60`、`charges_max 1..20`、恢复周期增量 `0..9`（`base_regen=3` × tide 上限 1.5 × 休息倍率 2）、单目标法术治疗每游戏日累计不超过其 `hp_max` 的 50%（超出部分结算为 0 并记录）、每施法者每游戏日 `instant` 自主施法软预算 8 次、每 Scene 活动效果实例上限 32、活动锚点上限 2。 |
| `REQ-MAGIC-024` | 传送禁令是永久反例测试对象：在 Schema、Registry、提案校验、效果 handler 四层分别注入传送语义（瞬移坐标、跨 Scene 位移效果、`teleport` 命名），四层必须全部拒绝（`RULE-MAGIC-006`）。 |
| `RULE-MAGIC-064` | 魔法对经济的物质影响只允许三条注册通道：法器充能（消耗 Mana 产生使用价值）、`reinforce_structure` 减缓维护成本、治疗替代药水需求；任何效果 handler 不得产出 Item、货币或原材料（`RULE-MAGIC-058`）。 |
| `RULE-MAGIC-065` | 治疗日累计上限按 `(target_id, game_day)` 维度由 MAGIC 结算侧记账，与 COMBAT 战斗内治疗分账；两账合并审计不得超过 RESIDENT 的 HP 恢复不变量。 |
| `RULE-MAGIC-066` | 平衡参数（包络常量、预算、阈值）集中在版本化 `magic.balance.v1` 配置 Catalog；调整走文档版本变更，运行时不可热改，存档内历史结算不受新参数追溯。 |
| `RULE-MAGIC-067` | 1/7/30 游戏日模拟必须包含魔法活动抽样：施法频率、Mana 收支、效果实例存量、治疗量分布均落在包络内，越界即模拟测试失败。 |
| `RULE-MAGIC-068` | 本目录语料审计（§5.2）纳入 repository lint：文档结构、ID 连续性、JSON 可解析性与未完成标记检查任一失败阻断合入。 |

## 5. 数据与接口

### 5.1 测试矩阵

`DES-MAGIC-012`：`TEST-MAGIC-001..030` 全量矩阵：

| 范围 | 测试 ID | 类型 |
|---|---|---|
| 世界观/学派 | `TEST-MAGIC-001..004` | Catalog 审计、仲裁 fixture |
| Mana | `TEST-MAGIC-005..006` | 公式 Table Test、状态机 |
| SpellDefinition | `TEST-MAGIC-007..009` | Contract、封闭性审计、目标矩阵 |
| 施法合法性 | `TEST-MAGIC-010..012` | 七级短路、法律 Table、Encounter 切换 |
| 学习成长 | `TEST-MAGIC-013..014` | 端到端、幂等对账 |
| 自主施法 | `TEST-MAGIC-015..016` | 候选过滤、目击统计 |
| 玩家施法 | `TEST-MAGIC-017..018` | 等价性、反馈映射 |
| 环境交互 | `TEST-MAGIC-019..021` | 注册表闭合、路由集成、真值不变性 |
| 魔法物品 | `TEST-MAGIC-022..023` | 守恒、合法性等价 |
| 表现 | `TEST-MAGIC-024..025` | 映射闭合、降级链 |
| 平衡与反例 | `TEST-MAGIC-026..030` | 本文件 §11 |

### 5.2 语料机械审计

```powershell
$ErrorActionPreference='Stop'
$files=Get-ChildItem -File 'docs\11-magic\*.md' | Sort-Object Name
if($files.Count -ne 12){throw 'file count'}
$raw=@($files | ForEach-Object {Get-Content -Raw -Encoding utf8 $_.FullName})
$ids=@($raw | ForEach-Object {[regex]::Match($_,'(?m)^doc_id:\s*(DOC-MAGIC-\d{3})$').Groups[1].Value})
$expected=@(1..12 | ForEach-Object {'DOC-MAGIC-{0:D3}' -f $_})
if((Compare-Object $ids $expected).Count){throw 'doc id sequence'}
$all=$raw -join "`n"
$rules=@([regex]::Matches($all,'`(RULE-MAGIC-\d{3})`') | ForEach-Object {$_.Groups[1].Value} | Sort-Object -Unique)
if($rules.Count -ne 68){throw 'rule continuity'}
$placeholder='(?i)\b('+'TO'+'DO|T'+'BD|FIX'+'ME)\b'
if($all -match $placeholder){throw 'placeholder'}
foreach($t in $raw){foreach($m in [regex]::Matches($t,'(?s)```json\r?\n(.*?)```')){$null=$m.Groups[1].Value|ConvertFrom-Json}}
'MAGIC_CORPUS_OK'
```

## 6. 正常流程

1. 每次修改 `docs/11-magic` 或魔法 Catalog：先跑 §5.2 语料审计与构建期包络校验。
2. CI 执行 `TEST-MAGIC-001..025` 单元/契约层，再执行 §11 平衡与集成层。
3. 1/7/30 日模拟按 `RULE-MAGIC-067` 采样并出包络报告。
4. 包络调整走 `magic.balance.v1` 版本变更 + 本文件同步更新。

## 7. 边界情况

- 包络参数与法术定义冲突（如新法术 `mana_cost=70`）：构建期失败优先于任何运行时行为，不允许"先上线后调参"。
- 治疗日上限跨日边界：以 `periodic.calendar.day_boundary`（`RULE-TIME-046`）为日切，跨午夜的 ritual 治疗按提交时刻归日。
- 模拟中出现零施法世界（无施法者配置）：魔法抽样断言按"无活动"通过，不误报。
- 旧存档在包络收紧后：历史事件不重判（`RULE-MAGIC-066`），仅新提交受新包络。

## 8. 错误与降级

平衡越界属于构建/测试失败，不是运行时降级路径；运行时结算发现越界输入按 fail closed 拒绝并触发诊断。语料审计失败输出首个失败断言名，修复后全量重跑，不允许跳过单项。

## 9. 安全与性能

模拟测试使用固定 Seed 复现（`RULE-FOUNDATION-026`），报告只含统计与 entity ID，不含对话或 Secret 内容。语料审计为纯本地文件操作，无网络调用；30 日模拟的魔法抽样按日聚合，避免全事件扫描。

## 10. 验收标准

- 四层传送反例全部拒绝且无状态变化（`REQ-MAGIC-024`）。
- 全部包络常量有构建期校验点与越界反例。
- `TEST-MAGIC-001..030` 无缺号、全部可执行且通过。
- 30 游戏日模拟的 Mana 收支、治疗量、效果实例存量、施法频率报告落在包络内。
- §5.2 审计在本目录当前版本输出 `MAGIC_CORPUS_OK`。

## 11. 测试追踪

| 测试 ID | 覆盖项 | 方法与断言 |
|---|---|---|
| `TEST-MAGIC-026` | `REQ-MAGIC-024` | 四层传送注入反例：Schema 拒绝、Registry lint 拒绝、提案 `FORBIDDEN`、handler 无位移能力静态证明 |
| `TEST-MAGIC-027` | `REQ-MAGIC-023`, `RULE-MAGIC-065..066` | 包络构建期校验矩阵；治疗日上限跨日与双账合并审计 |
| `TEST-MAGIC-028` | `RULE-MAGIC-064` | 经济守恒集成：法术活动 30 日模拟中 Item/货币总量仅经注册 source/sink 变化 |
| `TEST-MAGIC-029` | `RULE-MAGIC-067` | 1/7/30 日模拟魔法抽样与包络断言；固定 Seed 复现一致 |
| `TEST-MAGIC-030` | `RULE-MAGIC-068` | 语料审计集成到 lint 管线并对注入损坏（缺节、坏 JSON、断号）逐项报错 |

## 12. 关联文档

- `DOC-FOUNDATION-007`：需求-设计-测试追溯总规
- `DOC-MAGIC-003/004/005/009/010`：被包络约束的数值来源
- `DOC-COMBAT-012`：战斗侧测试矩阵的分账邻接
- `DOC-ECON-012`：经济平衡测试的守恒邻接
- `DOC-TIME-010`：Seed 复现与模拟基建

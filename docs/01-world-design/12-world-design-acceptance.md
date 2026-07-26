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

所有 case 使用确定性 fixture alias；测试装配时 alias 必须解析为固定 ULID，不能由当次运行随机生成。每个 case 的 evidence bundle 固定包含 `inputs.jsonl`、`committed_events.jsonl`、`before_after_state.json`、`assertions.json`，有视觉断言时另含 `visual_evidence.json`。`assertions.json.result` 只有在全部 expected state 与禁止副作用断言通过时才可写 `passed`。

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

以下 12 个 `WorldAcceptanceCase` 全部重复执行并得到 `passed` 才可通过。共同 Seed 仍在每条 case 中显式给出，防止 runner 隐式继承错误 fixture。

### 10.1 普通清晨

- `case_id`：`acceptance.world.ordinary_morning`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年融霜月 10 日 07:00；`region.crown_creek_town`；初始 Revision 100。
- Requirement edges：`REQ-WORLD-001`, `REQ-WORLD-002`, `REQ-WORLD-004`, `REQ-WORLD-006`, `REQ-WORLD-041`。
- 角色知识/前置状态：`fixture.resident.blacksmith` 知道今日修具排班，`fixture.resident.innkeeper` 知道早餐库存；Needs 合法、路径可达；玩家未提交 Command；`FakeModelProvider` 使用固定合法响应。
- 逐步输入：① 推进 GameTime 至 07:30；② 调度铁匠 `work`；③ 调度酒馆老板 `talk` 后为自己 `buy` 早餐；④ 获取 Revision 100 后增量事件。
- Expected committed event/state：至少三次成功事务分别证明 `work`、`talk`、`buy` 从提案进入 committed state；最终 Revision ≥103，居民日程/Inventory 由各 owner 正常更新。
- 明确禁止副作用：所有 causation 均不得引用 PlayerCommand；不得创建 Quest、危机、货币或物品的无来源变化。
- 证据：bundle 保存输入提案、Revision 100→最终值的 Event Envelope、两名居民 before/after 投影和 causation 断言。
- 结果：只有居民独立完成且全部禁止副作用为 false 时写 `passed`。

### 10.2 三地区往返

- `case_id`：`acceptance.world.three_region_roundtrip`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年融霜月 10 日 09:00；起点 `region.crown_creek_town`；初始 Revision 200。
- Requirement edges：`REQ-WORLD-010`, `REQ-WORLD-011`, `REQ-WORLD-012`, `REQ-WORLD-013`, `REQ-WORLD-041`。
- 角色知识/前置状态：玩家知道四个 fixture Semantic Exit：镇→林、林→镇、镇→矿、矿→镇；arrival point 均合法；Catalog 已加载三 Region、13 node semantic 和 12 hook。
- 逐步输入：① `move_to` 镇→林；② 读取森林 node/hook projection；③ 林→镇；④ 镇→矿；⑤ 读取矿洞 projection；⑥ 尝试林→矿的未登记 direct exit。
- Expected committed event/state：前四次合法转场各提交 arrival Region 与合法站立点；未登记 direct exit 返回稳定拒绝且 Revision 不增长；Region Catalog 保持三条。
- 明确禁止副作用：不得瞬移、落入 Collision、创建新 Region、创建森林—矿洞直连、丢失镇区 node/hook projection。
- 证据：bundle 保存四次合法转场 Event、一次拒绝结果、三个 Region Catalog 快照及逐 Region node/hook 集合比较。
- 结果：四条合法边和一条非法边的断言全部成立才写 `passed`。

### 10.3 盟誓争议

- `case_id`：`acceptance.world.oath_dispute`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年长阳月 1 日 08:00；`region.twilight_whisper_forest`；初始 Revision 300。
- Requirement edges：`REQ-WORLD-005`, `REQ-WORLD-008`, `REQ-WORLD-009`, `REQ-WORLD-019`, `REQ-WORLD-020`, `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-041`。
- 角色知识/前置状态：守誓者知道 `history.creek_forest_oath` 全文与禁采标记；采集者只知道公开边界；合作社代表知道订单短缺；客观状态为边界内资源尚未再生。
- 逐步输入：① 玩家观察 `node_semantic.forest.oath_boundary_marker`；② 分别询问三方；③ 提交调解提议“延期采集并由镇务采购库存”；④ 三方各自回应。
- Expected committed event/state：观察、三次 Speech Act 与被接受/拒绝的调解结果均有事件；Objective Fact 仍是“资源未再生”，各角色 Belief/立场独立记录。
- 明确禁止副作用：谣言不得覆写 HistoricalRecord；组织 Secret 不得泄露；不得按 ancestry/faith 推定立场；未接受提议不得扣资源。
- 证据：bundle 保存三份权限过滤前后摘要、Speech Act Event、Fact/Belief 分层快照和资源守恒断言。
- 结果：事实层不变且主观层可分歧、无越权披露时写 `passed`。

### 10.4 矿洞失败

- `case_id`：`acceptance.world.mine_defeat`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年灰收月 16 日 14:00；`region.silver_ash_mine`；初始 Revision 400。
- Requirement edges：`REQ-WORLD-003`, `REQ-WORLD-006`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-035`, `REQ-WORLD-041`。
- 角色知识/前置状态：`fixture.resident.miner` 位于 `node_semantic.mine.supported_work_face`，HP=1，存在合法撤退点；支护失效 hook 激活；治疗资源库存非零。
- 逐步输入：① 触发 `hook.event.mine.support_failure`；② 结算致命数值；③ 执行确定性失败转换；④ 提交治疗/撤离恢复计划。
- Expected committed event/state：矿工进入 `severe_injury` 或 `unconscious_retreat`，Resident ID 仍存在；Aftermath Active；治疗资源或 GameTime 被预留，恢复条件有 deadline。
- 明确禁止副作用：不得写 death terminal、删除/替换 Resident、免费满状态复位、创建未登记矿区或跳过资源守恒。
- 证据：bundle 保存伤害结算、失败转换、Resident before/after、Reservation 与 Aftermath Event。
- 结果：身份保留、非零恢复成本和 Aftermath 均可证时写 `passed`。

### 10.5 镇长越权

- `case_id`：`acceptance.world.mayor_overreach`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年新芽月 12 日 10:00；`region.crown_creek_town`；初始 Revision 500。
- Requirement edges：`REQ-WORLD-001`, `REQ-WORLD-017`, `REQ-WORLD-018`, `REQ-WORLD-020`, `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-041`。
- 角色知识/前置状态：玩家具有镇长身份但无 Sandbox Admin；目标居民有 personal Secret、unique Item 和中性关系；议会/守卫组织 Catalog 已加载。
- 逐步输入：① 请求读取 personal Secret；② 请求无程序没收 unique Item；③ 请求把 trust 强制设为 100；④ 查询每次 Result 与 Revision。
- Expected committed event/state：三项请求均在权限/规则边界被拒绝，返回稳定 reason code；Revision 始终为 500，原 Secret、Item owner 与关系值不变。
- 明确禁止副作用：不得生成伪造同意、后台补偿 Event、Admin audit 标记或部分写入。
- 证据：bundle 保存三个 Command/Result、同一 Revision 的 before/after 状态 Hash 与无 Event 断言。
- 结果：三项均拒绝且零状态副作用时写 `passed`。

### 10.6 多重身份

- `case_id`：`acceptance.world.multiple_identity`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年蜂歌月 8 日 11:00；`region.crown_creek_town`；初始 Revision 600。
- Requirement edges：`REQ-WORLD-014`, `REQ-WORLD-015`, `REQ-WORLD-016`, `REQ-WORLD-022`, `REQ-WORLD-025`, `REQ-WORLD-027`, `REQ-WORLD-041`。
- 角色知识/前置状态：初始化三个 fixture：同为 `ancestry.woodkin` 但文化/职业相反的两人，以及不同 ancestry 但同文化/同违法 allegation 的第三人；三者掌握 `language.crown_common`。
- 逐步输入：① 提交三名 Resident 初始化；② 触发共享炖锅习俗；③ 对同一轻微 allegation 执行法律分类；④ 比较职业、关系、语言与处分投影。
- Expected committed event/state：三名身份分别提交；共享习俗 Event 可被参与/拒绝；相同事实获得相同法律分类，个体职业/关系保持 fixture 值。
- 明确禁止副作用：不得按 ancestry 自动改变善恶、职业、trust、语言或处分；退出习俗不得自动扣资产/HP/自由。
- 证据：bundle 保存初始化 Event、identity projection diff、习俗结果与法律分类对照表。
- 结果：所有组合合法且无本质主义副作用时写 `passed`。

### 10.7 节庆危机

- `case_id`：`acceptance.world.festival_crisis`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年灰收月 15 日 16:00；`region.crown_creek_town`；初始 Revision 700。
- Requirement edges：`REQ-WORLD-006`, `REQ-WORLD-021`, `REQ-WORLD-022`, `REQ-WORLD-023`, `REQ-WORLD-029`, `REQ-WORLD-030`, `REQ-WORLD-041`。
- 角色知识/前置状态：`festival.silver_ash_vigil` 已 Scheduled 于当日 18:00；暴雨将激活 `hook.weather.town.storm_shelter`；镇长具有公共安全与节庆预算权限。
- 逐步输入：① 激活暴雨/避难 hook；② 提交缩减并延期至灰收月 16 日 18:00 的议会决定；③ 推进至新日期；④ 一名无信仰居民选择退出礼仪。
- Expected committed event/state：原 Schedule、延期决定、新 Schedule、避难开放与次日 Festival Active/Aftermath 均保留因果；退出只改变参与记录。
- 明确禁止副作用：不得静默改原日期、强制礼拜、创建第 13 月、丢失预算事务或同时激活另一重大危机。
- 证据：bundle 保存 Calendar round-trip、Festival 生命周期 Event、预算事务和退出居民状态。
- 结果：日期、事件链、自愿参与和压力预算均正确时写 `passed`。

### 10.8 禁术与急救

- `case_id`：`acceptance.world.forbidden_spell_first_aid`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年初雪月 4 日 13:00；`region.crown_creek_town`；初始 Revision 800。
- Requirement edges：`REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-026`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-034`, `REQ-WORLD-041`。
- 角色知识/前置状态：攻击性 Elemental Spell 在公共空间为 prohibited；`fixture.resident.patient` 昏迷并存在即时生命风险，无法表达同意；治疗者无权读取 personal Secret。
- 逐步输入：① 玩家提交公共空间攻击性施法；② 治疗者提交紧急 Restoration；③ 查询患者、Secret ACL 和 Revision。
- Expected committed event/state：禁术被拒绝且 Revision 不增长；急救以明确 emergency-consent-exception 提交，患者转入稳定重伤/治疗状态。
- 明确禁止副作用：禁术不得消耗/伤害目标；急救不得读取或输出 personal Secret、强制关系变化或清除长期伤情。
- 证据：bundle 保存拒绝 Result、急救 Event、患者状态 diff、Secret 出口零泄露扫描。
- 结果：一拒绝一提交且 Secret/关系无副作用时写 `passed`。

### 10.9 模型离线

- `case_id`：`acceptance.world.model_offline`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年长夜月 7 日 08:00；`region.crown_creek_town`；初始 Revision 900。
- Requirement edges：`REQ-WORLD-001`, `REQ-WORLD-002`, `REQ-WORLD-004`, `REQ-WORLD-006`, `REQ-WORLD-038`, `REQ-WORLD-041`。
- 角色知识/前置状态：两名居民分别需要进食与避险；`FakeModelProvider` 固定返回 timeout；Utility AI Catalog 只含已注册 `eat`, `rest`, `move_to`, `wait`。
- 逐步输入：① 触发两次模型请求并得到 timeout；② 达到有限重试上限；③ 运行 Utility AI；④ 推进一游戏小时。
- Expected committed event/state：模型请求记录失败/降级；居民分别提交合法进食与移动到安全点，Needs 和位置按 owner 规则更新。
- 明确禁止副作用：不得无限重试、创建新 lore/Action/Spell/法律结果、跳过路径/Inventory 校验或阻塞 World Tick。
- 证据：bundle 保存请求次数、fallback 选择、提交 Event、Tick 延迟与 Catalog diff=empty。
- 结果：有界降级维持安全且 Catalog 不变时写 `passed`。

### 10.10 生成与视觉 Canon 冲突

- `case_id`：`acceptance.world.generated_canon_conflict`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年余烬月 20 日 15:00；`region.crown_creek_town`；初始 Revision 1000。
- Requirement edges：`REQ-WORLD-007`, `REQ-WORLD-009`, `REQ-WORLD-010`, `REQ-WORLD-028`, `REQ-WORLD-029`, `REQ-WORLD-030`, `REQ-WORLD-031`, `REQ-WORLD-034`, `REQ-WORLD-036`, `REQ-WORLD-037`, `REQ-WORLD-038`, `REQ-WORLD-039`, `REQ-WORLD-041`, `REQ-WORLD-043`。
- 角色知识/前置状态：Registry 已加载 `DOC-WORLD-003..010` owner Catalog；Asset Manifest 为空；内容校验器启用 history/Region/death/content/imitation checks。
- 逐步输入：① 提交符合 palette/material/Ground Art 约束的中性 Brief；② 提交把当前年改为 488、增加第四 Region、使正式居民永久死亡并要求直接模仿具名创作者的冲突 Brief；③ 比较 Registry、Manifest 与 Revision。
- Expected committed event/state：中性 Brief 仅得到“可进入下游生产”的 validation record，不写世界状态；冲突 Brief 返回 `WORLD_CANON_CONFLICT`/内容边界拒绝；Revision 仍为 1000。
- 明确禁止副作用：不得新增 Registry/Region/history ID、Asset Manifest 项、death terminal、受保护模仿提示或自动“修正后提交”。
- 证据：bundle 保存两份输入 Hash、linter 逐项结果、Registry/Manifest before-after Hash 和零世界 Event 断言；`visual_evidence.json` 记录 Brief token 检查而非最终 Visual QA。
- 结果：合法 Brief 可移交、冲突 Brief 全拒绝且无写入时写 `passed`。

### 10.11 七日余波

- `case_id`：`acceptance.world.seven_day_aftermath`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；起始为王冠历 487 年雷穗月 3 日 06:00；`region.crown_creek_town`；初始 Revision 1100。
- Requirement edges：`REQ-WORLD-003`, `REQ-WORLD-006`, `REQ-WORLD-019`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-035`, `REQ-WORLD-041`。
- 角色知识/前置状态：一场重大危机刚进入 Resolved；一名居民重伤、一处公共设施受损、一项赔偿争议待处理；Narrative Pressure Budget 已占用。
- 逐步输入：① 进入 Aftermath；② 连续推进七游戏日；③ 执行治疗、修复、赔偿调解；④ 逐日记录重大危机数与平静时段。
- Expected committed event/state：至少一项治疗、一项修复或赔偿结果提交；重伤成本不为零；Aftermath 最终 Resolved/Archived；七日内至少一个完整平静日。
- 明确禁止副作用：不得立即清空伤病/债务/关系记忆、并发第二个重大危机、无限 Aftermath 或免费恢复资源。
- 证据：bundle 保存七日事件时间线、Pressure Budget、资源/关系 diff 与 Aftermath 状态迁移。
- 结果：长期反馈、恢复成本与平静日同时存在时写 `passed`。

### 10.12 存档一致性

- `case_id`：`acceptance.world.save_reload_consistency`
- 固定上下文：`seed_hex=0123456789abcdeffedcba9876543210`；王冠历 487 年金叶月 11 日 21:00；当前 `region.twilight_whisper_forest`；初始 Revision 1200。
- Requirement edges：`REQ-WORLD-007`, `REQ-WORLD-009`, `REQ-WORLD-021`, `REQ-WORLD-032`, `REQ-WORLD-036`, `REQ-WORLD-037`, `REQ-WORLD-039`, `REQ-WORLD-041`, `REQ-WORLD-043`。
- 角色知识/前置状态：Revision 1200 已包含 `history.creek_forest_oath` Belief、一个未完成 Aftermath、固定 GameTime、三 Region Catalog 和九个 Approved Historical Fact。
- 逐步输入：① 在 Revision 1200 创建 Snapshot 并记录 Event Log tail；② 关闭世界；③ 从 Snapshot+Event Log 重载；④ 运行 Canon/Seed/GameTime/后果状态 Hash 比较。
- Expected committed event/state：重载不创建新 DomainEvent 或 Revision；Seed、GameTime、Region/History Registry、Resident ID、Belief 来源和 Aftermath 状态逐字段相同。
- 明确禁止副作用：不得按离线 RealTime 推进、重新请求模型改写历史、生成新 Seed、丢失伤病/被俘状态或把 Belief 升级为 Fact。
- 证据：bundle 保存 Snapshot 元数据、Event tail、重载前后 canonical state Hash、字段 diff=empty 与 Revision=1200。
- 结果：所有持久字段相等且零重载副作用时写 `passed`。

## 11. 测试追踪

| 测试 ID | 具体 Requirement edges | 断言 |
|---|---|---|
| `TEST-WORLD-040` | `REQ-WORLD-040`; `RULE-WORLD-053`, `RULE-WORLD-054`, `RULE-WORLD-055` | 12 文件、YAML、十二节、围栏、whitespace 全通过 |
| `TEST-WORLD-041` | `REQ-WORLD-001`, `REQ-WORLD-002`, `REQ-WORLD-003`, `REQ-WORLD-004`, `REQ-WORLD-005`, `REQ-WORLD-006`, `REQ-WORLD-007`, `REQ-WORLD-008`, `REQ-WORLD-009`, `REQ-WORLD-010`, `REQ-WORLD-011`, `REQ-WORLD-012`, `REQ-WORLD-013`, `REQ-WORLD-041` | 玩家体验、循环、历史与三地区 case 集通过 |
| `TEST-WORLD-042` | `REQ-WORLD-014`, `REQ-WORLD-015`, `REQ-WORLD-016`, `REQ-WORLD-017`, `REQ-WORLD-018`, `REQ-WORLD-019`, `REQ-WORLD-020`, `REQ-WORLD-021`, `REQ-WORLD-022`, `REQ-WORLD-023`, `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-026`, `REQ-WORLD-027`, `REQ-WORLD-041` | 身份、组织、Calendar 与法律 case 集通过 |
| `TEST-WORLD-043` | `REQ-WORLD-028`, `REQ-WORLD-029`, `REQ-WORLD-030`, `REQ-WORLD-031`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-034`, `REQ-WORLD-035`, `REQ-WORLD-041` | 视觉 Brief、内容边界、非永久后果 case 集通过 |
| `TEST-WORLD-044` | `REQ-WORLD-036`, `REQ-WORLD-037`, `REQ-WORLD-038`, `REQ-WORLD-039`, `REQ-WORLD-043` | Canon、命名、生成内容与变更流程审计通过 |
| `TEST-WORLD-045` | `REQ-WORLD-042`, `RULE-WORLD-056` | 43/43 Requirement 均有 DOC/Design/Rule/Test 边 |
| `TEST-WORLD-046` | `REQ-WORLD-043` | WORLD ID 唯一、引用解析、临时文本与范围扫描零失败 |
| `TEST-WORLD-047` | `REQ-WORLD-001`, `REQ-WORLD-002`, `REQ-WORLD-004`, `REQ-WORLD-006`, `REQ-WORLD-041` | 执行 `acceptance.world.ordinary_morning` |
| `TEST-WORLD-048` | `REQ-WORLD-010`, `REQ-WORLD-011`, `REQ-WORLD-012`, `REQ-WORLD-013`, `REQ-WORLD-041` | 执行 `acceptance.world.three_region_roundtrip` |
| `TEST-WORLD-049` | `REQ-WORLD-005`, `REQ-WORLD-008`, `REQ-WORLD-009`, `REQ-WORLD-019`, `REQ-WORLD-020`, `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-041` | 执行 `acceptance.world.oath_dispute` |
| `TEST-WORLD-050` | `REQ-WORLD-003`, `REQ-WORLD-006`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-035`, `REQ-WORLD-041` | 执行 `acceptance.world.mine_defeat` |
| `TEST-WORLD-051` | `REQ-WORLD-001`, `REQ-WORLD-017`, `REQ-WORLD-018`, `REQ-WORLD-020`, `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-041` | 执行 `acceptance.world.mayor_overreach` |
| `TEST-WORLD-052` | `REQ-WORLD-014`, `REQ-WORLD-015`, `REQ-WORLD-016`, `REQ-WORLD-022`, `REQ-WORLD-025`, `REQ-WORLD-027`, `REQ-WORLD-041` | 执行 `acceptance.world.multiple_identity` |
| `TEST-WORLD-053` | `REQ-WORLD-006`, `REQ-WORLD-021`, `REQ-WORLD-022`, `REQ-WORLD-023`, `REQ-WORLD-029`, `REQ-WORLD-030`, `REQ-WORLD-041` | 执行 `acceptance.world.festival_crisis` |
| `TEST-WORLD-054` | `REQ-WORLD-024`, `REQ-WORLD-025`, `REQ-WORLD-026`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-034`, `REQ-WORLD-041` | 执行 `acceptance.world.forbidden_spell_first_aid` |
| `TEST-WORLD-055` | `REQ-WORLD-001`, `REQ-WORLD-002`, `REQ-WORLD-004`, `REQ-WORLD-006`, `REQ-WORLD-038`, `REQ-WORLD-041` | 执行 `acceptance.world.model_offline` |
| `TEST-WORLD-056` | `REQ-WORLD-007`, `REQ-WORLD-009`, `REQ-WORLD-010`, `REQ-WORLD-028`, `REQ-WORLD-029`, `REQ-WORLD-030`, `REQ-WORLD-031`, `REQ-WORLD-034`, `REQ-WORLD-036`, `REQ-WORLD-037`, `REQ-WORLD-038`, `REQ-WORLD-039`, `REQ-WORLD-041`, `REQ-WORLD-043` | 执行 `acceptance.world.generated_canon_conflict` |
| `TEST-WORLD-057` | `REQ-WORLD-003`, `REQ-WORLD-006`, `REQ-WORLD-019`, `REQ-WORLD-032`, `REQ-WORLD-033`, `REQ-WORLD-035`, `REQ-WORLD-041` | 执行 `acceptance.world.seven_day_aftermath` |
| `TEST-WORLD-058` | `REQ-WORLD-007`, `REQ-WORLD-009`, `REQ-WORLD-021`, `REQ-WORLD-032`, `REQ-WORLD-036`, `REQ-WORLD-037`, `REQ-WORLD-039`, `REQ-WORLD-041`, `REQ-WORLD-043` | 执行 `acceptance.world.save_reload_consistency` |

Canonical document 定义边另由各文档第 11 节逐项维护；本表不使用 Requirement 范围缩写。

## 12. 关联文档

- `DOC-FOUNDATION-007`：全局 traceability policy 与 WORLD ID range
- `DOC-FOUNDATION-008`：12 个 WORLD 文件的路径基线
- `DOC-WORLD-001..011`：本 Gate 的内容输入
- `DOC-MAP-001..012`：首个直接消费 WORLD Region 合约的下游 domain
- `DOC-RELEASE-011..012`：全 corpus 测试和最终发布验收

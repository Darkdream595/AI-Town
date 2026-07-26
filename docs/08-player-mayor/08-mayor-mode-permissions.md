---
doc_id: DOC-PLAYER-008
title: 镇长治理权限、预算与信息边界
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - mayor-command
  - mayor-governance-permissions
  - mayor-budget-boundary
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-WORLD-006
  - DOC-WORLD-008
  - DOC-TIME-002
  - DOC-ECON-001
  - DOC-ECON-006
  - DOC-ECON-011
  - DOC-PLAYER-003
requirements:
  - REQ-PLAYER-008
last_updated: 2026-07-26
---

# 镇长治理权限、预算与信息边界

## 1. 目的

`REQ-PLAYER-008`：定义 Mayor office、jurisdiction、治理命令、公共预算限制、程序保障和公开信息投影，使镇长能真实影响世界而不能侵犯私人权利或绕过守恒。

## 2. 非目标

本文不拥有法律条文、公共 Building、Appropriation/Encumbrance 数值、WorldEvent 模板或 MAP geometry；PLAYER 拥有 MayorCommand 和 authority check，各 owner 负责规则与提交。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Mayor Office | WORLD 授予特定 Resident 的 versioned 治理职位 |
| Jurisdiction | Office 可操作的 Region、公共 subject 与 policy kind 集合 |
| MayorCommand | `mayor.*` tagged union，和 PlayerCommand/AdminCommand 不相容 |
| Governance Proposal | 尚未提交的公告、税率、工资、节日、道路或灾害响应计划 |
| Public Projection | 可向镇长展示的预算/人口/事件聚合，不含私人 secret |

## 4. 规则与不变量

- `RULE-PLAYER-036`：MayorCommand 要求 `mayor_active`、active Mayor office、匹配 jurisdiction、policy capability 和最新 authority version。
- `RULE-PLAYER-037`：公共支出必须由 ECON active Appropriation + Encumbrance + public account balance 三重约束；Mayor 不能 mint、制造负余额或跳过 Transaction。
- `RULE-PLAYER-038`：镇长不能读取私人记忆、personal/shared_secret、私人 Inventory/交易明细、隐藏关系数值或未获合法披露的居民健康信息。
- `RULE-PLAYER-039`：镇长不能强制改变感情、直接没收私人财产、指定战斗胜负、set Building stage、改 Collision 或伪造 WorldEvent；必须走 consent/legal order/owner workflow。
- `RULE-PLAYER-040`：紧急治理仍须 registered emergency policy、上限、期限、reason、事后审计和 owner validator，不能成为通用 Admin 旁路。

## 5. 数据与接口

### 5.1 MayorCommand Schema

```json
{
  "protocol_version": 1,
  "command_id": "01K1CMDX000000000000000008",
  "world_id": "01K1WRDX000000000000000001",
  "expected_revision": 312,
  "type": "mayor.public_work.propose",
  "payload": {
    "office_id": "01K1FFCE000000000000000001",
    "expected_office_version": 4,
    "jurisdiction_id": "jurisdiction.crowncreek",
    "public_subject_id": "road.market.east",
    "purpose_id": "public_work.road_repair",
    "maximum_budget_copper_feather": 5000,
    "requested_completion_game_time": 10080
  }
}
```

`type` 是后端注册 union：`mayor.budget.propose`、`mayor.tax.propose`、`mayor.wage.propose`、`mayor.public_work.propose`、`mayor.notice.publish`、`mayor.festival.schedule`、`mayor.emergency.respond`、`mayor.statistics.query`。每型 strict Schema，拒绝额外字段。

### 5.2 治理能力矩阵

| 能力 | Mayor 可做 | Owner/限制 |
|---|---|---|
| 公共预算 | 提议拨款、查看公共汇总 | ECON balance + appropriation + encumbrance |
| 税率/工资 | 在法律边界内提议 | WORLD law、GameTime 生效窗、ECON |
| 公共建筑/道路 | 提议、批准授权阶段 | land right、材料、EVENT stage、MAP patch |
| 公告/节日 | 发布公开内容、排期 | EVENT template、预算、内容/频率限制 |
| 灾害响应 | 选择注册响应计划 | emergency classification、资源上限 |
| 公共统计 | 查询聚合 | k-anonymity/最小披露、无 secret |
| 私人财产/关系 | 仅依法发起程序 | consent/order；不能 direct mutation |
| 战斗/居民意志 | 无直接控制 | 不能指定目标行为或胜负 |

## 6. 正常流程

1. `Tab` 进入 Mayor，TIME 持有 `mayor_management` token。
2. Backend 生成只读 Public Projection，标注 source Revision、office/jurisdiction version 和每项更新时间。
3. 玩家编辑 Governance Proposal；Client 只提交期望、上限和注册 subject。
4. PLAYER 验证 mode/office/jurisdiction，WORLD 验证程序/法律，ECON/MAP/EVENT 验证资源和 owner state。
5. 高影响命令展示结构化确认摘要；确认后用新 command ID 和最新 Revision 提交。
6. 成功产生 Mayor audit metadata、owner DomainEvent 和公开结果；失败无部分支出/政策生效。

## 7. 边界情况

MayorCommand 按 `(world_id, command_id)` 幂等并比较 payload hash；office、appropriation、encumbrance 和 subject 都使用 expected version。两个拨款竞争额度时最多一个成功。Office 任期结束或权限撤销使所有未提交 proposal 失效、阻止新命令并触发安全退出 Mayor。已提交政策按法律 owner 规则继续，不因 UI 关闭撤销；撤销是新治理命令。

## 8. 错误与降级

public-work Saga 失败时释放 active Encumbrance，并由 EVENT/MAP 决定阶段补偿；PLAYER 不 set stage。commit 成功但 Client 断线时按 idempotency result 和 DomainEvent 恢复。

## 9. 安全与性能

每个 MayorCommand 的 decision 记录 `office_id/authority_version/jurisdiction/policy_id/result/reason/correlation`，不记录私人输入。该记录是治理审计，不是 Sandbox Admin audit，也不标记存档。Public Projection 只含聚合与公开字段，statistics 查询受 k-anonymity/最小披露约束。

## 10. 验收标准

- Mayor capability 仅在 active office + jurisdiction + mode 同时满足时有效。
- 公共支出同时受账户余额、Appropriation 和 Encumbrance 约束。
- 私人记忆/secret/Inventory/关系 raw value 无法通过统计或错误信息推断。
- 没收、强制感情、指定胜负、direct MAP/Building mutation 全部拒绝。
- 撤权、并发预算、Saga failure 和重连结果确定。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-PLAYER-029` | Mayor command union、office 与 jurisdiction |
| `TEST-PLAYER-030` | budget/appropriation/encumbrance 并发守恒 |
| `TEST-PLAYER-031` | secret/private inference 与 direct mutation 拒绝 |
| `TEST-PLAYER-032` | office revocation、public-work Saga 与幂等恢复 |

## 12. 关联文档

- `DOC-WORLD-006`：治理结构与公共预算语义
- `DOC-WORLD-008`：法律、财产权与程序保障
- `DOC-ECON-011`：Appropriation/Encumbrance canonical contract
- `DOC-PLAYER-009`：Mayor 与 Sandbox Admin 不相互包含

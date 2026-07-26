---
doc_id: DOC-RESIDENT-006
title: 职业、工作地与住所分配
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - resident-profession-reference
  - resident-residence-reference
  - assignment-lifecycle
depends_on:
  - DOC-WORLD-008
  - DOC-MAP-008
  - DOC-RESIDENT-005
requirements:
  - REQ-RESIDENT-006
last_updated: 2026-07-26
---

# 职业、工作地与住所分配

## 1. 目的

`REQ-RESIDENT-006`：定义居民职业身份、工作地成员关系、住所访问与转职/迁居状态机；ECON 拥有职业定义、工资与产出，MAP 拥有 Entrance/通行。

## 2. 非目标

不定义工资、营业、税、建筑所有权、Door permission 算法或日程执行；本域只保存经 owner 验证的 assignment 引用与居民侧状态。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Profession Assignment | ECON-issued runtime assignment ID |
| Workplace | ECON/EVENT 拥有的工作地点实体 |
| Residence Assignment | 居民与住所单元、bed semantic node 的合法绑定 |
| Assignment State | `proposed/active/suspended/ended` |
| Role Change | 原 assignment 结束、新 assignment 激活的原子流程 |

## 4. 数据与接口

`DES-RESIDENT-006`：

```json
{
  "profession": {
    "assignment_id":"01K1AB2CD3EF4GH5JK6MNP7QRA",
    "profession_id":"profession.apothecary",
    "workplace_id":"building.apothecary",
    "state":"active",
    "effective_from_game_time":480,
    "effective_until_game_time":null
  },
  "residence": {
    "assignment_id":"01K1AB2CD3EF4GH5JK6MNP7QRB",
    "building_id":"building.riverside_house_02",
    "interior_scene_id":"interior.riverside_house_02",
    "bed_node_id":"semantic_node.riverside_house_02.bed_a",
    "state":"active"
  }
}
```

`validate_assignment_refs` 由 Orchestrator 查询 ECON/EVENT/MAP；Resident 只接收验证 token 和 owner IDs。

## 5. 规则与不变量

- `RULE-RESIDENT-029`：同一 GameTime 每居民最多一个 `active` profession 与一个 `active` residence assignment。
- `RULE-RESIDENT-030`：profession 与 ancestry/culture 无硬绑定；资格只引用显式 Skill、Ability、许可或已提交成员关系。
- `RULE-RESIDENT-031`：Residence 必须有可解析 Interior、合法 Entrance 和 standable bed node；无床时只能进入显式 `temporary_shelter` assignment。
- `RULE-RESIDENT-032`：Role Change 在一个 Unit of Work 中结束旧 assignment 并激活新 assignment；失败保留旧状态。
- `RULE-RESIDENT-033`：职业暂停/结束不修改余额、Item、工资债权或工作产出；这些由 ECON Command 处理。
- `RULE-RESIDENT-034`：住所引用不等于房屋产权，不能授权打开私人容器或读取 Secret。

## 6. 正常流程

1. AI/玩家提交转职或迁居意图。
2. ECON/EVENT/MAP owner 验证资格、容量、成员关系、Entrance 和 bed node。
3. Orchestrator 建立 assignment/reservation。
4. Resident 原子切换居民侧引用并生成 `ResidentAssignmentChanged`。
5. TIME owner 后续依据新 assignment 重新排定 routine。

## 7. 边界情况

- 工作地损坏时 assignment 可 `suspended`，职业身份保留且不虚构工资。
- Residence 不可达时进入有限期临时住所，必须有 review GameTime。
- 被俘/昏迷只暂停 assignment，不自动解雇或转移产权。
- 两个居民争用一张床由 owner capacity reservation 决胜，败者不写入 assignment。

## 8. 错误与降级

返回 `RESIDENT_ASSIGNMENT_CONFLICT`、`RESIDENT_WORKPLACE_INVALID`、`RESIDENT_RESIDENCE_UNREACHABLE`、`RESIDENT_BED_CAPACITY_FULL`。owner 不可用时保持现有 assignment；紧急住所使用已登记 shelter，不随机选择私宅。

## 9. 安全与性能

住所与工作地访问由 Authority Server 验证，不接受 Client `can_enter`。对 AI 只披露公开职业和当前可进入目的地，私人地址按权限过滤。

## 10. 验收标准

- 转职成功/失败分别原子替换/保留旧 assignment。
- 工作地受损、昏迷、被俘均不会误改 ECON 状态。
- 无合法 Entrance/bed 的 residence 被拒绝。
- 职业组合与 ancestry/culture 无相关硬约束。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-021` | active assignment 唯一性 Property Test |
| `TEST-RESIDENT-022` | 转职事务回滚与幂等 |
| `TEST-RESIDENT-023` | Entrance/bed/capacity Integration Test |
| `TEST-RESIDENT-024` | suspension 不修改 ECON authority |

## 12. 关联文档

- `DOC-MAP-008`：Entrance/Interior transfer
- `DOC-RESIDENT-009`：routine 消费 assignment
- `DOC-ECON-002..003`：职业、工资、工作日程 canonical owner


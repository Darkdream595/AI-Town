---
doc_id: DOC-ECON-002
title: 职业与工作场所
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - profession-catalog
  - employment-contract
  - workplace-economic-capability
depends_on:
  - DOC-FOUNDATION-003
  - DOC-WORLD-004
  - DOC-WORLD-006
  - DOC-ECON-001
requirements:
  - REQ-ECON-002
last_updated: 2026-07-26
---

# 职业与工作场所

## 1. 目的

`REQ-ECON-002`：定义首版职业 Catalog、工作场所经济能力与 Employment Contract，使 AI 居民和玩家可在相同技能、地点、许可、工资与离职规则下工作。

## 2. 非目标

本文不拥有 Resident 身份、技能数值、健康状态、建筑状态、Semantic Node 坐标或 GameTime 调度；只保存其稳定引用与工作经济合约。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| ProfessionDefinition | 跨存档稳定的职业能力、许可和产出类型定义 |
| Workplace | 可提供岗位、服务或生产能力的 ECON aggregate，引用 Building/Location |
| EmploymentContract | 雇主、worker、岗位、工资、有效期和状态的运行时合约 |
| Shift Role | 一次排班内的具体职责，不改变 Resident 身份 |
| Player Job | `worker_resident_id` 指向玩家 ResidentId 的普通 Employment Contract |

## 4. 规则与不变量

- `RULE-ECON-005`：首版 Profession Catalog 至少包含铁匠、药剂师、酒馆老板、商人、镇卫、矿工、采集者、木匠、法师、治疗者和冒险者。
- `RULE-ECON-006`：Workplace 必须引用 WORLD 登记区域语义与 MAP 解析的 `location_semantic_node_id`；ECON 不拥有坐标、Building 生命周期或通行性。
- `RULE-ECON-007`：一个 worker 在同一 GameTime 最多有一个 `active_shift` 排他 Reservation；多份 Employment Contract 可共存，但排班不能重叠。
- `RULE-ECON-008`：玩家工作与 AI 工作使用同一 Contract、技能/许可 projection、Reservation、工资和产出规则，差异仅是 Action 来源。

## 5. 数据与接口

`DES-ECON-002`：

```json
{
  "schema_version": 1,
  "employment_contract_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "profession_id": "profession.blacksmith",
  "worker_resident_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "employer_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "workplace_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "role_id": "role.blacksmith.journeyman",
  "wage_copper_feather_per_shift": 180,
  "starts_at_game_time": 2880,
  "ends_at_game_time": null,
  "state": "active",
  "version": 3
}
```

`state` 为 `offered/active/suspended/ended/rejected`。Workplace 另含 `parent_building_id`、`location_semantic_node_id`、`position_capacity`、`service_definition_ids[]`、`required_permission_ids[]`。Resident aggregate 只持有 `employment_contract_id`/`inventory_id` 引用；TIME 只调度 Shift；AI 只提议 `work` 或合约动作。

## 6. 正常流程

1. 雇主发布含职位、工资、场所、有效期的 Offer。
2. 权威端读取 worker 的 ResidentId、技能/健康/许可只读 projection 与 Workplace 可用性。
3. worker 接受后以 `expected_revision` 创建 active Contract。
4. TIME 在班次开始请求排他 `worker_shift` 与 workplace capacity Reservation。
5. 工作完成后由 ECON 结算工资与产出；Resident 仅接收相关引用或 Needs/疲劳结果事件。
6. 转职通过结束旧 Contract、创建新 Contract 表达，不改写历史。

## 7. 边界情况

- Workplace 所属 Building 损坏或 MAP 不可达时 Contract 保留但转为 `suspended`，不能假定 worker 已到岗。
- 组织关键岗位空缺时可开放服务节点或委托，不凭空创建工资或背景正式居民。
- 同一 worker 可有非重叠兼职；冲突 Offer 可保存但不能同时激活班次。
- 法师、治疗者等职业不自动授予 Spell、治疗同意或法律豁免。
- 玩家离开岗位或暂停输入时，只结算已提交的工作进度。

## 8. 错误与降级

返回 `profession_unknown`、`workplace_unavailable`、`qualification_failed`、`permission_missing`、`shift_conflict`、`capacity_full` 或 `stale_revision`。AI 不可用时不自动签订/终止长期 Contract；已接受的安全基础岗位可由确定性调度继续。

## 9. 安全与性能

模型不能伪造技能、许可、雇主签名或工资支付。Workplace capacity 以 Reservation 强制；Catalog 在构建期校验稳定 ID 与版本，运行时按 `region_id/profession_id` 建索引，不能每 Tick 遍历全部 Contract。

## 10. 验收标准

- 十一个必需 ProfessionDefinition 全部存在且 Stable ID 唯一。
- Contract 可追踪 worker、雇主、Workplace、工资、有效期与版本。
- 玩家与 AI 对同一岗位得到相同合法性和工资结果。
- 双份重叠班次只能授予一个排他 Reservation。
- Building 损坏、位置不可达、许可撤销和转职均不产生孤立工资或丢失历史。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-005` | Profession Catalog 必需集合与唯一性 |
| `TEST-ECON-006` | Workplace location/building 引用可解析且不夺取 ownership |
| `TEST-ECON-007` | 玩家/AI job parity 与资格/许可拒绝 |
| `TEST-ECON-008` | 重叠 Contract、capacity、suspend/转职状态机 |

## 12. 关联文档

- `DOC-WORLD-004`：工作与服务 node semantic
- `DOC-WORLD-006`：组织与关键岗位边界
- `DOC-MAP-008`：入口、位置与到达条件
- `DOC-ECON-003`：排班、工资与工作结算

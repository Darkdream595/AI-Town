---
doc_id: DOC-ECON-007
title: 商店与服务
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - shop
  - shop-opening-hours
  - service-sale
depends_on:
  - DOC-WORLD-004
  - DOC-MAP-008
  - DOC-ECON-002
  - DOC-ECON-005
  - DOC-ECON-006
requirements:
  - REQ-ECON-007
last_updated: 2026-07-26
---

# 商店与服务

## 1. 目的

`REQ-ECON-007`：定义商店库存、营业时间、员工覆盖、柜台/服务节点与商品或服务交付，使买卖、治疗、修理、住宿等交易在明确可达、有人值守和有资源的条件下完成。

## 2. 非目标

本文不定义地图坐标、Door permission、治疗效果、修理数值、对话协商文本或 AI 营业决策；对应 owner 提供已提交投影，ECON 只结算服务合约。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Shop | 拥有销售 Inventory、Monetary Account、营业规则与 ServiceDefinition 的 ECON aggregate |
| Opening Interval | 以周内整数 GameTime offset 表示的半开区间 `[start,end)` |
| Staff Coverage | 至少一名具备角色/许可、已到岗且持有 Shift Reservation 的 worker |
| ServiceDefinition | 输入资源、价格、交付条件、预期时长和取消规则 |
| Service Order | 预留付款、资源、员工与服务位的 Transaction workflow |

## 4. 规则与不变量

- `RULE-ECON-025`：Shop 可接受新订单当且仅当当前 GameTime 位于 Opening Interval、状态为 `open`、Staff Coverage 满足且服务 Semantic Node 可用。
- `RULE-ECON-026`：商品 sale 必须预留销售库存与买方目标容量；服务 order 必须额外预留员工、service slot 与定义的输入资源。
- `RULE-ECON-027`：营业结束不取消已在截止前 committed 的 sale；进行中的 service 按 Definition 明确完成或退款规则处理，不能静默吞款。
- `RULE-ECON-028`：Shop price、stock、staff 与 hours 均为权威 projection；Client/AI 口头声称“开门/有货/打折”不能绕过验证。

## 5. 数据与接口

`DES-ECON-007`：

```json
{
  "schema_version": 1,
  "shop_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "shop_definition_id": "shop.apothecary.crown_creek",
  "sales_inventory_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "revenue_account_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
  "workplace_id": "01K1AB2CD3EF4GH5JK6MNP7QRW",
  "service_node_id": "node_semantic.town.clinic_service",
  "opening_intervals": [{"day_index": 1, "start_minute": 480, "end_minute": 1080}],
  "required_staff_roles": ["role.apothecary.counter"],
  "service_definition_ids": ["service.apothecary.identify", "service.apothecary.prepare"],
  "state": "open",
  "version": 4
}
```

`state` 为 `open/temporarily_closed/suspended/decommissioned`。接口：

```text
query_shop_offer(shop_id, observer_context, game_time, revision) -> LocalShopOffer
reserve_shop_order(offer_id, buyer_inventory_id, action_id, revision) -> ReservationSet
commit_shop_order(command_id, reservation_ids, revision) -> TransactionResult
```

## 6. 正常流程

1. actor 到达 MAP owner 解析的服务节点并请求本地 Offer。
2. ECON 校验 Opening Interval、Shop state、Staff Coverage、库存和权限。
3. Pricing 生成有时限 Quote；actor 可提议接受，但不能改结算 legs。
4. 系统按资源全序预留付款、库存、目标容量、员工与 service slot。
5. 商品 sale 立即原子提交；长服务创建 Service Order 并由 TIME 调度完成。
6. 完成/取消按 ServiceDefinition 产生交付或退款 Transaction 与事件。

## 7. 边界情况

- 跨午夜营业拆为两个 day interval，禁止 `start > end` 的模糊表达。
- 最后一名 staff 离岗时停止新订单；已接受服务按安全取消策略处理。
- Shop Door locked 或 MAP snapshot 未 ready 时即使 hours=open 也不能提供现场服务。
- 背景商队使用 `hook.event.town.market_arrival` 创建有界临时 Shop，不创建第四 Region。
- 玩家经营 Shop 与 AI 经营 Shop 使用同一 staff/hours/stock/Transaction 规则。

## 8. 错误与降级

返回 `shop_closed`、`staff_unavailable`、`service_node_unavailable`、`out_of_stock`、`service_capacity_full`、`quote_expired` 或 `shop_suspended`。模型不可用时 Shop 保持已提交 hours 和确定性固定 Offer；不自动改变价格或签订新服务。

## 9. 安全与性能

Observer 只获得公开 Offer，不暴露后台完整库存、员工私人状态或进货成本。按 `next_opening_boundary_game_time` 和 active order 建索引；不能逐 Tick 扫描全部 Shop。临时 Shop 有 Catalog 白名单、库存和生命周期上限。

## 10. 验收标准

- open/closed、staff present/absent、stock present/absent 与 service node ready/unready 组合均有确定结果。
- Sale 预留库存、付款和目标容量；Service 额外预留 staff/slot/input。
- 闭店边界、跨午夜、最后员工离岗和取消退款无部分交付。
- 玩家/AI 商店行为 parity。
- Offer 只包含观察者在当地合法可知信息。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-025` | Opening Interval 边界与跨午夜 |
| `TEST-ECON-026` | stock/staff/node/capacity Reservation |
| `TEST-ECON-027` | 服务完成、闭店中断、取消与退款 |
| `TEST-ECON-028` | 本地 Offer 披露与玩家/AI parity |

## 12. 关联文档

- `DOC-WORLD-004`：市场、诊疗与制作 node semantic
- `DOC-MAP-008`：到达与 Door 条件
- `DOC-ECON-003`：Staff Shift
- `DOC-ECON-008`：Quote 与有界价格

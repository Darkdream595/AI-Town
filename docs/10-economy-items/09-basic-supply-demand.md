---
doc_id: DOC-ECON-009
title: 基础供需与短缺
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - production-chain
  - demand-window
  - shortage-state
depends_on:
  - DOC-WORLD-004
  - DOC-ECON-004
  - DOC-ECON-007
  - DOC-ECON-008
requirements:
  - REQ-ECON-009
last_updated: 2026-07-26
---

# 基础供需与短缺

## 1. 目的

`REQ-ECON-009`：定义森林、矿洞与镇区生产之间的有界生产链、滚动需求窗口和短缺状态，使 1/7/30 日模拟具有可解释反馈而不会无限涨价、凭空补货或依赖全知市场。

## 2. 非目标

本文不构建宏观经济、跨国贸易、复杂拍卖或随机无限资源；EVENT 拥有天气/灾害，WORLD 拥有地区资源角色，ECON 只消费其已提交 modifier。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Production Chain | 从采集 source、Recipe、Workplace 到商品 Inventory 的注册有向图 |
| Supply Window | 指定 Shop/Region/Item 在过去 1440 GameTime 分钟的进入数量 |
| Demand Window | 同期 committed sale quantity 加合法未满足需求计数 |
| Shortage | 可售量低于 Definition 的 reorder threshold 且需求持续的状态 |
| Local Market Observation | 居民在指定 Region/Shop 实际观察到的价格、缺货或公开公告 |

## 4. 规则与不变量

- `RULE-ECON-033`：首版链必须覆盖森林的木材/草药/食材、矿洞的矿石/魔晶/石料，以及镇区工具/武器/药水/食物/魔法物品/建筑材料。
- `RULE-ECON-034`：Supply/Demand 只由已提交 Transaction、Craft、Gather 与明确 lost-demand event 更新；模型文本、购物意图和 UI 点击不计数。
- `RULE-ECON-035`：默认窗口为过去 1440 GameTime 分钟，按 60 分钟 bucket；高倍速批处理与逐分钟更新必须得到相同 bucket totals。
- `RULE-ECON-036`：Shortage 只能提高有界 pricing modifier、触发注册补货/事件候选或公开缺货；不能负库存、跳过 Recipe、凭空生成 Item 或无限累计 multiplier。

## 5. 数据与接口

`DES-ECON-009`：

```json
{
  "schema_version": 1,
  "market_key": {
    "region_id": "region.crown_creek_town",
    "shop_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
    "item_definition_id": "item.material.iron_ingot"
  },
  "window_end_game_time": 10080,
  "bucket_minutes": 60,
  "window_minutes": 1440,
  "supply_quantity": 18,
  "committed_demand_quantity": 22,
  "unmet_demand_quantity": 7,
  "available_quantity": 2,
  "reorder_threshold": 6,
  "shortage_state": "active",
  "scarcity_q1000": 1450,
  "last_revision": 321
}
```

`shortage_state` 为 `normal/watch/active/recovering`；转换使用连续两个 bucket 的阈值滞回，避免边界抖动。

## 6. 正常流程

1. Gather/Craft/Sale Transaction 提交后追加 market delta。
2. TIME 在 bucket boundary 触发 ECON 聚合，不逐 Tick 重算。
3. ECON 滚动移除过期 bucket，计算本地 supply、demand 与 available quantity。
4. 状态机按阈值与滞回更新 Shortage，并产生公开 read model。
5. Pricing 读取限幅 scarcity multiplier；AI 只获得当前居民已观察或公开的信息。
6. 补货仍通过合法 work/gather/craft/transport 行动完成。

## 7. 边界情况

- 外来商队可通过已登记 market arrival 事件带入显式 Inventory source，不隐含远方无限库存。
- 天气关闭路径时未到达货物不计 supply，已 Reservation 的在途 Item 也未进入 Shop available quantity。
- lost demand 只在合法 Offer 因 stock shortage 拒绝时记录，同一 ActionId 幂等计一次。
- `0×` 暂停时 window 不滚动；恢复不依据 RealTime 离线时间过期。
- 零需求但低库存进入 `watch` 而非 active shortage。

## 8. 错误与降级

返回 `market_key_invalid`、`bucket_out_of_order`、`delta_duplicate`、`production_chain_cycle` 或 `supply_projection_inconsistent`。聚合延迟时沿用上个 committed modifier 并标记 stale，不允许用预测值写价格；恢复 audit 失败时暂停相关市场写入。

## 9. 安全与性能

每 market key 固定 24 个小时 bucket，增量 O(1)；Production Chain 在构建期验证有向无环且节点有界。公开 observation 不含私人 Inventory、未公开订单或其他 Region 的实时隐藏库存。

## 10. 验收标准

- 必需原料与产品链均可追溯到 source、Recipe 和 Workplace。
- 1440 分钟窗口与 60 分钟 bucket 在速度倍率、暂停和恢复后结果一致。
- Shortage 状态具有滞回、modifier 上限和恢复路径。
- 无负库存、无凭空补货、无重复 lost demand。
- 未到访 Shop 的居民上下文不自动获得其隐藏库存。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-033` | 三 Region 必需生产链与 DAG |
| `TEST-ECON-034` | committed delta 与 ActionId 幂等 |
| `TEST-ECON-035` | bucket/window 在 `0×..4×`、暂停、恢复的等价性 |
| `TEST-ECON-036` | shortage 滞回、modifier 上限、本地信息边界 |

## 12. 关联文档

- `DOC-WORLD-004`：三个 Region 的资源角色
- `DOC-ECON-008`：scarcity/demand multiplier
- `DOC-ECON-010`：Recipe 与资源消费
- `DOC-ECON-012`：30 日平衡测试

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
  "signal_streak": 3,
  "scarcity_policy_id": "scarcity_policy.local_market.v1",
  "scarcity_policy_version": 1,
  "scarcity_q1000": 1496,
  "market_snapshot_hash": "sha256:30cb762b7a104a553fbcf801f248c929366b55958dfab609f012ca351ddc4c49",
  "last_revision": 321
}
```

版本化 `ScarcityPolicy` 是 `scarcity_q1000` 的唯一算法来源：

```json
{
  "policy_id": "scarcity_policy.local_market.v1",
  "policy_version": 1,
  "window_minutes": 1440,
  "bucket_minutes": 60,
  "minimum_q1000": 700,
  "maximum_q1000": 2000,
  "deficit_weight_q1000": 600,
  "unmet_demand_weight_q1000": 400,
  "surplus_relief_weight_q1000": 300,
  "hysteresis_closed_buckets": 2,
  "empty_window_fallback_q1000": 1000
}
```

所有数量输入均为 `0..2147483647` 的整数，`reorder_threshold` 为 `1..2147483647`；因此下式中间值不会溢出 int64。定义正整数除法 `qdiv(n,d)=floor((2*n+d)/(2*d))`，即精确 `round_half_up(n/d)`：

```text
deficit_q1000 = qdiv(max(reorder_threshold - available_quantity, 0) * 1000, reorder_threshold)
surplus_q1000 = min(qdiv(max(available_quantity - reorder_threshold, 0) * 1000, reorder_threshold), 1000)
demand_total = committed_demand_quantity + unmet_demand_quantity
unmet_q1000 = demand_total == 0 ? 0 : qdiv(unmet_demand_quantity * 1000, demand_total)
raw_q1000 = 1000
            + qdiv(deficit_weight_q1000 * deficit_q1000, 1000)
            + qdiv(unmet_demand_weight_q1000 * unmet_q1000, 1000)
            - qdiv(surplus_relief_weight_q1000 * surplus_q1000, 1000)
scarcity_q1000 = clamp(raw_q1000, minimum_q1000, maximum_q1000)
```

窗口为空（24 个 bucket 均无 supply、committed/unmet demand，且 available/reorder projection 暂不可用）时使用 `1000` 并标记 `neutral_empty_window`；不是任意可选值。Quote input hash 必须包含 policy ID/version、window end、24 个 bucket hash、available/reorder、committed/unmet totals 与计算结果。

Golden vectors：

```json
{
  "scarcity_golden_vectors": [
    {"available": 10, "reorder": 10, "committed": 10, "unmet": 0, "expected_q1000": 1000},
    {"available": 0, "reorder": 10, "committed": 10, "unmet": 10, "expected_q1000": 1800},
    {"available": 20, "reorder": 10, "committed": 10, "unmet": 0, "expected_q1000": 700},
    {"available": 2, "reorder": 6, "committed": 22, "unmet": 7, "expected_q1000": 1496}
  ]
}
```

`shortage_state` 为 `normal/watch/active/recovering`。闭合 bucket 的 `shortage_signal = available < reorder_threshold && demand_total > 0`，`recovery_signal = available >= reorder_threshold && unmet_demand_quantity == 0`。`normal` 首个 shortage signal 转 `watch/streak=1`；`watch` 第二个连续 signal 转 `active/streak=2`，否则回 `normal/0`；`active` 首个 recovery signal 转 `recovering/1`；`recovering` 第二个连续 recovery signal 转 `normal/0`，任一非 recovery signal 立即回 `active/0`。状态不再叠加另一个价格 multiplier，避免同一输入双重计价。

## 6. 正常流程

1. Gather/Craft/Sale Transaction 提交后追加 market delta。
2. TIME 在 bucket boundary 触发 ECON 聚合，不逐 Tick 重算。
3. ECON 滚动移除过期 bucket，计算本地 supply、demand、available quantity 与确定的 `scarcity_q1000`。
4. 状态机按两 bucket 滞回更新 Shortage，并产生含 policy/version/hash 的公开 read model。
5. Pricing 校验并读取该限幅 multiplier；AI 只获得当前居民已观察或公开的信息。
6. 补货仍通过合法 work/gather/craft/transport 行动完成。

## 7. 边界情况

- 外来商队可通过已登记 market arrival 事件带入显式 Inventory source，不隐含远方无限库存。
- 天气关闭路径时未到达货物不计 supply，已 Reservation 的在途 Item 也未进入 Shop available quantity。
- lost demand 只在合法 Offer 因 stock shortage 拒绝时记录，同一 ActionId 幂等计一次。
- `0×` 暂停时 window 不滚动；恢复不依据 RealTime 离线时间过期。
- 零需求但低库存进入 `watch` 而非 active shortage。

## 8. 错误与降级

返回 `market_key_invalid`、`bucket_out_of_order`、`delta_duplicate`、`scarcity_policy_unknown`、`scarcity_recompute_mismatch`、`production_chain_cycle` 或 `supply_projection_inconsistent`。聚合延迟时沿用上个 committed modifier 与完整 policy/snapshot hash 并标记 stale，不允许用预测值写价格；恢复 audit 失败时暂停相关市场写入。

## 9. 安全与性能

每 market key 固定 24 个小时 bucket，增量 O(1)；Production Chain 在构建期验证有向无环且节点有界。公开 observation 不含私人 Inventory、未公开订单或其他 Region 的实时隐藏库存。

## 10. 验收标准

- 必需原料与产品链均可追溯到 source、Recipe 和 Workplace。
- 1440 分钟窗口与 60 分钟 bucket 在速度倍率、暂停和恢复后结果一致。
- Shortage 状态具有精确两 bucket 滞回；四个 golden vector 可重算且 modifier 固定在 `700..2000`。
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

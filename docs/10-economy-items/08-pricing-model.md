---
doc_id: DOC-ECON-008
title: 有界定价模型
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - price-quote
  - bounded-pricing
  - economic-information-boundary
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-ECON-001
  - DOC-ECON-007
requirements:
  - REQ-ECON-008
last_updated: 2026-07-26
---

# 有界定价模型

## 1. 目的

`REQ-ECON-008`：用整数、版本化且有上下限的公式生成本地 Quote，使库存、近期需求、地区事件、利润率和合法折扣影响价格，同时不向居民泄露全世界经济信息。

## 2. 非目标

本文不模拟证券市场、竞价撮合、实时全局价格、自由文本讨价还价或由模型生成任意金额；关系本身由 MEMORY 拥有，ECON 只接收经 Orchestrator 验证的折扣 entitlement。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Base Price | Item/Service Catalog 中的正整数铜羽基准价 |
| Q1000 Multiplier | `1000=1.0` 的整数定点倍率 |
| Price Context | 固定 Revision、Shop、地区与观察者可用权益的不可变输入 |
| Quote | 有 `quote_id`、unit price、数量、到期 GameTime 与输入 hash 的非 Reservation 报价 |
| Local Information | Shop 自有库存/交易窗口、公开地区事件、已授权 entitlement；不含隐藏全局状态 |

## 4. 规则与不变量

- `RULE-ECON-029`：所有价格以 CopperFeather 整数计算；中间乘法使用有界大整数，最终 `round_half_up`，不得使用二进制浮点。
- `RULE-ECON-030`：单位价格公式为 `clamp(round_half_up(base × scarcity_q1000 × event_q1000 × margin_q1000 × discount_q1000 / 1000^4), floor, ceiling)`；`scarcity_q1000` 是 supply、committed demand 与 unmet demand 的唯一供需输入，禁止第二个 demand multiplier。
- `RULE-ECON-031`：各 multiplier 必须处于注册范围：scarcity `700..2000`、event `500..2000`、margin `1000..1600`、discount `700..1000`；`floor>=1` 且 `ceiling>=floor`。
- `RULE-ECON-032`：Quote 固定输入 Revision/hash，默认有效 10 GameTime 分钟；接受时仍重新验证库存、entitlement、税与 Reservation，不能把 Quote 当已成交事实。

## 5. 数据与接口

`DES-ECON-008`：

```json
{
  "schema_version": 1,
  "quote_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "shop_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "item_definition_id": "item.potion.healing_small",
  "quantity": 2,
  "base_unit_price_copper_feather": 100,
  "scarcity_provenance": {
    "policy_id": "scarcity_policy.local_market.v1",
    "policy_version": 1,
    "market_snapshot_hash": "sha256:30cb762b7a104a553fbcf801f248c929366b55958dfab609f012ca351ddc4c49",
    "market_snapshot_revision": 200
  },
  "multipliers_q1000": {
    "scarcity": 1200,
    "event": 1000,
    "margin": 1250,
    "discount": 900
  },
  "unit_price_copper_feather": 135,
  "floor_copper_feather": 50,
  "ceiling_copper_feather": 300,
  "observed_revision": 200,
  "expires_at_game_time": 610,
  "input_hash": "sha256:2a1b9d4f7d6e33f29d3e3d7340a7a74c8c651f366cf942a653fcfd7e9b087a6a"
}
```

Quote 使用以下 strict contract；全部 record 拒绝额外字段，因此加入 `demand` 或其他未登记 multiplier 必须 Schema 失败：

```json
{
  "strict_quote_contract_version": 1,
  "additional_properties": false,
  "quote_exact_fields": ["schema_version", "quote_id", "shop_id", "item_definition_id", "quantity", "base_unit_price_copper_feather", "scarcity_provenance", "multipliers_q1000", "unit_price_copper_feather", "floor_copper_feather", "ceiling_copper_feather", "observed_revision", "expires_at_game_time", "input_hash"],
  "scarcity_provenance_exact_fields": ["policy_id", "policy_version", "market_snapshot_hash", "market_snapshot_revision"],
  "multiplier_exact_fields": ["scarcity", "event", "margin", "discount"],
  "multiplier_ranges_q1000": {
    "scarcity": [700, 2000],
    "event": [500, 2000],
    "margin": [1000, 1600],
    "discount": [700, 1000]
  },
  "integer_ranges": {
    "quantity": [1, 9999],
    "base_unit_price_copper_feather": [1, 9223372036854775807],
    "unit_price_copper_feather": [1, 9223372036854775807],
    "floor_copper_feather": [1, 9223372036854775807],
    "ceiling_copper_feather": [1, 9223372036854775807]
  }
}
```

对正整数定义 `round_half_up(n/d)=floor((2*n+d)/(2*d))`。实现先用有界大整数计算 `numerator=base×scarcity×event×margin×discount` 与 `denominator=1000^4`，再执行一次 round 和 clamp；不得逐 multiplier 舍入。`input_hash` 必须覆盖 strict contract version、全部 Quote 字段、ScarcityPolicy ID/version 和 market snapshot hash/revision。

折扣输入是 ECON-owned `discount_entitlement={entitlement_id,band,discount_q1000,issued_revision,expires_at}`；Orchestrator 可从其他 owner 的授权投影映射，但 ECON 不 import、不存储 affection/trust 等关系维度。

## 6. 正常流程

1. 读取 Shop 本地 stock、已提交 demand window，以及 `DOC-ECON-009` 产生的 policy ID/version、market snapshot hash 与 `scarcity_q1000`，再读取公开地区 modifier 与 Catalog Base Price。
2. 读取调用者可披露的折扣 entitlement；缺失时使用 `1000`。
3. 重新计算/校验 scarcity golden formula，拒绝任何独立 demand field，逐项限幅并按单次 rounding 公式计算；input hash 覆盖 scarcity policy/version 和 market snapshot hash。
4. 返回只含本地可知因素摘要的 Quote。
5. 接受 Quote 时检查 expiry、hash、Revision-sensitive inputs 与 buyer maximum unit price，再进入 Reservation/Transaction。

## 7. 边界情况

- 公式示例的 `100×1200×1000×1250×900/1000^4=135`，`round_half_up=135`；同一 demand window 已包含在 scarcity 中，不再乘第二次。
- 库存为 0 时不因 ceiling 生成虚假 Offer，直接 `out_of_stock`。
- 公开灾害 modifier 到期后旧 Quote 可在其固定有效期内使用，但提交仍按定义的 quote policy 验证；税变更总是要求重报价。
- actor 可提交 `maximum_unit_price` 作为拒绝阈值，不能指定更低结算价。
- Background 模拟只用 actor 当时获知的 Quote/market observation，不读取最新全局未来信息。

## 8. 错误与降级

返回 `base_price_missing`、`price_multiplier_out_of_range`、`quote_schema_additional_property`、`scarcity_provenance_invalid`、`quote_expired`、`quote_input_changed`、`maximum_price_exceeded` 或 `discount_entitlement_invalid`。市场投影为空时只能采用 ScarcityPolicy 定义的 `neutral_empty_window=1000`；暂时不可用但存在历史 committed snapshot 时沿用完整 policy/hash 并标记 stale，不能另造 demand fallback。

## 9. 安全与性能

Quote 不披露商店成本、完整库存或私人关系数值。相同 input hash 的 Quote 可按 Shop/Item/observer entitlement band 短暂缓存；缓存不得跨 Revision-sensitive modifier。整数乘法先检查位宽，拒绝超大 quantity。

## 10. 验收标准

- 固定向量 `base=100, scarcity=1200, event=1000, margin=1250, discount=900` 得到 `135`，跨 Python/TypeScript fixture 一致。
- 所有 multiplier 与最终 unit price 永远在注册界限内。
- strict Quote 只接受 scarcity/event/margin/discount 四项，独立 demand 字段被拒绝且需求只由 scarcity 计入一次。
- Quote 过期、税/库存变化、entitlement 撤销与最大价限制均有拒绝路径。
- AI/玩家只能接受/拒绝或给 maximum price，不能指定结算值。
- 居民的经济上下文不包含未观察的其他 Shop 库存或未来需求。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-029` | Q1000 公式、round_half_up 与跨语言 golden vectors |
| `TEST-ECON-030` | multiplier/floor/ceiling property boundaries |
| `TEST-ECON-031` | Quote expiry/input hash/maximum price |
| `TEST-ECON-032` | local information 与 relationship entitlement boundary |

## 12. 关联文档

- `DOC-FOUNDATION-006`：整数货币
- `DOC-ECON-007`：Shop Offer
- `DOC-ECON-009`：唯一供需输入 `scarcity_q1000`
- `DOC-ECON-006`：Quote 接受后的 Transaction

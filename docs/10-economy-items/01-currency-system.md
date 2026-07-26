---
doc_id: DOC-ECON-001
title: 货币系统
version: 1.0.0
status: approved-for-implementation
owner_domain: economy
canonical_for:
  - currency-unit
  - monetary-account
  - currency-conservation
depends_on:
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
requirements:
  - REQ-ECON-001
last_updated: 2026-07-26
---

# 货币系统

## 1. 目的

`REQ-ECON-001`：以整数铜羽建立唯一权威货币模型，并保证居民、商店、组织与公共预算之间的每次余额变化可追踪、可回滚且满足守恒。

## 2. 非目标

本文不定义商品价格、工资、税率、银行借贷或 UI 排版；不支持浮点余额、第二种法定货币、加密货币或由 Client/AI 直接指定结算结果。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Copper Feather | `CopperFeather=int64`，唯一存储与计算单位，中文“铜羽” |
| Silver Crown | 仅用于显示，`1 silver_crown = 100 copper_feather`，中文“银冠” |
| Monetary Account | 由 ECON 拥有的余额账户，引用 Resident、组织、商店或公共机构 owner ID |
| Ledger Entry | 一次 Transaction 内对账户的有符号整数变化 |
| Mint/Burn | 受权限约束、显式登记的货币 source/sink；普通交易、税和费用都不是 source/sink |

## 4. 规则与不变量

- `RULE-ECON-001`：所有持久余额、价格、工资、税费和赔偿只使用整数 `copper_feather`；任何成功提交后的账户余额不得小于 0 或超出 int64。
- `RULE-ECON-002`：普通 Ledger Entry 在一个 Transaction 内代数和必须为 0；税与费用必须转入明确收款账户，不能通过少记账销毁货币。
- `RULE-ECON-003`：Mint/Burn 必须引用注册 `monetary_authority_reason_id`、权限证据与独立 DomainEvent；镇长、AI 和普通居民不能自行 mint。
- `RULE-ECON-004`：显示层可拆为银冠与铜羽，但 parse/format round-trip 必须恢复原整数，禁止四舍五入改变余额。

## 5. 数据与接口

`DES-ECON-001`：版本 1 Schema：

```json
{
  "schema_version": 1,
  "account_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "owner_entity_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "account_kind": "resident",
  "balance_copper_feather": 1234,
  "state": "open",
  "opened_game_time": 1440,
  "last_revision": 42
}
```

`account_kind` 只允许 `resident/shop/organization/public_budget/escrow/system_source/system_sink`。写接口：

```text
quote_balance(account_id, revision) -> CurrencyBalanceView
post_currency_legs(transaction_id, entries[], expected_revision) -> CurrencyPostResult
format_currency(amount_copper_feather, locale) -> DisplayAmount
```

Schema 增字段必须提升 `schema_version`；旧事件由 ECON upcaster 转换，不能猜测丢失金额。

## 6. 正常流程

1. Orchestrator 从已验证 actor/owner 解析付款与收款账户。
2. ECON 以固定 Revision 读取余额并创建 Transaction currency legs。
3. 按 `account_id` 升序锁定写集，检查权限、int64 上下界、非负余额和总和。
4. 余额、Ledger Entry、幂等结果与 DomainEvent 在一个 Unit of Work 提交。
5. 前端只根据已提交事件显示银冠/铜羽，不预测余额。

## 7. 边界情况

- 金额为 0 的业务 leg 被拒绝，避免伪造无效审计；总价为 0 的赠与使用 Item Transaction，不生成货币 leg。
- `-1`、`9223372036854775808`、JSON 浮点和科学计数值在协议边界拒绝。
- 关闭账户只能在余额为 0、无 active Reservation 且无未决 Transaction 时进行。
- 赔偿、税和服务费均是内部转账；只有注册初始化、测试夹具或受审计 Admin 恢复可产生 Mint/Burn。

## 8. 错误与降级

返回 `invalid_currency_amount`、`insufficient_funds`、`account_closed`、`currency_overflow`、`unbalanced_ledger`、`mint_permission_denied` 或 `stale_revision`。任何错误均不写余额、不产生成功事件且 Revision 不增长；显示格式化失败可退化为“`1234 铜羽`”，不影响权威值。

## 9. 安全与性能

Client、模型和价格请求只能提交最大可接受金额，不能提交可信余额或 Ledger Entry。按账户与 GameTime 分页查询，禁止每 Tick 汇总全世界账本；提交时只检查写集，总量守恒在周期与恢复审计中分片复核。

## 10. 验收标准

- `1234` 往返显示为 `12 银冠 34 铜羽` 后仍为 `1234`。
- 普通交易、税费、工资和赔偿的 Ledger Entry 总和逐事务为 0。
- 并发透支最多一个 Transaction 成功，失败者无部分扣款。
- 未授权 Mint/Burn、负余额、浮点金额和 int64 溢出均被拒绝。
- Snapshot/Event 重放后每个账户余额与 Ledger 投影一致。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-ECON-001` | CopperFeather int64 与银冠/铜羽 round-trip property |
| `TEST-ECON-002` | 普通、税费与工资 Ledger 守恒 |
| `TEST-ECON-003` | 并发透支、overflow 与 unauthorized mint 拒绝 |
| `TEST-ECON-004` | Snapshot/Event 恢复后余额重建一致 |

## 12. 关联文档

- `DOC-FOUNDATION-005`：货币守恒全局不变量
- `DOC-FOUNDATION-006`：`CopperFeather` 与 `GameInstant`
- `DOC-ECON-006`：原子 Transaction 与幂等提交
- `DOC-ECON-011`：公共预算账户

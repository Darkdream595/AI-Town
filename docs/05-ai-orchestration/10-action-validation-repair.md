---
doc_id: DOC-AI-010
title: Action 校验、修复与重规划
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - action-validation-pipeline
  - validation-outcome-taxonomy
  - bounded-proposal-repair
depends_on:
  - DOC-AI-004
  - DOC-AI-005
  - DOC-TIME-007
requirements:
  - REQ-AI-010
last_updated: 2026-07-26
---

# Action 校验、修复与重规划

## 1. 目的

`REQ-AI-010`：定义 Proposal 从协议到最新 Domain 状态的分层校验、`REPAIRABLE/REPLAN_REQUIRED/FORBIDDEN` outcome、白名单修复、审计和无副作用拒绝。

## 2. 非目标

本文不让 AI validator 替代 owner，不通过修改世界来“使提案合法”，不自动改目标/Action，不把拒绝伪装成成功。

## 3. 术语与定义

| Outcome | 含义 | 后续 |
|---|---|---|
| `VALID` | 可构造授权候选 | Reservation + latest commit check |
| `REPAIRABLE` | 不改变意图的有限形状/引用规范化可修 | 最多一次 repair |
| `REPLAN_REQUIRED` | 世界/目标/资源变化或意图不可达 | 新 Context，新 plan |
| `FORBIDDEN` | 权限、秘密、能力或安全边界越界 | 拒绝、审计，不回显隐藏事实 |
| `TRANSIENT_OWNER_UNAVAILABLE` | owner 暂不可验证 | deadline 内有限重试，否则 fallback |

## 4. 数据与接口

`DES-AI-010`：

```json
{
  "outcome_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "proposal_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "outcome": "REPLAN_REQUIRED",
  "stage": "domain_latest_state",
  "reason_codes": ["destination_unreachable", "navigation_revision_changed"],
  "observed_revision": 84,
  "validated_revision": 87,
  "repair_patch": null,
  "allowed_retry": true,
  "audit_severity": "normal",
  "outcome_version": 1
}
```

阶段固定：

```text
transport bytes
-> JSON syntax
-> DOC-AI-004 strict Schema
-> DOC-AI-005 cross-field/reference visibility
-> actor capability/permission
-> target/distance/navigation
-> resource/cooldown/quote/turn/deadline
-> Reservation plan
-> World Runtime latest commit checks
```

repair whitelist 仅允许：移除 JSON code fence、Unicode NFC、把空 `spoken_text` 归一为 null、对明确 stable enum 做大小写拒绝后的模型再输出、补回模型遗漏但 Context 中唯一且非敏感的 `quote_id=null/world_point=null`。实现不得静默插字段；repair 通过独立 `output-repair/v1` 重新生成完整 artifact，并再次走全链。

## 5. 规则与不变量

- `RULE-AI-055`：校验顺序固定，任一失败无状态、Reservation、Event 或 Revision 变化。
- `RULE-AI-056`：`REPAIRABLE` 不得改变 action、目标、数量、金额、Recipe/Spell/Combat option、权限或目的；最多一次。
- `RULE-AI-057`：stale Revision、目标消失、路径/Quote/turn/资源变化为 `REPLAN_REQUIRED`，不得对旧 Context shape repair。
- `RULE-AI-058`：Admin、未授权秘密、不可用能力、任意 action/数值结算、越权财产/伤害为 `FORBIDDEN`，不自动降级成相似动作。
- `RULE-AI-059`：只有 Domain owner 可返回 AuthorizedIntent；AI validator 不能设置 `can_enter/can_pay/hit/damage/yield/owner`。
- `RULE-AI-060`：同一 proposal validation 以 `(proposal_id, latest_revision, validator_bundle_version)` 幂等；提交仍使用独立 command ID。

## 6. 正常流程

strict decode→semantic check→按 Catalog 调 owner validators→汇总最小 reason codes→VALID 时生成 immutable AuthorizedIntent 与 lock requests→TIME 全取 Reservation→World Runtime 最新提交检查→原子事件。repair/replan 产生新的 proposal_id，并以 causation 关联旧 Proposal。

## 7. 边界情况

多个失败只返回对 actor 可见且足够的原因；例如“permission_denied”不能泄露隐藏 owner。Schema 错误和 forbidden 同时存在时先返回 Schema error，修复后仍需 forbidden 检查。提交前 Navigation revision 改变即 replan，即使路径形状看似仍可走。

## 8. 错误与降级

validator timeout 是 owner unavailable，不默认 VALID。repair provider 失败进入 fallback；连续三次同 reason replan 在 10 游戏分钟窗口内触发 loop breaker，选择 wait/observe/seek safety 而非继续耗费请求。

## 9. 安全与性能

reason payload 只含 code、field pointer、脱敏 ref hash。所有 owner validator 有界且无外网 I/O；可并行纯读检查，但最终结果按固定 stage/reason 排序。单 Proposal reason 最多 16。

## 10. 验收标准

- 每个 stage 有 VALID/negative fixture，失败零副作用。
- repair whitelist/property test 证明关键意图字段不变。
- stale/forbidden 不走 shape repair；forbidden 不泄露隐藏事实。
- VALID Proposal 仍能在 commit-time state change 下安全失败。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-037` | stage ordering/outcome matrix |
| `TEST-AI-038` | repair whitelist/intention immutability |
| `TEST-AI-039` | forbidden/no-secret/no-auto-downgrade |
| `TEST-AI-040` | commit-time race/reservation rollback/idempotency |

## 12. 关联文档

- `DOC-AI-004..005`：shape 与 owner map
- `DOC-TIME-007`：Reservation atomicity
- `DOC-AI-011`：loop/terminal fallback

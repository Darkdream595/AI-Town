---
doc_id: DOC-PLAYER-012
title: 玩家与镇长系统验收矩阵
version: 1.0.0
status: approved-for-implementation
owner_domain: player
canonical_for:
  - player-system-acceptance
  - player-mayor-fixtures
  - admin-audit-oracles
depends_on:
  - DOC-PLAYER-001
  - DOC-PLAYER-002
  - DOC-PLAYER-003
  - DOC-PLAYER-004
  - DOC-PLAYER-005
  - DOC-PLAYER-006
  - DOC-PLAYER-007
  - DOC-PLAYER-008
  - DOC-PLAYER-009
  - DOC-PLAYER-010
  - DOC-PLAYER-011
requirements:
  - REQ-PLAYER-012
last_updated: 2026-07-26
---

# 玩家与镇长系统验收矩阵

## 1. 目的

`REQ-PLAYER-012`：以可执行 fixtures、command sequences 和 machine-checkable oracles 验收玩家创建、移动、交互、自然语言、世界影响、Resident/Mayor/Admin 权限、全屏与无障碍，不以“页面能打开”替代规则证明。

## 2. 非目标

本文不替代各 owner 单元测试、全量浏览器视觉 QA、发布包新机验收或安全渗透测试；它定义 PLAYER subsystem 的集成门槛和证据格式。

## 3. 验收层级

| 层级 | Runner | 关注点 |
|---|---|---|
| Contract | JSON Schema + table runner | tagged union、字段、ID、版本、错误 |
| Domain parity | deterministic headless world | Player/AI 同一 validator 与守恒 |
| Integration | FastAPI + SQLite + WebSocket | 幂等、Revision、Outbox、恢复 |
| Browser E2E | headed Chromium Stable | 键盘、DOM focus、camera、fullscreen |
| Recovery | crash/fault injection | atomicity、orphan token、audit chain |
| Accessibility | axe + keyboard/manual | focus、ARIA、Reduced Motion、文本替代 |

## 4. 固定 Fixtures

```json
{
  "schema_version": 1,
  "fixture_set_id": "player.acceptance.v1",
  "world_seed": 20260726,
  "world_id": "01K1WORLD000000000000000001",
  "initial_revision": 500,
  "player_binding_id": "01K1PLAYER00000000000000001",
  "player_resident_id": "01K1RESIDENT0000000000001",
  "comparison_ai_resident_id": "01K1RESIDENT0000000000002",
  "mayor_office_id": "01K1OFFICE0000000000000001",
  "public_account_balance_copper_feather": 10000,
  "appropriation_limit_copper_feather": 5000,
  "scenes": [
    "scene.crowncreek.town",
    "scene.interior.apothecary"
  ],
  "obstacles": [
    "building.apothecary",
    "tree.market.01",
    "water.creek.01",
    "door.apothecary.front"
  ]
}
```

Fixture 还固定 role/health/Inventory/Quote/map revision、一个 public secret、一个 personal secret、一个 dynamic Door 和可故障注入的 Admin audit sink。测试不得调用模型生成随机规则数据；自然语言模型输出用已记录 fixture response。

## 5. 核心 E2E 场景

| 场景 ID | 操作序列 | Oracle |
|---|---|---|
| `acceptance.player.create` | 新世界创建玩家→中途 crash→重试 | 单 binding/Resident；AI quota 不变；无 orphan |
| `acceptance.player.move_parity` | 玩家与 AI 从同点走向同目标 | 路径合法性、终点、拒绝 code parity |
| `acceptance.player.collision` | 压住 WASD 朝房屋/树/水/封锁区 | 无穿越；blur 后停止；Revision 连续 |
| `acceptance.player.mode_pause` | Dialogue→关对话→Tab Mayor→Combat signal | token ledger 不提前恢复；禁止战斗切换 |
| `acceptance.player.interact_trade` | E 选目标→买物→重发 command | 单次 Transaction/event；余额/ownership 守恒 |
| `acceptance.player.nl_input` | 输入含糊购买→澄清→确认→报价过期 | stale 拒绝，无副作用，重新确认 |
| `acceptance.player.impact` | 工作→赠与→Quest→修路提议 | 六维事件 causation/correlation 完整 |
| `acceptance.player.permission` | 伪造 role/读取 secret/普通命令调用 Mayor | 全拒绝且错误不泄露秘密 |
| `acceptance.player.mayor_budget` | 两个并发公共支出竞争额度 | 最多一个成功；三层预算不透支 |
| `acceptance.player.admin_audit` | enable→challenge→tamper/replay→成功→回档 | 仅原 payload 一次成功；taint 永久；chain 有效 |
| `acceptance.player.fullscreen` | 首次启动→点击全屏→拒绝→F11 提示→重试→Esc | 始终可玩；focus/layout 恢复；规则 hash 不变 |
| `acceptance.player.accessibility` | 键盘完成对话/Mayor/设置；Reduced Motion | 无 focus escape/双触发；语义等价 |

## 6. 成对 parity Oracle

对注册 action `move_to/talk/work/buy/sell/give_item/use_object/craft/gather/cast_spell/start_encounter/build/repair`，构造等价 PlayerCommand 与 AI ActionProposal：

```text
normalize(decision_source)
→ run same actor projection, target, parameters, revision and seed
→ assert validation result/reason equal
→ if committed, assert owner state hash and DomainEvent payload equal
→ assert only source metadata differs
```

AI/Memory 并行实现只提供 action/knowledge projection；本测试不读取 chain of thought，也不把模型文本当 oracle。

## 7. 故障注入矩阵

| 注入点 | 预期 |
|---|---|
| binding/Resident/account commit 前后 | 全成或全败 |
| move ack 丢失/乱序/Revision gap | Snapshot 收敛，无 teleport |
| Mayor token acquire 后 UI 前 | reload 恢复 Mayor 或确定回滚且不运行世界 |
| ECON Reservation/commit/Outbox | 无 double-spend；event 可重发 |
| NL parser timeout/invalid JSON | speech-only/表单 fallback，不猜测执行 |
| Admin attempted/challenge/mutation/audit/mark | mutation 仅在五者可一致提交时成功 |
| fullscreen promise reject/context loss | windowed 可玩；两类恢复不混淆 |
| input profile write/corruption | 旧/default profile 可达，世界状态不变 |

## 8. 证据 Schema

```json
{
  "schema_version": 1,
  "evidence_id": "01K1EVIDENCE0000000000001",
  "fixture_set_id": "player.acceptance.v1",
  "scenario_id": "acceptance.player.admin_audit",
  "build_version": "0.1.0",
  "result": "passed",
  "initial_revision": 500,
  "final_revision": 501,
  "state_hash_before": "sha256:8e885b6f4a8b0a55c49fa2d56c9d4e9b5974177074950ab9e3339744ec302803",
  "state_hash_after": "sha256:9b1f6da6bdd4587e43a86e9adf79fb8a7dd055c6f92fcb15384630e91886b046",
  "event_ids": [
    "01K1EVENT00000000000000012"
  ],
  "audit_hash_valid": true,
  "artifacts": [
    "evidence/player/admin-audit.json"
  ]
}
```

证据不得包含 API Key、原始 secret、私人记忆、未脱敏对话或模型 reasoning。Browser 场景另记录 OS/browser full version、viewport、DPR、headed=true 和截图/录像。

## 9. 通过门槛

- `TEST-PLAYER-001..044` 全部通过，0 Critical/Important waiver。
- parity action 全集结果差异为 0；secret exposure、权限 union confusion、守恒破坏为 0。
- 1000 次 movement reconciliation 无非法站立；100 次 command retry 无重复 commit。
- Admin 50 个故障边界无未标记 mutation，audit chain 全部可验证。
- 720p、1080p、fullscreen 三 viewport 的 keyboard-only 与 focus 流程通过。

## 10. 失败分类与归属

`PLAYER_CONTRACT_FAILED` 归 PLAYER；MAP legality mismatch 归 MAP；经济守恒归 ECON；Pause Ledger 归 TIME；DOM/focus/visual 归 RENDER；协议/Outbox 归 BACKEND。跨域失败由 scenario owner 建单一 defect 并链接各 owner evidence，禁止通过放宽 oracle 或跳过 fixture 关闭。

## 11. 验收清单

- 玩家创建、移动、交互、自然语言和长期影响有完整 happy/deny/recovery。
- Player Intent、MayorCommand、AdminCommand 三个 union 不能互相解析。
- 预算、产权、秘密、关系、战斗、Collision 和 SaveIntegrityMark 边界均有反例。
- 双击启动首屏、F11/按钮、Fullscreen 失败恢复和按键提示有 headed evidence。
- 每个结果可由 command/event/revision/hash 复核，视觉成功不代替 Domain 成功。

## 12. 关联文档

- `DOC-PLAYER-001..011`：被验收的 PLAYER canonical contract
- `DOC-MAP-012`：导航/碰撞 parity fixtures
- `DOC-TIME-012`：Pause/速度/恢复 fixtures
- `DOC-ECON-012`：交易/预算/产权 fixtures
- `DOC-RENDER-012`：headed browser、性能与视觉 QA evidence


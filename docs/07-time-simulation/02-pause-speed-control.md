---
doc_id: DOC-TIME-002
title: 暂停与速度控制
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - overworld-pause-policy
  - simulation-speed-control
  - pause-token-ledger
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-001
requirements:
  - REQ-TIME-002
last_updated: 2026-07-26
---

# 暂停与速度控制

## 1. 目的

`REQ-TIME-002`：定义合法倍率、暂停原因、可嵌套 Pause Token、有效速度计算和恢复规则，使对话输入、镇长管理、回合制战斗、手动暂停、恢复屏障与关闭流程不会互相提前解除。

## 2. 非目标

本文不定义对话 UI、镇长权限、Encounter 流程或 Launcher 退出协议；对应 owner 只能通过 Pause Port 申请和释放 token。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Requested Speed | 玩家或 backpressure controller 请求的 `0/0.5/1/2/4` 倍率 |
| Effective Speed | 有 blocking token 时为 0，否则为 requested speed |
| Pause Token | 带稳定 token ID、原因、owner、scope 和生命周期的暂停声明 |
| Blocking Reason | `manual`, `dialogue_input`, `mayor_management`, `combat`, `shutdown`, `recovery_barrier`, `fatal_consistency_error` |
| Advisory Slowdown | Queue overload 触发的倍率上限，不创建 blocking token |
| Pause Ledger | TIME 拥有的当前 token 集和已提交 acquire/release 事实 |

## 4. 规则与不变量

- `RULE-TIME-007`：任一有效 blocking Pause Token 存在时，Overworld Effective Speed 必须为 `0×`。
- `RULE-TIME-008`：token 只能由创建它的 owner 或恢复协调器以同一 `token_id` 幂等释放；释放一个 token 不影响其他 token。
- `RULE-TIME-009`：自然语言输入框、镇长管理事务和 Encounter Active 阶段默认申请 blocking token；仅打开非交互信息面板不自动暂停。
- `RULE-TIME-010`：`shutdown/recovery_barrier/fatal_consistency_error` 的优先级高于用户解除暂停和速度请求。
- `RULE-TIME-011`：requested speed 变更在下一个 World Tick 生效并产生 ClockControl Event；Client 本地按钮状态不构成事实。
- `RULE-TIME-012`：backpressure 可按 `4→2→1→0.5` 降低 speed cap，但不得自动恢复到高于玩家 requested speed，也不得跳过规则工作。

## 5. 数据与接口

`DES-TIME-002`：

```json
{
  "schema_version": 1,
  "command_id": "01K1AB2CD3EF4GH5JK6MNP7QRS",
  "world_id": "01K1AB2CD3EF4GH5JK6MNP7QRT",
  "operation": "acquire",
  "token": {
    "token_id": "01K1AB2CD3EF4GH5JK6MNP7QRV",
    "owner_domain": "dialogue",
    "reason": "dialogue_input",
    "scope": "overworld",
    "acquired_at_game_time": 1830
  }
}
```

Schema 约束：`operation` 仅 `acquire/release`；`scope` 首版仅 `overworld`；`reason` 必须来自上节 enum；`token_id` 为 ULID；release payload 只携带 token ID 和 owner。接口：

```text
request_speed(command_id, requested_speed) -> ClockControlResult
acquire_pause(command_id, token) -> PauseResult
release_pause(command_id, token_id, owner_domain) -> PauseResult
get_effective_clock_control(world_id) -> {requested_speed, speed_cap, effective_speed, active_tokens}
```

状态机：

```text
running(speed>0) -- acquire first token --> paused
paused -- acquire another token --> paused
paused -- release non-last token --> paused
paused -- release last token --> running(requested_speed limited by cap)
running -- request 0x --> paused_by_speed
paused_by_speed -- request positive speed --> running
any -- fatal token --> consistency_paused
```

## 6. 正常流程

1. 对话、镇长、Combat 或 shutdown owner 以 Command 获取 Pause Token。
2. TIME 在同一提交边界写 ledger 与 ClockControl Event。
3. 下一个 Tick 读取 effective speed；为 0 时不增加 Clock Phase，但仍处理 RealTime health、网络和安全退出。
4. owner 完成流程后按 token ID 释放。
5. 最后一个 blocking token 释放后，以当前 requested speed 和 speed cap 恢复。

## 7. 边界情况

- 玩家在 combat 中点击 4×：记录 requested speed=4，但 effective speed 仍为 0。
- 对话与镇长面板嵌套时，先关闭任一流程不会恢复世界。
- 断线导致 owner 无法主动释放时，仅其有界恢复流程可根据已提交会话终态释放；禁止按 RealTime 猜测。
- 重放 acquire/release Command 返回原结果，不创建第二 token 或重复 release event。
- 进程关闭时 `shutdown` token 不需要在旧进程释放；重启由 `DOC-TIME-009` 的恢复状态替代。

## 8. 错误与降级

未知 reason、owner 不匹配、重复释放不同 payload 或非法倍率返回 `TIME_PAUSE_COMMAND_INVALID` 且无状态变化。Pause Ledger 损坏时进入 consistency pause，必须在 Recovery Barrier 下审计，禁止默认为 running。

## 9. 安全与性能

Pause Port 不接受 Client 自报 owner；Gateway 映射已授权命令类型。active token 数量首版每 world 上限 64，超限视为一致性错误。有效速度计算为不可变 ledger 的 O(n) 小集合扫描或计数索引。

## 10. 验收标准

- 七种 blocking reason 均能独立暂停并正确嵌套。
- Dialogue、Mayor、Combat、Shutdown 四条主流程没有提前恢复 GameTime。
- 0× 与 Pause Token 均冻结 GameTime，但 RealTime timeout/退出仍运行。
- backpressure 降档和玩家倍率请求组合结果确定。
- 断线、重复命令和恢复后 token ledger 无泄漏。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-TIME-004` | `RULE-TIME-007..010` token nesting 与优先级 |
| `TEST-TIME-005` | `RULE-TIME-011..012` speed apply boundary 与 cap |
| `TEST-TIME-006` | 幂等、断线和 ledger 恢复 |

## 12. 关联文档

- `DOC-TIME-001`：倍率与 Clock Phase
- `DOC-TIME-009`：shutdown 和 restart
- `DOC-DIALOGUE-001`：对话生命周期消费者
- `DOC-PLAYER-003`：镇长模式消费者
- `DOC-COMBAT-001`：Encounter pause 消费者

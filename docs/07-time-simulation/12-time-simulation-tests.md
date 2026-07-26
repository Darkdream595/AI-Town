---
doc_id: DOC-TIME-012
title: 时间与模拟验收测试
version: 1.0.0
status: approved-for-implementation
owner_domain: time
canonical_for:
  - time-simulation-acceptance
  - deterministic-replay-test-matrix
  - time-traceability
depends_on:
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-TIME-001
  - DOC-TIME-002
  - DOC-TIME-003
  - DOC-TIME-004
  - DOC-TIME-005
  - DOC-TIME-006
  - DOC-TIME-007
  - DOC-TIME-008
  - DOC-TIME-009
  - DOC-TIME-010
  - DOC-TIME-011
requirements:
  - REQ-TIME-012
last_updated: 2026-07-26
---

# 时间与模拟验收测试

## 1. 目的

`REQ-TIME-012`：建立覆盖三时钟、倍率、Pause、Tick、调度公平、simulation tier、长任务、Reservation、周期队列、关闭恢复、Seed/AI replay 和 backpressure 的可执行验收矩阵与追踪闭环。

## 2. 非目标

本文不以人工观察 UI 时钟代替权威断言，不验收业务 owner 的价格、天气或 Needs 公式；fixture 使用 owner fake Port，断言 TIME 的调用时间、顺序、幂等和状态边界。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Deterministic Run | 相同 initial snapshot、seed、commands、model records 与 tick sequence 的运行 |
| State Hash | canonical JSON 排序后对 TIME-owned state 计算 SHA-256 |
| Event Trace | 按 Revision 与 queue full order 保存的执行记录 |
| Fault Point | transaction、checkpoint、shutdown 或 replay 中可重复注入的失败点 |
| Acceptance Bundle | input、command、expected、actual、event trace、metrics 和 result 的证据目录 |
| Parity | tier/render cadence/model online 状态变化后，不应变化的权威结果相等 |

## 4. 规则与不变量

- `RULE-TIME-068`：每个 TIME Requirement 必须至少有一个可执行 Test ID、固定输入和机器断言。
- `RULE-TIME-069`：确定性测试必须比较 State Hash、Event Trace、queue next item、Seed sequence 和 Revision，不能只比较最终 GameTime。
- `RULE-TIME-070`：故障注入至少覆盖 transaction 前/中/后、checkpoint 前/后、shutdown 前/中/后和 replay mismatch。
- `RULE-TIME-071`：1/7/30 游戏日模拟每次结束运行 `RULE-FOUNDATION-016..030` 全量 invariant，期间每游戏日保存分片 audit。
- `RULE-TIME-072`：验收 bundle 禁止包含 API Key、Secret、未过滤 Prompt 或 `reasoning_content`。

## 5. 数据与接口

`DES-TIME-012`：Scenario Manifest：

```json
{
  "schema_version": 1,
  "suite_id": "acceptance.time.v1",
  "initial": {
    "seed_hex": "0123456789abcdeffedcba9876543210",
    "revision": 100,
    "game_time": 1830,
    "clock_phase_quanta": 0,
    "requested_speed": 1
  },
  "runs": [
    {"case_id": "clock.200_ticks.1x", "ticks": 200, "speed": 1, "expected_game_time": 1850, "expected_phase": 0},
    {"case_id": "clock.25_ticks.4x", "ticks": 25, "speed": 4, "expected_game_time": 1840, "expected_phase": 0},
    {"case_id": "pause.200_ticks", "ticks": 200, "speed": 1, "pause_reason": "dialogue_input", "expected_game_time": 1830, "expected_phase": 0}
  ],
  "required_hashes": ["time_state", "event_trace", "queue_head", "seed_sequences"]
}
```

实现测试 Port：

```text
run_time_scenario(manifest, fake_owner_ports) -> AcceptanceBundle
inject_time_fault(fault_point, occurrence) -> FaultHandle
compare_deterministic_runs(bundle_a, bundle_b) -> DeterminismReport
audit_time_traceability() -> TraceabilityReport
```

## 6. 正常流程

1. 构造固定 Clock/Queue/Resident/Long Action/Reservation snapshot。
2. 加载 Fake Resident/AI/Economy/Event Port 与 recorded AI response。
3. 按显式 Tick Sequence 输入 commands 和 fault。
4. 收集每次 commit 的 Revision、DomainEvent、queue outcome 和 hashes。
5. 同 fixture 至少运行两次，并在 30/60/144 FPS render driver 下做 parity。
6. 输出 bundle；任一 Secret scan 或 traceability failure 使 suite failed。

## 7. 边界情况

- test runner 被系统墙钟回拨：使用 fake monotonic clock，结果不变。
- 并发命令输入顺序不同但 accepted sequence 相同：归一后 trace 相同。
- recorded AI response 缺失：对应 case 必须显式走 fallback，不允许访问真实网络。
- 30 日 backlog 触发降档：仍需跑完或明确 safe pause；不能为测试跳过事件。
- crash fixture 恢复到上一完整 Revision 后继续，最终 hash 与无 crash 对照相同。

## 8. 错误与降级

fixture 缺字段、hash 算法版本不匹配、Fake Port 调用未登记或 bundle 泄露扫描失败时返回 `TIME_ACCEPTANCE_INVALID`，不得标记 skipped-as-pass。性能环境不达标可记录 capacity failure，但 correctness suite 仍必须执行。

## 9. 安全与性能

测试只使用 fixture ID 和合成文本；bundle 在写盘前执行敏感键名与高熵 token 扫描。30 日模拟支持事件摘要，但 State Hash、Seed sequence 和不可丢 Event count 必须保留。

## 10. 验收标准

### 10.1 可执行确定性 smoke command

以下 PowerShell 5.1 命令无需项目依赖，可验证 Clock quanta 与 Seed v1 固定向量：

```powershell
$ErrorActionPreference = 'Stop'
function Convert-HexToBytes([string]$hex) {
  $bytes = New-Object byte[] ($hex.Length / 2)
  for ($index = 0; $index -lt $bytes.Length; $index++) {
    $bytes[$index] = [Convert]::ToByte($hex.Substring($index * 2, 2), 16)
  }
  return $bytes
}
function Convert-BytesToHex([byte[]]$bytes) {
  return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}
function Advance-Clock([int]$gameTime, [int]$phase, [int]$ticks, [int]$quantaPerTick) {
  $total = $phase + ($ticks * $quantaPerTick)
  return @{ game_time = $gameTime + [Math]::Floor($total / 20); phase = $total % 20 }
}
$oneX = Advance-Clock 1830 0 200 2
$fourX = Advance-Clock 1830 0 25 8
if ($oneX.game_time -ne 1850 -or $oneX.phase -ne 0) { throw 'clock 1x failed' }
if ($fourX.game_time -ne 1840 -or $fourX.phase -ne 0) { throw 'clock 4x failed' }
$seed = Convert-HexToBytes '0123456789abcdeffedcba9876543210'
$streamHmac = New-Object System.Security.Cryptography.HMACSHA256 (,$seed)
$streamKey = $streamHmac.ComputeHash([Text.Encoding]::UTF8.GetBytes("ai-town/v1`0time.weather`0world"))
$streamHmac.Dispose()
$drawHmac = New-Object System.Security.Cryptography.HMACSHA256 (,$streamKey)
$drawData = [byte[]]([Text.Encoding]::UTF8.GetBytes("draw`0") + [byte[]](0,0,0,0,0,0,0,0))
$rawBlock = $drawHmac.ComputeHash($drawData)
$drawHmac.Dispose()
if ((Convert-BytesToHex $streamKey) -ne '67f681f7d39d24580768808d033be6ffd0cd3eb661ddaab200ca184bc1073b5f') { throw 'stream key failed' }
if ((Convert-BytesToHex $rawBlock) -ne 'c7801dd6c40f8ef4f422b58c1360dbe8afeb3a2f53c9428d3061b7fff71885b8') { throw 'raw block failed' }
'TIME_DETERMINISM_SMOKE_PASS'
```

### 10.2 场景矩阵

| Case ID | 输入 | 核心断言 |
|---|---|---|
| `acceptance.time.clock_matrix` | 五倍率各 1000 Tick | GameTime/phase 精确，无浮点漂移 |
| `acceptance.time.pause_nesting` | Dialogue+Mayor+Combat+Shutdown token | 最后 token 前 effective speed=0 |
| `acceptance.time.scheduler_fairness` | 12 Resident + emergency storm | 并发≤2、routine 10 分钟不饥饿 |
| `acceptance.time.tier_roundtrip` | Active→Warm→Background→Active | 守恒 hash 一致、位置合法 |
| `acceptance.time.long_action_crash` | 20 checkpoint + 8 fault points | progress/产出最多一次 |
| `acceptance.time.lock_conflict` | 1000 randomized Lock Set | 无 deadlock、无部分 held |
| `acceptance.time.periodic_30_days` | 30 日四类 cadence | 无漂移、无重复 occurrence |
| `acceptance.time.offline_zero_delta` | offline 1m/1h/30d | GameTime/phase/work/expiry delta=0 |
| `acceptance.time.seed_replay` | 固定 vector + stream reorder | hash/sequence 相同，无网络 AI replay |
| `acceptance.time.overload_fallback` | 4× backlog pressure | 逐级降档、健康 30s 后逐级恢复 |

全部十个 case、1/7/30 日 invariant audit、traceability 和 Secret scan 均通过，TIME domain 才可标记 accepted。

## 11. 测试追踪

| Test ID | Requirement / Rule |
|---|---|
| `TEST-TIME-034` | `REQ-TIME-001..004`, `RULE-TIME-001..024`, `RULE-TIME-073` |
| `TEST-TIME-035` | `REQ-TIME-005..008`, `RULE-TIME-025..048` |
| `TEST-TIME-036` | `REQ-TIME-009..012`, `RULE-TIME-049..072` |

## 12. 关联文档

- `DOC-FOUNDATION-005`：Simulation invariant 集
- `DOC-FOUNDATION-007`：全局追踪策略
- `DOC-TIME-001..011`：本验收 suite 的 canonical 输入
- `DOC-BACKEND-012`：集成性能测试
- `DOC-RELEASE-011..012`：全项目测试与发布 Gate

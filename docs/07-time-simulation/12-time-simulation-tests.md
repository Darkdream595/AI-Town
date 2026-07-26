---
doc_id: DOC-TIME-012
title: 时间与模拟验收测试
version: 1.0.3
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
    "requested_speed_multiplier": 4,
    "speed_cap_multiplier": 1
  },
  "runs": [
    {"case_id": "clock.200_ticks.1x", "ticks": 200, "speed": 1, "expected_game_time": 1850, "expected_phase": 0},
    {"case_id": "clock.25_ticks.4x", "ticks": 25, "speed": 4, "expected_game_time": 1840, "expected_phase": 0},
    {"case_id": "speed.cap.no_token", "requested_speed_multiplier": 4, "speed_cap_multiplier": 1, "blocking_token_count": 0, "expected_effective_speed_multiplier": 1},
    {"case_id": "speed.cap.with_token", "requested_speed_multiplier": 4, "speed_cap_multiplier": 1, "blocking_token_count": 1, "expected_effective_speed_multiplier": 0},
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

以下 PowerShell 5.1 命令无需项目依赖，可验证 Clock quanta、完整 v1 Evidence upcast、缺证据安全失败、strict v2 全字段 round-trip 与 Seed v1 固定向量：

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
function Resolve-EffectiveSpeed([double]$requestedSpeed, [double]$speedCap, [int]$blockingTokenCount) {
  if ($blockingTokenCount -gt 0) { return [double]0 }
  return [Math]::Min($requestedSpeed, $speedCap)
}
function Assert-StrictShape($value, [string[]]$allowedFields, [string]$label) {
  $actualFields = @($value.PSObject.Properties.Name)
  $missingFields = @($allowedFields | Where-Object { $actualFields -cnotcontains $_ })
  $additionalFields = @($actualFields | Where-Object { $allowedFields -cnotcontains $_ })
  if ($missingFields.Count -gt 0 -or $additionalFields.Count -gt 0) {
    throw "TIME_RECOVERY_AUDIT_FAILED:$label missing=$($missingFields -join ',') additional=$($additionalFields -join ',')"
  }
}
function Get-PauseLedgerHash($ledger) {
  $records = @()
  foreach ($token in @($ledger | Sort-Object token_id)) {
    $records += '{"token_id":"' + $token.token_id + '","owner_domain":"' + $token.owner_domain + '","reason":"' + $token.reason + '","scope":"' + $token.scope + '","acquired_at_game_time":' + $token.acquired_at_game_time + '}'
  }
  $canonicalJson = '[' + ($records -join ',') + ']'
  $sha256 = [Security.Cryptography.SHA256]::Create()
  try {
    return Convert-BytesToHex ($sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonicalJson)))
  } finally {
    $sha256.Dispose()
  }
}
$v1Fields = @('schema_version','world_id','revision','game_time','clock_phase_quanta','next_tick_sequence','event_queue_hash','scheduler_hash','long_action_hash','reservation_hash','shutdown_state')
$evidenceFields = @('schema_version','evidence_type','world_id','checkpoint_revision','requested_speed_multiplier','speed_cap_multiplier','effective_speed_multiplier','active_blocking_token_count','backpressure_overload_windows','backpressure_healthy_real_ms','clock_control_version','pause_ledger_hash')
$v2Fields = @('schema_version','world_id','revision','game_time','clock_phase_quanta','requested_speed_multiplier','speed_cap_multiplier','backpressure_overload_windows','backpressure_healthy_real_ms','clock_control_version','pause_ledger_hash','next_tick_sequence','event_queue_hash','scheduler_hash','long_action_hash','reservation_hash','shutdown_state')
function Test-JsonNumber($value) {
  return $value -is [byte] -or $value -is [sbyte] -or $value -is [int16] -or $value -is [uint16] -or $value -is [int32] -or $value -is [uint32] -or $value -is [int64] -or $value -is [uint64] -or $value -is [single] -or $value -is [double] -or $value -is [decimal]
}
function Test-JsonInteger($value) {
  if ($value -is [string] -or $value -is [bool] -or $null -eq $value) { return $false }
  if ($value -is [byte] -or $value -is [sbyte] -or $value -is [int16] -or $value -is [uint16] -or $value -is [int32] -or $value -is [uint32] -or $value -is [int64] -or $value -is [uint64]) { return $true }
  if ($value -is [single] -or $value -is [double] -or $value -is [decimal]) {
    $number = [double]$value
    return -not [double]::IsNaN($number) -and -not [double]::IsInfinity($number) -and [Math]::Floor($number) -eq $number
  }
  return $false
}
function Assert-IntegerRange($value, [long]$minimum, $maximum, [string]$label) {
  if (-not (Test-JsonInteger $value)) { throw "TIME_RECOVERY_AUDIT_FAILED:$label type=integer" }
  $number = [decimal]$value
  if ($number -lt $minimum -or ($null -ne $maximum -and $number -gt [decimal]$maximum)) {
    throw "TIME_RECOVERY_AUDIT_FAILED:$label range"
  }
}
function Assert-NumberEnum($value, [double[]]$allowed, [string]$label) {
  if (-not (Test-JsonNumber $value)) { throw "TIME_RECOVERY_AUDIT_FAILED:$label type=number" }
  $number = [double]$value
  if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or -not ($allowed -contains $number)) {
    throw "TIME_RECOVERY_AUDIT_FAILED:$label enum"
  }
}
function Assert-StringPattern($value, [string]$pattern, [string]$label) {
  if ($value -isnot [string] -or $value -cnotmatch $pattern) { throw "TIME_RECOVERY_AUDIT_FAILED:$label pattern" }
}
function Assert-Const($value, $expected, [string]$label) {
  if ($value -cne $expected) { throw "TIME_RECOVERY_AUDIT_FAILED:$label const" }
}
function Assert-CheckpointV1($value) {
  Assert-StrictShape $value $v1Fields 'checkpoint_v1'
  Assert-IntegerRange $value.schema_version 1 1 'checkpoint_v1.schema_version'
  Assert-StringPattern $value.world_id '^[0-9A-HJKMNP-TV-Z]{26}$' 'checkpoint_v1.world_id'
  Assert-IntegerRange $value.revision 0 $null 'checkpoint_v1.revision'
  Assert-IntegerRange $value.game_time 0 $null 'checkpoint_v1.game_time'
  Assert-IntegerRange $value.clock_phase_quanta 0 19 'checkpoint_v1.clock_phase_quanta'
  Assert-IntegerRange $value.next_tick_sequence 0 $null 'checkpoint_v1.next_tick_sequence'
  foreach ($field in @('event_queue_hash','scheduler_hash','long_action_hash','reservation_hash')) {
    Assert-StringPattern $value.$field '^[a-f0-9]{64}$' "checkpoint_v1.$field"
  }
  Assert-Const $value.shutdown_state 'checkpointed' 'checkpoint_v1.shutdown_state'
}
function Assert-RecoveryEvidenceV1($value) {
  Assert-StrictShape $value $evidenceFields 'recovery_evidence_v1'
  Assert-IntegerRange $value.schema_version 1 1 'evidence.schema_version'
  Assert-Const $value.evidence_type 'clock_control_recovery' 'evidence.evidence_type'
  Assert-StringPattern $value.world_id '^[0-9A-HJKMNP-TV-Z]{26}$' 'evidence.world_id'
  Assert-IntegerRange $value.checkpoint_revision 0 $null 'evidence.checkpoint_revision'
  Assert-NumberEnum $value.requested_speed_multiplier @(0,0.5,1,2,4) 'evidence.requested_speed_multiplier'
  Assert-NumberEnum $value.speed_cap_multiplier @(0.5,1,2,4) 'evidence.speed_cap_multiplier'
  Assert-NumberEnum $value.effective_speed_multiplier @(0,0.5,1,2,4) 'evidence.effective_speed_multiplier'
  Assert-IntegerRange $value.active_blocking_token_count 0 64 'evidence.active_blocking_token_count'
  Assert-IntegerRange $value.backpressure_overload_windows 0 6 'evidence.backpressure_overload_windows'
  Assert-IntegerRange $value.backpressure_healthy_real_ms 0 30000 'evidence.backpressure_healthy_real_ms'
  Assert-IntegerRange $value.clock_control_version 1 $null 'evidence.clock_control_version'
  Assert-StringPattern $value.pause_ledger_hash '^[a-f0-9]{64}$' 'evidence.pause_ledger_hash'
}
function Assert-CheckpointV2($value) {
  Assert-StrictShape $value $v2Fields 'checkpoint_v2'
  Assert-IntegerRange $value.schema_version 2 2 'checkpoint_v2.schema_version'
  Assert-StringPattern $value.world_id '^[0-9A-HJKMNP-TV-Z]{26}$' 'checkpoint_v2.world_id'
  Assert-IntegerRange $value.revision 0 $null 'checkpoint_v2.revision'
  Assert-IntegerRange $value.game_time 0 $null 'checkpoint_v2.game_time'
  Assert-IntegerRange $value.clock_phase_quanta 0 19 'checkpoint_v2.clock_phase_quanta'
  Assert-NumberEnum $value.requested_speed_multiplier @(0,0.5,1,2,4) 'checkpoint_v2.requested_speed_multiplier'
  Assert-NumberEnum $value.speed_cap_multiplier @(0.5,1,2,4) 'checkpoint_v2.speed_cap_multiplier'
  Assert-IntegerRange $value.backpressure_overload_windows 0 6 'checkpoint_v2.backpressure_overload_windows'
  Assert-IntegerRange $value.backpressure_healthy_real_ms 0 30000 'checkpoint_v2.backpressure_healthy_real_ms'
  Assert-IntegerRange $value.clock_control_version 1 $null 'checkpoint_v2.clock_control_version'
  Assert-StringPattern $value.pause_ledger_hash '^[a-f0-9]{64}$' 'checkpoint_v2.pause_ledger_hash'
  Assert-IntegerRange $value.next_tick_sequence 0 $null 'checkpoint_v2.next_tick_sequence'
  foreach ($field in @('event_queue_hash','scheduler_hash','long_action_hash','reservation_hash')) {
    Assert-StringPattern $value.$field '^[a-f0-9]{64}$' "checkpoint_v2.$field"
  }
  Assert-Const $value.shutdown_state 'checkpointed' 'checkpoint_v2.shutdown_state'
}
function Convert-CheckpointV1ToV2($checkpointV1, $evidenceV1, $pauseLedger) {
  Assert-CheckpointV1 $checkpointV1
  Assert-RecoveryEvidenceV1 $evidenceV1
  if ($checkpointV1.world_id -ne $evidenceV1.world_id -or $checkpointV1.revision -ne $evidenceV1.checkpoint_revision) {
    throw 'TIME_RECOVERY_AUDIT_FAILED:revision'
  }
  if (@($pauseLedger).Count -ne $evidenceV1.active_blocking_token_count -or (Get-PauseLedgerHash $pauseLedger) -ne $evidenceV1.pause_ledger_hash) {
    throw 'TIME_RECOVERY_AUDIT_FAILED:pause_ledger'
  }
  if ((Resolve-EffectiveSpeed $evidenceV1.requested_speed_multiplier $evidenceV1.speed_cap_multiplier $evidenceV1.active_blocking_token_count) -ne $evidenceV1.effective_speed_multiplier) {
    throw 'TIME_RECOVERY_AUDIT_FAILED:effective_speed'
  }
  $checkpointV2 = [pscustomobject][ordered]@{
    schema_version = 2
    world_id = $checkpointV1.world_id
    revision = $checkpointV1.revision
    game_time = $checkpointV1.game_time
    clock_phase_quanta = $checkpointV1.clock_phase_quanta
    requested_speed_multiplier = $evidenceV1.requested_speed_multiplier
    speed_cap_multiplier = $evidenceV1.speed_cap_multiplier
    backpressure_overload_windows = $evidenceV1.backpressure_overload_windows
    backpressure_healthy_real_ms = $evidenceV1.backpressure_healthy_real_ms
    clock_control_version = $evidenceV1.clock_control_version
    pause_ledger_hash = $evidenceV1.pause_ledger_hash
    next_tick_sequence = $checkpointV1.next_tick_sequence
    event_queue_hash = $checkpointV1.event_queue_hash
    scheduler_hash = $checkpointV1.scheduler_hash
    long_action_hash = $checkpointV1.long_action_hash
    reservation_hash = $checkpointV1.reservation_hash
    shutdown_state = $checkpointV1.shutdown_state
  }
  Assert-CheckpointV2 $checkpointV2
  return $checkpointV2
}
$oneX = Advance-Clock 1830 0 200 2
$fourX = Advance-Clock 1830 0 25 8
if ($oneX.game_time -ne 1850 -or $oneX.phase -ne 0) { throw 'clock 1x failed' }
if ($fourX.game_time -ne 1840 -or $fourX.phase -ne 0) { throw 'clock 4x failed' }
if ((Resolve-EffectiveSpeed 4 1 0) -ne 1) { throw 'speed cap without token failed' }
if ((Resolve-EffectiveSpeed 4 1 1) -ne 0) { throw 'speed cap with token failed' }
$checkpointV1 = @'
{"schema_version":1,"world_id":"01K1AB2CD3EF4GH5JK6MNP7QRS","revision":820,"game_time":1830,"clock_phase_quanta":6,"next_tick_sequence":40822,"event_queue_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","scheduler_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","long_action_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","reservation_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","shutdown_state":"checkpointed"}
'@ | ConvertFrom-Json
$evidenceV1 = @'
{"schema_version":1,"evidence_type":"clock_control_recovery","world_id":"01K1AB2CD3EF4GH5JK6MNP7QRS","checkpoint_revision":820,"requested_speed_multiplier":4,"speed_cap_multiplier":1,"effective_speed_multiplier":0,"active_blocking_token_count":1,"backpressure_overload_windows":2,"backpressure_healthy_real_ms":0,"clock_control_version":17,"pause_ledger_hash":"aef5b1cc44fafa992bac6022d8ba9bf61dbc42a080ea5961f55aabbe263fcbb3"}
'@ | ConvertFrom-Json
$pauseLedger = @(@{
  token_id = '01K1AB2CD3EF4GH5JK6MNP7QRV'
  owner_domain = 'time'
  reason = 'shutdown'
  scope = 'overworld'
  acquired_at_game_time = 1830
})
$expectedV2 = @'
{"schema_version":2,"world_id":"01K1AB2CD3EF4GH5JK6MNP7QRS","revision":820,"game_time":1830,"clock_phase_quanta":6,"requested_speed_multiplier":4,"speed_cap_multiplier":1,"backpressure_overload_windows":2,"backpressure_healthy_real_ms":0,"clock_control_version":17,"pause_ledger_hash":"aef5b1cc44fafa992bac6022d8ba9bf61dbc42a080ea5961f55aabbe263fcbb3","next_tick_sequence":40822,"event_queue_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","scheduler_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","long_action_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","reservation_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","shutdown_state":"checkpointed"}
'@ | ConvertFrom-Json
$upcastV2 = Convert-CheckpointV1ToV2 $checkpointV1 $evidenceV1 $pauseLedger
$serializedV2 = $upcastV2 | ConvertTo-Json -Compress
$roundTripV2 = $serializedV2 | ConvertFrom-Json
Assert-CheckpointV2 $roundTripV2
foreach ($field in $v2Fields) {
  $actual = ConvertTo-Json -Compress -InputObject $roundTripV2.$field
  $expected = ConvertTo-Json -Compress -InputObject $expectedV2.$field
  if ($actual -ne $expected) { throw "checkpoint all-field round-trip failed:$field" }
}
if ((Resolve-EffectiveSpeed $roundTripV2.requested_speed_multiplier $roundTripV2.speed_cap_multiplier 1) -ne 0) { throw 'startup pause composition failed' }
if ((Resolve-EffectiveSpeed $roundTripV2.requested_speed_multiplier $roundTripV2.speed_cap_multiplier 0) -ne 1) { throw 'restored cap composition failed' }
function Assert-RecoveryAuditFailure([scriptblock]$action, [string]$label, $source, [string]$sourceBefore) {
  $recoveryState = 'recovery_barrier'
  $failed = $false
  try { $null = & $action } catch {
    if ($_.Exception.Message -notlike 'TIME_RECOVERY_AUDIT_FAILED:*') { throw }
    $failed = $true
  }
  if (-not $failed) { throw "$label was accepted" }
  if (($source | ConvertTo-Json -Compress) -ne $sourceBefore -or $recoveryState -ne 'recovery_barrier') {
    throw "$label changed source or Recovery Barrier"
  }
}
$extraV2 = $serializedV2 | ConvertFrom-Json
$extraV2 | Add-Member -NotePropertyName unexpected_field -NotePropertyValue true
Assert-RecoveryAuditFailure { Assert-CheckpointV2 $extraV2 } 'v2 additionalProperties' $extraV2 ($extraV2 | ConvertTo-Json -Compress)
$missingEvidence = ($evidenceV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$missingEvidence.PSObject.Properties.Remove('pause_ledger_hash')
$sourceV1Before = $checkpointV1 | ConvertTo-Json -Compress
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $checkpointV1 $missingEvidence $pauseLedger } 'evidence required' $checkpointV1 $sourceV1Before
$extraEvidence = ($evidenceV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$extraEvidence | Add-Member -NotePropertyName unexpected_field -NotePropertyValue true
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $checkpointV1 $extraEvidence $pauseLedger } 'evidence additionalProperties' $checkpointV1 $sourceV1Before
$cap3Evidence = ($evidenceV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$cap3Evidence.speed_cap_multiplier = 3
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $checkpointV1 $cap3Evidence $pauseLedger } 'evidence enum cap=3' $checkpointV1 $sourceV1Before
$stringGameTimeV1 = ($checkpointV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$stringGameTimeV1.game_time = 'not-an-integer'
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $stringGameTimeV1 $evidenceV1 $pauseLedger } 'v1 integer type' $stringGameTimeV1 ($stringGameTimeV1 | ConvertTo-Json -Compress)
$constEvidence = ($evidenceV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$constEvidence.evidence_type = 'wrong_type'
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $checkpointV1 $constEvidence $pauseLedger } 'evidence const' $checkpointV1 $sourceV1Before
$rangeV1 = ($checkpointV1 | ConvertTo-Json -Compress) | ConvertFrom-Json
$rangeV1.clock_phase_quanta = 20
Assert-RecoveryAuditFailure { Convert-CheckpointV1ToV2 $rangeV1 $evidenceV1 $pauseLedger } 'v1 maximum' $rangeV1 ($rangeV1 | ConvertTo-Json -Compress)
$cap3V2 = $serializedV2 | ConvertFrom-Json
$cap3V2.speed_cap_multiplier = 3
Assert-RecoveryAuditFailure { Assert-CheckpointV2 $cap3V2 } 'v2 enum cap=3' $cap3V2 ($cap3V2 | ConvertTo-Json -Compress)
$badHashV2 = $serializedV2 | ConvertFrom-Json
$badHashV2.pause_ledger_hash = 'bad'
Assert-RecoveryAuditFailure { Assert-CheckpointV2 $badHashV2 } 'v2 hash pattern' $badHashV2 ($badHashV2 | ConvertTo-Json -Compress)
$badUlidV2 = $serializedV2 | ConvertFrom-Json
$badUlidV2.world_id = 'bad'
Assert-RecoveryAuditFailure { Assert-CheckpointV2 $badUlidV2 } 'v2 ULID pattern' $badUlidV2 ($badUlidV2 | ConvertTo-Json -Compress)
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
'TIME_STRICT_VALIDATORS_PASS'
'TIME_INVALID_FIXTURES_REJECTED=10'
'TIME_V2_REQUIRED_FIELDS_ROUNDTRIP=17'
'TIME_DETERMINISM_SMOKE_PASS'
```

### 10.2 场景矩阵

| Case ID | 输入 | 核心断言 |
|---|---|---|
| `acceptance.time.clock_matrix` | 五倍率各 1000 Tick | GameTime/phase 精确，无浮点漂移 |
| `acceptance.time.pause_nesting` | Dialogue+Mayor+Combat+Shutdown token | 最后 token 前 effective speed=0 |
| `acceptance.time.speed_cap_composition` | requested=4、cap=1、无 token/有 token | effective 分别为 1/0，释放 token 后仍为 1 |
| `acceptance.time.scheduler_fairness` | 12 Resident + emergency storm | 并发≤2、routine 10 分钟不饥饿 |
| `acceptance.time.tier_roundtrip` | Active→Warm→Background→Active | 守恒 hash 一致、位置合法 |
| `acceptance.time.long_action_crash` | 20 checkpoint + 8 fault points | progress/产出最多一次 |
| `acceptance.time.lock_conflict` | 1000 randomized Lock Set | 无 deadlock、无部分 held |
| `acceptance.time.periodic_30_days` | 30 日四类 cadence | 无漂移、无重复 occurrence |
| `acceptance.time.offline_zero_delta` | offline 1m/1h/30d | GameTime/phase/work/expiry delta=0 |
| `acceptance.time.checkpoint_v1_complete_evidence_upcast` | strict v1 + canonical Evidence + rebuilt ledger | 精确 strict v2、全部 required 字段 round-trip、startup 0/释放后 1 |
| `acceptance.time.checkpoint_v1_missing_evidence` | 缺/额外字段、cap=3、string GameTime、坏 const/range/ULID/hash | 三套 validator 全约束 stable failure，Recovery Barrier/source bytes 不变 |
| `acceptance.time.seed_replay` | 固定 vector + stream reorder | hash/sequence 相同，无网络 AI replay |
| `acceptance.time.overload_fallback` | 4× backlog pressure | 逐级降档、健康 30s 后逐级恢复 |

全部十三个 case、1/7/30 日 invariant audit、traceability 和 Secret scan 均通过，TIME domain 才可标记 accepted。

## 11. 测试追踪

| Test ID | Requirement / Rule |
|---|---|
| `TEST-TIME-034` | `REQ-TIME-001..004`, `RULE-TIME-001..024`, `RULE-TIME-073` |
| `TEST-TIME-035` | `REQ-TIME-005..008`, `RULE-TIME-025..048` |
| `TEST-TIME-036` | `REQ-TIME-009..012`, `RULE-TIME-049..072`, `RULE-TIME-074..076` |

## 12. 关联文档

- `DOC-FOUNDATION-005`：Simulation invariant 集
- `DOC-FOUNDATION-007`：全局追踪策略
- `DOC-TIME-001..011`：本验收 suite 的 canonical 输入
- `DOC-BACKEND-012`：集成性能测试
- `DOC-RELEASE-011..012`：全项目测试与发布 Gate

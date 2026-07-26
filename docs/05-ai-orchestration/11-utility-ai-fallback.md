---
doc_id: DOC-AI-011
title: Utility AI 与 Tactical Utility AI 降级
version: 1.0.0
status: approved-for-implementation
owner_domain: ai
canonical_for:
  - survival-utility-fallback
  - tactical-utility-fallback
  - fallback-safety-boundary
depends_on:
  - DOC-AI-005
  - DOC-AI-009
  - DOC-AI-010
  - DOC-RESIDENT-004
requirements:
  - REQ-AI-011
last_updated: 2026-07-26
---

# Utility AI 与 Tactical Utility AI 降级

## 1. 目的

`REQ-AI-011`：在模型超时、不可用、格式失败、deadline miss 或 replan loop 时，以确定性 Utility AI 维持正式居民生存/安全，并以 Tactical Utility AI 完成合法战斗回合。

## 2. 非目标

Fallback 不替代居民长期自主叙事，不生成新 Recipe/Spell/Action，不越权交易/建筑/秘密，不决定伤害或路径。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Survival Utility | 对安全、健康、饥饿、疲劳和卡死的本地评分 |
| Tactical Utility | 从 COMBAT 提供的合法行动集合中确定性选一 |
| Candidate | 已注册 Action + owner 提供的当前合法最小参数 |
| Utility Score | 整数 q1000 分数和稳定 tie-break |
| Fallback Episode | 从触发到模型恢复/安全结束的一段审计记录 |

## 4. 数据与接口

`DES-AI-011` 生存候选白名单：

```text
seek_safety -> move_to
obtain_food -> move_to/eat（仅已有可食物或 owner 提供合法 source）
rest_at_authorized_place -> move_to/rest
seek_healing -> move_to/talk/use_object（仅 owner 注册）
leave_hazard -> move_to
wait_safely -> wait
observe_blocker -> observe
```

禁止 fallback 主动 `buy/sell/give_item/craft/gather/explore/cast_spell/start_encounter/build/repair`；已有 long action 的机械 completion 由 TIME/owner 继续，不是新决策。

评分：

```text
score =
  safety_urgency_q1000 * 1000 +
  health_urgency_q1000 * 800 +
  hunger_urgency_q1000 * 600 +
  fatigue_urgency_q1000 * 500 +
  completion_likelihood_q1000 * 200 -
  path_cost_bucket * 50 -
  recent_repeat_count * 120
```

所有输入是 owner projection 的有界整数；按较高 score、较小 action ID、较小 target ID 决胜。

Tactical Utility 只接收 COMBAT 的 `LegalCombatOption[]`，依次评分：避免正式居民被击败、可完成明确防御/救援、预期规则效用、资源保守、稳定 option ID；无合法主动项时选择 owner 注册 `defend/pass/surrender` 中可用者。

## 5. 规则与不变量

- `RULE-AI-061`：Utility 只从 owner 已给出的合法候选中选择，结果仍走 DOC-AI-010 与正常 commit pipeline。
- `RULE-AI-062`：同一 state hash/candidate set/fallback policy version 得到同一选择；不调用网络或非 Seed 随机。
- `RULE-AI-063`：Survival 只维持安全/基本 Needs，不发起经济承诺、施法、战斗、建设或社会操纵。
- `RULE-AI-064`：Tactical 只选择 legal option；COMBAT owner 决定命中、伤害、消耗和结果，正式 Resident 无永久死亡。
- `RULE-AI-065`：fallback 不能穿越 Collision、传送、制造资源、读取秘密或跳过 Reservation。
- `RULE-AI-066`：每个 episode 记录 trigger、policy version、候选 IDs、chosen ID、committed outcome 和恢复条件，不记录私人 payload。

## 6. 正常流程

AI Request 终止→TIME 创建 `utility_fallback` job→owner 汇总 legal candidates→Utility 评分选一→构造 server-originated ActionProposal-compatible intent→正常 validator/Reservation/commit→事件驱动下一 evaluation。provider 连续健康且无 backlog 后，下一非紧急机会恢复模型，不中断已提交长行动。

## 7. 边界情况

食物不可达/不属于 actor 时不选择 eat；床无权限改为安全 wait；所有 safe point 不可达时原地 wait+诊断，不直线穿墙。战斗 legal set 为空是 COMBAT invariant failure，不能伪造 attack。高倍速 backlog 下 fallback 仍按 GameTime/TIME fairness。

## 8. 错误与降级

候选为空返回 `fallback_no_legal_candidate`，TIME 降速/安全暂停相关 actor 并告警；评分溢出/未知 candidate 使 episode 失败。连续 fallback 不自行扩大权限，直到 owner state/model health 改变。

## 9. 安全与性能

候选上限 32，纯整数评分 O(n)，目标每 resident <1 real ms。日志只含 Stable/Runtime ID 和 reason；不得复制完整 DecisionContext。

## 10. 验收标准

- provider 全故障下 8–12 居民可维持安全/基本 Needs 且世界 Tick 不阻塞。
- 相同 fixture 100 次 byte-equivalent 选择。
- fallback 不能执行禁用 action 或绕过 owner validation。
- combat option 只来自 legal set，数值结算仍由 COMBAT。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-AI-041` | survival candidate whitelist/forbidden set |
| `TEST-AI-042` | deterministic score/tie-break |
| `TEST-AI-043` | Tactical legal-option subset |
| `TEST-AI-044` | no path/resource/secret/authority bypass |

## 12. 关联文档

- `DOC-AI-009`：fallback trigger
- `DOC-TIME-004`：utility job
- `DOC-COMBAT-006`：legal combat options owner

---
doc_id: DOC-RESIDENT-003
title: 人格、价值观与偏好
version: 1.0.0
status: approved-for-implementation
owner_domain: resident
canonical_for:
  - personality-profile
  - resident-values-preferences-fears
depends_on:
  - DOC-FOUNDATION-003
  - DOC-RESIDENT-001
  - DOC-RESIDENT-002
requirements:
  - REQ-RESIDENT-003
last_updated: 2026-07-26
---

# 人格、价值观与偏好

## 1. 目的

`REQ-RESIDENT-003`：把人格、价值观、偏好与恐惧定义为可解释的 utility 输入；它们可以调整候选行动效用，但绝不能直接执行 Action、绕过合法集合或写世界状态。

## 2. 非目标

不拥有 AI 规划、Prompt、Action Catalog 或关系变化公式；不把人格当作精神诊断，也不由 ancestry、职业或文化硬编码人格。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Personality Dimension | `0..100` 的稳定倾向 |
| Value | 有权重的抽象优先项，如安全、诚实、共同体 |
| Preference | 对已登记活动/环境/对象类别的弱倾向 |
| Fear | 对风险类别的敏感项，包含强度与可恢复条件 |
| Utility Modifier | AI owner 消费的有界无副作用分数输入 |

## 4. 数据与接口

`DES-RESIDENT-003`：

```json
{
  "schema_version": 1,
  "dimensions": {
    "sociability": 62,
    "diligence": 80,
    "curiosity": 55,
    "empathy": 71,
    "caution": 68,
    "assertiveness": 44
  },
  "values": [
    {"value_id":"value.community","weight_q1000":850},
    {"value_id":"value.honesty","weight_q1000":700}
  ],
  "preferences": [
    {"preference_id":"preference.activity.herbalism","weight_q1000":500}
  ],
  "fears": [
    {"fear_id":"fear.mine_collapse","intensity_q1000":650,"recovery_policy_id":"recovery.fear.gradual_safe_exposure"}
  ],
  "profile_revision": 3
}
```

Resident 发布 `get_personality_utility_inputs(resident_id, revision)`；AI owner 将其映射到自己的 DecisionContext projection。

## 5. 规则与不变量

- `RULE-RESIDENT-012`：六个 dimension 均为整数 `0..100`；缺项按 Catalog 中性值 50，而非随机猜测。
- `RULE-RESIDENT-013`：value/preference/fear 权重为 `-1000..1000` 或 `0..1000` 的定义域值，重复 ID 拒绝。
- `RULE-RESIDENT-014`：人格只产出 utility input；任何人格字段均无 Command、Repository 或 Action execution 权限。
- `RULE-RESIDENT-015`：AI 先从 owner 提供的合法候选集合选择；人格 modifier 每候选总绝对值上限 2000，不能使非法候选合法。
- `RULE-RESIDENT-016`：长期变化必须由已提交事件、变更原因和上限控制；单事件 dimension 变化不超过 2 点、每 30 游戏日累计不超过 10 点。
- `RULE-RESIDENT-017`：ancestry/culture/profession 不提供默认人格；模板必须显式给出并通过组合多样性检查。

## 6. 正常流程

1. AI 的 Orchestrator 获取版本固定的人格投影。
2. AI owner 构建合法候选行动并计算基础 utility。
3. 人格/价值/偏好/恐惧产生有界 modifier 与解释标签。
4. AI 或 Utility AI 选择候选；Owner validator 仍按最新 Revision 校验。
5. 重大已提交经历可提出 `AdjustPersonalityCommand`，Resident 按速率限制提交。

## 7. 边界情况

- 高勤勉不能覆盖昏迷、封路或无工具等前置失败。
- 恐惧可降低进入矿洞的效用，但紧急救援是否可行动仍由合法能力与 AI 权衡决定。
- 两个 value 冲突时同时输出，Resident 不自行决定优先级。
- 模型描述与量化 profile 冲突时，Schema profile 为 utility 输入；文本不改状态。

## 8. 错误与降级

越界权重、未知 ID、重复 ID 或过快漂移返回 `RESIDENT_PERSONALITY_INVALID`。AI owner 不可用时 Utility AI 使用相同 projection；profile 缺损时使用中性投影并记录一次诊断。

## 9. 安全与性能

不得基于人格推断受保护身份、秘密或法律责任。投影不包含自由文本，最大 32 个 value/preference/fear 条目，可按 `profile_revision` 缓存。

## 10. 验收标准

- 静态检查不存在从 Personality 模块直接调用 Action/Repository。
- 非法 Action 在任意人格权重下仍非法。
- 单事件与 30 日人格漂移不超过上限。
- 相同 profile 与候选集合生成相同 utility input。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-RESIDENT-009` | dimension/weight Schema 边界 |
| `TEST-RESIDENT-010` | 非法 Action 不被 personality 合法化 |
| `TEST-RESIDENT-011` | 事件与 30 日漂移限幅 |
| `TEST-RESIDENT-012` | ancestry/职业不产生默认人格 Property Test |

## 12. 关联文档

- `DOC-RESIDENT-004`：短期 Emotion 与 Need
- `DOC-AI-004..006`：下游 ActionProposal 与计划
- `DOC-FOUNDATION-003`：AI projection 边界


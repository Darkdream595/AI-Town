---
doc_id: DOC-FOUNDATION-007
title: 需求、设计与测试追踪矩阵
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - global-traceability-policy
  - foundation-traceability-matrix
  - domain-id-range-reservations
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
requirements:
  - REQ-PRODUCT-001
  - REQ-PRODUCT-002
  - REQ-PRODUCT-003
  - REQ-PRODUCT-004
  - REQ-PRODUCT-005
  - REQ-PRODUCT-006
  - REQ-PRODUCT-007
  - REQ-PRODUCT-008
  - REQ-PRODUCT-009
  - REQ-PRODUCT-010
  - REQ-PRODUCT-011
  - REQ-PRODUCT-012
  - REQ-PRODUCT-013
  - REQ-PRODUCT-014
  - REQ-PRODUCT-015
  - REQ-PRODUCT-016
  - REQ-PRODUCT-017
  - REQ-PRODUCT-018
  - REQ-PRODUCT-019
  - REQ-PRODUCT-020
last_updated: 2026-07-26
---

# 需求、设计与测试追踪矩阵

## 1. 目的

建立从 Must Requirement 到 canonical document、Design ID、Rule ID 和 Test ID 的双向追踪；同时为十五个 subsystem 保留互不冲突的 ID 空间。

## 2. 非目标

本文件不复制 domain 设计内容，也不提前虚构 180 份计划文档中的具体 requirement。domain 文档完成后在其 canonical owner 定义行，本矩阵于全量审计阶段汇总。

## 3. 术语与定义

| 字段 | 定义 |
|---|---|
| Requirement ID | 可验收的外部或系统约束，格式 `REQ-<DOMAIN>-NNN` |
| Design ID | 满足需求的结构/流程，格式 `DES-<DOMAIN>-NNN` |
| Rule ID | 实现不得违反的规则，格式 `RULE-<DOMAIN>-NNN` |
| Test ID | 可执行或可审计验证，格式 `TEST-<DOMAIN>-NNN` |
| `covered` | 至少有 canonical design 和 test，且无已知冲突 |
| `reserved-range` | ID 空间已分配给 owner，但不是一条实际 Requirement |

## 4. 规则与不变量

- `RULE-FOUNDATION-046`：每个 Must Requirement 必须有唯一 canonical document、至少一个 Design ID 和至少一个 Test ID。
- `RULE-FOUNDATION-047`：ID 一经发布不复用；删除需求时状态改为 `retired` 并保留原因与替代 ID。
- `RULE-FOUNDATION-048`：只有 prefix owner 可定义对应 ID；其他 domain 只能引用。
- `RULE-FOUNDATION-049`：范围行不是需求，不计入覆盖率；实际需求必须拆为单独行，禁止使用范围掩盖未追踪项。
- `RULE-FOUNDATION-050`：`Must` 全部 covered 才可通过 G4；`Should` 缺口必须有明确版本与 owner，首版不使用无主 deferred 状态。

## 5. 数据与接口

`DES-FOUNDATION-007`：traceability registry 的机器可读投影包含：

```json
{
  "requirement_id": "REQ-PRODUCT-004",
  "canonical_document_id": "DOC-FOUNDATION-001",
  "design_ids": ["DES-FOUNDATION-002", "DES-FOUNDATION-003"],
  "rule_ids": ["RULE-FOUNDATION-002", "RULE-FOUNDATION-016"],
  "test_ids": ["TEST-FOUNDATION-003", "TEST-FOUNDATION-008"],
  "priority": "Must",
  "status": "covered"
}
```

### 5.1 Foundation requirement matrix

| Requirement ID | Canonical document | Design IDs | Rule IDs | Test IDs | Priority | Status |
|---|---|---|---|---|---|---|
| `REQ-PRODUCT-001` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-002` | `RULE-FOUNDATION-001` | `TEST-FOUNDATION-001` | Must | covered |
| `REQ-PRODUCT-002` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001` | `RULE-FOUNDATION-001` | `TEST-FOUNDATION-001` | Must | covered |
| `REQ-PRODUCT-003` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-003`, `DES-FOUNDATION-005`, `DES-FOUNDATION-006` | `RULE-FOUNDATION-017`, `RULE-FOUNDATION-039..042` | `TEST-FOUNDATION-002`, `TEST-FOUNDATION-020`, `TEST-FOUNDATION-028` | Must | covered |
| `REQ-PRODUCT-004` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-002`, `DES-FOUNDATION-003`, `DES-FOUNDATION-005` | `RULE-FOUNDATION-002..003`, `RULE-FOUNDATION-016` | `TEST-FOUNDATION-003`, `TEST-FOUNDATION-008` | Must | covered |
| `REQ-PRODUCT-005` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-003` | `RULE-FOUNDATION-001`, `RULE-FOUNDATION-009` | `TEST-FOUNDATION-004` | Must | covered |
| `REQ-PRODUCT-006` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-003` | `RULE-FOUNDATION-030` | `TEST-FOUNDATION-004`, `TEST-FOUNDATION-025` | Must | covered |
| `REQ-PRODUCT-007` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-002` | `RULE-FOUNDATION-005`, `RULE-FOUNDATION-007` | `TEST-FOUNDATION-003`, `TEST-FOUNDATION-009`, `TEST-FOUNDATION-011` | Must | covered |
| `REQ-PRODUCT-008` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-002`, `DES-FOUNDATION-005`, `DES-FOUNDATION-006` | `RULE-FOUNDATION-027`, `RULE-FOUNDATION-029`, `RULE-FOUNDATION-038` | `TEST-FOUNDATION-005`, `TEST-FOUNDATION-012`, `TEST-FOUNDATION-023`, `TEST-FOUNDATION-027` | Must | covered |
| `REQ-PRODUCT-009` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-005` | `RULE-FOUNDATION-025` | `TEST-FOUNDATION-005`, `TEST-FOUNDATION-024` | Must | covered |
| `REQ-PRODUCT-010` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-007` | `RULE-FOUNDATION-046`, `RULE-FOUNDATION-050` | `TEST-FOUNDATION-006`, `TEST-FOUNDATION-030` | Must | covered |
| `REQ-PRODUCT-011` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-003` | `RULE-FOUNDATION-001`, `RULE-FOUNDATION-008` | `TEST-FOUNDATION-004` | Must | covered |
| `REQ-PRODUCT-012` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-003` | `RULE-FOUNDATION-011`, `RULE-FOUNDATION-041` | `TEST-FOUNDATION-002`, `TEST-FOUNDATION-016` | Must | covered |
| `REQ-PRODUCT-013` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-003`, `DES-FOUNDATION-005` | `RULE-FOUNDATION-009`, `RULE-FOUNDATION-017` | `TEST-FOUNDATION-002`, `TEST-FOUNDATION-020` | Must | covered |
| `REQ-PRODUCT-014` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-002` | `RULE-FOUNDATION-027`, `RULE-FOUNDATION-029` | `TEST-FOUNDATION-005`, `TEST-FOUNDATION-023` | Must | covered |
| `REQ-PRODUCT-015` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-001`, `DES-FOUNDATION-002` | `RULE-FOUNDATION-001`, `RULE-FOUNDATION-002` | `TEST-FOUNDATION-001`, `TEST-FOUNDATION-008` | Must | covered |
| `REQ-PRODUCT-016` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-004`, `DES-FOUNDATION-005` | `RULE-FOUNDATION-020`, `RULE-FOUNDATION-024` | `TEST-FOUNDATION-007`, `TEST-FOUNDATION-022` | Must | covered |
| `REQ-PRODUCT-017` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-003`, `DES-FOUNDATION-004` | `RULE-FOUNDATION-008`, `RULE-FOUNDATION-015` | `TEST-FOUNDATION-003`, `TEST-FOUNDATION-013`, `TEST-FOUNDATION-019` | Must | covered |
| `REQ-PRODUCT-018` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-005`, `DES-FOUNDATION-006` | `RULE-FOUNDATION-026`, `RULE-FOUNDATION-033`, `RULE-FOUNDATION-035..038` | `TEST-FOUNDATION-005`, `TEST-FOUNDATION-024`, `TEST-FOUNDATION-027` | Must | covered |
| `REQ-PRODUCT-019` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-002`, `DES-FOUNDATION-005` | `RULE-FOUNDATION-024` | `TEST-FOUNDATION-007`, `TEST-FOUNDATION-022` | Must | covered |
| `REQ-PRODUCT-020` | `DOC-FOUNDATION-001` | `DES-FOUNDATION-007`, `DES-FOUNDATION-008` | `RULE-FOUNDATION-046..050`, `RULE-FOUNDATION-051..053` | `TEST-FOUNDATION-006`, `TEST-FOUNDATION-030..032` | Must | covered |

### 5.2 十五个 domain reserved row ranges

这些行是 ID 空间契约，不是实际需求；每个 subsystem 必须将实际 `Must` 拆成单行并替换汇总视图。

| Requirement ID range | Canonical document range | Design ID range | Test ID range | Priority | Status |
|---|---|---|---|---|---|
| `REQ-WORLD-001..999` | `DOC-WORLD-001..012` | `DES-WORLD-001..999` | `TEST-WORLD-001..999` | domain-defined | reserved-range |
| `REQ-MAP-001..999` | `DOC-MAP-001..012` | `DES-MAP-001..999` | `TEST-MAP-001..999` | domain-defined | reserved-range |
| `REQ-RENDER-001..999` | `DOC-RENDER-001..012` | `DES-RENDER-001..999` | `TEST-RENDER-001..999` | domain-defined | reserved-range |
| `REQ-RESIDENT-001..999` | `DOC-RESIDENT-001..012` | `DES-RESIDENT-001..999` | `TEST-RESIDENT-001..999` | domain-defined | reserved-range |
| `REQ-AI-001..999` | `DOC-AI-001..012` | `DES-AI-001..999` | `TEST-AI-001..999` | domain-defined | reserved-range |
| `REQ-MEMORY-001..999` | `DOC-MEMORY-001..012` | `DES-MEMORY-001..999` | `TEST-MEMORY-001..999` | domain-defined | reserved-range |
| `REQ-TIME-001..999` | `DOC-TIME-001..012` | `DES-TIME-001..999` | `TEST-TIME-001..999` | domain-defined | reserved-range |
| `REQ-PLAYER-001..999` | `DOC-PLAYER-001..012` | `DES-PLAYER-001..999` | `TEST-PLAYER-001..999` | domain-defined | reserved-range |
| `REQ-DIALOGUE-001..999` | `DOC-DIALOGUE-001..012` | `DES-DIALOGUE-001..999` | `TEST-DIALOGUE-001..999` | domain-defined | reserved-range |
| `REQ-ECON-001..999` | `DOC-ECON-001..012` | `DES-ECON-001..999` | `TEST-ECON-001..999` | domain-defined | reserved-range |
| `REQ-MAGIC-001..999` | `DOC-MAGIC-001..012` | `DES-MAGIC-001..999` | `TEST-MAGIC-001..999` | domain-defined | reserved-range |
| `REQ-COMBAT-001..999` | `DOC-COMBAT-001..012` | `DES-COMBAT-001..999` | `TEST-COMBAT-001..999` | domain-defined | reserved-range |
| `REQ-EVENT-001..999` | `DOC-EVENT-001..012` | `DES-EVENT-001..999` | `TEST-EVENT-001..999` | domain-defined | reserved-range |
| `REQ-BACKEND-001..999` | `DOC-BACKEND-001..012` | `DES-BACKEND-001..999` | `TEST-BACKEND-001..999` | domain-defined | reserved-range |
| `REQ-RELEASE-001..999` | `DOC-RELEASE-001..012` | `DES-RELEASE-001..999` | `TEST-RELEASE-001..999` | domain-defined | reserved-range |

## 6. 正常流程

1. Canonical owner 在文档中定义 Requirement、Design、Rule 与 Test。
2. 生成器提取 ID、owner、链接和状态，拒绝重复定义。
3. 每个 Must Requirement 建立至少一个设计和测试边。
4. 变更评审从 Requirement 正向检查测试，也从 Test 反向检查业务依据。
5. G4 审计合并十五个 domain 的实际行并计算覆盖率。

## 7. 边界情况

- 一个 Design 可覆盖多个 Requirement，但每条 Requirement 仍独立列出。
- 一个 Requirement 跨 domain 时，产品/发起 domain 保持 canonical owner，其他 domain 定义自己的 supporting Design 并引用它。
- 测试暂不自动化时可使用审计型 Test ID，但必须给出可重复输入、步骤和断言。
- Requirement 被替代时保留旧行并标记 `retired`，新增 `superseded_by`；不得修改旧 ID 语义。

## 8. 错误与降级

发现重复 ID、悬空引用、无测试 Must、无 owner 或范围外需求时，文档 Gate 失败；不得以文字说明代替修复。生成器故障时使用确定性脚本重新提取，人工 spot check 不能宣称全量通过。

## 9. 安全与性能

矩阵不收录 Secret、Prompt 原文或玩家内容。全量提取应限定十六个明确 corpus 目录，线性扫描 188 份 Markdown；禁止扫描受保护路径或无关用户文件。

## 10. 验收标准

- `REQ-PRODUCT-001..020` 恰好二十行，全部 priority `Must`、status `covered`。
- 每行均有 canonical document、Design、Rule、Test。
- 十五个 domain 各有唯一的 Requirement/Design/Test range。
- ID 唯一性、引用解析和 Must coverage 审计无错误。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-FOUNDATION-030` | Foundation 20/20 Must Requirement 具有 design 与 test |
| `TEST-FOUNDATION-031` | 十五组 prefix/range 唯一且与 document owner 一致 |
| `TEST-FOUNDATION-032` | 全量 ID 无重复定义、无悬空引用、无跨 owner 竞争定义 |

## 12. 关联文档

- `DOC-FOUNDATION-001`：二十项产品 Requirement 的 canonical 定义
- `DOC-FOUNDATION-003`：十五个 domain ownership
- `DOC-FOUNDATION-005`：跨系统 Rule
- `DOC-FOUNDATION-008`：188 份文档与 DOC ID 映射

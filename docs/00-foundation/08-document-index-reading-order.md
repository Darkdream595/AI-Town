---
doc_id: DOC-FOUNDATION-008
title: 文档索引与依赖优先阅读顺序
version: 1.0.0
status: approved-for-implementation
owner_domain: foundation
canonical_for:
  - corpus-document-index
  - dependency-first-reading-order
  - canonical-owner-lookup
depends_on:
  - DOC-FOUNDATION-001
  - DOC-FOUNDATION-002
  - DOC-FOUNDATION-003
  - DOC-FOUNDATION-004
  - DOC-FOUNDATION-005
  - DOC-FOUNDATION-006
  - DOC-FOUNDATION-007
requirements:
  - REQ-PRODUCT-020
last_updated: 2026-07-26
---

# 文档索引与依赖优先阅读顺序

## 1. 目的

提供 188 份 corpus 文档的精确 DOC ID、路径、初始状态、dependency-first 阅读顺序和 canonical-owner 查找入口。该索引是文档数量与路径的唯一基线。

## 2. 非目标

本文件不表示 180 份 subsystem 文档已经完成；`planned` 只表示路径与 owner 已分配。内容完成、交叉引用解析和全量审计通过后，才可在 G4 将其状态更新为 `approved-for-implementation`。

## 3. 术语与定义

| 术语 | 定义 |
|---|---|
| Corpus | 本索引中的 8 份 foundation + 15 × 12 份 subsystem 文档 |
| Reading wave | 前一波合约可作为后一波输入的依赖层 |
| `approved-for-implementation` | 内容已完成当前 Task 的结构与范围审计 |
| `planned` | DOC ID、owner 和路径已保留，正文将在对应 Task 完成 |
| Canonical lookup | 从概念定位到唯一 owner domain 与文档范围 |

## 4. 规则与不变量

- `RULE-FOUNDATION-051`：Corpus 文件总数必须恰好为 `8 + 15 × 12 = 188`。
- `RULE-FOUNDATION-052`：每个 DOC ID 与路径一一对应；重命名必须原子更新索引和全部引用，不得复用旧 DOC ID。
- `RULE-FOUNDATION-053`：阅读顺序按依赖层而非文件夹编号推导；实现者先读所有 `depends_on` 再读当前文档。
- `RULE-FOUNDATION-054`：初始状态只能是 8 个 foundation `approved-for-implementation` 和 180 个 subsystem `planned`。
- `RULE-FOUNDATION-055`：状态只能在对应正文、结构、ID 与链接审计通过后升级，不得由文件存在性自动推断。

## 5. 数据与接口

`DES-FOUNDATION-008`：索引记录为 `{doc_id, path, owner_domain, reading_wave, status}`，DOC ID 从文件 YAML front matter 校验，路径以 repository-relative POSIX separator 保存。

### 5.1 Wave 0：跨系统总纲（8）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-FOUNDATION-001` | `docs/00-foundation/01-product-vision-success-criteria.md` | approved-for-implementation |
| `DOC-FOUNDATION-002` | `docs/00-foundation/02-overall-architecture.md` | approved-for-implementation |
| `DOC-FOUNDATION-003` | `docs/00-foundation/03-system-boundaries-dependency-map.md` | approved-for-implementation |
| `DOC-FOUNDATION-004` | `docs/00-foundation/04-global-glossary.md` | approved-for-implementation |
| `DOC-FOUNDATION-005` | `docs/00-foundation/05-cross-system-invariants.md` | approved-for-implementation |
| `DOC-FOUNDATION-006` | `docs/00-foundation/06-id-time-coordinate-standards.md` | approved-for-implementation |
| `DOC-FOUNDATION-007` | `docs/00-foundation/07-requirement-design-test-traceability.md` | approved-for-implementation |
| `DOC-FOUNDATION-008` | `docs/00-foundation/08-document-index-reading-order.md` | approved-for-implementation |

### 5.2 Wave 1：世界与游戏设计（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-WORLD-001` | `docs/01-world-design/01-product-positioning-player-experience.md` | planned |
| `DOC-WORLD-002` | `docs/01-world-design/02-core-gameplay-loop.md` | planned |
| `DOC-WORLD-003` | `docs/01-world-design/03-world-origin-history.md` | planned |
| `DOC-WORLD-004` | `docs/01-world-design/04-geography-regions.md` | planned |
| `DOC-WORLD-005` | `docs/01-world-design/05-races-cultures.md` | planned |
| `DOC-WORLD-006` | `docs/01-world-design/06-kingdoms-organizations-factions.md` | planned |
| `DOC-WORLD-007` | `docs/01-world-design/07-religion-calendar-festivals.md` | planned |
| `DOC-WORLD-008` | `docs/01-world-design/08-laws-social-norms.md` | planned |
| `DOC-WORLD-009` | `docs/01-world-design/09-japanese-western-fantasy-style.md` | planned |
| `DOC-WORLD-010` | `docs/01-world-design/10-dark-content-boundaries.md` | planned |
| `DOC-WORLD-011` | `docs/01-world-design/11-canon-content-consistency.md` | planned |
| `DOC-WORLD-012` | `docs/01-world-design/12-world-design-acceptance.md` | planned |

### 5.3 Wave 2：地图、空间与导航（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-MAP-001` | `docs/02-map-navigation/01-world-coordinate-system.md` | planned |
| `DOC-MAP-002` | `docs/02-map-navigation/02-region-topology.md` | planned |
| `DOC-MAP-003` | `docs/02-map-navigation/03-ai-map-generation-spec.md` | planned |
| `DOC-MAP-004` | `docs/02-map-navigation/04-map-layering.md` | planned |
| `DOC-MAP-005` | `docs/02-map-navigation/05-walkable-area-definition.md` | planned |
| `DOC-MAP-006` | `docs/02-map-navigation/06-collision-polygon-spec.md` | planned |
| `DOC-MAP-007` | `docs/02-map-navigation/07-navigation-grid-pathfinding.md` | planned |
| `DOC-MAP-008` | `docs/02-map-navigation/08-doors-entrances-interiors.md` | planned |
| `DOC-MAP-009` | `docs/02-map-navigation/09-region-transitions.md` | planned |
| `DOC-MAP-010` | `docs/02-map-navigation/10-dynamic-obstacle-updates.md` | planned |
| `DOC-MAP-011` | `docs/02-map-navigation/11-camera-map-boundaries.md` | planned |
| `DOC-MAP-012` | `docs/02-map-navigation/12-navigation-collision-tests.md` | planned |

### 5.4 Wave 3A：渲染、美术与音频（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-RENDER-001` | `docs/03-rendering-art-audio/01-phaser-rendering-architecture.md` | planned |
| `DOC-RENDER-002` | `docs/03-rendering-art-audio/02-scene-lifecycle.md` | planned |
| `DOC-RENDER-003` | `docs/03-rendering-art-audio/03-map-compositing-pipeline.md` | planned |
| `DOC-RENDER-004` | `docs/03-rendering-art-audio/04-character-sprite-spec.md` | planned |
| `DOC-RENDER-005` | `docs/03-rendering-art-audio/05-animation-state-machine.md` | planned |
| `DOC-RENDER-006` | `docs/03-rendering-art-audio/06-structure-environment-rendering.md` | planned |
| `DOC-RENDER-007` | `docs/03-rendering-art-audio/07-day-night-weather-visuals.md` | planned |
| `DOC-RENDER-008` | `docs/03-rendering-art-audio/08-magic-combat-vfx.md` | planned |
| `DOC-RENDER-009` | `docs/03-rendering-art-audio/09-parchment-ui-visual-system.md` | planned |
| `DOC-RENDER-010` | `docs/03-rendering-art-audio/10-music-environment-audio.md` | planned |
| `DOC-RENDER-011` | `docs/03-rendering-art-audio/11-asset-manifest-fallbacks.md` | planned |
| `DOC-RENDER-012` | `docs/03-rendering-art-audio/12-performance-visual-qa.md` | planned |

### 5.5 Wave 3B：居民与生命周期（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-RESIDENT-001` | `docs/04-residents-lifecycle/01-resident-data-model.md` | planned |
| `DOC-RESIDENT-002` | `docs/04-residents-lifecycle/02-identity-race-appearance.md` | planned |
| `DOC-RESIDENT-003` | `docs/04-residents-lifecycle/03-personality-values.md` | planned |
| `DOC-RESIDENT-004` | `docs/04-residents-lifecycle/04-needs-emotions.md` | planned |
| `DOC-RESIDENT-005` | `docs/04-residents-lifecycle/05-skills-abilities.md` | planned |
| `DOC-RESIDENT-006` | `docs/04-residents-lifecycle/06-profession-residence.md` | planned |
| `DOC-RESIDENT-007` | `docs/04-residents-lifecycle/07-health-injury-illness.md` | planned |
| `DOC-RESIDENT-008` | `docs/04-residents-lifecycle/08-age-non-permanent-death.md` | planned |
| `DOC-RESIDENT-009` | `docs/04-residents-lifecycle/09-daily-life-structure.md` | planned |
| `DOC-RESIDENT-010` | `docs/04-residents-lifecycle/10-inventory-ownership.md` | planned |
| `DOC-RESIDENT-011` | `docs/04-residents-lifecycle/11-resident-creation-initialization.md` | planned |
| `DOC-RESIDENT-012` | `docs/04-residents-lifecycle/12-resident-system-tests.md` | planned |

### 5.6 Wave 4A：记忆与社会关系（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-MEMORY-001` | `docs/06-memory-social/01-memory-data-model.md` | planned |
| `DOC-MEMORY-002` | `docs/06-memory-social/02-memory-write-rules.md` | planned |
| `DOC-MEMORY-003` | `docs/06-memory-social/03-relevant-memory-retrieval.md` | planned |
| `DOC-MEMORY-004` | `docs/06-memory-social/04-memory-consolidation-summary.md` | planned |
| `DOC-MEMORY-005` | `docs/06-memory-social/05-forgetting-importance-decay.md` | planned |
| `DOC-MEMORY-006` | `docs/06-memory-social/06-multidimensional-relationships.md` | planned |
| `DOC-MEMORY-007` | `docs/06-memory-social/07-social-graph.md` | planned |
| `DOC-MEMORY-008` | `docs/06-memory-social/08-rumor-propagation.md` | planned |
| `DOC-MEMORY-009` | `docs/06-memory-social/09-secrets-privacy.md` | planned |
| `DOC-MEMORY-010` | `docs/06-memory-social/10-belief-objective-fact-separation.md` | planned |
| `DOC-MEMORY-011` | `docs/06-memory-social/11-player-behavior-memory.md` | planned |
| `DOC-MEMORY-012` | `docs/06-memory-social/12-memory-relationship-tests.md` | planned |

### 5.7 Wave 4B：时间、调度与世界模拟（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-TIME-001` | `docs/07-time-simulation/01-game-time-model.md` | planned |
| `DOC-TIME-002` | `docs/07-time-simulation/02-pause-speed-control.md` | planned |
| `DOC-TIME-003` | `docs/07-time-simulation/03-simulation-tick.md` | planned |
| `DOC-TIME-004` | `docs/07-time-simulation/04-resident-scheduler.md` | planned |
| `DOC-TIME-005` | `docs/07-time-simulation/05-active-warm-background-tiers.md` | planned |
| `DOC-TIME-006` | `docs/07-time-simulation/06-long-running-actions.md` | planned |
| `DOC-TIME-007` | `docs/07-time-simulation/07-concurrent-action-conflicts.md` | planned |
| `DOC-TIME-008` | `docs/07-time-simulation/08-world-periodic-updates.md` | planned |
| `DOC-TIME-009` | `docs/07-time-simulation/09-closed-game-pause.md` | planned |
| `DOC-TIME-010` | `docs/07-time-simulation/10-seed-reproducibility.md` | planned |
| `DOC-TIME-011` | `docs/07-time-simulation/11-performance-load-budget.md` | planned |
| `DOC-TIME-012` | `docs/07-time-simulation/12-time-simulation-tests.md` | planned |

### 5.8 Wave 5A：经济、职业与物品（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-ECON-001` | `docs/10-economy-items/01-currency-system.md` | planned |
| `DOC-ECON-002` | `docs/10-economy-items/02-professions-workplaces.md` | planned |
| `DOC-ECON-003` | `docs/10-economy-items/03-work-schedules-income.md` | planned |
| `DOC-ECON-004` | `docs/10-economy-items/04-item-data-model.md` | planned |
| `DOC-ECON-005` | `docs/10-economy-items/05-inventory-rules.md` | planned |
| `DOC-ECON-006` | `docs/10-economy-items/06-transaction-model.md` | planned |
| `DOC-ECON-007` | `docs/10-economy-items/07-shops-services.md` | planned |
| `DOC-ECON-008` | `docs/10-economy-items/08-pricing-model.md` | planned |
| `DOC-ECON-009` | `docs/10-economy-items/09-basic-supply-demand.md` | planned |
| `DOC-ECON-010` | `docs/10-economy-items/10-crafting-resource-consumption.md` | planned |
| `DOC-ECON-011` | `docs/10-economy-items/11-property-building-ownership.md` | planned |
| `DOC-ECON-012` | `docs/10-economy-items/12-economic-balance-tests.md` | planned |

### 5.9 Wave 5B：魔法系统（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-MAGIC-001` | `docs/11-magic/01-magic-worldview.md` | planned |
| `DOC-MAGIC-002` | `docs/11-magic/02-magic-schools.md` | planned |
| `DOC-MAGIC-003` | `docs/11-magic/03-mana-recovery.md` | planned |
| `DOC-MAGIC-004` | `docs/11-magic/04-spell-data-model.md` | planned |
| `DOC-MAGIC-005` | `docs/11-magic/05-casting-legality.md` | planned |
| `DOC-MAGIC-006` | `docs/11-magic/06-magic-learning-growth.md` | planned |
| `DOC-MAGIC-007` | `docs/11-magic/07-resident-autonomous-casting.md` | planned |
| `DOC-MAGIC-008` | `docs/11-magic/08-player-casting.md` | planned |
| `DOC-MAGIC-009` | `docs/11-magic/09-magic-environment-interactions.md` | planned |
| `DOC-MAGIC-010` | `docs/11-magic/10-magical-items.md` | planned |
| `DOC-MAGIC-011` | `docs/11-magic/11-magic-vfx-audio.md` | planned |
| `DOC-MAGIC-012` | `docs/11-magic/12-magic-balance-tests.md` | planned |

### 5.10 Wave 5C：回合制战斗与健康（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-COMBAT-001` | `docs/12-combat-health/01-encounter-trigger-rules.md` | planned |
| `DOC-COMBAT-002` | `docs/12-combat-health/02-turn-order.md` | planned |
| `DOC-COMBAT-003` | `docs/12-combat-health/03-combat-actions.md` | planned |
| `DOC-COMBAT-004` | `docs/12-combat-health/04-combat-stats-formulas.md` | planned |
| `DOC-COMBAT-005` | `docs/12-combat-health/05-status-effects.md` | planned |
| `DOC-COMBAT-006` | `docs/12-combat-health/06-damage-healing.md` | planned |
| `DOC-COMBAT-007` | `docs/12-combat-health/07-npc-tactical-decisions.md` | planned |
| `DOC-COMBAT-008` | `docs/12-combat-health/08-player-combat-ui.md` | planned |
| `DOC-COMBAT-009` | `docs/12-combat-health/09-escape-defeat-non-permanent-death.md` | planned |
| `DOC-COMBAT-010` | `docs/12-combat-health/10-loot-consequences.md` | planned |
| `DOC-COMBAT-011` | `docs/12-combat-health/11-combat-world-event-integration.md` | planned |
| `DOC-COMBAT-012` | `docs/12-combat-health/12-combat-test-matrix.md` | planned |

### 5.11 Wave 5D：事件、任务、建筑与环境（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-EVENT-001` | `docs/13-events-building-environment/01-world-event-engine.md` | planned |
| `DOC-EVENT-002` | `docs/13-events-building-environment/02-event-trigger-conditions.md` | planned |
| `DOC-EVENT-003` | `docs/13-events-building-environment/03-ai-event-director.md` | planned |
| `DOC-EVENT-004` | `docs/13-events-building-environment/04-quest-lifecycle.md` | planned |
| `DOC-EVENT-005` | `docs/13-events-building-environment/05-event-consequence-propagation.md` | planned |
| `DOC-EVENT-006` | `docs/13-events-building-environment/06-weather-natural-environment.md` | planned |
| `DOC-EVENT-007` | `docs/13-events-building-environment/07-building-data-model.md` | planned |
| `DOC-EVENT-008` | `docs/13-events-building-environment/08-building-placement-rules.md` | planned |
| `DOC-EVENT-009` | `docs/13-events-building-environment/09-construction-upgrades.md` | planned |
| `DOC-EVENT-010` | `docs/13-events-building-environment/10-destruction-repair.md` | planned |
| `DOC-EVENT-011` | `docs/13-events-building-environment/11-world-diff-map-sync.md` | planned |
| `DOC-EVENT-012` | `docs/13-events-building-environment/12-event-building-recovery-tests.md` | planned |

### 5.12 Wave 6A：AI 决策与模型编排（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-AI-001` | `docs/05-ai-orchestration/01-cognition-pipeline.md` | planned |
| `DOC-AI-002` | `docs/05-ai-orchestration/02-resident-visible-context.md` | planned |
| `DOC-AI-003` | `docs/05-ai-orchestration/03-prompt-layering.md` | planned |
| `DOC-AI-004` | `docs/05-ai-orchestration/04-action-proposal-schema.md` | planned |
| `DOC-AI-005` | `docs/05-ai-orchestration/05-tool-action-catalog.md` | planned |
| `DOC-AI-006` | `docs/05-ai-orchestration/06-daily-hourly-immediate-planning.md` | planned |
| `DOC-AI-007` | `docs/05-ai-orchestration/07-thinking-mode-routing.md` | planned |
| `DOC-AI-008` | `docs/05-ai-orchestration/08-token-cache-cost-control.md` | planned |
| `DOC-AI-009` | `docs/05-ai-orchestration/09-concurrency-request-scheduling.md` | planned |
| `DOC-AI-010` | `docs/05-ai-orchestration/10-action-validation-repair.md` | planned |
| `DOC-AI-011` | `docs/05-ai-orchestration/11-utility-ai-fallback.md` | planned |
| `DOC-AI-012` | `docs/05-ai-orchestration/12-ai-behavior-evaluation.md` | planned |

### 5.13 Wave 6B：对话与交流（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-DIALOGUE-001` | `docs/09-dialogue/01-conversation-lifecycle.md` | planned |
| `DOC-DIALOGUE-002` | `docs/09-dialogue/02-distance-participation-conditions.md` | planned |
| `DOC-DIALOGUE-003` | `docs/09-dialogue/03-dialogue-context-construction.md` | planned |
| `DOC-DIALOGUE-004` | `docs/09-dialogue/04-natural-language-intent.md` | planned |
| `DOC-DIALOGUE-005` | `docs/09-dialogue/05-speech-act-model.md` | planned |
| `DOC-DIALOGUE-006` | `docs/09-dialogue/06-emotion-tone.md` | planned |
| `DOC-DIALOGUE-007` | `docs/09-dialogue/07-interruption-exit.md` | planned |
| `DOC-DIALOGUE-008` | `docs/09-dialogue/08-group-dialogue.md` | planned |
| `DOC-DIALOGUE-009` | `docs/09-dialogue/09-dialogue-relationship-effects.md` | planned |
| `DOC-DIALOGUE-010` | `docs/09-dialogue/10-chinese-localization.md` | planned |
| `DOC-DIALOGUE-011` | `docs/09-dialogue/11-dialogue-safety-content-boundaries.md` | planned |
| `DOC-DIALOGUE-012` | `docs/09-dialogue/12-dialogue-system-tests.md` | planned |

### 5.14 Wave 6C：玩家与镇长模式（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-PLAYER-001` | `docs/08-player-mayor/01-player-resident-creation.md` | planned |
| `DOC-PLAYER-002` | `docs/08-player-mayor/02-player-movement-control.md` | planned |
| `DOC-PLAYER-003` | `docs/08-player-mayor/03-resident-mayor-mode-switch.md` | planned |
| `DOC-PLAYER-004` | `docs/08-player-mayor/04-player-interaction-capabilities.md` | planned |
| `DOC-PLAYER-005` | `docs/08-player-mayor/05-natural-language-input.md` | planned |
| `DOC-PLAYER-006` | `docs/08-player-mayor/06-player-world-impact.md` | planned |
| `DOC-PLAYER-007` | `docs/08-player-mayor/07-resident-mode-permissions.md` | planned |
| `DOC-PLAYER-008` | `docs/08-player-mayor/08-mayor-mode-permissions.md` | planned |
| `DOC-PLAYER-009` | `docs/08-player-mayor/09-admin-command-audit.md` | planned |
| `DOC-PLAYER-010` | `docs/08-player-mayor/10-camera-fullscreen-control.md` | planned |
| `DOC-PLAYER-011` | `docs/08-player-mayor/11-input-guidance-accessibility.md` | planned |
| `DOC-PLAYER-012` | `docs/08-player-mayor/12-player-system-acceptance.md` | planned |

### 5.15 Wave 7：后端、API 与安全（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-BACKEND-001` | `docs/14-backend-api-security/01-fastapi-service-architecture.md` | planned |
| `DOC-BACKEND-002` | `docs/14-backend-api-security/02-domain-module-boundaries.md` | planned |
| `DOC-BACKEND-003` | `docs/14-backend-api-security/03-websocket-lifecycle.md` | planned |
| `DOC-BACKEND-004` | `docs/14-backend-api-security/04-rest-api.md` | planned |
| `DOC-BACKEND-005` | `docs/14-backend-api-security/05-command-protocol.md` | planned |
| `DOC-BACKEND-006` | `docs/14-backend-api-security/06-domain-event-protocol.md` | planned |
| `DOC-BACKEND-007` | `docs/14-backend-api-security/07-schema-versioning.md` | planned |
| `DOC-BACKEND-008` | `docs/14-backend-api-security/08-local-session-permissions.md` | planned |
| `DOC-BACKEND-009` | `docs/14-backend-api-security/09-deepseek-key-protection.md` | planned |
| `DOC-BACKEND-010` | `docs/14-backend-api-security/10-transaction-idempotency.md` | planned |
| `DOC-BACKEND-011` | `docs/14-backend-api-security/11-error-codes-recovery.md` | planned |
| `DOC-BACKEND-012` | `docs/14-backend-api-security/12-performance-logging-tests.md` | planned |

### 5.16 Wave 8：存档、启动与发布质量（12）

| DOC ID | 路径 | 状态 |
|---|---|---|
| `DOC-RELEASE-001` | `docs/15-persistence-release-quality/01-sqlite-data-model.md` | planned |
| `DOC-RELEASE-002` | `docs/15-persistence-release-quality/02-database-migrations.md` | planned |
| `DOC-RELEASE-003` | `docs/15-persistence-release-quality/03-snapshot-event-log.md` | planned |
| `DOC-RELEASE-004` | `docs/15-persistence-release-quality/04-auto-manual-saves.md` | planned |
| `DOC-RELEASE-005` | `docs/15-persistence-release-quality/05-multi-world-management.md` | planned |
| `DOC-RELEASE-006` | `docs/15-persistence-release-quality/06-backup-corruption-recovery.md` | planned |
| `DOC-RELEASE-007` | `docs/15-persistence-release-quality/07-configuration-secret-management.md` | planned |
| `DOC-RELEASE-008` | `docs/15-persistence-release-quality/08-double-click-launcher.md` | planned |
| `DOC-RELEASE-009` | `docs/15-persistence-release-quality/09-bundled-runtime-release-package.md` | planned |
| `DOC-RELEASE-010` | `docs/15-persistence-release-quality/10-logging-diagnostics-package.md` | planned |
| `DOC-RELEASE-011` | `docs/15-persistence-release-quality/11-project-test-strategy.md` | planned |
| `DOC-RELEASE-012` | `docs/15-persistence-release-quality/12-release-acceptance-checklist.md` | planned |

### 5.17 状态计数

| 状态 | Foundation | Subsystem | 合计 |
|---|---:|---:|---:|
| approved-for-implementation | 8 | 0 | 8 |
| planned | 0 | 180 | 180 |
| **总计** | **8** | **180** | **188** |

## 6. 正常流程

1. 新参与者依次阅读 `DOC-FOUNDATION-001..008`。
2. 按 Wave 1–8 阅读；同一 wave 内先读取当前文档 YAML 的 `depends_on`。
3. 查找规则时先定位第 5 节的 DOC ID，再到第 11 节 owner 表确定 canonical domain。
4. 对正文完成的文档运行 YAML、十二节、ID、围栏、链接和 whitespace 审计。
5. 只有审计通过才将索引状态从 `planned` 更新为 `approved-for-implementation`。

## 7. 边界情况

- 同一 wave 不代表文档互不依赖，YAML `depends_on` 仍是精确顺序。
- 一个概念跨多个 domain 时，canonical owner 定义写规则，consumer 文档只引用。
- 文件重命名不创建新语义时保留 DOC ID；语义拆分时分配新 DOC ID 并保留迁移映射。
- 最终审计发现范围外第 189 份 corpus 文档时必须移出 corpus 或合并到 owner，不能更新目标总数。

## 8. 错误与降级

索引路径不存在、DOC ID 不匹配、状态计数不为 188 或链接失效时，G3/G4 失败。索引生成工具不可用时可用 PowerShell 对十六个明确目录验证，但不能通过扩大扫描范围或忽略错误降级。

## 9. 安全与性能

索引审计只访问本表列出的明确 corpus 路径，不读取其他目录。188 条记录可全量加载；构建期生成 `doc_id -> path` 与 `canonical_topic -> owner` 两个不可变映射，重复键立即失败。

## 10. 验收标准

- 本文件恰好列出 188 条 DOC 记录：8 条 foundation、每个 subsystem 12 条。
- 路径与实施计划逐字符一致，DOC prefix 与 owner 一致。
- 初始状态计数为 8 approved + 180 planned。
- reading wave 满足 `DOC-FOUNDATION -> WORLD -> MAP/RESIDENT -> MEMORY/TIME/... -> BACKEND -> RELEASE` 的依赖方向。
- canonical-owner lookup 覆盖十五个 subsystem 且无重复 owner。

## 11. 测试追踪

| 测试 ID | 断言 |
|---|---|
| `TEST-FOUNDATION-033` | 从本文件解析出恰好 188 个唯一 DOC ID 和 188 个唯一路径 |
| `TEST-FOUNDATION-034` | foundation=8、subsystem domain=15、每 domain=12、planned=180 |
| `TEST-FOUNDATION-035` | 所有 `depends_on` 指向已登记 DOC ID 且 reading graph 无环 |
| `TEST-FOUNDATION-036` | DOC prefix、路径目录与 canonical owner 三者一致 |

## 12. 关联文档

### Canonical-owner lookup

| Canonical topic | Owner domain | 文档范围 |
|---|---|---|
| 产品边界、全局架构、共享术语、不变量、基元、追踪 | `FOUNDATION` | `DOC-FOUNDATION-001..008` |
| 世界 lore、区域身份、文化、法律、Canon | `WORLD` | `DOC-WORLD-001..012` |
| 坐标细化、Walkability、Collision、Navigation | `MAP` | `DOC-MAP-001..012` |
| Scene、Asset、Animation、UI、Audio | `RENDER` | `DOC-RENDER-001..012` |
| Resident aggregate、Needs、健康、生命周期 | `RESIDENT` | `DOC-RESIDENT-001..012` |
| DecisionContext、Prompt、ActionProposal、Model routing | `AI` | `DOC-AI-001..012` |
| Memory、Belief、关系、Rumor、Secret | `MEMORY` | `DOC-MEMORY-001..012` |
| GameTime、Tick、调度、长任务、Seed stream | `TIME` | `DOC-TIME-001..012` |
| Player identity、模式、输入、Mayor/Admin permission | `PLAYER` | `DOC-PLAYER-001..012` |
| Conversation、Speech Act、对话安全 | `DIALOGUE` | `DOC-DIALOGUE-001..012` |
| Currency、Item、Inventory、Transaction、价格 | `ECON` | `DOC-ECON-001..012` |
| Mana、SpellDefinition、施法规则 | `MAGIC` | `DOC-MAGIC-001..012` |
| Encounter、Turn、公式、伤害、战斗结果 | `COMBAT` | `DOC-COMBAT-001..012` |
| WorldEvent、Quest、Weather、Building、WorldDiff | `EVENT` | `DOC-EVENT-001..012` |
| FastAPI、REST/WebSocket、Envelope、Session、安全 | `BACKEND` | `DOC-BACKEND-001..012` |
| SQLite、Snapshot、存档、Launcher、Package、质量 Gate | `RELEASE` | `DOC-RELEASE-001..012` |

- `DOC-FOUNDATION-003`：Domain 边界、依赖与 data ownership 的规范说明
- `DOC-FOUNDATION-007`：Requirement/Design/Test 追踪与 ID ranges

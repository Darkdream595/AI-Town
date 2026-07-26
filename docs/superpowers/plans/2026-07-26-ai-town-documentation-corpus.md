# AI Town Documentation Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continuously produce, cross-link, audit, and commit the complete 188-document AI Town specification corpus before any game implementation begins.

**Architecture:** The corpus has eight cross-system foundation documents and fifteen bounded subsystem directories containing twelve documents each. Foundation documents own global terminology and invariants; subsystem documents own domain rules and reference other domains by stable IDs instead of duplicating definitions.

**Tech Stack:** Markdown, Mermaid, JSON examples, JSON Schema terminology, Git, PowerShell, `rg`

## Global Constraints

- Communicate and write visible documentation in Chinese; preserve English technical names, identifiers, protocols, and type names.
- Target Windows 10/11 and a local FastAPI authority server with a Phaser 3 browser client.
- Use `deepseek-v4-flash` with `https://api.deepseek.com`; do not use retired compatibility model names.
- Produce exactly 188 documents: eight foundation documents plus fifteen subsystems with twelve documents each.
- Do not create game source code, database files, formal image assets, dependency manifests, or runtime packages during this plan.
- Once document production starts, execute all tasks continuously without per-document or per-subsystem user review.
- Commit after each bounded task for recovery, but do not pause for approval between commits.
- Ask the user for one acceptance review only after all 188 documents and the final audits are complete.
- Never read, scan, copy, stage, test, or package any path matching `old-dont-look*`.
- Never use `git add .`; stage only the explicit documentation paths produced by the current task.
- Every document must contain purpose, non-goals, terminology, rules, invariants, normal flows, boundary cases, failure/degradation, interfaces, security/performance impact, acceptance criteria, and test IDs where applicable.
- Each rule has one canonical owner. Other documents reference the owner by stable ID and do not restate the rule as a competing definition.
- Do not leave unresolved placeholders, ambiguous alternatives, or unowned requirements.
- Use requirement IDs in the form `REQ-<DOMAIN>-NNN`, design IDs as `DES-<DOMAIN>-NNN`, rule IDs as `RULE-<DOMAIN>-NNN`, and test IDs as `TEST-<DOMAIN>-NNN`.
- Use lowercase kebab-case filenames with a two-digit ordering prefix.

## Document Header Contract

Every corpus document starts with YAML front matter containing these keys in this order:

```yaml
---
doc_id: DOC-MAP-001
title: 世界坐标系
version: 1.0.0
status: approved-for-implementation
owner_domain: map
canonical_for:
  - world-coordinate-system
depends_on:
  - DOC-FOUNDATION-006
requirements:
  - REQ-MAP-001
last_updated: 2026-07-26
---
```

Each document then uses this section order:

```text
# Title
## 1. 目的
## 2. 非目标
## 3. 术语与定义
## 4. 规则与不变量
## 5. 数据与接口
## 6. 正常流程
## 7. 边界情况
## 8. 错误与降级
## 9. 安全与性能
## 10. 验收标准
## 11. 测试追踪
## 12. 关联文档
```

Sections that genuinely do not apply must state the concrete reason. They must not be silently omitted.

## Corpus Layout

```text
docs/
├─ 00-foundation/
├─ 01-world-design/
├─ 02-map-navigation/
├─ 03-rendering-art-audio/
├─ 04-residents-lifecycle/
├─ 05-ai-orchestration/
├─ 06-memory-social/
├─ 07-time-simulation/
├─ 08-player-mayor/
├─ 09-dialogue/
├─ 10-economy-items/
├─ 11-magic/
├─ 12-combat-health/
├─ 13-events-building-environment/
├─ 14-backend-api-security/
└─ 15-persistence-release-quality/
```

---

### Task 1: Cross-System Foundation

**Files:**
- Create: `docs/00-foundation/01-product-vision-success-criteria.md`
- Create: `docs/00-foundation/02-overall-architecture.md`
- Create: `docs/00-foundation/03-system-boundaries-dependency-map.md`
- Create: `docs/00-foundation/04-global-glossary.md`
- Create: `docs/00-foundation/05-cross-system-invariants.md`
- Create: `docs/00-foundation/06-id-time-coordinate-standards.md`
- Create: `docs/00-foundation/07-requirement-design-test-traceability.md`
- Create: `docs/00-foundation/08-document-index-reading-order.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-26-ai-town-system-design.md`
- Produces: `DOC-FOUNDATION-001..008`, global vocabulary, domain ownership, stable ID rules, reading order, and traceability tables used by every later task.

- [ ] **Step 1: Write product vision and measurable success criteria**

Create `01-product-vision-success-criteria.md` with player promise, first-version scope, explicit exclusions, ten completion criteria, product risks, and `REQ-PRODUCT-001..020`.

- [ ] **Step 2: Write the authoritative architecture**

Create `02-overall-architecture.md` with the local Client–Server diagram, backend authority boundary, AI proposal pipeline, frontend rendering boundary, queue isolation, module responsibilities, and recovery flow.

- [ ] **Step 3: Write system boundaries and dependency direction**

Create `03-system-boundaries-dependency-map.md` with all fifteen domains, allowed dependencies, forbidden dependencies, canonical data ownership, and Mermaid dependency graphs without cycles at the domain layer.

- [ ] **Step 4: Write the global glossary**

Create `04-global-glossary.md` defining every shared English identifier and Chinese display term, including `ActionProposal`, `PlayerCommand`, `DomainEvent`, `WorldEvent`, `Quest`, `WorldDiff`, `Revision`, `Reservation`, `Snapshot`, `Semantic Node`, `Walkability`, and `Collision`.

- [ ] **Step 5: Write cross-system invariants**

Create `05-cross-system-invariants.md` with invariant IDs covering authority, position legality, ownership, money, knowledge access, event causality, idempotency, Revision monotonicity, secret handling, non-permanent resident death, and Seed behavior.

- [ ] **Step 6: Write ID, time, and coordinate standards**

Create `06-id-time-coordinate-standards.md` with stable ID grammar, ULID usage, world and local coordinates, direction conventions, integer currency units, `RealTime`, `GameTime`, `TurnTime`, timestamp serialization, and unit conversion rules.

- [ ] **Step 7: Create the traceability matrix**

Create `07-requirement-design-test-traceability.md` with a row for every foundation requirement and reserved row ranges for all fifteen domains. Each row has requirement ID, canonical document, design IDs, test IDs, priority, and status.

- [ ] **Step 8: Create the document index**

Create `08-document-index-reading-order.md` listing exactly 188 planned documents, dependency-first reading order, canonical-owner lookup, and document status counts initialized to the eight completed foundation documents plus 180 planned subsystem documents.

- [ ] **Step 9: Verify and commit foundation documents**

Run:

```powershell
$files = Get-ChildItem -LiteralPath docs/00-foundation -File
if ($files.Count -ne 8) { throw "Expected 8 foundation documents, found $($files.Count)" }
rg -n "REQ-|DES-|RULE-|TEST-" docs/00-foundation
git diff --check -- docs/00-foundation
git add -- docs/00-foundation
git commit -m "docs: 建立 AI 小镇跨系统总纲"
```

Expected: eight files, stable ID matches in every file, no whitespace errors, one commit.

### Task 2: World and Game Design

**Files:**
- Create: `docs/01-world-design/01-product-positioning-player-experience.md`
- Create: `docs/01-world-design/02-core-gameplay-loop.md`
- Create: `docs/01-world-design/03-world-origin-history.md`
- Create: `docs/01-world-design/04-geography-regions.md`
- Create: `docs/01-world-design/05-races-cultures.md`
- Create: `docs/01-world-design/06-kingdoms-organizations-factions.md`
- Create: `docs/01-world-design/07-religion-calendar-festivals.md`
- Create: `docs/01-world-design/08-laws-social-norms.md`
- Create: `docs/01-world-design/09-japanese-western-fantasy-style.md`
- Create: `docs/01-world-design/10-dark-content-boundaries.md`
- Create: `docs/01-world-design/11-canon-content-consistency.md`
- Create: `docs/01-world-design/12-world-design-acceptance.md`

**Interfaces:**
- Consumes: `DOC-FOUNDATION-001..008`
- Produces: `DOC-WORLD-001..012`, `REQ-WORLD-*`, canonical lore, tone, legal context, and content constraints used by residents, AI, magic, dialogue, events, and art.

- [ ] **Step 1: Write documents 01–03**

Define the player experience, exploration–conversation–relationship–event loop, world origin, historical eras, the current year, and the reasons a mixed human/magic settlement exists.

- [ ] **Step 2: Write documents 04–06**

Define Crown Creek Town, Twilight Whisper Forest, Silver Ash Mine, cultures, races, kingdom authority, town institutions, guilds, faith groups, and faction tensions without adding a fourth playable region.

- [ ] **Step 3: Write documents 07–09**

Define calendar, festivals, religion, town law, social customs, language conventions, hand-painted Japanese Western fantasy direction, palette families, material vocabulary, and forbidden direct imitation.

- [ ] **Step 4: Write documents 10–12**

Define dark-fantasy content boundaries, non-permanent resident death, betrayal/capture/injury consequences, Canon governance, naming consistency, lore acceptance scenarios, and test traceability.

- [ ] **Step 5: Verify and commit world-design documents**

Run the twelve-file count, front-matter key check, stable-ID scan, `git diff --check`, explicit `git add -- docs/01-world-design`, and commit:

```powershell
git commit -m "docs: 完成世界与游戏设计规格"
```

### Task 3: Map, Space, and Navigation

**Files:**
- Create: `docs/02-map-navigation/01-world-coordinate-system.md`
- Create: `docs/02-map-navigation/02-region-topology.md`
- Create: `docs/02-map-navigation/03-ai-map-generation-spec.md`
- Create: `docs/02-map-navigation/04-map-layering.md`
- Create: `docs/02-map-navigation/05-walkable-area-definition.md`
- Create: `docs/02-map-navigation/06-collision-polygon-spec.md`
- Create: `docs/02-map-navigation/07-navigation-grid-pathfinding.md`
- Create: `docs/02-map-navigation/08-doors-entrances-interiors.md`
- Create: `docs/02-map-navigation/09-region-transitions.md`
- Create: `docs/02-map-navigation/10-dynamic-obstacle-updates.md`
- Create: `docs/02-map-navigation/11-camera-map-boundaries.md`
- Create: `docs/02-map-navigation/12-navigation-collision-tests.md`

**Interfaces:**
- Consumes: `DOC-FOUNDATION-005..006`, `DOC-WORLD-004`, `DOC-WORLD-009`
- Produces: `DOC-MAP-001..012`, coordinate types, walkability representation, Collision Polygon rules, navigation interfaces, entrance contracts, and acceptance maps.

- [ ] **Step 1: Write documents 01–03**

Specify world units, axes, origins, region dimensions, exit graph, indoor coordinates, image-generation prompt constraints, ground-art exclusions, scale, seams, and image acceptance.

- [ ] **Step 2: Write documents 04–06**

Specify the five layers, authoritative walkable representation, Polygon winding, boundaries, obstacle tags, road semantics, and rules preventing pixel-derived collision.

- [ ] **Step 3: Write documents 07–09**

Specify navigation grid resolution, A* costs, dynamic cost modifiers, path result types, entrance approach points, door reservations, indoor transfer, paired region exits, and failure recovery.

- [ ] **Step 4: Write documents 10–12**

Specify atomic navigation updates for construction and damage, camera clamping, map loading, debug overlays, unreachable-node audits, critical-route tests, and player/NPC parity.

- [ ] **Step 5: Verify and commit map documents**

Count twelve files, verify `REQ-MAP`, `DES-MAP`, `RULE-MAP`, and `TEST-MAP` references, check Mermaid fences, then commit explicitly with:

```powershell
git commit -m "docs: 完成地图空间与导航规格"
```

### Task 4: Rendering, Art, and Audio

**Files:**
- Create: `docs/03-rendering-art-audio/01-phaser-rendering-architecture.md`
- Create: `docs/03-rendering-art-audio/02-scene-lifecycle.md`
- Create: `docs/03-rendering-art-audio/03-map-compositing-pipeline.md`
- Create: `docs/03-rendering-art-audio/04-character-sprite-spec.md`
- Create: `docs/03-rendering-art-audio/05-animation-state-machine.md`
- Create: `docs/03-rendering-art-audio/06-structure-environment-rendering.md`
- Create: `docs/03-rendering-art-audio/07-day-night-weather-visuals.md`
- Create: `docs/03-rendering-art-audio/08-magic-combat-vfx.md`
- Create: `docs/03-rendering-art-audio/09-parchment-ui-visual-system.md`
- Create: `docs/03-rendering-art-audio/10-music-environment-audio.md`
- Create: `docs/03-rendering-art-audio/11-asset-manifest-fallbacks.md`
- Create: `docs/03-rendering-art-audio/12-performance-visual-qa.md`

**Interfaces:**
- Consumes: `DOC-WORLD-009`, `DOC-MAP-001..012`
- Produces: `DOC-RENDER-001..012`, scene contracts, asset IDs, animation mappings, UI tokens, audio states, fallback behavior, and rendering budgets.

- [ ] **Step 1: Write documents 01–03**

Define Phaser scenes, render layers, camera, lifecycle, asset loading, region unload, map slicing, composite order, deterministic depth sorting, and resize behavior.

- [ ] **Step 2: Write documents 04–06**

Define four-direction six-frame walking, Idle frames, portraits, combat sprites, animation state transitions, structure stages, occlusion, shadows, and missing-animation fallback.

- [ ] **Step 3: Write documents 07–09**

Define day/night lighting, weather overlays, VFX registration, reduced-motion behavior, resident HUD, dialogue layout, mayor layout, 720p/1080p constraints, and fullscreen prompts.

- [ ] **Step 4: Write documents 10–12**

Define area soundscapes, music layers, licensing fields, Asset Manifest, fallback resources, lazy loading, texture budgets, 60 FPS target, visual QA, and collision-overlay inspection.

- [ ] **Step 5: Verify and commit rendering documents**

Verify twelve files and all `asset_id`, `animation_id`, and `render` examples against canonical naming, then commit:

```powershell
git commit -m "docs: 完成渲染美术与音频规格"
```

### Task 5: Residents and Lifecycle

**Files:**
- Create: `docs/04-residents-lifecycle/01-resident-data-model.md`
- Create: `docs/04-residents-lifecycle/02-identity-race-appearance.md`
- Create: `docs/04-residents-lifecycle/03-personality-values.md`
- Create: `docs/04-residents-lifecycle/04-needs-emotions.md`
- Create: `docs/04-residents-lifecycle/05-skills-abilities.md`
- Create: `docs/04-residents-lifecycle/06-profession-residence.md`
- Create: `docs/04-residents-lifecycle/07-health-injury-illness.md`
- Create: `docs/04-residents-lifecycle/08-age-non-permanent-death.md`
- Create: `docs/04-residents-lifecycle/09-daily-life-structure.md`
- Create: `docs/04-residents-lifecycle/10-inventory-ownership.md`
- Create: `docs/04-residents-lifecycle/11-resident-creation-initialization.md`
- Create: `docs/04-residents-lifecycle/12-resident-system-tests.md`

**Interfaces:**
- Consumes: foundation, world, map, and rendering contracts.
- Produces: `DOC-RESIDENT-001..012`, Resident aggregate, traits, Needs, health states, schedules, initialization rules, and resident invariants.

- [ ] **Step 1: Write documents 01–03**

Specify the Resident aggregate, stable identity, appearance references, personality dimensions, values, preferences, fears, and rules preventing personality from becoming direct executable authority.

- [ ] **Step 2: Write documents 04–06**

Specify Needs thresholds, emotion state, skills, abilities, profession contracts, residence access, workplace membership, and role changes.

- [ ] **Step 3: Write documents 07–09**

Specify health, illness, injury, unconsciousness, aging without first-version permanent death, recovery, routine structure, interruptions, and long-action integration.

- [ ] **Step 4: Write documents 10–12**

Specify resident Inventory references, ownership boundaries, 8–12 resident initialization, required service coverage, validation, scenario fixtures, and acceptance tests.

- [ ] **Step 5: Verify and commit resident documents**

Verify twelve files and consistency with economy-owned item rules and combat-owned damage rules, then commit:

```powershell
git commit -m "docs: 完成居民与生命周期规格"
```

### Task 6: AI Decision and Model Orchestration

**Files:**
- Create: `docs/05-ai-orchestration/01-cognition-pipeline.md`
- Create: `docs/05-ai-orchestration/02-resident-visible-context.md`
- Create: `docs/05-ai-orchestration/03-prompt-layering.md`
- Create: `docs/05-ai-orchestration/04-action-proposal-schema.md`
- Create: `docs/05-ai-orchestration/05-tool-action-catalog.md`
- Create: `docs/05-ai-orchestration/06-daily-hourly-immediate-planning.md`
- Create: `docs/05-ai-orchestration/07-thinking-mode-routing.md`
- Create: `docs/05-ai-orchestration/08-token-cache-cost-control.md`
- Create: `docs/05-ai-orchestration/09-concurrency-request-scheduling.md`
- Create: `docs/05-ai-orchestration/10-action-validation-repair.md`
- Create: `docs/05-ai-orchestration/11-utility-ai-fallback.md`
- Create: `docs/05-ai-orchestration/12-ai-behavior-evaluation.md`

**Interfaces:**
- Consumes: Resident, world, map, time, memory, economy, magic, combat, and event read models.
- Produces: `DOC-AI-001..012`, `ActionProposal`, Prompt IDs, model request policy, validation outcomes, fallback behavior, and evaluation cases.

- [ ] **Step 1: Write documents 01–03**

Define cognition stages, subjective context filtering, context budgets, system/developer/world/resident Prompt layers, injection boundaries, and Prompt versioning.

- [ ] **Step 2: Write documents 04–06**

Define the complete `ActionProposal` JSON Schema, every first-version Action with parameters, Daily Plan, Hourly Intent, Immediate Action, abort conditions, and stale-plan behavior.

- [ ] **Step 3: Write documents 07–09**

Define explicit Thinking toggle behavior, `reasoning_effort`, JSON Output, discarded `reasoning_content`, Token budgets, cache keys, cost display, priorities, concurrency two, cancellation, and deadlines.

- [ ] **Step 4: Write documents 10–12**

Define repairable/replan/forbidden outcomes, local Utility AI survival actions, Tactical Utility AI, fixed evaluation scenarios, legality metrics, latency, repeated actions, personality consistency, and secret leakage tests.

- [ ] **Step 5: Verify and commit AI documents**

Check all model names and Base URLs against the official references in the design spec, ensure every Action has one canonical schema, then commit:

```powershell
git commit -m "docs: 完成 AI 决策与模型编排规格"
```

### Task 7: Memory and Social Relationships

**Files:**
- Create: `docs/06-memory-social/01-memory-data-model.md`
- Create: `docs/06-memory-social/02-memory-write-rules.md`
- Create: `docs/06-memory-social/03-relevant-memory-retrieval.md`
- Create: `docs/06-memory-social/04-memory-consolidation-summary.md`
- Create: `docs/06-memory-social/05-forgetting-importance-decay.md`
- Create: `docs/06-memory-social/06-multidimensional-relationships.md`
- Create: `docs/06-memory-social/07-social-graph.md`
- Create: `docs/06-memory-social/08-rumor-propagation.md`
- Create: `docs/06-memory-social/09-secrets-privacy.md`
- Create: `docs/06-memory-social/10-belief-objective-fact-separation.md`
- Create: `docs/06-memory-social/11-player-behavior-memory.md`
- Create: `docs/06-memory-social/12-memory-relationship-tests.md`

**Interfaces:**
- Consumes: Resident identity and Domain Event references.
- Produces: `DOC-SOCIAL-001..012`, Memory types, retrieval scores, relationship vector, Belief transfer, privacy gates, and social tests.

- [ ] **Step 1: Write documents 01–03**

Define Episodic Memory, Semantic Belief, Social Impression, Commitment, Routine Knowledge, provenance, write eligibility, and retrieval scoring.

- [ ] **Step 2: Write documents 04–06**

Define consolidation, cold storage, importance, forgetting, reactivation, and the five relationship dimensions `affection`, `trust`, `fear`, `respect`, and `intimacy`.

- [ ] **Step 3: Write documents 07–09**

Define Social Graph edges, faction overlays, rumor source chains, distortion, confidence, and `public`, `community`, `faction`, `relationship`, `personal`, `shared_secret` access levels.

- [ ] **Step 4: Write documents 10–12**

Define objective facts versus subjective beliefs, player action memory, mayor consequences, deletion behavior, access-control tests, propagation tests, and reload consistency.

- [ ] **Step 5: Verify and commit memory documents**

Verify twelve files, ensure secrets are filtered before Prompt construction, and commit:

```powershell
git commit -m "docs: 完成记忆与社会关系规格"
```

### Task 8: Time, Scheduling, and Simulation

**Files:**
- Create: `docs/07-time-simulation/01-game-time-model.md`
- Create: `docs/07-time-simulation/02-pause-speed-control.md`
- Create: `docs/07-time-simulation/03-simulation-tick.md`
- Create: `docs/07-time-simulation/04-resident-scheduler.md`
- Create: `docs/07-time-simulation/05-active-warm-background-tiers.md`
- Create: `docs/07-time-simulation/06-long-running-actions.md`
- Create: `docs/07-time-simulation/07-concurrent-action-conflicts.md`
- Create: `docs/07-time-simulation/08-world-periodic-updates.md`
- Create: `docs/07-time-simulation/09-closed-game-pause.md`
- Create: `docs/07-time-simulation/10-seed-reproducibility.md`
- Create: `docs/07-time-simulation/11-performance-load-budget.md`
- Create: `docs/07-time-simulation/12-time-simulation-tests.md`

**Interfaces:**
- Consumes: global time standard, Resident actions, AI deadlines, world services.
- Produces: `DOC-TIME-001..012`, clock API, event queue, simulation tiers, long-action lifecycle, Reservation policy, and performance targets.

- [ ] **Step 1: Write documents 01–03**

Define `RealTime`, `GameTime`, `TurnTime`, one-second-to-one-minute default, `0×/0.5×/1×/2×/4×`, 10 Hz World Tick, and 60 FPS separation.

- [ ] **Step 2: Write documents 04–06**

Define priority scheduling, AI request handling, Active/Warm/Background behavior, long-action lifecycle, progress, interruption, and recovery.

- [ ] **Step 3: Write documents 07–09**

Define resource Reservation, stable lock order, event queue, weather/economy intervals, dialogue pause, mayor pause, combat pause, shutdown pause, and restart behavior.

- [ ] **Step 4: Write documents 10–12**

Define Seed streams, recorded AI replay, load budgets, high-speed fallback, queue limits, deterministic tests, and simulation acceptance.

- [ ] **Step 5: Verify and commit time documents**

Verify every time unit and multiplier against foundation standards, then commit:

```powershell
git commit -m "docs: 完成时间调度与世界模拟规格"
```

### Task 9: Player and Mayor Modes

**Files:**
- Create: `docs/08-player-mayor/01-player-resident-creation.md`
- Create: `docs/08-player-mayor/02-player-movement-control.md`
- Create: `docs/08-player-mayor/03-resident-mayor-mode-switch.md`
- Create: `docs/08-player-mayor/04-player-interaction-capabilities.md`
- Create: `docs/08-player-mayor/05-natural-language-input.md`
- Create: `docs/08-player-mayor/06-player-world-impact.md`
- Create: `docs/08-player-mayor/07-resident-mode-permissions.md`
- Create: `docs/08-player-mayor/08-mayor-mode-permissions.md`
- Create: `docs/08-player-mayor/09-admin-command-audit.md`
- Create: `docs/08-player-mayor/10-camera-fullscreen-control.md`
- Create: `docs/08-player-mayor/11-input-guidance-accessibility.md`
- Create: `docs/08-player-mayor/12-player-system-acceptance.md`

**Interfaces:**
- Consumes: navigation, residents, rendering, social, economy, combat, events, backend permissions.
- Produces: `DOC-PLAYER-001..012`, `PlayerCommand`, input map, mode states, mayor capabilities, Admin audit, and acceptance flows.

- [ ] **Step 1: Write documents 01–03**

Define player identity, creation, keyboard input, authority reconciliation, collision parity, `Tab` switching, prohibited transition states, and pause semantics.

- [ ] **Step 2: Write documents 04–06**

Define interactions, natural-language entry, social/economic/political/spatial/conflict/narrative impact paths, and Domain Event causality.

- [ ] **Step 3: Write documents 07–09**

Define resident permissions, mayor governance, budget restrictions, inaccessible secrets, Sandbox Admin confirmation, save marking, and independent audit events.

- [ ] **Step 4: Write documents 10–12**

Define camera, fullscreen, responsive input prompts, rebinding, accessibility, failure recovery, E2E scenarios, and acceptance tests.

- [ ] **Step 5: Verify and commit player documents**

Verify player and AI rules share the same Domain validation except decision source, then commit:

```powershell
git commit -m "docs: 完成玩家与镇长模式规格"
```

### Task 10: Dialogue and Communication

**Files:**
- Create: `docs/09-dialogue/01-conversation-lifecycle.md`
- Create: `docs/09-dialogue/02-distance-participation-conditions.md`
- Create: `docs/09-dialogue/03-dialogue-context-construction.md`
- Create: `docs/09-dialogue/04-natural-language-intent.md`
- Create: `docs/09-dialogue/05-speech-act-model.md`
- Create: `docs/09-dialogue/06-emotion-tone.md`
- Create: `docs/09-dialogue/07-interruption-exit.md`
- Create: `docs/09-dialogue/08-group-dialogue.md`
- Create: `docs/09-dialogue/09-dialogue-relationship-effects.md`
- Create: `docs/09-dialogue/10-chinese-localization.md`
- Create: `docs/09-dialogue/11-dialogue-safety-content-boundaries.md`
- Create: `docs/09-dialogue/12-dialogue-system-tests.md`

**Interfaces:**
- Consumes: Player speech, AI context, memory, secrets, relationships, time pause, rendering.
- Produces: `DOC-DIALOGUE-001..012`, Conversation states, context schema, Speech Acts, group-turn policy, localization, and safety tests.

- [ ] **Step 1: Write documents 01–03**

Define start, active, awaiting-player, awaiting-model, interrupted, ended states; proximity, sight, participation, attention Reservation, and subjective context.

- [ ] **Step 2: Write documents 04–06**

Define natural-language intent boundaries, Speech Acts, response schema, emotion/tone display, refusal, lying, negotiation, and commitment creation.

- [ ] **Step 3: Write documents 07–09**

Define interruption priorities, cancellation, group dialogue turns, overhearing, memory writes, relationship deltas, and player influence.

- [ ] **Step 4: Write documents 10–12**

Define Chinese punctuation and terminology, text-as-data rendering, injection resistance, content boundaries, malicious-input fixtures, and E2E tests.

- [ ] **Step 5: Verify and commit dialogue documents**

Verify no dialogue path bypasses domain validation or secret access, then commit:

```powershell
git commit -m "docs: 完成对话与交流规格"
```

### Task 11: Economy, Jobs, and Items

**Files:**
- Create: `docs/10-economy-items/01-currency-system.md`
- Create: `docs/10-economy-items/02-professions-workplaces.md`
- Create: `docs/10-economy-items/03-work-schedules-income.md`
- Create: `docs/10-economy-items/04-item-data-model.md`
- Create: `docs/10-economy-items/05-inventory-rules.md`
- Create: `docs/10-economy-items/06-transaction-model.md`
- Create: `docs/10-economy-items/07-shops-services.md`
- Create: `docs/10-economy-items/08-pricing-model.md`
- Create: `docs/10-economy-items/09-basic-supply-demand.md`
- Create: `docs/10-economy-items/10-crafting-resource-consumption.md`
- Create: `docs/10-economy-items/11-property-building-ownership.md`
- Create: `docs/10-economy-items/12-economic-balance-tests.md`

**Interfaces:**
- Consumes: residents, time, map locations, AI Actions, building events.
- Produces: `DOC-ECON-001..012`, integer currency, Item ownership, Inventory, atomic Transaction, pricing, crafting, property, and balance tests.

- [ ] **Step 1: Write documents 01–03**

Define Silver Crown/Copper Feather integer units, profession contracts, workplaces, schedules, wages, role changes, and player jobs.

- [ ] **Step 2: Write documents 04–06**

Define Item kinds, provenance, unique ownership, containers, weight/slot limits, Reservation, Transaction states, idempotency, and rollback.

- [ ] **Step 3: Write documents 07–09**

Define shop inventory, staff, hours, services, bounded pricing formula, local information limits, production chains, demand windows, and shortage behavior.

- [ ] **Step 4: Write documents 10–12**

Define crafting inputs/outputs, failures, property deeds, public budget interactions, conservation audits, high-speed tests, and recovery tests.

- [ ] **Step 5: Verify and commit economy documents**

Run an explicit cross-reference audit against Resident Inventory mentions, then commit:

```powershell
git commit -m "docs: 完成经济职业与物品规格"
```

### Task 12: Magic

**Files:**
- Create: `docs/11-magic/01-magic-worldview.md`
- Create: `docs/11-magic/02-magic-schools.md`
- Create: `docs/11-magic/03-mana-recovery.md`
- Create: `docs/11-magic/04-spell-data-model.md`
- Create: `docs/11-magic/05-casting-legality.md`
- Create: `docs/11-magic/06-magic-learning-growth.md`
- Create: `docs/11-magic/07-resident-autonomous-casting.md`
- Create: `docs/11-magic/08-player-casting.md`
- Create: `docs/11-magic/09-magic-environment-interactions.md`
- Create: `docs/11-magic/10-magical-items.md`
- Create: `docs/11-magic/11-magic-vfx-audio.md`
- Create: `docs/11-magic/12-magic-balance-tests.md`

**Interfaces:**
- Consumes: world law, residents, AI Actions, items, map semantics, rendering.
- Produces: `DOC-MAGIC-001..012`, schools, Mana, `SpellDefinition`, legality, learning, environment effects, and tests.

- [ ] **Step 1: Write documents 01–03**

Define cosmology, Elemental/Restoration/Warding/Illusion/Spirit/Arcane schools, Mana units, regeneration, exhaustion, and world-law implications.

- [ ] **Step 2: Write documents 04–06**

Define complete `SpellDefinition`, target types, costs, range, requirements, registered effects, law checks, teachers, books, skill gates, and learning progress.

- [ ] **Step 3: Write documents 07–09**

Define AI spell choice, player commands, witness and reputation effects, fire, healing, purification, detection, light, reinforcement, anchors, illusion, and curse interfaces.

- [ ] **Step 4: Write documents 10–12**

Define magical-item ownership, charges, VFX/audio IDs, reduced effects, balance constraints, illegal teleport tests, and environment integration tests.

- [ ] **Step 5: Verify and commit magic documents**

Verify every spell effect is registered and no free-form effect can mutate the world, then commit:

```powershell
git commit -m "docs: 完成魔法系统规格"
```

### Task 13: Turn-Based Combat and Health

**Files:**
- Create: `docs/12-combat-health/01-encounter-trigger-rules.md`
- Create: `docs/12-combat-health/02-turn-order.md`
- Create: `docs/12-combat-health/03-combat-actions.md`
- Create: `docs/12-combat-health/04-combat-stats-formulas.md`
- Create: `docs/12-combat-health/05-status-effects.md`
- Create: `docs/12-combat-health/06-damage-healing.md`
- Create: `docs/12-combat-health/07-npc-tactical-decisions.md`
- Create: `docs/12-combat-health/08-player-combat-ui.md`
- Create: `docs/12-combat-health/09-escape-defeat-non-permanent-death.md`
- Create: `docs/12-combat-health/10-loot-consequences.md`
- Create: `docs/12-combat-health/11-combat-world-event-integration.md`
- Create: `docs/12-combat-health/12-combat-test-matrix.md`

**Interfaces:**
- Consumes: residents, items, magic, AI, time, rendering, events.
- Produces: `DOC-COMBAT-001..012`, Encounter state, legal turns, formulas, status registry, Tactical AI request, defeat, rewards, and tests.

- [ ] **Step 1: Write documents 01–03**

Define encounter sources, participant locks, four-character party limit, front/rear positions, turn lifecycle, legal actions, surrender, negotiation, and escape.

- [ ] **Step 2: Write documents 04–06**

Define HP/MP/Strength/Defense/Magic/Resistance/Agility/Focus, deterministic formulas, Seed random rolls, status stacking, damage, healing, and post-battle persistence.

- [ ] **Step 3: Write documents 07–09**

Define one model decision per AI turn, legal-action context, Tactical Utility fallback, player UI, browser refresh, unconsciousness, injury, capture, retreat, and rescue.

- [ ] **Step 4: Write documents 10–12**

Define loot provenance, equipment damage, social and event consequences, Overworld pause, result transaction, idempotency, combat fixtures, and complete test matrix.

- [ ] **Step 5: Verify and commit combat documents**

Verify models never determine numeric outcomes and formal residents are not permanently deleted, then commit:

```powershell
git commit -m "docs: 完成回合制战斗与健康规格"
```

### Task 14: Events, Quests, Buildings, and Environment

**Files:**
- Create: `docs/13-events-building-environment/01-world-event-engine.md`
- Create: `docs/13-events-building-environment/02-event-trigger-conditions.md`
- Create: `docs/13-events-building-environment/03-ai-event-director.md`
- Create: `docs/13-events-building-environment/04-quest-lifecycle.md`
- Create: `docs/13-events-building-environment/05-event-consequence-propagation.md`
- Create: `docs/13-events-building-environment/06-weather-natural-environment.md`
- Create: `docs/13-events-building-environment/07-building-data-model.md`
- Create: `docs/13-events-building-environment/08-building-placement-rules.md`
- Create: `docs/13-events-building-environment/09-construction-upgrades.md`
- Create: `docs/13-events-building-environment/10-destruction-repair.md`
- Create: `docs/13-events-building-environment/11-world-diff-map-sync.md`
- Create: `docs/13-events-building-environment/12-event-building-recovery-tests.md`

**Interfaces:**
- Consumes: world, AI, map, time, residents, economy, magic, combat.
- Produces: `DOC-EVENT-001..012`, Event Template, Event lifecycle, Quest objectives, weather, Building aggregate, World Diff, and recovery tests.

- [ ] **Step 1: Write documents 01–03**

Define DomainEvent/WorldEvent/Quest separation, lifecycle, triggers, conflict rules, Narrative Pressure Budget, AI Director input/output, template-only authority, and Thinking usage.

- [ ] **Step 2: Write documents 04–06**

Define Quest states, structured objectives, AI resident participation, failure, deadlines, consequences, seeded weather, hazards, visuals, navigation, and economy effects.

- [ ] **Step 3: Write documents 07–09**

Define Building aggregate, stages, Footprint, entrances, ownership, placement validation, required routes, resources, labor, progression, and upgrades.

- [ ] **Step 4: Write documents 10–12**

Define damage, rubble, repair, atomic map sync, append-only World Diff, reverse changes, interrupted recovery, duplicate-event prevention, and scenario tests.

- [ ] **Step 5: Verify and commit event/building documents**

Verify no AI Director output can directly mutate the database and every map change references navigation rules, then commit:

```powershell
git commit -m "docs: 完成事件建筑与环境规格"
```

### Task 15: Backend, API, and Security

**Files:**
- Create: `docs/14-backend-api-security/01-fastapi-service-architecture.md`
- Create: `docs/14-backend-api-security/02-domain-module-boundaries.md`
- Create: `docs/14-backend-api-security/03-websocket-lifecycle.md`
- Create: `docs/14-backend-api-security/04-rest-api.md`
- Create: `docs/14-backend-api-security/05-command-protocol.md`
- Create: `docs/14-backend-api-security/06-domain-event-protocol.md`
- Create: `docs/14-backend-api-security/07-schema-versioning.md`
- Create: `docs/14-backend-api-security/08-local-session-permissions.md`
- Create: `docs/14-backend-api-security/09-deepseek-key-protection.md`
- Create: `docs/14-backend-api-security/10-transaction-idempotency.md`
- Create: `docs/14-backend-api-security/11-error-codes-recovery.md`
- Create: `docs/14-backend-api-security/12-performance-logging-tests.md`

**Interfaces:**
- Consumes: all Domain commands, events, schemas, persistence, rendering needs.
- Produces: `DOC-BACKEND-001..012`, REST routes, WebSocket frames, Command/Event envelopes, protocol versioning, local security, errors, and diagnostics.

- [ ] **Step 1: Write documents 01–03**

Define FastAPI process, static hosting, module boundaries, allowed dependency direction, async queues, WebSocket Ticket, heartbeat, reconnect, Revision catch-up, and Snapshot fallback.

- [ ] **Step 2: Write documents 04–06**

Define every REST endpoint, request/response schemas, Command Envelope, Event Envelope, causation, correlation, render payload, authorization, and validation order.

- [ ] **Step 3: Write documents 07–09**

Define protocol compatibility, migrations, loopback binding, Origin/Host checks, SameSite Session, CORS, rate/body limits, Windows Credential Manager or DPAPI, and secret redaction.

- [ ] **Step 4: Write documents 10–12**

Define transaction/idempotency behavior, error-code registry, model/network/storage failures, backpressure, safe shutdown, local metrics, structured logs, security fixtures, and load tests.

- [ ] **Step 5: Verify and commit backend documents**

Verify every API schema has a version and every sensitive field has an explicit log policy, then commit:

```powershell
git commit -m "docs: 完成后端 API 与安全规格"
```

### Task 16: Persistence, Startup, Release, and Quality

**Files:**
- Create: `docs/15-persistence-release-quality/01-sqlite-data-model.md`
- Create: `docs/15-persistence-release-quality/02-database-migrations.md`
- Create: `docs/15-persistence-release-quality/03-snapshot-event-log.md`
- Create: `docs/15-persistence-release-quality/04-auto-manual-saves.md`
- Create: `docs/15-persistence-release-quality/05-multi-world-management.md`
- Create: `docs/15-persistence-release-quality/06-backup-corruption-recovery.md`
- Create: `docs/15-persistence-release-quality/07-configuration-secret-management.md`
- Create: `docs/15-persistence-release-quality/08-double-click-launcher.md`
- Create: `docs/15-persistence-release-quality/09-bundled-runtime-release-package.md`
- Create: `docs/15-persistence-release-quality/10-logging-diagnostics-package.md`
- Create: `docs/15-persistence-release-quality/11-project-test-strategy.md`
- Create: `docs/15-persistence-release-quality/12-release-acceptance-checklist.md`

**Interfaces:**
- Consumes: all state, Event, schema, security, frontend asset, and test requirements.
- Produces: `DOC-RELEASE-001..012`, database layout, WAL policy, saves, worlds, backups, Launcher, package, diagnostics, test strategy, and release Gate.

- [ ] **Step 1: Write documents 01–03**

Define `app.sqlite3`, per-world `world.sqlite3`, normalized state, append-only events, Snapshots, Revision, WAL, foreign keys, single writer, and checkpoints.

- [ ] **Step 2: Write documents 04–06**

Define five automatic recovery points, three manual slots, branch-on-load, multi-world metadata, export/import, recoverable deletion, migration backups, corruption triage, and disk-full behavior.

- [ ] **Step 3: Write documents 07–09**

Define non-sensitive configuration, Windows Secret storage, user-data path, release directory, Batch launcher, single instance, random port, health polling, tray behavior, bundled Python, and no player Node dependency.

- [ ] **Step 4: Write documents 10–12**

Define redacted diagnostics, test layers, FakeModelProvider, AI evaluations, 1/7/30-day simulation, browser E2E, visual QA, packaged-release validation, and exact G9 checklist.

- [ ] **Step 5: Verify and commit persistence/release documents**

Verify Windows Chinese/space path cases, no Key storage in SQLite, and exact save counts, then commit:

```powershell
git commit -m "docs: 完成存档启动与发布质量规格"
```

### Task 17: Corpus-Wide Traceability and Consistency Audit

**Files:**
- Modify: `docs/00-foundation/07-requirement-design-test-traceability.md`
- Modify: `docs/00-foundation/08-document-index-reading-order.md`
- Modify: any corpus document with a discovered inconsistency

**Interfaces:**
- Consumes: all 188 corpus documents.
- Produces: complete traceability, final document counts, resolved cross-domain links, and an implementation-ready corpus.

- [ ] **Step 1: Verify exact document counts**

Run:

```powershell
$foundationCount = @(Get-ChildItem -LiteralPath docs/00-foundation -File -Filter *.md).Count
$subsystemDirectories = Get-ChildItem -LiteralPath docs -Directory |
  Where-Object { $_.Name -match '^(0[1-9]|1[0-5])-' }
$subsystemCounts = $subsystemDirectories | ForEach-Object {
  [pscustomobject]@{
    Directory = $_.Name
    Count = @(Get-ChildItem -LiteralPath $_.FullName -File -Filter *.md).Count
  }
}
if ($foundationCount -ne 8) { throw "Foundation count is $foundationCount" }
if ($subsystemDirectories.Count -ne 15) { throw "Subsystem directory count is $($subsystemDirectories.Count)" }
if (@($subsystemCounts | Where-Object Count -ne 12).Count -ne 0) {
  $subsystemCounts | Format-Table
  throw "Each subsystem must contain 12 documents"
}
$total = $foundationCount + ($subsystemCounts | Measure-Object Count -Sum).Sum
if ($total -ne 188) { throw "Corpus count is $total" }
"Corpus count: $total"
```

Expected: `Corpus count: 188`.

- [ ] **Step 2: Scan unresolved language and deprecated model names**

Run:

```powershell
$redFlags = @(
  ('T' + 'BD'),
  ('T' + 'ODO'),
  '待补充',
  '稍后实现',
  ('deepseek-' + 'chat'),
  ('deepseek-' + 'reasoner')
)
$corpusDirectories = @(
  'docs/00-foundation',
  'docs/01-world-design',
  'docs/02-map-navigation',
  'docs/03-rendering-art-audio',
  'docs/04-residents-lifecycle',
  'docs/05-ai-orchestration',
  'docs/06-memory-social',
  'docs/07-time-simulation',
  'docs/08-player-mayor',
  'docs/09-dialogue',
  'docs/10-economy-items',
  'docs/11-magic',
  'docs/12-combat-health',
  'docs/13-events-building-environment',
  'docs/14-backend-api-security',
  'docs/15-persistence-release-quality'
)
$matches = Get-ChildItem -LiteralPath $corpusDirectories -File -Recurse |
  Select-String -SimpleMatch -Pattern $redFlags
if ($matches) {
  $matches
  throw 'Unresolved or deprecated text found in corpus'
}
```

Expected: no matches.

- [ ] **Step 3: Validate required front matter and section headings**

Use a PowerShell loop over the sixteen explicit corpus directories. For every Markdown file, assert that the first line is `---`, all nine required front-matter keys exist, and headings `## 1.` through `## 12.` each occur exactly once. Print the exact failing path and missing key or heading, then fix every failure.

- [ ] **Step 4: Validate Markdown structure**

For every corpus file, count fenced-code markers and require an even count. Group headings within each file and reject duplicate full heading lines. Run `git diff --check` over the sixteen corpus directories.

- [ ] **Step 5: Audit stable IDs**

Extract all `REQ-`, `DES-`, `RULE-`, `TEST-`, and `DOC-` identifiers. Verify canonical definitions are unique, every cross-reference resolves, each Must requirement has at least one design ID and test ID, and no domain uses another domain's prefix for a competing definition.

- [ ] **Step 6: Audit schemas and protocol names**

Compare all JSON examples and tables for `ActionProposal`, `PlayerCommand`, `DomainEvent`, `WorldEvent`, `Quest`, `WorldDiff`, `Revision`, `Reservation`, `Snapshot`, `SpellDefinition`, `EncounterState`, and Item ownership. Fix field-name, type, unit, enum, and version differences at their canonical owner.

- [ ] **Step 7: Audit cross-system invariants**

Trace each invariant through map movement, AI Actions, player commands, economy, magic, combat, events, persistence, API, and recovery. Resolve any rule that permits negative inventory, duplicate ownership, unauthorized secrets, illegal position, repeated commands, non-monotonic Revision, or permanent deletion of a formal resident.

- [ ] **Step 8: Complete traceability and index**

Update `07-requirement-design-test-traceability.md` so every Must requirement has canonical design and test coverage. Update `08-document-index-reading-order.md` so all 188 entries are marked `approved-for-implementation`, links resolve, canonical owners are listed, and counts equal 188.

- [ ] **Step 9: Commit the audited corpus**

Run:

```powershell
git diff --check -- docs
git add -- docs/00-foundation docs/01-world-design docs/02-map-navigation `
  docs/03-rendering-art-audio docs/04-residents-lifecycle `
  docs/05-ai-orchestration docs/06-memory-social docs/07-time-simulation `
  docs/08-player-mayor docs/09-dialogue docs/10-economy-items `
  docs/11-magic docs/12-combat-health docs/13-events-building-environment `
  docs/14-backend-api-security docs/15-persistence-release-quality
git commit -m "docs: 完成 AI 小镇全量规格审计"
```

Expected: a commit containing only audited corpus changes.

### Task 18: One-Time Documentation Acceptance Handoff

**Files:**
- Read: all 188 corpus documents
- Read: `docs/superpowers/specs/2026-07-26-ai-town-system-design.md`
- Read: `docs/superpowers/plans/2026-07-26-ai-town-documentation-corpus.md`

**Interfaces:**
- Consumes: completed and audited corpus.
- Produces: one user-facing acceptance package and the G3/G4 evidence needed for G5.

- [ ] **Step 1: Capture final evidence**

Record the exact 188-file count, latest commit hashes, clean Git status, placeholder scan result, ID audit result, link audit result, traceability coverage, and a concise list of all fifteen domains.

- [ ] **Step 2: Prepare the single acceptance summary**

Provide links to the foundation index, traceability matrix, each of the fifteen subsystem directories, the design spec, and this plan. Summarize resolved risks, any explicit limitations retained from the design, and the evidence for G3 and G4.

- [ ] **Step 3: Request one user review**

Ask the user to review the complete corpus once. Do not request per-document, per-directory, or per-commit approval. Do not start formal map generation or game implementation until the user approves G5.

## Post-Corpus Planning Rule

After G5, create separate implementation plans for bounded software increments rather than one monolithic game plan. The minimum sequence is:

1. Foundation schemas, World Runtime, persistence, and FakeModelProvider.
2. Map/navigation and minimal Phaser player movement.
3. Residents, time, AI orchestration, memory, and dialogue.
4. Economy, items, buildings, events, weather, magic, and combat.
5. Formal image assets, audio, UI polish, release packaging, and full acceptance.

Each software plan must use TDD, exact file paths, executable test commands, and its own user-approved scope. This documentation plan authorizes no game implementation.

# P17 前端渲染系统补全实施计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development` 执行本计划。
> 主 agent 负责共享契约与最终集成；3 个 subagent 只能修改被分配的独立文件。

**目标：** 补齐 `docs/03-rendering-art-audio/` 对应的 14 个纯逻辑渲染模块，
覆盖 `TEST-RENDER-001`～`TEST-RENDER-012`，并将关键契约接入现有 Phaser
运行时。

**架构：** 所有规则计算放在无 Phaser 依赖的 `frontend/src/render/` 模块中；
Scene 和 DOM Bridge 只负责消费决策结果。Snapshot/Event 先经过协议、Revision
和事务门，再原子更新投影。

**技术栈：** TypeScript 5.3、Vitest 1.6、Phaser 3.80、Vite 5。

---

## 文件所有权

### 主 agent

- 修改：`frontend/src/render/protocol.ts`
- 修改：`frontend/src/render/snapshot_gate.ts`
- 创建：`frontend/src/render/manifest.ts`
- 创建：`frontend/src/render/ui_layout.ts`
- 创建：`frontend/src/render/perf.ts`
- 创建：`frontend/src/render/__tests__/protocol_snapshot.test.ts`
- 创建：`frontend/src/render/__tests__/manifest.test.ts`
- 创建：`frontend/src/render/__tests__/ui_layout.test.ts`
- 创建：`frontend/src/render/__tests__/perf.test.ts`
- 修改：`frontend/src/types/rendering.ts`
- 修改：`frontend/src/scenes/WorldScene.ts`
- 修改：`frontend/src/scenes/UIScene.ts`
- 修改：`frontend/src/ui/PhaserDomBridge.ts`
- 修改：`frontend/src/utils/SpriteLoader.ts`
- 修改：`frontend/index.html`
- 必要时修改现有 Scene/UI 测试。

### subagent A

- 创建：`frontend/src/render/event_sequencer.ts`
- 创建：`frontend/src/render/scene_lifecycle.ts`
- 创建：`frontend/src/render/map_slices.ts`
- 创建：`frontend/src/render/__tests__/event_sequencer.test.ts`
- 创建：`frontend/src/render/__tests__/scene_lifecycle.test.ts`
- 创建：`frontend/src/render/__tests__/map_slices.test.ts`

### subagent B

- 创建：`frontend/src/render/animation_sm.ts`
- 创建：`frontend/src/render/sprite_lint.ts`
- 创建：`frontend/src/render/structures.ts`
- 创建：`frontend/src/render/__tests__/animation_sm.test.ts`
- 创建：`frontend/src/render/__tests__/sprite_lint.test.ts`
- 创建：`frontend/src/render/__tests__/structures.test.ts`

### subagent C

- 创建：`frontend/src/render/environment.ts`
- 创建：`frontend/src/render/vfx.ts`
- 创建：`frontend/src/render/audio_state.ts`
- 创建：`frontend/src/render/__tests__/environment.test.ts`
- 创建：`frontend/src/render/__tests__/vfx.test.ts`
- 创建：`frontend/src/render/__tests__/audio_state.test.ts`

所有 subagent 禁止修改 `types/rendering.ts`、Scene、DOM、HTML、配置、锁文件和
Git 状态。需要共享类型时在自己的模块中定义最小导出类型，汇合时由主 agent
统一收敛。

---

## 任务 1：公共协议与 Snapshot Gate

**文件：**

- 修改：`frontend/src/render/protocol.ts`
- 修改：`frontend/src/render/snapshot_gate.ts`
- 创建：`frontend/src/render/__tests__/protocol_snapshot.test.ts`

- [ ] **步骤 1：编写协议与 Snapshot 失败测试**

测试至少覆盖：

```ts
it('rejects non-finite coordinates without partial acceptance', () => {
  const frame = makeFrame({ camera_target: { scene_id: SCENE_ID, x_wu: NaN, y_wu: 0 } });
  expect(validateRenderFrameInput(frame)).toMatchObject({ ok: false });
});

it('treats same revision and same hash as idempotent replay', () => {
  const gate = new SnapshotGate(WORLD_ID, SCENE_ID);
  expect(gate.evaluate(makeFrame({ revision: 7, snapshot_id: 'a' })).action).toBe('apply');
  expect(gate.evaluate(makeFrame({ revision: 7, snapshot_id: 'b' })).action)
    .toBe('idempotent_replay');
});

it('rejects nested WorldPoint from another scene', () => {
  const frame = makeFrame({
    entities: [makeEntity({ world_point: { scene_id: 'other', x_wu: 0, y_wu: 0 } })],
  });
  expect(validateRenderFrameInput(frame).ok).toBe(false);
});
```

- [ ] **步骤 2：运行聚焦测试并确认 Red**

```powershell
cd D:\dream\JT_AI\AI_Town\frontend
node node_modules/vitest/vitest.mjs run src/render/__tests__/protocol_snapshot.test.ts
```

预期：至少因嵌套 `scene_id` 未与 envelope 对齐或目标行为缺失而失败。

- [ ] **步骤 3：最小修正协议校验**

保持现有 public API；补充：

- camera/entity WorldPoint 的 `scene_id === frame.scene_id`；
- Event payload 中存在 WorldPoint 时同样校验；
- `quantizeWu` 对非有限数不返回可应用值；
- Snapshot 同 Revision 冲突保持 fail closed。

- [ ] **步骤 4：运行聚焦测试确认 Green**

运行步骤 2 命令，预期全部通过。

---

## 任务 2：Event 定序、Scene 生命周期与地图切片（subagent A）

**文件：**

- 创建：`frontend/src/render/event_sequencer.ts`
- 创建：`frontend/src/render/scene_lifecycle.ts`
- 创建：`frontend/src/render/map_slices.ts`
- 创建对应 3 个测试文件。

- [ ] **步骤 1：EventSequencer Red**

期望 API：

```ts
const sequencer = new EventSequencer(WORLD_ID, SCENE_ID, { now: () => now });
sequencer.onSnapshotApplied(10);
expect(sequencer.ingest(makeEvent({ revision: 11, index: 1, count: 2 })).status)
  .toBe('waiting_transaction');
expect(sequencer.ingest(makeEvent({ revision: 11, index: 0, count: 2 })).applied)
  .toHaveLength(2);
```

覆盖：

- `(world_id,event_id)` 去重；
- 10,000 ID LRU；
- 30 分钟 TTL；
- transaction count/index 一致性；
- 按 index、event_id 排序；
- stale 丢弃；
- Revision gap 请求重同步；
- Snapshot 后清理 pending。

- [ ] **步骤 2：运行 EventSequencer 测试确认 Red**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/event_sequencer.test.ts
```

- [ ] **步骤 3：实现 EventSequencer 并确认 Green**

只在事务收齐时返回可应用 events；任何 contract error 都不得返回部分 events。

- [ ] **步骤 4：SceneLifecycle Red**

覆盖：

- 缺字段拒绝并保留当前 Scene；
- 同时最多一个 load job；
- 更高 Revision 取消旧 job；
- 三次失败回退最后确认 Scene 并请求 Snapshot；
- 5,000 ms Warm Dispose；
- 5 秒内同 ID 回退复用。

- [ ] **步骤 5：实现 SceneLifecycle 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/scene_lifecycle.test.ts
```

- [ ] **步骤 6：MapSlices Red**

覆盖：

- viewport/zoom 到 world bounds；
- 负 slice index 剔除；
- visible range 外扩一圈并 clamp；
- `>20` cells 或 `>160 MiB` 切换 LOD1；
- LOD1 仍超预算返回 failure；
- 3840×2160、zoom 0.75/2.0、Scene edge。

- [ ] **步骤 7：实现 MapSlices 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/map_slices.test.ts
```

- [ ] **步骤 8：运行 A 组测试**

```powershell
node node_modules/vitest/vitest.mjs run `
  src/render/__tests__/event_sequencer.test.ts `
  src/render/__tests__/scene_lifecycle.test.ts `
  src/render/__tests__/map_slices.test.ts
```

---

## 任务 3：Sprite、动画与 Structure（subagent B）

**文件：**

- 创建：`frontend/src/render/animation_sm.ts`
- 创建：`frontend/src/render/sprite_lint.ts`
- 创建：`frontend/src/render/structures.ts`
- 创建对应 3 个测试文件。

- [ ] **步骤 1：AnimationMachine Red**

覆盖：

```ts
expect(priorityOf('downed')).toBeGreaterThan(priorityOf('hurt'));
expect(priorityOf('hurt')).toBeGreaterThan(priorityOf('attack'));
expect(priorityOf('attack')).toBe(priorityOf('cast'));
```

以及：

- 同优先级仅更新 Revision 覆盖；
- 旧 Revision 不覆盖；
- attack/cast/hurt 最长 900 ms；
- 回到最新权威 idle/walk；
- fallback：目标动画 → 同方向 idle → south idle；
- 缺失诊断按 `(asset_id,scene_id)` 只发一次。

- [ ] **步骤 2：实现 AnimationMachine 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/animation_sm.test.ts
```

- [ ] **步骤 3：SpriteLint Red**

覆盖 Stable Catalog ID、四方向、每方向 6 walk 帧、正整数 frame size、
anchor `{x: 0.5, y: 1}` 和 locale 文案 ID 拒绝。

- [ ] **步骤 4：实现 SpriteLint 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/sprite_lint.test.ts
```

- [ ] **步骤 5：Structure Red**

覆盖：

- stage 只能由确认投影生成 transition plan；
- 同 `building_id` 所有 visible pieces 单次替换；
- 缺资源保留上一 stage 并产生 fallback notice；
- shadow depth 在 ground 与 entity 之间；
- occluder alpha 为 0.45；
- stage 计划不包含 collision 写入。

- [ ] **步骤 6：实现 Structure 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/structures.test.ts
```

- [ ] **步骤 7：运行 B 组测试**

```powershell
node node_modules/vitest/vitest.mjs run `
  src/render/__tests__/animation_sm.test.ts `
  src/render/__tests__/sprite_lint.test.ts `
  src/render/__tests__/structures.test.ts
```

---

## 任务 4：Environment、VFX 与 Audio（subagent C）

**文件：**

- 创建：`frontend/src/render/environment.ts`
- 创建：`frontend/src/render/vfx.ts`
- 创建：`frontend/src/render/audio_state.ts`
- 创建对应 3 个测试文件。

- [ ] **步骤 1：Environment Red**

覆盖：

- `game_time mod 1440`；
- 300/420/1080/1200/0 边界；
- 0～1439 每分钟恰好匹配一个 band；
- smoothstep `t*t*(3-2*t)`；
- registry ID/hash/band mismatch 保留上一有效 state；
- mismatch 输出 `RENDER_LIGHTING_REGISTRY_MISMATCH` 与 resync；
- 未知 weather 降级 `weather.clear`；
- intensity clamp；
- Reduced Motion 不生成粒子、flash、shake。

- [ ] **步骤 2：实现 Environment 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/environment.test.ts
```

- [ ] **步骤 3：VFX Red**

覆盖 duration 100～1500、attach point、event 去重、到期回收、Scene dispose、
96 上限、关键战斗效果优先、未知资源 fallback 与 Reduced Motion。

- [ ] **步骤 4：实现 VFX 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/vfx.test.ts
```

- [ ] **步骤 5：Audio Red**

覆盖：

- Scene/Weather/Band/Encounter projection 派生；
- 500 ms crossfade；
- 每类 layer 单实例；
- bus 并发上限 8；
- autoplay blocked 保留目标 state；
- asset → LicenseRecord → license text path/hash 全链。

- [ ] **步骤 6：实现 Audio 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/audio_state.test.ts
```

- [ ] **步骤 7：运行 C 组测试**

```powershell
node node_modules/vitest/vitest.mjs run `
  src/render/__tests__/environment.test.ts `
  src/render/__tests__/vfx.test.ts `
  src/render/__tests__/audio_state.test.ts
```

---

## 任务 5：Asset Manifest

**文件：**

- 创建：`frontend/src/render/manifest.ts`
- 创建：`frontend/src/render/__tests__/manifest.test.ts`

- [ ] **步骤 1：编写 schema 与 lint Red**

覆盖：

- exact `$id`；
- root/definitions/required/type/pattern/enum/additionalProperties；
- URI/date-time format assertion；
- Stable Catalog ID、规范相对 path；
- asset/path/license 唯一；
- license foreign key、terms allowlist；
- 实际 SHA-256 与 byte length；
- required group fallback；
- fallback DAG cycle；
- ground/structure 与规则层边界；
- 14 个稳定诊断码及 JSON Pointer。

- [ ] **步骤 2：运行测试确认 Red**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/manifest.test.ts
```

- [ ] **步骤 3：实现零依赖 validator 与五步 lint**

不引入 Ajv。只实现 canonical schema 实际使用的 JSON Schema 关键字，拒绝未知
或未实现的 schema 行为，不静默放行。

- [ ] **步骤 4：运行测试确认 Green**

运行步骤 2 命令。

---

## 任务 6：UI Layout 与 Performance

**文件：**

- 创建：`frontend/src/render/ui_layout.ts`
- 创建：`frontend/src/render/perf.ts`
- 创建对应 2 个测试文件。

- [ ] **步骤 1：UiLayout Red**

覆盖：

- 720p Safe Area 16 px、1080p 24 px；
- compact 阈值；
- text scale 不超过 1.25；
- modal/focus 阻止 world keyboard/pointer；
- listener cleanup 后恢复；
- fullscreen target 仅 `game-shell`；
- 无 user gesture 拒绝 fullscreen。

- [ ] **步骤 2：实现 UiLayout 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/ui_layout.test.ts
```

- [ ] **步骤 3：Performance Red**

覆盖：

- nearest-rank `ceil(p*N)-1`；
- p95 ≤16.67 ms、p99 ≤25 ms；
- 三 iteration 独立判定；
- 未压缩纹理 mip 链；
- block-compressed `ceil(width/blockWidth)`；
- shared texture 去重；
- 1.10 margin；
- 总预算 ≤268,435,456 bytes；
- context loss 后 ledger 重建。

- [ ] **步骤 4：实现 Performance 并确认 Green**

```powershell
node node_modules/vitest/vitest.mjs run src/render/__tests__/perf.test.ts
```

---

## 任务 7：汇合审查与公共类型收敛

**文件：**

- 修改：`frontend/src/types/rendering.ts`
- 审查全部 `frontend/src/render/*.ts`

- [ ] **步骤 1：逐组审查文件边界**

确认：

- subagent 未修改越界文件；
- 无重复公共类型冲突；
- reason code 与文档一致；
- 所有模块无 Phaser import；
- 每个新增 public function 都有直接测试。

- [ ] **步骤 2：最小扩展共享类型**

动画状态从既有集合兼容扩展到：

```ts
export type RenderAnimationState =
  | 'idle'
  | 'walk'
  | 'work'
  | 'combat'
  | 'cast'
  | 'attack'
  | 'hurt'
  | 'downed';
```

只把运行时集成所需的公共 envelope/projection 类型上移；其余保留模块局部。

- [ ] **步骤 3：运行全部 render 测试**

```powershell
node node_modules/vitest/vitest.mjs run src/render
```

预期：全部通过。

---

## 任务 8：Phaser 与 DOM 集成

**文件：**

- 修改：`frontend/src/scenes/WorldScene.ts`
- 修改：`frontend/src/scenes/UIScene.ts`
- 修改：`frontend/src/ui/PhaserDomBridge.ts`
- 修改：`frontend/src/utils/SpriteLoader.ts`
- 修改：`frontend/index.html`
- 必要时修改现有 Scene/UI 测试。

- [ ] **步骤 1：先写集成 Red**

在现有测试中增加：

- WorldScene 不应用 stale/duplicate/gap/未收齐事务；
- Snapshot apply 清理旧 pending；
- modal 激活时 world input 被抑制；
- fullscreen target 为 `game-shell`；
- Sprite fallback 采用 lint/animation 结果。

- [ ] **步骤 2：运行现有 Scene/UI 测试确认 Red**

```powershell
node node_modules/vitest/vitest.mjs run `
  src/scenes/__tests__/WorldScene.test.ts `
  src/scenes/__tests__/UIScene.test.ts `
  src/core/__tests__/integration.test.ts
```

- [ ] **步骤 3：接入 WorldScene**

WorldScene 只负责：

- 将 Snapshot 送入 `SnapshotGate`；
- 将 Event 送入 `EventSequencer`；
- 对 `applied` 的完整事务调用现有实体更新函数；
- gap/mismatch 通过 EventBus 发出 resync 请求；
- Scene shutdown 时 dispose VFX/sequence state。

- [ ] **步骤 4：接入 UI 与 DOM**

- `#game-shell` 包裹 `#game-container` 与 `#ui-overlay`；
- modal/focus 状态驱动 `UiInputGate`；
- fullscreen 只操作 `#game-shell`；
- listener 在 shutdown/destroy 时清理。

- [ ] **步骤 5：修复两个基线 TS6133**

- `PhaserDomBridge.ts` 的 `gameTime`：若 UI 确需展示则使用；否则删除参数并同步调用方。
- `SpriteLoader.ts` 的 `atlasConfig`：若无行为需求则删除无用变量，不用假读取规避检查。

- [ ] **步骤 6：运行集成测试确认 Green**

运行步骤 2 命令，预期全部通过。

---

## 任务 9：完整验证

- [ ] **步骤 1：完整 Vitest**

```powershell
cd D:\dream\JT_AI\AI_Town\frontend
node node_modules/vitest/vitest.mjs run
```

预期：既有 34 项与新增测试全部通过，无 unhandled error。

- [ ] **步骤 2：TypeScript typecheck**

```powershell
node node_modules/typescript/bin/tsc --noEmit
```

预期：exit code 0，无 TS6133。

- [ ] **步骤 3：Build typecheck**

```powershell
node node_modules/typescript/bin/tsc -p tsconfig.build.json
```

预期：exit code 0。

- [ ] **步骤 4：Production build**

```powershell
node node_modules/vite/bin/vite.js build
```

预期：exit code 0，生成 `frontend/dist/`；不把构建产物加入提交范围。

- [ ] **步骤 5：范围审查**

```powershell
git status --short
git diff --stat
git diff --check
```

确认：

- `testing-self-study/` 未被修改；
- 后端变化仅限后续 Launcher/Release 收尾所需契约与测试；
- 无锁文件、依赖或无关格式化变化；
- Kimi 的两个未跟踪文件已纳入 P17 diff；
- 按用户后续指令由主 agent 完成统一验证与提交。
